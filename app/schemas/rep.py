from typing import Optional

from app.enums import RepType
from app.schemas.base import AppBase


class RepCreate(AppBase):
    email: str
    display_name: str
    rep_type: Optional[RepType] = None


class RepUpdate(AppBase):
    display_name: Optional[str] = None
    rep_type: Optional[RepType] = None


class RepResponse(AppBase):
    email: str
    display_name: str
    rep_type: Optional[str] = None


class RepTeamRow(AppBase):
    email: str
    display_name: str
    rep_type: Optional[str] = None
    avg_personalisation: Optional[float] = None
    avg_clarity: Optional[float] = None
    avg_value_proposition: Optional[float] = None
    avg_cta: Optional[float] = None
    avg_overall: Optional[float] = None
    chain_count: Optional[int] = None
    avg_chain_score: Optional[float] = None
