"""Add mentor directions and knowledge topic directions."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260801_0022"
down_revision = "20260801_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mentor_track_assignments",
        sa.Column("mentor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("track_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["mentor_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["track_id"], ["learning_tracks.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("mentor_id", "track_id"),
    )
    op.create_table(
        "knowledge_topic_tracks",
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("track_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["topic_id"], ["knowledge_topics.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["track_id"], ["learning_tracks.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("topic_id", "track_id"),
    )
    op.execute(
        """
        INSERT INTO mentor_track_assignments (mentor_id, track_id)
        SELECT DISTINCT ms.mentor_id, lte.track_id
        FROM mentor_students ms
        JOIN learning_track_enrollments lte ON lte.user_id = ms.student_id
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO mentor_track_assignments (mentor_id, track_id)
        SELECT u.id, lt.id
        FROM users u CROSS JOIN learning_tracks lt
        WHERE u.role = 'mentor'
          AND NOT EXISTS (
              SELECT 1 FROM mentor_track_assignments mta WHERE mta.mentor_id = u.id
          )
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO knowledge_topic_tracks (topic_id, track_id)
        SELECT kt.id, lt.id FROM knowledge_topics kt CROSS JOIN learning_tracks lt
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("knowledge_topic_tracks")
    op.drop_table("mentor_track_assignments")
