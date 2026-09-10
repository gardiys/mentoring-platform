"""Archive AI analysis versions and isolate restarted jobs."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260910_0086"
down_revision = "20260908_0085"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "intelligence_interviews",
        sa.Column("analysis_revision", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_table(
        "intelligence_analysis_archives",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "interview_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("intelligence_interviews.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "requested_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("interview_id", "revision", name="uq_analysis_archive_revision"),
    )
    op.create_index(
        "ix_intelligence_analysis_archives_interview_id",
        "intelligence_analysis_archives",
        ["interview_id"],
    )


def downgrade() -> None:
    op.drop_table("intelligence_analysis_archives")
    op.drop_column("intelligence_interviews", "analysis_revision")
