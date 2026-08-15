import logging
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import JournalUser
from app.core.config import get_settings
from app.core.errors import api_error
from app.db.session import get_db_session
from app.interviews.companies import suggest_companies
from app.interviews.intelligence_queue import enqueue_intelligence_job
from app.interviews.intelligence_schemas import IntelligenceInterviewDetail
from app.interviews.intelligence_service import intelligence_detail, start_stage_ai_analysis
from app.interviews.journal_service import (
    add_stage_attachment,
    cancel_offer,
    clear_stage_attachment,
    clear_stage_media,
    create_process,
    create_stage,
    delete_own_process,
    ensure_stage_attachment_capacity,
    ensure_stage_editable,
    get_process_model,
    get_stage_attachment_model,
    get_stage_model,
    list_interview_directions,
    list_processes,
    process_detail,
    set_offer_file,
    set_process_outcome,
    set_process_recruiters,
    set_stage_media,
    update_process,
    update_stage,
)
from app.interviews.media import ensure_stage_media_browser_playable
from app.interviews.models import InterviewProcessStage, InterviewProcessStatus
from app.interviews.schemas import (
    CompanyOption,
    InterviewDirectionOption,
    InterviewDownloadUrl,
    InterviewMultipartUploadIntent,
    InterviewProcessDetail,
    InterviewProcessMutation,
    InterviewProcessOutcomeMutation,
    InterviewProcessRecruitersMutation,
    InterviewProcessStageMutation,
    InterviewProcessSummary,
    InterviewUploadComplete,
    InterviewUploadIntent,
    InterviewUploadIntentResponse,
    InterviewUploadProtocol,
    InterviewUploadRequest,
)
from app.interviews.upload_cleanup import delete_upload_if_unreferenced
from app.interviews.uploads import (
    SAFE_ATTACHMENT_CONTENT_TYPES,
    SAFE_OFFER_CONTENT_TYPES,
    CompletedMultipartUploadPart,
    InterviewUploadStore,
    StoredUpload,
)

router = APIRouter(prefix="/interviews/journal", tags=["interview-journal"])
Session = Annotated[AsyncSession, Depends(get_db_session)]
settings = get_settings()
store = InterviewUploadStore(settings)
logger = logging.getLogger(__name__)


async def _enqueue_ai_analysis(interview_id: UUID) -> None:
    try:
        job_id = await enqueue_intelligence_job("submit_transcription", str(interview_id))
    except Exception:
        logger.exception("Could not enqueue AI analysis interview_id=%s", interview_id)
        api_error(503, "interview_processing_unavailable", "Processing queue is unavailable")
    if job_id is None:
        api_error(503, "interview_processing_unavailable", "Processing queue is unavailable")


def _media_upload_rules(content_type: str) -> tuple[tuple[str, ...], int]:
    normalized = content_type.split(";", 1)[0].strip().lower()
    if normalized.startswith("video/"):
        return ("video",), settings.interview_video_max_bytes
    if normalized.startswith("audio/"):
        return ("audio",), settings.interview_audio_max_bytes
    api_error(
        415,
        "unsupported_interview_file_type",
        "The selected file type is not supported",
    )


def _upload_intent_read(intent: object) -> InterviewUploadIntent:
    return InterviewUploadIntent.model_validate(intent, from_attributes=True)


async def _create_upload_intent(
    user_id: UUID,
    payload: InterviewUploadRequest,
    *,
    category: str,
    resource: str,
    allowed_content_types: tuple[str, ...],
    max_bytes: int,
) -> InterviewUploadIntentResponse:
    if payload.upload_protocol is InterviewUploadProtocol.MULTIPART_V1:
        intent = await store.create_multipart_upload_intent(
            user_id=user_id,
            category=category,
            resource=resource,
            filename=payload.filename,
            content_type=payload.content_type,
            size=payload.size,
            allowed_content_types=allowed_content_types,
            max_bytes=max_bytes,
        )
        return InterviewMultipartUploadIntent.model_validate(intent, from_attributes=True)
    return _upload_intent_read(
        store.create_upload_intent(
            user_id=user_id,
            category=category,
            filename=payload.filename,
            content_type=payload.content_type,
            size=payload.size,
            allowed_content_types=allowed_content_types,
            max_bytes=max_bytes,
        )
    )


async def _complete_upload(
    user_id: UUID,
    payload: InterviewUploadComplete,
    *,
    category: str,
    resource: str,
    allowed_content_types: tuple[str, ...],
    max_bytes: int,
) -> StoredUpload:
    if payload.upload_protocol is InterviewUploadProtocol.MULTIPART_V1:
        if payload.upload_id is None or payload.upload_token is None:
            api_error(422, "invalid_interview_upload", "Multipart upload metadata is invalid")
        return await store.complete_multipart_upload(
            user_id=user_id,
            category=category,
            resource=resource,
            storage_key=payload.storage_key,
            upload_id=payload.upload_id,
            upload_token=payload.upload_token,
            filename=payload.filename,
            content_type=payload.content_type,
            expected_size=payload.size,
            parts=tuple(
                CompletedMultipartUploadPart(
                    part_number=part.part_number,
                    etag=part.etag,
                )
                for part in payload.parts
            ),
            allowed_content_types=allowed_content_types,
            max_bytes=max_bytes,
        )
    return await store.complete_upload(
        user_id=user_id,
        category=category,
        storage_key=payload.storage_key,
        filename=payload.filename,
        content_type=payload.content_type,
        expected_size=payload.size,
        allowed_content_types=allowed_content_types,
        max_bytes=max_bytes,
    )


@router.get("/companies", response_model=list[CompanyOption])
async def journal_company_suggestions(
    session: Session,
    student: JournalUser,
    q: str = Query(min_length=1, max_length=240),
    limit: int = Query(default=8, ge=1, le=20),
) -> list[CompanyOption]:
    companies = await suggest_companies(session, q, limit)
    return [CompanyOption(id=company.id, name=company.name) for company in companies]


@router.get("/directions", response_model=list[InterviewDirectionOption])
async def journal_directions(
    session: Session, student: JournalUser
) -> list[InterviewDirectionOption]:
    return await list_interview_directions(session, student)


@router.get("/tracks", response_model=list[InterviewProcessSummary])
async def journal_tracks(
    session: Session,
    student: JournalUser,
    status_filter: Literal["all", "active", "closed", "offer"] = Query(
        default="all", alias="status"
    ),
) -> list[InterviewProcessSummary]:
    selected_status = None if status_filter == "all" else InterviewProcessStatus(status_filter)
    return await list_processes(session, student, selected_status)


@router.post("/tracks", response_model=InterviewProcessDetail, status_code=status.HTTP_201_CREATED)
async def journal_create_track(
    payload: InterviewProcessMutation, session: Session, student: JournalUser
) -> InterviewProcessDetail:
    return await create_process(session, student, payload)


@router.get("/tracks/{process_id}", response_model=InterviewProcessDetail)
async def journal_track(
    process_id: UUID, session: Session, student: JournalUser
) -> InterviewProcessDetail:
    return await process_detail(session, student, process_id)


@router.delete(
    "/tracks/{process_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def journal_delete_track(
    process_id: UUID, session: Session, student: JournalUser
) -> Response:
    storage_keys = await delete_own_process(session, student, process_id)
    for storage_key in storage_keys:
        await delete_upload_if_unreferenced(session, store, storage_key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/tracks/{process_id}", response_model=InterviewProcessDetail)
async def journal_update_track(
    process_id: UUID,
    payload: InterviewProcessMutation,
    session: Session,
    student: JournalUser,
) -> InterviewProcessDetail:
    return await update_process(session, student, process_id, payload)


@router.patch("/tracks/{process_id}/recruiters", response_model=InterviewProcessDetail)
async def journal_track_recruiters(
    process_id: UUID,
    payload: InterviewProcessRecruitersMutation,
    session: Session,
    student: JournalUser,
) -> InterviewProcessDetail:
    return await set_process_recruiters(session, student, process_id, payload)


@router.patch("/tracks/{process_id}/outcome", response_model=InterviewProcessDetail)
async def journal_track_outcome(
    process_id: UUID,
    payload: InterviewProcessOutcomeMutation,
    session: Session,
    student: JournalUser,
) -> InterviewProcessDetail:
    return await set_process_outcome(session, student, process_id, payload)


@router.post("/tracks/{process_id}/stages", response_model=InterviewProcessDetail)
async def journal_create_stage(
    process_id: UUID,
    payload: InterviewProcessStageMutation,
    session: Session,
    student: JournalUser,
) -> InterviewProcessDetail:
    return await create_stage(session, student, process_id, payload)


@router.put("/tracks/{process_id}/stages/{stage_id}", response_model=InterviewProcessDetail)
async def journal_update_stage(
    process_id: UUID,
    stage_id: UUID,
    payload: InterviewProcessStageMutation,
    session: Session,
    student: JournalUser,
) -> InterviewProcessDetail:
    return await update_stage(session, student, process_id, stage_id, payload)


@router.post(
    "/tracks/{process_id}/stages/{stage_id}/ai-analysis",
    response_model=IntelligenceInterviewDetail,
    status_code=status.HTTP_201_CREATED,
)
async def journal_start_stage_ai_analysis(
    process_id: UUID,
    stage_id: UUID,
    session: Session,
    student: JournalUser,
) -> IntelligenceInterviewDetail:
    interview = await start_stage_ai_analysis(session, student, process_id, stage_id)
    try:
        await _enqueue_ai_analysis(interview.id)
    except Exception:
        stage = await session.get(InterviewProcessStage, stage_id)
        if stage is not None:
            stage.ai_analysis_requested_at = None
        await session.delete(interview)
        await session.commit()
        raise
    return await intelligence_detail(session, student, interview.id)


@router.post(
    "/tracks/{process_id}/stages/{stage_id}/media/upload",
    response_model=InterviewUploadIntentResponse,
)
async def journal_create_stage_media_upload(
    process_id: UUID,
    stage_id: UUID,
    payload: InterviewUploadRequest,
    session: Session,
    student: JournalUser,
) -> InterviewUploadIntentResponse:
    stage = await get_stage_model(session, student, process_id, stage_id)
    ensure_stage_editable(stage)
    allowed_types, max_bytes = _media_upload_rules(payload.content_type)
    return await _create_upload_intent(
        student.id,
        payload,
        category="media",
        resource=f"interview-stage-media:{process_id}:{stage_id}",
        allowed_content_types=allowed_types,
        max_bytes=max_bytes,
    )


@router.post(
    "/tracks/{process_id}/stages/{stage_id}/media/complete",
    response_model=InterviewProcessDetail,
)
async def journal_complete_stage_media_upload(
    process_id: UUID,
    stage_id: UUID,
    payload: InterviewUploadComplete,
    session: Session,
    student: JournalUser,
) -> InterviewProcessDetail:
    await get_stage_model(session, student, process_id, stage_id)
    allowed_types, max_bytes = _media_upload_rules(payload.content_type)
    upload = await _complete_upload(
        student.id,
        payload,
        category="media",
        resource=f"interview-stage-media:{process_id}:{stage_id}",
        allowed_content_types=allowed_types,
        max_bytes=max_bytes,
    )
    try:
        detail, previous_key = await set_stage_media(session, student, process_id, stage_id, upload)
    except Exception:
        await delete_upload_if_unreferenced(session, store, upload.storage_key)
        raise
    if previous_key != upload.storage_key:
        await store.delete(previous_key)
    return detail


@router.get(
    "/tracks/{process_id}/stages/{stage_id}/media",
    response_model=InterviewDownloadUrl,
)
async def journal_download_stage_media(
    process_id: UUID,
    stage_id: UUID,
    session: Session,
    student: JournalUser,
    inline: bool = Query(default=False),
) -> InterviewDownloadUrl:
    stage = await get_stage_model(session, student, process_id, stage_id)
    if (
        stage.media_storage_key is None
        or stage.media_filename is None
        or stage.media_content_type is None
        or stage.media_size is None
    ):
        api_error(404, "interview_media_not_found", "Interview media was not found")
    upload = await ensure_stage_media_browser_playable(session, stage, store)
    return InterviewDownloadUrl(
        url=store.download_url(
            upload,
            inline=inline,
        )
    )


@router.delete(
    "/tracks/{process_id}/stages/{stage_id}/media",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def journal_delete_stage_media(
    process_id: UUID, stage_id: UUID, session: Session, student: JournalUser
) -> Response:
    _, previous_key = await clear_stage_media(session, student, process_id, stage_id)
    await store.delete(previous_key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/tracks/{process_id}/stages/{stage_id}/attachments/upload",
    response_model=InterviewUploadIntentResponse,
)
async def journal_create_stage_attachment_upload(
    process_id: UUID,
    stage_id: UUID,
    payload: InterviewUploadRequest,
    session: Session,
    student: JournalUser,
) -> InterviewUploadIntentResponse:
    await ensure_stage_attachment_capacity(session, student, process_id, stage_id)
    return await _create_upload_intent(
        student.id,
        payload,
        category="attachments",
        resource=f"interview-stage-attachment:{process_id}:{stage_id}",
        allowed_content_types=SAFE_ATTACHMENT_CONTENT_TYPES,
        max_bytes=settings.interview_attachment_max_bytes,
    )


@router.post(
    "/tracks/{process_id}/stages/{stage_id}/attachments/complete",
    response_model=InterviewProcessDetail,
)
async def journal_complete_stage_attachment_upload(
    process_id: UUID,
    stage_id: UUID,
    payload: InterviewUploadComplete,
    session: Session,
    student: JournalUser,
) -> InterviewProcessDetail:
    upload = await _complete_upload(
        student.id,
        payload,
        category="attachments",
        resource=f"interview-stage-attachment:{process_id}:{stage_id}",
        allowed_content_types=SAFE_ATTACHMENT_CONTENT_TYPES,
        max_bytes=settings.interview_attachment_max_bytes,
    )
    try:
        return await add_stage_attachment(session, student, process_id, stage_id, upload)
    except Exception:
        await delete_upload_if_unreferenced(session, store, upload.storage_key)
        raise


@router.get(
    "/tracks/{process_id}/stages/{stage_id}/attachments/{attachment_id}",
    response_model=InterviewDownloadUrl,
)
async def journal_download_stage_attachment(
    process_id: UUID,
    stage_id: UUID,
    attachment_id: UUID,
    session: Session,
    student: JournalUser,
    inline: bool = Query(default=False),
) -> InterviewDownloadUrl:
    attachment = await get_stage_attachment_model(
        session, student, process_id, stage_id, attachment_id
    )
    can_open_inline = attachment.content_type.startswith("image/") or (
        attachment.content_type == "application/pdf"
    )
    return InterviewDownloadUrl(
        url=store.download_url(
            StoredUpload(
                storage_key=attachment.storage_key,
                filename=attachment.filename,
                content_type=attachment.content_type,
                size=attachment.size,
            ),
            inline=inline and can_open_inline,
        )
    )


@router.delete(
    "/tracks/{process_id}/stages/{stage_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def journal_delete_stage_attachment(
    process_id: UUID,
    stage_id: UUID,
    attachment_id: UUID,
    session: Session,
    student: JournalUser,
) -> Response:
    _, storage_key = await clear_stage_attachment(
        session, student, process_id, stage_id, attachment_id
    )
    await store.delete(storage_key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/tracks/{process_id}/offer/upload",
    response_model=InterviewUploadIntentResponse,
)
async def journal_create_offer_upload(
    process_id: UUID,
    payload: InterviewUploadRequest,
    session: Session,
    student: JournalUser,
) -> InterviewUploadIntentResponse:
    await get_process_model(session, student, process_id)
    return await _create_upload_intent(
        student.id,
        payload,
        category="offers",
        resource=f"interview-offer:{process_id}",
        allowed_content_types=SAFE_OFFER_CONTENT_TYPES,
        max_bytes=settings.interview_offer_max_bytes,
    )


@router.post(
    "/tracks/{process_id}/offer/complete",
    response_model=InterviewProcessDetail,
)
async def journal_complete_offer_upload(
    process_id: UUID,
    payload: InterviewUploadComplete,
    session: Session,
    student: JournalUser,
) -> InterviewProcessDetail:
    await get_process_model(session, student, process_id)
    upload = await _complete_upload(
        student.id,
        payload,
        category="offers",
        resource=f"interview-offer:{process_id}",
        allowed_content_types=SAFE_OFFER_CONTENT_TYPES,
        max_bytes=settings.interview_offer_max_bytes,
    )
    try:
        detail, previous_key = await set_offer_file(session, student, process_id, upload)
    except Exception:
        await delete_upload_if_unreferenced(session, store, upload.storage_key)
        raise
    if previous_key != upload.storage_key:
        await store.delete(previous_key)
    return detail


@router.get("/tracks/{process_id}/offer", response_model=InterviewDownloadUrl)
async def journal_download_offer(
    process_id: UUID, session: Session, student: JournalUser
) -> InterviewDownloadUrl:
    process = await get_process_model(session, student, process_id)
    if (
        process.offer_storage_key is None
        or process.offer_filename is None
        or process.offer_content_type is None
        or process.offer_size is None
    ):
        api_error(404, "interview_offer_not_found", "Offer file was not found")
    return InterviewDownloadUrl(
        url=store.download_url(
            StoredUpload(
                storage_key=process.offer_storage_key,
                filename=process.offer_filename,
                content_type=process.offer_content_type,
                size=process.offer_size,
            )
        )
    )


@router.delete(
    "/tracks/{process_id}/offer",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def journal_delete_offer(
    process_id: UUID, session: Session, student: JournalUser
) -> Response:
    _, previous_key = await cancel_offer(session, student, process_id)
    await store.delete(previous_key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
