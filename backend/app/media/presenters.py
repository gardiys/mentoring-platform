from collections.abc import Iterable

from app.media.models import ProtectedContentMedia
from app.media.schemas import ContentMediaKind, ProtectedContentMediaRead


def content_media_read(media: ProtectedContentMedia) -> ProtectedContentMediaRead:
    kind = (
        ContentMediaKind.VIDEO
        if media.content_type.startswith("video/")
        else ContentMediaKind.AUDIO
    )
    return ProtectedContentMediaRead(
        id=media.id,
        kind=kind,
        filename=media.filename,
        content_type=media.content_type,
        size=media.size,
        title=media.title,
        position=media.position,
        processing_status=media.processing_status,
        normalization_attempts=media.normalization_attempts,
        normalization_started_at=media.normalization_started_at,
        normalization_completed_at=media.normalization_completed_at,
        normalization_error_code=media.normalization_error_code,
        normalization_error_message=media.normalization_error_message,
        playback_available=media.playback_available,
        created_at=media.created_at,
    )


def content_media_reads(
    media_items: Iterable[ProtectedContentMedia],
) -> list[ProtectedContentMediaRead]:
    return [
        content_media_read(media)
        for media in sorted(
            media_items,
            key=lambda item: (item.position, item.created_at, item.id),
        )
    ]
