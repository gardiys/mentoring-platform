from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel

from app.progress.models import ProgressStatus
from app.progress.schemas import ProgressSummary


class RoadmapStartRequest(BaseModel):
    started_on: date | None = None


class RoadmapListItem(ProgressSummary):
    id: UUID
    slug: str
    title: str
    description: str | None
    started_at: datetime | None
    completed_at: datetime | None
    total_duration_days: int
    planned_completion_at: datetime | None


class TopicListItem(BaseModel):
    id: UUID
    slug: str
    title: str
    description: str | None
    estimated_minutes: int | None
    status: ProgressStatus
    first_completed_at: datetime | None
    last_completed_at: datetime | None


class SectionRead(BaseModel):
    id: UUID
    title: str
    description: str | None
    duration_days: int | None
    deadline_at: datetime | None
    topics: list[TopicListItem]


class RoadmapDetail(ProgressSummary):
    id: UUID
    slug: str
    title: str
    description: str | None
    started_at: datetime | None
    completed_at: datetime | None
    total_duration_days: int
    planned_completion_at: datetime | None
    sections: list[SectionRead]


class TopicContext(BaseModel):
    id: UUID
    slug: str | None = None
    title: str


class TopicDetail(BaseModel):
    id: UUID
    slug: str
    title: str
    description: str | None
    content_markdown: str
    estimated_minutes: int | None
    roadmap: TopicContext
    section: TopicContext
    status: ProgressStatus
    started_at: datetime | None
    first_completed_at: datetime | None
    last_completed_at: datetime | None
