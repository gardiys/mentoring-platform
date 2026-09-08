from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from html import escape
from typing import Annotated
from urllib.parse import parse_qs, urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.desktop import DesktopGrant, desktop_user, token_hash
from app.auth.web_session import (
    BROWSER_SESSION_COOKIE,
    SignedPayloadError,
    read_browser_session,
    sign_payload,
    verify_payload,
)
from app.core.config import get_settings
from app.core.errors import api_error
from app.db.session import get_db_session
from app.users.models import User, UserRole

router = APIRouter(prefix="/auth/desktop", tags=["desktop-auth"])
settings = get_settings()
Session = Annotated[AsyncSession, Depends(get_db_session)]
HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY"}


def secret() -> str:
    if not settings.desktop_auth_enabled or settings.web_session_secret is None:
        api_error(503, "desktop_auth_unavailable", "Desktop authentication is not configured")
    return settings.web_session_secret.get_secret_value()


async def browser_user(request: Request, session: AsyncSession) -> User | None:
    cookie = request.cookies.get(BROWSER_SESSION_COOKIE)
    if not cookie:
        return None
    try:
        identity = read_browser_session(cookie, secret())
    except SignedPayloadError:
        return None
    user = await session.get(User, identity.user_id)
    if user is None or user.session_version != identity.version:
        return None
    if user.role is not UserRole.STUDENT or not user.is_active:
        api_error(403, "desktop_access_denied", "An active student account is required")
    return user


def page(content: str) -> HTMLResponse:
    return HTMLResponse(
        """<!doctype html><html lang="ru"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Подключение Copilot · Потрачено</title>
<style>body{margin:0;
background:#faf7f1;
color:#19355f;
font:16px/1.65 system-ui}
main{max-width:480px;
margin:8vh auto;
padding:32px;
background:#fffdf9;
border:1px solid #e5dfd4;
border-radius:20px}
h1{font-size:25px}
code{display:block;
font-size:28px;
letter-spacing:4px;
background:#eaf3ff;
padding:15px;
text-align:center}
button{padding:12px 20px;
margin:14px 8px 0 0;
border:0;
border-radius:10px;
background:#19355f;
color:white;
font:inherit;
cursor:pointer}
button[value=deny]{background:#f1ece3;
color:#19355f}
</style><main>"""
        + content
        + "</main></html>",
        headers=HEADERS,
    )


@router.post("/start")
async def start(request: Request, session: Session) -> JSONResponse:
    secret()
    now = datetime.now(UTC)
    # Bounded unauthenticated grant creation; no raw IP addresses are retained.
    requester = token_hash((request.client.host if request.client else "unknown") + secret())
    count = await session.scalar(
        select(func.count())
        .select_from(DesktopGrant)
        .where(
            DesktopGrant.requester_hash == requester,
            DesktopGrant.created_at > now - timedelta(minutes=5),
        )
    )
    if count and count >= 120:
        api_error(429, "desktop_rate_limited", "Too many login attempts; try again later")
    await session.execute(
        delete(DesktopGrant).where(
            DesktopGrant.expires_at < now - timedelta(days=1),
            (DesktopGrant.token_expires_at.is_(None)) | (DesktopGrant.token_expires_at < now),
        )
    )
    device = secrets.token_urlsafe(32)
    code = secrets.token_hex(4).upper()
    grant = DesktopGrant(
        device_hash=token_hash(device),
        user_code=code[:4] + "-" + code[4:],
        requester_hash=requester,
        created_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    session.add(grant)
    await session.commit()
    await session.refresh(grant)
    return JSONResponse(
        {
            "request_id": str(grant.id),
            "device_code": device,
            "user_code": grant.user_code,
            "expires_in": 300,
            "interval": 3,
            "verification_uri": settings.web_frontend_url.rstrip("/")
            + "/api/v1/auth/desktop/authorize?"
            + urlencode({"request_id": str(grant.id)}),
        },
        headers=HEADERS,
    )


@router.get("/authorize", response_model=None)
async def authorize(request_id: UUID, request: Request, session: Session) -> Response:
    secret()
    user = await browser_user(request, session)
    if user is None:
        path = "/api/v1/auth/desktop/authorize?" + urlencode({"request_id": str(request_id)})
        return RedirectResponse(
            "/api/v1/auth/web/telegram/start?" + urlencode({"next": path}),
            status_code=302,
            headers=HEADERS,
        )
    grant = await session.get(DesktopGrant, request_id)
    if grant is None or grant.status != "pending" or grant.expires_at <= datetime.now(UTC):
        return page("<h1>Запрос недоступен</h1><p>Вернись в приложение и начни вход заново.</p>")
    csrf = sign_payload(
        {
            "kind": "desktop_approval",
            "grant": str(grant.id),
            "user": str(user.id),
            "version": user.session_version,
            "exp": int(grant.expires_at.timestamp()),
        },
        secret(),
    )
    return page(
        "<h1>Подключить Interview Copilot?</h1><p>Сверь код с приложением. "
        "Подтверждай только вход, который начал сам.</p><code>"
        + escape(grant.user_code)
        + "</code><p>Copilot получит доступ к базе знаний, вопросам и опубликованному резюме. "
        "Обработка материалов AI включается отдельно в приложении.</p>"
        + '<form method="post" action="/api/v1/auth/desktop/authorize">'
        '<input type="hidden" name="csrf" value="'
        + escape(csrf, quote=True)
        + '"><button name="decision" value="approve">Подключить</button>'
        '<button name="decision" value="deny">Отмена</button></form>'
    )


@router.post("/authorize")
async def approve(request: Request, session: Session) -> HTMLResponse:
    user = await browser_user(request, session)
    if user is None:
        api_error(401, "desktop_login_required", "Sign in to the platform first")
    if request.headers.get("origin", "").rstrip("/") != settings.web_frontend_url.rstrip("/"):
        api_error(403, "desktop_invalid_origin", "Invalid confirmation origin")
    raw = await request.body()
    if len(raw) > 4096:
        api_error(400, "desktop_invalid_form", "Invalid confirmation")
    try:
        form = parse_qs(raw.decode())
        csrf = verify_payload(form.get("csrf", [""])[0], secret(), expected_kind="desktop_approval")
        request_id = UUID(csrf["grant"])
        if csrf["user"] != str(user.id) or csrf["version"] != user.session_version:
            raise ValueError("Wrong account")
    except (ValueError, KeyError, SignedPayloadError):
        api_error(403, "desktop_invalid_confirmation", "Invalid or expired confirmation")
    approved = form.get("decision") == ["approve"]
    result = await session.execute(
        update(DesktopGrant)
        .where(
            DesktopGrant.id == request_id,
            DesktopGrant.status == "pending",
            DesktopGrant.expires_at > datetime.now(UTC),
        )
        .values(
            status="approved" if approved else "denied",
            user_id=user.id,
            session_version=user.session_version,
        )
        .returning(DesktopGrant.id)
    )
    await session.commit()
    if result.scalar_one_or_none() is None:
        api_error(409, "desktop_request_consumed", "Request expired or already confirmed")
    return page(
        "<h1>Готово</h1><p>Вернись в приложение — вход завершится автоматически.</p>"
        if approved
        else "<h1>Подключение отменено</h1><p>Доступ приложению не выдан.</p>"
    )


class Poll(BaseModel):
    request_id: UUID
    device_code: str = Field(min_length=32, max_length=128)


@router.post("/token")
async def poll(body: Poll, session: Session) -> JSONResponse:
    secret()
    now = datetime.now(UTC)
    grant = await session.scalar(
        select(DesktopGrant)
        .where(
            DesktopGrant.id == body.request_id,
            DesktopGrant.device_hash == token_hash(body.device_code),
        )
        .with_for_update()
    )
    if grant is None or grant.expires_at <= now or grant.status in {"issued", "revoked"}:
        return JSONResponse({"status": "expired"}, headers=HEADERS)
    if grant.status == "denied":
        return JSONResponse({"status": "denied"}, headers=HEADERS)
    if grant.status == "pending":
        if grant.polled_at and (now - grant.polled_at).total_seconds() < 2:
            return JSONResponse(
                {"status": "pending", "interval": 3}, status_code=429, headers=HEADERS
            )
        grant.polled_at = now
        await session.commit()
        return JSONResponse({"status": "pending"}, headers=HEADERS)
    user = await session.get(User, grant.user_id)
    if (
        user is None
        or user.role is not UserRole.STUDENT
        or not user.is_active
        or user.session_version != grant.session_version
    ):
        return JSONResponse({"status": "denied"}, headers=HEADERS)
    token = "copilot_" + secrets.token_urlsafe(48)
    grant.token_hash = token_hash(token)
    grant.token_expires_at = now + timedelta(seconds=settings.desktop_access_token_ttl_seconds)
    grant.status = "issued"
    await session.commit()
    return JSONResponse(
        {
            "status": "approved",
            "access_token": token,
            "expires_in": settings.desktop_access_token_ttl_seconds,
        },
        headers=HEADERS,
    )


@router.post("/logout", status_code=204)
async def logout(request: Request, session: Session) -> Response:
    token = request.headers.get("authorization", "").removeprefix("Bearer ")
    await desktop_user(session, token, request)
    await session.execute(
        update(DesktopGrant)
        .where(DesktopGrant.token_hash == token_hash(token))
        .values(status="revoked", token_hash=None)
    )
    await session.commit()
    return Response(status_code=204, headers=HEADERS)
