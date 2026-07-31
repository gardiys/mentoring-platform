from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.interviews.models import InterviewCardFrequency, InterviewReviewRating
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
