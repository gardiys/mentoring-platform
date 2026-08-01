"""Add a required learning direction to interview processes."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260801_0016"
down_revision: str | None = "20260801_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "interview_processes",
        sa.Column("track_id", sa.UUID(), nullable=True),
    )
    op.execute(
        """
        UPDATE interview_processes AS process
        SET track_id = COALESCE(
            (
                SELECT enrollment.track_id
                FROM learning_track_enrollments AS enrollment
                JOIN learning_tracks AS track ON track.id = enrollment.track_id
                WHERE enrollment.user_id = process.user_id
                ORDER BY track.position, track.title, track.id
                LIMIT 1
            ),
            (
                SELECT track.id
                FROM learning_tracks AS track
                ORDER BY
                    CASE WHEN track.slug = 'python' THEN 0 ELSE 1 END,
                    track.position,
                    track.title,
                    track.id
                LIMIT 1
            )
        )
        """
    )
    op.alter_column("interview_processes", "track_id", nullable=False)
    op.create_foreign_key(
        "fk_interview_processes_track_id_learning_tracks",
        "interview_processes",
        "learning_tracks",
        ["track_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_interview_processes_track_id",
        "interview_processes",
        ["track_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_interview_processes_track_id", table_name="interview_processes")
    op.drop_constraint(
        "fk_interview_processes_track_id_learning_tracks",
        "interview_processes",
        type_="foreignkey",
    )
    op.drop_column("interview_processes", "track_id")
