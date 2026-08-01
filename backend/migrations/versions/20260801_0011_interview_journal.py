"""Add personal interview process journal and protected attachments."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260801_0011"
down_revision: str | None = "20260801_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    process_status = postgresql.ENUM(
        "active", "closed", "offer", name="interview_process_status", create_type=False
    )
    stage_type = postgresql.ENUM(
        "screening",
        "technical_screening",
        "technical_interview",
        "system_design",
        "final_interview",
        "other",
        name="interview_stage_type",
        create_type=False,
    )
    process_status.create(op.get_bind(), checkfirst=True)
    stage_type.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "interview_processes",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("company_name", sa.String(length=240), nullable=False),
        sa.Column("status", process_status, nullable=False),
        sa.Column("close_reason", sa.Text(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("offer_storage_key", sa.String(length=180), nullable=True),
        sa.Column("offer_filename", sa.String(length=500), nullable=True),
        sa.Column("offer_content_type", sa.String(length=160), nullable=True),
        sa.Column("offer_size", sa.BigInteger(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_interview_processes_user_status",
        "interview_processes",
        ["user_id", "status"],
    )
    op.create_table(
        "interview_process_stages",
        sa.Column("process_id", sa.UUID(), nullable=False),
        sa.Column("stage_type", stage_type, nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("media_storage_key", sa.String(length=180), nullable=True),
        sa.Column("media_filename", sa.String(length=500), nullable=True),
        sa.Column("media_content_type", sa.String(length=160), nullable=True),
        sa.Column("media_size", sa.BigInteger(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["process_id"], ["interview_processes.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_interview_process_stages_process_date",
        "interview_process_stages",
        ["process_id", "scheduled_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_interview_process_stages_process_date",
        table_name="interview_process_stages",
    )
    op.drop_table("interview_process_stages")
    op.drop_index("ix_interview_processes_user_status", table_name="interview_processes")
    op.drop_table("interview_processes")
    postgresql.ENUM(name="interview_stage_type").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="interview_process_status").drop(op.get_bind(), checkfirst=True)
