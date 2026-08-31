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
    String,
    Text,
    false,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.payments.models import PaymentAttemptStatus


class ConsultationType(StrEnum):
    FREE_TOPIC = "free_topic"
    TECHNICAL_MOCK = "technical_mock"
    LEGEND_MOCK = "legend_mock"
    RESUME_LEGEND = "resume_legend"
    SYSTEM_DESIGN_MOCK = "system_design_mock"
    WORK_TASK = "work_task"


class ConsultationStatus(StrEnum):
    REQUESTED = "requested"
    PAYMENT_PENDING = "payment_pending"
    PAID = "paid"
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class GoTransitionStatus(StrEnum):
    SUBMITTED = "submitted"
    APPROVED = "approved"
    PAYMENT_PENDING = "payment_pending"
    PAID = "paid"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class ProgramCompletion(Base):
    __tablename__ = "program_completions"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    track_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("learning_tracks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class ConsultationMentorSetting(TimestampMixin, Base):
    __tablename__ = "consultation_mentor_settings"

    mentor_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
        nullable=False,
    )
    updated_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class ConsultationTypeSetting(TimestampMixin, Base):
    __tablename__ = "consultation_type_settings"
    __table_args__ = (
        CheckConstraint("alumni_price_kopecks > 0", name="alumni_price_positive"),
        CheckConstraint("standard_price_kopecks > 0", name="standard_price_positive"),
        CheckConstraint(
            "standard_price_kopecks >= alumni_price_kopecks",
            name="standard_price_not_lower_than_alumni",
        ),
        CheckConstraint("mentor_reward_kopecks >= 0", name="mentor_reward_non_negative"),
        CheckConstraint(
            "mentor_reward_kopecks <= alumni_price_kopecks",
            name="mentor_reward_not_higher_than_price",
        ),
        CheckConstraint(
            "duration_minutes >= 15 AND duration_minutes <= 480",
            name="duration_minutes_range",
        ),
    )

    consultation_type: Mapped[ConsultationType] = mapped_column(
        Enum(
            ConsultationType,
            name="consultation_type",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        primary_key=True,
    )
    alumni_price_kopecks: Mapped[int] = mapped_column(BigInteger, nullable=False)
    standard_price_kopecks: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mentor_reward_kopecks: Mapped[int] = mapped_column(BigInteger, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(nullable=False, default=60)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class GoTransitionProgramSetting(TimestampMixin, Base):
    __tablename__ = "go_transition_program_settings"
    __table_args__ = (CheckConstraint("id = 1", name="singleton_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    description_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class ConsultationRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "consultation_requests"
    __table_args__ = (
        CheckConstraint("price_kopecks > 0", name="price_positive"),
        CheckConstraint("mentor_reward_kopecks >= 0", name="mentor_reward_non_negative"),
        Index("ix_consultation_requests_student_created", "student_id", "created_at"),
        Index("ix_consultation_requests_status_created", "status", "created_at"),
    )

    student_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    mentor_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    brief: Mapped[str] = mapped_column(Text, nullable=False)
    consultation_type: Mapped[ConsultationType] = mapped_column(
        Enum(
            ConsultationType,
            name="consultation_type",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=ConsultationType.FREE_TOPIC,
    )
    price_kopecks: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mentor_reward_kopecks: Mapped[int] = mapped_column(BigInteger, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(nullable=False, default=60)
    status: Mapped[ConsultationStatus] = mapped_column(
        Enum(
            ConsultationStatus,
            name="consultation_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=ConsultationStatus.REQUESTED,
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    written_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class GoTransitionApplication(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "go_transition_applications"
    __table_args__ = (
        CheckConstraint("upfront_price_kopecks > 0", name="upfront_price_positive"),
        CheckConstraint(
            "success_fee_percent > 0 AND success_fee_percent <= 1000",
            name="success_fee_percent_range",
        ),
        Index("ix_go_transition_applications_student_created", "student_id", "created_at"),
        Index("ix_go_transition_applications_status_created", "status", "created_at"),
    )

    student_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    motivation: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[GoTransitionStatus] = mapped_column(
        Enum(
            GoTransitionStatus,
            name="go_transition_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=GoTransitionStatus.SUBMITTED,
    )
    upfront_price_kopecks: Mapped[int] = mapped_column(BigInteger, nullable=False)
    success_fee_percent: Mapped[int] = mapped_column(nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    terms_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class OpportunityPaymentAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "opportunity_payment_attempts"
    __table_args__ = (
        CheckConstraint(
            "(consultation_request_id IS NOT NULL)::int + "
            "(transition_application_id IS NOT NULL)::int = 1",
            name="one_payable_resource",
        ),
        Index("ix_opportunity_payment_attempts_consultation", "consultation_request_id"),
        Index("ix_opportunity_payment_attempts_transition", "transition_application_id"),
    )

    consultation_request_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("consultation_requests.id", ondelete="CASCADE"),
        nullable=True,
    )
    transition_application_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("go_transition_applications.id", ondelete="CASCADE"),
        nullable=True,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="tochka")
    payment_link_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    provider_operation_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )
    status: Mapped[PaymentAttemptStatus] = mapped_column(
        Enum(
            PaymentAttemptStatus,
            name="payment_attempt_status",
            values_callable=lambda enum: [item.value for item in enum],
            create_type=False,
        ),
        nullable=False,
        default=PaymentAttemptStatus.PENDING,
    )
    payment_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_create_response: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
