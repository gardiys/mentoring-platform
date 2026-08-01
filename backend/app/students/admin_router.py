from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AdminUser
from app.db.session import get_db_session
from app.students.schemas import (
    AdminStudentAccessMutation,
    AdminStudentDetail,
    AdminStudentMutation,
    AdminStudentOptions,
    AdminStudentPage,
)
from app.students.service import (
    create_student,
    list_students,
    set_student_access,
    student_detail,
    student_options,
    update_student,
)

router = APIRouter(prefix="/admin/students", tags=["admin-students"])
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("", response_model=AdminStudentPage)
async def admin_students(
    session: Session,
    _admin: AdminUser,
    q: str | None = Query(default=None, max_length=160),
    access: Literal["all", "active", "blocked"] = Query(default="all"),
    mentor_id: UUID | None = None,
    without_mentor: bool = False,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AdminStudentPage:
    return await list_students(
        session,
        query=q,
        access=access,
        mentor_id=mentor_id,
        without_mentor=without_mentor,
        limit=limit,
        offset=offset,
    )


@router.get("/options", response_model=AdminStudentOptions)
async def admin_student_options(session: Session, _admin: AdminUser) -> AdminStudentOptions:
    return await student_options(session)


@router.post("", response_model=AdminStudentDetail, status_code=status.HTTP_201_CREATED)
async def admin_create_student(
    payload: AdminStudentMutation, session: Session, _admin: AdminUser
) -> AdminStudentDetail:
    return await create_student(session, payload)


@router.get("/{student_id}", response_model=AdminStudentDetail)
async def admin_student(
    student_id: UUID, session: Session, _admin: AdminUser
) -> AdminStudentDetail:
    return await student_detail(session, student_id)


@router.put("/{student_id}", response_model=AdminStudentDetail)
async def admin_update_student(
    student_id: UUID,
    payload: AdminStudentMutation,
    session: Session,
    _admin: AdminUser,
) -> AdminStudentDetail:
    return await update_student(session, student_id, payload)


@router.patch("/{student_id}/access", response_model=AdminStudentDetail)
async def admin_set_student_access(
    student_id: UUID,
    payload: AdminStudentAccessMutation,
    session: Session,
    _admin: AdminUser,
) -> AdminStudentDetail:
    return await set_student_access(session, student_id, is_active=payload.is_active)
