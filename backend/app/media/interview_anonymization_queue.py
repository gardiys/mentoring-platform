from typing import Any
from uuid import UUID

from arq.connections import ArqRedis, RedisSettings, create_pool

from app.core.config import get_settings
from app.media.normalization_queue import CONTENT_MEDIA_NORMALIZATION_QUEUE_NAME


def interview_media_anonymization_job_id(stage_id: str) -> str:
    return f"interview-media-anonymization:{UUID(stage_id)}"


async def enqueue_interview_media_anonymization(
    stage_id: str,
    *,
    defer_seconds: int | float | None = None,
    redis: ArqRedis | None = None,
) -> str:
    """Enqueue one idempotent anonymized-copy job for an interview stage."""
    job_id = interview_media_anonymization_job_id(stage_id)
    owned_pool = redis is None
    if redis is None:
        redis = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    try:
        options: dict[str, Any] = {
            "_expires": get_settings().content_media_normalization_job_expires_seconds,
            "_job_id": job_id,
            "_queue_name": CONTENT_MEDIA_NORMALIZATION_QUEUE_NAME,
        }
        if defer_seconds is not None:
            options["_defer_by"] = defer_seconds
        job = await redis.enqueue_job(
            "anonymize_interview_stage_media",
            str(UUID(stage_id)),
            **options,
        )
        return job.job_id if job is not None else job_id
    finally:
        if owned_pool:
            await redis.aclose()
