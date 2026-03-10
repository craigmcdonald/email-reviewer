"""Classify emails as auto-replies, non-sales, or real emails using pattern matching and Haiku."""

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
    """Classify unclassified emails (both incoming and outgoing).

    Processes in two phases following the batch-commit pattern:
    1. Pattern matching pass: subject pattern checks for incoming emails only.
    2. Haiku API pass: AI classification for all remaining unclassified emails,
       including outgoing emails that may be internal/non-sales communications.

    Each batch re-queries fresh ORM objects and commits independently so
    completed work survives crashes.
    """
    summary = {
        "total": 0,
        "classified": 0,
        "auto_replies_found": 0,
        "chains_extracted": 0,
        "errors": 0,
        "batch_errors": 0,
    }

    # Phase 1: collect IDs and subjects for pattern matching (no ORM objects held)
    # Classify both incoming and outgoing emails. Incoming emails may be
    # auto-replies, bounces, or calendar responses. Outgoing emails may be
    # internal communications (support tickets, etc.) that should not be scored.
    stmt = (
        select(Email.id, Email.subject, Email.direction, Email.to_email)
        .where(Email.direction.in_(["INCOMING_EMAIL", "EMAIL"]))
        .where(Email.is_auto_reply == False)  # noqa: E712
        .where(or_(Email.quoted_metadata.is_(None), Email.quoted_metadata == JSON.NULL))
    )
    result = await session.execute(stmt)
    unclassified = result.all()

    summary["total"] = len(unclassified)

    if not unclassified:
        return summary

    # Split into pattern-matched IDs and remaining IDs.
    # Subject patterns only apply to incoming emails (auto-reply indicators).
    pattern_matched_ids = []
    remaining_ids = []
    for email_id, subject, direction, to_email in unclassified:
        if direction == "INCOMING_EMAIL" and _matches_subject_pattern(subject):
            pattern_matched_ids.append(email_id)
        else:
            remaining_ids.append(email_id)

    # Phase 2: pattern matching pass — batch-committed
    for i in range(0, len(pattern_matched_ids), batch_size):
        batch_ids = pattern_matched_ids[i : i + batch_size]
        try:
            emails = (await session.execute(
                select(Email).where(Email.id.in_(batch_ids))
            )).scalars().all()

            for email in emails:
                email.is_auto_reply = True
                email.quoted_metadata = []

            summary["auto_replies_found"] += len(emails)
            summary["classified"] += len(emails)
            await session.commit()
        except Exception:
            logger.exception("Pattern classification batch %d failed", i // batch_size)
            await session.rollback()
            summary["batch_errors"] += 1

    if not remaining_ids:
        return summary

    # Phase 3: Haiku API pass — batch-committed
    settings = await get_settings(session)
    if not settings.classifier_prompt_blocks:
        return summary

    system_prompt = assemble_prompt(
        settings.classifier_prompt_blocks, CLASSIFIER_DIMENSIONS
    )
    client = AsyncAnthropic()
    try:
        semaphore = asyncio.Semaphore(batch_size)

        for i in range(0, len(remaining_ids), batch_size):
            batch_ids = remaining_ids[i : i + batch_size]
            try:
                emails = (await session.execute(
                    select(Email).where(Email.id.in_(batch_ids))
                )).scalars().all()

                tasks = []
                for email in emails:
                    body = email.body_text or ""
                    if len(body) > MAX_BODY_LENGTH:
                        body = body[:MAX_BODY_LENGTH]
                    direction_label = (
                        "Outgoing" if email.direction == "EMAIL" else "Incoming"
                    )
                    user_msg = (
                        f"Direction: {direction_label}\n"
                        f"To: {email.to_email or ''}\n"
                        f"Subject: {email.subject or ''}\n"
                        f"Body:\n{body}"
                    )
                    tasks.append(
                        _call_haiku_with_retry(client, user_msg, system_prompt, semaphore)
                    )

                results = await asyncio.gather(*tasks, return_exceptions=True)

                for email, api_result in zip(emails, results):
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

                    # Always set quoted_metadata to mark as processed
                    email.quoted_metadata = quoted if quoted else []
                    if quoted:
                        summary["chains_extracted"] += 1

                    summary["classified"] += 1

                await session.commit()
            except Exception:
                logger.exception("Haiku classification batch %d failed", i // batch_size)
                await session.rollback()
                summary["batch_errors"] += 1
    finally:
        await client.close()

    return summary
