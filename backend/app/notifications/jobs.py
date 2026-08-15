from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from math import ceil
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db import models as _db_models  # noqa: F401
from app.db.session import async_session_factory
from app.mentors.models import (
    MentorStudent,
    StudentLearningStatus,
    StudentMentorshipState,
)
from app.notifications.models import (
    NotificationKind,
    TelegramOutbox,
    TelegramOutboxStatus,
)
from app.notifications.service import (
    create_notification,
    queue_telegram_message,
    telegram_action_url,
    telegram_public_url,
)
from app.payments.models import (
    PaymentInstallment,
    PaymentInstallmentStatus,
    StudentEmployment,
    StudentEmploymentStatus,
)
from app.schedule.models import ScheduleEvent, ScheduleEventKind
from app.schedule.service import next_schedule_occurrence
from app.tracks.models import LearningTrack, LearningTrackEnrollment
from app.users.models import User, UserRole

logger = logging.getLogger(__name__)
# Telegram requires the bot token in the request path. httpx logs request URLs
# at INFO by default, so this worker must never expose that URL in production logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
settings = get_settings()
MAX_ATTEMPTS = 8
BATCH_SIZE = 20


async def startup(ctx: dict[str, Any]) -> None:
    proxy = (
        settings.telegram_bot_proxy_url.get_secret_value()
        if settings.telegram_bot_proxy_url is not None
        else None
    )
    ctx["telegram_client"] = httpx.AsyncClient(proxy=proxy, timeout=20)


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["telegram_client"].aclose()


async def deliver_telegram_outbox(ctx: dict[str, Any]) -> None:
    if settings.telegram_bot_token is None:
        return
    now = datetime.now(UTC)
    stale_before = now - timedelta(minutes=10)
    async with async_session_factory() as session:
        await session.execute(
            update(TelegramOutbox)
            .where(
                TelegramOutbox.status == TelegramOutboxStatus.PROCESSING,
                TelegramOutbox.processing_started_at < stale_before,
            )
            .values(
                status=TelegramOutboxStatus.QUEUED,
                processing_started_at=None,
                available_at=now,
                last_error="Delivery worker was interrupted",
            )
        )
        rows = list(
            await session.scalars(
                select(TelegramOutbox)
                .where(
                    TelegramOutbox.status == TelegramOutboxStatus.QUEUED,
                    TelegramOutbox.available_at <= now,
                )
                .order_by(TelegramOutbox.created_at)
                .limit(BATCH_SIZE)
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            row.status = TelegramOutboxStatus.PROCESSING
            row.processing_started_at = now
            row.attempts += 1
        await session.commit()

    for row in rows:
        await _deliver_one(ctx["telegram_client"], row.id)


async def _deliver_one(client: httpx.AsyncClient, outbox_id: object) -> None:
    async with async_session_factory() as session:
        row = await session.get(TelegramOutbox, outbox_id)
        if row is None or row.status != TelegramOutboxStatus.PROCESSING:
            return
        payload: dict[str, object] = {
            "chat_id": row.chat_id,
            "text": row.text,
            "disable_web_page_preview": True,
        }
        if row.message_thread_id is not None:
            payload["message_thread_id"] = row.message_thread_id
        if row.action_label and row.action_url:
            payload["reply_markup"] = {
                "inline_keyboard": [
                    [{"text": row.action_label, "url": row.action_url}]
                ]
            }
        token = settings.telegram_bot_token
        assert token is not None
        try:
            response = await client.post(
                f"https://api.telegram.org/bot{token.get_secret_value()}/sendMessage",
                json=payload,
            )
            response.raise_for_status()
        except (httpx.HTTPError, ValueError) as error:
            retry_after = _retry_after(error)
            row.last_error = _safe_error(error)
            row.processing_started_at = None
            if row.attempts >= MAX_ATTEMPTS or _permanent_telegram_error(error):
                row.status = TelegramOutboxStatus.FAILED
                logger.warning(
                    "Telegram notification permanently failed outbox_id=%s attempts=%s error=%s",
                    row.id,
                    row.attempts,
                    row.last_error,
                )
            else:
                row.status = TelegramOutboxStatus.QUEUED
                row.available_at = datetime.now(UTC) + timedelta(
                    seconds=retry_after or min(900, 15 * (2 ** (row.attempts - 1)))
                )
                logger.warning(
                    "Telegram notification will retry outbox_id=%s attempts=%s",
                    row.id,
                    row.attempts,
                )
        else:
            row.status = TelegramOutboxStatus.SENT
            row.sent_at = datetime.now(UTC)
            row.processing_started_at = None
            row.last_error = None
        await session.commit()


def _retry_after(error: Exception) -> int | None:
    if not isinstance(error, httpx.HTTPStatusError):
        return None
    try:
        payload = error.response.json()
        value = payload.get("parameters", {}).get("retry_after")
        return int(value) if value is not None else None
    except (TypeError, ValueError, AttributeError):
        return None


def _permanent_telegram_error(error: Exception) -> bool:
    return isinstance(error, httpx.HTTPStatusError) and error.response.status_code in {
        400,
        401,
        403,
        404,
    }


def _safe_error(error: Exception) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        try:
            payload = error.response.json()
            description = str(payload.get("description", "Telegram API error"))
        except (ValueError, AttributeError):
            description = "Telegram API error"
        return f"HTTP {error.response.status_code}: {description}"[:1000]
    return error.__class__.__name__


async def schedule_payment_reminders(ctx: dict[str, Any]) -> None:
    del ctx
    local_now = datetime.now(ZoneInfo(settings.notification_reminder_timezone))
    if local_now.hour != settings.notification_reminder_hour:
        return
    today = local_now.date()
    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(PaymentInstallment, StudentEmployment, User)
                .join(
                    StudentEmployment,
                    StudentEmployment.id == PaymentInstallment.employment_id,
                )
                .join(User, User.id == StudentEmployment.student_id)
                .where(
                    PaymentInstallment.status.in_(
                        [
                            PaymentInstallmentStatus.SCHEDULED,
                            PaymentInstallmentStatus.PENDING,
                        ]
                    ),
                    PaymentInstallment.due_date <= today + timedelta(days=3),
                    StudentEmployment.status == StudentEmploymentStatus.ACTIVE,
                    User.role == UserRole.STUDENT,
                    User.is_active.is_(True),
                )
                .order_by(PaymentInstallment.due_date)
            )
        ).all()
        for installment, _employment, student in rows:
            reminder_kind = _reminder_kind(installment.due_date, today)
            if reminder_kind is None:
                continue
            amount = f"{installment.amount_kopecks / 100:,.0f}".replace(",", " ")
            if reminder_kind == "soon":
                title = "Скоро платёж"
                body = f"{installment.due_date:%d.%m} нужно внести {amount} ₽."
            elif reminder_kind == "today":
                title = "Сегодня срок платежа"
                body = f"Сегодня нужно внести {amount} ₽."
            else:
                overdue_days = (today - installment.due_date).days
                title = "Платёж просрочен"
                body = f"Платёж {amount} ₽ просрочен на {overdue_days} дн."
            event_key = (
                f"payment-reminder:{installment.id}:{reminder_kind}:{today.isoformat()}"
            )
            await create_notification(
                session,
                user_id=student.id,
                event_key=event_key,
                kind=NotificationKind.PAYMENT_DUE,
                title=title,
                body=body,
                action_url="/payments",
            )
            if student.telegram_id is not None:
                action_url = telegram_action_url("/payments")
                await queue_telegram_message(
                    session,
                    event_key=f"telegram:{event_key}",
                    chat_id=student.telegram_id,
                    text=f"{title}\n\n{body}",
                    action_label="Открыть платежи" if action_url else None,
                    action_url=action_url,
                )
        await session.commit()


async def schedule_group_call_reminders(ctx: dict[str, Any]) -> None:
    del ctx
    if (
        settings.telegram_bot_token is None
        or not settings.telegram_group_call_reminders_enabled
    ):
        return
    now = datetime.now(UTC)
    reminder_deadline = now + timedelta(
        minutes=settings.telegram_group_call_reminder_minutes
    )
    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(ScheduleEvent, LearningTrack)
                .join(LearningTrack, LearningTrack.id == ScheduleEvent.track_id)
                .where(
                    LearningTrack.is_published.is_(True),
                    or_(
                        ScheduleEvent.kind == ScheduleEventKind.WEEKLY_CALL,
                        (
                            (ScheduleEvent.kind == ScheduleEventKind.MEETING)
                            & (ScheduleEvent.starts_at > now)
                            & (ScheduleEvent.starts_at <= reminder_deadline)
                        ),
                    ),
                )
            )
        ).all()
        for event, track in rows:
            occurrence = next_schedule_occurrence(event, now=now)
            if occurrence is None or occurrence > reminder_deadline:
                continue
            students = await _event_students(session, event)
            if not students:
                continue
            local_occurrence = occurrence.astimezone(
                ZoneInfo(settings.notification_reminder_timezone)
            )
            minutes_left = max(1, ceil((occurrence - now).total_seconds() / 60))
            source = "Ваш ментор" if event.mentor_id is not None else "Платформа"
            text = (
                "Скоро групповой созвон\n\n"
                f"«{event.title}» начнётся примерно через {minutes_left} мин.\n"
                f"Время: {local_occurrence:%d.%m в %H:%M}\n"
                f"Направление: {track.title}\n"
                f"Организатор: {source}"
            )
            description = " ".join((event.description or "").split())
            if description:
                text += f"\n\n{description[:1_000]}"
            occurrence_key = occurrence.isoformat()
            event_keys = {
                student.id: (
                    f"telegram:group-call:{event.id}:{occurrence_key}:{student.id}"
                )
                for student in students
            }
            existing = set(
                await session.scalars(
                    select(TelegramOutbox.event_key).where(
                        TelegramOutbox.event_key.in_(event_keys.values())
                    )
                )
            )
            for student in students:
                event_key = event_keys[student.id]
                if event_key in existing:
                    continue
                assert student.telegram_id is not None
                meeting_url = (
                    telegram_public_url(event.meeting_url)
                    if event.meeting_url is not None
                    else None
                )
                action_url = meeting_url or telegram_action_url("/my-mentor")
                await queue_telegram_message(
                    session,
                    event_key=event_key,
                    chat_id=student.telegram_id,
                    text=text,
                    action_label=(
                        "Подключиться к созвону ↗"
                        if meeting_url
                        else ("Открыть расписание" if action_url else None)
                    ),
                    action_url=action_url,
                )
        await session.commit()


async def _event_students(session: AsyncSession, event: ScheduleEvent) -> list[User]:
    statement = (
        select(User)
        .join(
            LearningTrackEnrollment,
            LearningTrackEnrollment.user_id == User.id,
        )
        .where(
            LearningTrackEnrollment.track_id == event.track_id,
            User.role == UserRole.STUDENT,
            User.is_active.is_(True),
            User.program_excluded_at.is_(None),
            User.telegram_id.is_not(None),
        )
    )
    if event.mentor_id is not None:
        mentor = await session.get(User, event.mentor_id)
        if mentor is None or not mentor.is_active or mentor.role not in {
            UserRole.MENTOR,
            UserRole.ADMIN,
        }:
            return []
        statement = statement.join(
            MentorStudent,
            MentorStudent.student_id == User.id,
        ).where(MentorStudent.mentor_id == event.mentor_id)
    return list(await session.scalars(statement.distinct()))


async def schedule_daily_reminders(ctx: dict[str, Any]) -> None:
    del ctx
    if settings.telegram_bot_token is None or not settings.telegram_daily_reminders_enabled:
        return
    local_now = datetime.now(ZoneInfo(settings.notification_reminder_timezone))
    if local_now.hour != settings.telegram_daily_reminder_hour:
        return
    today = local_now.date()
    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(User, MentorStudent, StudentMentorshipState)
                .outerjoin(MentorStudent, MentorStudent.student_id == User.id)
                .outerjoin(
                    StudentMentorshipState,
                    StudentMentorshipState.student_id == User.id,
                )
                .where(
                    User.role == UserRole.STUDENT,
                    User.is_active.is_(True),
                    User.program_excluded_at.is_(None),
                    User.telegram_id.is_not(None),
                )
            )
        ).all()
        for student, relation, state in rows:
            learning_status = (
                state.learning_status
                if state is not None
                else (
                    relation.learning_status
                    if relation is not None
                    else StudentLearningStatus.LEARNING
                )
            )
            if learning_status is StudentLearningStatus.FINISHED:
                continue
            assert student.telegram_id is not None
            await queue_telegram_message(
                session,
                event_key=f"telegram:daily-reminder:{today.isoformat()}:{student.id}",
                chat_id=student.telegram_id,
                text=(
                    "Не забудьте написать дейлик\n\n"
                    "Подведите итоги сегодняшнего дня: что сделали, что планируете "
                    "дальше и где нужна помощь."
                ),
            )
        await session.commit()


def _reminder_kind(due_date: date, today: date) -> str | None:
    delta = (due_date - today).days
    if delta == 3:
        return "soon"
    if delta == 0:
        return "today"
    if delta < 0:
        overdue_days = -delta
        if overdue_days in {1, 3, 7} or (overdue_days > 7 and overdue_days % 7 == 0):
            return "overdue"
    return None


class NotificationWorkerSettings:
    functions: list[object] = []
    cron_jobs = [
        cron(
            deliver_telegram_outbox,
            second={0, 15, 30, 45},
            run_at_startup=True,
            max_tries=1,
            keep_result=0,
        ),
        cron(
            schedule_payment_reminders,
            minute=0,
            run_at_startup=True,
            max_tries=1,
            keep_result=0,
        ),
        cron(
            schedule_group_call_reminders,
            minute=None,
            second=5,
            run_at_startup=True,
            max_tries=1,
            keep_result=0,
        ),
        cron(
            schedule_daily_reminders,
            minute=0,
            run_at_startup=True,
            max_tries=1,
            keep_result=0,
        ),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 4
    job_timeout = 60
    keep_result = 0
    health_check_interval = 30


WorkerSettings = NotificationWorkerSettings
