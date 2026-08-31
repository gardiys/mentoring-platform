"""Add consultation catalog types and administrator-selected mentors.

Revision ID: 20260831_0071
Revises: 20260830_0070
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260831_0071"
down_revision: str | None = "20260830_0070"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    consultation_type = postgresql.ENUM(
        "free_topic",
        "technical_mock",
        "legend_mock",
        "resume_legend",
        "system_design_mock",
        "work_task",
        name="consultation_type",
    )
    consultation_type.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "consultation_mentor_settings",
        sa.Column("mentor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.ForeignKeyConstraint(["mentor_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("mentor_id"),
    )
    op.add_column(
        "consultation_requests",
        sa.Column(
            "consultation_type",
            postgresql.ENUM(name="consultation_type", create_type=False),
            server_default="free_topic",
            nullable=False,
        ),
    )
    op.alter_column(
        "consultation_requests",
        "mentor_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    # The previous schema required a concrete mentor. Requests deliberately
    # created with the "any mentor" option cannot be represented there.
    op.execute("DELETE FROM consultation_requests WHERE mentor_id IS NULL")
    op.alter_column(
        "consultation_requests",
        "mentor_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.drop_column("consultation_requests", "consultation_type")
    op.drop_table("consultation_mentor_settings")
    postgresql.ENUM(name="consultation_type").drop(op.get_bind(), checkfirst=True)
