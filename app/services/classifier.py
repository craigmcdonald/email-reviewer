"""Classify incoming emails as auto-replies or real emails using pattern matching and Haiku."""

import asyncio
import json
import logging
import re

from anthropic import AsyncAnthropic, RateLimitError
from sqlalchemy import JSON, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email import Email
from app.models.settings import CLASSIFIER_DIMENSIONS, Settings, assemble_prompt
from app.services.settings import get_settings

logger = logging.getLogger(__name__)

MAX_BODY_LENGTH = 2000
MAX_RATE_LIMIT_RETRIES = 5
DEFAULT_RETRY_AFTER = 60

SUBJECT_PATTERNS = [
    re.compile(r"^Automatic reply:", re.IGNORECASE),
    re.compile(r"^Out of Office:", re.IGNORECASE),
    re.compile(r"^OOO:", re.IGNORECASE),
    re.compile(r"^Accepted:", re.IGNORECASE),
    re.compile(r"^Declined:", re.IGNORECASE),
    re.compile(r"^Tentative:", re.IGNORECASE),
    re.compile(r"^Undeliverable:", re.IGNORECASE),
    re.compile(r"^Mail Delivery Failed", re.IGNORECASE),
]


def _matches_subject_pattern(subject: str | None) -> bool:
    """Check if a subject matches known auto-reply patterns."""
    if not subject:
        return False
    return any(p.search(subject) for p in SUBJECT_PATTERNS)


async def _call_haiku_with_retry(
    client: AsyncAnthropic,
    user_message: str,
    system_prompt: str,
    semaphore: asyncio.Semaphore,
) -> dict | None:
    """Call Haiku for classification, retrying on 429."""
    async with semaphore:
        for attempt in range(MAX_RATE_LIMIT_RETRIES):
            try:
                response = await client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=300,
                    system=[{"type": "text", "text": system_prompt}],
                    messages=[{"role": "user", "content": user_message}],
                )
                try:
                    return json.loads(response.content[0].text)
                except (json.JSONDecodeError, IndexError):
                    return None
            except RateLimitError as exc:
                if attempt == MAX_RATE_LIMIT_RETRIES - 1:
                    raise
                try:
                    delay = float(exc.response.headers["retry-after"])
                except (AttributeError, KeyError, TypeError, ValueError):
                    delay = DEFAULT_RETRY_AFTER
                logger.warning(
                    "Rate limited by Claude API, retry-after %gs (attempt %d/%d)",
                    delay, attempt + 1, MAX_RATE_LIMIT_RETRIES,
                )
                await asyncio.sleep(delay)
    return None


async def classify_emails(
    session: AsyncSession, batch_size: int = 10
) -> dict:
    """Classify unclassified incoming emails.

    1. Fast pass: subject-pattern matching for obvious auto-replies.
    2. Haiku pass: API classification for remaining unclassified incoming emails.

    Returns summary counts.
    """
    summary = {
        "total": 0,
        "classified": 0,
        "auto_replies_found": 0,
        "chains_extracted": 0,
        "errors": 0,
    }

    # Find unclassified incoming emails (is_auto_reply=False and no quoted_metadata yet)
    # We classify emails that haven't been through the classifier yet.
    # Use a marker: emails with direction=INCOMING_EMAIL that haven't been classified
    # We'll process all incoming emails that are is_auto_reply=False
    # and check subject patterns + send remaining to Haiku.
    stmt = (
        select(Email)
        .where(Email.direction == "INCOMING_EMAIL")
        .where(Email.is_auto_reply == False)  # noqa: E712
        .where(or_(Email.quoted_metadata.is_(None), Email.quoted_metadata == JSON.NULL))
    )
    result = await session.execute(stmt)
    unclassified = result.scalars().all()

    summary["total"] = len(unclassified)

    if not unclassified:
        return summary

    # Pass 1: subject-pattern matching
    pattern_matched = []
    remaining = []
    for email in unclassified:
        if _matches_subject_pattern(email.subject):
            email.is_auto_reply = True
            summary["auto_replies_found"] += 1
            summary["classified"] += 1
            pattern_matched.append(email)
        else:
            remaining.append(email)

    await session.flush()

    if not remaining:
        return summary

    # Pass 2: Haiku classification
    settings = await get_settings(session)
    if not settings.classifier_prompt_blocks:
        # No classifier prompt configured, skip API classification
        return summary

    system_prompt = assemble_prompt(
        settings.classifier_prompt_blocks, CLASSIFIER_DIMENSIONS
    )
    client = AsyncAnthropic()
    semaphore = asyncio.Semaphore(batch_size)

    for i in range(0, len(remaining), batch_size):
        batch = remaining[i:i + batch_size]
        tasks = []
        for email in batch:
            body = email.body_text or ""
            if len(body) > MAX_BODY_LENGTH:
                body = body[:MAX_BODY_LENGTH]
            user_msg = f"Subject: {email.subject or ''}\nBody:\n{body}"
            tasks.append(
                _call_haiku_with_retry(client, user_msg, system_prompt, semaphore)
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for email, api_result in zip(batch, results):
            if isinstance(api_result, Exception):
                summary["errors"] += 1
                continue

            if api_result is None:
                summary["errors"] += 1
                continue

            email_type = api_result.get("email_type", "real_email")
            quoted = api_result.get("quoted_emails", [])

            if email_type != "real_email":
                email.is_auto_reply = True
                summary["auto_replies_found"] += 1

            if quoted:
                email.quoted_metadata = quoted
                summary["chains_extracted"] += 1

            summary["classified"] += 1

        await session.flush()

    return summary
