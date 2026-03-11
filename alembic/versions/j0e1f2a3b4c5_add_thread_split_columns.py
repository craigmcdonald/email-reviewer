"""add thread split columns to emails and settings

Revision ID: j0e1f2a3b4c5
Revises: i9d0e1f2a3b4
Create Date: 2026-03-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = 'j0e1f2a3b4c5'
down_revision: Union[str, None] = 'i9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('emails', sa.Column('is_thread_split', sa.Boolean(), server_default='0', nullable=False))
    op.add_column('emails', sa.Column('split_from_id', sa.Integer(), sa.ForeignKey('emails.id'), nullable=True))
    op.add_column('settings', sa.Column('thread_splitter_prompt_blocks', JSONB(), nullable=True))
    op.add_column('settings', sa.Column('thread_split_indicators', JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('settings', 'thread_split_indicators')
    op.drop_column('settings', 'thread_splitter_prompt_blocks')
    op.drop_column('emails', 'split_from_id')
    op.drop_column('emails', 'is_thread_split')
