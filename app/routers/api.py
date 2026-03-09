from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.enums import RepType
from app.models.rep import Rep
from app.schemas.rep import RepResponse, RepTeamRow, RepUpdate
from app.schemas.stats import StatsResponse
from app.services.chain import get_chain_detail, get_rep_chains
from app.services.rep import get_email_detail, get_rep_emails, get_stats, get_team

router = APIRouter(prefix="/api")


@router.get("/reps", response_model=list[RepTeamRow])
async def list_reps(session: AsyncSession = Depends(get_db)):
    result = await get_team(session)
    return [
        RepTeamRow(
            email=r.email,
            display_name=r.display_name,
            rep_type=r.rep_type,
            avg_personalisation=round(r.avg_personalisation, 2) if r.avg_personalisation else None,
            avg_clarity=round(r.avg_clarity, 2) if r.avg_clarity else None,
            avg_value_proposition=round(r.avg_value_proposition, 2) if r.avg_value_proposition else None,
            avg_cta=round(r.avg_cta, 2) if r.avg_cta else None,
            avg_overall=round(r.avg_overall, 2) if r.avg_overall else None,
            chain_count=r.chain_count,
            avg_chain_score=round(r.avg_chain_score, 2) if r.avg_chain_score else None,
        )
        for r in result["items"]
    ]


@router.patch("/reps/{rep_email}", response_model=RepResponse)
async def update_rep(
    rep_email: str,
    payload: RepUpdate,
    session: AsyncSession = Depends(get_db),
):
    stmt = select(Rep).where(Rep.email == rep_email)
    result = await session.execute(stmt)
    rep = result.scalars().first()
    if not rep:
        raise HTTPException(status_code=404, detail="Rep not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "rep_type" and value is not None:
            try:
                RepType(value)
            except ValueError:
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid rep_type: {value}. Must be one of: {', '.join(t.value for t in RepType)}",
                )
        setattr(rep, field, value)

    await session.flush()
    await session.refresh(rep)
    return rep


@router.get("/reps/{rep_email}/emails")
async def list_rep_emails(
    rep_email: str,
    type: str | None = Query(None, alias="type"),
    session: AsyncSession = Depends(get_db),
):
    email_type = None
    if type in ("outreach", "follow_up"):
        email_type = type
    elif type == "unanswered":
        chains = await get_rep_chains(session, rep_email, page=1, per_page=200)
        return [c for c in chains["items"] if c.get("is_unanswered")]
    elif type == "chain":
        chains = await get_rep_chains(session, rep_email, page=1, per_page=200)
        return [c for c in chains["items"] if not c.get("is_unanswered")]

    result = await get_rep_emails(session, rep_email, email_type=email_type)
    return [
        {
            "id": e.id,
            "subject": e.subject,
            "from_email": e.from_email,
            "to_email": e.to_email,
            "timestamp": e.timestamp,
            "score": {
                "overall": e.score.overall,
                "personalisation": e.score.personalisation,
                "clarity": e.score.clarity,
                "value_proposition": e.score.value_proposition,
                "cta": e.score.cta,
                "notes": e.score.notes,
            } if e.score else None,
        }
        for e in result["items"]
    ]


@router.get("/reps/{rep_email}/chains")
async def list_rep_chains(
    rep_email: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1),
    session: AsyncSession = Depends(get_db),
):
    return await get_rep_chains(session, rep_email, page=page, per_page=per_page)


@router.get("/chains/{chain_id}")
async def chain_detail(chain_id: int, session: AsyncSession = Depends(get_db)):
    result = await get_chain_detail(session, chain_id)
    if not result:
        raise HTTPException(status_code=404, detail="Chain not found")
    return result


@router.get("/emails/{email_id}")
async def email_detail(email_id: int, session: AsyncSession = Depends(get_db)):
    email = await get_email_detail(session, email_id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    return {
        "id": email.id,
        "subject": email.subject,
        "from_email": email.from_email,
        "to_email": email.to_email,
        "body_text": email.body_text,
        "timestamp": email.timestamp,
        "score": {
            "id": email.score.id,
            "overall": email.score.overall,
            "personalisation": email.score.personalisation,
            "clarity": email.score.clarity,
            "value_proposition": email.score.value_proposition,
            "cta": email.score.cta,
            "notes": email.score.notes,
            "score_error": email.score.score_error,
            "scored_at": email.score.scored_at,
        } if email.score else None,
    }


@router.get("/stats", response_model=StatsResponse)
async def stats(session: AsyncSession = Depends(get_db)):
    return await get_stats(session)
