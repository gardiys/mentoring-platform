from app.core.config import Settings
from app.core.errors import api_error
from app.interviews.uploads import (
    InterviewUploadStore,
    OpenedDownload,
    StoredUpload,
    UploadIntent,
)

SAFE_CONTENT_AUDIO_TYPES = (
    "audio/aac",
    "audio/flac",
    "audio/mp4",
    "audio/mpeg",
    "audio/ogg",
    "audio/wav",
    "audio/webm",
    "audio/x-m4a",
)
SAFE_CONTENT_VIDEO_TYPES = (
    "video/mp4",
    "video/ogg",
    "video/quicktime",
    "video/webm",
    "video/x-matroska",
)


class PrivateMediaStore(InterviewUploadStore):
    """Shared private-S3 transport; interview naming remains as a compatibility alias."""


def content_media_upload_rules(
    settings: Settings, content_type: str
) -> tuple[tuple[str, ...], int]:
    normalized = content_type.split(";", 1)[0].strip().lower()
    if normalized in SAFE_CONTENT_VIDEO_TYPES:
        return SAFE_CONTENT_VIDEO_TYPES, settings.content_video_max_bytes
    if normalized in SAFE_CONTENT_AUDIO_TYPES:
        return SAFE_CONTENT_AUDIO_TYPES, settings.interview_audio_max_bytes
    api_error(
        415,
        "unsupported_content_media_type",
        "Only supported audio and video files can be attached",
    )


__all__ = [
    "OpenedDownload",
    "PrivateMediaStore",
    "StoredUpload",
    "UploadIntent",
    "content_media_upload_rules",
]
