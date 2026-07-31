from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.progress.models import ProgressStatus


class ProgressSummary(BaseModel):
    completed_topics: int
    total_topics: int
    progress_percent: int


class TopicProgressRead(BaseModel):
    topic_id: UUID
    status: ProgressStatus
    started_at: datetime | None
    first_completed_at: datetime | None
    last_completed_at: datetime | None


class ProgressUpdateRequest(BaseModel):
    status: str


class ProgressUpdateResponse(BaseModel):
    topic_progress: TopicProgressRead
    roadmap_progress: ProgressSummary
