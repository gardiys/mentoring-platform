from __future__ import annotations

import calendar
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import cast
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import api_error
from app.mentors.models import MentorStudent, StudentLearningStatus
from app.notifications.models import NotificationKind
from app.notifications.service import create_notification
from app.opportunities.models import (
    GoTransitionApplication,
    GoTransitionStatus,
    OpportunityPaymentAttempt,
    PythonRepeatApplication,
    PythonRepeatApplicationHistory,
    PythonRepeatApplicationStatus,
    PythonRepeatEmploymentOffer,
    PythonRepeatEnrollment,
    PythonRepeatEnrollmentStatus,
    PythonRepeatEvent,
    PythonRepeatInstallment,
    PythonRepeatInstallmentStatus,
    PythonRepeatObligationStatus,
    PythonRepeatOfferStatus,
    PythonRepeatProductOffer,
    PythonRepeatSuccessFeeObligation,
)
from app.opportunities.python_repeat_schemas import (
    AdminPythonRepeatApplicationRead,
    AdminPythonRepeatDashboard,
    AdminPythonRepeatOfferDecision,
    AdminPythonRepeatStudentRead,
    AdminPythonRepeatTransition,
    PythonRepeatApplicationCreate,
    PythonRepeatApplicationRead,
    PythonRepeatDashboard,
    PythonRepeatEligibilityRead,
    PythonRepeatEnrollmentRead,
    PythonRepeatInstallmentRead,
    PythonRepeatObligationRead,
    PythonRepeatOfferCreate,
    PythonRepeatOfferRead,
    PythonRepeatStatusHistoryRead,
    PythonRepeatTermsAcceptance,
)
from app.opportunities.schemas import OpportunityPaymentLinkRead
from app.opportunities.service import _student_has_overdue_obligations, _track_state
from app.payments.models import (
    MentorReward,
    MentorRewardKind,
    PaymentAttemptStatus,
    StudentEmployment,
    StudentEmploymentStatus,
)
from app.payments.tochka import TochkaError, TochkaPaymentService
from app.tracks.models import LearningTrack
from app.users.models import MENTOR_CAPABLE_ROLES, User, UserRole

PRODUCT_CODE = "PYTHON_REPEAT_MENTORSHIP"
DEFAULT_UPFRONT_KOPECKS = 3_000_000
DEFAULT_SUCCESS_FEE_PERCENT = 100
DEFAULT_INSTALLMENTS_COUNT = 2
DEFAULT_MENTOR_FIXED_KOPECKS = 1_000_000
DEFAULT_MENTOR_SHARE_PERCENT = 30
DEFAULT_ACTIVE_SUPPORT_MONTHS = 4
DEFAULT_PROBATION_SUPPORT_DAYS = 30
DEFAULT_INCLUDED_MOCKS = 2
DEFAULT_OFFER_VALID_DAYS = 14

ACTIVE_APPLICATION_STATUSES = {
    PythonRepeatApplicationStatus.DRAFT,
    PythonRepeatApplicationStatus.SUBMITTED,
    PythonRepeatApplicationStatus.UNDER_REVIEW,
    PythonRepeatApplicationStatus.NEEDS_DIAGNOSTIC,
    PythonRepeatApplicationStatus.NEEDS_CLARIFICATION,
    PythonRepeatApplicationStatus.APPROVED,
    PythonRepeatApplicationStatus.TERMS_ACCEPTED,
    PythonRepeatApplicationStatus.PAYMENT_PENDING,
    PythonRepeatApplicationStatus.PAID,
}


def _now() -> datetime:
    return datetime.now(UTC)


def _percent(amount: int, value: int) -> int:
    return int(
        (Decimal(amount) * Decimal(value) / Decimal(100)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


def _add_calendar_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _snapshot_int(snapshot: dict[str, object], key: str) -> int:
    value = snapshot.get(key)
    if not isinstance(value, int):
        raise ValueError(f"Invalid immutable terms snapshot: {key}")
    return value


async def _active_product(session: AsyncSession) -> PythonRepeatProductOffer:
    product = await session.scalar(
        select(PythonRepeatProductOffer)
        .where(PythonRepeatProductOffer.is_active.is_(True))
        .order_by(PythonRepeatProductOffer.version.desc())
        .limit(1)
    )
    if product is None:
        api_error(503, "python_repeat_offer_missing", "Product terms are not configured")
    return product


def _product_snapshot(product: PythonRepeatProductOffer) -> dict[str, object]:
    snapshot: dict[str, object] = {
        "product_code": PRODUCT_CODE,
        "terms_version": product.version,
        "upfront_price_kopecks": product.upfront_price_kopecks,
        "currency": "RUB",
        "success_fee_percent": product.success_fee_percent,
        "success_fee_installments_count": product.success_fee_installments_count,
        "mentor_fixed_accrual_kopecks": product.mentor_fixed_accrual_kopecks,
        "mentor_success_fee_share_percent": product.mentor_success_fee_share_percent,
        "active_support_months": product.active_support_months,
        "probation_support_days": product.probation_support_days,
        "included_mock_interviews": product.included_mock_interviews,
        "offer_valid_days": product.offer_valid_days,
    }
    if product.public_offer_revision:
        snapshot.update(
            {
                "success_fee_installment_percent": 50,
                "success_fee_first_due_months_after_employment": 1,
                "success_fee_second_due_months_after_employment": 2,
                "success_fee_minimum_kopecks": 0,
                "pre_acceptance_employment_processes_excluded": True,
                "public_offer_revision": product.public_offer_revision,
                "public_offer_published_at": (
                    product.public_offer_published_at.isoformat()
                    if product.public_offer_published_at
                    else None
                ),
                "public_offer_url": product.public_offer_url,
                "public_offer_sha256": product.public_offer_sha256,
                "acceptance_statement": product.acceptance_statement,
                "contract_acceptance_method": "payment_crediting",
            }
        )
    return snapshot


def _application_answers_snapshot(item: PythonRepeatApplication) -> dict[str, object]:
    return {
        "employment_status": item.employment_status.value,
        "reason": item.reason.value,
        "current_position": item.current_position,
        "current_company": item.current_company,
        "current_stack": item.current_stack,
        "last_interview_at": (
            item.last_interview_at.isoformat() if item.last_interview_at else None
        ),
        "target_position": item.target_position,
        "target_salary_kopecks": item.target_salary_kopecks,
        "technical_gaps": item.technical_gaps,
        "hours_per_week": item.hours_per_week,
        "desired_start_date": (
            item.desired_start_date.isoformat() if item.desired_start_date else None
        ),
        "search_mode": item.search_mode.value,
        "additional_comment": item.additional_comment,
    }


async def python_repeat_eligibility(
    session: AsyncSession,
    student: User,
    *,
    ignore_application_id: UUID | None = None,
) -> PythonRepeatEligibilityRead:
    settings = get_settings()
    if not settings.opportunities_enabled or not settings.python_repeat_mentorship_enabled:
        return PythonRepeatEligibilityRead(
            eligible=False,
            code="FEATURE_DISABLED",
            message="Повторное менторство временно недоступно.",
        )
    if not student.is_active:
        return PythonRepeatEligibilityRead(
            eligible=False,
            code="ACCOUNT_INACTIVE",
            message="Доступ к аккаунту закрыт.",
        )
    completed_tracks, active_tracks = await _track_state(session, student.id)
    completed_python = next((track for track in completed_tracks if _is_python(track)), None)
    if completed_python is None:
        return PythonRepeatEligibilityRead(
            eligible=False,
            code="PYTHON_NOT_COMPLETED",
            message="Программа доступна после завершения Python-направления.",
        )
    if any(_is_python(track) or _is_go(track) for track in active_tracks):
        return PythonRepeatEligibilityRead(
            eligible=False,
            code="ACTIVE_LONG_PROGRAM",
            message="Сначала завершите текущее долгосрочное обучение.",
        )
    initial_support_employment = await session.scalar(
        select(StudentEmployment.id)
        .where(
            StudentEmployment.student_id == student.id,
            StudentEmployment.status == StudentEmploymentStatus.ACTIVE,
            StudentEmployment.start_date > (_now().date() - timedelta(days=30)),
        )
        .limit(1)
    )
    if initial_support_employment is not None:
        return PythonRepeatEligibilityRead(
            eligible=False,
            code="INITIAL_SUPPORT_ACTIVE",
            message="Повторная программа станет доступна после первых 30 дней поддержки на работе.",
        )
    active_enrollment = await session.scalar(
        select(PythonRepeatEnrollment.id).where(
            PythonRepeatEnrollment.student_id == student.id,
            PythonRepeatEnrollment.status == PythonRepeatEnrollmentStatus.ACTIVE,
        )
    )
    if active_enrollment is not None:
        return PythonRepeatEligibilityRead(
            eligible=False,
            code="ACTIVE_REPEAT_ENROLLMENT",
            message="У вас уже есть активное повторное менторство.",
        )
    active_go = await session.scalar(
        select(GoTransitionApplication.id).where(
            GoTransitionApplication.student_id == student.id,
            GoTransitionApplication.status.in_(
                [
                    GoTransitionStatus.SUBMITTED,
                    GoTransitionStatus.APPROVED,
                    GoTransitionStatus.PAYMENT_PENDING,
                    GoTransitionStatus.PAID,
                ]
            ),
        )
    )
    if active_go is not None:
        return PythonRepeatEligibilityRead(
            eligible=False,
            code="ACTIVE_GO_APPLICATION",
            message="У вас уже есть активная заявка на переход в Go.",
        )
    active_application = await session.scalar(
        select(PythonRepeatApplication.id).where(
            PythonRepeatApplication.student_id == student.id,
            PythonRepeatApplication.status.in_(ACTIVE_APPLICATION_STATUSES),
            *(
                [PythonRepeatApplication.id != ignore_application_id]
                if ignore_application_id is not None
                else []
            ),
        )
    )
    if active_application is not None:
        return PythonRepeatEligibilityRead(
            eligible=False,
            code="ACTIVE_REPEAT_APPLICATION",
            message="У вас уже есть активная заявка.",
        )
    if await _student_has_overdue_obligations(session, student.id):
        return PythonRepeatEligibilityRead(
            eligible=False,
            code="OVERDUE_OBLIGATIONS",
            message="Перед новой программой нужно закрыть просроченные обязательства.",
        )
    repeat_overdue = await session.scalar(
        select(PythonRepeatInstallment.id)
        .join(
            PythonRepeatSuccessFeeObligation,
            PythonRepeatSuccessFeeObligation.id == PythonRepeatInstallment.obligation_id,
        )
        .join(
            PythonRepeatEnrollment,
            PythonRepeatEnrollment.id == PythonRepeatSuccessFeeObligation.enrollment_id,
        )
        .where(
            PythonRepeatEnrollment.student_id == student.id,
            PythonRepeatInstallment.status.in_(
                [
                    PythonRepeatInstallmentStatus.SCHEDULED,
                    PythonRepeatInstallmentStatus.PENDING,
                ]
            ),
            PythonRepeatInstallment.due_at < _now(),
        )
        .limit(1)
    )
    if repeat_overdue is not None:
        return PythonRepeatEligibilityRead(
            eligible=False,
            code="OVERDUE_REPEAT_OBLIGATIONS",
            message="Перед новой программой нужно закрыть просроченные обязательства.",
        )
    return PythonRepeatEligibilityRead(
        eligible=True,
        code="ELIGIBLE",
        message="Вы можете подать заявку на повторное менторство по Python.",
    )


def _is_python(track: LearningTrack) -> bool:
    value = f"{track.slug} {track.title}".casefold()
    return "python" in value or "питон" in value


def _is_go(track: LearningTrack) -> bool:
    value = f"{track.slug} {track.title}".casefold()
    return track.slug.casefold() == "go" or value.startswith("go ") or " golang" in value


async def _event(
    session: AsyncSession,
    event_type: str,
    aggregate_id: UUID,
    actor_id: UUID | None,
    *,
    suffix: str = "1",
    payload: dict[str, object] | None = None,
) -> None:
    await session.execute(
        insert(PythonRepeatEvent)
        .values(
            event_key=f"{event_type}:{aggregate_id}:{suffix}",
            event_type=event_type,
            aggregate_id=aggregate_id,
            actor_user_id=actor_id,
            payload=payload or {},
            created_at=_now(),
        )
        .on_conflict_do_nothing(index_elements=[PythonRepeatEvent.event_key])
    )


async def _notify_admins(
    session: AsyncSession,
    *,
    event_key: str,
    title: str,
    body: str,
    actor_id: UUID,
) -> None:
    admin_ids = await session.scalars(
        select(User.id).where(User.role == UserRole.ADMIN, User.is_active.is_(True))
    )
    for admin_id in admin_ids:
        await create_notification(
            session,
            user_id=admin_id,
            actor_user_id=actor_id,
            event_key=event_key,
            kind=NotificationKind.STATUS_CHANGED,
            title=title,
            body=body,
            action_url="/admin/opportunities/python-repeat",
        )


async def _notify_student(
    session: AsyncSession,
    *,
    student_id: UUID,
    event_key: str,
    title: str,
    body: str,
    actor_id: UUID | None = None,
    kind: NotificationKind = NotificationKind.STATUS_CHANGED,
) -> None:
    await create_notification(
        session,
        user_id=student_id,
        actor_user_id=actor_id,
        event_key=event_key,
        kind=kind,
        title=title,
        body=body,
        action_url="/opportunities/alumni/python-repeat",
    )


async def _transition(
    session: AsyncSession,
    application: PythonRepeatApplication,
    new_status: PythonRepeatApplicationStatus,
    actor_id: UUID | None,
    *,
    comment: str | None = None,
) -> None:
    old = application.status
    if old is new_status:
        return
    allowed: dict[PythonRepeatApplicationStatus, set[PythonRepeatApplicationStatus]] = {
        PythonRepeatApplicationStatus.DRAFT: {
            PythonRepeatApplicationStatus.SUBMITTED,
            PythonRepeatApplicationStatus.CANCELLED,
        },
        PythonRepeatApplicationStatus.SUBMITTED: {
            PythonRepeatApplicationStatus.UNDER_REVIEW,
            PythonRepeatApplicationStatus.CANCELLED,
        },
        PythonRepeatApplicationStatus.UNDER_REVIEW: {
            PythonRepeatApplicationStatus.NEEDS_DIAGNOSTIC,
            PythonRepeatApplicationStatus.NEEDS_CLARIFICATION,
            PythonRepeatApplicationStatus.APPROVED,
            PythonRepeatApplicationStatus.REJECTED,
            PythonRepeatApplicationStatus.CANCELLED,
        },
        PythonRepeatApplicationStatus.NEEDS_DIAGNOSTIC: {
            PythonRepeatApplicationStatus.UNDER_REVIEW,
            PythonRepeatApplicationStatus.CANCELLED,
        },
        PythonRepeatApplicationStatus.NEEDS_CLARIFICATION: {
            PythonRepeatApplicationStatus.SUBMITTED,
            PythonRepeatApplicationStatus.CANCELLED,
        },
        PythonRepeatApplicationStatus.APPROVED: {
            PythonRepeatApplicationStatus.TERMS_ACCEPTED,
            PythonRepeatApplicationStatus.EXPIRED,
            PythonRepeatApplicationStatus.CANCELLED,
        },
        PythonRepeatApplicationStatus.TERMS_ACCEPTED: {
            PythonRepeatApplicationStatus.PAYMENT_PENDING,
            PythonRepeatApplicationStatus.CANCELLED,
        },
        PythonRepeatApplicationStatus.PAYMENT_PENDING: {
            PythonRepeatApplicationStatus.PAID,
            PythonRepeatApplicationStatus.CANCELLED,
        },
        PythonRepeatApplicationStatus.PAID: {PythonRepeatApplicationStatus.ENROLLED},
        PythonRepeatApplicationStatus.REJECTED: set(),
        PythonRepeatApplicationStatus.ENROLLED: set(),
        PythonRepeatApplicationStatus.CANCELLED: set(),
        PythonRepeatApplicationStatus.EXPIRED: set(),
    }
    if new_status not in allowed[old]:
        api_error(
            409, "invalid_python_repeat_transition", f"Cannot move from {old} to {new_status}"
        )
    application.status = new_status
    session.add(
        PythonRepeatApplicationHistory(
            application_id=application.id,
            old_status=old,
            new_status=new_status,
            actor_user_id=actor_id,
            comment=comment,
            snapshot=application.terms_snapshot,
            created_at=_now(),
        )
    )
    await _event(
        session,
        f"PYTHON_REPEAT_APPLICATION_{new_status.value.upper()}",
        application.id,
        actor_id,
        suffix=str(len(application.status.value)) + f"-{_now().timestamp()}",
    )


async def create_application(
    session: AsyncSession, student: User, payload: PythonRepeatApplicationCreate
) -> PythonRepeatDashboard:
    eligibility = await python_repeat_eligibility(session, student)
    if not eligibility.eligible:
        api_error(409, eligibility.code.casefold(), eligibility.message)
    item = PythonRepeatApplication(student_id=student.id, **payload.model_dump())
    session.add(item)
    await session.flush()
    session.add(
        PythonRepeatApplicationHistory(
            application_id=item.id,
            old_status=None,
            new_status=PythonRepeatApplicationStatus.DRAFT,
            actor_user_id=student.id,
            created_at=_now(),
        )
    )
    await _event(session, "python_repeat_application_started", item.id, student.id)
    await session.commit()
    return await dashboard(session, student)


async def update_application(
    session: AsyncSession,
    student: User,
    application_id: UUID,
    payload: PythonRepeatApplicationCreate,
) -> PythonRepeatDashboard:
    item = await _owned_application(session, student.id, application_id, lock=True)
    if item.status not in {
        PythonRepeatApplicationStatus.DRAFT,
        PythonRepeatApplicationStatus.NEEDS_CLARIFICATION,
    }:
        api_error(
            409,
            "python_repeat_application_not_editable",
            "Application can only be edited while it is a draft or needs clarification",
        )
    for field, value in payload.model_dump().items():
        setattr(item, field, value)
    await _event(
        session,
        "python_repeat_application_updated",
        item.id,
        student.id,
        suffix=(
            str(item.updated_at.timestamp())
            if item.updated_at is not None
            else str(_now().timestamp())
        ),
    )
    await session.commit()
    return await dashboard(session, student)


async def submit_application(
    session: AsyncSession, student: User, application_id: UUID
) -> PythonRepeatDashboard:
    item = await _owned_application(session, student.id, application_id, lock=True)
    eligibility = await python_repeat_eligibility(session, student, ignore_application_id=item.id)
    if not eligibility.eligible and item.eligibility_override_by_user_id is None:
        api_error(409, eligibility.code.casefold(), eligibility.message)
    if item.status is PythonRepeatApplicationStatus.NEEDS_CLARIFICATION:
        await _transition(session, item, PythonRepeatApplicationStatus.SUBMITTED, student.id)
    else:
        await _transition(session, item, PythonRepeatApplicationStatus.SUBMITTED, student.id)
    await _event(session, "python_repeat_application_submitted", item.id, student.id)
    await _notify_admins(
        session,
        event_key=f"python-repeat-application-submitted:{item.id}",
        title="Новая заявка на повторное Python-менторство",
        body=f"Выпускник {student.first_name} отправил заявку на рассмотрение.",
        actor_id=student.id,
    )
    await session.commit()
    return await dashboard(session, student)


async def accept_terms(
    session: AsyncSession,
    student: User,
    application_id: UUID,
    *,
    acceptance: PythonRepeatTermsAcceptance,
    ip_address: str | None,
    user_agent: str | None,
    accept_language: str | None,
    request_id: str | None,
) -> PythonRepeatDashboard:
    item = await _owned_application(session, student.id, application_id, lock=True)
    if item.offer_expires_at is not None and item.offer_expires_at < _now():
        await _transition(session, item, PythonRepeatApplicationStatus.EXPIRED, student.id)
        await session.commit()
        api_error(409, "python_repeat_offer_expired", "The approved terms have expired")
    terms = item.terms_snapshot
    if terms is None:
        api_error(409, "python_repeat_terms_missing", "Approved terms were not found")
    expected_revision = terms.get("public_offer_revision")
    expected_hash = terms.get("public_offer_sha256")
    expected_statement = terms.get("acceptance_statement")
    if not all(
        isinstance(value, str) and value
        for value in (expected_revision, expected_hash, expected_statement)
    ):
        api_error(
            409,
            "python_repeat_public_offer_missing",
            "The approved public offer is not configured; ask the team to renew the offer",
        )
    if (
        acceptance.terms_version != item.terms_version
        or acceptance.public_offer_revision != expected_revision
        or acceptance.public_offer_sha256 != expected_hash
        or acceptance.acceptance_statement != expected_statement
    ):
        api_error(
            409,
            "python_repeat_offer_changed",
            "The public offer has changed; reload the page and review the current revision",
        )
    accepted_at = _now()
    await _transition(session, item, PythonRepeatApplicationStatus.TERMS_ACCEPTED, student.id)
    item.accepted_at = accepted_at
    item.accepted_by_user_id = student.id
    item.acceptance_ip_address = ip_address
    item.acceptance_user_agent = user_agent[:500] if user_agent else None
    item.acceptance_evidence = {
        "evidence_version": 1,
        "recorded_at": accepted_at.isoformat(),
        "application_id": str(item.id),
        "user": {
            "id": str(student.id),
            "email": student.email,
            "telegram_id": student.telegram_id,
            "telegram_username": student.telegram_username,
        },
        "application_answers": _application_answers_snapshot(item),
        "explicit_acceptance": {
            "accepted": acceptance.accepted,
            "statement": acceptance.acceptance_statement,
        },
        "offer": {
            "terms_version": item.terms_version,
            "revision": expected_revision,
            "published_at": terms.get("public_offer_published_at"),
            "url": terms.get("public_offer_url"),
            "sha256": expected_hash,
            "financial_terms": terms,
        },
        "technical": {
            "ip_address": ip_address,
            "user_agent": user_agent[:500] if user_agent else None,
            "accept_language": accept_language[:250] if accept_language else None,
            "request_id": request_id,
        },
        "contract_acceptance_method": "payment_crediting",
    }
    await _event(
        session,
        "python_repeat_terms_accepted",
        item.id,
        student.id,
        payload={
            "terms_version": item.terms_version,
            "public_offer_revision": expected_revision,
            "public_offer_sha256": expected_hash,
        },
    )
    await session.commit()
    return await dashboard(session, student)


async def checkout(
    session: AsyncSession, student: User, application_id: UUID
) -> OpportunityPaymentLinkRead:
    item = await _owned_application(session, student.id, application_id, lock=True)
    eligibility = await python_repeat_eligibility(session, student, ignore_application_id=item.id)
    if (
        not eligibility.eligible
        and eligibility.code != "FEATURE_DISABLED"
        and item.eligibility_override_by_user_id is None
    ):
        api_error(409, eligibility.code.casefold(), eligibility.message)
    if item.status is PythonRepeatApplicationStatus.TERMS_ACCEPTED:
        await _transition(session, item, PythonRepeatApplicationStatus.PAYMENT_PENDING, student.id)
    if item.status is not PythonRepeatApplicationStatus.PAYMENT_PENDING:
        api_error(409, "python_repeat_not_payable", "Application is not ready for payment")
    assert item.terms_snapshot is not None
    amount = _snapshot_int(item.terms_snapshot, "upfront_price_kopecks")
    result = await _payment_link(
        session,
        student,
        resource_id=item.id,
        amount=amount,
        repeat_application=item,
        return_path="/opportunities/alumni/python-repeat",
    )
    await _event(
        session,
        "python_repeat_checkout_started",
        item.id,
        student.id,
        suffix=result.payment_link_id,
    )
    await session.commit()
    return result


async def _payment_link(
    session: AsyncSession,
    student: User,
    *,
    resource_id: UUID,
    amount: int,
    repeat_application: PythonRepeatApplication | None = None,
    repeat_installment: PythonRepeatInstallment | None = None,
    return_path: str,
) -> OpportunityPaymentLinkRead:
    attempts = list(
        await session.scalars(
            select(OpportunityPaymentAttempt)
            .where(
                (OpportunityPaymentAttempt.python_repeat_application_id == resource_id)
                if repeat_application is not None
                else (OpportunityPaymentAttempt.python_repeat_installment_id == resource_id)
            )
            .order_by(OpportunityPaymentAttempt.created_at)
        )
    )
    for attempt in attempts:
        if attempt.status is PaymentAttemptStatus.PENDING:
            attempt.status = PaymentAttemptStatus.REVOKED
            attempt.payment_url = None
    if repeat_application is not None:
        payment_terms = repeat_application.terms_snapshot
    else:
        assert repeat_installment is not None
        obligation = await session.get(
            PythonRepeatSuccessFeeObligation, repeat_installment.obligation_id
        )
        if obligation is None:
            api_error(409, "python_repeat_obligation_missing", "Payment obligation was not found")
        payment_terms = obligation.terms_snapshot
    if not student.email:
        api_error(
            422,
            "python_repeat_payment_email_required",
            "Укажите email в профиле перед созданием платёжной ссылки.",
        )
    payment_link_id = f"pyrepeat_{resource_id.hex}_r{len(attempts) + 1}"
    try:
        payment = await TochkaPaymentService(get_settings()).create_payment_link(
            installment_id=resource_id,
            payment_link_id=payment_link_id,
            amount_kopecks=amount,
            client_name=" ".join(filter(None, (student.first_name, student.last_name))),
            client_email=student.email,
            return_path=return_path,
        )
    except TochkaError as error:
        api_error(502, "python_repeat_payment_link_failed", str(error))
    session.add(
        payment_attempt := OpportunityPaymentAttempt(
            python_repeat_application_id=repeat_application.id if repeat_application else None,
            python_repeat_installment_id=repeat_installment.id if repeat_installment else None,
            payment_link_id=payment.payment_link_id,
            provider_operation_id=payment.provider_operation_id,
            status=PaymentAttemptStatus.PENDING,
            payment_url=payment.payment_url,
            terms_snapshot=payment_terms,
            raw_create_response=payment.raw_response,
        )
    )
    await session.flush()
    if repeat_application is not None:
        repeat_application.acceptance_payment_link_id = payment.payment_link_id
        repeat_application.acceptance_provider_operation_id = payment.provider_operation_id
        evidence = dict(repeat_application.acceptance_evidence or {})
        evidence["latest_payment_attempt"] = {
            "attempt_id": str(payment_attempt.id),
            "payment_link_id": payment.payment_link_id,
            "provider_operation_id": payment.provider_operation_id,
            "created_at": _now().isoformat(),
        }
        repeat_application.acceptance_evidence = evidence
    return OpportunityPaymentLinkRead(
        payment_url=payment.payment_url,
        payment_link_id=payment.payment_link_id,
    )


async def approve_python_repeat_payment(
    session: AsyncSession,
    attempt: OpportunityPaymentAttempt,
    *,
    approved_at: datetime,
) -> None:
    if attempt.python_repeat_application_id is not None:
        application = await session.scalar(
            select(PythonRepeatApplication)
            .where(PythonRepeatApplication.id == attempt.python_repeat_application_id)
            .with_for_update()
        )
        if (
            application is None
            or application.status is not PythonRepeatApplicationStatus.PAYMENT_PENDING
        ):
            attempt.status = PaymentAttemptStatus.MANUAL_REVIEW
            return
        assert application.terms_snapshot is not None
        student = await session.get(User, application.student_id)
        if student is None:
            attempt.status = PaymentAttemptStatus.MANUAL_REVIEW
            return
        eligibility = await python_repeat_eligibility(
            session, student, ignore_application_id=application.id
        )
        if (
            not eligibility.eligible
            and eligibility.code != "FEATURE_DISABLED"
            and application.eligibility_override_by_user_id is None
        ):
            attempt.status = PaymentAttemptStatus.MANUAL_REVIEW
            return
        application.paid_at = approved_at
        application.contract_accepted_at = approved_at
        application.acceptance_payment_link_id = attempt.payment_link_id
        application.acceptance_provider_operation_id = attempt.provider_operation_id
        evidence = dict(application.acceptance_evidence or {})
        evidence["contract_acceptance"] = {
            "method": "payment_crediting",
            "accepted_at": approved_at.isoformat(),
            "payment_attempt_id": str(attempt.id),
            "payment_link_id": attempt.payment_link_id,
            "provider_operation_id": attempt.provider_operation_id,
            "amount_kopecks": _snapshot_int(application.terms_snapshot, "upfront_price_kopecks"),
            "currency": application.terms_snapshot.get("currency", "RUB"),
        }
        application.acceptance_evidence = evidence
        await _transition(session, application, PythonRepeatApplicationStatus.PAID, None)
        enrollment = await session.scalar(
            select(PythonRepeatEnrollment).where(
                PythonRepeatEnrollment.application_id == application.id
            )
        )
        if enrollment is None:
            completed_tracks, _ = await _track_state(session, application.student_id)
            python_track = next((track for track in completed_tracks if _is_python(track)), None)
            if python_track is None:
                attempt.status = PaymentAttemptStatus.MANUAL_REVIEW
                return
            enrollment = PythonRepeatEnrollment(
                application_id=application.id,
                student_id=application.student_id,
                track_id=python_track.id,
                previous_track_id=python_track.id,
                status=PythonRepeatEnrollmentStatus.ACTIVE,
                started_at=approved_at,
                terms_snapshot={
                    **application.terms_snapshot,
                    "application_id": str(application.id),
                    "previous_enrollment_id": {
                        "user_id": str(application.student_id),
                        "track_id": str(python_track.id),
                    },
                },
            )
            session.add(enrollment)
            await session.flush()
            await _event(session, "python_repeat_enrollment_created", enrollment.id, None)
        await _transition(session, application, PythonRepeatApplicationStatus.ENROLLED, None)
        await _event(session, "python_repeat_upfront_paid", application.id, None)
        await _notify_student(
            session,
            student_id=application.student_id,
            event_key=f"python-repeat-enrollment-created:{enrollment.id}",
            title="Вступительный платёж получен",
            body="Новое повторное Python-менторство создано и доступно в кабинете.",
            kind=NotificationKind.PAYMENT_DUE,
        )
        attempt.status = PaymentAttemptStatus.APPROVED
        attempt.approved_at = approved_at
        return
    assert attempt.python_repeat_installment_id is not None
    installment = await session.scalar(
        select(PythonRepeatInstallment)
        .where(PythonRepeatInstallment.id == attempt.python_repeat_installment_id)
        .with_for_update()
    )
    if installment is None or installment.status in {
        PythonRepeatInstallmentStatus.PAID,
        PythonRepeatInstallmentStatus.REFUNDED,
        PythonRepeatInstallmentStatus.CANCELLED,
    }:
        if installment is not None and installment.status is PythonRepeatInstallmentStatus.PAID:
            attempt.status = PaymentAttemptStatus.APPROVED
            attempt.approved_at = approved_at
        else:
            attempt.status = PaymentAttemptStatus.MANUAL_REVIEW
        return
    installment.status = PythonRepeatInstallmentStatus.PAID
    installment.paid_at = approved_at
    installment.actual_received_kopecks = installment.amount_kopecks
    attempt.status = PaymentAttemptStatus.APPROVED
    attempt.approved_at = approved_at
    obligation = await session.get(PythonRepeatSuccessFeeObligation, installment.obligation_id)
    if obligation is None:
        attempt.status = PaymentAttemptStatus.MANUAL_REVIEW
        return
    enrollment = await session.get(PythonRepeatEnrollment, obligation.enrollment_id)
    if enrollment is None:
        attempt.status = PaymentAttemptStatus.MANUAL_REVIEW
        return
    if enrollment.mentor_id is not None:
        existing = await session.scalar(
            select(MentorReward.id).where(
                MentorReward.python_repeat_installment_id == installment.id
            )
        )
        if existing is None:
            share = _snapshot_int(enrollment.terms_snapshot, "mentor_success_fee_share_percent")
            session.add(
                MentorReward(
                    python_repeat_installment_id=installment.id,
                    student_id=enrollment.student_id,
                    mentor_id=enrollment.mentor_id,
                    kind=MentorRewardKind.PYTHON_REPEAT_SUCCESS_FEE,
                    reward_percent=Decimal(share),
                    basis_kopecks=installment.amount_kopecks,
                    amount_kopecks=_percent(installment.amount_kopecks, share),
                    paid_kopecks=0,
                )
            )
            await _event(
                session, "python_repeat_mentor_success_fee_accrual_created", installment.id, None
            )
    paid_count = int(
        await session.scalar(
            select(func.count(PythonRepeatInstallment.id)).where(
                PythonRepeatInstallment.obligation_id == obligation.id,
                PythonRepeatInstallment.status == PythonRepeatInstallmentStatus.PAID,
            )
        )
        or 0
    )
    if paid_count == obligation.installments_count:
        obligation.status = PythonRepeatObligationStatus.PAID
        await _event(session, "python_repeat_success_fee_fully_paid", obligation.id, None)
    await _event(session, "python_repeat_installment_paid", installment.id, None)
    await _notify_student(
        session,
        student_id=enrollment.student_id,
        event_key=f"python-repeat-installment-paid:{installment.id}",
        title="Платёж по повторному менторству получен",
        body=f"Платёж №{installment.sequence_number} успешно зафиксирован.",
        kind=NotificationKind.PAYMENT_DUE,
    )


async def assign_mentor(
    session: AsyncSession, admin: User, enrollment_id: UUID, mentor_id: UUID
) -> AdminPythonRepeatDashboard:
    enrollment = await session.scalar(
        select(PythonRepeatEnrollment)
        .where(PythonRepeatEnrollment.id == enrollment_id)
        .with_for_update()
    )
    if enrollment is None:
        api_error(404, "python_repeat_enrollment_not_found", "Enrollment was not found")
    mentor = await session.get(User, mentor_id)
    if mentor is None or mentor.role not in MENTOR_CAPABLE_ROLES or not mentor.is_active:
        api_error(404, "mentor_not_found", "Active mentor was not found")
    enrollment.mentor_id = mentor.id
    enrollment.mentor_assigned_at = _now()
    enrollment.mentor_assigned_by_user_id = admin.id
    existing_relation = await session.scalar(
        select(MentorStudent).where(MentorStudent.student_id == enrollment.student_id)
    )
    if existing_relation is None:
        session.add(
            MentorStudent(
                mentor_id=mentor.id,
                student_id=enrollment.student_id,
                learning_status=StudentLearningStatus.LEARNING,
            )
        )
    elif existing_relation.mentor_id != mentor.id:
        await session.delete(existing_relation)
        await session.flush()
        session.add(
            MentorStudent(
                mentor_id=mentor.id,
                student_id=enrollment.student_id,
                learning_status=StudentLearningStatus.LEARNING,
            )
        )
    existing_reward = await session.scalar(
        select(MentorReward.id).where(MentorReward.python_repeat_enrollment_id == enrollment.id)
    )
    if existing_reward is None:
        amount = _snapshot_int(enrollment.terms_snapshot, "mentor_fixed_accrual_kopecks")
        session.add(
            MentorReward(
                python_repeat_enrollment_id=enrollment.id,
                student_id=enrollment.student_id,
                mentor_id=mentor.id,
                kind=MentorRewardKind.PYTHON_REPEAT_FIXED,
                basis_kopecks=_snapshot_int(enrollment.terms_snapshot, "upfront_price_kopecks"),
                amount_kopecks=amount,
                paid_kopecks=0,
            )
        )
        await _event(session, "python_repeat_fixed_mentor_accrual_created", enrollment.id, admin.id)
    await _event(
        session, "python_repeat_mentor_assigned", enrollment.id, admin.id, suffix=str(mentor.id)
    )
    await _notify_student(
        session,
        student_id=enrollment.student_id,
        event_key=f"python-repeat-mentor-assigned:{enrollment.id}:{mentor.id}",
        title="Назначен ментор повторной программы",
        body=f"Ваш ментор: {mentor.first_name}.",
        actor_id=admin.id,
    )
    await session.commit()
    return await admin_dashboard(session)


async def create_offer(
    session: AsyncSession, student: User, payload: PythonRepeatOfferCreate
) -> PythonRepeatDashboard:
    enrollment = await session.scalar(
        select(PythonRepeatEnrollment).where(
            PythonRepeatEnrollment.student_id == student.id,
            PythonRepeatEnrollment.status == PythonRepeatEnrollmentStatus.ACTIVE,
        )
    )
    if enrollment is None:
        api_error(409, "python_repeat_enrollment_required", "Active enrollment is required")
    item = PythonRepeatEmploymentOffer(
        enrollment_id=enrollment.id,
        student_id=student.id,
        technology_direction="Python Backend",
        currency="RUB",
        status=PythonRepeatOfferStatus.DRAFT,
        **payload.model_dump(),
    )
    session.add(item)
    await session.commit()
    return await dashboard(session, student)


async def submit_offer(
    session: AsyncSession, student: User, offer_id: UUID
) -> PythonRepeatDashboard:
    item = await session.scalar(
        select(PythonRepeatEmploymentOffer)
        .where(
            PythonRepeatEmploymentOffer.id == offer_id,
            PythonRepeatEmploymentOffer.student_id == student.id,
        )
        .with_for_update()
    )
    if item is None:
        api_error(404, "python_repeat_offer_not_found", "Offer was not found")
    if item.status is not PythonRepeatOfferStatus.DRAFT:
        api_error(409, "python_repeat_offer_not_draft", "Only draft offer can be submitted")
    item.status = PythonRepeatOfferStatus.SUBMITTED
    item.submitted_at = _now()
    await _event(session, "python_repeat_offer_submitted", item.id, student.id)
    await _notify_admins(
        session,
        event_key=f"python-repeat-offer-submitted:{item.id}",
        title="Новый оффер на проверку",
        body=f"{student.first_name} отправил оффер по повторному Python-менторству.",
        actor_id=student.id,
    )
    await session.commit()
    return await dashboard(session, student)


async def decide_offer(
    session: AsyncSession,
    admin: User,
    offer_id: UUID,
    payload: AdminPythonRepeatOfferDecision,
) -> AdminPythonRepeatDashboard:
    item = await session.scalar(
        select(PythonRepeatEmploymentOffer)
        .where(PythonRepeatEmploymentOffer.id == offer_id)
        .with_for_update()
    )
    if item is None:
        api_error(404, "python_repeat_offer_not_found", "Offer was not found")
    if item.status not in {PythonRepeatOfferStatus.SUBMITTED, PythonRepeatOfferStatus.UNDER_REVIEW}:
        api_error(409, "python_repeat_offer_not_reviewable", "Offer is not ready for review")
    item.verification_comment = payload.comment
    if not payload.verified:
        item.status = PythonRepeatOfferStatus.REJECTED
        await _notify_student(
            session,
            student_id=item.student_id,
            event_key=f"python-repeat-offer-rejected:{item.id}",
            title="Оффер требует исправления",
            body=payload.comment or "Администратор отклонил оффер. Проверьте комментарий.",
            actor_id=admin.id,
            kind=NotificationKind.OFFER,
        )
        await session.commit()
        return await admin_dashboard(session)
    assert payload.salary_base_kopecks is not None
    item.status = PythonRepeatOfferStatus.VERIFIED
    item.fixed_monthly_salary_kopecks = payload.salary_base_kopecks
    item.verified_at = _now()
    item.verified_by_user_id = admin.id
    enrollment = await session.get(PythonRepeatEnrollment, item.enrollment_id)
    if enrollment is None:
        api_error(409, "python_repeat_enrollment_missing", "Enrollment was not found")
    obligation = await session.scalar(
        select(PythonRepeatSuccessFeeObligation).where(
            PythonRepeatSuccessFeeObligation.verified_offer_id == item.id
        )
    )
    count = _snapshot_int(enrollment.terms_snapshot, "success_fee_installments_count")
    if obligation is None:
        fee_percent = _snapshot_int(enrollment.terms_snapshot, "success_fee_percent")
        total = _percent(payload.salary_base_kopecks, fee_percent)
        obligation = PythonRepeatSuccessFeeObligation(
            enrollment_id=enrollment.id,
            verified_offer_id=item.id,
            salary_base_kopecks=payload.salary_base_kopecks,
            success_fee_percent=fee_percent,
            total_amount_kopecks=total,
            installments_count=count,
            status=PythonRepeatObligationStatus.ACTIVE,
            terms_snapshot=enrollment.terms_snapshot,
        )
        session.add(obligation)
        await session.flush()
        base, remainder = divmod(total, count)
        uses_public_offer_schedule = (
            enrollment.terms_snapshot.get("success_fee_first_due_months_after_employment") == 1
            and enrollment.terms_snapshot.get("success_fee_second_due_months_after_employment") == 2
            and count == 2
        )
        legacy_first_due = max(item.expected_start_date, _now()) + timedelta(days=30)
        for index in range(count):
            due_at = (
                _add_calendar_months(item.expected_start_date, index + 1)
                if uses_public_offer_schedule
                else legacy_first_due + timedelta(days=15 * index)
            )
            session.add(
                PythonRepeatInstallment(
                    obligation_id=obligation.id,
                    sequence_number=index + 1,
                    amount_kopecks=base + (remainder if index == count - 1 else 0),
                    salary_percent=fee_percent // count,
                    due_at=due_at,
                    status=PythonRepeatInstallmentStatus.SCHEDULED,
                )
            )
        await _event(session, "python_repeat_success_fee_created", obligation.id, admin.id)
    await _event(session, "python_repeat_offer_verified", item.id, admin.id)
    await _notify_student(
        session,
        student_id=item.student_id,
        event_key=f"python-repeat-offer-verified:{item.id}",
        title="Оффер подтверждён",
        body=f"Зарплата подтверждена, график из {count} платежей сформирован.",
        actor_id=admin.id,
        kind=NotificationKind.OFFER,
    )
    await session.commit()
    return await admin_dashboard(session)


async def installment_checkout(
    session: AsyncSession, student: User, installment_id: UUID
) -> OpportunityPaymentLinkRead:
    row = (
        await session.execute(
            select(
                PythonRepeatInstallment, PythonRepeatSuccessFeeObligation, PythonRepeatEnrollment
            )
            .join(
                PythonRepeatSuccessFeeObligation,
                PythonRepeatSuccessFeeObligation.id == PythonRepeatInstallment.obligation_id,
            )
            .join(
                PythonRepeatEnrollment,
                PythonRepeatEnrollment.id == PythonRepeatSuccessFeeObligation.enrollment_id,
            )
            .where(
                PythonRepeatInstallment.id == installment_id,
                PythonRepeatEnrollment.student_id == student.id,
            )
            .with_for_update()
        )
    ).one_or_none()
    if row is None:
        api_error(404, "python_repeat_installment_not_found", "Installment was not found")
    installment, _obligation, _enrollment = row
    if installment.status not in {
        PythonRepeatInstallmentStatus.SCHEDULED,
        PythonRepeatInstallmentStatus.PENDING,
    }:
        api_error(409, "python_repeat_installment_not_payable", "Installment cannot be paid")
    installment.status = PythonRepeatInstallmentStatus.PENDING
    result = await _payment_link(
        session,
        student,
        resource_id=installment.id,
        amount=installment.amount_kopecks,
        repeat_installment=installment,
        return_path="/opportunities/alumni/python-repeat",
    )
    await session.commit()
    return result


async def development_complete(
    session: AsyncSession, student: User, payment_link_id: str
) -> PythonRepeatDashboard:
    if get_settings().app_env != "development":
        api_error(404, "not_found", "Resource was not found")
    attempt = await session.scalar(
        select(OpportunityPaymentAttempt)
        .where(OpportunityPaymentAttempt.payment_link_id == payment_link_id)
        .with_for_update()
    )
    if attempt is None:
        api_error(404, "payment_attempt_not_found", "Payment attempt was not found")
    owner_id = await _attempt_owner(session, attempt)
    if owner_id != student.id:
        api_error(404, "payment_attempt_not_found", "Payment attempt was not found")
    if attempt.status is not PaymentAttemptStatus.APPROVED:
        await approve_python_repeat_payment(session, attempt, approved_at=_now())
    await session.commit()
    return await dashboard(session, student)


async def development_fail(
    session: AsyncSession, student: User, payment_link_id: str
) -> PythonRepeatDashboard:
    if get_settings().app_env != "development":
        api_error(404, "not_found", "Resource was not found")
    attempt = await session.scalar(
        select(OpportunityPaymentAttempt)
        .where(OpportunityPaymentAttempt.payment_link_id == payment_link_id)
        .with_for_update()
    )
    if attempt is None or await _attempt_owner(session, attempt) != student.id:
        api_error(404, "payment_attempt_not_found", "Payment attempt was not found")
    if attempt.status is PaymentAttemptStatus.APPROVED:
        api_error(409, "payment_already_approved", "Approved payment cannot be failed")
    attempt.status = PaymentAttemptStatus.FAILED
    attempt.payment_url = None
    if attempt.python_repeat_installment_id is not None:
        installment = await session.get(
            PythonRepeatInstallment, attempt.python_repeat_installment_id
        )
        if installment is not None and installment.status is PythonRepeatInstallmentStatus.PENDING:
            installment.status = PythonRepeatInstallmentStatus.SCHEDULED
    await session.commit()
    return await dashboard(session, student)


async def development_refund(
    session: AsyncSession, student: User, installment_id: UUID
) -> PythonRepeatDashboard:
    if get_settings().app_env != "development":
        api_error(404, "not_found", "Resource was not found")
    row = (
        await session.execute(
            select(
                PythonRepeatInstallment, PythonRepeatSuccessFeeObligation, PythonRepeatEnrollment
            )
            .join(
                PythonRepeatSuccessFeeObligation,
                PythonRepeatSuccessFeeObligation.id == PythonRepeatInstallment.obligation_id,
            )
            .join(
                PythonRepeatEnrollment,
                PythonRepeatEnrollment.id == PythonRepeatSuccessFeeObligation.enrollment_id,
            )
            .where(
                PythonRepeatInstallment.id == installment_id,
                PythonRepeatEnrollment.student_id == student.id,
            )
            .with_for_update()
        )
    ).one_or_none()
    if row is None:
        api_error(404, "python_repeat_installment_not_found", "Installment was not found")
    installment, obligation, _ = row
    if installment.status is not PythonRepeatInstallmentStatus.PAID:
        api_error(
            409, "python_repeat_installment_not_paid", "Only paid installment can be refunded"
        )
    installment.status = PythonRepeatInstallmentStatus.REFUNDED
    installment.refunded_at = _now()
    obligation.status = PythonRepeatObligationStatus.ACTIVE
    reward = await session.scalar(
        select(MentorReward).where(MentorReward.python_repeat_installment_id == installment.id)
    )
    if reward is not None and reward.voided_at is None:
        if reward.paid_kopecks:
            session.add(
                MentorReward(
                    student_id=reward.student_id,
                    mentor_id=reward.mentor_id,
                    kind=MentorRewardKind.PYTHON_REPEAT_SUCCESS_FEE,
                    reward_percent=reward.reward_percent,
                    basis_kopecks=reward.basis_kopecks,
                    amount_kopecks=0,
                    paid_kopecks=0,
                    void_reason=f"Refund reversal for reward {reward.id}",
                )
            )
        reward.voided_at = _now()
        reward.voided_by_user_id = student.id
        reward.void_reason = "Development refund"
    await _event(session, "python_repeat_installment_refunded", installment.id, student.id)
    await session.commit()
    return await dashboard(session, student)


async def admin_transition_application(
    session: AsyncSession,
    admin: User,
    application_id: UUID,
    payload: AdminPythonRepeatTransition,
) -> AdminPythonRepeatDashboard:
    item = await session.scalar(
        select(PythonRepeatApplication)
        .where(PythonRepeatApplication.id == application_id)
        .with_for_update()
    )
    if item is None:
        api_error(404, "python_repeat_application_not_found", "Application was not found")
    if payload.status is PythonRepeatApplicationStatus.APPROVED:
        student = await session.get(User, item.student_id)
        if student is None:
            api_error(404, "student_not_found", "Student was not found")
        eligibility = await python_repeat_eligibility(
            session, student, ignore_application_id=item.id
        )
        if not eligibility.eligible and item.eligibility_override_by_user_id is None:
            api_error(409, eligibility.code.casefold(), eligibility.message)
        product = await _active_product(session)
        item.product_offer_id = product.id
        item.terms_version = product.version
        item.terms_snapshot = _product_snapshot(product)
        item.approved_at = _now()
        item.offer_expires_at = item.approved_at + timedelta(days=product.offer_valid_days)
    item.admin_comment = payload.comment
    item.responsible_user_id = payload.responsible_user_id or item.responsible_user_id or admin.id
    await _transition(session, item, payload.status, admin.id, comment=payload.comment)
    status_titles = {
        PythonRepeatApplicationStatus.UNDER_REVIEW: "Заявка принята в работу",
        PythonRepeatApplicationStatus.NEEDS_DIAGNOSTIC: "Нужна карьерная диагностика",
        PythonRepeatApplicationStatus.NEEDS_CLARIFICATION: "Нужно уточнить заявку",
        PythonRepeatApplicationStatus.APPROVED: "Заявка одобрена",
        PythonRepeatApplicationStatus.REJECTED: "Заявка отклонена",
        PythonRepeatApplicationStatus.CANCELLED: "Заявка отменена",
    }
    if payload.status in status_titles:
        await _notify_student(
            session,
            student_id=item.student_id,
            event_key=f"python-repeat-application-status:{item.id}:{payload.status.value}",
            title=status_titles[payload.status],
            body=payload.comment or "Статус заявки обновлён администратором.",
            actor_id=admin.id,
        )
    await session.commit()
    return await admin_dashboard(session)


async def eligibility_override(
    session: AsyncSession, admin: User, application_id: UUID, reason: str
) -> AdminPythonRepeatDashboard:
    item = await session.scalar(
        select(PythonRepeatApplication)
        .where(PythonRepeatApplication.id == application_id)
        .with_for_update()
    )
    if item is None:
        api_error(404, "python_repeat_application_not_found", "Application was not found")
    student = await session.get(User, item.student_id)
    if student is None:
        api_error(404, "student_not_found", "Student was not found")
    eligibility = await python_repeat_eligibility(session, student, ignore_application_id=item.id)
    if eligibility.code in {
        "ACCOUNT_INACTIVE",
        "ACTIVE_LONG_PROGRAM",
        "ACTIVE_REPEAT_ENROLLMENT",
        "ACTIVE_GO_APPLICATION",
        "OVERDUE_OBLIGATIONS",
        "OVERDUE_REPEAT_OBLIGATIONS",
    }:
        api_error(409, "eligibility_override_forbidden", "Active enrollment cannot be overridden")
    item.eligibility_override_by_user_id = admin.id
    item.eligibility_override_reason = reason
    await _event(session, "python_repeat_eligibility_overridden", item.id, admin.id)
    await session.commit()
    return await admin_dashboard(session)


async def _owned_application(
    session: AsyncSession, student_id: UUID, application_id: UUID, *, lock: bool
) -> PythonRepeatApplication:
    query = select(PythonRepeatApplication).where(
        PythonRepeatApplication.id == application_id,
        PythonRepeatApplication.student_id == student_id,
    )
    if lock:
        query = query.with_for_update()
    item = await session.scalar(query)
    if item is None:
        api_error(404, "python_repeat_application_not_found", "Application was not found")
    return item


async def _attempt_owner(session: AsyncSession, attempt: OpportunityPaymentAttempt) -> UUID | None:
    if attempt.python_repeat_application_id is not None:
        return cast(
            UUID | None,
            await session.scalar(
                select(PythonRepeatApplication.student_id).where(
                    PythonRepeatApplication.id == attempt.python_repeat_application_id
                )
            ),
        )
    if attempt.python_repeat_installment_id is not None:
        return cast(
            UUID | None,
            await session.scalar(
                select(PythonRepeatEnrollment.student_id)
                .join(
                    PythonRepeatSuccessFeeObligation,
                    PythonRepeatSuccessFeeObligation.enrollment_id == PythonRepeatEnrollment.id,
                )
                .join(
                    PythonRepeatInstallment,
                    PythonRepeatInstallment.obligation_id == PythonRepeatSuccessFeeObligation.id,
                )
                .where(PythonRepeatInstallment.id == attempt.python_repeat_installment_id)
            ),
        )
    return None


async def dashboard(session: AsyncSession, student: User) -> PythonRepeatDashboard:
    eligibility = await python_repeat_eligibility(session, student)
    product = await _active_product(session)
    application = await session.scalar(
        select(PythonRepeatApplication)
        .where(PythonRepeatApplication.student_id == student.id)
        .order_by(PythonRepeatApplication.created_at.desc())
        .limit(1)
    )
    enrollment = await session.scalar(
        select(PythonRepeatEnrollment)
        .where(PythonRepeatEnrollment.student_id == student.id)
        .order_by(PythonRepeatEnrollment.created_at.desc())
        .limit(1)
    )
    offers = (
        list(
            await session.scalars(
                select(PythonRepeatEmploymentOffer)
                .where(PythonRepeatEmploymentOffer.student_id == student.id)
                .order_by(PythonRepeatEmploymentOffer.created_at.desc())
            )
        )
        if enrollment is not None
        else []
    )
    obligation = None
    if enrollment is not None:
        obligation = await session.scalar(
            select(PythonRepeatSuccessFeeObligation)
            .where(PythonRepeatSuccessFeeObligation.enrollment_id == enrollment.id)
            .order_by(PythonRepeatSuccessFeeObligation.created_at.desc())
            .limit(1)
        )
    return PythonRepeatDashboard(
        enabled=(
            get_settings().opportunities_enabled and get_settings().python_repeat_mentorship_enabled
        ),
        eligibility=eligibility,
        product=_product_snapshot(product),
        application=await _application_read(session, application) if application else None,
        enrollment=PythonRepeatEnrollmentRead.model_validate(enrollment) if enrollment else None,
        offers=[PythonRepeatOfferRead.model_validate(item) for item in offers],
        obligation=await _obligation_read(session, obligation) if obligation else None,
    )


async def _application_read(
    session: AsyncSession, item: PythonRepeatApplication
) -> PythonRepeatApplicationRead:
    history = list(
        await session.scalars(
            select(PythonRepeatApplicationHistory)
            .where(PythonRepeatApplicationHistory.application_id == item.id)
            .order_by(PythonRepeatApplicationHistory.created_at)
        )
    )
    return PythonRepeatApplicationRead(
        **PythonRepeatApplicationRead.model_validate(item).model_dump(exclude={"history"}),
        history=[PythonRepeatStatusHistoryRead.model_validate(row) for row in history],
    )


async def _obligation_read(
    session: AsyncSession, item: PythonRepeatSuccessFeeObligation
) -> PythonRepeatObligationRead:
    installments = list(
        await session.scalars(
            select(PythonRepeatInstallment)
            .where(PythonRepeatInstallment.obligation_id == item.id)
            .order_by(PythonRepeatInstallment.sequence_number)
        )
    )
    return PythonRepeatObligationRead(
        **PythonRepeatObligationRead.model_validate(item).model_dump(exclude={"installments"}),
        installments=[PythonRepeatInstallmentRead.model_validate(row) for row in installments],
    )


async def admin_dashboard(session: AsyncSession) -> AdminPythonRepeatDashboard:
    applications = list(
        await session.scalars(
            select(PythonRepeatApplication)
            .order_by(PythonRepeatApplication.created_at.desc())
            .limit(200)
        )
    )
    mentors = list(
        await session.scalars(
            select(User)
            .where(User.role.in_(MENTOR_CAPABLE_ROLES), User.is_active.is_(True))
            .order_by(User.first_name, User.last_name)
        )
    )
    reads: list[AdminPythonRepeatApplicationRead] = []
    for item in applications:
        student = await session.get(User, item.student_id)
        if student is None:
            continue
        enrollment = await session.scalar(
            select(PythonRepeatEnrollment).where(PythonRepeatEnrollment.application_id == item.id)
        )
        offers = (
            list(
                await session.scalars(
                    select(PythonRepeatEmploymentOffer).where(
                        PythonRepeatEmploymentOffer.enrollment_id == enrollment.id
                    )
                )
            )
            if enrollment
            else []
        )
        obligation = (
            await session.scalar(
                select(PythonRepeatSuccessFeeObligation).where(
                    PythonRepeatSuccessFeeObligation.enrollment_id == enrollment.id
                )
            )
            if enrollment
            else None
        )
        installment_rows = (
            list(
                await session.scalars(
                    select(PythonRepeatInstallment).where(
                        PythonRepeatInstallment.obligation_id == obligation.id
                    )
                )
            )
            if obligation
            else []
        )
        paid_installments = sum(
            installment.actual_received_kopecks or 0
            for installment in installment_rows
            if installment.status == PythonRepeatInstallmentStatus.PAID
        )
        reward_rows = (
            list(
                await session.scalars(
                    select(MentorReward).where(
                        MentorReward.voided_at.is_(None),
                        or_(
                            MentorReward.python_repeat_enrollment_id == enrollment.id,
                            MentorReward.python_repeat_installment_id.in_(
                                [row.id for row in installment_rows]
                            ),
                        ),
                    )
                )
            )
            if enrollment
            else []
        )
        mentor_accrued = sum(reward.amount_kopecks for reward in reward_rows)
        mentor_paid = sum(reward.paid_kopecks for reward in reward_rows)
        upfront_received = (
            _snapshot_int(item.terms_snapshot, "upfront_price_kopecks")
            if item.paid_at is not None and item.terms_snapshot is not None
            else 0
        )
        revenue_received = upfront_received + paid_installments
        base = await _application_read(session, item)
        reads.append(
            AdminPythonRepeatApplicationRead(
                **base.model_dump(),
                student=_user_read(student),
                eligibility=await python_repeat_eligibility(
                    session, student, ignore_application_id=item.id
                ),
                enrollment=PythonRepeatEnrollmentRead.model_validate(enrollment)
                if enrollment
                else None,
                offers=[PythonRepeatOfferRead.model_validate(row) for row in offers],
                obligation=await _obligation_read(session, obligation) if obligation else None,
                revenue_received_kopecks=revenue_received,
                mentor_accrued_kopecks=mentor_accrued,
                mentor_paid_kopecks=mentor_paid,
                gross_remainder_kopecks=revenue_received - mentor_accrued,
            )
        )
    return AdminPythonRepeatDashboard(
        applications=reads,
        mentors=[_user_read(mentor) for mentor in mentors],
    )


def _user_read(user: User) -> AdminPythonRepeatStudentRead:
    return AdminPythonRepeatStudentRead(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        telegram_username=user.telegram_username,
        email=user.email,
    )
