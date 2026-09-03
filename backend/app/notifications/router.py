from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.db.session import get_db_session
from app.notifications.schemas import NotificationPage
from app.notifications.service import list_notifications, mark_all_read, mark_read

router = APIRouter(prefix="/notifications", tags=["notifications"])
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("", response_model=NotificationPage)
async def notifications_page(
    session: Session,
    user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> NotificationPage:
    return await list_notifications(session, user, limit=limit, offset=offset)


@router.put(
    "/{notification_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def notification_read(notification_id: UUID, session: Session, user: CurrentUser) -> Response:
    await mark_read(session, user, notification_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/read-all",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def notifications_read_all(session: Session, user: CurrentUser) -> Response:
    await mark_all_read(session, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
