from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AdminUser
from app.db.session import get_db_session
from app.knowledge.schemas import (
    AdminKnowledgeEntryMutation,
    AdminKnowledgeEntryRead,
    AdminKnowledgeTopicMutation,
    AdminKnowledgeTopicOutline,
    AdminKnowledgeTopicRead,
    AdminKnowledgeTopicSettingsMutation,
    AdminKnowledgeTopicSummary,
)
from app.knowledge.service import (
    create_admin_entry,
    create_admin_topic,
    get_admin_entry,
    get_admin_topic,
    get_admin_topic_outline,
    list_admin_topic_summaries,
    list_admin_topics,
    update_admin_entry,
    update_admin_topic,
    update_admin_topic_settings,
)

router = APIRouter(prefix="/admin/knowledge/topics", tags=["admin-knowledge"])
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("", response_model=list[AdminKnowledgeTopicRead])
async def admin_knowledge_topics(
    session: Session, _admin: AdminUser
) -> list[AdminKnowledgeTopicRead]:
    return await list_admin_topics(session)


@router.post("", response_model=AdminKnowledgeTopicRead, status_code=status.HTTP_201_CREATED)
async def admin_create_knowledge_topic(
    payload: AdminKnowledgeTopicMutation,
    session: Session,
    _admin: AdminUser,
) -> AdminKnowledgeTopicRead:
    return await create_admin_topic(session, payload)


@router.get("/summaries", response_model=list[AdminKnowledgeTopicSummary])
async def admin_knowledge_topic_summaries(
    session: Session, _admin: AdminUser
) -> list[AdminKnowledgeTopicSummary]:
    return await list_admin_topic_summaries(session)


@router.get("/{topic_id}/outline", response_model=AdminKnowledgeTopicOutline)
async def admin_knowledge_topic_outline(
    topic_id: UUID, session: Session, _admin: AdminUser
) -> AdminKnowledgeTopicOutline:
    return await get_admin_topic_outline(session, topic_id)


@router.patch("/{topic_id}/outline", response_model=AdminKnowledgeTopicOutline)
async def admin_update_knowledge_topic_outline(
    topic_id: UUID,
    payload: AdminKnowledgeTopicSettingsMutation,
    session: Session,
    _admin: AdminUser,
) -> AdminKnowledgeTopicOutline:
    return await update_admin_topic_settings(session, topic_id, payload)


@router.post(
    "/{topic_id}/entries",
    response_model=AdminKnowledgeEntryRead,
    status_code=status.HTTP_201_CREATED,
)
async def admin_create_knowledge_entry(
    topic_id: UUID,
    payload: AdminKnowledgeEntryMutation,
    session: Session,
    _admin: AdminUser,
) -> AdminKnowledgeEntryRead:
    return await create_admin_entry(session, topic_id, payload)


@router.get("/{topic_id}/entries/{entry_id}", response_model=AdminKnowledgeEntryRead)
async def admin_knowledge_entry(
    topic_id: UUID, entry_id: UUID, session: Session, _admin: AdminUser
) -> AdminKnowledgeEntryRead:
    return await get_admin_entry(session, topic_id, entry_id)


@router.put("/{topic_id}/entries/{entry_id}", response_model=AdminKnowledgeEntryRead)
async def admin_update_knowledge_entry(
    topic_id: UUID,
    entry_id: UUID,
    payload: AdminKnowledgeEntryMutation,
    session: Session,
    _admin: AdminUser,
) -> AdminKnowledgeEntryRead:
    return await update_admin_entry(session, topic_id, entry_id, payload)


@router.get("/{topic_id}", response_model=AdminKnowledgeTopicRead)
async def admin_knowledge_topic(
    topic_id: UUID, session: Session, _admin: AdminUser
) -> AdminKnowledgeTopicRead:
    return await get_admin_topic(session, topic_id)


@router.put("/{topic_id}", response_model=AdminKnowledgeTopicRead)
async def admin_update_knowledge_topic(
    topic_id: UUID,
    payload: AdminKnowledgeTopicMutation,
    session: Session,
    _admin: AdminUser,
) -> AdminKnowledgeTopicRead:
    return await update_admin_topic(session, topic_id, payload)
