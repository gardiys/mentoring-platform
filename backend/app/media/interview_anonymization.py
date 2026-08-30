from __future__ import annotations

import logging
import platform
import stat
import subprocess
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import anyio
from arq import Retry
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.interviews.media_guardrails import (
    MEDIA_TOOL_ENVIRONMENT,
    StagingCapacityError,
    StagingGuard,
    stage_media_file,
)
from app.interviews.models import (
    InterviewMediaAnonymizationStatus,
    InterviewProcess,
    InterviewProcessStage,
)
from app.interviews.uploads import (
    InterviewStorageReadError,
    InterviewStorageWriteError,
    InterviewUploadStore,
    StoredUpload,
)
from app.users.models import User
from app.users.privacy import public_identity_is_hidden

logger = logging.getLogger(__name__)
settings = get_settings()
MAX_JOB_TRIES = 4


class InterviewMediaAnonymizationError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class ClaimedInterviewMedia:
    stage_id: UUID
    source: StoredUpload
    source_key: str
    target_key: str
    target_filename: str
    target_content_type: str


async def anonymize_interview_stage_media(ctx: dict[str, Any], stage_id: str) -> None:
    claimed = await _claim(UUID(stage_id))
    if claimed is None:
        return
    store = _store(ctx)
    uploaded = False
    try:
        source = await store.resolve_upload_size(claimed.source)
        maximum_source_bytes = (
            settings.interview_video_max_bytes
            if claimed.target_content_type == "video/mp4"
            else settings.interview_audio_max_bytes
        )
        if source.size <= 0 or source.size > maximum_source_bytes:
            raise InterviewMediaAnonymizationError(
                "INVALID_SOURCE_SIZE",
                "Interview media has an invalid size",
                retryable=False,
            )
        claimed = replace(claimed, source=source)
        reserve_bytes = source.size * 2 + settings.content_media_normalization_output_overhead_bytes
        async with stage_media_file(
            _guard(ctx),
            filename=source.filename,
            maximum_bytes=reserve_bytes,
            expected_bytes=source.size,
            download=partial(store.download_to_path, source),
            staging_root=Path(settings.content_media_normalization_directory),
        ) as source_path:
            target = source_path.with_name(
                "anonymized.mp4" if claimed.target_content_type == "video/mp4" else "anonymized.m4a"
            )
            await _render_anonymized_copy(
                source_path,
                target,
                is_video=claimed.target_content_type == "video/mp4",
                timeout_seconds=settings.content_media_normalization_timeout_seconds,
            )
            target_stat = target.lstat()
            maximum_output = (
                source.size + settings.content_media_normalization_output_overhead_bytes
            )
            if (
                stat.S_ISLNK(target_stat.st_mode)
                or not stat.S_ISREG(target_stat.st_mode)
                or target_stat.st_size <= 0
                or target_stat.st_size > maximum_output
            ):
                raise InterviewMediaAnonymizationError(
                    "INVALID_OUTPUT",
                    "Anonymized media output is invalid",
                    retryable=False,
                )
            await store.upload_path(
                target,
                storage_key=claimed.target_key,
                content_type=claimed.target_content_type,
                expected_size=target_stat.st_size,
            )
            uploaded = True
            if await _complete(claimed, target_stat.st_size):
                uploaded = False
    except StagingCapacityError as error:
        await _fail(ctx, claimed, "STAGING_CAPACITY_EXCEEDED", str(error), retryable=True)
    except InterviewStorageReadError:
        await _fail(
            ctx, claimed, "STORAGE_READ_ERROR", "Source media is unavailable", retryable=True
        )
    except InterviewStorageWriteError:
        await _fail(
            ctx,
            claimed,
            "STORAGE_WRITE_ERROR",
            "Could not store anonymized media",
            retryable=True,
        )
    except InterviewMediaAnonymizationError as error:
        await _fail(ctx, claimed, error.code, str(error), retryable=error.retryable)
    except Exception:
        logger.exception("Unexpected interview anonymization failure stage_id=%s", claimed.stage_id)
        await _fail(
            ctx,
            claimed,
            "ANONYMIZATION_INTERNAL_ERROR",
            "Media anonymization failed unexpectedly",
            retryable=True,
        )
    finally:
        if uploaded:
            await store.delete_for_processing(claimed.target_key, suppress_errors=True)


async def reconcile_interview_media_anonymization(ctx: dict[str, Any]) -> None:
    now = datetime.now(UTC)
    stale_before = now - timedelta(seconds=settings.content_media_normalization_stale_seconds)
    async with async_session_factory() as session:
        stale = list(
            await session.scalars(
                select(InterviewProcessStage)
                .where(
                    InterviewProcessStage.media_anonymization_status
                    == InterviewMediaAnonymizationStatus.PROCESSING,
                    InterviewProcessStage.media_anonymization_started_at < stale_before,
                )
                .limit(100)
                .with_for_update(skip_locked=True)
            )
        )
        for stage in stale:
            stage.media_anonymization_status = InterviewMediaAnonymizationStatus.QUEUED
            stage.media_anonymization_error = "Worker was interrupted; the job will be retried"
        await session.commit()
        queued_ids = list(
            await session.scalars(
                select(InterviewProcessStage.id)
                .where(
                    InterviewProcessStage.media_anonymization_status
                    == InterviewMediaAnonymizationStatus.QUEUED
                )
                .order_by(InterviewProcessStage.updated_at, InterviewProcessStage.id)
                .limit(100)
            )
        )
    from app.media.interview_anonymization_queue import enqueue_interview_media_anonymization

    for queued_id in queued_ids:
        await enqueue_interview_media_anonymization(str(queued_id), redis=ctx["redis"])


async def _claim(stage_id: UUID) -> ClaimedInterviewMedia | None:
    async with async_session_factory() as session:
        row = (
            await session.execute(
                select(InterviewProcessStage, User)
                .join(InterviewProcess, InterviewProcess.id == InterviewProcessStage.process_id)
                .join(User, User.id == InterviewProcess.user_id)
                .where(InterviewProcessStage.id == stage_id)
                .with_for_update()
            )
        ).one_or_none()
        if row is None:
            return None
        stage, owner = row
        if not public_identity_is_hidden(owner):
            stage.media_anonymization_status = None
            stage.media_anonymization_error = None
            await session.commit()
            return None
        if stage.media_anonymization_status in {
            InterviewMediaAnonymizationStatus.READY,
            InterviewMediaAnonymizationStatus.FAILED,
            InterviewMediaAnonymizationStatus.PROCESSING,
        }:
            return None
        if not all(
            (
                stage.media_storage_key,
                stage.media_filename,
                stage.media_content_type,
                stage.media_size is not None,
            )
        ):
            stage.media_anonymization_status = InterviewMediaAnonymizationStatus.FAILED
            stage.media_anonymization_error = "Interview media is incomplete"
            await session.commit()
            return None
        content_type = stage.media_content_type.split(";", 1)[0].strip().lower()
        if not (content_type.startswith("video/") or content_type.startswith("audio/")):
            stage.media_anonymization_status = InterviewMediaAnonymizationStatus.FAILED
            stage.media_anonymization_error = "Only audio and video can be anonymized"
            await session.commit()
            return None
        is_video = content_type.startswith("video/")
        target_content_type = "video/mp4" if is_video else "audio/mp4"
        target_filename = f"anonymous-interview.{'mp4' if is_video else 'm4a'}"
        stage.media_anonymization_status = InterviewMediaAnonymizationStatus.PROCESSING
        stage.media_anonymization_started_at = datetime.now(UTC)
        stage.media_anonymization_completed_at = None
        stage.media_anonymization_error = None
        claimed = ClaimedInterviewMedia(
            stage_id=stage.id,
            source=StoredUpload(
                storage_key=stage.media_storage_key,
                filename=stage.media_filename,
                content_type=stage.media_content_type,
                size=stage.media_size,
            ),
            source_key=stage.media_storage_key,
            target_key=f"anonymized-interview-media/{stage.id}/v1.{'mp4' if is_video else 'm4a'}",
            target_filename=target_filename,
            target_content_type=target_content_type,
        )
        await session.commit()
        return claimed


async def _complete(claimed: ClaimedInterviewMedia, size: int) -> bool:
    async with async_session_factory() as session:
        stage = await session.scalar(
            select(InterviewProcessStage)
            .where(InterviewProcessStage.id == claimed.stage_id)
            .with_for_update()
        )
        if (
            stage is None
            or stage.media_storage_key != claimed.source_key
            or stage.media_anonymization_status != InterviewMediaAnonymizationStatus.PROCESSING
        ):
            return False
        stage.anonymized_media_storage_key = claimed.target_key
        stage.anonymized_media_filename = claimed.target_filename
        stage.anonymized_media_content_type = claimed.target_content_type
        stage.anonymized_media_size = size
        stage.media_anonymization_status = InterviewMediaAnonymizationStatus.READY
        stage.media_anonymization_completed_at = datetime.now(UTC)
        stage.media_anonymization_error = None
        await session.commit()
        return True


async def _fail(
    ctx: dict[str, Any],
    claimed: ClaimedInterviewMedia,
    code: str,
    message: str,
    *,
    retryable: bool,
) -> None:
    will_retry = retryable and max(int(ctx.get("job_try", 1)), 1) < MAX_JOB_TRIES
    async with async_session_factory() as session:
        stage = await session.scalar(
            select(InterviewProcessStage)
            .where(InterviewProcessStage.id == claimed.stage_id)
            .with_for_update()
        )
        if (
            stage is None
            or stage.media_storage_key != claimed.source_key
            or stage.media_anonymization_status != InterviewMediaAnonymizationStatus.PROCESSING
        ):
            return
        stage.media_anonymization_status = (
            InterviewMediaAnonymizationStatus.QUEUED
            if will_retry
            else InterviewMediaAnonymizationStatus.FAILED
        )
        stage.media_anonymization_error = f"{code}: {message}"[:500]
        stage.media_anonymization_completed_at = None if will_retry else datetime.now(UTC)
        await session.commit()
    if will_retry:
        delay = min(900, 60 << (max(int(ctx.get("job_try", 1)), 1) - 1))
        raise Retry(defer=delay)


async def _render_anonymized_copy(
    source: Path,
    target: Path,
    *,
    is_video: bool,
    timeout_seconds: float,
) -> None:
    command = _anonymization_command(source, target, is_video=is_video)
    try:
        result = await anyio.to_thread.run_sync(
            partial(
                subprocess.run,
                command,
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout_seconds,
                env=MEDIA_TOOL_ENVIRONMENT,
            )
        )
    except subprocess.TimeoutExpired as error:
        raise InterviewMediaAnonymizationError(
            "ANONYMIZATION_TIMEOUT", "Media anonymization timed out", retryable=True
        ) from error
    except (FileNotFoundError, OSError) as error:
        raise InterviewMediaAnonymizationError(
            "ANONYMIZATION_TOOL_UNAVAILABLE", "ffmpeg is unavailable", retryable=True
        ) from error
    if result.returncode != 0:
        raise InterviewMediaAnonymizationError(
            "ANONYMIZATION_FAILED",
            "The recording could not be converted into an anonymous copy",
            retryable=False,
        )


def _anonymization_command(source: Path, target: Path, *, is_video: bool) -> list[str]:
    common = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-protocol_whitelist",
        "file",
        "-i",
        str(source),
        "-map_metadata",
        "-1",
        "-map_chapters",
        "-1",
        "-sn",
        "-dn",
    ]
    # Change pitch while preserving duration. This removes a stable voiceprint
    # from casual listening; it is not positioned as biometric anonymization.
    audio_filter = "aresample=48000,asetrate=39360,aresample=48000,atempo=1.219512"
    if is_video:
        # The pinned static libx264 uses unsupported SIMD instructions in some
        # Docker Desktop arm64 VMs. Production x86_64 keeps optimized assembly;
        # arm64 development favors correctness over encoding speed.
        x264_compatibility = (
            ["-x264-params", "asm=0"]
            if platform.machine().casefold() in {"aarch64", "arm64"}
            else []
        )
        return [
            *common,
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-vf",
            "gblur=sigma=40:steps=3",
            "-af",
            audio_filter,
            "-c:v",
            "libx264",
            *x264_compatibility,
            "-preset",
            "veryfast",
            "-crf",
            "30",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-movflags",
            "+faststart",
            str(target),
        ]
    return [
        *common,
        "-map",
        "0:a:0",
        "-vn",
        "-af",
        audio_filter,
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        "-movflags",
        "+faststart",
        str(target),
    ]


def _store(ctx: dict[str, Any]) -> InterviewUploadStore:
    return cast(InterviewUploadStore, ctx["upload_store"])


def _guard(ctx: dict[str, Any]) -> StagingGuard:
    return cast(StagingGuard, ctx["staging_guard"])
