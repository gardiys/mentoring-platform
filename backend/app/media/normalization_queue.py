from typing import Any
from uuid import UUID

from arq.connections import ArqRedis, RedisSettings, create_pool

from app.core.config import get_settings

CONTENT_MEDIA_NORMALIZATION_QUEUE_NAME = "arq:queue:content-media-normalization"
DEFAULT_CONTENT_MEDIA_NORMALIZATION_JOB_EXPIRES_SECONDS = 7 * 24 * 60 * 60


def content_media_normalization_job_id(media_id: str) -> str:
    normalized_media_id = str(UUID(media_id))
    return f"content-media-normalization:{normalized_media_id}"


def _job_expires_seconds() -> int:
    configured = getattr(
        get_settings(),
        "content_media_normalization_job_expires_seconds",
        DEFAULT_CONTENT_MEDIA_NORMALIZATION_JOB_EXPIRES_SECONDS,
    )
    return max(int(configured), 1)


async def enqueue_content_media_normalization(
    media_id: str,
    *,
    defer_seconds: int | float | None = None,
    redis: ArqRedis | None = None,
) -> str:
    """Enqueue one idempotent normalization job for a protected media row."""
    job_id = content_media_normalization_job_id(media_id)
    owned_pool = redis is None
    if redis is None:
        redis = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    try:
        options: dict[str, Any] = {
            "_expires": _job_expires_seconds(),
            "_job_id": job_id,
            "_queue_name": CONTENT_MEDIA_NORMALIZATION_QUEUE_NAME,
        }
        if defer_seconds is not None:
            options["_defer_by"] = defer_seconds
        job = await redis.enqueue_job(
            "normalize_content_media",
            str(UUID(media_id)),
            **options,
        )
        return job.job_id if job is not None else job_id
    finally:
        if owned_pool:
            await redis.aclose()
