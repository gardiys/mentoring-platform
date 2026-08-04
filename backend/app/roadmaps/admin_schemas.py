from uuid import UUID

from pydantic import BaseModel, Field

from app.media.schemas import ProtectedContentMediaRead

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class AdminTopicCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=160, pattern=SLUG_PATTERN)
    title: str = Field(min_length=1, max_length=240)
    description: str | None = None
    content_markdown: str = Field(min_length=1)
    position: int = Field(default=0, ge=0)
    estimated_minutes: int | None = Field(default=None, gt=0)
    is_published: bool = False


class AdminSectionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: str | None = None
    position: int = Field(default=0, ge=0)
    duration_days: int | None = Field(default=None, gt=0)
    topics: list[AdminTopicCreate] = Field(min_length=1)


class AdminTopicUpdate(AdminTopicCreate):
    id: UUID | None = None


class AdminSectionUpdate(BaseModel):
    id: UUID | None = None
    title: str = Field(min_length=1, max_length=240)
    description: str | None = None
    position: int = Field(default=0, ge=0)
    duration_days: int | None = Field(default=None, gt=0)
    topics: list[AdminTopicUpdate] = Field(min_length=1)


class AdminRoadmapCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=160, pattern=SLUG_PATTERN)
    title: str = Field(min_length=1, max_length=240)
    description: str | None = None
    position: int = Field(default=0, ge=0)
    is_published: bool = False
    sections: list[AdminSectionCreate] = Field(min_length=1)


class AdminRoadmapUpdate(BaseModel):
    slug: str = Field(min_length=1, max_length=160, pattern=SLUG_PATTERN)
    title: str = Field(min_length=1, max_length=240)
    description: str | None = None
    position: int = Field(default=0, ge=0)
    is_published: bool = False
    sections: list[AdminSectionUpdate] = Field(min_length=1)


class AdminRoadmapSettingsMutation(BaseModel):
    slug: str = Field(min_length=1, max_length=160, pattern=SLUG_PATTERN)
    title: str = Field(min_length=1, max_length=240)
    description: str | None = None
    position: int = Field(default=0, ge=0)
    is_published: bool = False


class AdminSectionMutation(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: str | None = None
    position: int = Field(default=0, ge=0)
    duration_days: int | None = Field(default=None, gt=0)


class AdminTopicRead(BaseModel):
    id: UUID
    slug: str
    title: str
    description: str | None
    content_markdown: str
    position: int
    estimated_minutes: int | None
    is_published: bool
    media: list[ProtectedContentMediaRead]


class AdminSectionRead(BaseModel):
    id: UUID
    title: str
    description: str | None
    position: int
    duration_days: int | None
    topics: list[AdminTopicRead]


class AdminRoadmapRead(BaseModel):
    id: UUID
    slug: str
    title: str
    description: str | None
    position: int
    is_published: bool
    sections: list[AdminSectionRead]


class AdminTopicSummary(BaseModel):
    id: UUID
    slug: str
    title: str
    position: int
    estimated_minutes: int | None
    is_published: bool


class AdminSectionOutline(AdminSectionMutation):
    id: UUID
    topics: list[AdminTopicSummary]


class AdminRoadmapOutline(AdminRoadmapSettingsMutation):
    id: UUID
    sections: list[AdminSectionOutline]


class AdminRoadmapSummary(AdminRoadmapSettingsMutation):
    id: UUID
    section_count: int
    topic_count: int
