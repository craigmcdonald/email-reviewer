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
        "You are a demanding sales email evaluator. Score the following outgoing email on four dimensions, each from 1 to 10. "
        "Apply these standards strictly: 1-3 = poor (template-like, generic, or adds no value), 4-6 = adequate (competent but unremarkable), "
        "7-8 = strong (demonstrates genuine effort and insight), 9-10 = exceptional (rarely awarded - requires outstanding craft). "
        "A score of 7+ on any dimension requires clear, specific evidence of quality beyond the absence of errors.\n\n"
        "The email includes the sender's role (Rep role). Adjust your evaluation accordingly:\n"
        "- SDR or BizDev: Cold outreach to prospects. Most mass outreach should score 3-5. "
        "Emails to well-known or large companies face a higher bar because those prospects receive high volumes of outreach and generic pitches will not cut through.\n"
        "- AM (Account Manager): Communication with existing clients. These emails serve operational purposes - campaign briefings, performance updates, renewals, upsells. "
        "The bar for 'good' shifts: value comes from specific data (metrics, lead counts, CPL, conversion rates), tailored recommendations based on the client's campaign performance, "
        "and clear operational asks with deadlines. A generic status update with no data or specificity is a 3-4. "
        "An email packed with campaign-specific numbers, actionable insights, and concrete next steps is a 7-9."
    ),
    "value_proposition": (
        "**value_proposition** — Does the email present a compelling, specific reason for the recipient to engage or act? "
        "For SDR/BizDev: A strong value proposition identifies a problem or opportunity the recipient faces and explains how the sender addresses it. "
        "Flattering the recipient's own brand ('you already fit how Gen Z does X') is not a value proposition - it tells them what they already know. "
        "Stating that the sender exists and does something generic ('we connect students') without tying it to a specific gap or need is weak. "
        "Score 1-3 if the email just describes the sender's service without connecting to the recipient's situation. "
        "Score 4-6 if there is a relevant connection but it is obvious or generic to the sector. "
        "Score 7+ only if the email surfaces a specific insight, data point, or angle that gives the recipient a concrete reason to respond.\n"
        "For AM: Value means giving the client something actionable - performance data, benchmarks, recommendations, or strategic framing they can use to make decisions. "
        "A vague 'just checking in' or 'wanted to touch base' is a 1-3. "
        "Score 7+ if the email contains specific metrics, data-driven recommendations, or modelled projections tied to the client's situation."
    ),
    "personalisation": (
        "**personalisation** — How much genuine, specific knowledge about the recipient is evident? "
        "For SDR/BizDev: Inserting a company name, industry label, or generic statement about their sector into a template is not personalisation - "
        "if the same paragraph would work for any company in that sector with a name swap, score 1-3. "
        "References to the recipient's specific situation, recent activity, public statements, market challenges, or competitive landscape demonstrate real research. "
        "Well-known companies face a higher bar: mentioning what they obviously do is not personalisation. "
        "Score 7+ only if the email shows knowledge that could not come from a 10-second glance at the company homepage.\n"
        "For AM: Personalisation means using the client's own campaign data, account history, and specific context. "
        "Referencing their actual lead counts, campus selections, performance metrics, or previous conversations demonstrates real engagement. "
        "A generic account update that could apply to any client is a 3-4. "
        "Score 7+ if the email uses client-specific data to frame recommendations or next steps."
    ),
    "cta": (
        "**cta** — Is there a clear, specific, low-friction call to action? "
        "For SDR/BizDev: A vague 'would you be open to a quick call?' with no proposed time, agenda, or specificity is a 4-5. "
        "Score 7+ if the CTA proposes a concrete next step that makes it easy for the recipient to say yes.\n"
        "For AM: Score based on specificity and actionability. "
        "'Let me know your thoughts' is a 3-4. "
        "A concrete ask with a deadline ('confirm by 28 February to hold pricing', 'send final assets by Friday 6 September') is a 7-9."
    ),
    "clarity": (
        "**clarity** — Is the message easy to read, well-structured, and concise? "
        "Penalise waffle, excessive length, jargon, and unclear purpose. "
        "A short, well-structured email with a clear point scores well here even if weak on other dimensions. "
        "For AM emails, longer emails are acceptable if they are data-dense and well-structured - penalise length only when it adds no information."
    ),
    "closing": 'Respond with ONLY a JSON object in this exact format, no other text:\n{\n  "personalisation": <1-10>,\n  "clarity": <1-10>,\n  "value_proposition": <1-10>,\n  "cta": <1-10>,\n  "notes": "<brief 1-2 sentence explanation of the scores>"\n}',
}

DEFAULT_CHAIN_EMAIL_BLOCKS = {
    "opening": (
        "You are a demanding sales email evaluator. Score the following email within the context of its conversation chain on four dimensions, each from 1 to 10. "
        "Apply these standards strictly: 1-3 = poor, 4-6 = adequate, 7-8 = strong, 9-10 = exceptional. "
        "A score of 7+ requires clear evidence of quality. Consider the conversation history when evaluating.\n\n"
        "The email includes the sender's role (Rep role). Adjust your evaluation accordingly:\n"
        "- SDR or BizDev: Does this email advance the prospecting relationship or just repeat earlier pitches?\n"
        "- AM: Does this email move the client relationship forward with specific data, updates, or asks? "
        "AM chain emails should be evaluated on whether they build on prior conversation with new information, metrics, or decisions."
    ),
    "value_proposition": (
        "**value_proposition** — Does the email articulate specific value for the recipient, building on or advancing beyond what was said in previous messages? "
        "For SDR/BizDev: Repeating the same pitch from earlier in the chain is a 1-3. "
        "Score 7+ only if the email introduces new information, addresses a concern raised in the conversation, or deepens the value case.\n"
        "For AM: Does the email provide new data, updated metrics, or actionable recommendations that build on the conversation? "
        "Repeating what was already said is a 1-3. Score 7+ if it advances the client's decision-making with fresh, specific information."
    ),
    "personalisation": (
        "**personalisation** — Does the email demonstrate genuine knowledge of the recipient's situation? "
        "For SDR/BizDev: Template-level personalisation (company name, sector label) is a 1-3. "
        "Score 7+ only if the email shows real research or meaningful engagement with the recipient's needs.\n"
        "For AM: Drawing on the client's specific campaign data, previous discussions, or account context scores higher. "
        "Score 7+ if the email uses client-specific details to frame its points."
    ),
    "cta": (
        "**cta** — Is there a clear, specific call to action appropriate to this stage of the conversation? "
        "Score 7+ if the CTA proposes a concrete next step. "
        "For AM emails, specific deadlines or deliverable requests score higher than open-ended asks."
    ),
    "clarity": (
        "**clarity** — Is the message easy to read, well-structured, and concise? "
        "Penalise waffle, excessive length, and unclear purpose. "
        "For AM emails, longer messages are acceptable if data-dense and well-organised."
    ),
    "closing": 'Respond with ONLY a JSON object in this exact format, no other text:\n{\n  "personalisation": <1-10>,\n  "clarity": <1-10>,\n  "value_proposition": <1-10>,\n  "cta": <1-10>,\n  "notes": "<brief 1-2 sentence explanation of the scores>"\n}',
}

DEFAULT_CHAIN_EVAL_BLOCKS = {
    "opening": (
        "You are a demanding sales conversation evaluator. Evaluate the following email conversation chain on four dimensions, each from 1 to 10. "
        "Apply these standards strictly: 1-3 = poor, 4-6 = adequate, 7-8 = strong, 9-10 = exceptional.\n\n"
        "The email includes the sender's role (Rep role). Adjust your evaluation accordingly:\n"
        "- SDR or BizDev: Most outreach sequences that get no reply and just repeat the same pitch should score in the 2-4 range.\n"
        "- AM: Evaluate how well the conversation manages the client relationship. "
        "A chain that progresses from briefing to performance data to strategic recommendations shows strong account management. "
        "A chain of vague check-ins with no substance is a 2-4."
    ),
    "progression": (
        "**progression** — How well does the conversation advance toward its goal across emails? "
        "For SDR/BizDev: Sending the same template pitch repeatedly with minor rewording is a 1-3. "
        "Score 7+ only if the sequence shows genuine strategic progression - new angles, escalating value, or adapting based on signals.\n"
        "For AM: Does the conversation move through logical stages (briefing, updates, reviews, next steps)? "
        "Score 7+ if each email builds on the last with new data or decisions."
    ),
    "responsiveness": (
        "**responsiveness** — How timely and relevant are the follow-ups? "
        "Does the sender adapt to signals from the recipient (or lack thereof)? "
        "For SDR/BizDev: Sending on a rigid cadence with no adaptation is a 4-5.\n"
        "For AM: Does the sender respond to client questions or concerns with relevant information? "
        "Proactive updates at appropriate intervals score higher than reactive-only communication."
    ),
    "persistence": (
        "**persistence** — Does the sender maintain appropriate follow-up cadence? "
        "For SDR/BizDev: Balance persistence without being pushy or giving up too early.\n"
        "For AM: Consistent, proactive communication with the client. Regular updates with substance score well; going silent for long periods scores poorly."
    ),
    "conversation_quality": (
        "**conversation_quality** — Overall quality of the conversation as a multi-touch engagement. "
        "For SDR/BizDev: A series of template follow-ups to an unresponsive prospect is a 2-4 regardless of how polished each individual email is.\n"
        "For AM: A conversation that delivers data, recommendations, and clear next steps across multiple touchpoints is strong. "
        "A conversation of vague pleasantries with no operational substance is a 2-4."
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
