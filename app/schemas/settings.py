from datetime import date

from pydantic import field_validator, model_validator

from app.schemas.base import AppBase

WEIGHT_FIELDS = [
    "weight_value_proposition",
    "weight_personalisation",
    "weight_cta",
    "weight_clarity",
]

PROMPT_BLOCK_FIELDS = [
    "initial_email_prompt_blocks",
    "chain_email_prompt_blocks",
    "chain_evaluation_prompt_blocks",
]


class EmailPromptBlocks(AppBase):
    opening: str
    value_proposition: str
    personalisation: str
    cta: str
    clarity: str
    closing: str


class ChainPromptBlocks(AppBase):
    opening: str
    progression: str
    responsiveness: str
    persistence: str
    conversation_quality: str
    closing: str


class SettingsResponse(AppBase):
    id: int
    global_start_date: date
    company_domains: str
    scoring_batch_size: int
    auto_score_after_fetch: bool
    initial_email_prompt_blocks: EmailPromptBlocks | None = None
    chain_email_prompt_blocks: EmailPromptBlocks | None = None
    chain_evaluation_prompt_blocks: ChainPromptBlocks | None = None
    weight_value_proposition: float = 0.35
    weight_personalisation: float = 0.30
    weight_cta: float = 0.20
    weight_clarity: float = 0.15


class SettingsUpdate(AppBase):
    global_start_date: date | None = None
    company_domains: str | None = None
    scoring_batch_size: int | None = None
    auto_score_after_fetch: bool | None = None
    initial_email_prompt_blocks: EmailPromptBlocks | None = None
    chain_email_prompt_blocks: EmailPromptBlocks | None = None
    chain_evaluation_prompt_blocks: ChainPromptBlocks | None = None
    weight_value_proposition: float | None = None
    weight_personalisation: float | None = None
    weight_cta: float | None = None
    weight_clarity: float | None = None

    @field_validator("global_start_date")
    @classmethod
    def start_date_not_in_future(cls, v: date | None) -> date | None:
        if v is not None and v > date.today():
            raise ValueError("global_start_date cannot be in the future")
        return v

    @field_validator("company_domains")
    @classmethod
    def domains_not_empty(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("company_domains cannot be empty")
        return v

    @field_validator("scoring_batch_size")
    @classmethod
    def batch_size_positive(cls, v: int | None) -> int | None:
        if v is not None and v < 1:
            raise ValueError("scoring_batch_size must be >= 1")
        return v

    @field_validator(*PROMPT_BLOCK_FIELDS)
    @classmethod
    def prompt_blocks_not_empty(cls, v):
        if v is None:
            return v
        for field_name, field_value in v.model_dump().items():
            if isinstance(field_value, str) and not field_value.strip():
                raise ValueError(f"Prompt block '{field_name}' cannot be empty")
        return v

    @model_validator(mode="after")
    def weights_must_sum_to_one(self) -> "SettingsUpdate":
        provided = {
            f: getattr(self, f)
            for f in WEIGHT_FIELDS
            if f in self.model_fields_set
        }
        if not provided:
            return self
        if len(provided) != len(WEIGHT_FIELDS):
            missing = set(WEIGHT_FIELDS) - set(provided.keys())
            raise ValueError(
                f"All weight fields must be provided together. Missing: {', '.join(sorted(missing))}"
            )
        total = sum(provided.values())
        if abs(total - 1.0) > 0.001:
            raise ValueError(
                f"Weights must sum to 1.0 (got {total})"
            )
        return self
