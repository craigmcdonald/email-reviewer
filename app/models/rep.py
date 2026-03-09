from typing import Optional

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin, Base


class Rep(AuditMixin, Base):
    __tablename__ = "reps"

    email: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    rep_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
