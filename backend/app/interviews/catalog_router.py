import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CatalogUser
from app.auth.web_session import SignedPayloadError
from app.core.config import get_settings
from app.core.errors import api_error
from app.db.session import get_db_session
from app.interviews.catalog_service import (
    catalog_company_detail,
    create_catalog_comment,
    delete_catalog_comment,
    get_catalog_attachment,
    get_catalog_stage,
    list_catalog_authors,
    list_catalog_companies,
    list_catalog_directions,
    list_catalog_view_history,
    mark_catalog_stage_viewed,
    remove_catalog_favorite,
    set_catalog_favorite,
)
from app.interviews.media import ensure_stage_media_browser_playable
from app.interviews.models import (
    InterviewMediaAnonymizationStatus,
    InterviewProcess,
    InterviewProcessStage,
    InterviewStageType,
)
from app.interviews.protected_stream import (
    create_interview_stream_ticket,
    read_interview_stream_ticket,
)
from app.interviews.schemas import (
    InterviewCatalogAuthorRead,
    InterviewCatalogCommentMutation,
    InterviewCatalogCommentRead,
    InterviewCatalogCompanyDetail,
    InterviewCatalogCompanyPage,
    InterviewCatalogHistoryPage,
    InterviewCatalogMediaKind,
    InterviewDirectionOption,
    InterviewDownloadUrl,
)
from app.interviews.uploads import InterviewUploadStore, StoredUpload
from app.media.delivery import direct_private_media_response
from app.mentors.models import MentorStudent
from app.users.models import User, UserRole
from app.users.privacy import public_identity_is_hidden

router = APIRouter(prefix="/interviews/catalog", tags=["interview-catalog"])
Session = Annotated[AsyncSession, Depends(get_db_session)]
store = InterviewUploadStore(get_settings())
settings = get_settings()
STREAM_COOKIE = "interview_catalog_stream"
RANGE_PATTERN = re.compile(r"bytes=(?:\d+-\d*|-\d+)")


def _stream_secret() -> str:
    if settings.web_session_secret is not None:
        return settings.web_session_secret.get_secret_value()
    return settings.s3_secret_access_key.get_secret_value()


async def _catalog_media_for_viewer(
    session: AsyncSession, viewer: User, stage: InterviewProcessStage
) -> tuple[StoredUpload, bool]:
    use_anonymized = await _catalog_uses_anonymized_artifacts(session, viewer, stage)
    if use_anonymized:
        if (
            stage.media_anonymization_status is not InterviewMediaAnonymizationStatus.READY
            or stage.anonymized_media_storage_key is None
            or stage.anonymized_media_filename is None
            or stage.anonymized_media_content_type is None
            or stage.anonymized_media_size is None
        ):
            api_error(
                409,
                "interview_media_anonymization_pending",
                "The anonymous recording is still being prepared",
            )
        return (
            StoredUpload(
                storage_key=stage.anonymized_media_storage_key,
                filename=stage.anonymized_media_filename,
                content_type=stage.anonymized_media_content_type,
                size=stage.anonymized_media_size,
            ),
            True,
        )
    if (
        stage.media_storage_key is None
        or stage.media_filename is None
        or stage.media_content_type is None
        or stage.media_size is None
    ):
        api_error(404, "interview_media_not_found", "Interview media was not found")
    return (
        StoredUpload(
            storage_key=stage.media_storage_key,
            filename=stage.media_filename,
            content_type=stage.media_content_type,
            size=stage.media_size,
        ),
        False,
    )


async def _catalog_uses_anonymized_artifacts(
    session: AsyncSession, viewer: User, stage: InterviewProcessStage
) -> bool:
    owner = await session.scalar(
        select(User)
        .join(InterviewProcess, InterviewProcess.user_id == User.id)
        .where(InterviewProcess.id == stage.process_id)
    )
    if owner is None:
        api_error(404, "interview_media_owner_not_found", "Interview author was not found")
    can_view_original = viewer.role is UserRole.ADMIN or viewer.id == owner.id
    if not can_view_original and viewer.role is UserRole.MENTOR:
        can_view_original = (
            await session.scalar(
                select(MentorStudent.student_id).where(
                    MentorStudent.mentor_id == viewer.id,
                    MentorStudent.student_id == owner.id,
                )
            )
            is not None
        )
    return public_identity_is_hidden(owner) and not can_view_original


@router.get("/directions", response_model=list[InterviewDirectionOption])
async def catalog_directions(
    session: Session, student: CatalogUser
) -> list[InterviewDirectionOption]:
    return await list_catalog_directions(session, student)


@router.get("/authors", response_model=list[InterviewCatalogAuthorRead])
async def catalog_authors(
    session: Session, student: CatalogUser
) -> list[InterviewCatalogAuthorRead]:
    return await list_catalog_authors(session, student)


@router.get("/companies", response_model=InterviewCatalogCompanyPage)
async def catalog_companies(
    session: Session,
    student: CatalogUser,
    q: str | None = Query(default=None, min_length=1, max_length=240),
    author_id: UUID | None = None,
    track_id: UUID | None = None,
    stage_type: InterviewStageType | None = None,
    has_offer: bool = False,
    media_kind: InterviewCatalogMediaKind | None = None,
    has_ai_review: bool = False,
    favorites_only: bool = False,
    recruiter_username: str | None = Query(default=None, min_length=1, max_length=32),
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> InterviewCatalogCompanyPage:
    return await list_catalog_companies(
        session,
        student,
        q,
        author_id=author_id,
        track_id=track_id,
        stage_type=stage_type,
        has_offer=has_offer,
        media_kind=media_kind,
        has_ai_review=has_ai_review,
        favorites_only=favorites_only,
        recruiter_username=recruiter_username,
        limit=limit,
        offset=offset,
    )


@router.get("/companies/{company_id}", response_model=InterviewCatalogCompanyDetail)
async def catalog_company(
    company_id: UUID,
    session: Session,
    student: CatalogUser,
    author_id: UUID | None = None,
    track_id: UUID | None = None,
    stage_type: InterviewStageType | None = None,
    has_offer: bool = False,
    media_kind: InterviewCatalogMediaKind | None = None,
    has_ai_review: bool = False,
    favorites_only: bool = False,
    recruiter_username: str | None = Query(default=None, min_length=1, max_length=32),
) -> InterviewCatalogCompanyDetail:
    return await catalog_company_detail(
        session,
        student,
        company_id,
        author_id=author_id,
        track_id=track_id,
        stage_type=stage_type,
        has_offer=has_offer,
        media_kind=media_kind,
        has_ai_review=has_ai_review,
        favorites_only=favorites_only,
        recruiter_username=recruiter_username,
    )


@router.get("/history", response_model=InterviewCatalogHistoryPage)
async def catalog_view_history(
    session: Session,
    student: CatalogUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> InterviewCatalogHistoryPage:
    return await list_catalog_view_history(session, student, limit=limit, offset=offset)


@router.put(
    "/stages/{stage_id}/view",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def catalog_mark_stage_viewed(
    stage_id: UUID, session: Session, student: CatalogUser
) -> Response:
    await mark_catalog_stage_viewed(session, student, stage_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/stages/{stage_id}/favorite",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def catalog_favorite_stage(
    stage_id: UUID, session: Session, student: CatalogUser
) -> Response:
    await set_catalog_favorite(session, student, stage_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/stages/{stage_id}/favorite",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def catalog_unfavorite_stage(
    stage_id: UUID, session: Session, student: CatalogUser
) -> Response:
    await remove_catalog_favorite(session, student, stage_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/stages/{stage_id}/media", response_model=InterviewDownloadUrl)
async def catalog_stage_media(
    stage_id: UUID,
    session: Session,
    student: CatalogUser,
    request: Request,
    response: Response,
) -> InterviewDownloadUrl:
    stage = await get_catalog_stage(session, student, stage_id)
    _, is_anonymized = await _catalog_media_for_viewer(session, student, stage)
    await mark_catalog_stage_viewed(session, student, stage_id)
    if not is_anonymized:
        await ensure_stage_media_browser_playable(session, stage, store)
    ticket = create_interview_stream_ticket(
        user_id=student.id,
        stage_id=stage.id,
        user_agent=request.headers.get("user-agent", ""),
        secret=_stream_secret(),
        ttl_seconds=settings.interview_stream_ticket_ttl_seconds,
    )
    media_path = f"/api/v1/interviews/catalog/stages/{stage.id}/media"
    response.set_cookie(
        key=STREAM_COOKIE,
        value=ticket,
        max_age=settings.interview_stream_ticket_ttl_seconds,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        path=media_path,
    )
    return InterviewDownloadUrl(url=f"{media_path}/stream")


@router.get("/stages/{stage_id}/media/stream", response_model=None)
async def catalog_stream_stage_media(
    stage_id: UUID,
    session: Session,
    request: Request,
) -> RedirectResponse:
    ticket = request.cookies.get(STREAM_COOKIE)
    if ticket is None:
        api_error(401, "interview_stream_ticket_required", "Playback session is required")
    try:
        user_id, ticket_stage_id = read_interview_stream_ticket(
            ticket,
            user_agent=request.headers.get("user-agent", ""),
            secret=_stream_secret(),
        )
    except SignedPayloadError:
        api_error(401, "invalid_interview_stream_ticket", "Playback session has expired")
    if ticket_stage_id != stage_id:
        api_error(401, "invalid_interview_stream_ticket", "Playback session is invalid")

    destination = request.headers.get("sec-fetch-dest")
    if destination is not None and destination not in {"audio", "video"}:
        api_error(403, "interview_media_player_required", "Use the platform media player")

    user = await session.get(User, user_id)
    if (
        user is None
        or user.role not in {UserRole.STUDENT, UserRole.MENTOR, UserRole.ADMIN}
        or (user.role is UserRole.STUDENT and not user.is_active)
    ):
        api_error(403, "interview_stream_access_denied", "Playback access is not available")
    stage = await get_catalog_stage(session, user, stage_id)
    upload, _ = await _catalog_media_for_viewer(session, user, stage)

    range_header = request.headers.get("range")
    if range_header is not None and RANGE_PATTERN.fullmatch(range_header) is None:
        api_error(416, "invalid_interview_media_range", "Requested range is invalid")
    return direct_private_media_response(
        store,
        upload,
        expires_in=settings.media_stream_redirect_ttl_seconds,
    )


@router.get(
    "/stages/{stage_id}/attachments/{attachment_id}",
    response_model=InterviewDownloadUrl,
)
async def catalog_stage_attachment(
    stage_id: UUID,
    attachment_id: UUID,
    session: Session,
    student: CatalogUser,
    inline: bool = Query(default=False),
) -> InterviewDownloadUrl:
    attachment = await get_catalog_attachment(session, student, stage_id, attachment_id)
    stage = await get_catalog_stage(session, student, stage_id)
    is_anonymized = await _catalog_uses_anonymized_artifacts(session, student, stage)
    if is_anonymized:
        api_error(
            404,
            "interview_attachment_hidden",
            "Attachments are hidden for this anonymous interview",
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


@router.post(
    "/stages/{stage_id}/comments",
    response_model=InterviewCatalogCommentRead,
    status_code=status.HTTP_201_CREATED,
)
async def catalog_create_comment(
    stage_id: UUID,
    payload: InterviewCatalogCommentMutation,
    session: Session,
    student: CatalogUser,
) -> InterviewCatalogCommentRead:
    return await create_catalog_comment(session, student, stage_id, payload)


@router.delete(
    "/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def catalog_delete_comment(
    comment_id: UUID, session: Session, student: CatalogUser
) -> Response:
    await delete_catalog_comment(session, student, comment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
