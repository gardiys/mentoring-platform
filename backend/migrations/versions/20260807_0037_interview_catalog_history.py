"""Add interview catalog view history and favorites.

Revision ID: 20260807_0037
Revises: 20260805_0036
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260807_0037"
down_revision: str | None = "20260805_0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "interview_catalog_views",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("first_viewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_viewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["stage_id"],
            ["interview_process_stages.id"],
            ondelete="CASCADE",
            name="fk_interview_catalog_views_stage_id_interview_process_stages",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_interview_catalog_views_user_id_users",
        ),
        sa.PrimaryKeyConstraint("user_id", "stage_id", name="pk_interview_catalog_views"),
    )
    op.create_index(
        "ix_interview_catalog_views_user",
        "interview_catalog_views",
        ["user_id", "last_viewed_at"],
    )
    op.create_table(
        "interview_catalog_favorites",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("process_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["process_id"],
            ["interview_processes.id"],
            ondelete="CASCADE",
            name="fk_interview_catalog_favorites_process_id_interview_processes",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_interview_catalog_favorites_user_id_users",
        ),
        sa.PrimaryKeyConstraint("user_id", "process_id", name="pk_interview_catalog_favorites"),
    )
    op.create_index(
        "ix_interview_catalog_favorites_user",
        "interview_catalog_favorites",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_interview_catalog_favorites_user", table_name="interview_catalog_favorites")
    op.drop_table("interview_catalog_favorites")
    op.drop_index("ix_interview_catalog_views_user", table_name="interview_catalog_views")
    op.drop_table("interview_catalog_views")
