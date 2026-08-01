from __future__ import annotations

import logging
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Depends, Query, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import telegram_oidc
from app.auth.web_session import (
    BROWSER_SESSION_COOKIE,
    OAUTH_STATE_COOKIE,
    SignedPayloadError,
    code_challenge,
    create_browser_session,
    create_oauth_state,
    read_oauth_state,
    safe_next_path,
)
from app.core.config import get_settings
from app.core.errors import api_error
from app.db.session import get_db_session
from app.users.models import User

router = APIRouter(prefix="/auth/web", tags=["web-auth"])
settings = get_settings()
logger = logging.getLogger(__name__)
Session = Annotated[AsyncSession, Depends(get_db_session)]


def _configuration() -> tuple[str, str, str, str]:
    if (
        settings.telegram_web_client_id is None
        or settings.telegram_web_client_secret is None
        or settings.telegram_web_redirect_uri is None
        or settings.web_session_secret is None
    ):
        api_error(503, "web_auth_unavailable", "Web authentication is not configured")
    return (
        settings.telegram_web_client_id,
        settings.telegram_web_client_secret.get_secret_value(),
        settings.telegram_web_redirect_uri,
        settings.web_session_secret.get_secret_value(),
    )


def _frontend_redirect(path: str, *, error: str | None = None) -> str:
    if error is not None:
        path = f"/login?{urlencode({'error': error})}"
    return f"{settings.web_frontend_url.rstrip('/')}{safe_next_path(path)}"


def _cookie_secure() -> bool:
    return settings.app_env == "production"


@router.get("/telegram/start", response_class=RedirectResponse)
async def start_telegram_login(next: str = Query(default="/roadmaps")) -> RedirectResponse:
    client_id, _, redirect_uri, session_secret = _configuration()
    state, verifier, state_token = create_oauth_state(
        session_secret,
        settings.web_oauth_state_ttl_seconds,
        next,
    )
    response = RedirectResponse(
        telegram_oidc.authorization_url(
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
            challenge=code_challenge(verifier),
        ),
        status_code=302,
    )
    response.set_cookie(
        OAUTH_STATE_COOKIE,
        state_token,
        max_age=settings.web_oauth_state_ttl_seconds,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        path="/api/v1/auth/web/telegram",
    )
    return response


@router.get("/telegram/callback", response_class=RedirectResponse)
async def telegram_callback(
    session: Session,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    oauth_state: str | None = Cookie(default=None, alias=OAUTH_STATE_COOKIE),
) -> RedirectResponse:
    client_id, client_secret, redirect_uri, session_secret = _configuration()
    if error is not None or code is None or state is None or oauth_state is None:
        response = RedirectResponse(_frontend_redirect("/login", error="telegram_login_failed"))
        response.delete_cookie(OAUTH_STATE_COOKIE, path="/api/v1/auth/web/telegram")
        return response

    try:
        verifier, next_path = read_oauth_state(oauth_state, session_secret, state)
    except SignedPayloadError:
        response = RedirectResponse(_frontend_redirect("/login", error="invalid_login_state"))
        response.delete_cookie(OAUTH_STATE_COOKIE, path="/api/v1/auth/web/telegram")
        return response

    try:
        identity = await telegram_oidc.exchange_code_for_identity(
            code=code,
            verifier=verifier,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            proxy_url=(
                settings.telegram_oidc_proxy_url.get_secret_value()
                if settings.telegram_oidc_proxy_url is not None
                else None
            ),
        )
    except telegram_oidc.TelegramOidcError:
        logger.exception("Telegram web authentication failed")
        response = RedirectResponse(_frontend_redirect("/login", error="telegram_login_failed"))
        response.delete_cookie(OAUTH_STATE_COOKIE, path="/api/v1/auth/web/telegram")
        return response

    user = await session.scalar(select(User).where(User.telegram_id == identity.telegram_id))
    if user is None:
        response = RedirectResponse(
            _frontend_redirect("/login", error="platform_access_not_granted")
        )
        response.delete_cookie(OAUTH_STATE_COOKIE, path="/api/v1/auth/web/telegram")
        return response

    if (user.first_name, user.last_name) != (identity.first_name, identity.last_name):
        user.first_name = identity.first_name
        user.last_name = identity.last_name
        await session.commit()
        await session.refresh(user)

    response = RedirectResponse(_frontend_redirect(next_path), status_code=302)
    response.set_cookie(
        BROWSER_SESSION_COOKIE,
        create_browser_session(user.id, session_secret, settings.web_session_ttl_seconds),
        max_age=settings.web_session_ttl_seconds,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        path="/",
    )
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/api/v1/auth/web/telegram")
    return response


@router.post("/logout", status_code=204, response_class=Response)
async def logout(response: Response) -> Response:
    response.delete_cookie(BROWSER_SESSION_COOKIE, path="/")
    response.status_code = 204
    return response
