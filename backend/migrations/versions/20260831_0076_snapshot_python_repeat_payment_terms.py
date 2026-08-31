"""Snapshot repeat-Python terms on every payment attempt.

Revision ID: 20260831_0076
Revises: 20260831_0075
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260831_0076"
down_revision: str | None = "20260831_0075"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "opportunity_payment_attempts",
        sa.Column("terms_snapshot", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("opportunity_payment_attempts", "terms_snapshot")
