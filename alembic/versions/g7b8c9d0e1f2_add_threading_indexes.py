"""add indexes on message_id, in_reply_to, thread_id

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-03-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'g7b8c9d0e1f2'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(op.f('ix_emails_message_id'), 'emails', ['message_id'])
    op.create_index(op.f('ix_emails_in_reply_to'), 'emails', ['in_reply_to'])
    op.create_index(op.f('ix_emails_thread_id'), 'emails', ['thread_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_emails_thread_id'), table_name='emails')
    op.drop_index(op.f('ix_emails_in_reply_to'), table_name='emails')
    op.drop_index(op.f('ix_emails_message_id'), table_name='emails')
