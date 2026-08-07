from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AdminUser
from app.core.config import get_settings
from app.db.session import get_db_session
from app.media.storage import PrivateMediaStore
from app.roadmaps.admin_schemas import (
    AdminRoadmapCreate,
    AdminRoadmapOutline,
    AdminRoadmapRead,
    AdminRoadmapSettingsMutation,
    AdminRoadmapSummary,
    AdminRoadmapUpdate,
    AdminSectionMutation,
    AdminSectionOutline,
    AdminTopicCreate,
    AdminTopicRead,
)
from app.roadmaps.admin_service import (
    create_admin_section,
    create_admin_topic,
    create_roadmap,
    delete_roadmap,
    get_admin_roadmap,
    get_admin_roadmap_outline,
    get_admin_section,
    get_admin_topic,
    list_admin_roadmap_summaries,
    list_admin_roadmaps,
    update_admin_section,
    update_admin_topic,
    update_roadmap,
    update_roadmap_settings,
)

router = APIRouter(prefix="/admin/roadmaps", tags=["admin-roadmaps"])
Session = Annotated[AsyncSession, Depends(get_db_session)]
store = PrivateMediaStore(get_settings())


@router.get("", response_model=list[AdminRoadmapRead])
async def admin_roadmaps(session: Session, _admin: AdminUser) -> list[AdminRoadmapRead]:
    return await list_admin_roadmaps(session)


@router.post("", response_model=AdminRoadmapRead, status_code=status.HTTP_201_CREATED)
async def admin_create_roadmap(
    payload: AdminRoadmapCreate, session: Session, _admin: AdminUser
) -> AdminRoadmapRead:
    return await create_roadmap(session, payload)


@router.get("/summaries", response_model=list[AdminRoadmapSummary])
async def admin_roadmap_summaries(session: Session, _admin: AdminUser) -> list[AdminRoadmapSummary]:
    return await list_admin_roadmap_summaries(session)


@router.get("/{roadmap_id}/outline", response_model=AdminRoadmapOutline)
async def admin_roadmap_outline(
    roadmap_id: UUID, session: Session, _admin: AdminUser
) -> AdminRoadmapOutline:
    return await get_admin_roadmap_outline(session, roadmap_id)


@router.patch("/{roadmap_id}/outline", response_model=AdminRoadmapOutline)
async def admin_update_roadmap_outline(
    roadmap_id: UUID,
    payload: AdminRoadmapSettingsMutation,
    session: Session,
    _admin: AdminUser,
) -> AdminRoadmapOutline:
    return await update_roadmap_settings(session, roadmap_id, payload)


@router.post(
    "/{roadmap_id}/sections",
    response_model=AdminSectionOutline,
    status_code=status.HTTP_201_CREATED,
)
async def admin_create_roadmap_section(
    roadmap_id: UUID,
    payload: AdminSectionMutation,
    session: Session,
    _admin: AdminUser,
) -> AdminSectionOutline:
    return await create_admin_section(session, roadmap_id, payload)


@router.get("/{roadmap_id}/sections/{section_id}", response_model=AdminSectionOutline)
async def admin_roadmap_section(
    roadmap_id: UUID, section_id: UUID, session: Session, _admin: AdminUser
) -> AdminSectionOutline:
    return await get_admin_section(session, roadmap_id, section_id)


@router.put("/{roadmap_id}/sections/{section_id}", response_model=AdminSectionOutline)
async def admin_update_roadmap_section(
    roadmap_id: UUID,
    section_id: UUID,
    payload: AdminSectionMutation,
    session: Session,
    _admin: AdminUser,
) -> AdminSectionOutline:
    return await update_admin_section(session, roadmap_id, section_id, payload)


@router.post(
    "/{roadmap_id}/sections/{section_id}/topics",
    response_model=AdminTopicRead,
    status_code=status.HTTP_201_CREATED,
)
async def admin_create_roadmap_topic(
    roadmap_id: UUID,
    section_id: UUID,
    payload: AdminTopicCreate,
    session: Session,
    _admin: AdminUser,
) -> AdminTopicRead:
    return await create_admin_topic(session, roadmap_id, section_id, payload)


@router.get(
    "/{roadmap_id}/sections/{section_id}/topics/{topic_id}",
    response_model=AdminTopicRead,
)
async def admin_roadmap_topic(
    roadmap_id: UUID,
    section_id: UUID,
    topic_id: UUID,
    session: Session,
    _admin: AdminUser,
) -> AdminTopicRead:
    return await get_admin_topic(session, roadmap_id, section_id, topic_id)


@router.put(
    "/{roadmap_id}/sections/{section_id}/topics/{topic_id}",
    response_model=AdminTopicRead,
)
async def admin_update_roadmap_topic(
    roadmap_id: UUID,
    section_id: UUID,
    topic_id: UUID,
    payload: AdminTopicCreate,
    session: Session,
    _admin: AdminUser,
) -> AdminTopicRead:
    return await update_admin_topic(session, roadmap_id, section_id, topic_id, payload)


@router.get("/{roadmap_id}", response_model=AdminRoadmapRead)
async def admin_roadmap(roadmap_id: UUID, session: Session, _admin: AdminUser) -> AdminRoadmapRead:
    return await get_admin_roadmap(session, roadmap_id)


@router.put("/{roadmap_id}", response_model=AdminRoadmapRead)
async def admin_update_roadmap(
    roadmap_id: UUID,
    payload: AdminRoadmapUpdate,
    session: Session,
    _admin: AdminUser,
) -> AdminRoadmapRead:
    return await update_roadmap(session, roadmap_id, payload)


@router.delete("/{roadmap_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def admin_delete_roadmap(roadmap_id: UUID, session: Session, _admin: AdminUser) -> Response:
    storage_keys = await delete_roadmap(session, roadmap_id)
    for storage_key in storage_keys:
        await store.delete(storage_key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
