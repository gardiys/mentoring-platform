from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import api_error
from app.progress.models import ProgressStatus, TopicProgress
from app.progress.schemas import ProgressSummary
from app.roadmaps.models import RoadmapEnrollment, RoadmapSection, Topic


@dataclass(frozen=True)
class ProgressCounts:
    completed: int
    total: int

    @property
    def percent(self) -> int:
        return round(self.completed / self.total * 100) if self.total else 0


async def get_progress_counts(
    session: AsyncSession, user_id: UUID, roadmap_id: UUID
) -> ProgressCounts:
    total = await session.scalar(
        select(func.count(Topic.id))
        .join(RoadmapSection, Topic.section_id == RoadmapSection.id)
        .where(RoadmapSection.roadmap_id == roadmap_id, Topic.is_published.is_(True))
    )
    completed = await session.scalar(
        select(func.count(TopicProgress.topic_id))
        .join(Topic, TopicProgress.topic_id == Topic.id)
        .join(RoadmapSection, Topic.section_id == RoadmapSection.id)
        .where(
            RoadmapSection.roadmap_id == roadmap_id,
            Topic.is_published.is_(True),
            TopicProgress.user_id == user_id,
            TopicProgress.status == ProgressStatus.COMPLETED,
        )
    )
    return ProgressCounts(completed=completed or 0, total=total or 0)


def to_summary(counts: ProgressCounts) -> ProgressSummary:
    return ProgressSummary(
        completed_topics=counts.completed,
        total_topics=counts.total,
        progress_percent=counts.percent,
    )


async def update_topic_progress(
    session: AsyncSession, *, user_id: UUID, topic: Topic, status_value: str
) -> tuple[TopicProgress, ProgressSummary]:
    try:
        status = ProgressStatus(status_value)
    except ValueError:
        api_error(422, "invalid_progress_status", "Progress status is invalid")

    now = datetime.now(UTC)
    progress = await session.get(TopicProgress, (user_id, topic.id), with_for_update=True)
    if progress is None:
        progress = TopicProgress(user_id=user_id, topic_id=topic.id)
        session.add(progress)

    if status is not ProgressStatus.NOT_STARTED and progress.started_at is None:
        progress.started_at = now
    if status is ProgressStatus.COMPLETED:
        if progress.first_completed_at is None:
            progress.first_completed_at = now
        progress.last_completed_at = now
    progress.status = status
    progress.updated_at = now
    await session.flush()

    roadmap_id = topic.section.roadmap_id
    enrollment = await session.get(RoadmapEnrollment, (user_id, roadmap_id), with_for_update=True)
    if enrollment is None:
        enrollment = RoadmapEnrollment(user_id=user_id, roadmap_id=roadmap_id)
        session.add(enrollment)
    if status is not ProgressStatus.NOT_STARTED and enrollment.started_at is None:
        enrollment.started_at = now

    counts = await get_progress_counts(session, user_id, roadmap_id)
    if counts.total > 0 and counts.completed == counts.total:
        enrollment.completed_at = enrollment.completed_at or now
    else:
        enrollment.completed_at = None
    await session.commit()
    await session.refresh(progress)
    return progress, to_summary(counts)
