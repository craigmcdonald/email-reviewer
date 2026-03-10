import math
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import ChainScore, Email, EmailChain, Rep, Score


def _paginate_result(items, total: int, page: int, per_page: int | None):
    if per_page:
        pages = math.ceil(total / per_page)
    else:
        pages = 1
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


async def get_team(
    session: AsyncSession,
    *,
    page: int = 1,
    per_page: int | None = 20,
    rep_type: str | None = None,
):
    """All reps with score averages (null if unscored), sorted by overall desc.

    Optional filters:
    - rep_type: filter by RepType value, or "Unassigned" for reps with no type set.
    """
    # Subquery for chain stats per rep
    chain_subq = (
        select(
            Email.from_email.label("rep_email"),
            func.count(func.distinct(Email.chain_id)).label("chain_count"),
        )
        .where(Email.chain_id.isnot(None))
        .group_by(Email.from_email)
        .subquery()
    )

    # Subquery for avg chain score per rep
    chain_score_subq = (
        select(
            Email.from_email.label("rep_email"),
            func.avg(ChainScore.conversation_quality).label("avg_chain_score"),
        )
        .join(EmailChain, EmailChain.id == Email.chain_id)
        .join(ChainScore, ChainScore.chain_id == EmailChain.id)
        .where(Email.chain_id.isnot(None))
        .group_by(Email.from_email)
        .subquery()
    )

    # Subquery for per-rep score averages
    score_subq = (
        select(
            Email.from_email.label("rep_email"),
            func.avg(Score.personalisation).label("avg_personalisation"),
            func.avg(Score.clarity).label("avg_clarity"),
            func.avg(Score.value_proposition).label("avg_value_proposition"),
            func.avg(Score.cta).label("avg_cta"),
            func.avg(Score.overall).label("avg_overall"),
        )
        .join(Score, Score.email_id == Email.id)
        .group_by(Email.from_email)
        .subquery()
    )

    base = (
        select(
            Rep.email,
            Rep.display_name,
            Rep.rep_type,
            score_subq.c.avg_personalisation,
            score_subq.c.avg_clarity,
            score_subq.c.avg_value_proposition,
            score_subq.c.avg_cta,
            score_subq.c.avg_overall,
            chain_subq.c.chain_count,
            chain_score_subq.c.avg_chain_score,
        )
        .outerjoin(score_subq, score_subq.c.rep_email == Rep.email)
        .outerjoin(chain_subq, chain_subq.c.rep_email == Rep.email)
        .outerjoin(chain_score_subq, chain_score_subq.c.rep_email == Rep.email)
        .order_by(score_subq.c.avg_overall.desc().nullslast())
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
    total_scored_stmt = select(func.count(Score.id))
    total_reps_stmt = select(func.count(Rep.email))
    avg_overall_stmt = select(func.avg(Score.overall))

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
