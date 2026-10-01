"""Check Soniox authentication/proxy/model without sending a recording."""

import asyncio

from app.core.config import get_settings
from app.interviews.intelligence_providers import TranscriptionProviderError
from app.interviews.soniox_provider import SonioxTranscriptionProvider


async def check() -> int:
    settings = get_settings()
    try:
        provider = SonioxTranscriptionProvider(
            settings.model_copy(
                update={
                    "soniox_timeout_seconds": min(settings.soniox_timeout_seconds, 30),
                }
            )
        )
    except TranscriptionProviderError as error:
        print(f"Soniox connectivity: FAILED ({error.code})")
        return 1
    try:
        await provider.check_connection()
    except TranscriptionProviderError as error:
        print(f"Soniox connectivity: FAILED ({error.code})")
        return 1
    finally:
        await provider.close()
    print("Soniox connectivity: OK (async model and language hints)")
    print("Diarization is checked on transcript output; /models has no capability flag.")
    print(f"Model: {settings.soniox_model}")
    print("Proxy: configured" if settings.soniox_proxy_url else "Proxy: direct connection")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(check()))
