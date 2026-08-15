"""Add in-app notifications and reliable Telegram outbox.

Revision ID: 20260815_0057
Revises: 20260815_0056
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260815_0057"
down_revision: str | None = "20260815_0056"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    notification_kind = postgresql.ENUM(
        "interview_published",
        "mock_interview",
        "mock_feedback",
        "mentor_document",
        "offer",
        "status_changed",
        "mentor_feedback",
        "payment_due",
        name="notification_kind",
        create_type=False,
    )
    telegram_outbox_status = postgresql.ENUM(
        "queued",
        "processing",
        "sent",
        "failed",
        name="telegram_outbox_status",
        create_type=False,
    )
    notification_kind.create(op.get_bind(), checkfirst=True)
    telegram_outbox_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "platform_notifications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("kind", notification_kind, nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("action_url", sa.String(length=1000), nullable=False),
        sa.Column("event_key", sa.String(length=240), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_key"),
    )
    op.create_index(
        "ix_platform_notifications_user_read_created",
        "platform_notifications",
        ["user_id", "read_at", "created_at"],
    )

    op.create_table(
        "telegram_outbox",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_key", sa.String(length=240), nullable=False),
        sa.Column("chat_id", sa.String(length=100), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("action_label", sa.String(length=80), nullable=True),
        sa.Column("action_url", sa.String(length=1000), nullable=True),
        sa.Column(
            "status", telegram_outbox_status, server_default="queued", nullable=False
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_key"),
    )
    op.create_index(
        "ix_telegram_outbox_status_available",
        "telegram_outbox",
        ["status", "available_at", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_telegram_outbox_status_available", table_name="telegram_outbox")
    op.drop_table("telegram_outbox")
    op.drop_index(
        "ix_platform_notifications_user_read_created",
        table_name="platform_notifications",
    )
    op.drop_table("platform_notifications")
    postgresql.ENUM(name="telegram_outbox_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="notification_kind").drop(op.get_bind(), checkfirst=True)
