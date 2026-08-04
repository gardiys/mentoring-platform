import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import RedirectResponse
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
)
from app.interviews.media import ensure_stage_media_browser_playable
from app.interviews.models import InterviewStageType
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
    InterviewCatalogMediaKind,
    InterviewDirectionOption,
    InterviewDownloadUrl,
)
from app.interviews.uploads import InterviewUploadStore, StoredUpload
from app.media.delivery import direct_private_media_response
from app.users.models import User, UserRole

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
    )


@router.get("/stages/{stage_id}/media", response_model=InterviewDownloadUrl)
async def catalog_stage_media(
    stage_id: UUID,
    session: Session,
    student: CatalogUser,
    request: Request,
    response: Response,
) -> InterviewDownloadUrl:
    stage = await get_catalog_stage(session, student, stage_id)
    if (
        stage.media_storage_key is None
        or stage.media_filename is None
        or stage.media_content_type is None
        or stage.media_size is None
    ):
        api_error(404, "interview_media_not_found", "Interview media was not found")
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
    if (
        stage.media_storage_key is None
        or stage.media_filename is None
        or stage.media_content_type is None
        or stage.media_size is None
    ):
        api_error(404, "interview_media_not_found", "Interview media was not found")

    range_header = request.headers.get("range")
    if range_header is not None and RANGE_PATTERN.fullmatch(range_header) is None:
        api_error(416, "invalid_interview_media_range", "Requested range is invalid")
    return direct_private_media_response(
        store,
        StoredUpload(
            storage_key=stage.media_storage_key,
            filename=stage.media_filename,
            content_type=stage.media_content_type,
            size=stage.media_size,
        ),
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
