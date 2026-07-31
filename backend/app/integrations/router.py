from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.integrations.dependencies import BotIntegration
from app.integrations.schemas import (
    GrantedRoadmapRead,
    GrantedTrackRead,
    ProvisionTelegramStudentRequest,
    ProvisionTelegramStudentResponse,
)
from app.integrations.service import provision_telegram_student
from app.users.schemas import UserRead

router = APIRouter(prefix="/integrations/telegram", tags=["integrations"])
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.post("/students", response_model=ProvisionTelegramStudentResponse)
async def provision_student(
    payload: ProvisionTelegramStudentRequest,
    session: Session,
    _: BotIntegration,
) -> ProvisionTelegramStudentResponse:
    result = await provision_telegram_student(session, payload)
    return ProvisionTelegramStudentResponse(
        created=result.created,
        access_created=result.access_created,
        user=UserRead.model_validate(result.user),
        track=GrantedTrackRead(
            id=result.track.id,
            slug=result.track.slug,
            title=result.track.title,
        ),
        roadmaps=[
            GrantedRoadmapRead(id=roadmap.id, slug=roadmap.slug, title=roadmap.title)
            for roadmap in result.roadmaps
        ],
    )
