import re
from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.interviews.intelligence_models import IntelligenceProcessingStatus
from app.interviews.models import (
    CompanyAliasProposalStatus,
    InterviewCardFrequency,
    InterviewCardFrequencyMode,
    InterviewProcessStatus,
    InterviewReviewRating,
    InterviewStageType,
    RecruiterFeedbackKind,
)
from app.roadmaps.admin_schemas import SLUG_PATTERN
from app.users.models import UserRole


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
    frequency_mode: InterviewCardFrequencyMode = InterviewCardFrequencyMode.MANUAL
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
    frequency_override: InterviewCardFrequency | None
    frequency_mode: InterviewCardFrequencyMode
    frequency_threshold: int
    position: int
    is_published: bool
    asked_count: int
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
    frequency_override: InterviewCardFrequency | None
    frequency_mode: InterviewCardFrequencyMode
    frequency_threshold: int
    position: int
    is_published: bool
    asked_count: int


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


class InterviewUploadProtocol(StrEnum):
    LEGACY_POST = "legacy-post"
    MULTIPART_V1 = "multipart-v1"


class InterviewUploadRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    filename: str = Field(min_length=1, max_length=500)
    content_type: str = Field(min_length=1, max_length=160)
    size: int = Field(gt=0)
    upload_protocol: InterviewUploadProtocol = InterviewUploadProtocol.LEGACY_POST


class InterviewUploadIntent(BaseModel):
    upload_url: str
    fields: dict[str, str]
    storage_key: str
    filename: str
    content_type: str
    size: int
    expires_in: int


class InterviewMultipartUploadPartIntent(BaseModel):
    part_number: int = Field(ge=1, le=10_000)
    upload_url: str
    headers: dict[str, str]


class InterviewMultipartUploadIntent(BaseModel):
    upload_protocol: Literal["multipart-v1"]
    upload_id: str
    upload_token: str
    abort_url: str
    storage_key: str
    filename: str
    content_type: str
    size: int
    part_size: int
    part_count: int
    parts: list[InterviewMultipartUploadPartIntent]
    expires_in: int


class InterviewCompletedMultipartPart(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    part_number: int = Field(ge=1, le=10_000)
    etag: str = Field(min_length=1, max_length=200)


class InterviewUploadComplete(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    storage_key: str = Field(min_length=1, max_length=500)
    filename: str = Field(min_length=1, max_length=500)
    content_type: str = Field(min_length=1, max_length=160)
    size: int = Field(gt=0)
    upload_protocol: InterviewUploadProtocol = InterviewUploadProtocol.LEGACY_POST
    upload_id: str | None = Field(default=None, min_length=1, max_length=1_000)
    upload_token: str | None = Field(default=None, min_length=1, max_length=8_192)
    parts: list[InterviewCompletedMultipartPart] = Field(default_factory=list, max_length=10_000)

    @model_validator(mode="after")
    def validate_upload_protocol_fields(self) -> "InterviewUploadComplete":
        if self.upload_protocol is InterviewUploadProtocol.MULTIPART_V1:
            if self.upload_id is None or self.upload_token is None or not self.parts:
                raise ValueError("Multipart completion requires upload_id, upload_token and parts")
        elif self.upload_id is not None or self.upload_token is not None or self.parts:
            raise ValueError("Multipart fields require upload_protocol=multipart-v1")
        return self


class InterviewMultipartUploadAbort(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    storage_key: str = Field(min_length=1, max_length=500)
    upload_id: str = Field(min_length=1, max_length=1_000)
    upload_token: str = Field(min_length=1, max_length=8_192)


type InterviewUploadIntentResponse = InterviewUploadIntent | InterviewMultipartUploadIntent


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
    company_alias_confirmed: bool = False
    recruiter_telegram_usernames: list[str] | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def validate_company_alias_confirmation(self) -> "InterviewProcessMutation":
        if self.company_alias is not None and (
            self.company_id is None or not self.company_alias_confirmed
        ):
            raise ValueError(
                "An alternative company name requires a selected company and explicit confirmation"
            )
        if self.company_alias_confirmed and self.company_alias is None:
            raise ValueError("No alternative company name was provided")
        return self

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


class InterviewStageEditLockReason(StrEnum):
    WINDOW_EXPIRED = "window_expired"
    AI_ANALYSIS_REQUESTED = "ai_analysis_requested"


class InterviewProcessDeleteLockReason(StrEnum):
    WINDOW_EXPIRED = "window_expired"
    AI_ANALYSIS_REQUESTED = "ai_analysis_requested"


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
    can_edit: bool
    edit_locked_reason: InterviewStageEditLockReason | None
    editable_until: datetime
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


class AdminCompanyAliasProposalRead(BaseModel):
    id: UUID
    company_id: UUID | None
    company_name: str
    alias_name: str
    suggested_by_user_id: UUID | None
    suggested_by_name: str | None
    suggested_by_telegram_username: str | None
    status: CompanyAliasProposalStatus
    conflicting_company_id: UUID | None
    conflicting_company_name: str | None
    reviewed_by_name: str | None
    reviewed_at: datetime | None
    rejection_reason: str | None
    created_at: datetime


class AdminCompanyAliasProposalPage(BaseModel):
    items: list[AdminCompanyAliasProposalRead]
    total: int
    limit: int
    offset: int


class AdminCompanyAliasProposalMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    action: Literal["approve", "reject"]
    merge_conflicting_company: bool = False
    rejection_reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_decision(self) -> "AdminCompanyAliasProposalMutation":
        if self.action == "reject" and not self.rejection_reason:
            raise ValueError("A rejection reason is required")
        if self.action == "reject" and self.merge_conflicting_company:
            raise ValueError("Rejected aliases cannot merge companies")
        return self


class InterviewProcessDetail(InterviewProcessSummary):
    stages: list[InterviewProcessStageRead]
    offer: InterviewAttachmentRead | None
    can_delete: bool
    delete_locked_reason: InterviewProcessDeleteLockReason | None
    deletable_until: datetime


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
    is_viewed: bool = False
    first_viewed_at: datetime | None = None
    last_viewed_at: datetime | None = None
    is_favorite: bool = False


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
    unviewed_count: int = 0
    has_favorite: bool = False


class InterviewCatalogCompanyPage(BaseModel):
    items: list[InterviewCatalogCompanyListItem]
    total: int
    limit: int
    offset: int


class InterviewCatalogCompanyDetail(BaseModel):
    id: UUID
    name: str
    tracks: list[InterviewCatalogTrackRead]


class InterviewCatalogHistoryItem(BaseModel):
    stage_id: UUID
    process_id: UUID
    company_id: UUID
    company_name: str
    track_title: str
    stage_type: InterviewStageType
    scheduled_at: datetime
    description: str | None
    first_viewed_at: datetime
    last_viewed_at: datetime


class InterviewCatalogHistoryPage(BaseModel):
    items: list[InterviewCatalogHistoryItem]
    total: int
    limit: int
    offset: int


class RecruiterContactCompanyRead(BaseModel):
    id: UUID
    name: str


class RecruiterContactTrackRead(BaseModel):
    id: UUID
    slug: str
    title: str


class RecruiterSort(StrEnum):
    RECOMMENDED = "recommended"
    MOST_HELPFUL = "most_helpful"
    MOST_CONTACTED = "most_contacted"
    RECENTLY_CONTACTED = "recently_contacted"
    USERNAME = "username"


class RecruiterFeedbackMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    kind: RecruiterFeedbackKind
    reason: str | None = Field(default=None, max_length=1_000)

    @model_validator(mode="after")
    def validate_reason(self) -> "RecruiterFeedbackMutation":
        if self.kind is RecruiterFeedbackKind.OTHER and not self.reason:
            raise ValueError("A reason is required for other recruiter feedback")
        return self


class RecruiterFeedbackRead(BaseModel):
    kind: RecruiterFeedbackKind
    reason: str | None
    updated_at: datetime


class RecruiterIssueCommentRead(BaseModel):
    author_id: UUID
    author_first_name: str
    author_telegram_username: str | None
    author_role: UserRole
    kind: RecruiterFeedbackKind
    reason: str
    updated_at: datetime


class RecruiterContactRead(BaseModel):
    id: UUID
    telegram_username: str
    companies: list[RecruiterContactCompanyRead]
    tracks: list[RecruiterContactTrackRead]
    total_contact_opens: int
    students_contacted_count: int
    last_contacted_at: datetime | None
    helpful_count: int
    ignores_count: int
    no_longer_works_count: int
    account_missing_count: int
    other_issue_count: int
    issue_comments: list[RecruiterIssueCommentRead]
    issue_comments_total: int
    has_contacted: bool
    my_contact_opens: int
    my_last_contacted_at: datetime | None
    my_feedback: RecruiterFeedbackRead | None


class RecruiterCompanyGroupRead(BaseModel):
    company: RecruiterContactCompanyRead
    recruiters: list[RecruiterContactRead]


class RecruiterContactPage(BaseModel):
    items: list[RecruiterCompanyGroupRead]
    total: int
    limit: int
    offset: int


class RecruiterContactOpenRead(BaseModel):
    recruiter_id: UUID
    url: str
    total_contact_opens: int
    students_contacted_count: int
    last_contacted_at: datetime
    my_contact_opens: int
    my_last_contacted_at: datetime
