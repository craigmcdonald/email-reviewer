from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Rep
from app.services.chain import get_chain_detail, get_rep_chains
from app.services.export import export_rep_chains, export_rep_emails
from app.services.feed import get_feed, get_feed_reps
from app.services.rep import get_rep_emails, get_team, get_team_trends
from app.templating import templates

router = APIRouter()

XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def score_class(value) -> str:
    """Return a CSS class based on score value."""
    if value is None:
        return ""
    if value >= 7:
        return "score-high"
    if value >= 4:
        return "score-mid"
    return "score-low"


def reply_bar_class(rate) -> str:
    """Return CSS class for reply rate bar fill."""
    if rate is None:
        return ""
    if rate >= 0.25:
        return "bar-high"
    if rate >= 0.15:
        return "bar-mid"
    return "bar-low"


def resp_time_bar_class(hours) -> str:
    """Return CSS class for response time bar fill."""
    if hours is None:
        return ""
    if hours <= 8:
        return "bar-high"
    if hours <= 24:
        return "bar-mid"
    return "bar-low"


@router.get("/", include_in_schema=False)
async def team(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=0),
    rep_type: str = Query(""),
    session: AsyncSession = Depends(get_db),
):
    effective_per_page = per_page or None
    result = await get_team(
        session, page=page, per_page=effective_per_page, rep_type=rep_type or None
    )
    trends = await get_team_trends(session)
    start = (page - 1) * per_page + 1 if per_page else 1
    end = start + len(result["items"]) - 1 if result["items"] else 0
    return templates.TemplateResponse(
        request,
        "team.html",
        {
            "rows": result["items"],
            "trends": trends,
            "score_class": score_class,
            "reply_bar_class": reply_bar_class,
            "resp_time_bar_class": resp_time_bar_class,
            "page": result["page"],
            "per_page": per_page,
            "total": result["total"],
            "pages": result["pages"],
            "start": start,
            "end": end,
            "rep_type_filter": rep_type,
            "active_nav": "team",
        },
    )


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _parse_int(value: str | None) -> int | None:
    if not value:
        return None
    return int(value)


def _section_params(params, prefix: str) -> dict:
    """Extract prefixed query params for a section (e.g. 'o_page', 'f_search')."""
    return {
        "page": int(params.get(f"{prefix}_page", 1)),
        "per_page": int(params.get(f"{prefix}_per_page", 20)),
        "search": params.get(f"{prefix}_search", "") or "",
        "date_from": params.get(f"{prefix}_date_from", "") or "",
        "date_to": params.get(f"{prefix}_date_to", "") or "",
        "score_min": params.get(f"{prefix}_score_min", "") or "",
        "score_max": params.get(f"{prefix}_score_max", "") or "",
    }


def _section_context(prefix: str, params: dict, result: dict) -> dict:
    """Build template context for a section from params and query result."""
    page = params["page"]
    per_page = params["per_page"]
    return {
        f"{prefix}_items": result["items"],
        f"{prefix}_page": result["page"],
        f"{prefix}_per_page": per_page,
        f"{prefix}_total": result["total"],
        f"{prefix}_pages": result["pages"],
        f"{prefix}_start": (page - 1) * per_page + 1 if per_page else 1,
        f"{prefix}_end": (
            (page - 1) * per_page + len(result["items"])
            if per_page and result["items"]
            else len(result["items"])
        ),
        f"{prefix}_search": params["search"],
        f"{prefix}_date_from": params["date_from"],
        f"{prefix}_date_to": params["date_to"],
        f"{prefix}_score_min": _parse_int(params["score_min"]) or "",
        f"{prefix}_score_max": _parse_int(params["score_max"]) or "",
    }


@router.get("/feed", include_in_schema=False)
async def feed_page(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1),
    search: str = Query(""),
    rep_email: str = Query(""),
    date_from: str = Query(""),
    date_to: str = Query(""),
    score_min: str = Query(""),
    score_max: str = Query(""),
    unanswered: str = Query(""),
    session: AsyncSession = Depends(get_db),
):
    result = await get_feed(
        session,
        page=page,
        per_page=per_page,
        search=search or None,
        rep_email=rep_email or None,
        date_from=_parse_date(date_from),
        date_to=_parse_date(date_to),
        score_min=_parse_int(score_min),
        score_max=_parse_int(score_max),
        unanswered_only=bool(unanswered),
    )
    reps = await get_feed_reps(session)
    start = (page - 1) * per_page + 1
    end = start + len(result["items"]) - 1 if result["items"] else 0

    # Build filter query string for pagination links (excludes page/per_page)
    filter_parts = []
    if search:
        filter_parts.append(f"&search={search}")
    if rep_email:
        filter_parts.append(f"&rep_email={rep_email}")
    if date_from:
        filter_parts.append(f"&date_from={date_from}")
    if date_to:
        filter_parts.append(f"&date_to={date_to}")
    if score_min:
        filter_parts.append(f"&score_min={score_min}")
    if score_max:
        filter_parts.append(f"&score_max={score_max}")
    if unanswered:
        filter_parts.append("&unanswered=1")
    filter_qs = "".join(filter_parts)

    return templates.TemplateResponse(
        request,
        "feed.html",
        {
            "items": result["items"],
            "reps": reps,
            "score_class": score_class,
            "page": result["page"],
            "per_page": per_page,
            "total": result["total"],
            "pages": result["pages"],
            "start": start,
            "end": end,
            "search": search,
            "rep_email": rep_email,
            "date_from": date_from,
            "date_to": date_to,
            "score_min": _parse_int(score_min) or "",
            "score_max": _parse_int(score_max) or "",
            "unanswered": unanswered,
            "filter_qs": filter_qs,
            "active_nav": "inbox",
        },
    )


@router.get("/chains/{chain_id}", include_in_schema=False)
async def chain_detail_page(
    chain_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    chain = await get_chain_detail(session, chain_id)
    if not chain:
        raise HTTPException(status_code=404, detail="Chain not found")
    return templates.TemplateResponse(
        request,
        "chain_detail.html",
        {
            "chain": chain,
            "score_class": score_class,
        },
    )


@router.get("/reps/{rep_email}", include_in_schema=False)
async def rep_detail(
    rep_email: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    stmt = select(Rep).where(Rep.email == rep_email)
    result = await session.execute(stmt)
    rep = result.scalars().first()
    if not rep:
        raise HTTPException(status_code=404, detail="Rep not found")

    params = request.query_params

    # Outreach section (prefix: o)
    o = _section_params(params, "o")
    o_effective_per_page = o["per_page"] or None
    outreach_result = await get_rep_emails(
        session, rep_email,
        page=o["page"], per_page=o_effective_per_page,
        search=o["search"] or None,
        date_from=_parse_date(o["date_from"]),
        date_to=_parse_date(o["date_to"]),
        score_min=_parse_int(o["score_min"]),
        score_max=_parse_int(o["score_max"]),
        email_type="outreach",
    )

    # Follow-up section (prefix: f)
    f = _section_params(params, "f")
    f_effective_per_page = f["per_page"] or None
    followup_result = await get_rep_emails(
        session, rep_email,
        page=f["page"], per_page=f_effective_per_page,
        search=f["search"] or None,
        date_from=_parse_date(f["date_from"]),
        date_to=_parse_date(f["date_to"]),
        score_min=_parse_int(f["score_min"]),
        score_max=_parse_int(f["score_max"]),
        email_type="follow_up",
    )

    # Conversations section (prefix: c)
    c = _section_params(params, "c")
    c_status = params.get("c_status", "") or ""
    c_effective_per_page = c["per_page"] or None
    chains_result = await get_rep_chains(
        session, rep_email,
        page=c["page"], per_page=c_effective_per_page or 20,
        search=c["search"] or None,
        date_from=_parse_date(c["date_from"]),
        date_to=_parse_date(c["date_to"]),
        score_min=_parse_int(c["score_min"]),
        score_max=_parse_int(c["score_max"]),
        status=c_status or None,
    )

    ctx = {
        "rep": rep,
        "score_class": score_class,
        "c_status": c_status,
    }
    ctx.update(_section_context("o", o, outreach_result))
    ctx.update(_section_context("f", f, followup_result))
    ctx.update(_section_context("c", c, chains_result))

    return templates.TemplateResponse(request, "rep_detail.html", ctx)


@router.get("/reps/{rep_email}/export", include_in_schema=False)
async def rep_export(
    rep_email: str,
    section: str = Query("outreach"),
    export_all: bool = Query(False),
    search: str = Query(""),
    date_from: str = Query(""),
    date_to: str = Query(""),
    score_min: str = Query(""),
    score_max: str = Query(""),
    status: str = Query(""),
    session: AsyncSession = Depends(get_db),
):
    stmt = select(Rep).where(Rep.email == rep_email)
    result = await session.execute(stmt)
    rep = result.scalars().first()
    if not rep:
        raise HTTPException(status_code=404, detail="Rep not found")

    if section == "conversations":
        buf = await export_rep_chains(
            session, rep_email,
            search=search or None,
            date_from=_parse_date(date_from),
            date_to=_parse_date(date_to),
            score_min=_parse_int(score_min),
            score_max=_parse_int(score_max),
            export_all=export_all,
            status=status or None,
        )
        filename = f"{rep.display_name.replace(' ', '_')}_conversations.xlsx"
    else:
        email_type = "follow_up" if section == "follow_ups" else "outreach"
        buf = await export_rep_emails(
            session, rep_email,
            search=search or None,
            date_from=_parse_date(date_from),
            date_to=_parse_date(date_to),
            score_min=_parse_int(score_min),
            score_max=_parse_int(score_max),
            export_all=export_all,
            email_type=email_type,
        )
        suffix = "follow_ups" if section == "follow_ups" else "emails"
        filename = f"{rep.display_name.replace(' ', '_')}_{suffix}.xlsx"

    return StreamingResponse(
        buf,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
