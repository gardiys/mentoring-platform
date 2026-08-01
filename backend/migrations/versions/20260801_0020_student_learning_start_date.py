"""Add the canonical student learning start date."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260801_0020"
down_revision: str | None = "20260801_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("learning_start_date", sa.Date(), nullable=True))
    # Preserve an already chosen roadmap start. Imported students without a
    # started roadmap receive their persisted account creation date.
    op.execute(
        """
        UPDATE users AS student
        SET learning_start_date = COALESCE(
            (
                SELECT MIN(enrollment.started_at)::date
                FROM roadmap_enrollments AS enrollment
                WHERE enrollment.user_id = student.id
                  AND enrollment.started_at IS NOT NULL
            ),
            student.created_at::date
        )
        WHERE student.role = 'student'
        """
    )
    op.execute(
        """
        UPDATE roadmap_enrollments AS enrollment
        SET started_at = student.learning_start_date::timestamp AT TIME ZONE 'UTC'
        FROM users AS student
        WHERE student.id = enrollment.user_id
          AND enrollment.started_at IS NULL
          AND student.learning_start_date IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_column("users", "learning_start_date")
