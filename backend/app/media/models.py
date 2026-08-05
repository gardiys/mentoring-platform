from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ContentMediaProcessingStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class ProtectedContentMedia(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "protected_content_media"
    __table_args__ = (
        CheckConstraint(
            "(knowledge_entry_id IS NOT NULL) <> (roadmap_topic_id IS NOT NULL)",
            name="exactly_one_parent",
        ),
        CheckConstraint("size > 0", name="size_positive"),
        CheckConstraint("position >= 0", name="position_non_negative"),
        CheckConstraint(
            "normalization_attempts >= 0",
            name="normalization_attempts_non_negative",
        ),
        CheckConstraint(
            "normalization_revision >= 0",
            name="normalization_revision_non_negative",
        ),
        CheckConstraint(
            "normalization_completed_at IS NULL "
            "OR normalization_started_at IS NULL "
            "OR normalization_completed_at >= normalization_started_at",
            name="normalization_timestamps_ordered",
        ),
        CheckConstraint(
            "processing_status <> 'processing' OR normalization_started_at IS NOT NULL",
            name="processing_requires_started_at",
        ),
        CheckConstraint(
            "NOT allow_original_playback_during_normalization "
            "OR processing_status = 'ready' "
            "OR normalization_source_key = storage_key",
            name="original_playback_source_consistent",
        ),
        Index(
            "ix_protected_content_media_knowledge_position",
            "knowledge_entry_id",
            "position",
        ),
        Index(
            "ix_protected_content_media_roadmap_position",
            "roadmap_topic_id",
            "position",
        ),
        Index(
            "ix_protected_content_media_processing_status_updated_at",
            "processing_status",
            "updated_at",
        ),
        Index(
            "ux_protected_content_media_normalization_source_key",
            "normalization_source_key",
            unique=True,
        ),
    )

    knowledge_entry_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge_entries.id", ondelete="CASCADE"),
        nullable=True,
    )
    roadmap_topic_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("topics.id", ondelete="CASCADE"),
        nullable=True,
    )
    uploaded_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    storage_key: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(160), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str | None] = mapped_column(String(240), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processing_status: Mapped[ContentMediaProcessingStatus] = mapped_column(
        Enum(
            ContentMediaProcessingStatus,
            name="content_media_processing_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=ContentMediaProcessingStatus.READY,
        server_default=ContentMediaProcessingStatus.READY.value,
        nullable=False,
    )
    normalization_attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    normalization_revision: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    normalization_source_key: Mapped[str | None] = mapped_column(
        String(180),
        nullable=True,
    )
    normalization_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    normalization_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    normalization_error_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    normalization_error_message: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    allow_original_playback_during_normalization: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )

    @property
    def playback_available(self) -> bool:
        if self.processing_status is ContentMediaProcessingStatus.READY:
            return True
        return (
            self.allow_original_playback_during_normalization
            and self.normalization_source_key is not None
            and self.storage_key == self.normalization_source_key
        )

    knowledge_entry = relationship("KnowledgeEntry", back_populates="media")
    roadmap_topic = relationship("Topic", back_populates="media")
    uploaded_by = relationship("User")
