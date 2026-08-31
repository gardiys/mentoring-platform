"""Link repeat Python enrollment to the completed enrollment composite key.

Revision ID: 20260831_0075
Revises: 20260831_0074
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260831_0075"
down_revision: str | None = "20260831_0074"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_python_repeat_previous_enrollment",
        "python_repeat_enrollments",
        "learning_track_enrollments",
        ["student_id", "previous_track_id"],
        ["user_id", "track_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_python_repeat_previous_enrollment",
        "python_repeat_enrollments",
        type_="foreignkey",
    )
