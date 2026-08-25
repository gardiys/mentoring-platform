"""Optimize notification inbox polling.

Revision ID: 20260825_0068
Revises: 20260819_0067
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260825_0068"
down_revision: str | None = "20260819_0067"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_platform_notifications_user_created_id",
        "platform_notifications",
        ["user_id", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_platform_notifications_user_created_id",
        table_name="platform_notifications",
    )
