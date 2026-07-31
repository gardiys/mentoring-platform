from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.core.errors import api_error
from app.db.session import get_db_session
from app.progress.schemas import ProgressUpdateRequest, ProgressUpdateResponse, TopicProgressRead
from app.progress.service import update_topic_progress
from app.roadmaps.queries import (
    build_roadmap_detail,
    build_topic_detail,
    get_roadmap_model,
    get_topic_model,
    has_roadmap_access,
    list_roadmaps,
    start_roadmap,
)
from app.roadmaps.schemas import RoadmapDetail, RoadmapListItem, TopicDetail

router = APIRouter(tags=["roadmaps"])
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/roadmaps", response_model=list[RoadmapListItem])
async def roadmaps(session: Session, current_user: CurrentUser) -> list[RoadmapListItem]:
    return await list_roadmaps(session, current_user.id)


@router.get("/roadmaps/{roadmap_slug}", response_model=RoadmapDetail)
async def roadmap_detail(
    roadmap_slug: str, session: Session, current_user: CurrentUser
) -> RoadmapDetail:
    roadmap = await get_roadmap_model(session, roadmap_slug)
    if roadmap is None or not await has_roadmap_access(session, current_user.id, roadmap.id):
        api_error(404, "roadmap_not_found", "Roadmap was not found")
    return await build_roadmap_detail(session, roadmap, current_user.id)


@router.post("/roadmaps/{roadmap_slug}/start", response_model=RoadmapDetail)
async def start_roadmap_progress(
    roadmap_slug: str, session: Session, current_user: CurrentUser
) -> RoadmapDetail:
    roadmap = await get_roadmap_model(session, roadmap_slug)
    if roadmap is None or not await has_roadmap_access(session, current_user.id, roadmap.id):
        api_error(404, "roadmap_not_found", "Roadmap was not found")
    await start_roadmap(session, user_id=current_user.id, roadmap_id=roadmap.id)
    return await build_roadmap_detail(session, roadmap, current_user.id)


@router.get("/topics/{topic_id}", response_model=TopicDetail)
async def topic_detail(topic_id: UUID, session: Session, current_user: CurrentUser) -> TopicDetail:
    topic = await get_topic_model(session, topic_id)
    if topic is None or not await has_roadmap_access(
        session, current_user.id, topic.section.roadmap_id
    ):
        api_error(404, "topic_not_found", "Topic was not found")
    return await build_topic_detail(session, topic, current_user.id)


@router.put("/me/topics/{topic_id}/progress", response_model=ProgressUpdateResponse)
async def set_topic_progress(
    topic_id: UUID,
    payload: ProgressUpdateRequest,
    session: Session,
    current_user: CurrentUser,
) -> ProgressUpdateResponse:
    topic = await get_topic_model(session, topic_id)
    if topic is None or not await has_roadmap_access(
        session, current_user.id, topic.section.roadmap_id
    ):
        api_error(404, "topic_not_found", "Topic was not found")
    progress, roadmap_progress = await update_topic_progress(
        session, user_id=current_user.id, topic=topic, status_value=payload.status
    )
    return ProgressUpdateResponse(
        topic_progress=TopicProgressRead(
            topic_id=progress.topic_id,
            status=progress.status,
            started_at=progress.started_at,
            first_completed_at=progress.first_completed_at,
            last_completed_at=progress.last_completed_at,
        ),
        roadmap_progress=roadmap_progress,
    )
