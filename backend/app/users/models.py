from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
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
    Integer,
    Numeric,
    String,
    true,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserRole(StrEnum):
    STUDENT = "student"
    MENTOR = "mentor"
    ADMIN = "admin"


MENTOR_CAPABLE_ROLES = (UserRole.MENTOR, UserRole.ADMIN)


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "repayment_percent > 0 AND repayment_percent <= 1000",
            name="repayment_percent_range",
        ),
        CheckConstraint(
            "entry_payment_kopecks >= 0",
            name="entry_payment_non_negative",
        ),
        CheckConstraint(
            "session_version >= 1",
            name="session_version_positive",
        ),
    )
    email: Mapped[str | None] = mapped_column(String(320), unique=True, index=True, nullable=True)
    telegram_id: Mapped[int | None] = mapped_column(
        BigInteger, unique=True, index=True, nullable=True
    )
    telegram_username: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    learning_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    repayment_percent: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), default=Decimal("200.00"), nullable=False
    )
    entry_payment_kopecks: Mapped[int] = mapped_column(
        BigInteger, default=4_500_000, nullable=False
    )
    entry_payment_paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    program_excluded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    program_exclusion_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False
    )
    session_version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default="1",
        nullable=False,
    )
    public_identity_hidden_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    public_identity_hidden_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    public_identity_hidden_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    personal_data_erased_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    personal_data_erased_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    personal_data_erasure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    enrollments = relationship("RoadmapEnrollment", back_populates="user")
    topic_progress = relationship("TopicProgress", back_populates="user")
