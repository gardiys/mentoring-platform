from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import api_error
from app.roadmaps.admin_schemas import (
    AdminRoadmapCreate,
    AdminRoadmapOutline,
    AdminRoadmapRead,
    AdminRoadmapSettingsMutation,
    AdminRoadmapSummary,
    AdminRoadmapUpdate,
    AdminSectionMutation,
    AdminSectionOutline,
    AdminSectionRead,
    AdminTopicCreate,
    AdminTopicRead,
    AdminTopicSummary,
)
from app.roadmaps.models import Roadmap, RoadmapSection, Topic


def _to_read(roadmap: Roadmap) -> AdminRoadmapRead:
    return AdminRoadmapRead(
        id=roadmap.id,
        slug=roadmap.slug,
        title=roadmap.title,
        description=roadmap.description,
        position=roadmap.position,
        is_published=roadmap.is_published,
        sections=[
            AdminSectionRead(
                id=section.id,
                title=section.title,
                description=section.description,
                position=section.position,
                duration_days=section.duration_days,
                topics=[
                    AdminTopicRead(
                        id=topic.id,
                        slug=topic.slug,
                        title=topic.title,
                        description=topic.description,
                        content_markdown=topic.content_markdown,
                        position=topic.position,
                        estimated_minutes=topic.estimated_minutes,
                        is_published=topic.is_published,
                    )
                    for topic in sorted(section.topics, key=lambda item: item.position)
                ],
            )
            for section in sorted(roadmap.sections, key=lambda item: item.position)
        ],
    )


async def get_admin_roadmap_model(
    session: AsyncSession, roadmap_id: UUID, *, lock: bool = False
) -> Roadmap:
    statement = (
        select(Roadmap)
        .where(Roadmap.id == roadmap_id)
        .options(selectinload(Roadmap.sections).selectinload(RoadmapSection.topics))
    )
    if lock:
        statement = statement.with_for_update()
    roadmap = cast(Roadmap | None, await session.scalar(statement))
    if roadmap is None:
        api_error(404, "roadmap_not_found", "Roadmap was not found")
    return roadmap


async def list_admin_roadmaps(session: AsyncSession) -> list[AdminRoadmapRead]:
    roadmaps = (
        await session.scalars(
            select(Roadmap)
            .order_by(Roadmap.position, Roadmap.title)
            .options(selectinload(Roadmap.sections).selectinload(RoadmapSection.topics))
        )
    ).all()
    return [_to_read(roadmap) for roadmap in roadmaps]


async def get_admin_roadmap(session: AsyncSession, roadmap_id: UUID) -> AdminRoadmapRead:
    return _to_read(await get_admin_roadmap_model(session, roadmap_id))


async def list_admin_roadmap_summaries(
    session: AsyncSession,
) -> list[AdminRoadmapSummary]:
    rows = (
        await session.execute(
            select(
                Roadmap,
                func.count(func.distinct(RoadmapSection.id)),
                func.count(func.distinct(Topic.id)),
            )
            .outerjoin(RoadmapSection, RoadmapSection.roadmap_id == Roadmap.id)
            .outerjoin(Topic, Topic.section_id == RoadmapSection.id)
            .group_by(Roadmap.id)
            .order_by(Roadmap.position, Roadmap.title)
        )
    ).all()
    return [
        AdminRoadmapSummary(
            id=roadmap.id,
            slug=roadmap.slug,
            title=roadmap.title,
            description=roadmap.description,
            position=roadmap.position,
            is_published=roadmap.is_published,
            section_count=section_count,
            topic_count=topic_count,
        )
        for roadmap, section_count, topic_count in rows
    ]


async def get_admin_roadmap_outline(session: AsyncSession, roadmap_id: UUID) -> AdminRoadmapOutline:
    roadmap = await session.get(Roadmap, roadmap_id)
    if roadmap is None:
        api_error(404, "roadmap_not_found", "Roadmap was not found")
    sections = list(
        await session.scalars(
            select(RoadmapSection)
            .where(RoadmapSection.roadmap_id == roadmap_id)
            .order_by(RoadmapSection.position, RoadmapSection.id)
        )
    )
    topic_rows = (
        await session.execute(
            select(
                Topic.id,
                Topic.section_id,
                Topic.slug,
                Topic.title,
                Topic.position,
                Topic.estimated_minutes,
                Topic.is_published,
            )
            .join(RoadmapSection, RoadmapSection.id == Topic.section_id)
            .where(RoadmapSection.roadmap_id == roadmap_id)
            .order_by(Topic.position, Topic.id)
        )
    ).all()
    topics_by_section: dict[UUID, list[AdminTopicSummary]] = {}
    for topic_id, section_id, slug, title, position, estimated_minutes, is_published in topic_rows:
        topics_by_section.setdefault(section_id, []).append(
            AdminTopicSummary(
                id=topic_id,
                slug=slug,
                title=title,
                position=position,
                estimated_minutes=estimated_minutes,
                is_published=is_published,
            )
        )
    return AdminRoadmapOutline(
        id=roadmap.id,
        slug=roadmap.slug,
        title=roadmap.title,
        description=roadmap.description,
        position=roadmap.position,
        is_published=roadmap.is_published,
        sections=[
            AdminSectionOutline(
                id=section.id,
                title=section.title,
                description=section.description,
                position=section.position,
                duration_days=section.duration_days,
                topics=topics_by_section.get(section.id, []),
            )
            for section in sections
        ],
    )


async def update_roadmap_settings(
    session: AsyncSession,
    roadmap_id: UUID,
    payload: AdminRoadmapSettingsMutation,
) -> AdminRoadmapOutline:
    roadmap = await session.get(Roadmap, roadmap_id, with_for_update=True)
    if roadmap is None:
        api_error(404, "roadmap_not_found", "Roadmap was not found")
    conflict = select(Roadmap.id).where(Roadmap.slug == payload.slug, Roadmap.id != roadmap_id)
    if await session.scalar(conflict) is not None:
        api_error(409, "roadmap_slug_conflict", "Roadmap slug is already in use")
    roadmap.slug = payload.slug
    roadmap.title = payload.title
    roadmap.description = payload.description
    roadmap.position = payload.position
    roadmap.is_published = payload.is_published
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        api_error(409, "roadmap_conflict", "Roadmap contains conflicting values")
    return await get_admin_roadmap_outline(session, roadmap_id)


async def get_admin_section(
    session: AsyncSession, roadmap_id: UUID, section_id: UUID
) -> AdminSectionOutline:
    outline = await get_admin_roadmap_outline(session, roadmap_id)
    section = next((item for item in outline.sections if item.id == section_id), None)
    if section is None:
        api_error(404, "roadmap_section_not_found", "Roadmap section was not found")
    return section


async def create_admin_section(
    session: AsyncSession, roadmap_id: UUID, payload: AdminSectionMutation
) -> AdminSectionOutline:
    if await session.get(Roadmap, roadmap_id) is None:
        api_error(404, "roadmap_not_found", "Roadmap was not found")
    section = RoadmapSection(roadmap_id=roadmap_id)
    _apply_section(section, payload)
    session.add(section)
    await session.commit()
    await session.refresh(section)
    return await get_admin_section(session, roadmap_id, section.id)


async def update_admin_section(
    session: AsyncSession,
    roadmap_id: UUID,
    section_id: UUID,
    payload: AdminSectionMutation,
) -> AdminSectionOutline:
    section = await session.get(RoadmapSection, section_id, with_for_update=True)
    if section is None or section.roadmap_id != roadmap_id:
        api_error(404, "roadmap_section_not_found", "Roadmap section was not found")
    _apply_section(section, payload)
    await session.commit()
    return await get_admin_section(session, roadmap_id, section_id)


def _apply_section(section: RoadmapSection, payload: AdminSectionMutation) -> None:
    section.title = payload.title
    section.description = payload.description
    section.position = payload.position
    section.duration_days = payload.duration_days


async def get_admin_topic(
    session: AsyncSession, roadmap_id: UUID, section_id: UUID, topic_id: UUID
) -> AdminTopicRead:
    topic = await session.get(Topic, topic_id)
    section = await session.get(RoadmapSection, section_id)
    if (
        topic is None
        or section is None
        or topic.section_id != section_id
        or section.roadmap_id != roadmap_id
    ):
        api_error(404, "topic_not_found", "Topic was not found")
    return _topic_read(topic)


async def _validate_topic_slug(
    session: AsyncSession, slug: str, topic_id: UUID | None = None
) -> None:
    statement = select(Topic.id).where(Topic.slug == slug)
    if topic_id is not None:
        statement = statement.where(Topic.id != topic_id)
    if await session.scalar(statement) is not None:
        api_error(409, "topic_slug_conflict", "Topic slug is already in use")


def _topic_read(topic: Topic) -> AdminTopicRead:
    return AdminTopicRead(
        id=topic.id,
        slug=topic.slug,
        title=topic.title,
        description=topic.description,
        content_markdown=topic.content_markdown,
        position=topic.position,
        estimated_minutes=topic.estimated_minutes,
        is_published=topic.is_published,
    )


def _apply_topic(topic: Topic, payload: AdminTopicCreate) -> None:
    topic.slug = payload.slug
    topic.title = payload.title
    topic.description = payload.description
    topic.content_markdown = payload.content_markdown
    topic.position = payload.position
    topic.estimated_minutes = payload.estimated_minutes
    topic.is_published = payload.is_published


async def create_admin_topic(
    session: AsyncSession,
    roadmap_id: UUID,
    section_id: UUID,
    payload: AdminTopicCreate,
) -> AdminTopicRead:
    section = await session.get(RoadmapSection, section_id)
    if section is None or section.roadmap_id != roadmap_id:
        api_error(404, "roadmap_section_not_found", "Roadmap section was not found")
    await _validate_topic_slug(session, payload.slug)
    topic = Topic(section_id=section_id)
    _apply_topic(topic, payload)
    session.add(topic)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        api_error(409, "topic_conflict", "Topic contains conflicting values")
    await session.refresh(topic)
    return _topic_read(topic)


async def update_admin_topic(
    session: AsyncSession,
    roadmap_id: UUID,
    section_id: UUID,
    topic_id: UUID,
    payload: AdminTopicCreate,
) -> AdminTopicRead:
    topic = await session.get(Topic, topic_id, with_for_update=True)
    section = await session.get(RoadmapSection, section_id)
    if (
        topic is None
        or section is None
        or topic.section_id != section_id
        or section.roadmap_id != roadmap_id
    ):
        api_error(404, "topic_not_found", "Topic was not found")
    await _validate_topic_slug(session, payload.slug, topic_id)
    _apply_topic(topic, payload)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        api_error(409, "topic_conflict", "Topic contains conflicting values")
    await session.refresh(topic)
    return _topic_read(topic)


async def _validate_unique_slugs(
    session: AsyncSession,
    *,
    roadmap_id: UUID | None,
    roadmap_slug: str,
    topic_slugs: list[str],
) -> None:
    roadmap_conflict = select(Roadmap.id).where(Roadmap.slug == roadmap_slug)
    if roadmap_id is not None:
        roadmap_conflict = roadmap_conflict.where(Roadmap.id != roadmap_id)
    if await session.scalar(roadmap_conflict) is not None:
        api_error(409, "roadmap_slug_conflict", "Roadmap slug is already in use")

    if len(topic_slugs) != len(set(topic_slugs)):
        api_error(409, "topic_slug_conflict", "Topic slugs must be unique")
    topic_conflict = select(Topic.slug).where(Topic.slug.in_(topic_slugs))
    if roadmap_id is not None:
        topic_conflict = topic_conflict.join(
            RoadmapSection, Topic.section_id == RoadmapSection.id
        ).where(RoadmapSection.roadmap_id != roadmap_id)
    if await session.scalar(topic_conflict.limit(1)) is not None:
        api_error(409, "topic_slug_conflict", "Topic slug is already in use")


async def create_roadmap(session: AsyncSession, payload: AdminRoadmapCreate) -> AdminRoadmapRead:
    topic_slugs = [topic.slug for section in payload.sections for topic in section.topics]
    await _validate_unique_slugs(
        session,
        roadmap_id=None,
        roadmap_slug=payload.slug,
        topic_slugs=topic_slugs,
    )

    roadmap = Roadmap(
        slug=payload.slug,
        title=payload.title,
        description=payload.description,
        position=payload.position,
        is_published=payload.is_published,
    )
    for section_payload in payload.sections:
        section = RoadmapSection(
            title=section_payload.title,
            description=section_payload.description,
            position=section_payload.position,
            duration_days=section_payload.duration_days,
        )
        for topic_payload in section_payload.topics:
            section.topics.append(
                Topic(
                    slug=topic_payload.slug,
                    title=topic_payload.title,
                    description=topic_payload.description,
                    content_markdown=topic_payload.content_markdown,
                    position=topic_payload.position,
                    estimated_minutes=topic_payload.estimated_minutes,
                    is_published=topic_payload.is_published,
                )
            )
        roadmap.sections.append(section)
    session.add(roadmap)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        api_error(409, "roadmap_conflict", "Roadmap contains conflicting values")
    return _to_read(roadmap)


async def update_roadmap(
    session: AsyncSession, roadmap_id: UUID, payload: AdminRoadmapUpdate
) -> AdminRoadmapRead:
    roadmap = await get_admin_roadmap_model(session, roadmap_id, lock=True)
    topic_slugs = [topic.slug for section in payload.sections for topic in section.topics]
    await _validate_unique_slugs(
        session,
        roadmap_id=roadmap_id,
        roadmap_slug=payload.slug,
        topic_slugs=topic_slugs,
    )

    existing_sections = {section.id: section for section in roadmap.sections}
    supplied_section_ids = [section.id for section in payload.sections if section.id is not None]
    if len(supplied_section_ids) != len(set(supplied_section_ids)):
        api_error(422, "invalid_roadmap_structure", "Section IDs must be unique")
    if set(supplied_section_ids) != set(existing_sections):
        api_error(
            409,
            "roadmap_structure_removal_not_supported",
            "Existing sections cannot be removed in this editor",
        )

    roadmap.slug = payload.slug
    roadmap.title = payload.title
    roadmap.description = payload.description
    roadmap.position = payload.position
    roadmap.is_published = payload.is_published

    for section_payload in payload.sections:
        if section_payload.id is None:
            if any(topic.id is not None for topic in section_payload.topics):
                api_error(422, "invalid_roadmap_structure", "New sections need new topics")
            section = RoadmapSection()
            roadmap.sections.append(section)
        else:
            section = existing_sections[section_payload.id]

        existing_topics = {topic.id: topic for topic in section.topics}
        supplied_topic_ids = [topic.id for topic in section_payload.topics if topic.id is not None]
        if len(supplied_topic_ids) != len(set(supplied_topic_ids)):
            api_error(422, "invalid_roadmap_structure", "Topic IDs must be unique")
        if set(supplied_topic_ids) != set(existing_topics):
            api_error(
                409,
                "roadmap_structure_removal_not_supported",
                "Existing topics cannot be removed or moved in this editor",
            )

        section.title = section_payload.title
        section.description = section_payload.description
        section.position = section_payload.position
        section.duration_days = section_payload.duration_days
        for topic_payload in section_payload.topics:
            if topic_payload.id is None:
                topic = Topic()
                section.topics.append(topic)
            else:
                topic = existing_topics[topic_payload.id]
            topic.slug = topic_payload.slug
            topic.title = topic_payload.title
            topic.description = topic_payload.description
            topic.content_markdown = topic_payload.content_markdown
            topic.position = topic_payload.position
            topic.estimated_minutes = topic_payload.estimated_minutes
            topic.is_published = topic_payload.is_published

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        api_error(409, "roadmap_conflict", "Roadmap contains conflicting values")
    return _to_read(roadmap)
