from datetime import date
from typing import Optional, Union

from sqlalchemy import CheckConstraint, Date, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin, Base

EMAIL_DIMENSIONS = ["value_proposition", "personalisation", "cta", "clarity"]
CHAIN_DIMENSIONS = ["progression", "responsiveness", "persistence", "conversation_quality"]
CLASSIFIER_DIMENSIONS = ["email_type", "quoted_emails"]
THREAD_SPLITTER_DIMENSIONS = ["messages"]


def assemble_prompt(blocks: dict, dimensions: list[str]) -> str:
    """Concatenate opening, numbered dimension blocks, and closing into a prompt string."""
    parts = [blocks["opening"]]
    for i, dim in enumerate(dimensions, 1):
        parts.append(f"{i}. {blocks[dim]}")
    parts.append(blocks["closing"])
    return "\n\n".join(parts)


class Settings(AuditMixin, Base):
    __tablename__ = "settings"
    __table_args__ = (CheckConstraint("id = 1", name="single_row_settings"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    global_start_date: Mapped[date] = mapped_column(
        Date, default=date(2025, 9, 1)
    )
    company_domains: Mapped[str] = mapped_column(
        String, default="nativecampusadvertising.com,native.fm"
    )
    scoring_batch_size: Mapped[int] = mapped_column(Integer, default=5)
    auto_score_after_fetch: Mapped[bool] = mapped_column(default=True)

    initial_email_prompt_blocks: Mapped[Optional[dict]] = mapped_column(
        JSONB, default=None
    )
    chain_email_prompt_blocks: Mapped[Optional[dict]] = mapped_column(
        JSONB, default=None
    )
    chain_evaluation_prompt_blocks: Mapped[Optional[dict]] = mapped_column(
        JSONB, default=None
    )
    weight_value_proposition: Mapped[float] = mapped_column(Float, default=0.35)
    weight_personalisation: Mapped[float] = mapped_column(Float, default=0.30)
    weight_cta: Mapped[float] = mapped_column(Float, default=0.20)
    weight_clarity: Mapped[float] = mapped_column(Float, default=0.15)
    classifier_prompt_blocks: Mapped[Optional[dict]] = mapped_column(
        JSONB, default=None
    )
    follow_up_email_prompt_blocks: Mapped[Optional[dict]] = mapped_column(
        JSONB, default=None
    )
    thread_splitter_prompt_blocks: Mapped[Optional[dict]] = mapped_column(
        JSONB, default=None
    )
    thread_split_indicators: Mapped[Optional[Union[list, dict]]] = mapped_column(
        JSONB, default=None
    )
