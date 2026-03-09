"""add email classification and follow-up scoring fields

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-03-09 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = 'g7b8c9d0e1f2'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('emails', sa.Column('is_auto_reply', sa.Boolean(), server_default='0', nullable=False))
    op.add_column('emails', sa.Column('quoted_metadata', JSONB(), nullable=True))
    op.add_column('settings', sa.Column('classifier_prompt_blocks', JSONB(), nullable=True))
    op.add_column('settings', sa.Column('follow_up_email_prompt_blocks', JSONB(), nullable=True))

    # Backfill obvious auto-replies by subject pattern
    op.execute(
        "UPDATE emails SET is_auto_reply = true "
        "WHERE direction = 'INCOMING_EMAIL' AND ("
        "subject ILIKE 'Automatic reply:%' OR "
        "subject ILIKE 'Out of Office:%' OR "
        "subject ILIKE 'OOO:%' OR "
        "subject ILIKE 'Undeliverable:%' OR "
        "subject ILIKE 'Mail Delivery Failed%' OR "
        "subject ILIKE 'Accepted:%' OR "
        "subject ILIKE 'Declined:%' OR "
        "subject ILIKE 'Tentative:%'"
        ")"
    )


def downgrade() -> None:
    op.drop_column('settings', 'follow_up_email_prompt_blocks')
    op.drop_column('settings', 'classifier_prompt_blocks')
    op.drop_column('emails', 'quoted_metadata')
    op.drop_column('emails', 'is_auto_reply')
