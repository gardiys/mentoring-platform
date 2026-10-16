from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.notifications.models import NotificationKind
from app.notifications.service import (
    create_notification,
    queue_telegram_message,
    telegram_action_url,
)
from app.opportunities.models import (
    ConsultationRequest,
    GoTransitionApplication,
    OpportunityPaymentAttempt,
    PythonRepeatApplication,
    PythonRepeatInstallment,
)
from app.opportunities.stages import needs_action_sql, overdue_sql, stage_rows
from app.opportunities.workspace_schemas import OpportunitySummary
from app.payments.models import PaymentAttemptStatus
from app.users.models import User, UserRole


async def notify_user(
    session: AsyncSession,
    user: User,
    *,
    event_key: str,
    title: str,
    body: str,
    link: str | None,
    actor_id: UUID | None = None,
    kind: NotificationKind = NotificationKind.STATUS_CHANGED,
) -> None:
    if not user.is_active:
        return
    await create_notification(
        session,
        user_id=user.id,
        event_key=event_key,
        kind=kind,
        title=title,
        body=body,
        action_url=link,
        actor_user_id=actor_id,
    )
    if user.telegram_id:
        await queue_telegram_message(
            session,
            event_key=f"telegram:{event_key}:{user.id}",
            chat_id=user.telegram_id,
            text=f"{title}\n\n{body}"[:4096],
            action_label="Открыть заявку" if link else None,
            action_url=telegram_action_url(link) if link else None,
        )


async def notify_admins(
    session: AsyncSession,
    *,
    event_key: str,
    title: str,
    body: str,
    link: str,
    actor_id: UUID | None = None,
) -> None:
    for admin in await session.scalars(
        select(User).where(User.role == UserRole.ADMIN, User.is_active.is_(True))
    ):
        await notify_user(
            session,
            admin,
            event_key=event_key,
            title=title,
            body=body,
            link=link,
            actor_id=actor_id,
        )


async def mark_payment_for_review(
    session: AsyncSession, attempt: OpportunityPaymentAttempt
) -> None:
    resource: ConsultationRequest | GoTransitionApplication | PythonRepeatApplication | None
    attempt.status = PaymentAttemptStatus.MANUAL_REVIEW
    if attempt.consultation_request_id:
        link = f"/admin/opportunities?consultation={attempt.consultation_request_id}"
        product = "Консультация"
        resource = await session.get(ConsultationRequest, attempt.consultation_request_id)
    elif attempt.transition_application_id:
        link = f"/admin/opportunities?go={attempt.transition_application_id}"
        product = "Переход Python → Go"
        resource = await session.get(GoTransitionApplication, attempt.transition_application_id)
    else:
        application_id = attempt.python_repeat_application_id
        if not application_id and attempt.python_repeat_installment_id:
            installment = await session.get(
                PythonRepeatInstallment, attempt.python_repeat_installment_id
            )
            if installment:
                from app.opportunities.models import (
                    PythonRepeatEnrollment,
                    PythonRepeatSuccessFeeObligation,
                )

                obligation = await session.get(
                    PythonRepeatSuccessFeeObligation, installment.obligation_id
                )
                enrollment = (
                    await session.get(PythonRepeatEnrollment, obligation.enrollment_id)
                    if obligation
                    else None
                )
                application_id = enrollment.application_id if enrollment else None
        link = (
            f"/admin/opportunities/python-repeat?application={application_id}"
            if application_id
            else "/admin/opportunities"
        )
        product = "Повторное Python-менторство"
        resource = (
            await session.get(PythonRepeatApplication, application_id) if application_id else None
        )
    student = await session.get(User, resource.student_id) if resource else None
    identity = f"{student.first_name} {student.last_name or ''}" if student else "Ученик не найден"
    await notify_admins(
        session,
        event_key=f"opportunity-payment-review:{attempt.id}",
        title="Оплата требует проверки",
        body=f"{product}. {identity}. Попытка оплаты: {attempt.id}",
        link=link,
    )


async def opportunity_summary(
    session: AsyncSession, *, at: datetime | None = None
) -> OpportunitySummary:
    at = at or datetime.now(UTC)
    rows = stage_rows(at)
    counts = await session.execute(
        select(
            rows.c.product,
            rows.c.stage,
            func.count().label("count"),
            func.count().filter(needs_action_sql(rows)).label("needs_action"),
            func.count().filter(overdue_sql(rows, at)).label("overdue"),
        ).group_by(rows.c.product, rows.c.stage)
    )
    result = OpportunitySummary()
    for product, stage, count, needs_action, overdue in counts:
        getattr(result, product)[stage] = count
        result.needs_action_total += needs_action
        result.overdue_total += overdue
    return result


async def opportunity_digest(session: AsyncSession, *, at: datetime | None = None) -> None:
    settings = get_settings()
    at = at or datetime.now(UTC)
    local = at.astimezone(ZoneInfo(settings.notification_reminder_timezone))
    if local.hour != settings.notification_reminder_hour:
        return
    summary = await opportunity_summary(session, at=at)
    if not summary.overdue_total:
        return
    rows = stage_rows(at)
    counts = await session.execute(
        select(rows.c.stage, func.count()).where(overdue_sql(rows, at)).group_by(rows.c.stage)
    )
    labels = {
        "new": "новые заявки",
        "review": "на рассмотрении",
        "needs_schedule": "назначить время",
        "needs_completion": "встречи прошли — нужно закрыть",
        "payment_review": "проверить оплату",
        "expired": "условия истекли",
        "needs_mentor": "назначить ментора",
        "offer_review": "проверить оффер",
    }
    body = "Ждут действия: " + "; ".join(f"{labels[stage]} — {count}" for stage, count in counts)
    await notify_admins(
        session,
        event_key=f"opportunity-digest:{local.date()}",
        title="Заявки требуют внимания",
        body=body,
        link="/admin/opportunities",
    )
