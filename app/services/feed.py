"""Feed page service: unified reverse-chronological view of outreach activity."""

from datetime import date

from sqlalchemy import Float,case, cast, func, literal, literal_column, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.enums import EmailDirection, RepType
from app.models import Email, EmailChain, Rep, Score
from app.services.pagination import paginate_result as _paginate_result


async def get_feed_reps(session: AsyncSession) -> list:
    """Reps eligible for feed filtering: rep_type set and not Non-Sales."""
    stmt = (
        select(Rep)
        .where(Rep.rep_type.isnot(None), Rep.rep_type != RepType.NON_SALES.value)
        .order_by(Rep.display_name)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_feed(
    session: AsyncSession,
    *,
    page: int = 1,
    per_page: int = 20,
    search: str | None = None,
    rep_email: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    score_min: int | None = None,
    score_max: int | None = None,
    unanswered_only: bool = False,
) -> dict:
    """Unified feed combining standalone emails and conversations.

    Returns paginated dict with items carrying a 'type' field
    ("email" or "conversation").
    """
    if unanswered_only:
        # Only conversations with is_unanswered=True
        items_query, count_query = _build_unanswered_query(
            session, search=search, rep_email=rep_email,
            date_from=date_from, date_to=date_to,
            score_min=score_min, score_max=score_max,
        )
    else:
        items_query, count_query = _build_union_query(
            search=search, rep_email=rep_email,
            date_from=date_from, date_to=date_to,
            score_min=score_min, score_max=score_max,
        )

    total = (await session.execute(count_query)).scalar() or 0

    paginated = items_query.offset((page - 1) * per_page).limit(per_page)
    result = await session.execute(paginated)
    rows = result.all()

    items = []
    for row in rows:
        items.append(_row_to_item(row))

    return _paginate_result(items, total, page, per_page)


def _build_standalone_filters(
    *, search, rep_email, date_from, date_to, score_min, score_max,
):
    """Filter conditions for standalone outgoing emails."""
    filters = [
        Email.direction == EmailDirection.EMAIL.value,
        Email.chain_id.is_(None),
        Score.score_error.is_(False),
    ]
    if rep_email:
        filters.append(Email.from_email == rep_email)
    if search:
        pattern = f"%{search}%"
        filters.append(
            or_(
                Email.subject.ilike(pattern),
                Email.to_email.ilike(pattern),
                Email.to_name.ilike(pattern),
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
    return filters


def _standalone_select(*, search, rep_email, date_from, date_to, score_min, score_max):
    """SELECT for standalone outgoing emails."""
    filters = _build_standalone_filters(
        search=search, rep_email=rep_email,
        date_from=date_from, date_to=date_to,
        score_min=score_min, score_max=score_max,
    )
    return (
        select(
            literal("email").label("type"),
            Email.id.label("item_id"),
            Email.subject.label("subject"),
            Email.from_name.label("from_name"),
            Email.from_email.label("from_email"),
            Email.to_name.label("to_name"),
            Email.to_email.label("to_email"),
            Email.body_text.label("body_text"),
            Email.timestamp.label("sort_date"),
            Score.overall.label("score"),
            Score.notes.label("score_notes"),
            Score.personalisation.label("score_personalisation"),
            Score.clarity.label("score_clarity"),
            Score.value_proposition.label("score_value_proposition"),
            Score.cta.label("score_cta"),
            literal(None).label("email_count"),
            literal(False).label("is_unanswered"),
            literal(None).label("participants"),
        )
        .join(Score, Score.email_id == Email.id)
        .where(*filters)
    )


def _chain_latest_score_subq():
    """Subquery: most recent scored email per chain."""
    # Rank emails within each chain by scored_at desc
    ranked = (
        select(
            Email.chain_id.label("chain_id"),
            Score.overall.label("overall"),
            Score.notes.label("notes"),
            func.row_number().over(
                partition_by=Email.chain_id,
                order_by=Score.scored_at.desc().nullslast(),
            ).label("rn"),
        )
        .join(Score, Score.email_id == Email.id)
        .where(Email.chain_id.isnot(None), Score.score_error.is_(False))
        .subquery()
    )
    return (
        select(
            ranked.c.chain_id,
            ranked.c.overall,
            ranked.c.notes,
        )
        .where(ranked.c.rn == 1)
        .subquery()
    )


def _chain_first_outgoing_subq():
    """Subquery: first outgoing email per chain (for rep name/avatar)."""
    ranked = (
        select(
            Email.chain_id.label("chain_id"),
            Email.from_name.label("from_name"),
            Email.from_email.label("from_email"),
            func.row_number().over(
                partition_by=Email.chain_id,
                order_by=Email.position_in_chain.asc().nullsfirst(),
            ).label("rn"),
        )
        .where(
            Email.chain_id.isnot(None),
            Email.direction == EmailDirection.EMAIL.value,
        )
        .subquery()
    )
    return (
        select(
            ranked.c.chain_id,
            ranked.c.from_name,
            ranked.c.from_email,
        )
        .where(ranked.c.rn == 1)
        .subquery()
    )


def _build_chain_filters(
    chain_latest_score, first_outgoing,
    *, search, rep_email, date_from, date_to, score_min, score_max,
):
    """Filter conditions for conversation chains."""
    filters = []

    if rep_email:
        # Chain must have at least one outgoing email from this rep
        rep_chain_ids = (
            select(Email.chain_id)
            .where(
                Email.from_email == rep_email,
                Email.chain_id.isnot(None),
                Email.direction == EmailDirection.EMAIL.value,
            )
            .distinct()
            .subquery()
        )
        filters.append(EmailChain.id.in_(select(rep_chain_ids.c.chain_id)))

    if search:
        pattern = f"%{search}%"
        filters.append(EmailChain.normalized_subject.ilike(pattern))

    if date_from:
        filters.append(EmailChain.last_activity_at >= date_from)
    if date_to:
        filters.append(EmailChain.last_activity_at <= date_to)

    if score_min is not None:
        filters.append(chain_latest_score.c.overall >= score_min)
    if score_max is not None:
        filters.append(chain_latest_score.c.overall <= score_max)

    return filters


def _conversation_select(*, search, rep_email, date_from, date_to, score_min, score_max):
    """SELECT for conversation chains."""
    chain_latest_score = _chain_latest_score_subq()
    first_outgoing = _chain_first_outgoing_subq()

    filters = _build_chain_filters(
        chain_latest_score, first_outgoing,
        search=search, rep_email=rep_email,
        date_from=date_from, date_to=date_to,
        score_min=score_min, score_max=score_max,
    )

    stmt = (
        select(
            literal("conversation").label("type"),
            EmailChain.id.label("item_id"),
            EmailChain.normalized_subject.label("subject"),
            first_outgoing.c.from_name.label("from_name"),
            first_outgoing.c.from_email.label("from_email"),
            literal(None).label("to_name"),
            literal(None).label("to_email"),
            literal(None).label("body_text"),
            EmailChain.last_activity_at.label("sort_date"),
            chain_latest_score.c.overall.label("score"),
            chain_latest_score.c.notes.label("score_notes"),
            literal(None).label("score_personalisation"),
            literal(None).label("score_clarity"),
            literal(None).label("score_value_proposition"),
            literal(None).label("score_cta"),
            EmailChain.email_count.label("email_count"),
            EmailChain.is_unanswered.label("is_unanswered"),
            EmailChain.participants.label("participants"),
        )
        .outerjoin(chain_latest_score, chain_latest_score.c.chain_id == EmailChain.id)
        .outerjoin(first_outgoing, first_outgoing.c.chain_id == EmailChain.id)
    )
    if filters:
        stmt = stmt.where(*filters)
    return stmt


def _build_union_query(*, search, rep_email, date_from, date_to, score_min, score_max):
    """Build the union query for both standalone and conversation items."""
    kw = dict(
        search=search, rep_email=rep_email,
        date_from=date_from, date_to=date_to,
        score_min=score_min, score_max=score_max,
    )
    standalone = _standalone_select(**kw)
    conversations = _conversation_select(**kw)

    combined = union_all(standalone, conversations).subquery()
    items_query = select(combined).order_by(combined.c.sort_date.desc().nullslast())
    count_query = select(func.count()).select_from(combined)

    return items_query, count_query


def _build_unanswered_query(session, *, search, rep_email, date_from, date_to, score_min, score_max):
    """Build query for unanswered conversations only (no standalone emails)."""
    chain_latest_score = _chain_latest_score_subq()
    first_outgoing = _chain_first_outgoing_subq()

    filters = _build_chain_filters(
        chain_latest_score, first_outgoing,
        search=search, rep_email=rep_email,
        date_from=date_from, date_to=date_to,
        score_min=score_min, score_max=score_max,
    )
    filters.append(EmailChain.is_unanswered.is_(True))

    base = (
        select(
            literal("conversation").label("type"),
            EmailChain.id.label("item_id"),
            EmailChain.normalized_subject.label("subject"),
            first_outgoing.c.from_name.label("from_name"),
            first_outgoing.c.from_email.label("from_email"),
            literal(None).label("to_name"),
            literal(None).label("to_email"),
            literal(None).label("body_text"),
            EmailChain.last_activity_at.label("sort_date"),
            chain_latest_score.c.overall.label("score"),
            chain_latest_score.c.notes.label("score_notes"),
            literal(None).label("score_personalisation"),
            literal(None).label("score_clarity"),
            literal(None).label("score_value_proposition"),
            literal(None).label("score_cta"),
            EmailChain.email_count.label("email_count"),
            EmailChain.is_unanswered.label("is_unanswered"),
            EmailChain.participants.label("participants"),
        )
        .outerjoin(chain_latest_score, chain_latest_score.c.chain_id == EmailChain.id)
        .outerjoin(first_outgoing, first_outgoing.c.chain_id == EmailChain.id)
        .where(*filters)
    )

    sub = base.subquery()
    items_query = select(sub).order_by(sub.c.sort_date.desc().nullslast())
    count_query = select(func.count()).select_from(sub)

    return items_query, count_query


def _row_to_item(row) -> dict:
    """Convert a union result row to a feed item dict."""
    return {
        "type": row.type,
        "item_id": row.item_id,
        "subject": row.subject,
        "from_name": row.from_name,
        "from_email": row.from_email,
        "to_name": row.to_name,
        "to_email": row.to_email,
        "body_text": row.body_text,
        "sort_date": row.sort_date,
        "score": row.score,
        "score_notes": row.score_notes,
        "score_personalisation": row.score_personalisation,
        "score_clarity": row.score_clarity,
        "score_value_proposition": row.score_value_proposition,
        "score_cta": row.score_cta,
        "email_count": row.email_count,
        "is_unanswered": row.is_unanswered,
        "participants": row.participants,
    }
