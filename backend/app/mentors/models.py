from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class StudentLearningStatus(StrEnum):
    LEARNING = "learning"
    INTERVIEWING = "interviewing"
    PROBATION = "probation"
    FINISHED = "finished"


class StudentStrengthLevel(StrEnum):
    WEAK = "weak"
    MEDIUM = "medium"
    STRONG = "strong"


class MentorDocumentKind(StrEnum):
    RESUME = "resume"
    LEGEND = "legend"


class MockInterviewStatus(StrEnum):
    PLANNED = "planned"
    COMPLETED = "completed"


class MentorStudent(Base):
    __tablename__ = "mentor_students"
    __table_args__ = (
        CheckConstraint("mentor_id <> student_id", name="different_users"),
        CheckConstraint(
            "reward_percent IS NULL OR (reward_percent >= 0 AND reward_percent <= 100)",
            name="mentor_reward_percent_range",
        ),
        UniqueConstraint("student_id", name="uq_mentor_students_one_mentor_per_student"),
        Index("ix_mentor_students_mentor", "mentor_id", "student_id"),
    )

    mentor_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    student_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    learning_status: Mapped[StudentLearningStatus] = mapped_column(
        Enum(
            StudentLearningStatus,
            name="student_learning_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=StudentLearningStatus.LEARNING,
        nullable=False,
    )
    strength_level: Mapped[StudentStrengthLevel | None] = mapped_column(
        Enum(
            StudentStrengthLevel,
            name="student_strength_level",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    reward_percent: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)


class MentorTrackAssignment(Base):
    __tablename__ = "mentor_track_assignments"

    mentor_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    track_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("learning_tracks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MentorStudentNote(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mentor_student_notes"
    __table_args__ = (Index("ix_mentor_student_notes_student_created", "student_id", "created_at"),)

    mentor_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)


class MentorStudentDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mentor_student_documents"
    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "kind",
            name="uq_mentor_student_documents_one_document_per_kind",
        ),
        CheckConstraint(
            "text_content IS NOT NULL OR storage_key IS NOT NULL",
            name="document_has_content",
        ),
    )

    mentor_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[MentorDocumentKind] = mapped_column(
        Enum(
            MentorDocumentKind,
            name="mentor_document_kind",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(180), nullable=True)
    filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class MockInterview(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mock_interviews"
    __table_args__ = (
        Index("ix_mock_interviews_student_scheduled", "student_id", "scheduled_at"),
        Index("ix_mock_interviews_mentor_scheduled", "mentor_id", "scheduled_at"),
    )

    mentor_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[MockInterviewStatus] = mapped_column(
        Enum(
            MockInterviewStatus,
            name="mock_interview_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=MockInterviewStatus.PLANNED,
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    conducted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    media_storage_key: Mapped[str | None] = mapped_column(String(180), nullable=True)
    media_filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    media_content_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    media_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
