from __future__ import annotations

import logging
import re
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AdminUser, CurrentUser
from app.auth.web_session import SignedPayloadError
from app.core.config import get_settings
from app.core.errors import api_error
from app.db.session import get_db_session
from app.interviews.upload_cleanup import delete_upload_if_unreferenced
from app.interviews.uploads import CompletedMultipartUploadPart
from app.media.delivery import direct_private_media_response
from app.media.models import ContentMediaProcessingStatus, ProtectedContentMedia
from app.media.normalization_queue import enqueue_content_media_normalization
from app.media.presenters import content_media_read
from app.media.protected_stream import (
    create_bound_stream_ticket,
    read_bound_stream_ticket,
)
from app.media.schemas import (
    ContentMediaMultipartUploadIntent,
    ContentMediaPlayback,
    ContentMediaUploadFinalize,
    ContentMediaUploadIntent,
    ContentMediaUploadIntentResponse,
    ContentMediaUploadProtocol,
    ContentMediaUploadRequest,
    ProtectedContentMediaRead,
)
from app.media.service import (
    attach_knowledge_media,
    attach_roadmap_media,
    delete_knowledge_media,
    delete_roadmap_media,
    knowledge_media_for_user,
    require_admin_knowledge_entry,
    require_admin_roadmap_topic,
    roadmap_media_for_user,
)
from app.media.storage import PrivateMediaStore, StoredUpload, content_media_upload_rules
from app.users.models import User, UserRole

admin_knowledge_media_router = APIRouter(
    prefix="/admin/knowledge/topics",
    tags=["admin-knowledge-media"],
)
admin_roadmap_media_router = APIRouter(
    prefix="/admin/roadmaps",
    tags=["admin-roadmap-media"],
)
admin_content_media_router = APIRouter(
    prefix="/admin/content-media",
    tags=["admin-content-media"],
)
knowledge_media_router = APIRouter(prefix="/knowledge", tags=["knowledge-media"])
roadmap_media_router = APIRouter(tags=["roadmap-media"])
Session = Annotated[AsyncSession, Depends(get_db_session)]
settings = get_settings()
store = PrivateMediaStore(settings)
STREAM_COOKIE = "protected_content_media_stream"
RANGE_PATTERN = re.compile(r"bytes=(?:\d+-\d*|-\d+)")
MediaScope = Literal["knowledge", "roadmap"]
logger = logging.getLogger(__name__)


def _stream_secret() -> str:
    if settings.web_session_secret is not None:
        return settings.web_session_secret.get_secret_value()
    return settings.s3_secret_access_key.get_secret_value()


def _ticket_kind(scope: MediaScope) -> str:
    return f"{scope}_content_media_stream"


async def _upload_intent(
    admin: User,
    payload: ContentMediaUploadRequest,
    *,
    category: str,
    resource: str,
) -> ContentMediaUploadIntentResponse:
    allowed_types, max_bytes = content_media_upload_rules(settings, payload.content_type)
    _validate_media_size(payload.size, max_bytes)
    if payload.upload_protocol is ContentMediaUploadProtocol.MULTIPART_V1:
        intent = await store.create_multipart_upload_intent(
            user_id=admin.id,
            category=category,
            resource=resource,
            filename=payload.filename,
            content_type=payload.content_type,
            size=payload.size,
            allowed_content_types=allowed_types,
            max_bytes=max_bytes,
        )
        return ContentMediaMultipartUploadIntent.model_validate(intent, from_attributes=True)
    legacy_intent = store.create_upload_intent(
        user_id=admin.id,
        category=category,
        filename=payload.filename,
        content_type=payload.content_type,
        size=payload.size,
        allowed_content_types=allowed_types,
        max_bytes=max_bytes,
    )
    return ContentMediaUploadIntent.model_validate(legacy_intent, from_attributes=True)


async def _complete_upload(
    admin: User,
    payload: ContentMediaUploadFinalize,
    *,
    category: str,
    resource: str,
) -> StoredUpload:
    allowed_types, max_bytes = content_media_upload_rules(settings, payload.content_type)
    _validate_media_size(payload.size, max_bytes)
    if payload.upload_protocol is ContentMediaUploadProtocol.MULTIPART_V1:
        if payload.upload_id is None or payload.upload_token is None:
            api_error(422, "invalid_interview_upload", "Multipart upload metadata is invalid")
        return await store.complete_multipart_upload(
            user_id=admin.id,
            category=category,
            resource=resource,
            storage_key=payload.storage_key,
            upload_id=payload.upload_id,
            upload_token=payload.upload_token,
            filename=payload.filename,
            content_type=payload.content_type,
            expected_size=payload.size,
            parts=tuple(
                CompletedMultipartUploadPart(part_number=part.part_number, etag=part.etag)
                for part in payload.parts
            ),
            allowed_content_types=allowed_types,
            max_bytes=max_bytes,
        )
    return await store.complete_upload(
        user_id=admin.id,
        category=category,
        storage_key=payload.storage_key,
        filename=payload.filename,
        content_type=payload.content_type,
        expected_size=payload.size,
        allowed_content_types=allowed_types,
        max_bytes=max_bytes,
    )


def _validate_media_size(size: int, max_bytes: int) -> None:
    if size > max_bytes:
        api_error(
            413,
            "content_media_too_large",
            "The selected media file is too large",
        )


@admin_knowledge_media_router.post(
    "/{topic_id}/entries/{entry_id}/media/upload-url",
    response_model=ContentMediaUploadIntentResponse,
)
async def admin_knowledge_media_upload_url(
    topic_id: UUID,
    entry_id: UUID,
    payload: ContentMediaUploadRequest,
    session: Session,
    admin: AdminUser,
) -> ContentMediaUploadIntentResponse:
    await require_admin_knowledge_entry(session, topic_id, entry_id)
    return await _upload_intent(
        admin,
        payload,
        category="knowledge-media",
        resource=f"knowledge-media:{topic_id}:{entry_id}",
    )


@admin_knowledge_media_router.post(
    "/{topic_id}/entries/{entry_id}/media/finalize",
    response_model=ProtectedContentMediaRead,
    status_code=status.HTTP_201_CREATED,
)
async def admin_finalize_knowledge_media(
    topic_id: UUID,
    entry_id: UUID,
    payload: ContentMediaUploadFinalize,
    session: Session,
    admin: AdminUser,
) -> ProtectedContentMediaRead:
    entry = await require_admin_knowledge_entry(session, topic_id, entry_id)
    upload = await _complete_upload(
        admin,
        payload,
        category="knowledge-media",
        resource=f"knowledge-media:{topic_id}:{entry_id}",
    )
    try:
        media = await attach_knowledge_media(
            session,
            entry_id=entry.id,
            uploaded_by_user_id=admin.id,
            upload=upload,
            payload=payload,
        )
        await _enqueue_normalization_if_needed(media)
        return media
    except Exception:
        await delete_upload_if_unreferenced(session, store, upload.storage_key)
        raise


@admin_knowledge_media_router.delete(
    "/{topic_id}/entries/{entry_id}/media/{media_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def admin_delete_knowledge_media(
    topic_id: UUID,
    entry_id: UUID,
    media_id: UUID,
    session: Session,
    _admin: AdminUser,
) -> Response:
    storage_keys = await delete_knowledge_media(
        session,
        topic_id=topic_id,
        entry_id=entry_id,
        media_id=media_id,
    )
    for storage_key in storage_keys:
        await store.delete(storage_key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@admin_roadmap_media_router.post(
    "/{roadmap_id}/sections/{section_id}/topics/{topic_id}/media/upload-url",
    response_model=ContentMediaUploadIntentResponse,
)
async def admin_roadmap_media_upload_url(
    roadmap_id: UUID,
    section_id: UUID,
    topic_id: UUID,
    payload: ContentMediaUploadRequest,
    session: Session,
    admin: AdminUser,
) -> ContentMediaUploadIntentResponse:
    await require_admin_roadmap_topic(session, roadmap_id, section_id, topic_id)
    return await _upload_intent(
        admin,
        payload,
        category="roadmap-media",
        resource=f"roadmap-media:{roadmap_id}:{section_id}:{topic_id}",
    )


@admin_roadmap_media_router.post(
    "/{roadmap_id}/sections/{section_id}/topics/{topic_id}/media/finalize",
    response_model=ProtectedContentMediaRead,
    status_code=status.HTTP_201_CREATED,
)
async def admin_finalize_roadmap_media(
    roadmap_id: UUID,
    section_id: UUID,
    topic_id: UUID,
    payload: ContentMediaUploadFinalize,
    session: Session,
    admin: AdminUser,
) -> ProtectedContentMediaRead:
    topic = await require_admin_roadmap_topic(
        session,
        roadmap_id,
        section_id,
        topic_id,
    )
    upload = await _complete_upload(
        admin,
        payload,
        category="roadmap-media",
        resource=f"roadmap-media:{roadmap_id}:{section_id}:{topic_id}",
    )
    try:
        media = await attach_roadmap_media(
            session,
            topic_id=topic.id,
            uploaded_by_user_id=admin.id,
            upload=upload,
            payload=payload,
        )
        await _enqueue_normalization_if_needed(media)
        return media
    except Exception:
        await delete_upload_if_unreferenced(session, store, upload.storage_key)
        raise


@admin_roadmap_media_router.delete(
    "/{roadmap_id}/sections/{section_id}/topics/{topic_id}/media/{media_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def admin_delete_roadmap_media(
    roadmap_id: UUID,
    section_id: UUID,
    topic_id: UUID,
    media_id: UUID,
    session: Session,
    _admin: AdminUser,
) -> Response:
    storage_keys = await delete_roadmap_media(
        session,
        roadmap_id=roadmap_id,
        section_id=section_id,
        topic_id=topic_id,
        media_id=media_id,
    )
    for storage_key in storage_keys:
        await store.delete(storage_key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _enqueue_normalization_if_needed(media: ProtectedContentMediaRead) -> None:
    if media.processing_status is not ContentMediaProcessingStatus.QUEUED:
        return
    try:
        await enqueue_content_media_normalization(str(media.id))
    except Exception:
        # The durable queued state is authoritative. The worker reconciler will
        # enqueue it after Redis or the API connection recovers.
        logger.exception(
            "Could not enqueue content-media normalization media_id=%s; "
            "the worker reconciler will retry",
            media.id,
        )


@admin_content_media_router.post(
    "/{media_id}/normalization/retry",
    response_model=ProtectedContentMediaRead,
)
async def retry_content_media_normalization(
    media_id: UUID,
    session: Session,
    _admin: AdminUser,
) -> ProtectedContentMediaRead:
    media = await session.get(ProtectedContentMedia, media_id, with_for_update=True)
    if media is None:
        api_error(404, "content_media_not_found", "Media attachment was not found")
    if media.content_type.split(";", 1)[0].strip().lower() not in {
        "video/mp4",
        "video/quicktime",
    }:
        api_error(
            409,
            "content_media_normalization_not_supported",
            "Only MP4 and MOV videos can be prepared for browser playback",
        )
    if media.processing_status is ContentMediaProcessingStatus.READY:
        api_error(
            409,
            "content_media_already_ready",
            "The video is already ready for playback",
        )
    if media.processing_status is ContentMediaProcessingStatus.FAILED:
        media.processing_status = ContentMediaProcessingStatus.QUEUED
        media.normalization_source_key = media.storage_key
        media.normalization_started_at = None
        media.normalization_completed_at = None
        media.normalization_error_code = None
        media.normalization_error_message = None
        media.normalization_revision += 1
        await session.commit()
        await session.refresh(media)
    response = content_media_read(media)
    await _enqueue_normalization_if_needed(response)
    return response


def _set_playback_ticket(
    *,
    response: Response,
    request: Request,
    user: User,
    media_id: UUID,
    scope: MediaScope,
    media_path: str,
) -> ContentMediaPlayback:
    ticket = create_bound_stream_ticket(
        kind=_ticket_kind(scope),
        resource_claim="media_id",
        user_id=user.id,
        resource_id=media_id,
        user_agent=request.headers.get("user-agent", ""),
        secret=_stream_secret(),
        ttl_seconds=settings.interview_stream_ticket_ttl_seconds,
    )
    response.set_cookie(
        key=STREAM_COOKIE,
        value=ticket,
        max_age=settings.interview_stream_ticket_ttl_seconds,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        path=media_path,
    )
    return ContentMediaPlayback(
        url=f"{media_path}/stream",
        expires_in=settings.interview_stream_ticket_ttl_seconds,
    )


@knowledge_media_router.get(
    "/entries/{entry_slug}/media/{media_id}/playback",
    response_model=ContentMediaPlayback,
)
async def knowledge_media_playback(
    entry_slug: str,
    media_id: UUID,
    session: Session,
    current_user: CurrentUser,
    request: Request,
    response: Response,
) -> ContentMediaPlayback:
    media = await knowledge_media_for_user(
        session,
        current_user,
        entry_slug=entry_slug,
        media_id=media_id,
    )
    _require_media_ready(media)
    media_path = f"/api/v1/knowledge/entries/{entry_slug}/media/{media_id}"
    return _set_playback_ticket(
        response=response,
        request=request,
        user=current_user,
        media_id=media_id,
        scope="knowledge",
        media_path=media_path,
    )


@knowledge_media_router.get(
    "/entries/{entry_slug}/media/{media_id}/stream",
    response_model=None,
)
async def stream_knowledge_media(
    entry_slug: str,
    media_id: UUID,
    session: Session,
    request: Request,
) -> RedirectResponse:
    user = await _ticket_user(request, session, media_id=media_id, scope="knowledge")
    media = await knowledge_media_for_user(
        session,
        user,
        entry_slug=entry_slug,
        media_id=media_id,
    )
    return await _stream_media(request, media)


@roadmap_media_router.get(
    "/topics/{topic_id}/media/{media_id}/playback",
    response_model=ContentMediaPlayback,
)
async def roadmap_media_playback(
    topic_id: UUID,
    media_id: UUID,
    session: Session,
    current_user: CurrentUser,
    request: Request,
    response: Response,
) -> ContentMediaPlayback:
    media = await roadmap_media_for_user(
        session,
        current_user,
        topic_id=topic_id,
        media_id=media_id,
    )
    _require_media_ready(media)
    media_path = f"/api/v1/topics/{topic_id}/media/{media_id}"
    return _set_playback_ticket(
        response=response,
        request=request,
        user=current_user,
        media_id=media_id,
        scope="roadmap",
        media_path=media_path,
    )


@roadmap_media_router.get(
    "/topics/{topic_id}/media/{media_id}/stream",
    response_model=None,
)
async def stream_roadmap_media(
    topic_id: UUID,
    media_id: UUID,
    session: Session,
    request: Request,
) -> RedirectResponse:
    user = await _ticket_user(request, session, media_id=media_id, scope="roadmap")
    media = await roadmap_media_for_user(
        session,
        user,
        topic_id=topic_id,
        media_id=media_id,
    )
    return await _stream_media(request, media)


async def _ticket_user(
    request: Request,
    session: AsyncSession,
    *,
    media_id: UUID,
    scope: MediaScope,
) -> User:
    ticket = request.cookies.get(STREAM_COOKIE)
    if ticket is None:
        api_error(401, "content_media_ticket_required", "Playback session is required")
    try:
        user_id, ticket_media_id = read_bound_stream_ticket(
            ticket,
            expected_kind=_ticket_kind(scope),
            resource_claim="media_id",
            user_agent=request.headers.get("user-agent", ""),
            secret=_stream_secret(),
        )
    except SignedPayloadError:
        api_error(401, "invalid_content_media_ticket", "Playback session has expired")
    if ticket_media_id != media_id:
        api_error(401, "invalid_content_media_ticket", "Playback session is invalid")

    destination = request.headers.get("sec-fetch-dest")
    if destination is not None and destination not in {"audio", "video"}:
        api_error(403, "content_media_player_required", "Use the platform media player")

    user = await session.get(User, user_id)
    if (
        user is None
        or user.role not in {UserRole.STUDENT, UserRole.MENTOR, UserRole.ADMIN}
        or (user.role is UserRole.STUDENT and not user.is_active)
    ):
        api_error(403, "content_media_access_denied", "Playback access is not available")
    return user


async def _stream_media(
    request: Request,
    media: ProtectedContentMedia,
) -> RedirectResponse:
    _require_media_ready(media)
    range_header = request.headers.get("range")
    if range_header is not None and RANGE_PATTERN.fullmatch(range_header) is None:
        api_error(416, "invalid_content_media_range", "Requested range is invalid")
    upload = StoredUpload(
        storage_key=media.storage_key,
        filename=media.filename,
        content_type=media.content_type,
        size=media.size,
    )
    return direct_private_media_response(
        store,
        upload,
        expires_in=settings.media_stream_redirect_ttl_seconds,
    )


def _require_media_ready(media: ProtectedContentMedia) -> None:
    if media.playback_available:
        return
    if media.processing_status is ContentMediaProcessingStatus.FAILED:
        api_error(
            409,
            "content_media_normalization_failed",
            "The video could not be prepared for playback",
        )
    api_error(
        409,
        "content_media_preparing",
        "The video is still being prepared for playback",
    )
