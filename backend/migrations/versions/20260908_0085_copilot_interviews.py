"""Copilot interview usage, upload linkage and team context."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260908_0085"
down_revision = "20260908_0084"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("interview_processes", sa.Column("team_name", sa.String(240)))
    op.add_column("interview_processes", sa.Column("position_name", sa.String(240)))
    op.add_column("interview_processes", sa.Column("company_notes", sa.Text()))
    op.create_table(
        "copilot_sessions",
        sa.Column("tenant_id", sa.String(100), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "student_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "process_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("interview_processes.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "stage_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("interview_process_stages.id", ondelete="SET NULL"),
        ),
        sa.Column("mode", sa.String(10), nullable=False),
        sa.Column("track", sa.String(20), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("active_ms", sa.BigInteger(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
    )
    op.create_index("ix_copilot_sessions_student_id", "copilot_sessions", ["student_id"])
    op.create_index("ix_copilot_sessions_started_at", "copilot_sessions", ["started_at"])


def downgrade() -> None:
    op.drop_table("copilot_sessions")
    for column in ["company_notes", "position_name", "team_name"]:
        op.drop_column("interview_processes", column)
