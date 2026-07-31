from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import api_error
from app.roadmaps.models import Roadmap, RoadmapEnrollment
from app.tracks.models import LearningTrack, LearningTrackEnrollment, LearningTrackRoadmap
from app.tracks.schemas import (
    AdminTrackMutation,
    AdminTrackOptions,
    AdminTrackRead,
    AdminTrackRoadmapRead,
    AdminTrackStudentOption,
)
from app.users.models import User, UserRole


def _roadmap_read(roadmap: Roadmap, position: int) -> AdminTrackRoadmapRead:
    return AdminTrackRoadmapRead(
        id=roadmap.id,
        slug=roadmap.slug,
        title=roadmap.title,
        is_published=roadmap.is_published,
        position=position,
    )


async def get_track_model(
    session: AsyncSession,
    track_id: UUID,
    *,
    lock: bool = False,
) -> LearningTrack:
    statement = select(LearningTrack).where(LearningTrack.id == track_id)
    if lock:
        statement = statement.with_for_update()
    track = await session.scalar(statement)
    if track is None:
        api_error(404, "track_not_found", "Learning track was not found")
    return track


async def get_published_track_by_slug(session: AsyncSession, slug: str) -> LearningTrack:
    track = await session.scalar(
        select(LearningTrack).where(
            LearningTrack.slug == slug,
            LearningTrack.is_published.is_(True),
        )
    )
    if track is None:
        api_error(404, "track_not_found", "Published learning track was not found")
    return track


async def track_roadmap_models(
    session: AsyncSession, track_id: UUID, *, published_only: bool = False
) -> list[Roadmap]:
    statement = (
        select(Roadmap)
        .join(LearningTrackRoadmap, LearningTrackRoadmap.roadmap_id == Roadmap.id)
        .where(LearningTrackRoadmap.track_id == track_id)
        .order_by(LearningTrackRoadmap.position, Roadmap.title)
    )
    if published_only:
        statement = statement.where(Roadmap.is_published.is_(True))
    return list(await session.scalars(statement))


async def _to_read(session: AsyncSession, track: LearningTrack) -> AdminTrackRead:
    rows = (
        await session.execute(
            select(Roadmap, LearningTrackRoadmap.position)
            .join(LearningTrackRoadmap, LearningTrackRoadmap.roadmap_id == Roadmap.id)
            .where(LearningTrackRoadmap.track_id == track.id)
            .order_by(LearningTrackRoadmap.position, Roadmap.title)
        )
    ).all()
    student_ids = list(
        await session.scalars(
            select(LearningTrackEnrollment.user_id)
            .where(LearningTrackEnrollment.track_id == track.id)
            .order_by(LearningTrackEnrollment.granted_at)
        )
    )
    return AdminTrackRead(
        id=track.id,
        slug=track.slug,
        title=track.title,
        description=track.description,
        position=track.position,
        is_published=track.is_published,
        roadmaps=[_roadmap_read(roadmap, position) for roadmap, position in rows],
        student_ids=student_ids,
    )


async def list_admin_tracks(session: AsyncSession) -> list[AdminTrackRead]:
    tracks = list(
        await session.scalars(
            select(LearningTrack).order_by(LearningTrack.position, LearningTrack.title)
        )
    )
    return [await _to_read(session, track) for track in tracks]


async def get_admin_track(session: AsyncSession, track_id: UUID) -> AdminTrackRead:
    return await _to_read(session, await get_track_model(session, track_id))


async def get_admin_track_options(session: AsyncSession) -> AdminTrackOptions:
    roadmaps = list(
        await session.scalars(select(Roadmap).order_by(Roadmap.position, Roadmap.title))
    )
    students = list(
        await session.scalars(
            select(User).where(User.role == UserRole.STUDENT).order_by(User.first_name)
        )
    )
    return AdminTrackOptions(
        roadmaps=[_roadmap_read(roadmap, roadmap.position) for roadmap in roadmaps],
        students=[
            AdminTrackStudentOption(
                id=student.id,
                first_name=student.first_name,
                last_name=student.last_name,
                email=student.email,
                telegram_id=student.telegram_id,
            )
            for student in students
        ],
    )


async def _validate_track_payload(
    session: AsyncSession,
    payload: AdminTrackMutation,
    *,
    track_id: UUID | None,
) -> None:
    slug_conflict = select(LearningTrack.id).where(LearningTrack.slug == payload.slug)
    if track_id is not None:
        slug_conflict = slug_conflict.where(LearningTrack.id != track_id)
    if await session.scalar(slug_conflict) is not None:
        api_error(409, "track_slug_conflict", "Learning track slug is already in use")

    if payload.roadmap_ids:
        roadmap_count = await session.scalar(
            select(func.count(Roadmap.id)).where(Roadmap.id.in_(payload.roadmap_ids))
        )
        if roadmap_count != len(payload.roadmap_ids):
            api_error(422, "invalid_track_roadmaps", "One or more roadmaps do not exist")


async def ensure_track_access(
    session: AsyncSession,
    *,
    user_id: UUID,
    track_id: UUID,
) -> bool:
    now = datetime.now(UTC)
    created_id = await session.scalar(
        insert(LearningTrackEnrollment)
        .values(user_id=user_id, track_id=track_id, granted_at=now)
        .on_conflict_do_nothing(
            index_elements=[
                LearningTrackEnrollment.user_id,
                LearningTrackEnrollment.track_id,
            ]
        )
        .returning(LearningTrackEnrollment.user_id)
    )
    roadmap_ids = list(
        await session.scalars(
            select(LearningTrackRoadmap.roadmap_id).where(LearningTrackRoadmap.track_id == track_id)
        )
    )
    for roadmap_id in roadmap_ids:
        await session.execute(
            insert(RoadmapEnrollment)
            .values(user_id=user_id, roadmap_id=roadmap_id)
            .on_conflict_do_nothing(
                index_elements=[RoadmapEnrollment.user_id, RoadmapEnrollment.roadmap_id]
            )
        )
    return created_id is not None


async def _sync_track_roadmaps(
    session: AsyncSession, track_id: UUID, roadmap_ids: list[UUID]
) -> None:
    await session.execute(
        delete(LearningTrackRoadmap).where(LearningTrackRoadmap.track_id == track_id)
    )
    session.add_all(
        LearningTrackRoadmap(track_id=track_id, roadmap_id=roadmap_id, position=position)
        for position, roadmap_id in enumerate(roadmap_ids)
    )
    await session.flush()
    student_ids = list(
        await session.scalars(
            select(LearningTrackEnrollment.user_id).where(
                LearningTrackEnrollment.track_id == track_id
            )
        )
    )
    for student_id in student_ids:
        await ensure_track_access(session, user_id=student_id, track_id=track_id)


async def create_track(session: AsyncSession, payload: AdminTrackMutation) -> AdminTrackRead:
    await _validate_track_payload(session, payload, track_id=None)
    track = LearningTrack(
        slug=payload.slug,
        title=payload.title,
        description=payload.description,
        position=payload.position,
        is_published=payload.is_published,
    )
    session.add(track)
    try:
        await session.flush()
        await _sync_track_roadmaps(session, track.id, payload.roadmap_ids)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        api_error(409, "track_conflict", "Learning track contains conflicting values")
    return await _to_read(session, track)


async def update_track(
    session: AsyncSession, track_id: UUID, payload: AdminTrackMutation
) -> AdminTrackRead:
    track = await get_track_model(session, track_id, lock=True)
    await _validate_track_payload(session, payload, track_id=track_id)
    track.slug = payload.slug
    track.title = payload.title
    track.description = payload.description
    track.position = payload.position
    track.is_published = payload.is_published
    try:
        await _sync_track_roadmaps(session, track.id, payload.roadmap_ids)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        api_error(409, "track_conflict", "Learning track contains conflicting values")
    return await _to_read(session, track)


async def grant_track_access(session: AsyncSession, track_id: UUID, student_id: UUID) -> bool:
    await get_track_model(session, track_id)
    student = await session.get(User, student_id)
    if student is None or student.role is not UserRole.STUDENT:
        api_error(404, "student_not_found", "Student was not found")
    granted = await ensure_track_access(session, user_id=student_id, track_id=track_id)
    await session.commit()
    return granted


async def revoke_track_access(session: AsyncSession, track_id: UUID, student_id: UUID) -> None:
    await get_track_model(session, track_id)
    await session.execute(
        delete(LearningTrackEnrollment).where(
            LearningTrackEnrollment.track_id == track_id,
            LearningTrackEnrollment.user_id == student_id,
        )
    )
    await session.commit()
