from datetime import date, datetime, timedelta

from sqlalchemy import Float, case, cast, extract, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.enums import EmailDirection
from app.models import ChainScore, Email, EmailChain, Rep, Score
from app.services.pagination import paginate_result as _paginate_result

_WINDOW_DAYS = 30


def _window_start() -> datetime:
    return datetime.utcnow() - timedelta(days=_WINDOW_DAYS)


async def get_team(
    session: AsyncSession,
    *,
    page: int = 1,
    per_page: int | None = 20,
    rep_type: str | None = None,
):
    """All reps with rolling 30-day metrics, sorted by outreach score desc.

    Optional filters:
    - rep_type: filter by RepType value, or "Unassigned" for reps with no type set.
    """
    window_start = _window_start()

    # --- Outreach group ---

    # Emails per day (30d): outgoing emails in window / 30
    emails_per_day_subq = (
        select(
            Email.from_email.label("rep_email"),
            (
                cast(func.count(Email.id), Float) / _WINDOW_DAYS
            ).label("emails_per_day"),
        )
        .where(
            Email.direction == EmailDirection.EMAIL.value,
            Email.timestamp >= window_start,
        )
        .group_by(Email.from_email)
        .subquery()
    )

    # Reply rate (30d): outgoing emails in chains with incoming_count > 0 / total outgoing
    # First, outgoing emails in the window
    outgoing_in_window = (
        select(
            Email.from_email.label("rep_email"),
            func.count(Email.id).label("total_outgoing"),
            func.count(
                case(
                    (EmailChain.incoming_count > 0, Email.id),
                )
            ).label("replied_outgoing"),
        )
        .outerjoin(EmailChain, EmailChain.id == Email.chain_id)
        .where(
            Email.direction == EmailDirection.EMAIL.value,
            Email.timestamp >= window_start,
        )
        .group_by(Email.from_email)
        .subquery()
    )

    reply_rate_subq = (
        select(
            outgoing_in_window.c.rep_email,
            case(
                (
                    outgoing_in_window.c.total_outgoing > 0,
                    cast(outgoing_in_window.c.replied_outgoing, Float)
                    / outgoing_in_window.c.total_outgoing,
                ),
                else_=None,
            ).label("reply_rate"),
        )
        .subquery()
    )

    # Outreach score (30d): avg(scores.overall) where scored_at in window
    outreach_score_subq = (
        select(
            Email.from_email.label("rep_email"),
            func.avg(Score.overall).label("avg_overall"),
        )
        .join(Score, Score.email_id == Email.id)
        .where(Score.scored_at >= window_start)
        .group_by(Email.from_email)
        .subquery()
    )

    # --- Conversations group ---

    # Unanswered count: chains where rep has outgoing email AND is_unanswered = true (no window)
    unanswered_subq = (
        select(
            Email.from_email.label("rep_email"),
            func.count(func.distinct(EmailChain.id)).label("unanswered_count"),
        )
        .join(EmailChain, EmailChain.id == Email.chain_id)
        .where(
            Email.direction == EmailDirection.EMAIL.value,
            EmailChain.is_unanswered.is_(True),
        )
        .group_by(Email.from_email)
        .subquery()
    )

    # Avg response hours (30d)
    resp_hours_subq = (
        select(
            Email.from_email.label("rep_email"),
            func.avg(ChainScore.avg_response_hours).label("avg_response_hours"),
        )
        .join(EmailChain, EmailChain.id == Email.chain_id)
        .join(ChainScore, ChainScore.chain_id == EmailChain.id)
        .where(
            Email.direction == EmailDirection.EMAIL.value,
            ChainScore.scored_at >= window_start,
        )
        .group_by(Email.from_email)
        .subquery()
    )

    # Conversation score (30d)
    conv_score_subq = (
        select(
            Email.from_email.label("rep_email"),
            func.avg(ChainScore.conversation_quality).label("avg_conv_score"),
        )
        .join(EmailChain, EmailChain.id == Email.chain_id)
        .join(ChainScore, ChainScore.chain_id == EmailChain.id)
        .where(
            Email.direction == EmailDirection.EMAIL.value,
            ChainScore.scored_at >= window_start,
        )
        .group_by(Email.from_email)
        .subquery()
    )

    base = (
        select(
            Rep.email,
            Rep.display_name,
            Rep.rep_type,
            emails_per_day_subq.c.emails_per_day,
            reply_rate_subq.c.reply_rate,
            outreach_score_subq.c.avg_overall,
            unanswered_subq.c.unanswered_count,
            resp_hours_subq.c.avg_response_hours,
            conv_score_subq.c.avg_conv_score,
        )
        .outerjoin(
            emails_per_day_subq, emails_per_day_subq.c.rep_email == Rep.email
        )
        .outerjoin(reply_rate_subq, reply_rate_subq.c.rep_email == Rep.email)
        .outerjoin(
            outreach_score_subq, outreach_score_subq.c.rep_email == Rep.email
        )
        .outerjoin(unanswered_subq, unanswered_subq.c.rep_email == Rep.email)
        .outerjoin(resp_hours_subq, resp_hours_subq.c.rep_email == Rep.email)
        .outerjoin(conv_score_subq, conv_score_subq.c.rep_email == Rep.email)
        .order_by(outreach_score_subq.c.avg_overall.desc().nullslast())
    )

    if rep_type == "Unassigned":
        base = base.where(Rep.rep_type.is_(None))
    elif rep_type:
        base = base.where(Rep.rep_type == rep_type)

    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await session.execute(count_stmt)).scalar() or 0

    if per_page:
        base = base.offset((page - 1) * per_page).limit(per_page)

    result = await session.execute(base)
    return _paginate_result(result.all(), total, page, per_page)


async def get_team_trends(session: AsyncSession) -> dict:
    """Trend card data: current value, week-over-week delta, 7-week sparkline.

    Returns dict with keys: outreach_score, reply_rate, avg_response_time.
    Each has: value, delta, sparkline (list of 7 floats).
    """
    now = datetime.utcnow()
    window_start = now - timedelta(days=_WINDOW_DAYS)

    # Helper: compute weekly buckets for the last 7 weeks
    # Week 0 = oldest, week 6 = most recent (current week)
    seven_weeks_ago = now - timedelta(weeks=7)

    # --- Outreach Score ---
    outreach_weekly = await _weekly_avg(
        session,
        select(
            Score.scored_at.label("ts"),
            Score.overall.label("val"),
        ).where(Score.scored_at >= seven_weeks_ago),
        now,
    )

    outreach_current_stmt = select(func.avg(Score.overall)).where(
        Score.scored_at >= window_start
    )
    outreach_current = (await session.execute(outreach_current_stmt)).scalar()

    # --- Reply Rate ---
    # Weekly reply rate is trickier - compute per week
    reply_weekly = []
    for week_idx in range(7):
        week_start = now - timedelta(weeks=7 - week_idx)
        week_end = now - timedelta(weeks=6 - week_idx)
        total_stmt = select(func.count(Email.id)).where(
            Email.direction == EmailDirection.EMAIL.value,
            Email.timestamp >= week_start,
            Email.timestamp < week_end,
        )
        replied_stmt = (
            select(func.count(Email.id))
            .outerjoin(EmailChain, EmailChain.id == Email.chain_id)
            .where(
                Email.direction == EmailDirection.EMAIL.value,
                Email.timestamp >= week_start,
                Email.timestamp < week_end,
                EmailChain.incoming_count > 0,
            )
        )
        total_count = (await session.execute(total_stmt)).scalar() or 0
        replied_count = (await session.execute(replied_stmt)).scalar() or 0
        rate = (replied_count / total_count) if total_count > 0 else None
        reply_weekly.append(rate)

    # Current 30d reply rate
    total_30d_stmt = select(func.count(Email.id)).where(
        Email.direction == EmailDirection.EMAIL.value,
        Email.timestamp >= window_start,
    )
    replied_30d_stmt = (
        select(func.count(Email.id))
        .outerjoin(EmailChain, EmailChain.id == Email.chain_id)
        .where(
            Email.direction == EmailDirection.EMAIL.value,
            Email.timestamp >= window_start,
            EmailChain.incoming_count > 0,
        )
    )
    total_30d = (await session.execute(total_30d_stmt)).scalar() or 0
    replied_30d = (await session.execute(replied_30d_stmt)).scalar() or 0
    reply_current = (replied_30d / total_30d) if total_30d > 0 else None

    # --- Avg Response Time ---
    resp_weekly = await _weekly_avg(
        session,
        select(
            ChainScore.scored_at.label("ts"),
            ChainScore.avg_response_hours.label("val"),
        ).where(
            ChainScore.scored_at >= seven_weeks_ago,
            ChainScore.avg_response_hours.isnot(None),
        ),
        now,
    )

    resp_current_stmt = select(func.avg(ChainScore.avg_response_hours)).where(
        ChainScore.scored_at >= window_start,
        ChainScore.avg_response_hours.isnot(None),
    )
    resp_current = (await session.execute(resp_current_stmt)).scalar()

    def _delta(sparkline, inverted=False):
        """Week-on-week delta from last two sparkline entries."""
        curr = sparkline[-1] if len(sparkline) >= 1 else None
        prev = sparkline[-2] if len(sparkline) >= 2 else None
        if curr is None or prev is None:
            return None
        d = curr - prev
        return -d if inverted else d

    return {
        "outreach_score": {
            "value": round(outreach_current, 1) if outreach_current else None,
            "delta": _delta(outreach_weekly),
            "sparkline": outreach_weekly,
        },
        "reply_rate": {
            "value": round(reply_current * 100, 1) if reply_current else None,
            "delta": _delta(reply_weekly),
            "sparkline": reply_weekly,
        },
        "avg_response_time": {
            "value": round(resp_current, 1) if resp_current else None,
            "delta": _delta(resp_weekly, inverted=True),
            "sparkline": resp_weekly,
        },
    }


async def _weekly_avg(session: AsyncSession, base_stmt, now: datetime) -> list:
    """Compute 7 weekly average values from a statement with ts and val columns."""
    buckets = []
    for week_idx in range(7):
        week_start = now - timedelta(weeks=7 - week_idx)
        week_end = now - timedelta(weeks=6 - week_idx)
        sub = base_stmt.subquery()
        avg_stmt = select(func.avg(sub.c.val)).where(
            sub.c.ts >= week_start,
            sub.c.ts < week_end,
        )
        val = (await session.execute(avg_stmt)).scalar()
        buckets.append(round(val, 1) if val is not None else None)
    return buckets


async def _follow_up_ids(session, rep_email: str) -> set[int]:
    """Return IDs of emails that are follow-ups: same from_email, to_email,
    normalized subject, no chain_id, position > 1 ordered by timestamp."""
    from app.services.chain_builder import normalize_subject

    stmt = (
        select(Email)
        .where(Email.from_email == rep_email, Email.chain_id.is_(None))
        .order_by(Email.timestamp.asc())
    )
    result = await session.execute(stmt)
    emails = result.scalars().all()

    # Group by (from_email, to_email, normalized_subject)
    groups: dict[tuple[str, str, str], list[int]] = {}
    for e in emails:
        key = (e.from_email, e.to_email or "", normalize_subject(e.subject))
        groups.setdefault(key, []).append(e.id)

    follow_up_set: set[int] = set()
    for ids in groups.values():
        if len(ids) > 1:
            # Skip the first (outreach), rest are follow-ups
            follow_up_set.update(ids[1:])
    return follow_up_set


async def get_rep_emails(
    session: AsyncSession,
    rep_email: str,
    *,
    page: int = 1,
    per_page: int | None = 20,
    search: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    score_min: int | None = None,
    score_max: int | None = None,
    email_type: str | None = None,
):
    """Scored emails for one rep, ordered by date desc.

    Optional filters:
    - search: ILIKE match on subject or body_text
    - date_from / date_to: inclusive range on email timestamp
    - score_min / score_max: inclusive range on overall score
    - email_type: "outreach" (no chain_id, first in sequence),
      "follow_up" (no chain_id, subsequent in sequence)
    """
    filters = [Email.from_email == rep_email]

    fu_ids: set[int] | None = None
    if email_type in ("outreach", "follow_up"):
        filters.append(Email.chain_id.is_(None))
        fu_ids = await _follow_up_ids(session, rep_email)
        if email_type == "outreach":
            if fu_ids:
                filters.append(Email.id.notin_(fu_ids))
        elif email_type == "follow_up":
            if fu_ids:
                filters.append(Email.id.in_(fu_ids))
            else:
                # No follow-ups exist - return empty
                filters.append(Email.id == -1)

    if search:
        pattern = f"%{search}%"
        filters.append(
            or_(
                Email.subject.ilike(pattern),
                Email.body_text.ilike(pattern),
            )
        )
    if date_from:
        filters.append(Email.timestamp >= date_from)
    if date_to:
        filters.append(Email.timestamp <= date_to)
    if score_min is not None:
        filters.append(Score.overall >= score_min)
    if score_max is not None:
        filters.append(Score.overall <= score_max)

    filters.append(Score.score_error.is_(False))

    count_stmt = (
        select(func.count(Email.id))
        .join(Score, Score.email_id == Email.id)
        .where(*filters)
    )
    total = (await session.execute(count_stmt)).scalar() or 0

    stmt = (
        select(Email)
        .join(Score, Score.email_id == Email.id)
        .where(*filters)
        .options(joinedload(Email.score))
        .order_by(Email.timestamp.desc())
    )

    if per_page:
        stmt = stmt.offset((page - 1) * per_page).limit(per_page)

    result = await session.execute(stmt)
    items = result.scalars().unique().all()

    # Compute time_gap_seconds for follow-up emails
    if email_type == "follow_up" and items:
        from app.services.chain_builder import normalize_subject as _ns
        prior_stmt = (
            select(Email)
            .where(Email.from_email == rep_email, Email.chain_id.is_(None))
            .order_by(Email.timestamp.asc())
        )
        prior_result = await session.execute(prior_stmt)
        all_emails = prior_result.scalars().all()

        seq_map: dict[tuple[str, str], list] = {}
        for e in all_emails:
            key = (e.to_email or "", _ns(e.subject))
            seq_map.setdefault(key, []).append(e)

        for item in items:
            key = (item.to_email or "", _ns(item.subject))
            seq = seq_map.get(key, [])
            prev_ts = None
            for e in seq:
                if e.id == item.id:
                    break
                prev_ts = e.timestamp
            if prev_ts and item.timestamp:
                item.time_gap_seconds = (item.timestamp - prev_ts).total_seconds()
            else:
                item.time_gap_seconds = None

    return _paginate_result(list(items), total, page, per_page)


async def get_email_detail(session: AsyncSession, email_id: int):
    """Single email with its score."""
    stmt = (
        select(Email)
        .where(Email.id == email_id)
        .options(joinedload(Email.score))
    )
    result = await session.execute(stmt)
    return result.scalars().first()


async def get_stats(session: AsyncSession):
    """Summary counts and averages."""
    total_emails_stmt = select(func.count(Email.id))
    total_scored_stmt = select(func.count(Score.id)).where(Score.score_error.is_(False))
    total_reps_stmt = select(func.count(Rep.email))
    avg_overall_stmt = select(func.avg(Score.overall)).where(Score.score_error.is_(False))

    total_emails = (await session.execute(total_emails_stmt)).scalar() or 0
    total_scored = (await session.execute(total_scored_stmt)).scalar() or 0
    total_reps = (await session.execute(total_reps_stmt)).scalar() or 0
    avg_overall = (await session.execute(avg_overall_stmt)).scalar()

    return {
        "total_emails": total_emails,
        "total_scored": total_scored,
        "total_reps": total_reps,
        "avg_overall": round(avg_overall, 2) if avg_overall is not None else None,
    }
