from typing import Any
from uuid import UUID

from arq.connections import ArqRedis, RedisSettings, create_pool

from app.core.config import get_settings

DEFAULT_INTELLIGENCE_JOB_EXPIRES_SECONDS = 7 * 24 * 60 * 60
TRANSCRIPTION_QUEUE_NAME = "arq:queue:interview-transcription"
OPENAI_QUEUE_NAME = "arq:queue:interview-openai"
TRANSCRIPTION_FUNCTIONS = frozenset(
    {"submit_transcription", "poll_transcription", "process_transcription_result"}
)
OPENAI_FUNCTIONS = frozenset(
    {
        "extract_interview_structure",
        "refresh_interview_question_embeddings",
        "generate_answer_reviews",
        "route_question_occurrence",
        "find_existing_card_match",
        "assign_question_cluster",
        "recalculate_cluster_stats",
        "promote_question_cluster",
        "generate_cluster_candidate",
        "validate_cluster_answer",
        "create_personal_review_item",
        "backfill_existing_questions",
        "reprocess_question_occurrence",
        "refresh_interview_card_duplicate_cache",
    }
)


def intelligence_queue_name(function: str) -> str:
    if function in TRANSCRIPTION_FUNCTIONS:
        return TRANSCRIPTION_QUEUE_NAME
    if function in OPENAI_FUNCTIONS:
        return OPENAI_QUEUE_NAME
    raise ValueError(f"Unknown interview intelligence job: {function}")


def intelligence_job_id(function: str, interview_id: str) -> str:
    """Return the stable ARQ id used to deduplicate one interview stage."""
    normalized_interview_id = str(UUID(interview_id))
    return f"intelligence:{normalized_interview_id}:{function}"


def _job_expires_seconds() -> int:
    configured = getattr(
        get_settings(),
        "intelligence_job_expires_seconds",
        DEFAULT_INTELLIGENCE_JOB_EXPIRES_SECONDS,
    )
    return max(int(configured), 1)


async def enqueue_intelligence_job(
    function: str,
    interview_id: str,
    *,
    defer_seconds: int | float | None = None,
    redis: ArqRedis | None = None,
) -> str:
    """Enqueue an idempotent interview job with an explicit queue lifetime.

    ARQ returns ``None`` when the deterministic id already exists. That is a
    successful deduplication, so callers still receive the stable id instead of
    treating a repeated request as a queue outage.
    """
    job_id = intelligence_job_id(function, interview_id)
    owned_pool = redis is None
    if redis is None:
        redis = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    try:
        options: dict[str, Any] = {
            "_expires": _job_expires_seconds(),
            "_job_id": job_id,
            "_queue_name": intelligence_queue_name(function),
        }
        if defer_seconds is not None:
            options["_defer_by"] = defer_seconds
        job = await redis.enqueue_job(function, interview_id, **options)
        return job.job_id if job is not None else job_id
    finally:
        if owned_pool:
            await redis.aclose()


def card_automation_job_id(function: str, entity_id: str, revision: int) -> str:
    if function not in OPENAI_FUNCTIONS:
        raise ValueError(f"Unknown card automation job: {function}")
    normalized_id = str(UUID(entity_id))
    if revision < 0:
        raise ValueError("Card automation job revision must be non-negative")
    return f"card-automation:{normalized_id}:{function}:v{revision}"


async def enqueue_card_automation_job(
    function: str,
    entity_id: str,
    revision: int,
    *,
    defer_seconds: int | float | None = None,
    redis: ArqRedis | None = None,
) -> str:
    """Enqueue a revision-aware automation job.

    Mutable cluster aggregate jobs include the membership revision in their
    key, so an enqueue racing with a currently running older revision cannot
    be swallowed by Redis deduplication.
    """

    job_id = card_automation_job_id(function, entity_id, revision)
    owned_pool = redis is None
    if redis is None:
        redis = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    try:
        options: dict[str, Any] = {
            "_expires": _job_expires_seconds(),
            "_job_id": job_id,
            "_queue_name": intelligence_queue_name(function),
        }
        if defer_seconds is not None:
            options["_defer_by"] = defer_seconds
        job = await redis.enqueue_job(function, entity_id, revision, **options)
        return job.job_id if job is not None else job_id
    finally:
        if owned_pool:
            await redis.aclose()


async def enqueue_duplicate_cache_refresh(*, redis: ArqRedis | None = None) -> str:
    function = "refresh_interview_card_duplicate_cache"
    owned_pool = redis is None
    if redis is None:
        redis = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    job_id = "card-automation:duplicate-cache:refresh:v2"
    try:
        job = await redis.enqueue_job(
            function,
            _expires=_job_expires_seconds(),
            _job_id=job_id,
            _queue_name=OPENAI_QUEUE_NAME,
        )
        return job.job_id if job is not None else job_id
    finally:
        if owned_pool:
            await redis.aclose()
