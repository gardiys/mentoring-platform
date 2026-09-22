"""Best-effort execution snapshot; never confuse unavailable Redis with an idle worker."""

import asyncio
from typing import cast
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.interviews.intelligence_queue import OPENAI_QUEUE_NAME

ANSWER_FUNCTIONS = {
    "generate_cluster_candidate",
    "validate_cluster_answer",
    "review_cluster_for_automation",
}


async def running_card_cluster_ids() -> set[UUID] | None:
    redis = cast(
        Redis,
        Redis.from_url(
            get_settings().redis_url,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        ),
    )
    try:
        async with asyncio.timeout(1):
            if not await redis.exists(f"{OPENAI_QUEUE_NAME}:health-check"):
                return None
            result: set[UUID] = set()
            async for raw in redis.scan_iter(match="arq:in-progress:card-automation:*", count=100):
                parts = raw.decode().split(":")
                if len(parts) >= 6 and parts[4] in ANSWER_FUNCTIONS:
                    result.add(UUID(parts[3]))
            return result
    except (RedisError, TimeoutError, ValueError):
        return None
    finally:
        try:
            await redis.aclose()
        except RedisError:
            pass
