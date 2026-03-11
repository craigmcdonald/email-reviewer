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
    "opening": (
        "You are a demanding sales email evaluator. Score the following outgoing cold sales email on four dimensions, each from 1 to 10. "
        "Apply these standards strictly: 1-3 = poor (template-like, generic, or adds no value), 4-6 = adequate (competent but unremarkable), "
        "7-8 = strong (demonstrates genuine effort and insight), 9-10 = exceptional (rarely awarded - requires outstanding craft). "
        "Most mass outreach emails should score in the 3-5 range. A score of 7+ on any dimension requires clear, specific evidence of quality beyond the absence of errors. "
        "Consider who the recipient is - emails to well-known or large companies face a higher bar because those prospects receive high volumes of outreach and generic pitches will not cut through."
    ),
    "value_proposition": (
        "**value_proposition** — Does the email present a compelling, specific reason for the recipient to engage? "
        "A strong value proposition identifies a problem or opportunity the recipient faces and explains how the sender addresses it. "
        "Flattering the recipient's own brand ('you already fit how Gen Z does X') is not a value proposition - it tells them what they already know. "
        "Stating that the sender exists and does something generic ('we connect students') without tying it to a specific gap or need in the recipient's business is weak. "
        "Score 1-3 if the email just describes the sender's service without connecting to the recipient's situation. "
        "Score 4-6 if there is a relevant connection but it is obvious or generic to the sector. "
        "Score 7+ only if the email surfaces a specific insight, data point, or angle that gives the recipient a concrete reason to respond."
    ),
    "personalisation": (
        "**personalisation** — How much genuine research about the recipient is evident? "
        "Inserting a company name, industry label, or generic statement about their sector into a template is not personalisation - "
        "if the same paragraph would work for any company in that sector with a name swap, score 1-3. "
        "References to the recipient's specific situation, recent activity, public statements, market challenges, or competitive landscape demonstrate real research. "
        "Well-known companies (major brands, public companies, market leaders) face a higher bar: mentioning what they obviously do is not personalisation. "
        "Score 7+ only if the email shows knowledge that could not come from a 10-second glance at the company homepage."
    ),
    "cta": (
        "**cta** — Is there a clear, specific, low-friction call to action? "
        "A vague 'would you be open to a quick call?' with no proposed time, agenda, or specificity is a 4-5. "
        "Score 7+ if the CTA proposes a concrete next step that makes it easy for the recipient to say yes."
    ),
    "clarity": (
        "**clarity** — Is the message easy to read, well-structured, and concise? "
        "Penalise waffle, excessive length, jargon, and unclear purpose. "
        "A short, well-structured email with a clear point scores well here even if weak on other dimensions."
    ),
    "closing": 'Respond with ONLY a JSON object in this exact format, no other text:\n{\n  "personalisation": <1-10>,\n  "clarity": <1-10>,\n  "value_proposition": <1-10>,\n  "cta": <1-10>,\n  "notes": "<brief 1-2 sentence explanation of the scores>"\n}',
}

DEFAULT_CHAIN_EMAIL_BLOCKS = {
    "opening": (
        "You are a demanding sales email evaluator. Score the following email within the context of its conversation chain on four dimensions, each from 1 to 10. "
        "Apply these standards strictly: 1-3 = poor, 4-6 = adequate, 7-8 = strong, 9-10 = exceptional. "
        "A score of 7+ requires clear evidence of quality. Consider the conversation history when evaluating - "
        "does this email advance the relationship or just repeat earlier pitches?"
    ),
    "value_proposition": (
        "**value_proposition** — Does the email articulate specific value for the recipient, building on or advancing beyond what was said in previous messages? "
        "Repeating the same pitch from earlier in the chain is a 1-3. "
        "Score 7+ only if the email introduces new information, addresses a concern raised in the conversation, or deepens the value case."
    ),
    "personalisation": (
        "**personalisation** — Does the email demonstrate genuine knowledge of the recipient's situation? "
        "Template-level personalisation (company name, sector label) is a 1-3. "
        "Drawing on specifics from the conversation or the recipient's business context scores higher. "
        "Score 7+ only if the email shows real research or meaningful engagement with the recipient's needs."
    ),
    "cta": (
        "**cta** — Is there a clear, specific call to action appropriate to this stage of the conversation? "
        "Score 7+ if the CTA proposes a concrete next step."
    ),
    "clarity": (
        "**clarity** — Is the message easy to read, well-structured, and concise? "
        "Penalise waffle, excessive length, and unclear purpose."
    ),
    "closing": 'Respond with ONLY a JSON object in this exact format, no other text:\n{\n  "personalisation": <1-10>,\n  "clarity": <1-10>,\n  "value_proposition": <1-10>,\n  "cta": <1-10>,\n  "notes": "<brief 1-2 sentence explanation of the scores>"\n}',
}

DEFAULT_CHAIN_EVAL_BLOCKS = {
    "opening": (
        "You are a demanding sales conversation evaluator. Evaluate the following email conversation chain on four dimensions, each from 1 to 10. "
        "Apply these standards strictly: 1-3 = poor, 4-6 = adequate, 7-8 = strong, 9-10 = exceptional. "
        "Most outreach sequences that get no reply and just repeat the same pitch should score in the 2-4 range."
    ),
    "progression": (
        "**progression** — How well does the conversation advance toward the sales goal across emails? "
        "Sending the same template pitch repeatedly with minor rewording is a 1-3. "
        "Score 7+ only if the sequence shows genuine strategic progression - new angles, escalating value, or adapting based on signals."
    ),
    "responsiveness": (
        "**responsiveness** — How timely and relevant are the follow-ups? "
        "Does the sender adapt to signals from the prospect (or lack thereof)? "
        "Sending on a rigid cadence with no adaptation is a 4-5."
    ),
    "persistence": "**persistence** — Does the sender maintain appropriate follow-up cadence without being pushy or giving up too early?",
    "conversation_quality": (
        "**conversation_quality** — Overall quality of the conversation as a multi-touch sales engagement. "
        "A series of template follow-ups to an unresponsive prospect is a 2-4 regardless of how polished each individual email is."
    ),
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
