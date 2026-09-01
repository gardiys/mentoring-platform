from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AdminUser
from app.db.session import get_db_session
from app.mentors.models import StudentLearningStatus
from app.students.schemas import (
    AdminStudentAccessMutation,
    AdminStudentDetail,
    AdminStudentMediaAnonymizationStatus,
    AdminStudentMutation,
    AdminStudentOptions,
    AdminStudentPage,
    AdminStudentPersonalDataErasureMutation,
    AdminStudentPublicIdentityMutation,
)
from app.students.service import (
    create_student,
    erase_student_personal_data,
    list_students,
    retry_student_media_anonymization,
    set_student_access,
    set_student_public_identity,
    student_detail,
    student_media_anonymization_status,
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
    track_id: UUID | None = None,
    learning_status: Annotated[list[StudentLearningStatus] | None, Query()] = None,
    is_active: bool | None = None,
    access: Literal["all", "active", "blocked"] | None = Query(
        default=None,
        deprecated=True,
    ),
    mentor_id: UUID | None = None,
    without_mentor: bool = False,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AdminStudentPage:
    resolved_is_active = is_active
    if resolved_is_active is None:
        if access == "active":
            resolved_is_active = True
        elif access == "blocked":
            resolved_is_active = False
    return await list_students(
        session,
        query=q,
        track_id=track_id,
        learning_statuses=learning_status,
        is_active=resolved_is_active,
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


@router.patch("/{student_id}/public-identity", response_model=AdminStudentDetail)
async def admin_set_student_public_identity(
    student_id: UUID,
    payload: AdminStudentPublicIdentityMutation,
    session: Session,
    admin: AdminUser,
) -> AdminStudentDetail:
    return await set_student_public_identity(
        session,
        admin,
        student_id,
        hidden=payload.hidden,
        reason=payload.reason,
    )


@router.get(
    "/{student_id}/media-anonymization",
    response_model=AdminStudentMediaAnonymizationStatus,
)
async def admin_student_media_anonymization(
    student_id: UUID, session: Session, _admin: AdminUser
) -> AdminStudentMediaAnonymizationStatus:
    return await student_media_anonymization_status(session, student_id)


@router.post(
    "/{student_id}/media-anonymization/retry",
    response_model=AdminStudentMediaAnonymizationStatus,
)
async def admin_retry_student_media_anonymization(
    student_id: UUID, session: Session, _admin: AdminUser
) -> AdminStudentMediaAnonymizationStatus:
    return await retry_student_media_anonymization(session, student_id)


@router.post("/{student_id}/erase-personal-data", response_model=AdminStudentDetail)
async def admin_erase_student_personal_data(
    student_id: UUID,
    payload: AdminStudentPersonalDataErasureMutation,
    session: Session,
    admin: AdminUser,
) -> AdminStudentDetail:
    return await erase_student_personal_data(
        session,
        admin,
        student_id,
        reason=payload.reason,
    )
