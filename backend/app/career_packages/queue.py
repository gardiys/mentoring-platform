from uuid import UUID

from arq.connections import RedisSettings, create_pool

from app.core.config import get_settings
from app.interviews.intelligence_queue import OPENAI_QUEUE_NAME


async def enqueue_career_generation(run_id: UUID) -> str:
    job_id = f"career-package:{run_id}:generate"
    redis = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    try:
        job = await redis.enqueue_job(
            "generate_career_package",
            str(run_id),
            _job_id=job_id,
            _queue_name=OPENAI_QUEUE_NAME,
            _expires=7 * 24 * 60 * 60,
        )
        return job.job_id if job is not None else job_id
    finally:
        await redis.aclose()
