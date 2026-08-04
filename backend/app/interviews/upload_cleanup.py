import logging

from sqlalchemy import select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.interviews.models import (
    InterviewProcess,
    InterviewProcessStage,
    InterviewProcessStageAttachment,
)
from app.interviews.uploads import InterviewUploadStore
from app.media.models import ProtectedContentMedia
from app.mentors.models import MentorStudentDocument, MockInterview

logger = logging.getLogger(__name__)


async def delete_upload_if_unreferenced(
    session: AsyncSession,
    store: InterviewUploadStore,
    storage_key: str,
) -> bool:
    """Best-effort cleanup that never deletes an object referenced after a DB commit.

    Attachment services can successfully commit and then fail while constructing the
    response. Their route-level exception handler must therefore inspect all upload
    owners before treating the object as an orphan.
    """

    try:
        await session.rollback()
    except Exception:
        logger.exception(
            "Could not reset DB session before upload cleanup key=%s; preserving object",
            storage_key,
        )
        return False

    references = union_all(
        select(InterviewProcess.id).where(InterviewProcess.offer_storage_key == storage_key),
        select(InterviewProcessStage.id).where(
            InterviewProcessStage.media_storage_key == storage_key
        ),
        select(InterviewProcessStageAttachment.id).where(
            InterviewProcessStageAttachment.storage_key == storage_key
        ),
        select(MentorStudentDocument.id).where(MentorStudentDocument.storage_key == storage_key),
        select(MockInterview.id).where(MockInterview.media_storage_key == storage_key),
        select(ProtectedContentMedia.id).where(ProtectedContentMedia.storage_key == storage_key),
    ).limit(1)
    try:
        referenced_id = await session.scalar(references)
    except Exception:
        logger.exception(
            "Could not verify upload references key=%s; preserving object",
            storage_key,
        )
        return False
    if referenced_id is not None:
        logger.warning(
            "Preserving upload after response failure because DB references it key=%s",
            storage_key,
        )
        return False

    try:
        await store.delete(storage_key)
    except Exception:
        logger.exception("Could not clean unreferenced upload key=%s", storage_key)
        return False
    return True


__all__ = ["delete_upload_if_unreferenced"]
