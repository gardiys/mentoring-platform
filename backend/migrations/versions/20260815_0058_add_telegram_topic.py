"""Add Telegram forum topic to notification outbox.

Revision ID: 20260815_0058
Revises: 20260815_0057
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260815_0058"
down_revision: str | None = "20260815_0057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "telegram_outbox",
        sa.Column("message_thread_id", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("telegram_outbox", "message_thread_id")
