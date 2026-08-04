from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import api_error
from app.knowledge.models import KnowledgeEntry
from app.knowledge.service import get_public_entry
from app.media.models import ProtectedContentMedia
from app.media.presenters import content_media_read
from app.media.schemas import ContentMediaUploadFinalize, ProtectedContentMediaRead
from app.media.storage import StoredUpload
from app.roadmaps.models import RoadmapSection, Topic
from app.roadmaps.queries import get_topic_model, has_roadmap_access, roadmap_in_tracks
from app.tracks.access import accessible_track_ids
from app.users.models import User, UserRole


async def require_admin_knowledge_entry(
    session: AsyncSession,
    topic_id: UUID,
    entry_id: UUID,
) -> KnowledgeEntry:
    entry = await session.scalar(
        select(KnowledgeEntry).where(
            KnowledgeEntry.id == entry_id,
            KnowledgeEntry.topic_id == topic_id,
        )
    )
    if entry is None:
        api_error(404, "knowledge_entry_not_found", "Knowledge entry was not found")
    return entry


async def require_admin_roadmap_topic(
    session: AsyncSession,
    roadmap_id: UUID,
    section_id: UUID,
    topic_id: UUID,
) -> Topic:
    topic = await session.scalar(
        select(Topic)
        .join(RoadmapSection, RoadmapSection.id == Topic.section_id)
        .where(
            Topic.id == topic_id,
            Topic.section_id == section_id,
            RoadmapSection.roadmap_id == roadmap_id,
        )
    )
    if topic is None:
        api_error(404, "topic_not_found", "Topic was not found")
    return topic


async def attach_knowledge_media(
    session: AsyncSession,
    *,
    entry_id: UUID,
    uploaded_by_user_id: UUID,
    upload: StoredUpload,
    payload: ContentMediaUploadFinalize,
) -> ProtectedContentMediaRead:
    media = ProtectedContentMedia(
        knowledge_entry_id=entry_id,
        uploaded_by_user_id=uploaded_by_user_id,
        storage_key=upload.storage_key,
        filename=upload.filename,
        content_type=upload.content_type,
        size=upload.size,
        title=payload.title or None,
        position=payload.position,
    )
    session.add(media)
    await _commit_media(session)
    await session.refresh(media)
    return content_media_read(media)


async def attach_roadmap_media(
    session: AsyncSession,
    *,
    topic_id: UUID,
    uploaded_by_user_id: UUID,
    upload: StoredUpload,
    payload: ContentMediaUploadFinalize,
) -> ProtectedContentMediaRead:
    media = ProtectedContentMedia(
        roadmap_topic_id=topic_id,
        uploaded_by_user_id=uploaded_by_user_id,
        storage_key=upload.storage_key,
        filename=upload.filename,
        content_type=upload.content_type,
        size=upload.size,
        title=payload.title or None,
        position=payload.position,
    )
    session.add(media)
    await _commit_media(session)
    await session.refresh(media)
    return content_media_read(media)


async def _commit_media(session: AsyncSession) -> None:
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        api_error(
            409,
            "content_media_conflict",
            "The media attachment conflicts with existing content",
        )


async def _knowledge_media(
    session: AsyncSession,
    *,
    entry_id: UUID,
    media_id: UUID,
    lock: bool = False,
) -> ProtectedContentMedia:
    statement = select(ProtectedContentMedia).where(
        ProtectedContentMedia.id == media_id,
        ProtectedContentMedia.knowledge_entry_id == entry_id,
    )
    if lock:
        statement = statement.with_for_update()
    media = await session.scalar(statement)
    if media is None:
        api_error(404, "content_media_not_found", "Media attachment was not found")
    return media


async def _roadmap_media(
    session: AsyncSession,
    *,
    topic_id: UUID,
    media_id: UUID,
    lock: bool = False,
) -> ProtectedContentMedia:
    statement = select(ProtectedContentMedia).where(
        ProtectedContentMedia.id == media_id,
        ProtectedContentMedia.roadmap_topic_id == topic_id,
    )
    if lock:
        statement = statement.with_for_update()
    media = await session.scalar(statement)
    if media is None:
        api_error(404, "content_media_not_found", "Media attachment was not found")
    return media


async def delete_knowledge_media(
    session: AsyncSession,
    *,
    topic_id: UUID,
    entry_id: UUID,
    media_id: UUID,
) -> str:
    entry = await require_admin_knowledge_entry(session, topic_id, entry_id)
    media = await _knowledge_media(
        session,
        entry_id=entry.id,
        media_id=media_id,
        lock=True,
    )
    storage_key = media.storage_key
    await session.delete(media)
    await session.commit()
    return storage_key


async def delete_roadmap_media(
    session: AsyncSession,
    *,
    roadmap_id: UUID,
    section_id: UUID,
    topic_id: UUID,
    media_id: UUID,
) -> str:
    topic = await require_admin_roadmap_topic(
        session,
        roadmap_id,
        section_id,
        topic_id,
    )
    media = await _roadmap_media(
        session,
        topic_id=topic.id,
        media_id=media_id,
        lock=True,
    )
    storage_key = media.storage_key
    await session.delete(media)
    await session.commit()
    return storage_key


async def knowledge_media_for_user(
    session: AsyncSession,
    user: User,
    *,
    entry_slug: str,
    media_id: UUID,
) -> ProtectedContentMedia:
    entry = await get_public_entry(session, entry_slug, user)
    return await _knowledge_media(
        session,
        entry_id=entry.id,
        media_id=media_id,
    )


async def roadmap_media_for_user(
    session: AsyncSession,
    user: User,
    *,
    topic_id: UUID,
    media_id: UUID,
) -> ProtectedContentMedia:
    topic = await get_topic_model(session, topic_id)
    if topic is None or not await _can_view_roadmap(
        session,
        user,
        topic.section.roadmap_id,
    ):
        api_error(404, "topic_not_found", "Topic was not found")
    return await _roadmap_media(
        session,
        topic_id=topic.id,
        media_id=media_id,
    )


async def _can_view_roadmap(
    session: AsyncSession,
    user: User,
    roadmap_id: UUID,
) -> bool:
    if user.role is UserRole.ADMIN:
        return True
    if user.role is UserRole.MENTOR:
        return await roadmap_in_tracks(
            session,
            roadmap_id,
            await accessible_track_ids(session, user),
        )
    return await has_roadmap_access(session, user.id, roadmap_id)
