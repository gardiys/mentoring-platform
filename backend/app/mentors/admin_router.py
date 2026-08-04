from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AdminUser
from app.db.session import get_db_session
from app.mentors.admin_schemas import (
    AdminMentorCandidate,
    AdminMentorDirectionsMutation,
    AdminMentorListItem,
    AdminMentorMutation,
    AdminMentorProfileMutation,
    AdminStudentMentorMutation,
)
from app.mentors.admin_service import (
    create_admin_mentor,
    demote_mentor_to_student,
    list_admin_mentors,
    list_mentor_candidates,
    promote_student_to_mentor,
    reassign_student,
    update_admin_mentor_profile,
    update_mentor_directions,
)

router = APIRouter(prefix="/admin/mentors", tags=["admin-mentors"])
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("", response_model=list[AdminMentorListItem])
async def admin_mentors(session: Session, _admin: AdminUser) -> list[AdminMentorListItem]:
    return await list_admin_mentors(session)


@router.get("/candidates", response_model=list[AdminMentorCandidate])
async def admin_mentor_candidates(
    session: Session,
    _admin: AdminUser,
    q: str | None = Query(default=None, max_length=160),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[AdminMentorCandidate]:
    return await list_mentor_candidates(session, query=q, limit=limit)


@router.post("", response_model=AdminMentorListItem, status_code=status.HTTP_201_CREATED)
async def admin_create_mentor(
    payload: AdminMentorMutation, session: Session, _admin: AdminUser
) -> AdminMentorListItem:
    return await create_admin_mentor(session, payload)


@router.patch("/{mentor_id}/profile", response_model=AdminMentorListItem)
async def admin_update_mentor_profile(
    mentor_id: UUID,
    payload: AdminMentorProfileMutation,
    session: Session,
    _admin: AdminUser,
) -> AdminMentorListItem:
    return await update_admin_mentor_profile(session, mentor_id, payload)


@router.post("/{student_id}/promote", response_model=AdminMentorListItem)
async def admin_promote_student(
    student_id: UUID, session: Session, _admin: AdminUser
) -> AdminMentorListItem:
    return await promote_student_to_mentor(session, student_id)


@router.delete("/{mentor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_remove_mentor(mentor_id: UUID, session: Session, _admin: AdminUser) -> Response:
    await demote_mentor_to_student(session, mentor_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{mentor_id}/directions", response_model=AdminMentorListItem)
async def admin_update_mentor_directions(
    mentor_id: UUID,
    payload: AdminMentorDirectionsMutation,
    session: Session,
    _admin: AdminUser,
) -> AdminMentorListItem:
    return await update_mentor_directions(session, mentor_id, payload.track_ids)


@router.patch("/students/{student_id}/mentor", status_code=status.HTTP_204_NO_CONTENT)
async def admin_reassign_mentor_student(
    student_id: UUID,
    payload: AdminStudentMentorMutation,
    session: Session,
    _admin: AdminUser,
) -> Response:
    await reassign_student(session, student_id, payload.mentor_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
