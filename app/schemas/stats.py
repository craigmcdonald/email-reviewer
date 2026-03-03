from typing import Optional

from app.schemas.base import AppBase


class StatsResponse(AppBase):
    total_emails: int
    total_scored: int
    total_reps: int
    avg_overall: Optional[float] = None
