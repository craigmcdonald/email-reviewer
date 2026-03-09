from datetime import date
from typing import Optional

from sqlalchemy import CheckConstraint, Date, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin, Base

EMAIL_DIMENSIONS = ["value_proposition", "personalisation", "cta", "clarity"]
CHAIN_DIMENSIONS = ["progression", "responsiveness", "persistence", "conversation_quality"]

DEFAULT_INITIAL_EMAIL_BLOCKS: dict = {
    "opening": "You are an expert sales email evaluator. Score the following outgoing sales email on four dimensions, each from 1 (worst) to 10 (best):",
    "value_proposition": "**value_proposition** — Does the email clearly articulate what value the sender offers to the recipient?",
    "personalisation": "**personalisation** — How tailored is the email to the specific recipient? Does it reference their company, role, recent activity, or pain points?",
    "cta": "**cta** — Is there a clear, specific call to action? Is it easy for the recipient to take the next step?",
    "clarity": "**clarity** — Is the message easy to read and understand? Is it concise with a clear structure?",
    "closing": 'Respond with ONLY a JSON object in this exact format, no other text:\n{\n  "personalisation": <1-10>,\n  "clarity": <1-10>,\n  "value_proposition": <1-10>,\n  "cta": <1-10>,\n  "notes": "<brief 1-2 sentence explanation of the scores>"\n}',
}

DEFAULT_CHAIN_EMAIL_BLOCKS: dict = {
    "opening": "You are an expert sales email evaluator. Score the following email within the context of its conversation chain on four dimensions, each from 1 (worst) to 10 (best):",
    "value_proposition": "**value_proposition** — Does the email clearly articulate what value the sender offers?",
    "personalisation": "**personalisation** — How tailored is the email to the specific recipient and conversation context?",
    "cta": "**cta** — Is there a clear, specific call to action?",
    "clarity": "**clarity** — Is the message easy to read and understand? Is it concise with a clear structure?",
    "closing": 'Respond with ONLY a JSON object in this exact format, no other text:\n{\n  "personalisation": <1-10>,\n  "clarity": <1-10>,\n  "value_proposition": <1-10>,\n  "cta": <1-10>,\n  "notes": "<brief 1-2 sentence explanation of the scores>"\n}',
}

DEFAULT_CHAIN_EVAL_BLOCKS: dict = {
    "opening": "You are an expert sales conversation evaluator. Evaluate the following email conversation chain on four dimensions, each from 1 (worst) to 10 (best):",
    "progression": "**progression** — How well does the conversation advance toward the sales goal across emails?",
    "responsiveness": "**responsiveness** — How timely and relevant are the follow-ups?",
    "persistence": "**persistence** — Does the sender maintain appropriate follow-up cadence without being pushy?",
    "conversation_quality": "**conversation_quality** — Overall quality of the conversation as a multi-touch sales engagement.",
    "closing": 'Respond with ONLY a JSON object in this exact format, no other text:\n{\n  "progression": <1-10>,\n  "responsiveness": <1-10>,\n  "persistence": <1-10>,\n  "conversation_quality": <1-10>,\n  "notes": "<brief 1-2 sentence explanation of the scores>"\n}',
}


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
