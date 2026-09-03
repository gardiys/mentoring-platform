from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CareerPackageStatus(StrEnum):
    NOT_STARTED = "not_started"
    COLLECTING_DATA = "collecting_data"
    GENERATING = "generating"
    DRAFT = "draft"
    REVIEW_REQUIRED = "review_required"
    READY_TO_PUBLISH = "ready_to_publish"
    DELIVERY_PENDING = "delivery_pending"
    PROVIDED = "provided"
    REVISION_REQUESTED = "revision_requested"
    CANCELLED = "cancelled"


class CareerGenerationStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CareerGenerationComponent(StrEnum):
    ALL = "all"
    SELF_PRESENTATION = "self_presentation"
    ACTIVE_SEARCH = "active_search"


class CareerDeliveryChannel(StrEnum):
    PLATFORM = "platform"
    TELEGRAM = "telegram"
    EMAIL = "email"


class CareerDeliveryStatus(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class CareerDeliveryPurpose(StrEnum):
    PACKAGE_PROVIDED = "package_provided"
    PAYMENT_OBLIGATION = "payment_obligation"


class CareerObligationStatus(StrEnum):
    AWAITING_NOTICE = "awaiting_notice"
    ACTIVE = "active"
    HOLD = "hold"
    PAID = "paid"
    CANCELLED = "cancelled"


class CareerObjectionComponent(StrEnum):
    RESUME = "resume"
    SELF_PRESENTATION = "self_presentation_card"
    ACTIVE_SEARCH = "active_search_parameters"
    COMPLETENESS = "completeness"
    OTHER = "other"


class CareerObjectionStatus(StrEnum):
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    ACCEPTED = "accepted"
    PARTIALLY_ACCEPTED = "partially_accepted"
    REJECTED = "rejected"
    RESOLVED = "resolved"


class CareerResumeVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "career_resume_versions"
    __table_args__ = (
        UniqueConstraint("student_id", "version_number", name="uq_career_resume_student_version"),
        UniqueConstraint("student_id", "content_sha256", name="uq_career_resume_student_hash"),
        CheckConstraint(
            "text_content IS NOT NULL OR storage_key IS NOT NULL",
            name="has_content",
        ),
        Index("ix_career_resume_versions_student_finalized", "student_id", "finalized_at"),
    )

    student_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    source_document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("mentor_student_documents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    finalized_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    finalized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CareerPackage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "career_packages"
    __table_args__ = (
        UniqueConstraint("student_id", "track_id", name="uq_career_packages_student_track"),
        CheckConstraint("lock_version >= 1", name="lock_version_positive"),
        Index("ix_career_packages_status_updated", "status", "updated_at"),
    )

    student_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    track_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("learning_tracks.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[CareerPackageStatus] = mapped_column(
        Enum(
            CareerPackageStatus,
            name="career_package_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=CareerPackageStatus.NOT_STARTED,
    )
    source_resume_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("career_resume_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    latest_published_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("career_package_versions.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CareerPackageDraft(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "career_package_drafts"
    __table_args__ = (UniqueConstraint("package_id", name="uq_career_package_drafts_package"),)

    package_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("career_packages.id", ondelete="CASCADE"), nullable=False
    )
    source_resume_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("career_resume_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    source_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    self_presentation_card: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    active_search_parameters: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    missing_data: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    generation_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("career_package_generation_runs.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )
    last_edited_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_stale: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )


class CareerPackageGenerationRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "career_package_generation_runs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_career_generation_idempotency"),
        Index("ix_career_generation_package_created", "package_id", "created_at"),
    )

    package_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("career_packages.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[CareerGenerationStatus] = mapped_column(
        Enum(
            CareerGenerationStatus,
            name="career_generation_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=CareerGenerationStatus.QUEUED,
    )
    component: Mapped[CareerGenerationComponent] = mapped_column(
        Enum(
            CareerGenerationComponent,
            name="career_generation_component",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    requested_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    safe_error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class CareerPackageVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "career_package_versions"
    __table_args__ = (
        UniqueConstraint("package_id", "version_number", name="uq_career_versions_number"),
        UniqueConstraint("snapshot_sha256", name="uq_career_versions_snapshot_sha256"),
        Index("ix_career_versions_package_published", "package_id", "published_at"),
    )

    package_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("career_packages.id", ondelete="RESTRICT"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_resume_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("career_resume_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    rendered_html: Mapped[str] = mapped_column(Text, nullable=False)
    pdf_object_key: Mapped[str] = mapped_column(String(500), nullable=False)
    pdf_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    pdf_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    generated_by_ai: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    generation_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("career_package_generation_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    objection_deadline_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    payment_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    supersedes_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("career_package_versions.id", ondelete="SET NULL"),
        nullable=True,
    )


class CareerPackageDelivery(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "career_package_deliveries"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_career_deliveries_idempotency"),
        Index("ix_career_deliveries_version_channel", "package_version_id", "channel"),
    )

    package_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("career_package_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel: Mapped[CareerDeliveryChannel] = mapped_column(
        Enum(
            CareerDeliveryChannel,
            name="career_delivery_channel",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    status: Mapped[CareerDeliveryStatus] = mapped_column(
        Enum(
            CareerDeliveryStatus,
            name="career_delivery_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    purpose: Mapped[CareerDeliveryPurpose] = mapped_column(
        Enum(
            CareerDeliveryPurpose,
            name="career_delivery_purpose",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=CareerDeliveryPurpose.PACKAGE_PROVIDED,
    )
    recipient: Mapped[str] = mapped_column(String(320), nullable=False)
    external_message_id: Mapped[str | None] = mapped_column(String(240), nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    safe_error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)


class CareerPackageObligation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "career_package_obligations"
    __table_args__ = (
        UniqueConstraint("package_id", name="uq_career_obligations_package"),
        UniqueConstraint("idempotency_key", name="uq_career_obligations_idempotency"),
        CheckConstraint("amount_kopecks = 3000000", name="amount_fixed"),
        Index("ix_career_obligations_due_status", "due_at", "status"),
    )

    package_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("career_packages.id", ondelete="RESTRICT"), nullable=False
    )
    source_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("career_package_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    student_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    amount_kopecks: Mapped[int] = mapped_column(BigInteger, nullable=False, default=3_000_000)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="RUB")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[CareerObligationStatus] = mapped_column(
        Enum(
            CareerObligationStatus,
            name="career_obligation_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=CareerObligationStatus.AWAITING_NOTICE,
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)
    disputed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    offer_accepted_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    accrued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recorded_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    record_comment: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    notice_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CareerPackageObjection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "career_package_objections"
    __table_args__ = (
        Index("ix_career_objections_version_status", "package_version_id", "status"),
        Index("ix_career_objections_student_created", "student_id", "created_at"),
    )

    package_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("career_package_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    student_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    component: Mapped[CareerObjectionComponent] = mapped_column(
        Enum(
            CareerObjectionComponent,
            name="career_objection_component",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    expected_result: Mapped[str] = mapped_column(Text, nullable=False)
    attachments: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_late: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[CareerObjectionStatus] = mapped_column(
        Enum(
            CareerObjectionStatus,
            name="career_objection_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=CareerObjectionStatus.SUBMITTED,
    )
    resolution_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CareerSelfPresentationReview(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "career_self_presentation_reviews"
    __table_args__ = (Index("ix_career_reviews_package_held", "package_id", "held_at"),)

    package_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("career_packages.id", ondelete="CASCADE"), nullable=False
    )
    reviewer_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    held_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    strengths: Mapped[str] = mapped_column(Text, nullable=False)
    improvements: Mapped[str] = mapped_column(Text, nullable=False)
    preparation_for_next_attempt: Mapped[str] = mapped_column(Text, nullable=False)
    additional_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_to_student_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CareerPackageEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "career_package_events"
    __table_args__ = (Index("ix_career_events_package_created", "package_id", "created_at"),)

    package_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("career_packages.id", ondelete="CASCADE"), nullable=False
    )
    version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("career_package_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
