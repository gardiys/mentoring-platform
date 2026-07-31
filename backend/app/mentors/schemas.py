from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.roadmaps.schemas import RoadmapDetail


class StudentRoadmapSummary(BaseModel):
    id: UUID
    slug: str
    title: str
    completed_topics: int
    total_topics: int
    progress_percent: int
    started_at: datetime
    completed_at: datetime | None


class MentorStudentListItem(BaseModel):
    id: UUID
    first_name: str
    last_name: str | None
    email: str | None
    roadmaps: list[StudentRoadmapSummary]
    last_progress_at: datetime | None


class MentorStudentDetail(BaseModel):
    id: UUID
    first_name: str
    last_name: str | None
    email: str | None
    roadmaps: list[RoadmapDetail]
