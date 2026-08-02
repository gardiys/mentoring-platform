from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.interviews.intelligence_models import (
    IntelligenceAssessment,
    IntelligenceAttemptStage,
    IntelligenceAttemptStatus,
    IntelligenceDifficulty,
    IntelligenceInterviewType,
    IntelligenceProcessingStatus,
    IntelligenceQuestionKind,
    IntelligenceQuestionModerationStatus,
    IntelligenceReviewSource,
    IntelligenceReviewStatus,
    IntelligenceSpeakerRole,
)
from app.interviews.models import InterviewCardFrequency


class IntelligenceInterviewCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    company_name: str = Field(min_length=1, max_length=240)
    company_id: UUID | None = None
    company_alias: str | None = Field(default=None, max_length=240)
    track_id: UUID
    position_name: str | None = Field(default=None, max_length=240)
    interview_type: IntelligenceInterviewType
    interviewed_at: datetime


class IntelligenceInterviewSummary(BaseModel):
    id: UUID
    stage_id: UUID
    process_id: UUID
    student_id: UUID
    student_name: str
    company_name: str
    position_name: str | None
    track_id: UUID
    track_slug: str
    track_title: str
    interview_type: IntelligenceInterviewType
    interviewed_at: datetime
    processing_status: IntelligenceProcessingStatus
    duration_ms: int | None
    question_count: int
    suggested_review_count: int
    reviewed_count: int
    reviewed_at: datetime | None
    reviewed_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime


class IntelligenceSpeakerRead(BaseModel):
    id: UUID
    provider_speaker_key: str
    role: IntelligenceSpeakerRole
    display_name: str | None
    examples: list["IntelligenceUtteranceRead"] = Field(default_factory=list)


class IntelligenceUtteranceRead(BaseModel):
    id: UUID
    speaker_id: UUID
    speaker_key: str
    speaker_role: IntelligenceSpeakerRole
    sequence_number: int
    start_ms: int
    end_ms: int
    text: str


class IntelligenceReviewRead(BaseModel):
    id: UUID
    parent_review_id: UUID | None
    source: IntelligenceReviewSource
    status: IntelligenceReviewStatus
    assessment: IntelligenceAssessment
    score: float | None
    summary: str | None
    strengths: list[dict[str, object]]
    problems: list[dict[str, object]]
    missing_points: list[object]
    incorrect_statements: list[dict[str, object]]
    suggested_better_answer: str | None
    model_name: str | None
    prompt_version: str | None
    created_by_user_id: UUID | None
    rejection_reason: str | None
    created_at: datetime


class IntelligenceAnswerRead(BaseModel):
    id: UUID
    answer_text: str
    start_ms: int | None
    end_ms: int | None
    reviews: list[IntelligenceReviewRead]


class IntelligenceQuestionRead(BaseModel):
    id: UUID
    sequence_number: int
    question_text: str
    question_start_ms: int
    question_end_ms: int | None
    answer_start_ms: int | None
    answer_end_ms: int | None
    category: str
    question_kind: IntelligenceQuestionKind
    subcategory: str | None
    difficulty: IntelligenceDifficulty
    confidence: float
    is_low_confidence: bool
    answer: IntelligenceAnswerRead | None
    moderation_status: IntelligenceQuestionModerationStatus
    published_card_id: UUID | None


class IntelligenceMentorCommentRead(BaseModel):
    id: UUID
    mentor_id: UUID
    mentor_name: str
    mentor_telegram_username: str | None
    question_id: UUID | None
    timestamp_ms: int | None
    text: str
    created_at: datetime
    updated_at: datetime


class IntelligenceProcessingAttemptRead(BaseModel):
    id: UUID
    stage: IntelligenceAttemptStage
    status: IntelligenceAttemptStatus
    attempt_number: int
    provider: str | None
    error_code: str | None
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None


class IntelligenceProcessingRead(BaseModel):
    status: IntelligenceProcessingStatus
    failed_stage: IntelligenceAttemptStage | None
    error_code: str | None
    error_message: str | None
    transcribed: bool
    candidate_selected: bool
    questions_found: int
    reviews_completed: int
    attempts: list[IntelligenceProcessingAttemptRead]


class IntelligenceCommunicationDimensionRead(BaseModel):
    name: str
    score: float | None
    summary: str
    evidence_utterance_ids: list[str]
    confidence: float


class IntelligenceInterviewOverviewRead(BaseModel):
    overall_summary: str
    key_topics: list[str]
    communication_summary: str
    communication_score: float | None
    communication_dimensions: list[IntelligenceCommunicationDimensionRead]
    communication_strengths: list[str]
    communication_growth_areas: list[str]
    caveats: list[str]
    model_name: str | None
    prompt_version: str | None


class IntelligenceInterviewDetail(IntelligenceInterviewSummary):
    media_filename: str | None
    media_content_type: str | None
    media_size: int | None
    speakers: list[IntelligenceSpeakerRead]
    transcript: list[IntelligenceUtteranceRead]
    questions: list[IntelligenceQuestionRead]
    mentor_comments: list[IntelligenceMentorCommentRead]
    overview: IntelligenceInterviewOverviewRead | None
    processing: IntelligenceProcessingRead


class IntelligenceCandidateSpeakerMutation(BaseModel):
    speaker_id: UUID


class IntelligenceMentorCommentMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question_id: UUID | None = None
    timestamp_ms: int | None = Field(default=None, ge=0)
    text: str = Field(min_length=1, max_length=10_000)


class IntelligenceReviewEditMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    assessment: IntelligenceAssessment
    score: float | None = Field(default=None, ge=0, le=1)
    summary: str | None = None
    strengths: list[dict[str, object]] = Field(default_factory=list)
    problems: list[dict[str, object]] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    incorrect_statements: list[dict[str, object]] = Field(default_factory=list)
    suggested_better_answer: str | None = None


class IntelligenceReviewRejectMutation(BaseModel):
    reason: str = Field(
        default="other", pattern="^(wrong_assessment|bad_transcription|wrong_question|other)$"
    )


class IntelligenceQuestionModerationMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    action: str = Field(pattern="^(recommend|approve|reject)$")
    question_markdown: str | None = Field(default=None, min_length=1)
    answer_markdown: str | None = Field(default=None, min_length=1)
    category: str | None = Field(default=None, min_length=1, max_length=240)
    frequency: InterviewCardFrequency = InterviewCardFrequency.OCCASIONAL


class IntelligenceWebhookPayload(BaseModel):
    transcript_id: str = Field(min_length=1, max_length=500)
    status: str = Field(pattern="^(completed|error)$")


class IntelligenceMediaRead(BaseModel):
    url: str
    content_type: str


class IntelligenceReviewQueuePage(BaseModel):
    items: list[IntelligenceInterviewSummary]
    total: int
    limit: int
    offset: int


class AdminQuestionModerationSummary(BaseModel):
    question_id: UUID
    interview_id: UUID
    question_text: str
    category: str
    question_kind: IntelligenceQuestionKind
    difficulty: IntelligenceDifficulty
    moderation_status: IntelligenceQuestionModerationStatus
    company_name: str
    track_id: UUID
    track_slug: str
    track_title: str
    student_name: str
    interviewed_at: datetime


class AdminQuestionModerationDetail(AdminQuestionModerationSummary):
    candidate_answer: str | None
    suggested_answer: str | None
    matched_card_id: UUID | None
    matched_card_question: str | None
    matched_card_asked_count: int | None


class AdminQuestionModerationPage(BaseModel):
    items: list[AdminQuestionModerationSummary]
    total: int
    limit: int
    offset: int


class IntelligenceReviewQueueFilter(BaseModel):
    status: str = "all"

    @model_validator(mode="after")
    def validate_status(self) -> "IntelligenceReviewQueueFilter":
        if self.status not in {"needs_review", "reviewed", "processing", "all"}:
            raise ValueError("Unknown review queue filter")
        return self
