from typing import Any

from arq.connections import RedisSettings, create_pool

from app.core.config import get_settings


async def enqueue_intelligence_job(
    function: str, interview_id: str, *, defer_seconds: int | None = None
) -> str | None:
    redis = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    try:
        options: dict[str, Any] = {}
        if defer_seconds is not None:
            options["_defer_by"] = defer_seconds
        job = await redis.enqueue_job(function, interview_id, **options)
        return job.job_id if job is not None else None
    finally:
        await redis.aclose()
