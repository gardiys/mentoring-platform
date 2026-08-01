from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.knowledge.models import KnowledgeEntryKind
from app.roadmaps.admin_schemas import SLUG_PATTERN


class KnowledgeEntryListItem(BaseModel):
    id: UUID
    kind: KnowledgeEntryKind
    slug: str
    title: str
    summary: str | None


class KnowledgeTopicListItem(BaseModel):
    id: UUID
    slug: str
    title: str
    description: str | None
    article_count: int
    question_count: int


class KnowledgeTopicDetail(BaseModel):
    id: UUID
    slug: str
    title: str
    description: str | None
    entries: list[KnowledgeEntryListItem]


class KnowledgeTopicContext(BaseModel):
    id: UUID
    slug: str
    title: str


class KnowledgeEntryDetail(KnowledgeEntryListItem):
    content_markdown: str
    topic: KnowledgeTopicContext
    updated_at: datetime


class KnowledgeSearchResult(KnowledgeEntryListItem):
    topic: KnowledgeTopicContext
    excerpt: str
    rank: float


class AdminKnowledgeEntryMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: UUID | None = None
    kind: KnowledgeEntryKind = KnowledgeEntryKind.ARTICLE
    slug: str = Field(min_length=1, max_length=160, pattern=SLUG_PATTERN)
    title: str = Field(min_length=1, max_length=300)
    summary: str | None = None
    content_markdown: str = Field(min_length=1)
    position: int = Field(default=0, ge=0)
    is_published: bool = False


class AdminKnowledgeTopicMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    slug: str = Field(min_length=1, max_length=160, pattern=SLUG_PATTERN)
    title: str = Field(min_length=1, max_length=240)
    description: str | None = None
    position: int = Field(default=0, ge=0)
    is_published: bool = False
    track_ids: list[UUID] = Field(min_length=1)
    entries: list[AdminKnowledgeEntryMutation] = Field(default_factory=list)

    @field_validator("entries")
    @classmethod
    def unique_entry_ids(
        cls, value: list[AdminKnowledgeEntryMutation]
    ) -> list[AdminKnowledgeEntryMutation]:
        ids = [entry.id for entry in value if entry.id is not None]
        if len(ids) != len(set(ids)):
            raise ValueError("Knowledge entry IDs must be unique")
        slugs = [entry.slug for entry in value]
        if len(slugs) != len(set(slugs)):
            raise ValueError("Knowledge entry slugs must be unique")
        return value


class AdminKnowledgeTopicSettingsMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    slug: str = Field(min_length=1, max_length=160, pattern=SLUG_PATTERN)
    title: str = Field(min_length=1, max_length=240)
    description: str | None = None
    position: int = Field(default=0, ge=0)
    is_published: bool = False
    track_ids: list[UUID] = Field(min_length=1)


class AdminKnowledgeEntryRead(BaseModel):
    id: UUID
    kind: KnowledgeEntryKind
    slug: str
    title: str
    summary: str | None
    content_markdown: str
    position: int
    is_published: bool
    updated_at: datetime


class AdminKnowledgeTopicRead(BaseModel):
    id: UUID
    slug: str
    title: str
    description: str | None
    position: int
    is_published: bool
    track_ids: list[UUID]
    entries: list[AdminKnowledgeEntryRead]


class AdminKnowledgeEntrySummary(BaseModel):
    id: UUID
    kind: KnowledgeEntryKind
    slug: str
    title: str
    summary: str | None
    position: int
    is_published: bool
    updated_at: datetime


class AdminKnowledgeTopicSummary(AdminKnowledgeTopicSettingsMutation):
    id: UUID
    article_count: int
    question_count: int


class AdminKnowledgeTopicOutline(AdminKnowledgeTopicSettingsMutation):
    id: UUID
    entries: list[AdminKnowledgeEntrySummary]
