from __future__ import annotations

import os
import sys
from collections.abc import Sequence

from redis import Redis
from redis.exceptions import RedisError

DEFAULT_HEALTH_CHECK_KEY = "arq:queue:health-check"
SOCKET_TIMEOUT_SECONDS = 2


def arq_worker_is_healthy(redis_url: str, health_check_key: str) -> bool:
    """Read an ARQ heartbeat without importing the worker application."""
    client: Redis[bytes] | None = None
    try:
        client = Redis.from_url(
            redis_url,
            socket_connect_timeout=SOCKET_TIMEOUT_SECONDS,
            socket_timeout=SOCKET_TIMEOUT_SECONDS,
        )
        return client.get(health_check_key) is not None
    except (RedisError, ValueError):
        return False
    finally:
        if client is not None:
            client.close()


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(argv if argv is not None else sys.argv[1:])
    health_check_key = arguments[0] if arguments else DEFAULT_HEALTH_CHECK_KEY
    redis_url = os.environ.get("REDIS_URL", "").strip()
    if not redis_url:
        print("REDIS_URL is not configured", file=sys.stderr)
        return 1
    if arq_worker_is_healthy(redis_url, health_check_key):
        return 0
    print(f"ARQ heartbeat is missing for key {health_check_key!r}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
