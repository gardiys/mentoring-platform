from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    BigInteger,
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
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class IntelligenceInterviewType(StrEnum):
    HR = "hr"
    SCREENING = "screening"
    TECHNICAL = "technical"
    FINAL = "final"
    SYSTEM_DESIGN = "system_design"
    LIVE_CODING = "live_coding"
    OTHER = "other"


class IntelligenceProcessingStatus(StrEnum):
    DRAFT = "draft"
    UPLOADED = "uploaded"
    TRANSCRIPTION_SUBMITTED = "transcription_submitted"
    TRANSCRIBING = "transcribing"
    TRANSCRIPT_READY = "transcript_ready"
    AWAITING_CANDIDATE_SPEAKER = "awaiting_candidate_speaker"
    ANALYZING = "analyzing"
    READY = "ready"
    FAILED = "failed"


class IntelligenceSpeakerRole(StrEnum):
    UNKNOWN = "unknown"
    CANDIDATE = "candidate"
    INTERVIEWER = "interviewer"
    RECRUITER = "recruiter"
    OTHER = "other"


class IntelligenceDifficulty(StrEnum):
    UNKNOWN = "unknown"
    JUNIOR = "junior"
    MIDDLE = "middle"
    SENIOR = "senior"


class IntelligenceQuestionKind(StrEnum):
    TECHNICAL = "technical"
    HR = "hr"
    ORGANIZATIONAL = "organizational"
    OTHER = "other"


class IntelligenceReviewSource(StrEnum):
    AI = "ai"
    MENTOR = "mentor"


class IntelligenceReviewStatus(StrEnum):
    SUGGESTED = "suggested"
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"


class IntelligenceQuestionModerationStatus(StrEnum):
    PENDING = "pending"
    MENTOR_APPROVED = "mentor_approved"
    APPROVED = "approved"
    REJECTED = "rejected"


class IntelligenceAssessment(StrEnum):
    CORRECT = "correct"
    MOSTLY_CORRECT = "mostly_correct"
    PARTIAL = "partial"
    MOSTLY_INCORRECT = "mostly_incorrect"
    INCORRECT = "incorrect"
    UNABLE_TO_ASSESS = "unable_to_assess"


class IntelligenceAttemptStage(StrEnum):
    NORMALIZE = "normalize"
    TRANSCRIPTION_SUBMIT = "transcription_submit"
    TRANSCRIPTION_POLL = "transcription_poll"
    TRANSCRIPTION_PARSE = "transcription_parse"
    AI_EXTRACT = "ai_extract"
    AI_REVIEW = "ai_review"


class IntelligenceAttemptStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


class IntelligenceInterview(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "intelligence_interviews"
    __table_args__ = (
        Index("ix_intelligence_interviews_student_status", "student_id", "processing_status"),
        UniqueConstraint("stage_id", name="uq_intelligence_interviews_stage"),
    )

    stage_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("interview_process_stages.id", ondelete="CASCADE"),
        nullable=False,
    )
    student_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    position_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    interview_type: Mapped[IntelligenceInterviewType] = mapped_column(
        Enum(
            IntelligenceInterviewType,
            name="intelligence_interview_type",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    processing_status: Mapped[IntelligenceProcessingStatus] = mapped_column(
        Enum(
            IntelligenceProcessingStatus,
            name="intelligence_processing_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=IntelligenceProcessingStatus.DRAFT,
        nullable=False,
    )
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    normalized_audio_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    transcription_provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    transcription_provider_job_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    transcription_provider_payload: Mapped[dict[str, object] | None] = mapped_column(
        JSONB, nullable=True
    )
    candidate_speaker_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "intelligence_speakers.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_int_interview_candidate_speaker",
        ),
        nullable=True,
    )
    failed_stage: Mapped[IntelligenceAttemptStage | None] = mapped_column(
        Enum(
            IntelligenceAttemptStage,
            name="intelligence_attempt_stage",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=True,
    )
    processing_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    processing_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_summary_payload: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    ai_summary_model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    ai_summary_prompt_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class IntelligenceAIAdmission(UUIDPrimaryKeyMixin, Base):
    """Durable record of a user-triggered operation that can incur AI cost."""

    __tablename__ = "intelligence_ai_admissions"
    __table_args__ = (
        Index(
            "ix_intelligence_ai_admissions_requester_requested",
            "requester_user_id",
            "requested_at",
        ),
        Index(
            "ix_intelligence_ai_admissions_interview",
            "interview_id",
            "requested_at",
        ),
    )

    requester_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    interview_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("intelligence_interviews.id", ondelete="SET NULL"),
        nullable=True,
    )
    operation: Mapped[str] = mapped_column(String(40), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IntelligenceSpeaker(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "intelligence_speakers"
    __table_args__ = (
        UniqueConstraint(
            "interview_id", "provider_speaker_key", name="uq_intelligence_speaker_provider_key"
        ),
    )

    interview_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("intelligence_interviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_speaker_key: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[IntelligenceSpeakerRole] = mapped_column(
        Enum(
            IntelligenceSpeakerRole,
            name="intelligence_speaker_role",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=IntelligenceSpeakerRole.UNKNOWN,
        nullable=False,
    )
    display_name: Mapped[str | None] = mapped_column(String(160), nullable=True)


class IntelligenceUtterance(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "intelligence_utterances"
    __table_args__ = (
        UniqueConstraint(
            "interview_id", "sequence_number", name="uq_intelligence_utterance_sequence"
        ),
        Index("ix_intelligence_utterances_interview_start", "interview_id", "start_ms"),
        CheckConstraint("start_ms >= 0 AND end_ms >= start_ms", name="valid_time_range"),
    )

    interview_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("intelligence_interviews.id", ondelete="CASCADE"),
        nullable=False,
    )
    speaker_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("intelligence_speakers.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IntelligenceQuestion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "intelligence_questions"
    __table_args__ = (
        UniqueConstraint(
            "interview_id", "sequence_number", name="uq_intelligence_question_sequence"
        ),
        Index("ix_intelligence_questions_interview_start", "interview_id", "question_start_ms"),
        Index(
            "ix_intelligence_questions_published_card",
            "published_card_id",
            postgresql_where=text("published_card_id IS NOT NULL"),
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )

    interview_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("intelligence_interviews.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_embedding: Mapped[list[float] | None] = mapped_column(ARRAY(Float), nullable=True)
    question_embedding_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    question_embedding_dimensions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    question_embedding_source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    question_start_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    question_end_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    answer_start_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    answer_end_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    question_utterance_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), nullable=False
    )
    answer_utterance_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), nullable=False
    )
    category: Mapped[str] = mapped_column(String(120), nullable=False)
    question_kind: Mapped[IntelligenceQuestionKind] = mapped_column(
        Enum(
            IntelligenceQuestionKind,
            name="intelligence_question_kind",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=IntelligenceQuestionKind.OTHER,
        nullable=False,
    )
    subcategory: Mapped[str | None] = mapped_column(String(160), nullable=True)
    difficulty: Mapped[IntelligenceDifficulty] = mapped_column(
        Enum(
            IntelligenceDifficulty,
            name="intelligence_difficulty",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    moderation_status: Mapped[IntelligenceQuestionModerationStatus] = mapped_column(
        Enum(
            IntelligenceQuestionModerationStatus,
            name="intelligence_question_moderation_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=IntelligenceQuestionModerationStatus.PENDING,
        nullable=False,
    )
    mentor_reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    mentor_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    admin_reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    admin_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_card_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("interview_cards.id", ondelete="SET NULL"),
        nullable=True,
    )


class IntelligenceAnswer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "intelligence_answers"
    __table_args__ = (UniqueConstraint("question_id", name="uq_intelligence_answer_question"),)

    question_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("intelligence_questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    student_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    start_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    end_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class IntelligenceAnswerReview(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "intelligence_answer_reviews"
    __table_args__ = (Index("ix_intelligence_reviews_answer_created", "answer_id", "created_at"),)

    answer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("intelligence_answers.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_review_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("intelligence_answer_reviews.id", ondelete="SET NULL"),
        nullable=True,
    )
    source: Mapped[IntelligenceReviewSource] = mapped_column(
        Enum(
            IntelligenceReviewSource,
            name="intelligence_review_source",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    status: Mapped[IntelligenceReviewStatus] = mapped_column(
        Enum(
            IntelligenceReviewStatus,
            name="intelligence_review_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    assessment: Mapped[IntelligenceAssessment] = mapped_column(
        Enum(
            IntelligenceAssessment,
            name="intelligence_assessment",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    strengths: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list, nullable=False)
    problems: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list, nullable=False)
    missing_points: Mapped[list[object]] = mapped_column(JSONB, default=list, nullable=False)
    incorrect_statements: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    suggested_better_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)


class IntelligenceMentorComment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "intelligence_mentor_comments"
    __table_args__ = (
        Index("ix_intelligence_comments_interview_created", "interview_id", "created_at"),
    )

    mentor_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    interview_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("intelligence_interviews.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("intelligence_questions.id", ondelete="CASCADE"),
        nullable=True,
    )
    timestamp_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)


class IntelligenceProcessingAttempt(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "intelligence_processing_attempts"
    __table_args__ = (
        UniqueConstraint(
            "interview_id", "stage", "attempt_number", name="uq_intelligence_attempt_number"
        ),
        Index("ix_intelligence_attempts_interview_started", "interview_id", "started_at"),
    )

    interview_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("intelligence_interviews.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage: Mapped[IntelligenceAttemptStage] = mapped_column(
        Enum(
            IntelligenceAttemptStage,
            name="intelligence_attempt_stage",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    status: Mapped[IntelligenceAttemptStatus] = mapped_column(
        Enum(
            IntelligenceAttemptStatus,
            name="intelligence_attempt_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    external_request_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IntelligenceAIUsage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "intelligence_ai_usage"

    interview_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("intelligence_interviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("intelligence_questions.id", ondelete="CASCADE"),
        nullable=True,
    )
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    operation: Mapped[str] = mapped_column(String(40), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IntelligenceTranscriptionUsage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "intelligence_transcription_usage"

    interview_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("intelligence_interviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    provider_job_id: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
