from __future__ import annotations

import asyncio
import json
import logging
import zlib
from datetime import UTC, datetime
from typing import cast

from pydantic import BaseModel, ConfigDict
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.interviews.card_automation_schemas import (
    InterviewCardDuplicateCandidateRead,
    InterviewCardDuplicateCardRead,
)

logger = logging.getLogger(__name__)

CACHE_KEY = "card-automation:duplicate-candidates:v3"
REFRESH_STATUS_KEY = "card-automation:duplicate-candidates:refresh-status:v3"
REFRESH_LOCK_KEY = "card-automation:duplicate-candidates:refresh-lock:v3"
CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
CACHE_STALE_SECONDS = 30 * 60
REFRESH_STATUS_TTL_SECONDS = 15 * 60
REFRESH_LOCK_TTL_SECONDS = 10 * 60
REFRESH_ERROR_KEY = "card-automation:duplicate-candidates:error:v3"


class DuplicateCacheUnavailable(RuntimeError):
    pass


class InterviewCardDuplicateSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    items: list[InterviewCardDuplicateCandidateRead]


def _redis() -> Redis:
    return cast(
        Redis,
        Redis.from_url(
            get_settings().redis_url,
            decode_responses=False,
            socket_connect_timeout=2,
            socket_timeout=5,
        ),
    )


async def _close(redis: Redis) -> None:
    try:
        await redis.aclose()
    except RedisError:
        logger.warning("Could not close duplicate-card cache connection", exc_info=True)


def _encode_snapshot(snapshot: InterviewCardDuplicateSnapshot) -> bytes:
    # Deduplicate answer bodies AND stream compression: building one giant JSON
    # string still creates several full-size copies before zlib can consume it.
    compressor = zlib.compressobj(level=6)
    chunks: list[bytes] = []

    def emit(value: str) -> None:
        chunk = compressor.compress(value.encode("utf-8"))
        if chunk:
            chunks.append(chunk)

    emit('{"generated_at":' + json.dumps(snapshot.generated_at.isoformat()) + ',"cards":{')
    seen: set[str] = set()
    for item in snapshot.items:
        for card in (item.left, item.right):
            key = str(card.id)
            if key in seen:
                continue
            emit(("," if seen else "") + json.dumps(key) + ":" + card.model_dump_json())
            seen.add(key)
    emit('},"pairs":[')
    for index, item in enumerate(snapshot.items):
        emit(
            ("," if index else "")
            + json.dumps(
                {
                    "pair_key": item.pair_key,
                    "similarity": item.similarity,
                    "matched_source": item.matched_source,
                    "matched_text": item.matched_text,
                    "left": str(item.left.id),
                    "right": str(item.right.id),
                },
                ensure_ascii=False,
            )
        )
    emit("]}")
    chunks.append(compressor.flush())
    return b"".join(chunks)


def _decode_snapshot(payload: bytes) -> InterviewCardDuplicateSnapshot:
    data = json.loads(zlib.decompress(payload))
    cards = {
        key: InterviewCardDuplicateCardRead.model_validate(value)
        for key, value in data["cards"].items()
    }
    return InterviewCardDuplicateSnapshot(
        generated_at=data["generated_at"],
        items=[
            InterviewCardDuplicateCandidateRead(
                **{key: value for key, value in pair.items() if key not in {"left", "right"}},
                left=cards[pair["left"]],
                right=cards[pair["right"]],
            )
            for pair in data["pairs"]
        ],
    )


async def read_duplicate_snapshot() -> InterviewCardDuplicateSnapshot | None:
    redis = _redis()
    try:
        payload = await redis.get(CACHE_KEY)
    except RedisError as error:
        raise DuplicateCacheUnavailable("Duplicate-card cache is unavailable") from error
    finally:
        await _close(redis)
    if payload is None:
        return None
    try:
        return await asyncio.to_thread(_decode_snapshot, payload)
    except (ValueError, KeyError, TypeError, zlib.error):
        logger.warning("Ignoring invalid duplicate-card cache snapshot", exc_info=True)
        return None


async def write_duplicate_snapshot(
    items: list[InterviewCardDuplicateCandidateRead],
) -> InterviewCardDuplicateSnapshot:
    snapshot = InterviewCardDuplicateSnapshot(generated_at=datetime.now(UTC), items=items)
    payload = await asyncio.to_thread(_encode_snapshot, snapshot)
    redis = _redis()
    try:
        await redis.set(CACHE_KEY, payload, ex=CACHE_TTL_SECONDS)
    except RedisError as error:
        raise DuplicateCacheUnavailable("Duplicate-card cache is unavailable") from error
    finally:
        await _close(redis)
    return snapshot


async def mark_duplicate_refresh_queued() -> bool:
    redis = _redis()
    try:
        return bool(
            await redis.set(
                REFRESH_STATUS_KEY,
                b"queued",
                ex=REFRESH_STATUS_TTL_SECONDS,
                nx=True,
            )
        )
    except RedisError as error:
        raise DuplicateCacheUnavailable("Duplicate-card cache is unavailable") from error
    finally:
        await _close(redis)


async def mark_duplicate_refresh_running() -> None:
    redis = _redis()
    try:
        await redis.set(REFRESH_STATUS_KEY, b"running", ex=REFRESH_STATUS_TTL_SECONDS)
    except RedisError as error:
        raise DuplicateCacheUnavailable("Duplicate-card cache is unavailable") from error
    finally:
        await _close(redis)


async def duplicate_refresh_in_progress() -> bool:
    redis = _redis()
    try:
        return bool(await redis.exists(REFRESH_STATUS_KEY))
    except RedisError as error:
        raise DuplicateCacheUnavailable("Duplicate-card cache is unavailable") from error
    finally:
        await _close(redis)


async def clear_duplicate_refresh_status() -> None:
    redis = _redis()
    try:
        await redis.delete(REFRESH_STATUS_KEY)
    except RedisError:
        logger.warning("Could not clear duplicate-card refresh status", exc_info=True)
    finally:
        await _close(redis)


async def acquire_duplicate_refresh_lock(owner: str) -> bool:
    redis = _redis()
    try:
        return bool(
            await redis.set(
                REFRESH_LOCK_KEY,
                owner.encode("utf-8"),
                ex=REFRESH_LOCK_TTL_SECONDS,
                nx=True,
            )
        )
    except RedisError as error:
        raise DuplicateCacheUnavailable("Duplicate-card cache is unavailable") from error
    finally:
        await _close(redis)


async def release_duplicate_refresh_lock(owner: str) -> None:
    redis = _redis()
    try:
        async with redis.pipeline(transaction=True) as pipeline:
            await pipeline.watch(REFRESH_LOCK_KEY)
            current = await pipeline.get(REFRESH_LOCK_KEY)
            if current != owner.encode("utf-8"):
                await pipeline.reset()  # type: ignore[no-untyped-call]
                return
            pipeline.multi()  # type: ignore[no-untyped-call]
            pipeline.delete(REFRESH_LOCK_KEY)
            await pipeline.execute()
    except RedisError:
        logger.warning("Could not release duplicate-card refresh lock", exc_info=True)
    finally:
        await _close(redis)


async def duplicate_refresh_error() -> str | None:
    redis = _redis()
    try:
        value = await redis.get(REFRESH_ERROR_KEY)
        return value.decode() if value else None
    except RedisError as error:
        raise DuplicateCacheUnavailable("Duplicate-card cache is unavailable") from error
    finally:
        await _close(redis)


async def set_duplicate_refresh_error(failed: bool) -> None:
    redis = _redis()
    try:
        if failed:
            await redis.set(
                REFRESH_ERROR_KEY,
                "Не удалось рассчитать список. Повторите расчёт.",
                ex=REFRESH_STATUS_TTL_SECONDS,
            )
        else:
            await redis.delete(REFRESH_ERROR_KEY)
    finally:
        await _close(redis)


async def renew_duplicate_refresh_lock(owner: str) -> None:
    redis = _redis()
    try:
        await redis.execute_command(  # type: ignore[no-untyped-call]
            "EVAL",
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "redis.call('expire', KEYS[1], ARGV[2]); "
            "redis.call('expire', KEYS[2], ARGV[2]); return 1 else return 0 end",
            2,
            REFRESH_LOCK_KEY,
            REFRESH_STATUS_KEY,
            owner,
            str(REFRESH_LOCK_TTL_SECONDS),
        )
    finally:
        await _close(redis)
