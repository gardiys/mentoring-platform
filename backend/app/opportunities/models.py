from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
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


class PythonRepeatApplicationStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    NEEDS_DIAGNOSTIC = "needs_diagnostic"
    NEEDS_CLARIFICATION = "needs_clarification"
    APPROVED = "approved"
    REJECTED = "rejected"
    TERMS_ACCEPTED = "terms_accepted"
    PAYMENT_PENDING = "payment_pending"
    PAID = "paid"
    ENROLLED = "enrolled"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class PythonRepeatEmploymentStatus(StrEnum):
    EMPLOYED = "employed"
    UNEMPLOYED = "unemployed"
    ON_PROBATION = "on_probation"
    NOTICE_PERIOD = "notice_period"
    CAREER_BREAK = "career_break"
    OTHER = "other"


class PythonRepeatReason(StrEnum):
    LOST_JOB = "lost_job"
    FAILED_PROBATION = "failed_probation"
    WANTS_HIGHER_SALARY = "wants_higher_salary"
    WANTS_NEW_COMPANY = "wants_new_company"
    RETURNING_AFTER_BREAK = "returning_after_break"
    TECHNICAL_REFRESH = "technical_refresh"
    OTHER = "other"


class PythonRepeatSearchMode(StrEnum):
    ACTIVE_SEARCH = "active_search"
    SEARCH_WHILE_EMPLOYED = "search_while_employed"
    NOT_READY_TO_SEARCH = "not_ready_to_search"


class PythonRepeatEnrollmentStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PythonRepeatOfferStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    VERIFIED = "verified"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class PythonRepeatObligationStatus(StrEnum):
    ACTIVE = "active"
    PAID = "paid"
    CANCELLED = "cancelled"


class PythonRepeatInstallmentStatus(StrEnum):
    SCHEDULED = "scheduled"
    PENDING = "pending"
    PAID = "paid"
    REFUNDED = "refunded"
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
    terms_version: Mapped[int] = mapped_column(nullable=False, default=1)
    terms_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    terms_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    accepted_terms_snapshot: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)


class GoTransitionEnrollment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "go_transition_enrollments"
    __table_args__ = (
        UniqueConstraint("application_id", name="uq_go_transition_enrollment_application"),
        ForeignKeyConstraint(
            ["student_id", "previous_python_track_id"],
            ["learning_track_enrollments.user_id", "learning_track_enrollments.track_id"],
            name="fk_go_transition_previous_python_enrollment",
            ondelete="RESTRICT",
        ),
        CheckConstraint("source = 'python_to_go'", name="source_python_to_go"),
        Index("ix_go_transition_enrollment_student_created", "student_id", "created_at"),
        Index(
            "uq_go_transition_enrollment_active_student",
            "student_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    application_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("go_transition_applications.id", ondelete="RESTRICT"),
        nullable=False,
    )
    student_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    track_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("learning_tracks.id", ondelete="RESTRICT"), nullable=False
    )
    previous_python_track_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("learning_tracks.id", ondelete="RESTRICT"), nullable=False
    )
    mentor_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="python_to_go")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    terms_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class PythonRepeatProductOffer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "python_repeat_product_offers"
    __table_args__ = (
        UniqueConstraint("version", name="uq_python_repeat_offer_version"),
        CheckConstraint("upfront_price_kopecks > 0", name="upfront_price_positive"),
        CheckConstraint("success_fee_percent > 0", name="success_fee_percent_positive"),
        CheckConstraint("success_fee_installments_count > 0", name="installments_positive"),
        CheckConstraint("mentor_fixed_accrual_kopecks >= 0", name="fixed_accrual_non_negative"),
        CheckConstraint(
            "mentor_success_fee_share_percent >= 0 AND mentor_success_fee_share_percent <= 100",
            name="mentor_share_range",
        ),
        Index(
            "uq_python_repeat_offer_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    version: Mapped[int] = mapped_column(nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    upfront_price_kopecks: Mapped[int] = mapped_column(BigInteger, nullable=False)
    success_fee_percent: Mapped[int] = mapped_column(nullable=False)
    success_fee_installments_count: Mapped[int] = mapped_column(nullable=False)
    mentor_fixed_accrual_kopecks: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mentor_success_fee_share_percent: Mapped[int] = mapped_column(nullable=False)
    active_support_months: Mapped[int] = mapped_column(nullable=False)
    probation_support_days: Mapped[int] = mapped_column(nullable=False)
    included_mock_interviews: Mapped[int] = mapped_column(nullable=False)
    offer_valid_days: Mapped[int] = mapped_column(nullable=False)
    public_offer_revision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    public_offer_published_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    public_offer_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    public_offer_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    acceptance_statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PythonRepeatApplication(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "python_repeat_applications"
    __table_args__ = (
        Index("ix_python_repeat_applications_student_created", "student_id", "created_at"),
        Index("ix_python_repeat_applications_status_created", "status", "created_at"),
        Index(
            "uq_python_repeat_application_active_student",
            "student_id",
            unique=True,
            postgresql_where=text("status NOT IN ('rejected', 'cancelled', 'expired', 'enrolled')"),
        ),
    )

    student_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    employment_status: Mapped[PythonRepeatEmploymentStatus] = mapped_column(
        Enum(
            PythonRepeatEmploymentStatus,
            name="python_repeat_employment_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    reason: Mapped[PythonRepeatReason] = mapped_column(
        Enum(
            PythonRepeatReason,
            name="python_repeat_reason",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    current_position: Mapped[str | None] = mapped_column(String(240), nullable=True)
    current_company: Mapped[str | None] = mapped_column(String(240), nullable=True)
    current_stack: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_interview_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    target_position: Mapped[str] = mapped_column(String(240), nullable=False)
    target_salary_kopecks: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    technical_gaps: Mapped[str] = mapped_column(Text, nullable=False)
    hours_per_week: Mapped[int] = mapped_column(nullable=False)
    desired_start_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    search_mode: Mapped[PythonRepeatSearchMode] = mapped_column(
        Enum(
            PythonRepeatSearchMode,
            name="python_repeat_search_mode",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    additional_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[PythonRepeatApplicationStatus] = mapped_column(
        Enum(
            PythonRepeatApplicationStatus,
            name="python_repeat_application_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=PythonRepeatApplicationStatus.DRAFT,
    )
    responsible_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    eligibility_override_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    eligibility_override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_offer_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("python_repeat_product_offers.id", ondelete="RESTRICT"),
        nullable=True,
    )
    terms_version: Mapped[int | None] = mapped_column(nullable=True)
    terms_snapshot: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    offer_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    acceptance_ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    acceptance_user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    acceptance_evidence: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    contract_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acceptance_payment_link_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    acceptance_provider_operation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PythonRepeatApplicationHistory(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "python_repeat_application_history"
    __table_args__ = (
        Index("ix_python_repeat_history_application_created", "application_id", "created_at"),
    )

    application_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("python_repeat_applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    old_status: Mapped[PythonRepeatApplicationStatus | None] = mapped_column(
        Enum(
            PythonRepeatApplicationStatus,
            name="python_repeat_application_status",
            values_callable=lambda enum: [item.value for item in enum],
            create_type=False,
        ),
        nullable=True,
    )
    new_status: Mapped[PythonRepeatApplicationStatus] = mapped_column(
        Enum(
            PythonRepeatApplicationStatus,
            name="python_repeat_application_status",
            values_callable=lambda enum: [item.value for item in enum],
            create_type=False,
        ),
        nullable=False,
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    snapshot: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PythonRepeatEnrollment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "python_repeat_enrollments"
    __table_args__ = (
        UniqueConstraint("application_id", name="uq_python_repeat_enrollment_application"),
        ForeignKeyConstraint(
            ["student_id", "previous_track_id"],
            ["learning_track_enrollments.user_id", "learning_track_enrollments.track_id"],
            name="fk_python_repeat_previous_enrollment",
            ondelete="RESTRICT",
        ),
        Index("ix_python_repeat_enrollment_student_created", "student_id", "created_at"),
        Index(
            "uq_python_repeat_enrollment_active_student",
            "student_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    application_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("python_repeat_applications.id", ondelete="RESTRICT"),
        nullable=False,
    )
    student_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    track_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("learning_tracks.id", ondelete="RESTRICT"), nullable=False
    )
    previous_track_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("learning_tracks.id", ondelete="RESTRICT"), nullable=False
    )
    mentor_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    mentor_assigned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    mentor_assigned_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[PythonRepeatEnrollmentStatus] = mapped_column(
        Enum(
            PythonRepeatEnrollmentStatus,
            name="python_repeat_enrollment_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=PythonRepeatEnrollmentStatus.ACTIVE,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    personal_plan_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    terms_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class PythonRepeatEmploymentOffer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "python_repeat_employment_offers"
    __table_args__ = (
        Index("ix_python_repeat_offers_enrollment_created", "enrollment_id", "created_at"),
    )

    enrollment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("python_repeat_enrollments.id", ondelete="CASCADE"),
        nullable=False,
    )
    student_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    position: Mapped[str] = mapped_column(String(240), nullable=False)
    company: Mapped[str] = mapped_column(String(240), nullable=False)
    technology_direction: Mapped[str] = mapped_column(
        String(80), nullable=False, default="Python Backend"
    )
    fixed_monthly_salary_kopecks: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="RUB")
    employment_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expected_start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[PythonRepeatOfferStatus] = mapped_column(
        Enum(
            PythonRepeatOfferStatus,
            name="python_repeat_offer_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=PythonRepeatOfferStatus.DRAFT,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    verification_comment: Mapped[str | None] = mapped_column(Text, nullable=True)


class PythonRepeatSuccessFeeObligation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "python_repeat_success_fee_obligations"
    __table_args__ = (
        UniqueConstraint("verified_offer_id", name="uq_python_repeat_obligation_offer"),
        CheckConstraint("total_amount_kopecks > 0", name="total_positive"),
    )

    enrollment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("python_repeat_enrollments.id", ondelete="CASCADE"),
        nullable=False,
    )
    verified_offer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("python_repeat_employment_offers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    salary_base_kopecks: Mapped[int] = mapped_column(BigInteger, nullable=False)
    success_fee_percent: Mapped[int] = mapped_column(nullable=False)
    total_amount_kopecks: Mapped[int] = mapped_column(BigInteger, nullable=False)
    installments_count: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[PythonRepeatObligationStatus] = mapped_column(
        Enum(
            PythonRepeatObligationStatus,
            name="python_repeat_obligation_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=PythonRepeatObligationStatus.ACTIVE,
    )
    terms_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class PythonRepeatInstallment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "python_repeat_installments"
    __table_args__ = (
        UniqueConstraint(
            "obligation_id", "sequence_number", name="uq_python_repeat_installment_sequence"
        ),
        CheckConstraint("amount_kopecks > 0", name="amount_positive"),
        Index("ix_python_repeat_installments_due_status", "due_at", "status"),
    )

    obligation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("python_repeat_success_fee_obligations.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence_number: Mapped[int] = mapped_column(nullable=False)
    amount_kopecks: Mapped[int] = mapped_column(BigInteger, nullable=False)
    salary_percent: Mapped[int] = mapped_column(nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[PythonRepeatInstallmentStatus] = mapped_column(
        Enum(
            PythonRepeatInstallmentStatus,
            name="python_repeat_installment_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=PythonRepeatInstallmentStatus.SCHEDULED,
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_received_kopecks: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PythonRepeatEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "python_repeat_events"

    event_key: Mapped[str] = mapped_column(String(240), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OpportunityPaymentAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "opportunity_payment_attempts"
    __table_args__ = (
        CheckConstraint(
            "(consultation_request_id IS NOT NULL)::int + "
            "(transition_application_id IS NOT NULL)::int + "
            "(python_repeat_application_id IS NOT NULL)::int + "
            "(python_repeat_installment_id IS NOT NULL)::int = 1",
            name="one_payable_resource",
        ),
        Index("ix_opportunity_payment_attempts_consultation", "consultation_request_id"),
        Index("ix_opportunity_payment_attempts_transition", "transition_application_id"),
        Index("ix_opportunity_payment_attempts_python_repeat", "python_repeat_application_id"),
        Index("ix_opportunity_payment_attempts_python_installment", "python_repeat_installment_id"),
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
    python_repeat_application_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("python_repeat_applications.id", ondelete="CASCADE"),
        nullable=True,
    )
    python_repeat_installment_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("python_repeat_installments.id", ondelete="CASCADE"),
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
    terms_snapshot: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    raw_create_response: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
