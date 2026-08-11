from typing import Annotated
from uuid import UUID

from fastapi import Cookie, Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.telegram import (
    TelegramInitDataError,
    TelegramInitDataExpiredError,
    validate_telegram_init_data,
)
from app.auth.web_session import BROWSER_SESSION_COOKIE, SignedPayloadError, read_browser_session
from app.core.config import get_settings
from app.core.errors import api_error, forbidden, unauthorized
from app.db.session import get_db_session
from app.users.models import MENTOR_CAPABLE_ROLES, User, UserRole

settings = get_settings()


def _ensure_platform_access(user: User) -> User:
    if user.role is UserRole.STUDENT and not user.is_active:
        api_error(
            403,
            "student_access_suspended",
            "Student access has been suspended",
        )
    return user


async def _telegram_user(session: AsyncSession, init_data: str) -> User:
    if settings.telegram_bot_token is None:
        api_error(503, "telegram_auth_unavailable", "Telegram authentication is not configured")
    try:
        validated = validate_telegram_init_data(
            init_data,
            bot_token=settings.telegram_bot_token.get_secret_value(),
            max_age_seconds=settings.telegram_init_data_ttl_seconds,
        )
    except TelegramInitDataExpiredError:
        unauthorized("Telegram authentication data has expired")
    except TelegramInitDataError:
        unauthorized("Telegram authentication data is invalid")

    telegram_user = validated.user
    user = await session.scalar(select(User).where(User.telegram_id == telegram_user.id))
    if user is None:
        api_error(
            403,
            "platform_access_not_granted",
            "Platform access has not been granted",
        )
    _ensure_platform_access(user)

    # Names stored by the platform are canonical: they can come from the
    # onboarding bot, an import, or an explicit admin edit. Telegram profile
    # names are display names and must never overwrite those values on login.
    telegram_username = telegram_user.username.lstrip("@") if telegram_user.username else None
    if user.telegram_username != telegram_username:
        user.telegram_username = telegram_username
        await session.commit()
        await session.refresh(user)
    return user


async def get_current_user(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    authorization: Annotated[str | None, Header()] = None,
    x_dev_user_id: Annotated[UUID | None, Header()] = None,
    browser_session: Annotated[str | None, Cookie(alias=BROWSER_SESSION_COOKIE)] = None,
) -> User:
    if authorization and authorization.lower().startswith("tma "):
        return await _telegram_user(session, authorization[4:])

    if browser_session is not None and settings.web_session_secret is not None:
        try:
            browser_identity = read_browser_session(
                browser_session,
                settings.web_session_secret.get_secret_value(),
            )
        except SignedPayloadError:
            unauthorized("Browser session is invalid or has expired")
        user = await session.get(User, browser_identity.user_id)
        if user is None:
            api_error(401, "user_not_found", "User was not found")
        if user.session_version != browser_identity.version:
            unauthorized("Browser session has been revoked")
        return _ensure_platform_access(user)

    if settings.app_env != "development" or not settings.dev_auth_enabled:
        unauthorized()
    if x_dev_user_id is None:
        unauthorized()
    user = await session.get(User, x_dev_user_id)
    if user is None:
        api_error(401, "user_not_found", "User was not found")
    return _ensure_platform_access(user)


async def require_mentor(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if user.role not in MENTOR_CAPABLE_ROLES:
        forbidden("Mentor access is required")
    return user


async def require_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if user.role is not UserRole.ADMIN:
        forbidden("Admin access is required")
    return user


async def require_student(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if user.role is not UserRole.STUDENT:
        forbidden("Student access is required")
    return user


async def require_catalog_user(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if user.role not in {UserRole.STUDENT, UserRole.MENTOR, UserRole.ADMIN}:
        forbidden("Platform content access is required")
    return user


async def require_journal_user(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if user.role not in {UserRole.STUDENT, UserRole.MENTOR, UserRole.ADMIN}:
        forbidden("Student, mentor, or admin access is required")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
MentorUser = Annotated[User, Depends(require_mentor)]
AdminUser = Annotated[User, Depends(require_admin)]
StudentUser = Annotated[User, Depends(require_student)]
CatalogUser = Annotated[User, Depends(require_catalog_user)]
JournalUser = Annotated[User, Depends(require_journal_user)]
