from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import anyio
from arq import Retry, cron
from arq import func as arq_func
from arq.connections import RedisSettings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db import models as _db_models  # noqa: F401
from app.db.session import async_session_factory
from app.interviews.media_guardrails import (
    StagingCapacityError,
    StagingGuard,
    cleanup_stale_staging_directories,
    stage_media_file,
)
from app.interviews.uploads import (
    InterviewStorageReadError,
    InterviewStorageWriteError,
    InterviewUploadStore,
    StoredUpload,
)
from app.media.interview_anonymization import (
    anonymize_interview_stage_media,
    reconcile_interview_media_anonymization,
)
from app.media.models import ContentMediaProcessingStatus, ProtectedContentMedia
from app.media.normalization import (
    ContentMediaNormalizationError,
    NormalizedContentMedia,
    normalize_content_mp4,
)
from app.media.normalization_queue import (
    CONTENT_MEDIA_NORMALIZATION_QUEUE_NAME,
    enqueue_content_media_normalization,
)

logger = logging.getLogger(__name__)
settings = get_settings()
MAX_JOB_TRIES = 4
RECONCILIATION_MINUTES = set(range(60))
RECONCILIATION_BATCH_SIZE = 100
WORKER_HEALTH_CHECK_INTERVAL_SECONDS = 30


@dataclass(frozen=True)
class ClaimedContentMedia:
    id: UUID
    source: StoredUpload
    source_key: str
    current_revision: int
    target_revision: int
    generation: int

    @property
    def target_key(self) -> str:
        return f"normalized-content-media/{self.id}/r{self.target_revision}-g{self.generation}.mp4"


async def startup(ctx: dict[str, Any]) -> None:
    root = _staging_root()
    root.mkdir(parents=True, exist_ok=True)
    await _cleanup_staging_directories()
    ctx["upload_store"] = InterviewUploadStore(settings)
    ctx["staging_guard"] = StagingGuard(
        max_concurrency=settings.content_media_normalization_max_concurrency,
        min_free_bytes=settings.content_media_normalization_min_free_bytes,
        max_reserved_bytes=settings.content_media_normalization_max_reserved_bytes,
    )


async def reconcile_content_media_normalization(ctx: dict[str, Any]) -> None:
    """Recover interrupted jobs, enqueue queued rows, and retire old source objects."""
    await _cleanup_staging_directories()
    now = datetime.now(UTC)
    stale_before = now - timedelta(seconds=settings.content_media_normalization_stale_seconds)
    delete_before = now - timedelta(
        seconds=settings.content_media_normalization_source_delete_grace_seconds
    )
    async with async_session_factory() as session:
        stale = list(
            await session.scalars(
                select(ProtectedContentMedia)
                .where(
                    ProtectedContentMedia.processing_status
                    == ContentMediaProcessingStatus.PROCESSING,
                    ProtectedContentMedia.normalization_started_at.is_not(None),
                    ProtectedContentMedia.normalization_started_at < stale_before,
                )
                .order_by(ProtectedContentMedia.normalization_started_at)
                .limit(RECONCILIATION_BATCH_SIZE)
                .with_for_update(skip_locked=True)
            )
        )
        for media in stale:
            media.processing_status = ContentMediaProcessingStatus.QUEUED
            media.normalization_error_code = "WORKER_INTERRUPTED"
            media.normalization_error_message = (
                "Video preparation was interrupted and will be retried"
            )
        await session.commit()

        queued_ids = list(
            await session.scalars(
                select(ProtectedContentMedia.id)
                .where(
                    ProtectedContentMedia.processing_status == ContentMediaProcessingStatus.QUEUED
                )
                .order_by(ProtectedContentMedia.updated_at, ProtectedContentMedia.id)
                .limit(RECONCILIATION_BATCH_SIZE)
            )
        )
        source_cleanup = list(
            (
                await session.execute(
                    select(
                        ProtectedContentMedia.id,
                        ProtectedContentMedia.storage_key,
                        ProtectedContentMedia.normalization_source_key,
                    )
                    .where(
                        ProtectedContentMedia.processing_status
                        == ContentMediaProcessingStatus.READY,
                        ProtectedContentMedia.normalization_source_key.is_not(None),
                        ProtectedContentMedia.normalization_completed_at.is_not(None),
                        ProtectedContentMedia.normalization_completed_at <= delete_before,
                    )
                    .order_by(ProtectedContentMedia.normalization_completed_at)
                    .limit(RECONCILIATION_BATCH_SIZE)
                )
            ).all()
        )

    for media_id in queued_ids:
        await enqueue_content_media_normalization(str(media_id), redis=ctx["redis"])
    if queued_ids:
        logger.info("Reconciled queued content video jobs count=%s", len(queued_ids))

    cleaned = 0
    for media_id, active_key, source_key in source_cleanup:
        if not source_key:
            continue
        if source_key != active_key:
            deleted = await _store(ctx).delete_for_processing(
                source_key,
                suppress_errors=True,
            )
            if not deleted:
                continue
        if await _clear_retired_source_key(media_id, active_key, source_key):
            cleaned += 1
    if cleaned:
        logger.info("Retired original content video objects count=%s", cleaned)
    await reconcile_interview_media_anonymization(ctx)


async def normalize_content_media(ctx: dict[str, Any], media_id: str) -> None:
    parsed_id = UUID(media_id)
    claimed = await _claim_media(parsed_id)
    if claimed is None:
        return

    reserve_bytes = (
        claimed.source.size * 2 + settings.content_media_normalization_output_overhead_bytes
    )
    target_uploaded = False
    try:
        async with stage_media_file(
            _guard(ctx),
            filename=claimed.source.filename,
            maximum_bytes=reserve_bytes,
            expected_bytes=claimed.source.size,
            download=partial(_store(ctx).download_to_path, claimed.source),
            staging_root=_staging_root(),
        ) as source_path:
            normalized = await normalize_content_mp4(
                source_path,
                source_path.with_name("normalized.mp4"),
                source_size=claimed.source.size,
                declared_content_type=claimed.source.content_type,
                max_file_bytes=max(
                    settings.content_video_max_bytes,
                    claimed.source.size,
                ),
                max_duration_seconds=(settings.content_media_normalization_max_duration_seconds),
                probe_timeout_seconds=(settings.content_media_normalization_probe_timeout_seconds),
                remux_timeout_seconds=(settings.content_media_normalization_timeout_seconds),
                output_overhead_bytes=(settings.content_media_normalization_output_overhead_bytes),
            )
            if normalized.reused_source:
                await _complete_without_swap(claimed)
                return
            target = _required_target(normalized)
            await _store(ctx).upload_path(
                target,
                storage_key=claimed.target_key,
                content_type="video/mp4",
                expected_size=normalized.size,
            )
            target_uploaded = True
            swapped = await _complete_with_swap(claimed, normalized)
            if not swapped:
                await _store(ctx).delete_for_processing(
                    claimed.target_key,
                    suppress_errors=True,
                )
                return
            target_uploaded = False
    except StagingCapacityError as error:
        await _handle_failure(
            ctx,
            claimed,
            "STAGING_CAPACITY_EXCEEDED",
            (f"Video preparation capacity is temporarily unavailable ({error.reason})"),
            retryable=True,
        )
    except InterviewStorageReadError:
        await _handle_failure(
            ctx,
            claimed,
            "STORAGE_READ_ERROR",
            "The uploaded video could not be read from storage",
            retryable=True,
        )
    except InterviewStorageWriteError:
        await _handle_failure(
            ctx,
            claimed,
            "STORAGE_WRITE_ERROR",
            "The prepared video could not be saved to storage",
            retryable=True,
        )
    except ContentMediaNormalizationError as error:
        await _handle_failure(
            ctx,
            claimed,
            error.code,
            str(error),
            retryable=error.retryable,
        )
    except Exception:
        logger.exception(
            "Unexpected content media normalization failure media_id=%s",
            claimed.id,
        )
        await _handle_failure(
            ctx,
            claimed,
            "NORMALIZATION_INTERNAL_ERROR",
            "Video preparation failed unexpectedly",
            retryable=True,
        )
        return
    finally:
        if target_uploaded:
            await _delete_target_if_unreferenced(ctx, claimed)


async def _claim_media(media_id: UUID) -> ClaimedContentMedia | None:
    async with async_session_factory() as session:
        media = await session.scalar(
            select(ProtectedContentMedia)
            .where(ProtectedContentMedia.id == media_id)
            .with_for_update()
        )
        if media is None or media.processing_status in {
            ContentMediaProcessingStatus.READY,
            ContentMediaProcessingStatus.FAILED,
        }:
            return None
        if media.processing_status == ContentMediaProcessingStatus.PROCESSING:
            return None
        if media.content_type.split(";", 1)[0].strip().lower() not in {
            "video/mp4",
            "video/quicktime",
        }:
            media.processing_status = ContentMediaProcessingStatus.FAILED
            media.normalization_error_code = "UNSUPPORTED_NORMALIZATION_TYPE"
            media.normalization_error_message = (
                "Only MP4 and MOV content videos can currently be prepared"
            )
            media.normalization_completed_at = datetime.now(UTC)
            await session.commit()
            return None

        source_key = media.normalization_source_key or media.storage_key
        media.normalization_source_key = source_key
        media.processing_status = ContentMediaProcessingStatus.PROCESSING
        media.normalization_attempts += 1
        generation = media.normalization_attempts
        media.normalization_started_at = datetime.now(UTC)
        media.normalization_completed_at = None
        media.normalization_error_code = None
        media.normalization_error_message = None
        claimed = ClaimedContentMedia(
            id=media.id,
            source=StoredUpload(
                storage_key=source_key,
                filename=media.filename,
                content_type=media.content_type,
                size=media.size,
            ),
            source_key=source_key,
            current_revision=media.normalization_revision,
            target_revision=media.normalization_revision + 1,
            generation=generation,
        )
        await session.commit()
        return claimed


async def _complete_without_swap(claimed: ClaimedContentMedia) -> bool:
    async with async_session_factory() as session:
        media = await _locked_claim(session, claimed)
        if media is None:
            return False
        media.processing_status = ContentMediaProcessingStatus.READY
        media.normalization_revision = claimed.target_revision
        media.normalization_source_key = None
        media.normalization_completed_at = datetime.now(UTC)
        media.normalization_error_code = None
        media.normalization_error_message = None
        await session.commit()
        return True


async def _complete_with_swap(
    claimed: ClaimedContentMedia,
    normalized: NormalizedContentMedia,
) -> bool:
    async with async_session_factory() as session:
        media = await _locked_claim(session, claimed)
        if media is None:
            return False
        media.storage_key = claimed.target_key
        media.filename = f"{Path(media.filename).stem[:480]}.mp4"
        media.content_type = "video/mp4"
        media.size = normalized.size
        media.processing_status = ContentMediaProcessingStatus.READY
        media.normalization_revision = claimed.target_revision
        # Keep the original key for delayed cleanup. Existing signed player
        # URLs can continue reading it during the configured grace period.
        media.normalization_source_key = claimed.source_key
        media.normalization_completed_at = datetime.now(UTC)
        media.normalization_error_code = None
        media.normalization_error_message = None
        await session.commit()
        return True


async def _locked_claim(
    session: AsyncSession,
    claimed: ClaimedContentMedia,
) -> ProtectedContentMedia | None:
    media = await session.scalar(
        select(ProtectedContentMedia)
        .where(ProtectedContentMedia.id == claimed.id)
        .with_for_update()
    )
    if (
        media is None
        or media.processing_status != ContentMediaProcessingStatus.PROCESSING
        or media.normalization_source_key != claimed.source_key
        or media.storage_key != claimed.source_key
        or media.normalization_revision != claimed.current_revision
        or media.normalization_attempts != claimed.generation
    ):
        return None
    return media


async def _handle_failure(
    ctx: dict[str, Any],
    claimed: ClaimedContentMedia,
    code: str,
    message: str,
    *,
    retryable: bool,
) -> None:
    will_retry = retryable and _job_try(ctx) < MAX_JOB_TRIES
    changed = await _record_failure(
        claimed,
        code,
        message,
        retryable=will_retry,
    )
    logger.warning(
        "Content video normalization failed media_id=%s code=%s retryable=%s",
        claimed.id,
        code,
        will_retry,
    )
    if changed and will_retry:
        raise Retry(defer=_retry_delay(ctx))


async def _record_failure(
    claimed: ClaimedContentMedia,
    code: str,
    message: str,
    *,
    retryable: bool,
) -> bool:
    async with async_session_factory() as session:
        media = await _locked_claim(session, claimed)
        if media is None:
            return False
        media.processing_status = (
            ContentMediaProcessingStatus.QUEUED
            if retryable
            else ContentMediaProcessingStatus.FAILED
        )
        media.normalization_error_code = code[:100]
        media.normalization_error_message = message[:500]
        media.normalization_completed_at = None if retryable else datetime.now(UTC)
        await session.commit()
        return True


async def _clear_retired_source_key(
    media_id: UUID,
    active_key: str,
    source_key: str,
) -> bool:
    async with async_session_factory() as session:
        media = await session.scalar(
            select(ProtectedContentMedia)
            .where(ProtectedContentMedia.id == media_id)
            .with_for_update()
        )
        if (
            media is None
            or media.processing_status != ContentMediaProcessingStatus.READY
            or media.storage_key != active_key
            or media.normalization_source_key != source_key
        ):
            return False
        media.normalization_source_key = None
        await session.commit()
        return True


async def _delete_target_if_unreferenced(
    ctx: dict[str, Any],
    claimed: ClaimedContentMedia,
) -> None:
    """Avoid deleting an object when a DB commit succeeded but its ACK was lost."""
    try:
        async with async_session_factory() as session:
            active_key = await session.scalar(
                select(ProtectedContentMedia.storage_key).where(
                    ProtectedContentMedia.id == claimed.id
                )
            )
    except Exception:
        logger.exception(
            "Could not verify generated content object before cleanup media_id=%s key=%s",
            claimed.id,
            claimed.target_key,
        )
        return
    if active_key == claimed.target_key:
        return
    await _store(ctx).delete_for_processing(
        claimed.target_key,
        suppress_errors=True,
    )


async def _cleanup_staging_directories() -> int:
    """Periodically remove abandoned worker directories without touching live jobs."""
    # A valid job must time out and cross the stale threshold before its
    # directory is eligible. This remains safe if an operator configures a
    # cleanup age shorter than the worker's stale window.
    older_than_seconds = max(
        settings.content_media_normalization_cleanup_age_seconds,
        settings.content_media_normalization_stale_seconds + 60,
    )
    operation = partial(
        cleanup_stale_staging_directories,
        _staging_root(),
        older_than_seconds=older_than_seconds,
    )
    try:
        removed = int(await anyio.to_thread.run_sync(operation))
    except OSError:
        logger.exception("Could not clean stale content media staging directories")
        return 0
    if removed:
        logger.info("Removed stale content media staging directories count=%s", removed)
    return removed


def _required_target(normalized: NormalizedContentMedia) -> Path:
    if normalized.path is None:
        raise RuntimeError("Normalized media output path is missing")
    return normalized.path


def _store(ctx: dict[str, Any]) -> InterviewUploadStore:
    return cast(InterviewUploadStore, ctx["upload_store"])


def _guard(ctx: dict[str, Any]) -> StagingGuard:
    return cast(StagingGuard, ctx["staging_guard"])


def _staging_root() -> Path:
    return Path(settings.content_media_normalization_directory)


def _job_try(ctx: dict[str, Any]) -> int:
    return max(int(ctx.get("job_try", 1)), 1)


def _retry_delay(ctx: dict[str, Any]) -> int:
    exponent = _job_try(ctx) - 1
    delay: int = 60 << exponent
    return min(15 * 60, delay)


class ContentMediaWorkerSettings:
    functions = [
        arq_func(normalize_content_media, max_tries=MAX_JOB_TRIES),
        arq_func(anonymize_interview_stage_media, max_tries=MAX_JOB_TRIES),
    ]
    cron_jobs = [
        cron(
            reconcile_content_media_normalization,
            minute=RECONCILIATION_MINUTES,
            run_at_startup=True,
            max_tries=1,
            keep_result=0,
        )
    ]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    queue_name = CONTENT_MEDIA_NORMALIZATION_QUEUE_NAME
    max_jobs = settings.content_media_normalization_max_concurrency
    # Leave room for S3 download/upload around ffmpeg while ensuring the stale
    # reconciler can never reclaim a job that ARQ still considers alive.
    job_timeout = max(
        60,
        min(
            settings.content_media_normalization_timeout_seconds + 2_700,
            settings.content_media_normalization_stale_seconds - 60,
        ),
    )
    max_tries = MAX_JOB_TRIES
    keep_result = 0
    health_check_interval = WORKER_HEALTH_CHECK_INTERVAL_SECONDS


# Keep the conventional ARQ entry-point available for direct invocation.
WorkerSettings = ContentMediaWorkerSettings
