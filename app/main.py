import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.models.base import _current_user_var, set_current_user
from app.routers import api, dashboard, operations, settings

app = FastAPI()


@app.middleware("http")
async def set_audit_user(request: Request, call_next):
    """Set the current user context var for audit trail columns.

    Reads from CURRENT_USER env var for now. When auth is implemented,
    extract the authenticated user from the request here instead.
    """
    user = os.getenv("CURRENT_USER", "system")
    token = set_current_user(user)
    try:
        response = await call_next(request)
    finally:
        _current_user_var.reset(token)
    return response

app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
app.include_router(api.router)
app.include_router(settings.router)
app.include_router(operations.router)
app.include_router(dashboard.router)


@app.get("/health")
async def health():
    return {"status": "healthy"}
