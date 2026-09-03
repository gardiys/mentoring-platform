from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AdminUser, MentorUser, StudentUser
from app.core.config import get_settings
from app.db.session import get_db_session
from app.employment_qualification.models import EmploymentEvidenceType
from app.employment_qualification.queue import enqueue_employment_ai_suggestion
from app.employment_qualification.schemas import (
    EmploymentActualDutiesReport,
    EmploymentAIRequest,
    EmploymentAISuggestionRead,
    EmploymentAssessmentCreate,
    EmploymentCaseList,
    EmploymentCaseRead,
    EmploymentChangeReport,
    EmploymentDisputeCreate,
    EmploymentDisputeResolution,
    EmploymentEndReport,
    EmploymentEvidenceCreate,
    EmploymentInformationRequest,
    EmploymentOfferReport,
    EmploymentOfferStatusReport,
    EmploymentPolicyCreate,
    EmploymentPolicyRead,
    EmploymentQualificationMetrics,
    EmploymentTrackOption,
    EmploymentWorkStartReport,
)
from app.employment_qualification.service import (
    add_file_evidence,
    add_text_evidence,
    authorize_case_access,
    create_assessment,
    create_policy_snapshot,
    employment_qualification_metrics,
    evidence_file_for_actor,
    list_cases,
    open_dispute,
    report_actual_duties,
    report_change,
    report_end,
    report_offer,
    report_offer_status,
    report_work_start,
    request_ai_suggestion,
    request_information,
    resolve_dispute,
    student_track_options,
)
from app.interviews.schemas import (
    InterviewDownloadUrl,
    InterviewMultipartUploadIntent,
    InterviewUploadComplete,
    InterviewUploadIntent,
    InterviewUploadIntentResponse,
    InterviewUploadProtocol,
    InterviewUploadRequest,
)
from app.interviews.upload_cleanup import delete_upload_if_unreferenced
from app.interviews.uploads import (
    CompletedMultipartUploadPart,
    InterviewUploadStore,
    StoredUpload,
)

Session = Annotated[AsyncSession, Depends(get_db_session)]
student_router = APIRouter(prefix="/employment-cases", tags=["employment-cases"])
staff_router = APIRouter(prefix="/mentor/students", tags=["employment-cases"])
admin_router = APIRouter(prefix="/admin/students", tags=["employment-policies"])
settings = get_settings()
store = InterviewUploadStore(settings)
EVIDENCE_CONTENT_TYPES = ("application/pdf", "image", "text")
EVIDENCE_MAX_BYTES = 20 * 1024 * 1024


async def _evidence_upload_intent(
    actor_id: UUID, case_id: UUID, payload: InterviewUploadRequest
) -> InterviewUploadIntentResponse:
    if payload.upload_protocol is InterviewUploadProtocol.MULTIPART_V1:
        multipart_intent = await store.create_multipart_upload_intent(
            user_id=actor_id,
            category="employment-evidence",
            resource=f"employment-evidence:{case_id}",
            filename=payload.filename,
            content_type=payload.content_type,
            size=payload.size,
            allowed_content_types=EVIDENCE_CONTENT_TYPES,
            max_bytes=EVIDENCE_MAX_BYTES,
        )
        return InterviewMultipartUploadIntent.model_validate(multipart_intent, from_attributes=True)
    intent = store.create_upload_intent(
        user_id=actor_id,
        category="employment-evidence",
        filename=payload.filename,
        content_type=payload.content_type,
        size=payload.size,
        allowed_content_types=EVIDENCE_CONTENT_TYPES,
        max_bytes=EVIDENCE_MAX_BYTES,
    )
    return InterviewUploadIntent.model_validate(intent, from_attributes=True)


async def _complete_evidence_upload(
    actor_id: UUID, case_id: UUID, payload: InterviewUploadComplete
) -> StoredUpload:
    if payload.upload_protocol is InterviewUploadProtocol.MULTIPART_V1:
        if payload.upload_id is None or payload.upload_token is None:
            raise ValueError("Multipart upload metadata is missing")
        return await store.complete_multipart_upload(
            user_id=actor_id,
            category="employment-evidence",
            resource=f"employment-evidence:{case_id}",
            storage_key=payload.storage_key,
            upload_id=payload.upload_id,
            upload_token=payload.upload_token,
            filename=payload.filename,
            content_type=payload.content_type,
            expected_size=payload.size,
            parts=tuple(
                CompletedMultipartUploadPart(part_number=item.part_number, etag=item.etag)
                for item in payload.parts
            ),
            allowed_content_types=EVIDENCE_CONTENT_TYPES,
            max_bytes=EVIDENCE_MAX_BYTES,
        )
    return await store.complete_upload(
        user_id=actor_id,
        category="employment-evidence",
        storage_key=payload.storage_key,
        filename=payload.filename,
        content_type=payload.content_type,
        expected_size=payload.size,
        allowed_content_types=EVIDENCE_CONTENT_TYPES,
        max_bytes=EVIDENCE_MAX_BYTES,
    )


@student_router.get("/me", response_model=EmploymentCaseList)
async def my_cases(session: Session, student: StudentUser) -> EmploymentCaseList:
    return await list_cases(session, student)


@student_router.get("/me/track-options", response_model=list[EmploymentTrackOption])
async def my_track_options(session: Session, student: StudentUser) -> list[EmploymentTrackOption]:
    return await student_track_options(session, student)


@student_router.post(
    "/me/report-offer",
    response_model=EmploymentCaseRead,
    status_code=status.HTTP_201_CREATED,
)
async def my_report_offer(
    payload: EmploymentOfferReport,
    session: Session,
    student: StudentUser,
) -> EmploymentCaseRead:
    return await report_offer(session, student, payload)


@student_router.post("/{case_id}/work-start", response_model=EmploymentCaseRead)
async def my_report_work_start(
    case_id: UUID,
    payload: EmploymentWorkStartReport,
    session: Session,
    student: StudentUser,
) -> EmploymentCaseRead:
    return await report_work_start(session, student, case_id, payload)


@student_router.post("/{case_id}/offer-status", response_model=EmploymentCaseRead)
async def my_report_offer_status(
    case_id: UUID,
    payload: EmploymentOfferStatusReport,
    session: Session,
    student: StudentUser,
) -> EmploymentCaseRead:
    return await report_offer_status(session, student, case_id, payload)


@student_router.post("/{case_id}/actual-duties", response_model=EmploymentCaseRead)
async def my_report_actual_duties(
    case_id: UUID,
    payload: EmploymentActualDutiesReport,
    session: Session,
    student: StudentUser,
) -> EmploymentCaseRead:
    return await report_actual_duties(session, student, case_id, payload)


@student_router.post("/{case_id}/changes", response_model=EmploymentCaseRead)
async def my_report_change(
    case_id: UUID,
    payload: EmploymentChangeReport,
    session: Session,
    student: StudentUser,
) -> EmploymentCaseRead:
    return await report_change(session, student, case_id, payload)


@student_router.post("/{case_id}/end", response_model=EmploymentCaseRead)
async def my_report_end(
    case_id: UUID,
    payload: EmploymentEndReport,
    session: Session,
    student: StudentUser,
) -> EmploymentCaseRead:
    return await report_end(session, student, case_id, payload)


@student_router.post("/{case_id}/evidence", response_model=EmploymentCaseRead)
async def my_add_evidence(
    case_id: UUID,
    payload: EmploymentEvidenceCreate,
    session: Session,
    student: StudentUser,
) -> EmploymentCaseRead:
    return await add_text_evidence(session, student, case_id, payload)


@student_router.post("/{case_id}/evidence/upload", response_model=InterviewUploadIntentResponse)
async def my_create_evidence_upload(
    case_id: UUID,
    payload: InterviewUploadRequest,
    session: Session,
    student: StudentUser,
) -> InterviewUploadIntentResponse:
    await authorize_case_access(session, student, case_id)
    return await _evidence_upload_intent(student.id, case_id, payload)


@student_router.post("/{case_id}/evidence/complete", response_model=EmploymentCaseRead)
async def my_complete_evidence_upload(
    case_id: UUID,
    evidence_type: EmploymentEvidenceType,
    payload: InterviewUploadComplete,
    session: Session,
    student: StudentUser,
) -> EmploymentCaseRead:
    await authorize_case_access(session, student, case_id)
    upload = await _complete_evidence_upload(student.id, case_id, payload)
    checksum = await store.sha256(upload, max_bytes=EVIDENCE_MAX_BYTES)
    try:
        return await add_file_evidence(session, student, case_id, evidence_type, upload, checksum)
    except Exception:
        await delete_upload_if_unreferenced(session, store, upload.storage_key)
        raise


@student_router.get("/{case_id}/evidence/{evidence_id}/file", response_model=InterviewDownloadUrl)
async def my_open_evidence_file(
    case_id: UUID,
    evidence_id: UUID,
    session: Session,
    student: StudentUser,
) -> InterviewDownloadUrl:
    upload = await evidence_file_for_actor(session, student, case_id, evidence_id)
    return InterviewDownloadUrl(url=store.download_url(upload, inline=True, expires_in=300))


@student_router.post("/{case_id}/disputes", response_model=EmploymentCaseRead)
async def my_open_dispute(
    case_id: UUID,
    payload: EmploymentDisputeCreate,
    session: Session,
    student: StudentUser,
) -> EmploymentCaseRead:
    return await open_dispute(session, student, case_id, payload)


@staff_router.get("/{student_id}/employment-cases", response_model=EmploymentCaseList)
async def staff_cases(
    student_id: UUID,
    session: Session,
    actor: MentorUser,
) -> EmploymentCaseList:
    return await list_cases(session, actor, student_id)


@staff_router.post(
    "/{student_id}/employment-cases/{case_id}/request-information",
    response_model=EmploymentCaseRead,
)
async def staff_request_information(
    student_id: UUID,
    case_id: UUID,
    payload: EmploymentInformationRequest,
    session: Session,
    actor: MentorUser,
) -> EmploymentCaseRead:
    await authorize_case_access(session, actor, case_id, expected_student_id=student_id)
    return await request_information(session, actor, case_id, payload)


@staff_router.post(
    "/{student_id}/employment-cases/{case_id}/assessments", response_model=EmploymentCaseRead
)
async def staff_create_assessment(
    student_id: UUID,
    case_id: UUID,
    payload: EmploymentAssessmentCreate,
    session: Session,
    actor: MentorUser,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> EmploymentCaseRead:
    await authorize_case_access(session, actor, case_id, expected_student_id=student_id)
    if idempotency_key:
        payload = payload.model_copy(update={"idempotency_key": idempotency_key})
    return await create_assessment(session, actor, case_id, payload)


@staff_router.post(
    "/{student_id}/employment-cases/{case_id}/ai-suggestions",
    response_model=EmploymentAISuggestionRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def staff_request_ai_suggestion(
    student_id: UUID,
    case_id: UUID,
    payload: EmploymentAIRequest,
    session: Session,
    actor: MentorUser,
) -> EmploymentAISuggestionRead:
    await authorize_case_access(session, actor, case_id, expected_student_id=student_id)
    suggestion = await request_ai_suggestion(session, actor, case_id, payload)
    await enqueue_employment_ai_suggestion(suggestion.id)
    return EmploymentAISuggestionRead.model_validate(suggestion, from_attributes=True)


@staff_router.post(
    "/{student_id}/employment-cases/{case_id}/evidence", response_model=EmploymentCaseRead
)
async def staff_add_evidence(
    student_id: UUID,
    case_id: UUID,
    payload: EmploymentEvidenceCreate,
    session: Session,
    actor: MentorUser,
) -> EmploymentCaseRead:
    await authorize_case_access(session, actor, case_id, expected_student_id=student_id)
    return await add_text_evidence(session, actor, case_id, payload)


@staff_router.post(
    "/{student_id}/employment-cases/{case_id}/evidence/upload",
    response_model=InterviewUploadIntentResponse,
)
async def staff_create_evidence_upload(
    student_id: UUID,
    case_id: UUID,
    payload: InterviewUploadRequest,
    session: Session,
    actor: MentorUser,
) -> InterviewUploadIntentResponse:
    await authorize_case_access(session, actor, case_id, expected_student_id=student_id)
    return await _evidence_upload_intent(actor.id, case_id, payload)


@staff_router.post(
    "/{student_id}/employment-cases/{case_id}/evidence/complete",
    response_model=EmploymentCaseRead,
)
async def staff_complete_evidence_upload(
    student_id: UUID,
    case_id: UUID,
    evidence_type: EmploymentEvidenceType,
    payload: InterviewUploadComplete,
    session: Session,
    actor: MentorUser,
) -> EmploymentCaseRead:
    await authorize_case_access(session, actor, case_id, expected_student_id=student_id)
    upload = await _complete_evidence_upload(actor.id, case_id, payload)
    checksum = await store.sha256(upload, max_bytes=EVIDENCE_MAX_BYTES)
    try:
        return await add_file_evidence(session, actor, case_id, evidence_type, upload, checksum)
    except Exception:
        await delete_upload_if_unreferenced(session, store, upload.storage_key)
        raise


@staff_router.get(
    "/{student_id}/employment-cases/{case_id}/evidence/{evidence_id}/file",
    response_model=InterviewDownloadUrl,
)
async def staff_open_evidence_file(
    student_id: UUID,
    case_id: UUID,
    evidence_id: UUID,
    session: Session,
    actor: MentorUser,
) -> InterviewDownloadUrl:
    await authorize_case_access(session, actor, case_id, expected_student_id=student_id)
    upload = await evidence_file_for_actor(session, actor, case_id, evidence_id)
    return InterviewDownloadUrl(url=store.download_url(upload, inline=True, expires_in=300))


@staff_router.post(
    "/{student_id}/employment-cases/{case_id}/disputes/{dispute_id}/resolve",
    response_model=EmploymentCaseRead,
)
async def staff_resolve_dispute(
    student_id: UUID,
    case_id: UUID,
    dispute_id: UUID,
    payload: EmploymentDisputeResolution,
    session: Session,
    actor: MentorUser,
) -> EmploymentCaseRead:
    await authorize_case_access(session, actor, case_id, expected_student_id=student_id)
    return await resolve_dispute(session, actor, case_id, dispute_id, payload)


@admin_router.post(
    "/{student_id}/employment-policies",
    response_model=EmploymentPolicyRead,
    status_code=status.HTTP_201_CREATED,
)
async def admin_create_policy(
    student_id: UUID,
    payload: EmploymentPolicyCreate,
    session: Session,
    admin: AdminUser,
) -> EmploymentPolicyRead:
    item = await create_policy_snapshot(session, admin, student_id, payload)
    return EmploymentPolicyRead.model_validate(item, from_attributes=True)


@admin_router.get(
    "/employment-qualification/metrics",
    response_model=EmploymentQualificationMetrics,
)
async def admin_employment_metrics(
    session: Session,
    admin: AdminUser,
) -> EmploymentQualificationMetrics:
    return await employment_qualification_metrics(session, admin)
