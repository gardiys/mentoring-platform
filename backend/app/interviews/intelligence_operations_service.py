from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from arq.constants import health_check_key_suffix
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.interviews.intelligence_models import (
    IntelligenceAIAdmission,
    IntelligenceAttemptStatus,
    IntelligenceInterview,
    IntelligenceProcessingAttempt,
    IntelligenceProcessingStatus,
)
from app.interviews.intelligence_queue import OPENAI_QUEUE_NAME, TRANSCRIPTION_QUEUE_NAME
from app.interviews.intelligence_schemas import (
    AdminIntelligenceOperationsRead,
    IntelligenceOperationsFailureCodeRead,
    IntelligenceOperationsQueueRead,
    IntelligenceOperationsWorkerRead,
    IntelligenceOperationsWorkersRead,
)

ACTIVE_PROCESSING_STATUSES = (
    IntelligenceProcessingStatus.UPLOADED,
    IntelligenceProcessingStatus.TRANSCRIPTION_SUBMITTED,
    IntelligenceProcessingStatus.TRANSCRIBING,
    IntelligenceProcessingStatus.TRANSCRIPT_READY,
    IntelligenceProcessingStatus.ANALYZING,
)
QUEUE_METRICS_TIMEOUT_SECONDS = 1.5
QUEUE_CLOSE_TIMEOUT_SECONDS = 0.25
TRANSCRIPTION_HEALTH_CHECK_KEY = TRANSCRIPTION_QUEUE_NAME + health_check_key_suffix
OPENAI_HEALTH_CHECK_KEY = OPENAI_QUEUE_NAME + health_check_key_suffix


@dataclass(frozen=True)
class IntelligenceRedisMetrics:
    queues: IntelligenceOperationsQueueRead
    workers: IntelligenceOperationsWorkersRead


def _quota_day_bounds(now: datetime) -> tuple[datetime, datetime]:
    timezone = ZoneInfo(get_settings().interview_ai_quota_timezone)
    local_now = now.astimezone(timezone)
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return local_start.astimezone(UTC), (local_start + timedelta(days=1)).astimezone(UTC)


def _worker_health(heartbeat: object, ttl_ms: object) -> IntelligenceOperationsWorkerRead:
    if isinstance(heartbeat, bytes):
        heartbeat = heartbeat.decode("utf-8", errors="replace")
    heartbeat_text = heartbeat if isinstance(heartbeat, str) and heartbeat else None
    try:
        ttl_value = int(ttl_ms) if isinstance(ttl_ms, int | str | bytes | bytearray) else -1
    except ValueError:
        ttl_value = -1
    if heartbeat_text is None or ttl_value <= 0:
        return IntelligenceOperationsWorkerRead(
            status="unhealthy",
            heartbeat=heartbeat_text,
        )
    return IntelligenceOperationsWorkerRead(
        status="healthy",
        heartbeat=heartbeat_text,
        heartbeat_ttl_seconds=(ttl_value + 999) // 1_000,
    )


async def intelligence_redis_metrics() -> IntelligenceRedisMetrics:
    redis: Redis | None = None
    try:
        redis = Redis.from_url(
            get_settings().redis_url,
            decode_responses=True,
            socket_connect_timeout=QUEUE_METRICS_TIMEOUT_SECONDS,
            socket_timeout=QUEUE_METRICS_TIMEOUT_SECONDS,
        )
        async with asyncio.timeout(QUEUE_METRICS_TIMEOUT_SECONDS):
            async with redis.pipeline(transaction=False) as pipeline:
                pipeline.zcard(TRANSCRIPTION_QUEUE_NAME)
                pipeline.zcard(OPENAI_QUEUE_NAME)
                pipeline.get(TRANSCRIPTION_HEALTH_CHECK_KEY)
                pipeline.pttl(TRANSCRIPTION_HEALTH_CHECK_KEY)
                pipeline.get(OPENAI_HEALTH_CHECK_KEY)
                pipeline.pttl(OPENAI_HEALTH_CHECK_KEY)
                (
                    transcription_depth,
                    openai_depth,
                    transcription_heartbeat,
                    transcription_ttl_ms,
                    openai_heartbeat,
                    openai_ttl_ms,
                ) = await pipeline.execute()
    except Exception:
        return IntelligenceRedisMetrics(
            queues=IntelligenceOperationsQueueRead(available=False),
            workers=IntelligenceOperationsWorkersRead(),
        )
    finally:
        if redis is not None:
            with suppress(Exception):
                async with asyncio.timeout(QUEUE_CLOSE_TIMEOUT_SECONDS):
                    await redis.aclose()
    return IntelligenceRedisMetrics(
        queues=IntelligenceOperationsQueueRead(
            available=True,
            transcription_depth=int(transcription_depth),
            openai_depth=int(openai_depth),
        ),
        workers=IntelligenceOperationsWorkersRead(
            transcription=_worker_health(
                transcription_heartbeat,
                transcription_ttl_ms,
            ),
            openai=_worker_health(openai_heartbeat, openai_ttl_ms),
        ),
    )


async def intelligence_queue_metrics() -> IntelligenceOperationsQueueRead:
    """Compatibility wrapper for callers interested only in queue depths."""
    return (await intelligence_redis_metrics()).queues


async def admin_intelligence_operations(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> AdminIntelligenceOperationsRead:
    generated_at = now or datetime.now(UTC)
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)

    status_rows = (
        await session.execute(
            select(IntelligenceInterview.processing_status, func.count(IntelligenceInterview.id))
            .group_by(IntelligenceInterview.processing_status)
            .order_by(IntelligenceInterview.processing_status)
        )
    ).all()
    by_status = {status: 0 for status in IntelligenceProcessingStatus}
    for processing_status, count in status_rows:
        by_status[processing_status] = int(count)

    oldest_active_at = await session.scalar(
        select(func.min(IntelligenceInterview.updated_at)).where(
            IntelligenceInterview.processing_status.in_(ACTIVE_PROCESSING_STATUSES)
        )
    )
    if oldest_active_at is not None and oldest_active_at.tzinfo is None:
        oldest_active_at = oldest_active_at.replace(tzinfo=UTC)
    oldest_active_age_seconds = (
        max(int((generated_at - oldest_active_at).total_seconds()), 0)
        if oldest_active_at is not None
        else None
    )

    day_start, day_end = _quota_day_bounds(generated_at)
    launches_today = int(
        await session.scalar(
            select(func.count(IntelligenceAIAdmission.id)).where(
                IntelligenceAIAdmission.requested_at >= day_start,
                IntelligenceAIAdmission.requested_at < day_end,
            )
        )
        or 0
    )

    failure_code = func.coalesce(IntelligenceProcessingAttempt.error_code, "UNKNOWN")
    failure_rows = (
        await session.execute(
            select(failure_code, func.count(IntelligenceProcessingAttempt.id))
            .where(
                IntelligenceProcessingAttempt.status == IntelligenceAttemptStatus.FAILED,
                IntelligenceProcessingAttempt.finished_at >= generated_at - timedelta(hours=24),
            )
            .group_by(failure_code)
            .order_by(func.count(IntelligenceProcessingAttempt.id).desc(), failure_code)
        )
    ).all()

    redis_metrics = await intelligence_redis_metrics()
    active = sum(by_status[status] for status in ACTIVE_PROCESSING_STATUSES)
    failed = by_status[IntelligenceProcessingStatus.FAILED]
    ready = by_status[IntelligenceProcessingStatus.READY]
    return AdminIntelligenceOperationsRead(
        generated_at=generated_at,
        total=sum(by_status.values()),
        by_status=by_status,
        active=active,
        failed=failed,
        ready=ready,
        oldest_active_at=oldest_active_at,
        oldest_active_age_seconds=oldest_active_age_seconds,
        launches_today=launches_today,
        failure_codes_24h=[
            IntelligenceOperationsFailureCodeRead(code=code, count=int(count))
            for code, count in failure_rows
        ],
        queues=redis_metrics.queues,
        workers=redis_metrics.workers,
    )
