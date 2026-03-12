import contextvars
import os
from datetime import datetime, timezone

from sqlalchemy import String, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


_current_user_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_user",
    default=os.getenv("CURRENT_USER", "system"),
)


def set_current_user(user: str) -> contextvars.Token:
    """Set the current user for audit trail. Returns a token for resetting."""
    return _current_user_var.set(user)


def _get_current_user() -> str:
    return _current_user_var.get()


def _utcnow() -> datetime:
    """Naive UTC datetime compatible with TIMESTAMP WITHOUT TIME ZONE columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AuditMixin:
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)
    created_by: Mapped[str] = mapped_column(String, default="")
    updated_by: Mapped[str] = mapped_column(String, default="")

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "__tablename__"):
            event.listen(cls, "before_insert", _before_insert)
            event.listen(cls, "before_update", _before_update)


def _before_insert(mapper, connection, target):
    user = _get_current_user()
    target.created_by = user
    target.updated_by = user
    target.created_at = _utcnow()
    target.updated_at = _utcnow()


def _before_update(mapper, connection, target):
    user = _get_current_user()
    target.updated_by = user
    target.updated_at = _utcnow()
