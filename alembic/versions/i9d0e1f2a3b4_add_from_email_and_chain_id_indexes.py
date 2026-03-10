"""add indexes on emails.from_email and emails.chain_id

Revision ID: i9d0e1f2a3b4
Revises: h8c9d0e1f2a3
Create Date: 2026-03-10 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'i9d0e1f2a3b4'
down_revision: Union[str, None] = 'h8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('ix_emails_from_email', 'emails', ['from_email'])
    op.create_index('ix_emails_chain_id', 'emails', ['chain_id'])


def downgrade() -> None:
    op.drop_index('ix_emails_chain_id', table_name='emails')
    op.drop_index('ix_emails_from_email', table_name='emails')
