"""Add comments to catalog interview stages."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260801_0015"
down_revision: str | None = "20260801_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "interview_stage_comments",
        sa.Column("stage_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_interview_stage_comments_stage_created",
        "interview_stage_comments",
        ["stage_id", "created_at"],
    )
    op.create_index(
        "ix_interview_stage_comments_user_id",
        "interview_stage_comments",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_interview_stage_comments_user_id", table_name="interview_stage_comments")
    op.drop_index(
        "ix_interview_stage_comments_stage_created",
        table_name="interview_stage_comments",
    )
    op.drop_table("interview_stage_comments")
