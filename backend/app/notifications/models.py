from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class NotificationKind(StrEnum):
    INTERVIEW_PUBLISHED = "interview_published"
    MOCK_INTERVIEW = "mock_interview"
    MOCK_FEEDBACK = "mock_feedback"
    MENTOR_DOCUMENT = "mentor_document"
    OFFER = "offer"
    STATUS_CHANGED = "status_changed"
    MENTOR_FEEDBACK = "mentor_feedback"
    PAYMENT_DUE = "payment_due"


class TelegramOutboxStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    SENT = "sent"
    FAILED = "failed"


class PlatformNotification(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "platform_notifications"
    __table_args__ = (
        Index(
            "ix_platform_notifications_user_read_created",
            "user_id",
            "read_at",
            "created_at",
        ),
        Index(
            "ix_platform_notifications_user_created_id",
            "user_id",
            "created_at",
            "id",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[NotificationKind] = mapped_column(
        Enum(
            NotificationKind,
            name="notification_kind",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    action_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    event_key: Mapped[str] = mapped_column(String(240), nullable=False, unique=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TelegramOutbox(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "telegram_outbox"
    __table_args__ = (
        Index("ix_telegram_outbox_status_available", "status", "available_at", "created_at"),
    )

    event_key: Mapped[str] = mapped_column(String(240), nullable=False, unique=True)
    chat_id: Mapped[str] = mapped_column(String(100), nullable=False)
    message_thread_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    action_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    action_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[TelegramOutboxStatus] = mapped_column(
        Enum(
            TelegramOutboxStatus,
            name="telegram_outbox_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=TelegramOutboxStatus.QUEUED,
        server_default=TelegramOutboxStatus.QUEUED.value,
        nullable=False,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
