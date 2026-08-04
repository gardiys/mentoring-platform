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
