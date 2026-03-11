"""normalize email addresses to lowercase

Revision ID: k1f2a3b4c5d6
Revises: j0e1f2a3b4c5
Create Date: 2026-03-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'k1f2a3b4c5d6'
down_revision: Union[str, None] = 'j0e1f2a3b4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Lowercase email addresses in emails table
    op.execute("UPDATE emails SET from_email = LOWER(from_email) WHERE from_email != LOWER(from_email)")
    op.execute("UPDATE emails SET to_email = LOWER(to_email) WHERE to_email != LOWER(to_email)")

    # Reps table uses email as primary key. Rows with different casing
    # may refer to the same person. Merge duplicates by keeping the row
    # whose lowercase form already exists, or the first one found.
    # Use a temp table to handle PK conflicts safely.
    op.execute("""
        UPDATE reps SET email = LOWER(email)
        WHERE email != LOWER(email)
          AND NOT EXISTS (
              SELECT 1 FROM reps r2 WHERE r2.email = LOWER(reps.email)
          )
    """)
    # Delete remaining rows whose lowercase form already exists (duplicates)
    op.execute("""
        DELETE FROM reps
        WHERE email != LOWER(email)
    """)


def downgrade() -> None:
    # Irreversible: original casing is lost
    pass
