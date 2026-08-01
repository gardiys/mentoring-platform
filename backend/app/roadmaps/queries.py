from datetime import UTC, date, datetime, time, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.progress.models import ProgressStatus, TopicProgress
from app.progress.service import get_progress_counts
from app.roadmaps.models import Roadmap, RoadmapEnrollment, RoadmapSection, Topic
from app.roadmaps.schemas import (
    RoadmapDetail,
    RoadmapListItem,
    SectionRead,
    TopicContext,
    TopicDetail,
    TopicListItem,
)
from app.tracks.models import LearningTrack, LearningTrackEnrollment, LearningTrackRoadmap


async def list_roadmaps(
    session: AsyncSession,
    user_id: UUID,
    *,
    include_all_published: bool = False,
    track_ids: set[UUID] | None = None,
    require_enrollment: bool = True,
) -> list[RoadmapListItem]:
    statement = select(Roadmap).where(Roadmap.is_published.is_(True))
    if include_all_published:
        statement = statement.options(selectinload(Roadmap.sections)).order_by(Roadmap.position)
    elif not require_enrollment:
        statement = (
            statement.join(LearningTrackRoadmap, LearningTrackRoadmap.roadmap_id == Roadmap.id)
            .where(LearningTrackRoadmap.track_id.in_(track_ids or set()))
            .options(selectinload(Roadmap.sections))
            .distinct()
            .order_by(Roadmap.position)
        )
    else:
        statement = (
            statement.join(LearningTrackRoadmap, LearningTrackRoadmap.roadmap_id == Roadmap.id)
            .join(
                LearningTrackEnrollment,
                LearningTrackEnrollment.track_id == LearningTrackRoadmap.track_id,
            )
            .join(LearningTrack, LearningTrack.id == LearningTrackRoadmap.track_id)
            .where(
                LearningTrack.is_published.is_(True),
                LearningTrackEnrollment.user_id == user_id,
            )
            .options(selectinload(Roadmap.sections))
            .distinct()
            .order_by(Roadmap.position)
        )
        if track_ids is not None:
            statement = statement.where(LearningTrackRoadmap.track_id.in_(track_ids))
    roadmaps = (await session.scalars(statement)).all()
    result: list[RoadmapListItem] = []
    for roadmap in roadmaps:
        enrollment = await session.get(RoadmapEnrollment, (user_id, roadmap.id))
        counts = await get_progress_counts(session, user_id, roadmap.id)
        total_duration_days = sum(section.duration_days or 0 for section in roadmap.sections)
        result.append(
            RoadmapListItem(
                id=roadmap.id,
                slug=roadmap.slug,
                title=roadmap.title,
                description=roadmap.description,
                completed_topics=counts.completed,
                total_topics=counts.total,
                progress_percent=counts.percent,
                started_at=enrollment.started_at if enrollment else None,
                completed_at=enrollment.completed_at if enrollment else None,
                total_duration_days=total_duration_days,
                planned_completion_at=(
                    enrollment.started_at + timedelta(days=total_duration_days)
                    if enrollment is not None
                    and enrollment.started_at is not None
                    and total_duration_days > 0
                    else None
                ),
            )
        )
    return result


async def get_roadmap_model(session: AsyncSession, slug: str) -> Roadmap | None:
    return cast(
        Roadmap | None,
        await session.scalar(
            select(Roadmap)
            .where(Roadmap.slug == slug, Roadmap.is_published.is_(True))
            .options(selectinload(Roadmap.sections).selectinload(RoadmapSection.topics))
        ),
    )


async def has_roadmap_access(session: AsyncSession, user_id: UUID, roadmap_id: UUID) -> bool:
    track_id = await session.scalar(
        select(LearningTrackRoadmap.track_id)
        .join(
            LearningTrackEnrollment,
            LearningTrackEnrollment.track_id == LearningTrackRoadmap.track_id,
        )
        .join(LearningTrack, LearningTrack.id == LearningTrackRoadmap.track_id)
        .where(
            LearningTrackRoadmap.roadmap_id == roadmap_id,
            LearningTrackEnrollment.user_id == user_id,
            LearningTrack.is_published.is_(True),
        )
        .limit(1)
    )
    return track_id is not None


async def roadmap_in_tracks(session: AsyncSession, roadmap_id: UUID, track_ids: set[UUID]) -> bool:
    if not track_ids:
        return False
    return (
        await session.scalar(
            select(LearningTrackRoadmap.roadmap_id)
            .where(
                LearningTrackRoadmap.roadmap_id == roadmap_id,
                LearningTrackRoadmap.track_id.in_(track_ids),
            )
            .limit(1)
        )
        is not None
    )


async def build_roadmap_detail(
    session: AsyncSession, roadmap: Roadmap, user_id: UUID
) -> RoadmapDetail:
    topic_ids = [topic.id for section in roadmap.sections for topic in section.topics]
    progress_by_topic: dict[UUID, TopicProgress] = {}
    if topic_ids:
        progresses = (
            await session.scalars(
                select(TopicProgress).where(
                    TopicProgress.user_id == user_id, TopicProgress.topic_id.in_(topic_ids)
                )
            )
        ).all()
        progress_by_topic = {item.topic_id: item for item in progresses}

    sections: list[SectionRead] = []
    enrollment = await session.get(RoadmapEnrollment, (user_id, roadmap.id))
    cumulative_duration_days = 0
    for section in roadmap.sections:
        topics: list[TopicListItem] = []
        for topic in section.topics:
            if not topic.is_published:
                continue
            progress = progress_by_topic.get(topic.id)
            topics.append(
                TopicListItem(
                    id=topic.id,
                    slug=topic.slug,
                    title=topic.title,
                    description=topic.description,
                    estimated_minutes=topic.estimated_minutes,
                    status=progress.status if progress else ProgressStatus.NOT_STARTED,
                    first_completed_at=progress.first_completed_at if progress else None,
                    last_completed_at=progress.last_completed_at if progress else None,
                )
            )
        cumulative_duration_days += section.duration_days or 0
        sections.append(
            SectionRead(
                id=section.id,
                title=section.title,
                description=section.description,
                duration_days=section.duration_days,
                deadline_at=(
                    enrollment.started_at + timedelta(days=cumulative_duration_days)
                    if enrollment is not None
                    and enrollment.started_at is not None
                    and section.duration_days is not None
                    else None
                ),
                topics=topics,
            )
        )

    counts = await get_progress_counts(session, user_id, roadmap.id)
    return RoadmapDetail(
        id=roadmap.id,
        slug=roadmap.slug,
        title=roadmap.title,
        description=roadmap.description,
        sections=sections,
        completed_topics=counts.completed,
        total_topics=counts.total,
        progress_percent=counts.percent,
        started_at=enrollment.started_at if enrollment else None,
        completed_at=enrollment.completed_at if enrollment else None,
        total_duration_days=cumulative_duration_days,
        planned_completion_at=(
            enrollment.started_at + timedelta(days=cumulative_duration_days)
            if enrollment is not None
            and enrollment.started_at is not None
            and cumulative_duration_days > 0
            else None
        ),
    )


async def start_roadmap(
    session: AsyncSession,
    *,
    user_id: UUID,
    roadmap_id: UUID,
    started_on: date | None = None,
) -> None:
    enrollment = await session.get(RoadmapEnrollment, (user_id, roadmap_id), with_for_update=True)
    if enrollment is None:
        enrollment = RoadmapEnrollment(user_id=user_id, roadmap_id=roadmap_id)
        session.add(enrollment)
    if enrollment.started_at is None:
        enrollment.started_at = (
            datetime.now(UTC)
            if started_on is None
            else datetime.combine(started_on, time.min, tzinfo=UTC)
        )
    await session.commit()


async def get_topic_model(session: AsyncSession, topic_id: UUID) -> Topic | None:
    return cast(
        Topic | None,
        await session.scalar(
            select(Topic)
            .where(Topic.id == topic_id, Topic.is_published.is_(True))
            .options(selectinload(Topic.section).selectinload(RoadmapSection.roadmap))
        ),
    )


async def build_topic_detail(session: AsyncSession, topic: Topic, user_id: UUID) -> TopicDetail:
    progress = await session.get(TopicProgress, (user_id, topic.id))
    roadmap = topic.section.roadmap
    return TopicDetail(
        id=topic.id,
        slug=topic.slug,
        title=topic.title,
        description=topic.description,
        content_markdown=topic.content_markdown,
        estimated_minutes=topic.estimated_minutes,
        roadmap=TopicContext(id=roadmap.id, slug=roadmap.slug, title=roadmap.title),
        section=TopicContext(id=topic.section.id, title=topic.section.title),
        status=progress.status if progress else ProgressStatus.NOT_STARTED,
        started_at=progress.started_at if progress else None,
        first_completed_at=progress.first_completed_at if progress else None,
        last_completed_at=progress.last_completed_at if progress else None,
    )
