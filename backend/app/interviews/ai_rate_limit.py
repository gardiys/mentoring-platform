"""Model-scoped backoff shared by all AI workers, without holding a worker slot."""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Awaitable, Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING, Any, cast

from arq import Retry
from arq.constants import retry_key_prefix
from redis.asyncio import Redis

if TYPE_CHECKING:
    from app.interviews.intelligence_ai import InterviewAIError

COOLDOWN_ERROR = "OPENAI_MODEL_COOLDOWN"
DEFAULT_COOLDOWN_SECONDS = 60.0
_EXTEND = """
local remaining = redis.call('PTTL', KEYS[1])
local delay = tonumber(ARGV[1])
if remaining < delay then
    redis.call('SET', KEYS[1], '1', 'PX', delay)
    return delay
end
return remaining
"""
_REFUND = """
local tries = tonumber(redis.call('GET', KEYS[1]) or '0')
if tries > 0 then return redis.call('DECR', KEYS[1]) end
return 0
"""


def retry_after_seconds(headers: Mapping[str, str]) -> float:
    """Honor Retry-After seconds/date and the SDK's millisecond header, without shortening."""
    delays: list[float] = []
    for name, divisor in (("retry-after-ms", 1000), ("retry-after", 1)):
        value = headers.get(name)
        if value is None:
            continue
        try:
            delay = float(value) / divisor
        except ValueError:
            try:
                when = parsedate_to_datetime(value)
                delay = (
                    when.replace(tzinfo=when.tzinfo or UTC) - datetime.now(UTC)
                ).total_seconds()
            except (ValueError, TypeError, OverflowError):
                continue
        if math.isfinite(delay) and delay > 0:
            delays.append(delay)
    return max(delays) if delays else DEFAULT_COOLDOWN_SECONDS


class ModelCooldown:
    def __init__(self, redis_url: str, *, account_key: str) -> None:
        # Never store the API key or request content in Redis keys/logs.
        self.scope = hashlib.sha256(account_key.encode()).hexdigest()[:24]
        self.redis = cast(
            Redis,
            Redis.from_url(
                redis_url,
                socket_connect_timeout=2,
                socket_timeout=3,
                decode_responses=False,
            ),
        )

    def key(self, model: str) -> str:
        digest = hashlib.sha256(model.encode()).hexdigest()[:24]
        return f"ai:model-cooldown:v1:{self.scope}:{digest}"

    async def remaining(self, model: str) -> float:
        return max(int(await self.redis.pttl(self.key(model))), 0) / 1000

    async def extend(self, model: str, seconds: float) -> None:
        await cast(
            Awaitable[Any],
            self.redis.eval(_EXTEND, 1, self.key(model), str(math.ceil(seconds * 1000))),
        )

    def quota_key(self) -> str:
        return f"ai:account-quota:v1:{self.scope}"

    async def quota_remaining(self) -> float:
        return max(int(await self.redis.pttl(self.quota_key())), 0) / 1000

    async def pause_quota(self) -> None:
        await cast(Awaitable[Any], self.redis.eval(_EXTEND, 1, self.quota_key(), "3600000"))

    async def close(self) -> None:
        await self.redis.aclose()


async def defer_model_cooldown(ctx: dict[str, Any], error: InterviewAIError) -> None:
    """A blocked request was never sent: release the slot and preserve its retry budget."""
    if error.code != COOLDOWN_ERROR:
        return
    if ctx.get("job_id") and ctx.get("redis") is not None:
        await ctx["redis"].eval(_REFUND, 1, retry_key_prefix + str(ctx["job_id"]))
    raise Retry(
        defer=max(error.retry_after_seconds or DEFAULT_COOLDOWN_SECONDS, 1) + random.uniform(0.1, 5)
    ) from error


def retry_delay(error: InterviewAIError, fallback: float) -> float:
    return max(fallback, error.retry_after_seconds or 0)
