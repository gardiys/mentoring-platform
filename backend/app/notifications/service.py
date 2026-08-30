from __future__ import annotations

from datetime import UTC, datetime
from ipaddress import ip_address
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import api_error
from app.interviews.models import InterviewProcess, InterviewProcessStage, InterviewStageType
from app.mentors.models import MentorTrackAssignment
from app.notifications.models import (
    NotificationKind,
    PlatformNotification,
    TelegramOutbox,
)
from app.notifications.schemas import NotificationPage, NotificationRead
from app.tracks.models import LearningTrack, LearningTrackEnrollment
from app.users.models import User, UserRole
from app.users.privacy import public_identity_is_hidden, public_telegram_username, public_user_name

settings = get_settings()
TELEGRAM_MESSAGE_LIMIT = 4_096

STAGE_LABELS = {
    InterviewStageType.SCREENING: "скрининг",
    InterviewStageType.TECHNICAL_SCREENING: "технический скрининг",
    InterviewStageType.TECHNICAL_INTERVIEW: "техническое интервью",
    InterviewStageType.SYSTEM_DESIGN: "системный дизайн",
    InterviewStageType.FINAL_INTERVIEW: "финальное интервью",
    InterviewStageType.OTHER: "иной этап",
}


def _telegram_interview_destination(track_slug: str) -> tuple[str | None, int | None]:
    """Resolve a direction-specific destination with legacy global fallback."""
    slug = track_slug.casefold()
    if slug == "python" and settings.telegram_interview_python_chat_id:
        return (
            settings.telegram_interview_python_chat_id,
            settings.telegram_interview_python_topic_id,
        )
    if slug == "go" and settings.telegram_interview_go_chat_id:
        return (
            settings.telegram_interview_go_chat_id,
            settings.telegram_interview_go_topic_id,
        )
    return settings.telegram_interview_chat_id, settings.telegram_group_topic_id


def actor_name(actor: User) -> str:
    public_username = public_telegram_username(actor)
    username = f"@{public_username}" if public_username else None
    return " · ".join(value for value in (public_user_name(actor), username) if value)


def _telegram_author(actor: User) -> str:
    username = public_telegram_username(actor)
    name = public_user_name(actor)
    if username:
        return f"{name} (@{username.lstrip('@')})"
    return name if public_identity_is_hidden(actor) else f"{name} (Telegram username не указан)"


def _fit_telegram_message(prefix: str, description: str) -> str:
    if not description:
        return prefix
    separator = "\n\nОписание собеседования:\n"
    available = TELEGRAM_MESSAGE_LIMIT - len(prefix) - len(separator)
    if available <= 0:
        return prefix[: TELEGRAM_MESSAGE_LIMIT - 1] + "…"
    if len(description) > available:
        description = description[: max(0, available - 1)].rstrip() + "…"
    return f"{prefix}{separator}{description}"


def telegram_public_url(candidate: str) -> str | None:
    """Return a Telegram-safe public HTTPS URL, never a private address."""
    parsed = urlsplit(candidate)
    hostname = (parsed.hostname or "").casefold()
    if parsed.scheme not in {"http", "https"} or not hostname:
        return None
    if hostname == "localhost" or hostname.endswith(".localhost"):
        return None
    try:
        address = ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and (
        address.is_loopback or address.is_private or address.is_link_local or address.is_unspecified
    ):
        return None
    if parsed.scheme != "https":
        return None
    return candidate


def telegram_action_url(path: str) -> str | None:
    """Build a Telegram-safe URL for an authenticated platform page."""
    return telegram_public_url(f"{settings.web_frontend_url.rstrip('/')}{path}")


async def create_notification(
    session: AsyncSession,
    *,
    user_id: UUID,
    event_key: str,
    kind: NotificationKind,
    title: str,
    body: str,
    action_url: str,
    actor_user_id: UUID | None = None,
) -> None:
    if not action_url.startswith("/") or action_url.startswith("//"):
        raise ValueError("Notification action_url must be a local absolute path")
    await session.execute(
        insert(PlatformNotification)
        .values(
            user_id=user_id,
            actor_user_id=actor_user_id,
            event_key=f"{event_key}:{user_id}",
            kind=kind,
            title=title[:240],
            body=body,
            action_url=action_url,
        )
        .on_conflict_do_nothing(index_elements=[PlatformNotification.event_key])
    )


async def queue_telegram_message(
    session: AsyncSession,
    *,
    event_key: str,
    chat_id: str | int,
    text: str,
    message_thread_id: int | None = None,
    action_label: str | None = None,
    action_url: str | None = None,
) -> None:
    await session.execute(
        insert(TelegramOutbox)
        .values(
            event_key=event_key,
            chat_id=str(chat_id),
            message_thread_id=message_thread_id,
            text=text,
            action_label=action_label,
            action_url=action_url,
        )
        .on_conflict_do_nothing(index_elements=[TelegramOutbox.event_key])
    )


async def notify_student(
    session: AsyncSession,
    *,
    student_id: UUID,
    actor: User,
    event_key: str,
    kind: NotificationKind,
    title: str,
    body: str,
    action_url: str = "/my-mentor",
) -> None:
    if student_id == actor.id:
        return
    await create_notification(
        session,
        user_id=student_id,
        actor_user_id=actor.id,
        event_key=event_key,
        kind=kind,
        title=title,
        body=body,
        action_url=action_url,
    )


async def notify_interview_published(
    session: AsyncSession,
    *,
    actor: User,
    process: InterviewProcess,
    stage: InterviewProcessStage,
) -> None:
    recipient_ids = set(
        await session.scalars(
            select(User.id)
            .outerjoin(
                LearningTrackEnrollment,
                LearningTrackEnrollment.user_id == User.id,
            )
            .outerjoin(
                MentorTrackAssignment,
                MentorTrackAssignment.mentor_id == User.id,
            )
            .where(
                User.is_active.is_(True),
                User.id != actor.id,
                (
                    (User.role == UserRole.ADMIN)
                    | (
                        (User.role == UserRole.STUDENT)
                        & (LearningTrackEnrollment.track_id == process.track_id)
                    )
                    | (
                        (User.role == UserRole.MENTOR)
                        & (MentorTrackAssignment.track_id == process.track_id)
                    )
                ),
            )
            .distinct()
        )
    )
    stage_label = STAGE_LABELS[stage.stage_type]
    action_url = f"/interviews/catalog/{process.company_id}?stage={stage.id}"
    description = "" if public_identity_is_hidden(actor) else (stage.description or "").strip()
    compact_description = " ".join(description.split())
    body = f"{stage_label.capitalize()} в {process.company_name}. Автор: {actor_name(actor)}."
    if compact_description:
        body += f" {compact_description[:300]}"
    event_key = f"interview-stage-published:{stage.id}"
    for recipient_id in recipient_ids:
        await create_notification(
            session,
            user_id=recipient_id,
            actor_user_id=actor.id,
            event_key=event_key,
            kind=NotificationKind.INTERVIEW_PUBLISHED,
            title="Новое собеседование в каталоге",
            body=body,
            action_url=action_url,
        )

    track = (
        await session.execute(
            select(LearningTrack.slug, LearningTrack.title).where(
                LearningTrack.id == process.track_id
            )
        )
    ).one_or_none()
    if track is None:
        track_slug, track_title = "", None
    else:
        track_slug, track_title = track
    telegram_chat_id, telegram_topic_id = _telegram_interview_destination(track_slug)
    if telegram_chat_id:
        public_url = telegram_action_url(action_url)
        prefix = (
            "Новое собеседование в каталоге\n\n"
            f"Компания: {process.company_name}\n"
            f"Этап: {stage_label}\n"
            f"Направление: {track_title or 'не указано'}\n"
            f"Дата: {stage.scheduled_at:%d.%m.%Y %H:%M}\n"
            f"Автор: {_telegram_author(actor)}"
        )
        text = _fit_telegram_message(prefix, description)
        await queue_telegram_message(
            session,
            event_key=f"telegram:{event_key}",
            chat_id=telegram_chat_id,
            text=text,
            message_thread_id=telegram_topic_id,
            action_label="Смотреть собеседование ↗" if public_url else None,
            action_url=public_url,
        )


async def list_notifications(
    session: AsyncSession, user: User, *, limit: int, offset: int
) -> NotificationPage:
    filters = (PlatformNotification.user_id == user.id,)
    total, unread = (
        await session.execute(
            select(
                func.count(PlatformNotification.id),
                func.count(PlatformNotification.id).filter(PlatformNotification.read_at.is_(None)),
            ).where(*filters)
        )
    ).one()
    rows = list(
        await session.scalars(
            select(PlatformNotification)
            .where(*filters)
            .order_by(PlatformNotification.created_at.desc(), PlatformNotification.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return NotificationPage(
        items=[
            NotificationRead(
                id=row.id,
                kind=row.kind,
                title=row.title,
                body=row.body,
                action_url=row.action_url,
                read_at=row.read_at,
                created_at=row.created_at,
            )
            for row in rows
        ],
        total=total or 0,
        unread_count=unread or 0,
        limit=limit,
        offset=offset,
    )


async def mark_read(session: AsyncSession, user: User, notification_id: UUID) -> None:
    result = await session.execute(
        update(PlatformNotification)
        .where(
            PlatformNotification.id == notification_id,
            PlatformNotification.user_id == user.id,
        )
        .values(read_at=func.coalesce(PlatformNotification.read_at, datetime.now(UTC)))
        .returning(PlatformNotification.id)
    )
    if result.scalar_one_or_none() is None:
        api_error(404, "notification_not_found", "Notification was not found")
    await session.commit()


async def mark_all_read(session: AsyncSession, user: User) -> None:
    await session.execute(
        update(PlatformNotification)
        .where(
            PlatformNotification.user_id == user.id,
            PlatformNotification.read_at.is_(None),
        )
        .values(read_at=datetime.now(UTC))
    )
    await session.commit()
