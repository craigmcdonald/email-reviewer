from datetime import datetime
from typing import Optional

from app.schemas.base import AppBase


class EmailCreate(AppBase):
    from_email: str
    from_name: Optional[str] = None
    to_name: Optional[str] = None
    to_email: Optional[str] = None
    subject: Optional[str] = None
    body_text: Optional[str] = None
    direction: Optional[str] = None
    hubspot_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    fetched_at: Optional[datetime] = None


class EmailUpdate(AppBase):
    from_name: Optional[str] = None
    from_email: Optional[str] = None
    to_name: Optional[str] = None
    to_email: Optional[str] = None
    subject: Optional[str] = None
    body_text: Optional[str] = None
    direction: Optional[str] = None
    hubspot_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    fetched_at: Optional[datetime] = None


class EmailResponse(AppBase):
    id: int
    timestamp: Optional[datetime] = None
    from_name: Optional[str] = None
    from_email: str
    to_name: Optional[str] = None
    to_email: Optional[str] = None
    subject: Optional[str] = None
    body_text: Optional[str] = None
    direction: Optional[str] = None
    hubspot_id: Optional[str] = None
    fetched_at: Optional[datetime] = None
