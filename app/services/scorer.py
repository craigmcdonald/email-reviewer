"""Score unscored emails and conversation chains using the Claude API."""

import asyncio
import json
import logging
import math
from dataclasses import dataclass, field

from anthropic import AsyncAnthropic, RateLimitError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.base import _utcnow
from app.models.chain import EmailChain
from app.models.chain_score import ChainScore
from app.models.email import Email
from app.models.rep import Rep
from app.models.score import Score
from app.models.settings import (
    CHAIN_DIMENSIONS,
    EMAIL_DIMENSIONS,
    Settings,
    assemble_prompt,
)
from app.enums import RepType
from app.schemas.chain_score import ChainScoringResult
from app.schemas.score import ScoringResult
from app.services.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class EmailScoringContext:
    """Wraps an Email with scoring-pipeline metadata."""
    email: Email
    rep_type: str | None = None
    chain_context: str = ""
    follow_up_context: str = ""
    is_follow_up: bool = False

MAX_BODY_LENGTH = 4000
MAX_CHAIN_EMAIL_LENGTH = 2000
MIN_WORD_COUNT = 20
MAX_RATE_LIMIT_RETRIES = 5
DEFAULT_RETRY_AFTER = 60


def _format_email_header(email) -> str:
    """Format From/To/Date/Subject header block for an email."""
    from_parts = [email.from_name, email.from_email]
    from_str = " ".join(p for p in from_parts if p)
    to_parts = [email.to_name, email.to_email]
    to_str = " ".join(p for p in to_parts if p)
    date_str = str(email.timestamp) if email.timestamp else ""
    return (
        f"From: {from_str}\n"
        f"To: {to_str}\n"
        f"Date: {date_str}\n"
        f"Subject: {email.subject or ''}"
    )


def _calculate_weighted_overall(scores: dict, weights: dict) -> int:
    """Compute weighted sum of the 4 dimensions. Round to nearest int, clamp 1-10."""
    weighted = (
        scores["value_proposition"] * weights["weight_value_proposition"]
        + scores["personalisation"] * weights["weight_personalisation"]
        + scores["cta"] * weights["weight_cta"]
        + scores["clarity"] * weights["weight_clarity"]
    )
    rounded = math.floor(weighted + 0.5)
    return max(1, min(10, rounded))


def _build_user_message(ctx: EmailScoringContext) -> str:
    """Format email metadata and body into a prompt string for Claude."""
    email = ctx.email
    body = email.body_text or ""
    if len(body) > MAX_BODY_LENGTH:
        body = body[:MAX_BODY_LENGTH]

    parts = []

    # Include rep role context when available
    if ctx.rep_type:
        parts.append(f"Rep role: {ctx.rep_type}")

    # Include chain context for chain follow-up emails
    if ctx.chain_context and (email.position_in_chain or 0) > 1:
        parts.append(f"Previous conversation:\n{ctx.chain_context}\n")

    # Include follow-up context for unchained follow-up emails
    if ctx.follow_up_context:
        parts.append(f"Previous emails in sequence:\n{ctx.follow_up_context}\n")

    parts.append(f"{_format_email_header(email)}\nBody:\n{body}")

    return "\n".join(parts)


async def _build_chain_context(session: AsyncSession, email: Email) -> str:
    """Build context from prior emails in the same chain.

    Returns empty string when the email has no chain or is the first in its chain.
    Each prior email body is truncated to 2000 characters.
    """
    if email.chain_id is None or (email.position_in_chain or 0) <= 1:
        return ""

    stmt = (
        select(Email)
        .where(Email.chain_id == email.chain_id)
        .where(Email.position_in_chain < email.position_in_chain)
        .order_by(Email.position_in_chain)
    )
    result = await session.execute(stmt)
    prior_emails = result.scalars().all()

    if not prior_emails:
        return ""

    sections = []
    for prior in prior_emails:
        body = prior.body_text or ""
        if len(body) > MAX_CHAIN_EMAIL_LENGTH:
            body = body[:MAX_CHAIN_EMAIL_LENGTH]

        sections.append(f"{_format_email_header(prior)}\nBody: {body}")

    return "\n---\n".join(sections)


async def _build_follow_up_context(session: AsyncSession, email: Email) -> str:
    """Build context from prior emails in the same follow-up sequence.

    A follow-up sequence is emails from the same from_email to the same to_email
    with the same normalized subject, no chain_id, ordered by timestamp.
    Returns empty string if this is the first email or no prior emails exist.
    """
    from app.services.chain_builder import normalize_subject

    if email.chain_id is not None:
        return ""

    norm_subj = normalize_subject(email.subject)
    if not norm_subj:
        return ""

    # Find all emails from same sender to same recipient with same normalized subject
    stmt = (
        select(Email)
        .where(Email.from_email == email.from_email)
        .where(Email.to_email == email.to_email)
        .where(Email.chain_id.is_(None))
        .order_by(Email.timestamp.asc())
    )
    result = await session.execute(stmt)
    candidates = result.scalars().all()

    # Filter to same normalized subject and before current email
    prior = []
    for c in candidates:
        if normalize_subject(c.subject) != norm_subj:
            continue
        if c.id == email.id:
            break
        prior.append(c)

    if not prior:
        return ""

    sections = []
    for p in prior:
        body = p.body_text or ""
        if len(body) > MAX_CHAIN_EMAIL_LENGTH:
            body = body[:MAX_CHAIN_EMAIL_LENGTH]

        sections.append(f"{_format_email_header(p)}\nBody: {body}")

    return "\n---\n".join(sections)


def _get_retry_after(exc: RateLimitError) -> float:
    """Extract retry-after seconds from a RateLimitError's response headers."""
    try:
        return float(exc.response.headers["retry-after"])
    except (AttributeError, KeyError, TypeError, ValueError):
        return DEFAULT_RETRY_AFTER


async def _call_claude_with_retry(
    client: AsyncAnthropic, user_message: str, system_prompt: str
) -> tuple[object, dict]:
    """Call Claude API, retrying on 429 using the retry-after header.

    Returns (response, token_totals). Raises RateLimitError if all retries
    are exhausted.
    """
    total_tokens = {"input": 0, "output": 0}

    for attempt in range(MAX_RATE_LIMIT_RETRIES):
        try:
            response = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=300,
                system=[{"type": "text", "text": system_prompt}],
                messages=[{"role": "user", "content": user_message}],
            )
            total_tokens["input"] += response.usage.input_tokens
            total_tokens["output"] += response.usage.output_tokens
            return response, total_tokens
        except RateLimitError as exc:
            if attempt == MAX_RATE_LIMIT_RETRIES - 1:
                raise
            delay = _get_retry_after(exc)
            logger.warning(
                "Rate limited by Claude API, retry-after %gs (attempt %d/%d)",
                delay, attempt + 1, MAX_RATE_LIMIT_RETRIES,
            )
            await asyncio.sleep(delay)

    # Unreachable, but keeps the type checker happy
    raise RateLimitError(message="Rate limit retries exhausted", response=None, body=None)


async def _score_single_email(
    client: AsyncAnthropic,
    ctx: EmailScoringContext,
    semaphore: asyncio.Semaphore,
    settings: Settings,
) -> ScoringResult | None:
    """Call Claude to score one email. Retry once on parse failure.

    Retries with exponential backoff on rate limit (429) errors.
    Returns a ScoringResult on success or None if both parse attempts fail.
    """
    email = ctx.email
    user_message = _build_user_message(ctx)

    # Choose prompt based on email type
    if ctx.is_follow_up:
        blocks = settings.follow_up_email_prompt_blocks
    elif email.chain_id is not None and (email.position_in_chain or 0) > 1:
        blocks = settings.chain_email_prompt_blocks
    else:
        blocks = settings.initial_email_prompt_blocks
    if not blocks:
        raise ValueError("Prompt blocks not configured in settings")
    system_prompt = assemble_prompt(blocks, EMAIL_DIMENSIONS)

    async with semaphore:
        for _attempt in range(2):
            try:
                response, total_tokens = await _call_claude_with_retry(
                    client, user_message, system_prompt
                )
            except RateLimitError:
                return None

            try:
                raw = json.loads(response.content[0].text)
                result = ScoringResult(**raw, tokens=total_tokens)
                return result
            except (json.JSONDecodeError, ValueError, KeyError):
                continue

    return None


async def _get_rep_type_map(session: AsyncSession) -> dict[str, str | None]:
    """Load a mapping of rep email -> rep_type for all reps."""
    stmt = select(Rep.email, Rep.rep_type)
    result = await session.execute(stmt)
    return {row.email: row.rep_type for row in result.all()}


async def score_unscored_emails(
    session: AsyncSession, batch_size: int = 5
) -> dict:
    """Score emails that don't yet have a score record.

    Auto-reply emails (is_auto_reply=True) are skipped.
    Emails with empty or very short bodies (under 20 words) are skipped
    entirely - no score row is created since there is no content to
    evaluate. Emails from reps with no rep_type are skipped.

    Processes emails in batches of ``batch_size``, committing each batch
    to the database before moving on so that completed work survives
    crashes. Each batch queries its own fresh ORM objects to avoid
    stale-state issues after commit. Returns a summary dict with counts
    and total tokens used.
    """
    # Phase 1: identify which emails need scoring — collect plain IDs
    stmt = (
        select(Email)
        .outerjoin(Score, Email.id == Score.email_id)
        .where(Score.id.is_(None))
    )
    result = await session.execute(stmt)
    unscored = result.scalars().all()

    rep_type_map = await _get_rep_type_map(session)

    summary = {
        "total_unscored": len(unscored),
        "scored": 0,
        "skipped": 0,
        "skipped_untyped": 0,
        "skipped_non_sales": 0,
        "skipped_auto_reply": 0,
        "errors": 0,
        "batch_errors": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
    }

    ids_to_score = []

    for email in unscored:
        if email.is_auto_reply:
            summary["skipped_auto_reply"] += 1
            continue

        rep_type = rep_type_map.get(email.from_email)
        if rep_type is None:
            summary["skipped_untyped"] += 1
            continue

        if rep_type == RepType.NON_SALES.value:
            summary["skipped_non_sales"] += 1
            continue

        body = email.body_text or ""
        word_count = len(body.split()) if body.strip() else 0

        if not body.strip() or word_count < MIN_WORD_COUNT:
            summary["skipped"] += 1
        else:
            ids_to_score.append((email.id, rep_type))

    if ids_to_score:
        async with AsyncAnthropic() as client:
            settings = await get_settings(session)

            if not settings.initial_email_prompt_blocks:
                summary["error_message"] = "Initial email prompt blocks not configured in settings"
                return summary
            if not settings.chain_email_prompt_blocks:
                summary["error_message"] = "Chain email prompt blocks not configured in settings"
                return summary
            if not settings.follow_up_email_prompt_blocks:
                summary["error_message"] = "Follow-up email prompt blocks not configured in settings"
                return summary

            weights = {
                "weight_value_proposition": settings.weight_value_proposition,
                "weight_personalisation": settings.weight_personalisation,
                "weight_cta": settings.weight_cta,
                "weight_clarity": settings.weight_clarity,
            }

            # Phase 2: process in batches, each with fresh ORM objects
            for i in range(0, len(ids_to_score), batch_size):
                batch_items = ids_to_score[i : i + batch_size]
                batch_ids = [item[0] for item in batch_items]
                batch_rep_types = {item[0]: item[1] for item in batch_items}
                try:
                    emails = (await session.execute(
                        select(Email).where(Email.id.in_(batch_ids))
                    )).scalars().all()

                    semaphore = asyncio.Semaphore(batch_size)

                    contexts: list[EmailScoringContext] = []
                    for email in emails:
                        chain_context = await _build_chain_context(session, email)
                        follow_up_context = ""
                        is_follow_up = False
                        if email.chain_id is None:
                            fu_context = await _build_follow_up_context(session, email)
                            if fu_context:
                                follow_up_context = fu_context
                                is_follow_up = True
                        contexts.append(EmailScoringContext(
                            email=email,
                            rep_type=batch_rep_types[email.id],
                            chain_context=chain_context,
                            follow_up_context=follow_up_context,
                            is_follow_up=is_follow_up,
                        ))

                    tasks = [
                        _score_single_email(client, ctx, semaphore, settings)
                        for ctx in contexts
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    for ctx, scoring_result in zip(contexts, results):
                        if isinstance(scoring_result, BaseException):
                            logger.error(
                                "Email %d scoring raised: %s", ctx.email.id, scoring_result,
                            )
                            scoring_result = None
                        email = ctx.email
                        if scoring_result is not None:
                            dimension_scores = {
                                "value_proposition": scoring_result.value_proposition,
                                "personalisation": scoring_result.personalisation,
                                "cta": scoring_result.cta,
                                "clarity": scoring_result.clarity,
                            }
                            overall = _calculate_weighted_overall(dimension_scores, weights)
                            score = Score(
                                email_id=email.id,
                                personalisation=scoring_result.personalisation,
                                clarity=scoring_result.clarity,
                                value_proposition=scoring_result.value_proposition,
                                cta=scoring_result.cta,
                                overall=overall,
                                notes=scoring_result.notes,
                                score_error=False,
                                scored_at=_utcnow(),
                            )
                            session.add(score)
                            summary["scored"] += 1
                            summary["total_input_tokens"] += scoring_result.tokens.get("input", 0)
                            summary["total_output_tokens"] += scoring_result.tokens.get("output", 0)
                        else:
                            score = Score(
                                email_id=email.id,
                                score_error=True,
                                scored_at=_utcnow(),
                            )
                            session.add(score)
                            summary["errors"] += 1

                    await session.commit()
                except Exception:
                    logger.exception("Email scoring batch %d failed", i // batch_size)
                    await session.rollback()
                    summary["batch_errors"] += 1

    # Score unscored chains after individual emails
    chain_result = await score_unscored_chains(session, batch_size=batch_size)
    summary["chains_scored"] = chain_result["chains_scored"]
    summary["chain_errors"] = chain_result["errors"]
    summary["chains_skipped_untyped"] = chain_result.get("skipped_untyped", 0)
    summary["chains_skipped_non_sales"] = chain_result.get("skipped_non_sales", 0)
    summary["total_input_tokens"] += chain_result["total_input_tokens"]
    summary["total_output_tokens"] += chain_result["total_output_tokens"]

    return summary


def _compute_avg_response_hours(emails: list[Email]) -> float | None:
    """Compute average hours between consecutive outgoing emails."""
    outgoing = [
        e for e in sorted(emails, key=lambda e: e.position_in_chain or 0)
        if e.direction == "EMAIL" and e.timestamp is not None
    ]
    if len(outgoing) < 2:
        return None

    deltas = []
    for i in range(1, len(outgoing)):
        delta = (outgoing[i].timestamp - outgoing[i - 1].timestamp).total_seconds() / 3600
        deltas.append(delta)

    return sum(deltas) / len(deltas) if deltas else None


async def score_unscored_chains(
    session: AsyncSession, batch_size: int = 5
) -> dict:
    """Score chains that don't yet have a chain_score record.

    All chains with email_count >= 2 are scored (including unanswered).
    Chains where the rep has no rep_type are skipped.

    Processes chains in batches of ``batch_size``, committing each batch
    to the database before moving on so that completed work survives
    crashes. Each batch queries its own fresh ORM objects. Returns a
    summary dict.
    """
    # Phase 1: identify chain IDs to score
    stmt = (
        select(EmailChain)
        .outerjoin(ChainScore, EmailChain.id == ChainScore.chain_id)
        .where(ChainScore.id.is_(None))
        .where(EmailChain.email_count >= 2)
    )
    result = await session.execute(stmt)
    unscored_chains = result.scalars().all()

    summary = {
        "chains_scored": 0,
        "errors": 0,
        "batch_errors": 0,
        "skipped_untyped": 0,
        "skipped_non_sales": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
    }

    if not unscored_chains:
        return summary

    rep_type_map = await _get_rep_type_map(session)
    settings = await get_settings(session)

    if not settings.chain_evaluation_prompt_blocks:
        summary["error_message"] = "Chain evaluation prompt blocks not configured in settings"
        return summary

    chain_ids_to_score = [chain.id for chain in unscored_chains]

    async with AsyncAnthropic() as client:
        system_prompt = assemble_prompt(settings.chain_evaluation_prompt_blocks, CHAIN_DIMENSIONS)

        # Phase 2: process in batches concurrently, each with fresh ORM objects
        for i in range(0, len(chain_ids_to_score), batch_size):
            batch_ids = chain_ids_to_score[i : i + batch_size]
            try:
                # Prepare chain data for each chain in the batch
                chain_tasks = []
                chain_meta = []  # parallel list of (chain_id, avg_hours) or None for skipped

                for chain_id in batch_ids:
                    email_stmt = (
                        select(Email)
                        .where(Email.chain_id == chain_id)
                        .order_by(Email.position_in_chain)
                    )
                    email_result = await session.execute(email_stmt)
                    chain_emails = email_result.scalars().all()

                    rep_type = None
                    for email in chain_emails:
                        if email.direction == "EMAIL":
                            rep_type = rep_type_map.get(email.from_email)
                            if rep_type is not None:
                                break

                    if rep_type is None:
                        summary["skipped_untyped"] += 1
                        continue

                    if rep_type == RepType.NON_SALES.value:
                        summary["skipped_non_sales"] += 1
                        continue

                    sections = []
                    for email in chain_emails:
                        body = email.body_text or ""
                        if len(body) > MAX_CHAIN_EMAIL_LENGTH:
                            body = body[:MAX_CHAIN_EMAIL_LENGTH]
                        sections.append(f"{_format_email_header(email)}\nBody: {body}")

                    conversation_text = f"Rep role: {rep_type}\n\n" + "\n---\n".join(sections)
                    avg_hours = _compute_avg_response_hours(chain_emails)

                    chain_tasks.append(
                        _score_single_chain(client, conversation_text, system_prompt)
                    )
                    chain_meta.append((chain_id, avg_hours))

                if not chain_tasks:
                    continue

                results = await asyncio.gather(*chain_tasks, return_exceptions=True)

                for (chain_id, avg_hours), result in zip(chain_meta, results):
                    if isinstance(result, BaseException):
                        logger.error("Chain %d scoring raised: %s", chain_id, result)
                        scoring_result, total_tokens = None, {"input": 0, "output": 0}
                    else:
                        scoring_result, total_tokens = result

                    if scoring_result is not None:
                        chain_score = ChainScore(
                            chain_id=chain_id,
                            progression=scoring_result.progression,
                            responsiveness=scoring_result.responsiveness,
                            persistence=scoring_result.persistence,
                            conversation_quality=scoring_result.conversation_quality,
                            avg_response_hours=avg_hours,
                            notes=scoring_result.notes,
                            score_error=False,
                            scored_at=_utcnow(),
                        )
                        session.add(chain_score)
                        summary["chains_scored"] += 1
                    else:
                        chain_score = ChainScore(
                            chain_id=chain_id,
                            score_error=True,
                            scored_at=_utcnow(),
                        )
                        session.add(chain_score)
                        summary["errors"] += 1

                    summary["total_input_tokens"] += total_tokens["input"]
                    summary["total_output_tokens"] += total_tokens["output"]

                await session.commit()
            except Exception:
                logger.exception("Chain scoring batch %d failed", i // batch_size)
                await session.rollback()
                summary["batch_errors"] += 1

    return summary


async def _score_single_chain(
    client: AsyncAnthropic, conversation_text: str, system_prompt: str
) -> tuple[ChainScoringResult | None, dict]:
    """Score a single chain with retry on rate limit and parse failure.

    Returns (ChainScoringResult | None, token_totals).
    """
    total_tokens = {"input": 0, "output": 0}

    for _attempt in range(2):
        try:
            response, attempt_tokens = await _call_claude_with_retry(
                client, conversation_text, system_prompt
            )
            total_tokens["input"] += attempt_tokens["input"]
            total_tokens["output"] += attempt_tokens["output"]
        except RateLimitError:
            return None, total_tokens

        try:
            raw = json.loads(response.content[0].text)
            scoring_result = ChainScoringResult(**raw)
            return scoring_result, total_tokens
        except (json.JSONDecodeError, ValueError, KeyError):
            continue

    return None, total_tokens
