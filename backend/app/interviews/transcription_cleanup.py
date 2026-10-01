"""Retry remote cleanup independently of the transcription processing outcome."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import anyio
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.interviews.intelligence_models import (
    IntelligenceAttemptStage,
    IntelligenceInterview,
    IntelligenceProcessingAttempt,
    IntelligenceProcessingStatus,
    IntelligenceTranscriptionCleanup,
)
from app.interviews.intelligence_providers import TranscriptionProviderError
from app.interviews.soniox_provider import SonioxTranscriptionProvider

logger = logging.getLogger(__name__)
SAFE_STATUSES = {
    IntelligenceProcessingStatus.FAILED,
    IntelligenceProcessingStatus.AWAITING_CANDIDATE_SPEAKER,
    IntelligenceProcessingStatus.ANALYZING,
    IntelligenceProcessingStatus.READY,
}


async def sweep_soniox_resources(ctx: dict[str, Any]) -> None:
    # Backfill existing submissions and historical IDs before an admin restart.
    # The journal deliberately has no cascading FK: deleting an interview must
    # not lose the reference needed to delete its remote recording.
    async with async_session_factory() as session:
        for source in (
            select(
                IntelligenceInterview.transcription_provider_job_id, IntelligenceInterview.id
            ).where(
                IntelligenceInterview.transcription_provider == "soniox",
                IntelligenceInterview.transcription_provider_job_id.is_not(None),
            ),
            select(
                IntelligenceProcessingAttempt.external_request_id,
                IntelligenceProcessingAttempt.interview_id,
            ).where(
                IntelligenceProcessingAttempt.provider == "soniox",
                IntelligenceProcessingAttempt.stage
                == IntelligenceAttemptStage.TRANSCRIPTION_SUBMIT,
                IntelligenceProcessingAttempt.external_request_id.is_not(None),
            ),
        ):
            await session.execute(
                insert(IntelligenceTranscriptionCleanup)
                .from_select(
                    ["provider_job_id", "interview_id"],
                    source,
                )
                .on_conflict_do_nothing()
            )
        await session.commit()
        ids = list(
            await session.scalars(
                select(IntelligenceTranscriptionCleanup.provider_job_id)
                .where(
                    IntelligenceTranscriptionCleanup.completed_at.is_(None),
                    IntelligenceTranscriptionCleanup.next_attempt_at <= datetime.now(UTC),
                )
                .order_by(IntelligenceTranscriptionCleanup.next_attempt_at)
                .limit(100)
            )
        )
    if not ids:
        return
    provider = None
    try:
        provider = SonioxTranscriptionProvider(get_settings())
        for job_id in ids:
            async with async_session_factory() as session:
                record = await session.scalar(
                    select(IntelligenceTranscriptionCleanup)
                    .where(
                        IntelligenceTranscriptionCleanup.provider_job_id == job_id,
                        IntelligenceTranscriptionCleanup.completed_at.is_(None),
                    )
                    .with_for_update(skip_locked=True)
                )
                if record is None:
                    continue
                # Lock the interview too so requeue/parse cannot race deletion.
                interview = await session.scalar(
                    select(IntelligenceInterview)
                    .where(
                        IntelligenceInterview.id == record.interview_id,
                    )
                    .with_for_update()
                )
                record.next_attempt_at = datetime.now(UTC) + timedelta(minutes=15)
                if (
                    interview is not None
                    and interview.transcription_provider_job_id == job_id
                    and interview.processing_status not in SAFE_STATUSES
                ):
                    await session.commit()
                    continue
                try:
                    with anyio.fail_after(30):
                        if await provider.cleanup(job_id):
                            record.completed_at = datetime.now(UTC)
                except (TranscriptionProviderError, TimeoutError) as error:
                    logger.warning(
                        "Soniox cleanup deferred code=%s", getattr(error, "code", "TIMEOUT")
                    )
                await session.commit()
    except TranscriptionProviderError as error:
        logger.warning("Soniox cleanup unavailable code=%s", error.code)
    finally:
        if provider is not None:
            await provider.close()
