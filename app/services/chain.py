from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Email, EmailChain, ChainScore
from app.services.pagination import paginate_result as _paginate_result


async def get_chain_detail(session: AsyncSession, chain_id: int) -> dict | None:
    """Single chain with all emails in timestamp order and chain_score."""
    stmt = (
        select(EmailChain)
        .where(EmailChain.id == chain_id)
        .options(
            joinedload(EmailChain.chain_score),
            joinedload(EmailChain.emails).joinedload(Email.score),
        )
    )
    result = await session.execute(stmt)
    chain = result.scalars().unique().first()
    if not chain:
        return None

    sorted_emails = sorted(chain.emails, key=lambda e: (e.timestamp or e.created_at,))
    cs = chain.chain_score

    return {
        "id": chain.id,
        "normalized_subject": chain.normalized_subject,
        "participants": chain.participants,
        "started_at": chain.started_at,
        "last_activity_at": chain.last_activity_at,
        "email_count": chain.email_count,
        "outgoing_count": chain.outgoing_count,
        "incoming_count": chain.incoming_count,
        "chain_score": {
            "progression": cs.progression,
            "responsiveness": cs.responsiveness,
            "persistence": cs.persistence,
            "conversation_quality": cs.conversation_quality,
            "avg_response_hours": cs.avg_response_hours,
            "notes": cs.notes,
            "scored_at": cs.scored_at,
        } if cs else None,
        "emails": [
            {
                "id": e.id,
                "from_email": e.from_email,
                "from_name": e.from_name,
                "to_email": e.to_email,
                "to_name": e.to_name,
                "subject": e.subject,
                "body_text": e.body_text,
                "direction": e.direction,
                "timestamp": e.timestamp,
                "position_in_chain": e.position_in_chain,
                "score": {
                    "overall": e.score.overall,
                    "personalisation": e.score.personalisation,
                    "clarity": e.score.clarity,
                    "value_proposition": e.score.value_proposition,
                    "cta": e.score.cta,
                    "notes": e.score.notes,
                } if e.score else None,
            }
            for e in sorted_emails
        ],
    }


async def get_rep_chains(
    session: AsyncSession,
    rep_email: str,
    page: int = 1,
    per_page: int = 20,
    search: str | None = None,
    date_from=None,
    date_to=None,
    score_min: int | None = None,
    score_max: int | None = None,
    status: str | None = None,
) -> dict:
    """Chains where any email has from_email matching rep_email."""
    from sqlalchemy import or_

    chain_ids_subq = (
        select(Email.chain_id)
        .where(Email.from_email == rep_email, Email.chain_id.isnot(None))
        .distinct()
        .subquery()
    )

    filters = [EmailChain.id.in_(select(chain_ids_subq.c.chain_id))]

    if search:
        filters.append(EmailChain.normalized_subject.ilike(f"%{search}%"))
    if date_from:
        filters.append(EmailChain.started_at >= date_from)
    if date_to:
        filters.append(EmailChain.last_activity_at <= date_to)
    if status == "unanswered":
        filters.append(EmailChain.is_unanswered.is_(True))
    elif status == "answered":
        filters.append(EmailChain.is_unanswered.is_(False))

    # For score filters, join chain_score
    if score_min is not None or score_max is not None:
        base_q = (
            select(EmailChain)
            .join(ChainScore, ChainScore.chain_id == EmailChain.id)
            .where(*filters)
            .options(joinedload(EmailChain.chain_score))
        )
        if score_min is not None:
            base_q = base_q.where(ChainScore.conversation_quality >= score_min)
        if score_max is not None:
            base_q = base_q.where(ChainScore.conversation_quality <= score_max)
    else:
        base_q = (
            select(EmailChain)
            .where(*filters)
            .options(joinedload(EmailChain.chain_score))
        )

    count_stmt = select(func.count()).select_from(base_q.subquery())
    total = (await session.execute(count_stmt)).scalar() or 0

    stmt = (
        base_q
        .order_by(EmailChain.last_activity_at.desc().nullslast())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await session.execute(stmt)
    chains = result.scalars().unique().all()

    items = []
    for chain in chains:
        cs = chain.chain_score
        items.append({
            "id": chain.id,
            "normalized_subject": chain.normalized_subject,
            "participants": chain.participants,
            "started_at": chain.started_at,
            "last_activity_at": chain.last_activity_at,
            "email_count": chain.email_count,
            "outgoing_count": chain.outgoing_count,
            "incoming_count": chain.incoming_count,
            "is_unanswered": chain.is_unanswered,
            "progression": cs.progression if cs else None,
            "responsiveness": cs.responsiveness if cs else None,
            "persistence": cs.persistence if cs else None,
            "conversation_quality": cs.conversation_quality if cs else None,
            "avg_response_hours": cs.avg_response_hours if cs else None,
        })

    return _paginate_result(items, total, page, per_page)
