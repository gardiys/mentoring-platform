from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CatalogUser
from app.db.session import get_db_session
from app.interviews.recruiter_service import (
    delete_recruiter_feedback,
    list_recruiters,
    open_recruiter_contact,
    set_recruiter_feedback,
)
from app.interviews.schemas import (
    RecruiterContactOpenRead,
    RecruiterContactPage,
    RecruiterFeedbackMutation,
    RecruiterFeedbackRead,
    RecruiterSort,
)

router = APIRouter(prefix="/interviews/recruiters", tags=["interview-recruiters"])
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("", response_model=RecruiterContactPage)
async def recruiter_directory(
    session: Session,
    user: CatalogUser,
    q: str | None = Query(default=None, min_length=1, max_length=240),
    track_id: UUID | None = None,
    contacted: bool | None = None,
    sort: RecruiterSort = RecruiterSort.RECOMMENDED,
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> RecruiterContactPage:
    return await list_recruiters(
        session,
        user,
        query=q,
        track_id=track_id,
        contacted=contacted,
        sort=sort,
        limit=limit,
        offset=offset,
    )


@router.post("/{recruiter_id}/contact", response_model=RecruiterContactOpenRead)
async def recruiter_contact(
    recruiter_id: UUID, session: Session, user: CatalogUser
) -> RecruiterContactOpenRead:
    return await open_recruiter_contact(session, user, recruiter_id)


@router.put("/{recruiter_id}/feedback", response_model=RecruiterFeedbackRead)
async def recruiter_feedback(
    recruiter_id: UUID,
    payload: RecruiterFeedbackMutation,
    session: Session,
    user: CatalogUser,
) -> RecruiterFeedbackRead:
    return await set_recruiter_feedback(session, user, recruiter_id, payload)


@router.delete(
    "/{recruiter_id}/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def recruiter_feedback_delete(
    recruiter_id: UUID, session: Session, user: CatalogUser
) -> Response:
    await delete_recruiter_feedback(session, user, recruiter_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
