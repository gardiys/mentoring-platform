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
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class InterviewCardFrequency(StrEnum):
    FREQUENT = "frequent"
    OCCASIONAL = "occasional"


class InterviewReviewRating(StrEnum):
    AGAIN = "again"
    HARD = "hard"
    GOOD = "good"
    EASY = "easy"


class InterviewProcessStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"
    OFFER = "offer"


class InterviewStageType(StrEnum):
    SCREENING = "screening"
    TECHNICAL_SCREENING = "technical_screening"
    TECHNICAL_INTERVIEW = "technical_interview"
    SYSTEM_DESIGN = "system_design"
    FINAL_INTERVIEW = "final_interview"
    OTHER = "other"


class InterviewDeck(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "interview_decks"
    __table_args__ = (
        CheckConstraint("position >= 0", name="position_non_negative"),
        Index("ix_interview_decks_track_position", "track_id", "position"),
    )

    track_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("learning_tracks.id", ondelete="CASCADE"),
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    cards = relationship(
        "InterviewCard",
        back_populates="deck",
        cascade="all, delete-orphan",
        order_by="InterviewCard.position",
    )


class InterviewCard(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "interview_cards"
    __table_args__ = (
        CheckConstraint("position >= 0", name="position_non_negative"),
        Index("ix_interview_cards_deck_position", "deck_id", "position"),
    )

    deck_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("interview_decks.id", ondelete="CASCADE"),
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(240), nullable=False)
    companies: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_occurrence: Mapped[str | None] = mapped_column(String(40), nullable=True)
    question_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    answer_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    frequency: Mapped[InterviewCardFrequency] = mapped_column(
        Enum(
            InterviewCardFrequency,
            name="interview_card_frequency",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    deck = relationship("InterviewDeck", back_populates="cards")


class InterviewCardProgress(Base):
    __tablename__ = "interview_card_progress"
    __table_args__ = (
        CheckConstraint("repetitions >= 0", name="repetitions_non_negative"),
        CheckConstraint("interval_days >= 0", name="interval_days_non_negative"),
        CheckConstraint("ease_factor >= 1.3", name="ease_factor_minimum"),
        CheckConstraint("lapses >= 0", name="lapses_non_negative"),
        Index("ix_interview_card_progress_user_due", "user_id", "due_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    card_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("interview_cards.id", ondelete="CASCADE"),
        primary_key=True,
    )
    repetitions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ease_factor: Mapped[float] = mapped_column(Float, default=2.5, nullable=False)
    lapses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    first_learned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_rating: Mapped[InterviewReviewRating | None] = mapped_column(
        Enum(
            InterviewReviewRating,
            name="interview_review_rating",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=True,
    )


class InterviewTopicSelection(Base):
    __tablename__ = "interview_topic_selections"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    deck_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("interview_decks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    category: Mapped[str] = mapped_column(String(240), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Company(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(240), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(240), unique=True, nullable=False)
    transliterated_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)

    aliases = relationship(
        "CompanyAlias",
        back_populates="company",
        cascade="all, delete-orphan",
    )


class CompanyAlias(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "company_aliases"

    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(240), unique=True, nullable=False)
    transliterated_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)

    company = relationship("Company", back_populates="aliases")


class InterviewProcess(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "interview_processes"
    __table_args__ = (Index("ix_interview_processes_user_status", "user_id", "status"),)

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    track_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("learning_tracks.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    company_name: Mapped[str] = mapped_column(String(240), nullable=False)
    recruiter_telegram_usernames: Mapped[list[str]] = mapped_column(
        ARRAY(String(32)), default=list, server_default="{}", nullable=False
    )
    status: Mapped[InterviewProcessStatus] = mapped_column(
        Enum(
            InterviewProcessStatus,
            name="interview_process_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=InterviewProcessStatus.ACTIVE,
        nullable=False,
    )
    close_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    offer_storage_key: Mapped[str | None] = mapped_column(String(180), nullable=True)
    offer_filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    offer_content_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    offer_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    stages = relationship(
        "InterviewProcessStage",
        back_populates="process",
        cascade="all, delete-orphan",
        order_by="InterviewProcessStage.scheduled_at",
    )


class InterviewProcessStage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "interview_process_stages"
    __table_args__ = (
        Index("ix_interview_process_stages_process_date", "process_id", "scheduled_at"),
    )

    process_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("interview_processes.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage_type: Mapped[InterviewStageType] = mapped_column(
        Enum(
            InterviewStageType,
            name="interview_stage_type",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_storage_key: Mapped[str | None] = mapped_column(String(180), nullable=True)
    media_filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    media_content_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    media_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ai_analysis_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    process = relationship("InterviewProcess", back_populates="stages")
    attachments = relationship(
        "InterviewProcessStageAttachment",
        back_populates="stage",
        cascade="all, delete-orphan",
        order_by="InterviewProcessStageAttachment.created_at",
    )


class InterviewProcessStageAttachment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "interview_process_stage_attachments"
    __table_args__ = (Index("ix_interview_stage_attachments_stage", "stage_id", "created_at"),)

    stage_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("interview_process_stages.id", ondelete="CASCADE"),
        nullable=False,
    )
    storage_key: Mapped[str] = mapped_column(String(180), nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(160), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)

    stage = relationship("InterviewProcessStage", back_populates="attachments")


class InterviewStageComment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "interview_stage_comments"
    __table_args__ = (
        Index("ix_interview_stage_comments_stage_created", "stage_id", "created_at"),
        UniqueConstraint(
            "intelligence_interview_id",
            name="uq_interview_stage_comments_intelligence_interview",
        ),
    )

    stage_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("interview_process_stages.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_ai_feedback: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    intelligence_interview_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("intelligence_interviews.id", ondelete="CASCADE"),
        nullable=True,
    )
