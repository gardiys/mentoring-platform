"""Revocable Copilot credentials with explicit read and upload scopes."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from uuid import UUID

from fastapi import Request
from sqlalchemy import DateTime, ForeignKey, Integer, String, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.copilot.access import ensure_copilot_student
from app.core.config import get_settings
from app.core.errors import api_error
from app.db.base import Base, UUIDPrimaryKeyMixin
from app.users.models import User, UserRole


class DesktopGrant(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "desktop_grants"
    device_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_code: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    requester_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    session_version: Mapped[int | None] = mapped_column(Integer)
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def desktop_scope(request: Request) -> bool:
    path = request.url.path
    if request.method == "POST" and path == "/api/v1/auth/desktop/logout":
        return True
    if request.method == "POST" and re.fullmatch(
        r"/api/v1/(?:copilot/tracks|copilot/sessions/[a-f0-9-]{36}/(?:stage|media/(?:upload|complete))|uploads/multipart/abort)",
        path,
    ):
        return True
    return request.method == "GET" and bool(
        re.fullmatch(
            r"/api/v1/(?:me|copilot/(?:access|tracks|companies|tracks/[a-f0-9-]{36}/context)|knowledge/topics(?:/[^/]+)?|knowledge/entries/[^/]+|"
            r"interviews/decks(?:/[^/]+/questions)?|career-packages/me|"
            r"copilot/rag/(?:manifest|sources/(?:kb|card|resume)/[a-f0-9-]{36})|"
            r"copilot/preparation/(?:options|sources/(?:profile|document|resume|conditions|interview)/[a-f0-9-]{36}))",
            path,
        )
    )


async def desktop_user(session: AsyncSession, token: str, request: Request) -> User:
    if not get_settings().desktop_auth_enabled:
        api_error(503, "desktop_auth_unavailable", "Desktop authentication is disabled")
    if not desktop_scope(request):
        api_error(403, "desktop_scope_denied", "This operation is outside Copilot access")
    grant = await session.scalar(
        select(DesktopGrant).where(DesktopGrant.token_hash == token_hash(token))
    )
    if (
        grant is None
        or grant.status != "issued"
        or grant.token_expires_at is None
        or grant.token_expires_at <= datetime.now(UTC)
    ):
        api_error(401, "desktop_token_expired", "Sign in to Copilot again")
    user = await session.get(User, grant.user_id)
    if (
        user is None
        or user.role is not UserRole.STUDENT
        or not user.is_active
        or user.session_version != grant.session_version
    ):
        api_error(401, "desktop_access_revoked", "Copilot access has been revoked")
    if request.url.path != "/api/v1/auth/desktop/logout":
        await ensure_copilot_student(session, user)
    return user
