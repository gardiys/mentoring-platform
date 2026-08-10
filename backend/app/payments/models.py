from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PaymentInstallmentStatus(StrEnum):
    SCHEDULED = "scheduled"
    PENDING = "pending"
    PAID = "paid"
    CANCELLED = "cancelled"


class PaymentAttemptStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    FAILED = "failed"
    CANCELLED = "cancelled"
    MANUAL_REVIEW = "manual_review"
    REVOKED = "revoked"


class StudentEmploymentStatus(StrEnum):
    ACTIVE = "active"
    TERMINATED = "terminated"


class MentorRewardKind(StrEnum):
    EMPLOYMENT_PAYMENT = "employment_payment"
    ENTRY_PAYMENT = "entry_payment"
    PROGRAM_EXCLUSION = "program_exclusion"
    LEGACY_FIXED = "legacy_fixed"


class MentorPayoutStatus(StrEnum):
    REQUESTED = "requested"
    PAID = "paid"
    CANCELLED = "cancelled"


class MentorPayoutOrigin(StrEnum):
    MENTOR_REQUEST = "mentor_request"
    ADMIN_DIRECT = "admin_direct"


class StudentEmployment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "student_employments"
    __table_args__ = (
        CheckConstraint("net_salary_kopecks > 0", name="net_salary_positive"),
        CheckConstraint(
            "repayment_percent > 0 AND repayment_percent <= 1000",
            name="repayment_percent_range",
        ),
        CheckConstraint(
            "payment_day_first >= 1 AND payment_day_first <= 28",
            name="payment_day_first_range",
        ),
        CheckConstraint(
            "payment_day_second >= 1 AND payment_day_second <= 28",
            name="payment_day_second_range",
        ),
        CheckConstraint(
            "payment_day_first < payment_day_second",
            name="payment_days_ordered",
        ),
        Index("ix_student_employments_start_date", "start_date"),
        Index(
            "uq_student_employments_active_student",
            "student_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    student_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )
    company_name: Mapped[str] = mapped_column(String(240), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    net_salary_kopecks: Mapped[int] = mapped_column(BigInteger, nullable=False)
    repayment_percent: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    status: Mapped[StudentEmploymentStatus] = mapped_column(
        Enum(
            StudentEmploymentStatus,
            name="student_employment_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=StudentEmploymentStatus.ACTIVE,
        nullable=False,
    )
    ended_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payment_day_first: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=10)
    payment_day_second: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=25)
    recorded_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class PaymentInstallment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payment_installments"
    __table_args__ = (
        UniqueConstraint(
            "employment_id", "sequence_number", name="uq_payment_installments_sequence"
        ),
        CheckConstraint("sequence_number > 0", name="sequence_positive"),
        CheckConstraint("amount_kopecks > 0", name="amount_positive"),
        Index("ix_payment_installments_due_status", "due_date", "status"),
    )

    employment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("student_employments.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount_kopecks: Mapped[int] = mapped_column(BigInteger, nullable=False)
    salary_percent: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    status: Mapped[PaymentInstallmentStatus] = mapped_column(
        Enum(
            PaymentInstallmentStatus,
            name="payment_installment_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=PaymentInstallmentStatus.SCHEDULED,
        nullable=False,
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    revocation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class PaymentAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payment_attempts"
    __table_args__ = (
        UniqueConstraint("payment_link_id", name="uq_payment_attempts_link_id"),
        UniqueConstraint("provider_operation_id", name="uq_payment_attempts_provider_operation_id"),
        Index("ix_payment_attempts_installment_created", "installment_id", "created_at"),
        Index("ix_payment_attempts_operation", "provider_operation_id"),
    )

    installment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("payment_installments.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="tochka")
    payment_link_id: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_operation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[PaymentAttemptStatus] = mapped_column(
        Enum(
            PaymentAttemptStatus,
            name="payment_attempt_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=PaymentAttemptStatus.PENDING,
        nullable=False,
    )
    payment_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_create_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PaymentWebhookEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "payment_webhook_events"
    __table_args__ = (
        UniqueConstraint("deduplication_key", name="uq_payment_webhook_events_dedupe"),
        Index("ix_payment_webhook_events_attempt", "attempt_id"),
    )

    attempt_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payment_attempts.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    deduplication_key: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class MentorReward(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mentor_rewards"
    __table_args__ = (
        UniqueConstraint("installment_id", name="uq_mentor_rewards_installment"),
        CheckConstraint("amount_kopecks >= 0", name="amount_non_negative"),
        CheckConstraint(
            "paid_kopecks >= 0 AND paid_kopecks <= amount_kopecks",
            name="paid_amount_range",
        ),
        CheckConstraint(
            "basis_kopecks IS NULL OR basis_kopecks >= 0",
            name="basis_non_negative",
        ),
        CheckConstraint(
            "reward_percent IS NULL OR (reward_percent >= 0 AND reward_percent <= 100)",
            name="reward_percent_range",
        ),
        Index("ix_mentor_rewards_mentor_created", "mentor_id", "created_at"),
        Index(
            "uq_mentor_rewards_one_time_student_kind",
            "student_id",
            "kind",
            unique=True,
            postgresql_where=text("kind IN ('entry_payment', 'program_exclusion')"),
        ),
    )

    installment_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("payment_installments.id", ondelete="CASCADE"),
        nullable=True,
    )
    student_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    mentor_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[MentorRewardKind] = mapped_column(
        Enum(
            MentorRewardKind,
            name="mentor_reward_kind",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    reward_percent: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    basis_kopecks: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    amount_kopecks: Mapped[int] = mapped_column(BigInteger, nullable=False)
    paid_kopecks: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MentorPayout(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mentor_payouts"
    __table_args__ = (
        CheckConstraint("amount_kopecks > 0", name="amount_positive"),
        Index("ix_mentor_payouts_mentor_created", "mentor_id", "created_at"),
        Index("ix_mentor_payouts_status_created", "status", "created_at"),
        Index(
            "uq_mentor_payouts_open_mentor",
            "mentor_id",
            unique=True,
            postgresql_where=text("status = 'requested'"),
        ),
    )

    mentor_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    amount_kopecks: Mapped[int] = mapped_column(BigInteger, nullable=False)
    origin: Mapped[MentorPayoutOrigin] = mapped_column(
        Enum(
            MentorPayoutOrigin,
            name="mentor_payout_origin",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    status: Mapped[MentorPayoutStatus] = mapped_column(
        Enum(
            MentorPayoutStatus,
            name="mentor_payout_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    payment_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    paid_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    receipt_storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    receipt_filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    receipt_content_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    receipt_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    receipt_uploaded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class MentorPayoutAllocation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mentor_payout_allocations"
    __table_args__ = (
        UniqueConstraint("payout_id", "reward_id", name="uq_mentor_payout_allocations_pair"),
        CheckConstraint("amount_kopecks > 0", name="amount_positive"),
        Index("ix_mentor_payout_allocations_reward", "reward_id"),
    )

    payout_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("mentor_payouts.id", ondelete="CASCADE"), nullable=False
    )
    reward_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("mentor_rewards.id", ondelete="RESTRICT"), nullable=False
    )
    amount_kopecks: Mapped[int] = mapped_column(BigInteger, nullable=False)
