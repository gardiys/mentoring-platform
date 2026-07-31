from typing import cast
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import api_error
from app.knowledge.models import KnowledgeEntry, KnowledgeEntryKind, KnowledgeTopic
from app.knowledge.schemas import (
    AdminKnowledgeEntryMutation,
    AdminKnowledgeEntryRead,
    AdminKnowledgeEntrySummary,
    AdminKnowledgeTopicMutation,
    AdminKnowledgeTopicOutline,
    AdminKnowledgeTopicRead,
    AdminKnowledgeTopicSettingsMutation,
    AdminKnowledgeTopicSummary,
    KnowledgeEntryDetail,
    KnowledgeEntryListItem,
    KnowledgeSearchResult,
    KnowledgeTopicContext,
    KnowledgeTopicDetail,
    KnowledgeTopicListItem,
)


def _entry_list_item(entry: KnowledgeEntry) -> KnowledgeEntryListItem:
    return KnowledgeEntryListItem(
        id=entry.id,
        kind=entry.kind,
        slug=entry.slug,
        title=entry.title,
        summary=entry.summary,
    )


def _topic_context(topic: KnowledgeTopic) -> KnowledgeTopicContext:
    return KnowledgeTopicContext(id=topic.id, slug=topic.slug, title=topic.title)


async def list_public_topics(session: AsyncSession) -> list[KnowledgeTopicListItem]:
    topics = list(
        await session.scalars(
            select(KnowledgeTopic)
            .where(KnowledgeTopic.is_published.is_(True))
            .order_by(KnowledgeTopic.position, KnowledgeTopic.title)
            .options(selectinload(KnowledgeTopic.entries))
        )
    )
    return [
        KnowledgeTopicListItem(
            id=topic.id,
            slug=topic.slug,
            title=topic.title,
            description=topic.description,
            article_count=sum(
                entry.is_published and entry.kind is KnowledgeEntryKind.ARTICLE
                for entry in topic.entries
            ),
            question_count=sum(
                entry.is_published and entry.kind is KnowledgeEntryKind.QUESTION
                for entry in topic.entries
            ),
        )
        for topic in topics
    ]


async def get_public_topic(session: AsyncSession, slug: str) -> KnowledgeTopicDetail:
    topic = await session.scalar(
        select(KnowledgeTopic)
        .where(
            KnowledgeTopic.slug == slug,
            KnowledgeTopic.is_published.is_(True),
        )
        .options(selectinload(KnowledgeTopic.entries))
    )
    if topic is None:
        api_error(404, "knowledge_topic_not_found", "Knowledge topic was not found")
    entries = [
        _entry_list_item(entry)
        for entry in sorted(topic.entries, key=lambda item: item.position)
        if entry.is_published
    ]
    return KnowledgeTopicDetail(
        id=topic.id,
        slug=topic.slug,
        title=topic.title,
        description=topic.description,
        entries=entries,
    )


async def get_public_entry(session: AsyncSession, slug: str) -> KnowledgeEntryDetail:
    entry = await session.scalar(
        select(KnowledgeEntry)
        .join(KnowledgeTopic, KnowledgeTopic.id == KnowledgeEntry.topic_id)
        .where(
            KnowledgeEntry.slug == slug,
            KnowledgeEntry.is_published.is_(True),
            KnowledgeTopic.is_published.is_(True),
        )
        .options(selectinload(KnowledgeEntry.topic))
    )
    if entry is None:
        api_error(404, "knowledge_entry_not_found", "Knowledge entry was not found")
    return KnowledgeEntryDetail(
        **_entry_list_item(entry).model_dump(),
        content_markdown=entry.content_markdown,
        topic=_topic_context(entry.topic),
        updated_at=entry.updated_at,
    )


async def search_public_entries(
    session: AsyncSession, query_text: str, limit: int
) -> list[KnowledgeSearchResult]:
    search_query = func.websearch_to_tsquery("russian", query_text)
    rank = func.ts_rank_cd(KnowledgeEntry.search_vector, search_query)
    excerpt = func.left(
        func.regexp_replace(KnowledgeEntry.content_markdown, r"[#*`_>\[\]()]", "", "g"),
        280,
    )
    rows = (
        await session.execute(
            select(KnowledgeEntry, KnowledgeTopic, rank.label("rank"), excerpt.label("excerpt"))
            .join(KnowledgeTopic, KnowledgeTopic.id == KnowledgeEntry.topic_id)
            .where(
                KnowledgeEntry.is_published.is_(True),
                KnowledgeTopic.is_published.is_(True),
                KnowledgeEntry.search_vector.op("@@")(search_query),
            )
            .order_by(desc("rank"), KnowledgeEntry.title)
            .limit(limit)
        )
    ).all()
    return [
        KnowledgeSearchResult(
            **_entry_list_item(entry).model_dump(),
            topic=_topic_context(topic),
            excerpt=entry_excerpt.strip(),
            rank=float(entry_rank),
        )
        for entry, topic, entry_rank, entry_excerpt in rows
    ]


def _admin_entry_read(entry: KnowledgeEntry) -> AdminKnowledgeEntryRead:
    return AdminKnowledgeEntryRead(
        id=entry.id,
        kind=entry.kind,
        slug=entry.slug,
        title=entry.title,
        summary=entry.summary,
        content_markdown=entry.content_markdown,
        position=entry.position,
        is_published=entry.is_published,
        updated_at=entry.updated_at,
    )


def _admin_topic_read(topic: KnowledgeTopic) -> AdminKnowledgeTopicRead:
    return AdminKnowledgeTopicRead(
        id=topic.id,
        slug=topic.slug,
        title=topic.title,
        description=topic.description,
        position=topic.position,
        is_published=topic.is_published,
        entries=[
            _admin_entry_read(entry)
            for entry in sorted(topic.entries, key=lambda item: item.position)
        ],
    )


async def _admin_topic_model(
    session: AsyncSession, topic_id: UUID, *, lock: bool = False
) -> KnowledgeTopic:
    statement = (
        select(KnowledgeTopic)
        .where(KnowledgeTopic.id == topic_id)
        .options(selectinload(KnowledgeTopic.entries))
    )
    if lock:
        statement = statement.with_for_update()
    topic = cast(KnowledgeTopic | None, await session.scalar(statement))
    if topic is None:
        api_error(404, "knowledge_topic_not_found", "Knowledge topic was not found")
    return topic


async def list_admin_topics(session: AsyncSession) -> list[AdminKnowledgeTopicRead]:
    topics = list(
        await session.scalars(
            select(KnowledgeTopic)
            .order_by(KnowledgeTopic.position, KnowledgeTopic.title)
            .options(selectinload(KnowledgeTopic.entries))
        )
    )
    return [_admin_topic_read(topic) for topic in topics]


async def get_admin_topic(session: AsyncSession, topic_id: UUID) -> AdminKnowledgeTopicRead:
    return _admin_topic_read(await _admin_topic_model(session, topic_id))


async def list_admin_topic_summaries(
    session: AsyncSession,
) -> list[AdminKnowledgeTopicSummary]:
    article_count = func.count(KnowledgeEntry.id).filter(
        KnowledgeEntry.kind == KnowledgeEntryKind.ARTICLE
    )
    question_count = func.count(KnowledgeEntry.id).filter(
        KnowledgeEntry.kind == KnowledgeEntryKind.QUESTION
    )
    rows = (
        await session.execute(
            select(KnowledgeTopic, article_count, question_count)
            .outerjoin(KnowledgeEntry, KnowledgeEntry.topic_id == KnowledgeTopic.id)
            .group_by(KnowledgeTopic.id)
            .order_by(KnowledgeTopic.position, KnowledgeTopic.title)
        )
    ).all()
    return [
        AdminKnowledgeTopicSummary(
            id=topic.id,
            slug=topic.slug,
            title=topic.title,
            description=topic.description,
            position=topic.position,
            is_published=topic.is_published,
            article_count=articles,
            question_count=questions,
        )
        for topic, articles, questions in rows
    ]


async def get_admin_topic_outline(
    session: AsyncSession, topic_id: UUID
) -> AdminKnowledgeTopicOutline:
    topic = await _admin_topic_model(session, topic_id)
    return AdminKnowledgeTopicOutline(
        id=topic.id,
        slug=topic.slug,
        title=topic.title,
        description=topic.description,
        position=topic.position,
        is_published=topic.is_published,
        entries=[
            AdminKnowledgeEntrySummary(
                id=entry.id,
                kind=entry.kind,
                slug=entry.slug,
                title=entry.title,
                summary=entry.summary,
                position=entry.position,
                is_published=entry.is_published,
                updated_at=entry.updated_at,
            )
            for entry in sorted(topic.entries, key=lambda item: item.position)
        ],
    )


async def update_admin_topic_settings(
    session: AsyncSession,
    topic_id: UUID,
    payload: AdminKnowledgeTopicSettingsMutation,
) -> AdminKnowledgeTopicOutline:
    topic = await session.get(KnowledgeTopic, topic_id, with_for_update=True)
    if topic is None:
        api_error(404, "knowledge_topic_not_found", "Knowledge topic was not found")
    conflict = select(KnowledgeTopic.id).where(
        KnowledgeTopic.slug == payload.slug, KnowledgeTopic.id != topic_id
    )
    if await session.scalar(conflict) is not None:
        api_error(409, "knowledge_topic_slug_conflict", "Topic slug is already in use")
    topic.slug = payload.slug
    topic.title = payload.title
    topic.description = payload.description
    topic.position = payload.position
    topic.is_published = payload.is_published
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        api_error(409, "knowledge_topic_conflict", "Knowledge topic contains conflicts")
    return await get_admin_topic_outline(session, topic_id)


async def get_admin_entry(
    session: AsyncSession, topic_id: UUID, entry_id: UUID
) -> AdminKnowledgeEntryRead:
    entry = await session.get(KnowledgeEntry, entry_id)
    if entry is None or entry.topic_id != topic_id:
        api_error(404, "knowledge_entry_not_found", "Knowledge entry was not found")
    return _admin_entry_read(entry)


async def _validate_entry_slug(
    session: AsyncSession, slug: str, entry_id: UUID | None = None
) -> None:
    statement = select(KnowledgeEntry.id).where(KnowledgeEntry.slug == slug)
    if entry_id is not None:
        statement = statement.where(KnowledgeEntry.id != entry_id)
    if await session.scalar(statement) is not None:
        api_error(409, "knowledge_entry_slug_conflict", "Entry slug is already in use")


async def create_admin_entry(
    session: AsyncSession, topic_id: UUID, payload: AdminKnowledgeEntryMutation
) -> AdminKnowledgeEntryRead:
    if await session.get(KnowledgeTopic, topic_id) is None:
        api_error(404, "knowledge_topic_not_found", "Knowledge topic was not found")
    await _validate_entry_slug(session, payload.slug)
    entry = KnowledgeEntry(topic_id=topic_id)
    _apply_entry(entry, payload)
    session.add(entry)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        api_error(409, "knowledge_entry_conflict", "Knowledge entry contains conflicts")
    await session.refresh(entry)
    return _admin_entry_read(entry)


async def update_admin_entry(
    session: AsyncSession,
    topic_id: UUID,
    entry_id: UUID,
    payload: AdminKnowledgeEntryMutation,
) -> AdminKnowledgeEntryRead:
    entry = await session.get(KnowledgeEntry, entry_id, with_for_update=True)
    if entry is None or entry.topic_id != topic_id:
        api_error(404, "knowledge_entry_not_found", "Knowledge entry was not found")
    if payload.id is not None and payload.id != entry_id:
        api_error(422, "invalid_knowledge_entry", "Entry ID does not match the route")
    await _validate_entry_slug(session, payload.slug, entry_id)
    _apply_entry(entry, payload)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        api_error(409, "knowledge_entry_conflict", "Knowledge entry contains conflicts")
    await session.refresh(entry)
    return _admin_entry_read(entry)


async def _validate_slugs(
    session: AsyncSession,
    payload: AdminKnowledgeTopicMutation,
    *,
    topic_id: UUID | None,
) -> None:
    topic_conflict = select(KnowledgeTopic.id).where(KnowledgeTopic.slug == payload.slug)
    if topic_id is not None:
        topic_conflict = topic_conflict.where(KnowledgeTopic.id != topic_id)
    if await session.scalar(topic_conflict) is not None:
        api_error(409, "knowledge_topic_slug_conflict", "Topic slug is already in use")

    entry_slugs = [entry.slug for entry in payload.entries]
    if not entry_slugs:
        return
    entry_conflict = select(KnowledgeEntry.id).where(KnowledgeEntry.slug.in_(entry_slugs))
    if topic_id is not None:
        entry_conflict = entry_conflict.where(KnowledgeEntry.topic_id != topic_id)
    if await session.scalar(entry_conflict.limit(1)) is not None:
        api_error(409, "knowledge_entry_slug_conflict", "Entry slug is already in use")


def _apply_entry(entry: KnowledgeEntry, payload: AdminKnowledgeEntryMutation) -> None:
    entry.kind = payload.kind
    entry.slug = payload.slug
    entry.title = payload.title
    entry.summary = payload.summary
    entry.content_markdown = payload.content_markdown
    entry.position = payload.position
    entry.is_published = payload.is_published


async def create_admin_topic(
    session: AsyncSession, payload: AdminKnowledgeTopicMutation
) -> AdminKnowledgeTopicRead:
    await _validate_slugs(session, payload, topic_id=None)
    topic = KnowledgeTopic(
        slug=payload.slug,
        title=payload.title,
        description=payload.description,
        position=payload.position,
        is_published=payload.is_published,
    )
    for entry_payload in payload.entries:
        entry = KnowledgeEntry()
        _apply_entry(entry, entry_payload)
        topic.entries.append(entry)
    session.add(topic)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        api_error(409, "knowledge_topic_conflict", "Knowledge topic contains conflicts")
    return await get_admin_topic(session, topic.id)


async def update_admin_topic(
    session: AsyncSession,
    topic_id: UUID,
    payload: AdminKnowledgeTopicMutation,
) -> AdminKnowledgeTopicRead:
    topic = await _admin_topic_model(session, topic_id, lock=True)
    await _validate_slugs(session, payload, topic_id=topic_id)
    existing = {entry.id: entry for entry in topic.entries}
    supplied_ids = {entry.id for entry in payload.entries if entry.id is not None}
    if not supplied_ids.issubset(existing):
        api_error(422, "invalid_knowledge_structure", "Entry does not belong to this topic")

    topic.slug = payload.slug
    topic.title = payload.title
    topic.description = payload.description
    topic.position = payload.position
    topic.is_published = payload.is_published
    for entry in list(topic.entries):
        if entry.id not in supplied_ids:
            topic.entries.remove(entry)
    for entry_payload in payload.entries:
        entry = KnowledgeEntry() if entry_payload.id is None else existing[entry_payload.id]
        _apply_entry(entry, entry_payload)
        if entry_payload.id is None:
            topic.entries.append(entry)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        api_error(409, "knowledge_topic_conflict", "Knowledge topic contains conflicts")
    return await get_admin_topic(session, topic.id)
