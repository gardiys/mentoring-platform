"""Record every user-triggered AI operation for durable quotas.

Revision ID: 20260803_0031
Revises: 20260802_0030
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260803_0031"
down_revision: str | None = "20260802_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "intelligence_ai_admissions",
        sa.Column("requester_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("interview_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("operation", sa.String(length=40), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["interview_id"],
            ["intelligence_interviews.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["requester_user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_intelligence_ai_admissions_interview",
        "intelligence_ai_admissions",
        ["interview_id", "requested_at"],
    )
    op.create_index(
        "ix_intelligence_ai_admissions_requester_requested",
        "intelligence_ai_admissions",
        ["requester_user_id", "requested_at"],
    )

    # Preserve today's quota across deployment and retain launches whose
    # analysis row was manually deleted while the journal stage remains.
    op.execute(
        """
        INSERT INTO intelligence_ai_admissions (
            id,
            requester_user_id,
            interview_id,
            operation,
            requested_at
        )
        SELECT
            md5(stage.id::text || '-analysis')::uuid,
            process.user_id,
            intelligence.id,
            'analysis',
            stage.ai_analysis_requested_at
        FROM interview_process_stages AS stage
        JOIN interview_processes AS process ON process.id = stage.process_id
        LEFT JOIN intelligence_interviews AS intelligence ON intelligence.stage_id = stage.id
        WHERE stage.ai_analysis_requested_at IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_intelligence_ai_admissions_requester_requested",
        table_name="intelligence_ai_admissions",
    )
    op.drop_index(
        "ix_intelligence_ai_admissions_interview",
        table_name="intelligence_ai_admissions",
    )
    op.drop_table("intelligence_ai_admissions")
