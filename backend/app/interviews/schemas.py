import re
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.interviews.intelligence_models import IntelligenceProcessingStatus
from app.interviews.models import (
    InterviewCardFrequency,
    InterviewProcessStatus,
    InterviewReviewRating,
    InterviewStageType,
)
from app.roadmaps.admin_schemas import SLUG_PATTERN


class InterviewDeckStats(BaseModel):
    available_cards: int
    selected_categories: int
    total_categories: int
    total_cards: int
    learned_cards: int
    remaining_cards: int
    due_cards: int
    progress_percent: int


class InterviewDeckListItem(BaseModel):
    id: UUID
    slug: str
    title: str
    description: str | None
    track_id: UUID
    track_slug: str
    track_title: str
    stats: InterviewDeckStats


class InterviewCardStudy(BaseModel):
    id: UUID
    slug: str
    category: str
    companies: str | None
    question_markdown: str
    answer_markdown: str
    frequency: InterviewCardFrequency
    is_new: bool
    repetitions: int


class InterviewStudySession(BaseModel):
    deck: InterviewDeckListItem
    cards: list[InterviewCardStudy]


class InterviewReviewMutation(BaseModel):
    rating: InterviewReviewRating


class InterviewReviewResult(BaseModel):
    card_id: UUID
    rating: InterviewReviewRating
    repetitions: int
    interval_days: int
    due_at: datetime
    learned: bool


class InterviewTopicOption(BaseModel):
    name: str
    total_cards: int
    frequent_cards: int
    is_selected: bool


class InterviewTopicSelectionMutation(BaseModel):
    categories: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("categories")
    @classmethod
    def unique_categories(cls, value: list[str]) -> list[str]:
        normalized = [category.strip() for category in value]
        if any(not category or len(category) > 240 for category in normalized):
            raise ValueError("Interview categories must contain 1 to 240 characters")
        if len(normalized) != len(set(normalized)):
            raise ValueError("Interview categories must be unique")
        return normalized


class AdminInterviewCardMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: UUID | None = None
    slug: str = Field(min_length=1, max_length=180, pattern=SLUG_PATTERN)
    category: str = Field(default="Общее", min_length=1, max_length=240)
    companies: str | None = None
    question_markdown: str = Field(min_length=1)
    answer_markdown: str = Field(min_length=1)
    frequency: InterviewCardFrequency = InterviewCardFrequency.OCCASIONAL
    position: int = Field(default=0, ge=0)
    is_published: bool = False


class AdminInterviewDeckMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    track_id: UUID
    slug: str = Field(min_length=1, max_length=160, pattern=SLUG_PATTERN)
    title: str = Field(min_length=1, max_length=240)
    description: str | None = None
    position: int = Field(default=0, ge=0)
    is_published: bool = False
    cards: list[AdminInterviewCardMutation] = Field(default_factory=list)

    @field_validator("cards")
    @classmethod
    def unique_cards(
        cls, value: list[AdminInterviewCardMutation]
    ) -> list[AdminInterviewCardMutation]:
        ids = [card.id for card in value if card.id is not None]
        if len(ids) != len(set(ids)):
            raise ValueError("Interview card IDs must be unique")
        slugs = [card.slug for card in value]
        if len(slugs) != len(set(slugs)):
            raise ValueError("Interview card slugs must be unique")
        return value


class AdminInterviewDeckSettingsMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    track_id: UUID
    slug: str = Field(min_length=1, max_length=160, pattern=SLUG_PATTERN)
    title: str = Field(min_length=1, max_length=240)
    description: str | None = None
    position: int = Field(default=0, ge=0)
    is_published: bool = False


class AdminInterviewCardRead(BaseModel):
    id: UUID
    slug: str
    category: str
    companies: str | None
    source_number: int | None
    source_occurrence: str | None
    question_markdown: str
    answer_markdown: str
    frequency: InterviewCardFrequency
    position: int
    is_published: bool
    updated_at: datetime


class AdminInterviewDeckRead(BaseModel):
    id: UUID
    track_id: UUID
    track_slug: str
    track_title: str
    slug: str
    title: str
    description: str | None
    position: int
    is_published: bool
    cards: list[AdminInterviewCardRead]


class AdminInterviewDeckSummary(AdminInterviewDeckSettingsMutation):
    id: UUID
    track_slug: str
    track_title: str
    card_count: int
    frequent_count: int


class AdminInterviewCardSummary(BaseModel):
    id: UUID
    slug: str
    category: str
    question_preview: str
    frequency: InterviewCardFrequency
    position: int
    is_published: bool


class AdminInterviewCardPage(BaseModel):
    items: list[AdminInterviewCardSummary]
    total: int
    limit: int
    offset: int


class InterviewAttachmentRead(BaseModel):
    filename: str
    content_type: str
    size: int


class InterviewStageAttachmentRead(InterviewAttachmentRead):
    id: UUID
    created_at: datetime


class InterviewUploadRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    filename: str = Field(min_length=1, max_length=500)
    content_type: str = Field(min_length=1, max_length=160)
    size: int = Field(gt=0)


class InterviewUploadIntent(BaseModel):
    upload_url: str
    fields: dict[str, str]
    storage_key: str
    filename: str
    content_type: str
    size: int
    expires_in: int


class InterviewUploadComplete(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    storage_key: str = Field(min_length=1, max_length=500)
    filename: str = Field(min_length=1, max_length=500)
    content_type: str = Field(min_length=1, max_length=160)
    size: int = Field(gt=0)


class InterviewDownloadUrl(BaseModel):
    url: str


class CompanyOption(BaseModel):
    id: UUID
    name: str


class InterviewDirectionOption(BaseModel):
    id: UUID
    slug: str
    title: str


TELEGRAM_USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")


def _normalize_telegram_usernames(values: list[str]) -> list[str]:
    usernames: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        value = raw_value.strip()
        for prefix in ("https://t.me/", "http://t.me/", "t.me/"):
            if value.casefold().startswith(prefix):
                value = value[len(prefix) :].strip("/")
                break
        username = value.lstrip("@").casefold()
        if not TELEGRAM_USERNAME_PATTERN.fullmatch(username):
            raise ValueError("Enter a valid Telegram username, for example @recruiter_name")
        if username not in seen:
            seen.add(username)
            usernames.append(username)
    return usernames


class InterviewProcessMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    company_name: str = Field(min_length=1, max_length=240)
    track_id: UUID
    company_id: UUID | None = None
    company_alias: str | None = Field(default=None, min_length=1, max_length=240)
    recruiter_telegram_usernames: list[str] | None = Field(default=None, max_length=20)

    @field_validator("recruiter_telegram_usernames")
    @classmethod
    def normalize_recruiter_usernames(cls, values: list[str] | None) -> list[str] | None:
        return _normalize_telegram_usernames(values) if values is not None else None


class InterviewProcessRecruitersMutation(BaseModel):
    recruiter_telegram_usernames: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("recruiter_telegram_usernames")
    @classmethod
    def normalize_recruiter_usernames(cls, values: list[str]) -> list[str]:
        return _normalize_telegram_usernames(values)


class InterviewProcessStageMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    stage_type: InterviewStageType
    scheduled_at: datetime
    description: str | None = Field(default=None, max_length=10_000)


class InterviewProcessOutcomeMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    status: InterviewProcessStatus
    close_reason: str | None = Field(default=None, max_length=5_000)

    @model_validator(mode="after")
    def closed_process_has_reason(self) -> "InterviewProcessOutcomeMutation":
        if self.status is InterviewProcessStatus.CLOSED and not self.close_reason:
            raise ValueError("A close reason is required for a closed interview process")
        return self


class InterviewCatalogAuthorRead(BaseModel):
    id: UUID
    name: str
    telegram_username: str | None


class InterviewCatalogCommentRead(BaseModel):
    id: UUID
    author: InterviewCatalogAuthorRead | None
    body: str
    is_own: bool
    is_mentor_feedback: bool = False
    is_ai_feedback: bool = False
    created_at: datetime
    updated_at: datetime


class InterviewProcessStageRead(BaseModel):
    id: UUID
    stage_type: InterviewStageType
    scheduled_at: datetime
    description: str | None
    media: InterviewAttachmentRead | None
    attachments: list[InterviewStageAttachmentRead]
    comments: list[InterviewCatalogCommentRead] = Field(default_factory=list)
    ai_analysis_id: UUID | None = None
    ai_analysis_status: IntelligenceProcessingStatus | None = None
    ai_analysis_requested_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class InterviewProcessSummary(BaseModel):
    id: UUID
    company_name: str
    recruiter_telegram_usernames: list[str]
    track_id: UUID
    track_slug: str
    track_title: str
    status: InterviewProcessStatus
    close_reason: str | None = Field(description="Latest closure reason, retained after reopening")
    closed_at: datetime | None = Field(
        description="Time of the latest closure, retained after reopening"
    )
    stage_count: int
    next_stage_at: datetime | None
    has_offer_file: bool
    created_at: datetime
    updated_at: datetime


class AdminInterviewProcessSummary(InterviewProcessSummary):
    author: "InterviewCatalogAuthorRead"
    company_id: UUID


class AdminInterviewProcessPage(BaseModel):
    items: list[AdminInterviewProcessSummary]
    total: int
    limit: int
    offset: int


class InterviewProcessDetail(InterviewProcessSummary):
    stages: list[InterviewProcessStageRead]
    offer: InterviewAttachmentRead | None


class InterviewCatalogMediaKind(StrEnum):
    ANY = "any"
    VIDEO = "video"
    AUDIO = "audio"


class InterviewCatalogCommentMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    body: str = Field(min_length=1, max_length=5_000)


class InterviewCatalogStageRead(BaseModel):
    id: UUID
    stage_type: InterviewStageType
    scheduled_at: datetime
    description: str | None
    media: InterviewAttachmentRead | None
    attachments: list[InterviewStageAttachmentRead]
    comments: list[InterviewCatalogCommentRead]


class InterviewCatalogTrackRead(BaseModel):
    id: UUID
    author: InterviewCatalogAuthorRead
    recruiter_telegram_usernames: list[str]
    track_id: UUID
    track_slug: str
    track_title: str
    status: InterviewProcessStatus
    close_reason: str | None
    created_at: datetime
    updated_at: datetime
    stages: list[InterviewCatalogStageRead]


class InterviewCatalogCompanyListItem(BaseModel):
    id: UUID
    name: str
    track_count: int
    interview_count: int
    last_interview_at: datetime | None


class InterviewCatalogCompanyPage(BaseModel):
    items: list[InterviewCatalogCompanyListItem]
    total: int
    limit: int
    offset: int


class InterviewCatalogCompanyDetail(BaseModel):
    id: UUID
    name: str
    tracks: list[InterviewCatalogTrackRead]
