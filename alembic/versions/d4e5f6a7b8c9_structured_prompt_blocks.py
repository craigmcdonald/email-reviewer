"""replace text prompt columns with structured JSON prompt blocks

Revision ID: d4e5f6a7b8c9
Revises: bc88dceb13af
Create Date: 2026-03-09 12:00:00.000000

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'bc88dceb13af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_INITIAL_EMAIL_BLOCKS = {
    "opening": "You are an expert sales email evaluator. Score the following outgoing sales email on four dimensions, each from 1 (worst) to 10 (best):",
    "value_proposition": "**value_proposition** — Does the email clearly articulate what value the sender offers to the recipient?",
    "personalisation": "**personalisation** — How tailored is the email to the specific recipient? Does it reference their company, role, recent activity, or pain points?",
    "cta": "**cta** — Is there a clear, specific call to action? Is it easy for the recipient to take the next step?",
    "clarity": "**clarity** — Is the message easy to read and understand? Is it concise with a clear structure?",
    "closing": 'Respond with ONLY a JSON object in this exact format, no other text:\n{\n  "personalisation": <1-10>,\n  "clarity": <1-10>,\n  "value_proposition": <1-10>,\n  "cta": <1-10>,\n  "notes": "<brief 1-2 sentence explanation of the scores>"\n}',
}

DEFAULT_CHAIN_EMAIL_BLOCKS = {
    "opening": "You are an expert sales email evaluator. Score the following email within the context of its conversation chain on four dimensions, each from 1 (worst) to 10 (best):",
    "value_proposition": "**value_proposition** — Does the email clearly articulate what value the sender offers?",
    "personalisation": "**personalisation** — How tailored is the email to the specific recipient and conversation context?",
    "cta": "**cta** — Is there a clear, specific call to action?",
    "clarity": "**clarity** — Is the message easy to read and understand? Is it concise with a clear structure?",
    "closing": 'Respond with ONLY a JSON object in this exact format, no other text:\n{\n  "personalisation": <1-10>,\n  "clarity": <1-10>,\n  "value_proposition": <1-10>,\n  "cta": <1-10>,\n  "notes": "<brief 1-2 sentence explanation of the scores>"\n}',
}

DEFAULT_CHAIN_EVAL_BLOCKS = {
    "opening": "You are an expert sales conversation evaluator. Evaluate the following email conversation chain on four dimensions, each from 1 (worst) to 10 (best):",
    "progression": "**progression** — How well does the conversation advance toward the sales goal across emails?",
    "responsiveness": "**responsiveness** — How timely and relevant are the follow-ups?",
    "persistence": "**persistence** — Does the sender maintain appropriate follow-up cadence without being pushy?",
    "conversation_quality": "**conversation_quality** — Overall quality of the conversation as a multi-touch sales engagement.",
    "closing": 'Respond with ONLY a JSON object in this exact format, no other text:\n{\n  "progression": <1-10>,\n  "responsiveness": <1-10>,\n  "persistence": <1-10>,\n  "conversation_quality": <1-10>,\n  "notes": "<brief 1-2 sentence explanation of the scores>"\n}',
}


def upgrade() -> None:
    # Add new JSON columns
    op.add_column('settings', sa.Column('initial_email_prompt_blocks', JSONB, nullable=True))
    op.add_column('settings', sa.Column('chain_email_prompt_blocks', JSONB, nullable=True))
    op.add_column('settings', sa.Column('chain_evaluation_prompt_blocks', JSONB, nullable=True))

    # Migrate data: if old column has custom text, put it in opening block;
    # otherwise use the structured defaults
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, initial_email_prompt, chain_email_prompt, chain_evaluation_prompt FROM settings"))
    for row in rows:
        initial_blocks = DEFAULT_INITIAL_EMAIL_BLOCKS.copy()
        chain_blocks = DEFAULT_CHAIN_EMAIL_BLOCKS.copy()
        eval_blocks = DEFAULT_CHAIN_EVAL_BLOCKS.copy()

        # If user had custom text, preserve it in the opening block
        if row.initial_email_prompt is not None:
            initial_blocks = {
                "opening": row.initial_email_prompt,
                "value_proposition": "",
                "personalisation": "",
                "cta": "",
                "clarity": "",
                "closing": "",
            }
        if row.chain_email_prompt is not None:
            chain_blocks = {
                "opening": row.chain_email_prompt,
                "value_proposition": "",
                "personalisation": "",
                "cta": "",
                "clarity": "",
                "closing": "",
            }
        if row.chain_evaluation_prompt is not None:
            eval_blocks = {
                "opening": row.chain_evaluation_prompt,
                "progression": "",
                "responsiveness": "",
                "persistence": "",
                "conversation_quality": "",
                "closing": "",
            }

        conn.execute(
            sa.text(
                "UPDATE settings SET "
                "initial_email_prompt_blocks = :initial, "
                "chain_email_prompt_blocks = :chain, "
                "chain_evaluation_prompt_blocks = :eval "
                "WHERE id = :id"
            ),
            {
                "id": row.id,
                "initial": json.dumps(initial_blocks),
                "chain": json.dumps(chain_blocks),
                "eval": json.dumps(eval_blocks),
            },
        )

    # Drop old columns
    op.drop_column('settings', 'initial_email_prompt')
    op.drop_column('settings', 'chain_email_prompt')
    op.drop_column('settings', 'chain_evaluation_prompt')


def downgrade() -> None:
    # Re-add old text columns
    op.add_column('settings', sa.Column('initial_email_prompt', sa.Text(), nullable=True))
    op.add_column('settings', sa.Column('chain_email_prompt', sa.Text(), nullable=True))
    op.add_column('settings', sa.Column('chain_evaluation_prompt', sa.Text(), nullable=True))

    # Migrate data back: extract opening block as the text prompt
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, initial_email_prompt_blocks, chain_email_prompt_blocks, chain_evaluation_prompt_blocks FROM settings"))
    for row in rows:
        initial_text = None
        chain_text = None
        eval_text = None

        if row.initial_email_prompt_blocks:
            blocks = json.loads(row.initial_email_prompt_blocks) if isinstance(row.initial_email_prompt_blocks, str) else row.initial_email_prompt_blocks
            initial_text = blocks.get("opening", "")

        if row.chain_email_prompt_blocks:
            blocks = json.loads(row.chain_email_prompt_blocks) if isinstance(row.chain_email_prompt_blocks, str) else row.chain_email_prompt_blocks
            chain_text = blocks.get("opening", "")

        if row.chain_evaluation_prompt_blocks:
            blocks = json.loads(row.chain_evaluation_prompt_blocks) if isinstance(row.chain_evaluation_prompt_blocks, str) else row.chain_evaluation_prompt_blocks
            eval_text = blocks.get("opening", "")

        conn.execute(
            sa.text(
                "UPDATE settings SET "
                "initial_email_prompt = :initial, "
                "chain_email_prompt = :chain, "
                "chain_evaluation_prompt = :eval "
                "WHERE id = :id"
            ),
            {"id": row.id, "initial": initial_text, "chain": chain_text, "eval": eval_text},
        )

    # Drop new JSON columns
    op.drop_column('settings', 'initial_email_prompt_blocks')
    op.drop_column('settings', 'chain_email_prompt_blocks')
    op.drop_column('settings', 'chain_evaluation_prompt_blocks')
