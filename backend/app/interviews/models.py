from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
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
    func,
)
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
