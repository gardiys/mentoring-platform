from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import api_error
from app.legal.models import LegalCheckout
from app.opportunities.models import (
    ConsultationRequest,
    ConsultationStatus,
    GoTransitionApplication,
    GoTransitionStatus,
    OpportunityPaymentAttempt,
)
from app.opportunities.notifications import notify_admins, notify_user
from app.opportunities.service import (
    ALUMNI_GO_SUCCESS_FEE_PERCENT,
    ALUMNI_GO_UPFRONT_PRICE_KOPECKS,
    CONSULTATION_TYPES,
    GO_TRANSITION_OFFER_VALID_DAYS,
    GO_TRANSITION_TERMS_VERSION,
    _go_transition_terms_snapshot,
    _mentor_options,
    _track_state,
)
from app.opportunities.workspace_history import record_history
from app.payments.models import MentorReward, MentorRewardKind, PaymentAttemptStatus
from app.users.models import User

ConsultationAction = Literal[
    "approve", "reject", "mentor", "schedule", "complete", "summary", "cancel", "internal-note"
]
GoAction = Literal["approve", "reject", "extend", "cancel", "internal-note"]


async def go_payment_block_reason(session: AsyncSession, application_id: UUID) -> str | None:
    attempt = await session.scalar(
        select(OpportunityPaymentAttempt.id)
        .where(
            OpportunityPaymentAttempt.transition_application_id == application_id,
            OpportunityPaymentAttempt.status.in_(
                [
                    PaymentAttemptStatus.PENDING,
                    PaymentAttemptStatus.APPROVED,
                    PaymentAttemptStatus.MANUAL_REVIEW,
                ]
            ),
        )
        .limit(1)
    )
    if attempt:
        return "Сначала дождитесь завершения или проверки текущей попытки оплаты"
    checkout = await session.scalar(
        select(LegalCheckout.id)
        .where(
            LegalCheckout.application_id == application_id,
            LegalCheckout.status == "pending",
            LegalCheckout.expires_at > datetime.now(UTC),
        )
        .limit(1)
    )
    if checkout:
        return "У выпускника открыт действующий платёж по оферте. Дождитесь его завершения"
    return None


async def validate_mentor(session: AsyncSession, student_id: UUID, mentor_id: UUID) -> User:
    tracks, _active = await _track_state(session, student_id)
    if mentor_id not in {mentor.id for mentor in await _mentor_options(session, tracks)}:
        api_error(
            422,
            "consultation_mentor_not_available",
            "Выбранный ментор недоступен для этой консультации",
        )
    mentor = await session.get(User, mentor_id)
    assert mentor is not None
    return mentor


async def consultation_command(
    session: AsyncSession,
    admin: User,
    request_id: UUID,
    action: ConsultationAction,
    data: dict[str, Any],
) -> None:
    item = await session.scalar(
        select(ConsultationRequest).where(ConsultationRequest.id == request_id).with_for_update()
    )
    if item is None:
        api_error(404, "consultation_not_found", "Консультация не найдена")
    allowed = {
        "approve": {"requested"},
        "reject": {"requested"},
        "mentor": {"requested", "payment_pending", "paid", "scheduled"},
        "schedule": {"paid", "scheduled"},
        "complete": {"paid", "scheduled"},
        "summary": {"completed"},
        "cancel": {"payment_pending", "paid", "scheduled"},
    }
    if action != "internal-note" and str(item.status) not in allowed[action]:
        api_error(
            409, "invalid_consultation_transition", "Это действие недоступно на текущем этапе"
        )
    # Validate all preconditions before touching persisted fields.
    if action in {"approve", "mentor"}:
        await validate_mentor(session, item.student_id, data["mentor_id"])
    if action in {"schedule", "complete"} and (item.paid_at is None or item.mentor_id is None):
        api_error(409, "consultation_not_paid", "Нужны подтверждённая оплата и назначенный ментор")
    if action == "cancel" and item.paid_at and data.get("refund_required") is None:
        api_error(422, "refund_choice_required", "Укажите, требуется ли возврат денег")
    old_status = str(item.status)
    old_mentor = item.mentor_id
    now = datetime.now(UTC)
    title, body = "", ""
    if action == "approve":
        item.mentor_id = data["mentor_id"]
        item.admin_note = data.get("message_to_student")
        item.status = ConsultationStatus.PAYMENT_PENDING
        title, body = (
            "Консультация подтверждена — можно оплатить",
            item.admin_note or "Счёт доступен в кабинете выпускника",
        )
    elif action == "mentor":
        item.mentor_id = data["mentor_id"]
    elif action == "schedule":
        item.scheduled_at = data["scheduled_at"]
        item.status = ConsultationStatus.SCHEDULED
        title = (
            "Время консультации перенесено"
            if old_status == "scheduled"
            else "Время консультации назначено"
        )
    elif action in {"complete", "summary"}:
        item.written_summary = data["written_summary"]
        if action == "complete":
            item.scheduled_at = item.scheduled_at or data.get("held_at") or now
            item.status = ConsultationStatus.COMPLETED
            item.completed_at = item.completed_at or now
            existing = await session.scalar(
                select(MentorReward.id).where(MentorReward.consultation_request_id == item.id)
            )
            if existing is None:
                session.add(
                    MentorReward(
                        consultation_request_id=item.id,
                        student_id=item.student_id,
                        mentor_id=item.mentor_id,
                        kind=MentorRewardKind.CONSULTATION,
                        basis_kopecks=item.price_kopecks,
                        amount_kopecks=item.mentor_reward_kopecks,
                        paid_kopecks=0,
                    )
                )
        title, body = (
            "Итог консультации готов",
            "Итог и рекомендации доступны в кабинете выпускника",
        )
    elif action in {"cancel", "reject"}:
        item.status = ConsultationStatus.CANCELLED
        item.admin_note = data["reason"]
        await session.execute(
            update(OpportunityPaymentAttempt)
            .where(
                OpportunityPaymentAttempt.consultation_request_id == item.id,
                OpportunityPaymentAttempt.status == PaymentAttemptStatus.PENDING,
            )
            .values(status=PaymentAttemptStatus.REVOKED)
        )
        title, body = "Консультация отменена", item.admin_note
        if data.get("refund_required"):
            body += " Деньги вернут вручную после обработки возврата командой."
    elif action == "internal-note":
        item.internal_note = data.get("internal_note")
    snapshot = {**data, "action": action}
    if action == "mentor":
        snapshot["previous_mentor_id"] = old_mentor
    event_id = record_history(
        session,
        item,
        old_status,
        actor_id=admin.id,
        comment=data.get("reason") or data.get("message_to_student"),
        snapshot=snapshot,
    )
    student = await session.get(User, item.student_id)
    assert student is not None
    link = "/opportunities/alumni/consultations"
    if action == "schedule" or (action == "mentor" and item.status is ConsultationStatus.SCHEDULED):
        assert item.scheduled_at is not None
        local = item.scheduled_at.astimezone(
            ZoneInfo(get_settings().notification_reminder_timezone)
        )
        timezone_label = "МСК" if str(local.tzinfo) == "Europe/Moscow" else local.strftime("%Z")
        body = f"{local:%d.%m.%Y %H:%M} {timezone_label}, {item.duration_minutes} мин"
        if action == "mentor":
            title = "Назначен новый ментор консультации"
        mentor = await session.get(User, item.mentor_id)
        if mentor:
            format_label = next(
                row.title for row in CONSULTATION_TYPES if row.code == item.consultation_type
            )
            contacts = (
                f"{student.first_name} {student.last_name or ''} · @{student.telegram_username}"
                if student.telegram_username
                else f"{student.first_name} · {student.email or 'контакты в профиле'}"
            )
            await notify_user(
                session,
                mentor,
                event_key=f"consultation:{event_id}:mentor",
                title=title,
                body=f"{body}\n{format_label}\n{contacts}\n{item.brief[:2000]}",
                link=None,
                actor_id=admin.id,
            )
    if title:
        await notify_user(
            session,
            student,
            event_key=f"consultation:{event_id}",
            title=title,
            body=body,
            link=link,
            actor_id=admin.id,
        )
    if action == "cancel" and data.get("refund_required"):
        await notify_admins(
            session,
            event_key=f"consultation-refund:{event_id}",
            title="Оформите возврат за консультацию",
            body=f"{student.first_name}. {data['reason']}",
            link=f"/admin/opportunities?consultation={item.id}",
            actor_id=admin.id,
        )
    await session.commit()


async def go_command(
    session: AsyncSession, admin: User, application_id: UUID, action: GoAction, data: dict[str, Any]
) -> None:
    item = await session.scalar(
        select(GoTransitionApplication)
        .where(GoTransitionApplication.id == application_id)
        .with_for_update()
    )
    if item is None:
        api_error(404, "go_transition_not_found", "Заявка не найдена")
    if action in {"approve", "reject"} and item.status is not GoTransitionStatus.SUBMITTED:
        api_error(409, "go_transition_already_decided", "Заявка уже рассмотрена")
    now = datetime.now(UTC)
    if action in {"extend", "cancel"}:
        if item.status not in {GoTransitionStatus.APPROVED, GoTransitionStatus.PAYMENT_PENDING}:
            api_error(409, "invalid_go_transition", "Действие недоступно на текущем этапе")
        blocked = await go_payment_block_reason(session, item.id)
        if blocked:
            api_error(409, "go_payment_in_progress", blocked)
        if action == "extend" and (item.terms_expires_at is None or item.terms_expires_at > now):
            api_error(409, "go_terms_not_expired", "Срок одобренных условий ещё не истёк")
    old_status = str(item.status)
    if action in {"approve", "extend"}:
        if action == "approve":
            item.status = GoTransitionStatus.APPROVED
            item.admin_note = data.get("message_to_student")
        item.approved_at = now
        item.approved_by_user_id = admin.id
        item.terms_snapshot = _go_transition_terms_snapshot()
        item.terms_version = GO_TRANSITION_TERMS_VERSION
        item.upfront_price_kopecks = ALUMNI_GO_UPFRONT_PRICE_KOPECKS
        item.success_fee_percent = ALUMNI_GO_SUCCESS_FEE_PERCENT
        item.terms_expires_at = now + timedelta(days=GO_TRANSITION_OFFER_VALID_DAYS)
        item.terms_accepted_at = None
        item.accepted_terms_snapshot = None
    elif action in {"reject", "cancel"}:
        item.status = (
            GoTransitionStatus.REJECTED if action == "reject" else GoTransitionStatus.CANCELLED
        )
        item.admin_note = data["reason"]
    elif action == "internal-note":
        item.internal_note = data.get("internal_note")
    snapshot = {**data, "action": action}
    if action in {"approve", "extend"}:
        snapshot.update(terms_snapshot=item.terms_snapshot, terms_expires_at=item.terms_expires_at)
    event_id = record_history(
        session,
        item,
        old_status,
        actor_id=admin.id,
        comment=data.get("reason") or data.get("message_to_student"),
        snapshot=snapshot,
    )
    if action != "internal-note":
        labels = {
            "approve": "Заявка на Go одобрена",
            "reject": "Заявка на Go отклонена",
            "cancel": "Заявка на Go отменена",
            "extend": "Условия перехода в Go продлены",
        }
        student = await session.get(User, item.student_id)
        assert student is not None
        body = item.admin_note or "Решение доступно в кабинете выпускника"
        if action in {"approve", "extend"} and item.terms_expires_at:
            body += f". Условия действуют до {item.terms_expires_at:%d.%m.%Y}"
        await notify_user(
            session,
            student,
            event_key=f"go:{event_id}",
            title=labels[action],
            body=body,
            link="/opportunities/alumni/go-transition",
            actor_id=admin.id,
        )
    await session.commit()
