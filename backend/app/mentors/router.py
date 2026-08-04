from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import MentorUser, StudentUser
from app.core.config import get_settings
from app.core.errors import api_error
from app.db.session import get_db_session
from app.interviews.journal_service import (
    get_process_model,
    get_stage_attachment_model,
    get_stage_model,
)
from app.interviews.media import ensure_stage_media_browser_playable
from app.interviews.schemas import (
    InterviewCatalogCommentMutation,
    InterviewCatalogCommentRead,
    InterviewDownloadUrl,
    InterviewUploadComplete,
    InterviewUploadIntent,
    InterviewUploadRequest,
)
from app.interviews.uploads import InterviewUploadStore, StoredUpload
from app.mentors.models import (
    MentorDocumentKind,
    MentorStudentDocument,
    StudentLearningStatus,
)
from app.mentors.schemas import (
    MentorDocumentContentMutation,
    MentorDocumentRead,
    MentorInterviewDetail,
    MentorNoteMutation,
    MentorNoteRead,
    MentorStudentDetail,
    MentorStudentPage,
    MentorStudentStateMutation,
    MockInterviewFeedbackMutation,
    MockInterviewMutation,
    MockInterviewRead,
)
from app.mentors.service import (
    add_interview_feedback,
    assigned_student,
    complete_mock,
    create_mock,
    create_note,
    delete_note,
    get_document,
    get_mock,
    list_students,
    mentor_interview_detail,
    set_document_file,
    set_document_text,
    set_mock_media,
    student_detail,
    student_mock_interviews,
    update_note,
    update_student_state,
)

router = APIRouter(prefix="/mentor", tags=["mentor"])
Session = Annotated[AsyncSession, Depends(get_db_session)]
settings = get_settings()
store = InterviewUploadStore(settings)

DOCUMENT_TYPES = (
    "text",
    "image",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/rtf",
)


def _upload_intent(intent: object) -> InterviewUploadIntent:
    return InterviewUploadIntent.model_validate(intent, from_attributes=True)


def _stored_upload(
    storage_key: str | None,
    filename: str | None,
    content_type: str | None,
    size: int | None,
    *,
    code: str,
    message: str,
) -> StoredUpload:
    if storage_key is None or filename is None or content_type is None or size is None:
        api_error(404, code, message)
    return StoredUpload(
        storage_key=storage_key,
        filename=filename,
        content_type=content_type,
        size=size,
    )


def _media_rules(content_type: str) -> tuple[tuple[str, ...], int]:
    normalized = content_type.split(";", 1)[0].strip().lower()
    if normalized.startswith("video/"):
        return ("video",), settings.interview_video_max_bytes
    if normalized.startswith("audio/"):
        return ("audio",), settings.interview_audio_max_bytes
    api_error(415, "unsupported_mock_media_type", "Select an audio or video recording")


@router.get("/students", response_model=MentorStudentPage)
async def mentor_students(
    session: Session,
    mentor: MentorUser,
    query: str | None = Query(default=None, max_length=200),
    track_id: UUID | None = None,
    mentor_id: UUID | None = None,
    without_mentor: bool = False,
    is_active: bool | None = None,
    learning_status: Annotated[list[StudentLearningStatus] | None, Query()] = None,
    limit: int = Query(default=12, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> MentorStudentPage:
    return await list_students(
        session,
        mentor,
        query=query,
        track_id=track_id,
        mentor_id=mentor_id,
        without_mentor=without_mentor,
        is_active=is_active,
        learning_statuses=learning_status,
        limit=limit,
        offset=offset,
    )


@router.get("/students/{student_id}", response_model=MentorStudentDetail)
async def mentor_student(
    student_id: UUID, session: Session, mentor: MentorUser
) -> MentorStudentDetail:
    return await student_detail(session, mentor, student_id)


@router.patch("/students/{student_id}/state", response_model=MentorStudentDetail)
async def mentor_student_state(
    student_id: UUID,
    payload: MentorStudentStateMutation,
    session: Session,
    mentor: MentorUser,
) -> MentorStudentDetail:
    return await update_student_state(session, mentor, student_id, payload)


@router.post(
    "/students/{student_id}/notes",
    response_model=MentorNoteRead,
    status_code=status.HTTP_201_CREATED,
)
async def mentor_create_note(
    student_id: UUID,
    payload: MentorNoteMutation,
    session: Session,
    mentor: MentorUser,
) -> MentorNoteRead:
    return await create_note(session, mentor, student_id, payload.body)


@router.put("/students/{student_id}/notes/{note_id}", response_model=MentorNoteRead)
async def mentor_update_note(
    student_id: UUID,
    note_id: UUID,
    payload: MentorNoteMutation,
    session: Session,
    mentor: MentorUser,
) -> MentorNoteRead:
    return await update_note(session, mentor, student_id, note_id, payload.body)


@router.delete(
    "/students/{student_id}/notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def mentor_delete_note(
    student_id: UUID, note_id: UUID, session: Session, mentor: MentorUser
) -> Response:
    await delete_note(session, mentor, student_id, note_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/students/{student_id}/documents/{kind}", response_model=MentorDocumentRead)
async def mentor_set_document_text(
    student_id: UUID,
    kind: MentorDocumentKind,
    payload: MentorDocumentContentMutation,
    session: Session,
    mentor: MentorUser,
) -> MentorDocumentRead:
    document, previous_key = await set_document_text(session, mentor, student_id, kind, payload)
    await store.delete(previous_key)
    return document


@router.post(
    "/students/{student_id}/documents/{kind}/upload",
    response_model=InterviewUploadIntent,
)
async def mentor_document_upload(
    student_id: UUID,
    kind: MentorDocumentKind,
    payload: InterviewUploadRequest,
    session: Session,
    mentor: MentorUser,
) -> InterviewUploadIntent:
    await assigned_student(session, mentor, student_id)
    intent = store.create_upload_intent(
        user_id=mentor.id,
        category="mentor-document",
        filename=payload.filename,
        content_type=payload.content_type,
        size=payload.size,
        allowed_content_types=DOCUMENT_TYPES,
        max_bytes=settings.interview_attachment_max_bytes,
    )
    return _upload_intent(intent)


@router.post(
    "/students/{student_id}/documents/{kind}/complete",
    response_model=MentorDocumentRead,
)
async def mentor_document_complete(
    student_id: UUID,
    kind: MentorDocumentKind,
    payload: InterviewUploadComplete,
    session: Session,
    mentor: MentorUser,
) -> MentorDocumentRead:
    await assigned_student(session, mentor, student_id)
    upload = await store.complete_upload(
        user_id=mentor.id,
        category="mentor-document",
        storage_key=payload.storage_key,
        filename=payload.filename,
        content_type=payload.content_type,
        expected_size=payload.size,
        allowed_content_types=DOCUMENT_TYPES,
        max_bytes=settings.interview_attachment_max_bytes,
    )
    try:
        document, previous_key = await set_document_file(session, mentor, student_id, kind, upload)
    except Exception:
        await store.delete(upload.storage_key)
        raise
    await store.delete(previous_key)
    return document


@router.get("/students/{student_id}/documents/{kind}/file", response_model=InterviewDownloadUrl)
async def mentor_document_file(
    student_id: UUID,
    kind: MentorDocumentKind,
    session: Session,
    mentor: MentorUser,
    inline: bool = Query(default=True),
) -> InterviewDownloadUrl:
    document = await get_document(session, mentor, student_id, kind)
    if document is None:
        api_error(404, "mentor_document_file_not_found", "Document file was not found")
    return InterviewDownloadUrl(
        url=store.download_url(
            _stored_upload(
                document.storage_key,
                document.filename,
                document.content_type,
                document.size,
                code="mentor_document_file_not_found",
                message="Document file was not found",
            ),
            inline=inline,
        )
    )


@router.post(
    "/students/{student_id}/mock-interviews",
    response_model=MockInterviewRead,
    status_code=status.HTTP_201_CREATED,
)
async def mentor_create_mock(
    student_id: UUID,
    payload: MockInterviewMutation,
    session: Session,
    mentor: MentorUser,
) -> MockInterviewRead:
    return await create_mock(session, mentor, student_id, payload)


@router.patch(
    "/students/{student_id}/mock-interviews/{mock_id}/feedback",
    response_model=MockInterviewRead,
)
async def mentor_complete_mock(
    student_id: UUID,
    mock_id: UUID,
    payload: MockInterviewFeedbackMutation,
    session: Session,
    mentor: MentorUser,
) -> MockInterviewRead:
    return await complete_mock(session, mentor, student_id, mock_id, payload)


@router.post(
    "/students/{student_id}/mock-interviews/{mock_id}/media/upload",
    response_model=InterviewUploadIntent,
)
async def mentor_mock_media_upload(
    student_id: UUID,
    mock_id: UUID,
    payload: InterviewUploadRequest,
    session: Session,
    mentor: MentorUser,
) -> InterviewUploadIntent:
    await assigned_student(session, mentor, student_id)
    await get_mock(session, mentor, mock_id, student_id=student_id)
    allowed_types, max_bytes = _media_rules(payload.content_type)
    return _upload_intent(
        store.create_upload_intent(
            user_id=mentor.id,
            category="mock-media",
            filename=payload.filename,
            content_type=payload.content_type,
            size=payload.size,
            allowed_content_types=allowed_types,
            max_bytes=max_bytes,
        )
    )


@router.post(
    "/students/{student_id}/mock-interviews/{mock_id}/media/complete",
    response_model=MockInterviewRead,
)
async def mentor_mock_media_complete(
    student_id: UUID,
    mock_id: UUID,
    payload: InterviewUploadComplete,
    session: Session,
    mentor: MentorUser,
) -> MockInterviewRead:
    await assigned_student(session, mentor, student_id)
    await get_mock(session, mentor, mock_id, student_id=student_id)
    allowed_types, max_bytes = _media_rules(payload.content_type)
    upload = await store.complete_upload(
        user_id=mentor.id,
        category="mock-media",
        storage_key=payload.storage_key,
        filename=payload.filename,
        content_type=payload.content_type,
        expected_size=payload.size,
        allowed_content_types=allowed_types,
        max_bytes=max_bytes,
    )
    try:
        mock, previous_key = await set_mock_media(session, mentor, student_id, mock_id, upload)
    except Exception:
        await store.delete(upload.storage_key)
        raise
    await store.delete(previous_key)
    return mock


@router.get(
    "/students/{student_id}/mock-interviews/{mock_id}/media",
    response_model=InterviewDownloadUrl,
)
async def mentor_mock_media(
    student_id: UUID,
    mock_id: UUID,
    session: Session,
    mentor: MentorUser,
) -> InterviewDownloadUrl:
    await assigned_student(session, mentor, student_id)
    mock, _ = await get_mock(session, mentor, mock_id, student_id=student_id)
    return InterviewDownloadUrl(
        url=store.download_url(
            _stored_upload(
                mock.media_storage_key,
                mock.media_filename,
                mock.media_content_type,
                mock.media_size,
                code="mock_interview_media_not_found",
                message="Recording was not found",
            ),
            inline=True,
        )
    )


@router.get(
    "/students/{student_id}/interviews/{process_id}",
    response_model=MentorInterviewDetail,
)
async def mentor_interview(
    student_id: UUID,
    process_id: UUID,
    session: Session,
    mentor: MentorUser,
) -> MentorInterviewDetail:
    return await mentor_interview_detail(session, mentor, student_id, process_id)


@router.post(
    "/students/{student_id}/interviews/stages/{stage_id}/feedback",
    response_model=InterviewCatalogCommentRead,
    status_code=status.HTTP_201_CREATED,
)
async def mentor_interview_feedback(
    student_id: UUID,
    stage_id: UUID,
    payload: InterviewCatalogCommentMutation,
    session: Session,
    mentor: MentorUser,
) -> InterviewCatalogCommentRead:
    return await add_interview_feedback(session, mentor, student_id, stage_id, payload.body)


@router.get(
    "/students/{student_id}/interviews/{process_id}/stages/{stage_id}/media",
    response_model=InterviewDownloadUrl,
)
async def mentor_interview_media(
    student_id: UUID,
    process_id: UUID,
    stage_id: UUID,
    session: Session,
    mentor: MentorUser,
) -> InterviewDownloadUrl:
    await mentor_interview_detail(session, mentor, student_id, process_id)
    student, _ = await assigned_student(session, mentor, student_id, allow_any_user_for_admin=True)
    stage = await get_stage_model(session, student, process_id, stage_id)
    if (
        stage.media_storage_key is None
        or stage.media_filename is None
        or stage.media_content_type is None
        or stage.media_size is None
    ):
        api_error(404, "interview_media_not_found", "Interview media was not found")
    upload = await ensure_stage_media_browser_playable(session, stage, store)
    return InterviewDownloadUrl(url=store.download_url(upload, inline=True))


@router.get(
    "/students/{student_id}/interviews/{process_id}/stages/{stage_id}/attachments/{attachment_id}",
    response_model=InterviewDownloadUrl,
)
async def mentor_interview_attachment(
    student_id: UUID,
    process_id: UUID,
    stage_id: UUID,
    attachment_id: UUID,
    session: Session,
    mentor: MentorUser,
) -> InterviewDownloadUrl:
    await mentor_interview_detail(session, mentor, student_id, process_id)
    student, _ = await assigned_student(session, mentor, student_id, allow_any_user_for_admin=True)
    attachment = await get_stage_attachment_model(
        session, student, process_id, stage_id, attachment_id
    )
    return InterviewDownloadUrl(
        url=store.download_url(
            StoredUpload(
                storage_key=attachment.storage_key,
                filename=attachment.filename,
                content_type=attachment.content_type,
                size=attachment.size,
            ),
            inline=attachment.content_type.startswith("image/")
            or attachment.content_type == "application/pdf",
        )
    )


@router.get(
    "/students/{student_id}/interviews/{process_id}/offer",
    response_model=InterviewDownloadUrl,
)
async def mentor_interview_offer(
    student_id: UUID,
    process_id: UUID,
    session: Session,
    mentor: MentorUser,
) -> InterviewDownloadUrl:
    await mentor_interview_detail(session, mentor, student_id, process_id)
    student, _ = await assigned_student(session, mentor, student_id, allow_any_user_for_admin=True)
    process = await get_process_model(session, student, process_id)
    return InterviewDownloadUrl(
        url=store.download_url(
            _stored_upload(
                process.offer_storage_key,
                process.offer_filename,
                process.offer_content_type,
                process.offer_size,
                code="interview_offer_not_found",
                message="Offer file was not found",
            ),
            inline=True,
        )
    )


@router.get("/me/mock-interviews", response_model=list[MockInterviewRead])
async def my_mock_interviews(session: Session, student: StudentUser) -> list[MockInterviewRead]:
    return await student_mock_interviews(session, student)


@router.get("/me/mock-interviews/{mock_id}/media", response_model=InterviewDownloadUrl)
async def my_mock_interview_media(
    mock_id: UUID, session: Session, student: StudentUser
) -> InterviewDownloadUrl:
    mock, _ = await get_mock(session, student, mock_id)
    return InterviewDownloadUrl(
        url=store.download_url(
            _stored_upload(
                mock.media_storage_key,
                mock.media_filename,
                mock.media_content_type,
                mock.media_size,
                code="mock_interview_media_not_found",
                message="Recording was not found",
            ),
            inline=True,
        )
    )


@router.get("/me/documents", response_model=list[MentorDocumentRead])
async def my_mentor_documents(session: Session, student: StudentUser) -> list[MentorDocumentRead]:
    documents = list(
        await session.scalars(
            select(MentorStudentDocument)
            .where(MentorStudentDocument.student_id == student.id)
            .order_by(MentorStudentDocument.kind)
        )
    )
    return [
        MentorDocumentRead(
            id=document.id,
            kind=document.kind,
            text_content=document.text_content,
            file=(
                None
                if not all((document.filename, document.content_type, document.size))
                else {
                    "filename": document.filename,
                    "content_type": document.content_type,
                    "size": document.size,
                }
            ),
            created_at=document.created_at,
            updated_at=document.updated_at,
        )
        for document in documents
    ]


@router.get("/me/documents/{document_id}/file", response_model=InterviewDownloadUrl)
async def my_mentor_document_file(
    document_id: UUID, session: Session, student: StudentUser
) -> InterviewDownloadUrl:
    document = await session.scalar(
        select(MentorStudentDocument).where(
            MentorStudentDocument.id == document_id,
            MentorStudentDocument.student_id == student.id,
        )
    )
    if document is None:
        api_error(404, "mentor_document_file_not_found", "Document file was not found")
    return InterviewDownloadUrl(
        url=store.download_url(
            _stored_upload(
                document.storage_key,
                document.filename,
                document.content_type,
                document.size,
                code="mentor_document_file_not_found",
                message="Document file was not found",
            ),
            inline=True,
        )
    )
