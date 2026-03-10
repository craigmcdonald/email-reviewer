"""add unique index on emails.hubspot_id

Revision ID: h8c9d0e1f2a3
Revises: g7b8c9d0e1f2
Create Date: 2026-03-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'h8c9d0e1f2a3'
down_revision: Union[str, None] = 'g7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('ix_emails_hubspot_id', 'emails', ['hubspot_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_emails_hubspot_id', table_name='emails')
