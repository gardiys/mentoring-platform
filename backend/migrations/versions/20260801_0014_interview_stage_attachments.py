"""Add multiple attachments to interview stages."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260801_0014"
down_revision: str | None = "20260801_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "interview_process_stage_attachments",
        sa.Column("stage_id", sa.UUID(), nullable=False),
        sa.Column("storage_key", sa.String(length=180), nullable=False),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=160), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
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
            ["stage_id"], ["interview_process_stages.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_interview_stage_attachments_stage",
        "interview_process_stage_attachments",
        ["stage_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_interview_stage_attachments_stage",
        table_name="interview_process_stage_attachments",
    )
    op.drop_table("interview_process_stage_attachments")
