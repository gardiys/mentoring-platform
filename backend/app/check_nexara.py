from __future__ import annotations

import asyncio

from nexara import AsyncNexara, NexaraError

from app.core.config import get_settings


async def check() -> int:
    settings = get_settings()
    if settings.nexara_api_key is None:
        print("Nexara connectivity: FAILED (NEXARA_API_KEY is not configured)")
        return 1
    client = AsyncNexara(
        api_key=settings.nexara_api_key.get_secret_value(),
        base_url=settings.nexara_base_url,
        timeout=min(settings.nexara_timeout_seconds, 30),
        max_retries=0,
    )
    try:
        await client.billing.balance()
    except NexaraError as error:
        print(f"Nexara connectivity: FAILED ({type(error).__name__})")
        return 1
    finally:
        await client.aclose()
    print("Nexara connectivity: OK")
    print(f"Model: {settings.nexara_model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(check()))
