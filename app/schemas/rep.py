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
    emails_per_day: Optional[float] = None
    reply_rate: Optional[float] = None
    avg_overall: Optional[float] = None
    unanswered_count: Optional[int] = None
    avg_response_hours: Optional[float] = None
    avg_conv_score: Optional[float] = None
