from sqlalchemy.ext.asyncio import AsyncSession

from app.interviews.models import InterviewProcessStage
from app.interviews.uploads import (
    EXTERNAL_STORAGE_KEY_PREFIX,
    InterviewUploadStore,
    StoredUpload,
)


async def ensure_stage_media_browser_playable(
    session: AsyncSession,
    stage: InterviewProcessStage,
    store: InterviewUploadStore,
) -> StoredUpload:
    if (
        stage.media_storage_key is None
        or stage.media_filename is None
        or stage.media_content_type is None
        or stage.media_size is None
    ):
        raise ValueError("Interview stage has no media")
    upload = StoredUpload(
        storage_key=stage.media_storage_key,
        filename=stage.media_filename,
        content_type=stage.media_content_type,
        size=stage.media_size,
    )
    if not upload.storage_key.startswith(
        EXTERNAL_STORAGE_KEY_PREFIX
    ) or not upload.filename.casefold().endswith(".mp3"):
        return upload
    playable = await store.ensure_browser_playable(upload)
    if playable != upload:
        stage.media_storage_key = playable.storage_key
        stage.media_filename = playable.filename
        stage.media_content_type = playable.content_type
        stage.media_size = playable.size
        await session.commit()
    return playable
