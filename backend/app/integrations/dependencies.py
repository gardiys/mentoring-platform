import secrets
from typing import Annotated

from fastapi import Depends, Header

from app.core.config import get_settings
from app.core.errors import api_error, unauthorized

settings = get_settings()


async def require_bot_integration_token(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    configured_token = settings.bot_integration_token
    if configured_token is None:
        api_error(
            503,
            "bot_integration_unavailable",
            "Bot integration is not configured",
        )

    scheme, separator, supplied_token = (authorization or "").partition(" ")
    if (
        not separator
        or scheme.lower() != "bearer"
        or not secrets.compare_digest(
            supplied_token,
            configured_token.get_secret_value(),
        )
    ):
        unauthorized("Bot integration token is invalid")


BotIntegration = Annotated[None, Depends(require_bot_integration_token)]
