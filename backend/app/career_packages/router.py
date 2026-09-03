from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AdminUser, CurrentUser, MentorUser, StudentUser
from app.career_packages.models import CareerResumeVersion
from app.career_packages.schemas import (
    CareerAcknowledgeRead,
    CareerDraftMutation,
    CareerGenerationRequest,
    CareerGenerationRunRead,
    CareerObjectionCreate,
    CareerObjectionRead,
    CareerObjectionResolution,
    CareerObligationCreate,
    CareerObligationNoticeCreate,
    CareerPackageCreate,
    CareerPackageRead,
    CareerReviewMutation,
    CareerStudentPackageRead,
    CareerTrackOption,
)
from app.career_packages.service import (
    _event,
    _package,
    authorized_version,
    create_package,
    finalize_resume,
    get_staff_package_for_student,
    get_staff_track_options,
    publish_and_provide,
    record_payment_obligation,
    request_generation,
    resolve_objection,
    resume_version_upload,
    retry_email_delivery,
    retry_obligation_email_delivery,
    save_review,
    send_payment_obligation_notice,
    student_packages,
    submit_objection,
    update_draft,
    validate_completeness,
    version_pdf_upload,
)
from app.core.config import get_settings
from app.db.session import get_db_session
from app.interviews.schemas import InterviewDownloadUrl
from app.interviews.uploads import InterviewUploadStore

Session = Annotated[AsyncSession, Depends(get_db_session)]
settings = get_settings()
store = InterviewUploadStore(settings)

staff_router = APIRouter(prefix="/mentor/students", tags=["career-packages"])
student_router = APIRouter(prefix="/career-packages", tags=["career-packages"])


@staff_router.get("/{student_id}/career-packages", response_model=list[CareerPackageRead])
async def staff_list_packages(
    student_id: UUID, session: Session, actor: MentorUser
) -> list[CareerPackageRead]:
    return await get_staff_package_for_student(session, settings, actor, student_id)


@staff_router.get(
    "/{student_id}/career-package-track-options", response_model=list[CareerTrackOption]
)
async def staff_track_options(
    student_id: UUID, session: Session, actor: MentorUser
) -> list[CareerTrackOption]:
    return await get_staff_track_options(session, settings, actor, student_id)


@staff_router.post(
    "/{student_id}/career-packages",
    response_model=CareerPackageRead,
    status_code=status.HTTP_201_CREATED,
)
async def staff_create_package(
    student_id: UUID,
    payload: CareerPackageCreate,
    session: Session,
    actor: MentorUser,
) -> CareerPackageRead:
    return await create_package(session, settings, actor, student_id, payload.track_id)


@student_router.post("/{package_id}/final-resume", response_model=CareerPackageRead)
async def staff_finalize_resume(
    package_id: UUID, session: Session, actor: MentorUser
) -> CareerPackageRead:
    return await finalize_resume(session, settings, actor, package_id)


@student_router.put("/{package_id}/draft", response_model=CareerPackageRead)
async def staff_update_draft(
    package_id: UUID,
    payload: CareerDraftMutation,
    session: Session,
    actor: MentorUser,
) -> CareerPackageRead:
    return await update_draft(session, settings, actor, package_id, payload)


@student_router.post(
    "/{package_id}/generate",
    response_model=CareerGenerationRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def staff_generate(
    package_id: UUID,
    payload: CareerGenerationRequest,
    request: Request,
    session: Session,
    actor: MentorUser,
) -> CareerGenerationRunRead:
    run = await request_generation(
        session,
        settings,
        actor,
        package_id,
        payload.component,
        str(request.state.request_id),
    )
    return CareerGenerationRunRead.model_validate(run, from_attributes=True)


@student_router.post("/{package_id}/validate", response_model=CareerPackageRead)
async def staff_validate(
    package_id: UUID, session: Session, actor: MentorUser
) -> CareerPackageRead:
    return await validate_completeness(session, settings, actor, package_id)


@student_router.post("/{package_id}/publish", response_model=CareerPackageRead)
async def staff_publish(package_id: UUID, session: Session, actor: MentorUser) -> CareerPackageRead:
    return await publish_and_provide(session, settings, store, actor, package_id)


@student_router.post("/{package_id}/obligation", response_model=CareerPackageRead)
async def admin_record_obligation(
    package_id: UUID,
    payload: CareerObligationCreate,
    session: Session,
    actor: AdminUser,
) -> CareerPackageRead:
    return await record_payment_obligation(session, settings, actor, package_id, payload)


@student_router.post("/{package_id}/obligation/notice", response_model=CareerPackageRead)
async def admin_send_obligation_notice(
    package_id: UUID,
    payload: CareerObligationNoticeCreate,
    session: Session,
    actor: AdminUser,
) -> CareerPackageRead:
    return await send_payment_obligation_notice(session, settings, actor, package_id, payload)


@student_router.post("/{package_id}/deliveries/email/retry", response_model=CareerPackageRead)
async def staff_retry_email_delivery(
    package_id: UUID, session: Session, actor: MentorUser
) -> CareerPackageRead:
    return await retry_email_delivery(session, settings, actor, package_id)


@student_router.post(
    "/{package_id}/obligation/deliveries/email/retry",
    response_model=CareerPackageRead,
)
async def admin_retry_obligation_email_delivery(
    package_id: UUID, session: Session, actor: AdminUser
) -> CareerPackageRead:
    return await retry_obligation_email_delivery(session, settings, actor, package_id)


@student_router.patch("/{package_id}/objections/{objection_id}", response_model=CareerPackageRead)
async def staff_resolve_objection(
    package_id: UUID,
    objection_id: UUID,
    payload: CareerObjectionResolution,
    session: Session,
    actor: MentorUser,
) -> CareerPackageRead:
    return await resolve_objection(session, settings, actor, package_id, objection_id, payload)


@student_router.post("/{package_id}/self-presentation-reviews", response_model=CareerPackageRead)
async def staff_review(
    package_id: UUID,
    payload: CareerReviewMutation,
    session: Session,
    actor: MentorUser,
) -> CareerPackageRead:
    return await save_review(session, settings, actor, package_id, payload)


@student_router.get("/me", response_model=list[CareerStudentPackageRead])
async def my_packages(session: Session, student: StudentUser) -> list[CareerStudentPackageRead]:
    return await student_packages(session, settings, student)


@student_router.post(
    "/me/objections",
    response_model=CareerObjectionRead,
    status_code=status.HTTP_201_CREATED,
)
async def my_objection(
    payload: CareerObjectionCreate, session: Session, student: StudentUser
) -> CareerObjectionRead:
    return await submit_objection(session, settings, student, payload)


@student_router.post("/versions/{version_id}/acknowledge", response_model=CareerAcknowledgeRead)
async def acknowledge_version(
    version_id: UUID, session: Session, student: StudentUser
) -> CareerAcknowledgeRead:
    version = await authorized_version(session, student, version_id)
    # The immutable audit event is the acknowledgement evidence; the version is unchanged.
    owned_package = await _package(session, version.package_id)
    now = datetime.now(UTC)
    _event(
        session,
        owned_package,
        "version_acknowledged",
        student,
        version_id=version.id,
    )
    await session.commit()
    return CareerAcknowledgeRead(acknowledged_at=now)


@student_router.get("/versions/{version_id}/pdf", response_model=InterviewDownloadUrl)
async def package_pdf(
    version_id: UUID, session: Session, viewer: CurrentUser
) -> InterviewDownloadUrl:
    version = await authorized_version(session, viewer, version_id)
    return InterviewDownloadUrl(url=store.download_url(version_pdf_upload(version), inline=False))


@student_router.get("/versions/{version_id}/resume", response_model=InterviewDownloadUrl)
async def package_resume(
    version_id: UUID, session: Session, viewer: CurrentUser
) -> InterviewDownloadUrl:
    version = await authorized_version(session, viewer, version_id)
    resume = await session.get(CareerResumeVersion, version.source_resume_version_id)
    if resume is None:
        raise RuntimeError("Published career package references a missing resume version")
    return InterviewDownloadUrl(url=store.download_url(resume_version_upload(resume), inline=False))
