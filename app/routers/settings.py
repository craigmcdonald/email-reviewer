from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_config
from app.database import get_db
from app.models.settings import (
    DEFAULT_CHAIN_EMAIL_PROMPT,
    DEFAULT_CHAIN_EVALUATION_PROMPT,
    DEFAULT_INITIAL_EMAIL_PROMPT,
)
from app.schemas.settings import SettingsResponse, SettingsUpdate
from app.services.settings import get_settings, update_settings
from app.templating import templates

router = APIRouter()


@router.get("/api/settings", response_model=SettingsResponse)
async def read_settings(session: AsyncSession = Depends(get_db)):
    return await get_settings(session)


@router.patch("/api/settings", response_model=SettingsResponse)
async def patch_settings(
    updates: SettingsUpdate, session: AsyncSession = Depends(get_db)
):
    return await update_settings(session, updates)


@router.get("/api/settings/defaults")
async def settings_defaults():
    return {
        "initial_email_prompt": DEFAULT_INITIAL_EMAIL_PROMPT,
        "chain_email_prompt": DEFAULT_CHAIN_EMAIL_PROMPT,
        "chain_evaluation_prompt": DEFAULT_CHAIN_EVALUATION_PROMPT,
    }


@router.get("/settings", include_in_schema=False)
async def settings_page(
    request: Request,
    session: AsyncSession = Depends(get_db),
    tab: str = Query(default="general"),
):
    settings = await get_settings(session)
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "settings": settings,
            "dev_mode": not app_config.AUTH_ENABLED,
            "active_tab": tab,
        },
    )
