"""Split email threads into individual messages using configurable indicators and Haiku."""

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Optional

from anthropic import AsyncAnthropic, RateLimitError
from sqlalchemy import JSON, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email import Email
from app.models.settings import THREAD_SPLITTER_DIMENSIONS, Settings, assemble_prompt
from app.services.chain_builder import normalize_subject
from app.services.settings import get_settings

logger = logging.getLogger(__name__)

MAX_RATE_LIMIT_RETRIES = 5
DEFAULT_RETRY_AFTER = 60

BODY_SNIPPET_LENGTH = 150


def _matches_any_indicator(body: str, indicators: list[str]) -> bool:
    """Check if body text contains any of the configured thread indicators."""
    if not body or not indicators:
        return False
    for indicator in indicators:
        if indicator in body:
            return True
    return False


def _normalize_body_snippet(text: str) -> str:
    """Normalize body text for comparison: lowercase, collapse whitespace, take first N chars."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.lower().strip())[:BODY_SNIPPET_LENGTH]


def _find_duplicate(
    from_email: str,
    subject: str,
    body_snippet: str,
    timestamp: Optional[datetime],
    candidates: list[dict],
) -> Optional[dict]:
    """Check if an extracted message matches any existing email.

    Uses multi-signal matching:
    1. from_email (case-insensitive, required)
    2. normalized subject (required)
    3. body text opening substring (primary signal)
    4. timestamp within a few minutes (bonus, not required)
    """
    if not from_email or not candidates:
        return None

    norm_subject = normalize_subject(subject)
    norm_snippet = _normalize_body_snippet(body_snippet)

    for candidate in candidates:
        cand_email = (candidate.get("from_email") or "").lower()
        if cand_email != from_email.lower():
            continue

        cand_subject = normalize_subject(candidate.get("subject") or "")
        if cand_subject != norm_subject:
            continue

        cand_body = candidate.get("body_text") or ""
        cand_body_normalized = re.sub(r"\s+", " ", cand_body.lower().strip())
        if norm_snippet and norm_snippet in cand_body_normalized:
            return candidate

    return None


def _infer_direction(from_email: str, company_domains: list[str]) -> str:
    """Return 'EMAIL' if from_email is from a company domain, else 'INCOMING_EMAIL'."""
    if not from_email:
        return "INCOMING_EMAIL"
    domain = from_email.lower().split("@")[-1]
    for cd in company_domains:
        if domain == cd.lower():
            return "EMAIL"
    return "INCOMING_EMAIL"


async def _call_haiku_with_retry(
    client: AsyncAnthropic,
    user_message: str,
    system_prompt: str,
) -> list[dict] | None:
    """Call Haiku for thread splitting, retrying on 429."""
    for attempt in range(MAX_RATE_LIMIT_RETRIES):
        try:
            response = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
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


async def split_email_threads(
    session: AsyncSession, batch_size: int = 10
) -> dict:
    """Split email threads into individual messages.

    Processes emails that have quoted_metadata set (classified as having quoted content),
    have not yet been split, and whose body matches configurable thread indicators.
    Uses Haiku to extract individual messages from the thread body.
    """
    summary = {
        "candidates": 0,
        "threads_split": 0,
        "messages_created": 0,
        "duplicates_skipped": 0,
        "errors": 0,
    }

    settings = await get_settings(session)

    if not settings.thread_splitter_prompt_blocks:
        return summary

    indicators = settings.thread_split_indicators or []
    if not indicators:
        return summary

    company_domains = [
        d.strip() for d in (settings.company_domains or "").split(",") if d.strip()
    ]

    system_prompt = assemble_prompt(
        settings.thread_splitter_prompt_blocks, THREAD_SPLITTER_DIMENSIONS
    )

    # Query candidate emails: not yet split, have quoted_metadata, not auto-reply
    stmt = (
        select(Email.id)
        .where(Email.is_thread_split == False)  # noqa: E712
        .where(Email.is_auto_reply == False)  # noqa: E712
        .where(Email.quoted_metadata.isnot(None))
        .where(Email.quoted_metadata != JSON.NULL)
    )
    result = await session.execute(stmt)
    all_candidate_ids = [row[0] for row in result.all()]

    if not all_candidate_ids:
        return summary

    # Filter by indicator match (cheap pre-filter on body text)
    filtered_ids = []
    for eid in all_candidate_ids:
        email = await session.get(Email, eid)
        if email and _matches_any_indicator(email.body_text or "", indicators):
            filtered_ids.append(eid)
        session.expire(email)

    summary["candidates"] = len(filtered_ids)
    if not filtered_ids:
        return summary

    # Build candidate list for dedup: all existing emails
    dedup_stmt = select(
        Email.id, Email.from_email, Email.subject, Email.body_text, Email.timestamp
    )
    dedup_result = await session.execute(dedup_stmt)
    existing_emails = [
        {
            "id": row[0],
            "from_email": row[1],
            "subject": row[2],
            "body_text": row[3],
            "timestamp": row[4],
        }
        for row in dedup_result.all()
    ]

    client = AsyncAnthropic()
    try:
        for i in range(0, len(filtered_ids), batch_size):
            batch_ids = filtered_ids[i : i + batch_size]
            try:
                emails = (await session.execute(
                    select(Email).where(Email.id.in_(batch_ids))
                )).scalars().all()

                for email in emails:
                    try:
                        messages = await _call_haiku_with_retry(
                            client, email.body_text or "", system_prompt
                        )
                        if not messages or not isinstance(messages, list) or len(messages) < 2:
                            email.is_thread_split = True
                            continue

                        # First message = top-level, trim parent body
                        top_msg = messages[0]
                        trimmed_body = top_msg.get("body_text") or email.body_text
                        email.body_text = trimmed_body

                        # Update dedup list so parent's trimmed body is used
                        for entry in existing_emails:
                            if entry["id"] == email.id:
                                entry["body_text"] = trimmed_body
                                break

                        # Process quoted messages
                        for msg in messages[1:]:
                            msg_from = msg.get("from_email") or ""
                            msg_subject = msg.get("subject") or email.subject or ""
                            msg_body = msg.get("body_text") or ""

                            dup = _find_duplicate(
                                from_email=msg_from,
                                subject=msg_subject,
                                body_snippet=msg_body[:BODY_SNIPPET_LENGTH],
                                timestamp=None,
                                candidates=existing_emails,
                            )
                            if dup:
                                summary["duplicates_skipped"] += 1
                                continue

                            direction = _infer_direction(msg_from, company_domains)
                            child = Email(
                                from_email=msg_from,
                                from_name=msg.get("from_name"),
                                to_email=msg.get("to_email"),
                                to_name=msg.get("to_name"),
                                subject=msg_subject,
                                body_text=msg_body,
                                direction=direction,
                                split_from_id=email.id,
                                is_thread_split=True,
                                quoted_metadata=[],
                            )
                            session.add(child)
                            summary["messages_created"] += 1

                            # Add to dedup list so subsequent messages don't duplicate
                            existing_emails.append({
                                "id": None,
                                "from_email": msg_from,
                                "subject": msg_subject,
                                "body_text": msg_body,
                                "timestamp": None,
                            })

                        email.is_thread_split = True
                        summary["threads_split"] += 1

                    except Exception:
                        logger.exception("Failed to split email %d", email.id)
                        summary["errors"] += 1

                await session.commit()
            except Exception:
                logger.exception("Thread split batch %d failed", i // batch_size)
                await session.rollback()
                summary["errors"] += 1
    finally:
        await client.close()

    return summary
