from __future__ import annotations

import calendar
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.config import get_settings
from app.core.errors import api_error
from app.interviews.companies import get_or_create_company
from app.interviews.models import Company
from app.interviews.uploads import StoredUpload
from app.mentors.models import MentorStudent
from app.mentors.service import assigned_student
from app.notifications.models import NotificationKind
from app.notifications.service import actor_name, notify_student
from app.payments.models import (
    MentorPayout,
    MentorPayoutAllocation,
    MentorPayoutOrigin,
    MentorPayoutRevision,
    MentorPayoutStatus,
    MentorReward,
    MentorRewardKind,
    PaymentAttempt,
    PaymentAttemptStatus,
    PaymentInstallment,
    PaymentInstallmentDueDateRevision,
    PaymentInstallmentStatus,
    StudentEmployment,
    StudentEmploymentSalaryRevision,
    StudentEmploymentStatus,
    TochkaTestPayment,
)
from app.payments.schemas import (
    AdminEmploymentPaymentStatus,
    AdminMentorPayoutBalanceRead,
    AdminMentorPayoutDashboard,
    AdminMentorPayoutDetail,
    AdminPaymentListItem,
    AdminPaymentPage,
    AdminPaymentStudentPage,
    AdminPaymentStudentRead,
    AdminTochkaTestPaymentRead,
    EmploymentMutation,
    EmploymentRead,
    EmploymentTerminationMutation,
    MentorPayoutRead,
    MentorRewardRead,
    MentorRewardSummary,
    PaymentDueDateMutation,
    PaymentInstallmentRead,
    PaymentLinkRead,
    PaymentRevocationMutation,
    PaymentSummaryRead,
    StudentPaymentDashboard,
)
from app.payments.tochka import TochkaError, TochkaPaymentService
from app.users.models import User, UserRole

INSTALLMENT_PERCENT = Decimal("25")
ENTRY_PAYMENT_MENTOR_REWARD_KOPECKS = 1_000_000
PROGRAM_EXCLUSION_MENTOR_REWARD_KOPECKS = 1_000_000
TOCHKA_TEST_PAYMENT_AMOUNT_KOPECKS = 1_000


def calculate_installment_amounts(net_salary_kopecks: int, repayment_percent: Decimal) -> list[int]:
    total = _percent_of(net_salary_kopecks, repayment_percent)
    regular = _percent_of(net_salary_kopecks, INSTALLMENT_PERCENT)
    result: list[int] = []
    remaining = total
    while remaining > 0:
        amount = min(regular, remaining)
        result.append(amount)
        remaining -= amount
    return result


def calculate_installment_percents(repayment_percent: Decimal) -> list[Decimal]:
    result: list[Decimal] = []
    remaining = repayment_percent
    while remaining > 0:
        percent = min(INSTALLMENT_PERCENT, remaining)
        result.append(percent)
        remaining -= percent
    return result


def calculate_due_dates(start_date: date, payment_days: tuple[int, int], count: int) -> list[date]:
    if count <= 0:
        return []
    return _payment_dates_on_or_after(_add_month(start_date), payment_days, count)


def _payment_dates_on_or_after(
    eligible: date, payment_days: tuple[int, int], count: int
) -> list[date]:
    year, month = eligible.year, eligible.month
    result: list[date] = []
    while len(result) < count:
        for day in payment_days:
            candidate = date(year, month, day)
            if candidate >= eligible:
                result.append(candidate)
                if len(result) == count:
                    break
        month += 1
        if month == 13:
            year += 1
            month = 1
    return result


async def change_student_repayment_percent(
    session: AsyncSession, student_id: UUID, repayment_percent: Decimal
) -> None:
    employment = await session.scalar(
        select(StudentEmployment)
        .where(
            StudentEmployment.student_id == student_id,
            StudentEmployment.status == StudentEmploymentStatus.ACTIVE,
        )
        .with_for_update()
    )
    paid_exists = await session.scalar(
        select(PaymentInstallment.id)
        .join(StudentEmployment, StudentEmployment.id == PaymentInstallment.employment_id)
        .where(
            StudentEmployment.student_id == student_id,
            PaymentInstallment.status == PaymentInstallmentStatus.PAID,
        )
    )
    if paid_exists is not None:
        api_error(
            409,
            "repayment_percent_locked",
            "Repayment percentage cannot be changed after the first payment",
        )
    if employment is None or employment.repayment_percent == repayment_percent:
        return
    employment.repayment_percent = repayment_percent
    await _regenerate_unpaid_installments(session, employment)


async def set_employment(
    session: AsyncSession,
    actor: User,
    student_id: UUID,
    payload: EmploymentMutation,
) -> StudentPaymentDashboard:
    student, _relation = await assigned_student(session, actor, student_id, lock=True)
    employment = await session.scalar(
        select(StudentEmployment)
        .where(
            StudentEmployment.student_id == student.id,
            StudentEmployment.status == StudentEmploymentStatus.ACTIVE,
        )
        .with_for_update()
    )
    salary_kopecks = _rubles_to_kopecks(payload.net_salary_rubles)
    company = await _resolve_company(session, payload.company_id, payload.company_name)
    created_employment = employment is None
    if employment is None:
        remaining_percent = await remaining_repayment_percent(session, student)
        if remaining_percent <= 0:
            api_error(
                409,
                "repayment_obligation_fulfilled",
                "The student's repayment obligation has already been fulfilled",
            )
        employment = StudentEmployment(
            student_id=student.id,
            company_id=company.id,
            company_name=company.name,
            start_date=payload.start_date,
            billing_started_at=payload.start_date,
            net_salary_kopecks=salary_kopecks,
            repayment_percent=remaining_percent,
            status=StudentEmploymentStatus.ACTIVE,
            payment_day_first=10,
            payment_day_second=25,
            recorded_by_user_id=actor.id,
        )
        session.add(employment)
        await session.flush()
        await _regenerate_unpaid_installments(session, employment)
    else:
        paid_count = int(
            await session.scalar(
                select(func.count(PaymentInstallment.id)).where(
                    PaymentInstallment.employment_id == employment.id,
                    PaymentInstallment.status == PaymentInstallmentStatus.PAID,
                )
            )
            or 0
        )
        company_changed = (
            employment.company_id != company.id
            or employment.company_name.casefold() != company.name.casefold()
        )
        if paid_count and (company_changed or employment.start_date != payload.start_date):
            api_error(
                409,
                "employment_identity_locked",
                "Company and start date cannot be changed after a payment",
            )
        previous_salary_kopecks = employment.net_salary_kopecks
        employment.company_id = company.id
        employment.company_name = company.name
        employment.start_date = payload.start_date
        employment.billing_started_at = employment.billing_started_at or payload.start_date
        employment.net_salary_kopecks = salary_kopecks
        employment.recorded_by_user_id = actor.id
        if paid_count and previous_salary_kopecks != salary_kopecks:
            session.add(
                StudentEmploymentSalaryRevision(
                    employment_id=employment.id,
                    edited_by_user_id=actor.id,
                    previous_net_salary_kopecks=previous_salary_kopecks,
                    new_net_salary_kopecks=salary_kopecks,
                )
            )
            await _recalculate_installments_after_salary_correction(session, employment)
        elif not paid_count:
            await _regenerate_unpaid_installments(session, employment)
    if created_employment:
        salary_rubles = f"{salary_kopecks / 100:,.0f}".replace(",", " ")
        await notify_student(
            session,
            student_id=student.id,
            actor=actor,
            event_key=f"student-employment:{employment.id}",
            kind=NotificationKind.OFFER,
            title="Зафиксирован выход на работу",
            body=(
                f"{actor_name(actor)} добавил оффер: {company.name}, "
                f"выход {payload.start_date:%d.%m.%Y}, {salary_rubles} ₽ на руки."
            ),
            action_url="/payments",
        )
    await session.commit()
    return await payment_dashboard(session, actor, student.id)


async def terminate_employment(
    session: AsyncSession,
    actor: User,
    student_id: UUID,
    payload: EmploymentTerminationMutation,
) -> StudentPaymentDashboard:
    student, _relation = await assigned_student(session, actor, student_id, lock=True)
    employment = await _active_employment_for_update(session, student.id)
    if employment is None:
        api_error(409, "active_employment_not_found", "The student has no active employment")
    if employment.start_date is None:
        api_error(409, "employment_not_started", "Employment has not started yet")
    if payload.ended_at < employment.start_date:
        api_error(422, "invalid_employment_end_date", "End date cannot precede start date")

    await _terminate_employment_model(session, employment, payload.ended_at, payload.reason)
    await session.commit()
    return await payment_dashboard(session, actor, student.id)


async def terminate_active_employment_for_student(
    session: AsyncSession,
    student_id: UUID,
    *,
    ended_at: date,
    reason: str,
) -> bool:
    """Stop an active job and cancel its unpaid schedule without committing the transaction."""
    employment = await _active_employment_for_update(session, student_id)
    if employment is None:
        return False
    effective_end_date = max(ended_at, employment.start_date or ended_at)
    await _terminate_employment_model(session, employment, effective_end_date, reason)
    return True


async def _active_employment_for_update(
    session: AsyncSession, student_id: UUID
) -> StudentEmployment | None:
    employment: StudentEmployment | None = await session.scalar(
        select(StudentEmployment)
        .where(
            StudentEmployment.student_id == student_id,
            StudentEmployment.status == StudentEmploymentStatus.ACTIVE,
        )
        .with_for_update()
    )
    return employment


async def _terminate_employment_model(
    session: AsyncSession,
    employment: StudentEmployment,
    ended_at: date,
    reason: str | None,
) -> None:
    employment.status = StudentEmploymentStatus.TERMINATED
    employment.ended_at = ended_at
    employment.end_reason = reason or None
    installments = await _installments(session, employment.id)
    for installment in installments:
        if installment.status is PaymentInstallmentStatus.PAID:
            continue
        installment.status = PaymentInstallmentStatus.CANCELLED
        attempts = list(
            await session.scalars(
                select(PaymentAttempt).where(
                    PaymentAttempt.installment_id == installment.id,
                    PaymentAttempt.status.in_(
                        [PaymentAttemptStatus.PENDING, PaymentAttemptStatus.MANUAL_REVIEW]
                    ),
                )
            )
        )
        for attempt in attempts:
            attempt.status = PaymentAttemptStatus.CANCELLED
            attempt.payment_url = None


async def set_payment_days(
    session: AsyncSession,
    actor: User,
    student_id: UUID,
    payment_days: list[int],
) -> StudentPaymentDashboard:
    if actor.role is not UserRole.ADMIN and actor.id != student_id:
        api_error(
            403,
            "payment_schedule_forbidden",
            "Only the student or an admin can change dates",
        )
    student = await session.get(User, student_id)
    if student is None or student.role is not UserRole.STUDENT:
        api_error(404, "student_not_found", "Student was not found")
    employment = await session.scalar(
        select(StudentEmployment)
        .where(
            StudentEmployment.student_id == student_id,
            StudentEmployment.status == StudentEmploymentStatus.ACTIVE,
        )
        .with_for_update()
    )
    if employment is None:
        api_error(409, "employment_not_recorded", "Employment must be recorded first")
    first, second = sorted(payment_days)
    employment.payment_day_first = first
    employment.payment_day_second = second
    await _reschedule_unpaid_installments(session, employment)
    await session.commit()
    return await payment_dashboard(session, actor, student_id)


async def reschedule_installment_due_date(
    session: AsyncSession,
    admin: User,
    installment_id: UUID,
    payload: PaymentDueDateMutation,
) -> StudentPaymentDashboard:
    row = (
        await session.execute(
            select(PaymentInstallment, StudentEmployment)
            .join(StudentEmployment)
            .where(PaymentInstallment.id == installment_id)
            .with_for_update()
        )
    ).one_or_none()
    if row is None:
        api_error(404, "payment_installment_not_found", "Payment was not found")
    installment, employment = row
    if installment.status not in {
        PaymentInstallmentStatus.SCHEDULED,
        PaymentInstallmentStatus.PENDING,
    }:
        api_error(
            409,
            "payment_due_date_locked",
            "Only an unpaid active payment can be rescheduled",
        )
    if payload.due_date <= installment.due_date:
        api_error(
            422,
            "payment_due_date_not_later",
            "The new payment date must be later than the current date",
        )
    if payload.due_date < date.today():
        api_error(
            422,
            "payment_due_date_in_past",
            "The new payment date cannot be in the past",
        )
    conflicting_installment = await session.scalar(
        select(PaymentInstallment.id).where(
            PaymentInstallment.employment_id == employment.id,
            PaymentInstallment.id != installment.id,
            PaymentInstallment.due_date == payload.due_date,
            PaymentInstallment.status != PaymentInstallmentStatus.CANCELLED,
        )
    )
    if conflicting_installment is not None:
        api_error(
            409,
            "payment_due_date_conflict",
            "Another payment is already scheduled for this date",
        )
    previous_due_date = installment.due_date
    installment.due_date = payload.due_date
    session.add(
        PaymentInstallmentDueDateRevision(
            installment_id=installment.id,
            changed_by_user_id=admin.id,
            previous_due_date=previous_due_date,
            new_due_date=payload.due_date,
            reason=payload.reason,
        )
    )
    await session.commit()
    return await payment_dashboard(session, admin, employment.student_id)


async def payment_dashboard(
    session: AsyncSession, actor: User, student_id: UUID
) -> StudentPaymentDashboard:
    if actor.role is UserRole.STUDENT:
        if actor.id != student_id:
            api_error(403, "student_payments_forbidden", "Students can only view their payments")
        relation = await session.scalar(
            select(MentorStudent).where(MentorStudent.student_id == student_id)
        )
        student = actor
    else:
        student, relation = await assigned_student(session, actor, student_id)
    employments = list(
        await session.scalars(
            select(StudentEmployment)
            .where(StudentEmployment.student_id == student_id)
            .order_by(StudentEmployment.start_date, StudentEmployment.created_at)
        )
    )
    employment_by_id = {item.id: item for item in employments}
    active_employment = next(
        (item for item in reversed(employments) if item.status is StudentEmploymentStatus.ACTIVE),
        None,
    )
    installments = (
        []
        if not employments
        else list(
            await session.scalars(
                select(PaymentInstallment)
                .where(PaymentInstallment.employment_id.in_(employment_by_id))
                .order_by(PaymentInstallment.due_date, PaymentInstallment.sequence_number)
            )
        )
    )
    latest_attempts = await _latest_attempts(session, [item.id for item in installments])
    latest_due_date_revisions = await _latest_due_date_revisions(
        session, [item.id for item in installments]
    )
    today = date.today()
    reads = [
        PaymentInstallmentRead(
            id=item.id,
            sequence_number=item.sequence_number,
            due_date=item.due_date,
            amount_kopecks=item.amount_kopecks,
            salary_percent=item.salary_percent,
            employment_id=item.employment_id,
            company_name=employment_by_id[item.employment_id].company_name,
            status=item.status,
            paid_at=item.paid_at,
            revoked_at=item.revoked_at,
            revocation_reason=item.revocation_reason,
            due_date_changed_at=(
                latest_due_date_revisions[item.id].created_at
                if item.id in latest_due_date_revisions
                else None
            ),
            previous_due_date=(
                latest_due_date_revisions[item.id].previous_due_date
                if item.id in latest_due_date_revisions
                else None
            ),
            due_date_change_reason=(
                latest_due_date_revisions[item.id].reason
                if item.id in latest_due_date_revisions
                else None
            ),
            payment_url=(
                latest_attempts[item.id].payment_url
                if item.id in latest_attempts
                and latest_attempts[item.id].status
                in {PaymentAttemptStatus.PENDING, PaymentAttemptStatus.MANUAL_REVIEW}
                else None
            ),
            can_pay=(
                actor.id == student_id
                and not employment_by_id[item.employment_id].billing_on_hold
                and item.status
                in {
                    PaymentInstallmentStatus.SCHEDULED,
                    PaymentInstallmentStatus.PENDING,
                }
                and employment_by_id[item.employment_id].status is StudentEmploymentStatus.ACTIVE
            ),
        )
        for item in installments
    ]
    paid = sum(
        item.amount_kopecks for item in installments if item.status is PaymentInstallmentStatus.PAID
    )
    remaining = sum(
        item.amount_kopecks
        for item in installments
        if item.status
        in {
            PaymentInstallmentStatus.SCHEDULED,
            PaymentInstallmentStatus.PENDING,
        }
    )
    overdue = sum(
        item.amount_kopecks
        for item in installments
        if item.status
        in {
            PaymentInstallmentStatus.SCHEDULED,
            PaymentInstallmentStatus.PENDING,
        }
        and item.due_date < today
    )
    paid_percent = sum(
        (
            item.salary_percent
            for item in installments
            if item.status is PaymentInstallmentStatus.PAID
        ),
        Decimal("0"),
    )
    active_installments = [
        item for item in installments if item.status is not PaymentInstallmentStatus.CANCELLED
    ]
    name = " ".join(filter(None, (student.first_name, student.last_name)))
    return StudentPaymentDashboard(
        student_id=student.id,
        student_name=name,
        repayment_percent=student.repayment_percent,
        mentor_reward_percent=relation.reward_percent if relation else None,
        employment=_employment_read(active_employment) if active_employment else None,
        employment_history=[_employment_read(item) for item in reversed(employments)],
        installments=reads,
        summary=PaymentSummaryRead(
            total_owed_kopecks=paid + remaining,
            paid_kopecks=paid,
            remaining_kopecks=remaining,
            overdue_kopecks=overdue,
            paid_installments=sum(
                item.status is PaymentInstallmentStatus.PAID for item in active_installments
            ),
            total_installments=len(active_installments),
            paid_salary_percent=paid_percent,
            remaining_salary_percent=max(student.repayment_percent - paid_percent, Decimal("0")),
        ),
        can_manage_employment=actor.role in {UserRole.MENTOR, UserRole.ADMIN},
        can_manage_payment_days=actor.role is UserRole.ADMIN or actor.id == student.id,
    )


async def create_payment_link(
    session: AsyncSession, student: User, installment_id: UUID
) -> PaymentLinkRead:
    settings = get_settings()
    row = (
        await session.execute(
            select(PaymentInstallment, StudentEmployment)
            .join(StudentEmployment, StudentEmployment.id == PaymentInstallment.employment_id)
            .where(
                PaymentInstallment.id == installment_id,
                StudentEmployment.student_id == student.id,
            )
            .with_for_update()
        )
    ).one_or_none()
    if row is None:
        api_error(404, "payment_installment_not_found", "Payment was not found")
    installment, employment = row
    if installment.status is PaymentInstallmentStatus.PAID:
        api_error(409, "payment_already_paid", "This payment has already been confirmed")
    if (
        employment.status is not StudentEmploymentStatus.ACTIVE
        or installment.status is PaymentInstallmentStatus.CANCELLED
    ):
        api_error(409, "payment_cancelled", "This payment was cancelled after employment ended")
    manual_review_exists = await session.scalar(
        select(PaymentAttempt.id).where(
            PaymentAttempt.installment_id == installment.id,
            PaymentAttempt.status == PaymentAttemptStatus.MANUAL_REVIEW,
        )
    )
    if manual_review_exists is not None:
        api_error(
            409,
            "payment_requires_manual_review",
            "The bank payment is awaiting administrator review",
        )
    existing = await session.scalar(
        select(PaymentAttempt)
        .where(
            PaymentAttempt.installment_id == installment.id,
            PaymentAttempt.status == PaymentAttemptStatus.PENDING,
            PaymentAttempt.payment_url.is_not(None),
        )
        .order_by(PaymentAttempt.created_at.desc())
    )
    if existing is not None and existing.payment_url is not None:
        # A click on "Pay" always starts a new bank attempt. A link may have
        # expired after the student opened it without completing the payment.
        existing.status = PaymentAttemptStatus.REVOKED
        existing.payment_url = None

    attempt_count = int(
        await session.scalar(
            select(func.count(PaymentAttempt.id)).where(
                PaymentAttempt.installment_id == installment.id
            )
        )
        or 0
    )
    payment_link_id = f"mp_{installment.id.hex}_r{attempt_count + 1}"
    try:
        result = await TochkaPaymentService(settings).create_payment_link(
            installment_id=installment.id,
            payment_link_id=payment_link_id,
            amount_kopecks=installment.amount_kopecks,
            client_name=" ".join(filter(None, (student.first_name, student.last_name))),
            client_email=student.email or "",
        )
    except TochkaError as error:
        api_error(502, "tochka_payment_link_failed", str(error))
    attempt = PaymentAttempt(
        installment_id=installment.id,
        provider="tochka",
        payment_link_id=result.payment_link_id,
        provider_operation_id=result.provider_operation_id,
        status=PaymentAttemptStatus.PENDING,
        payment_url=result.payment_url,
        raw_create_response=result.raw_response,
    )
    session.add(attempt)
    installment.status = PaymentInstallmentStatus.PENDING
    await session.commit()
    return PaymentLinkRead(installment_id=installment.id, payment_url=result.payment_url)


async def mark_payment_attempt_failed(
    session: AsyncSession,
    student: User,
    installment_id: UUID,
    payment_link_id: str,
) -> None:
    row = (
        await session.execute(
            select(PaymentAttempt, PaymentInstallment)
            .join(PaymentInstallment, PaymentInstallment.id == PaymentAttempt.installment_id)
            .join(StudentEmployment, StudentEmployment.id == PaymentInstallment.employment_id)
            .where(
                PaymentInstallment.id == installment_id,
                StudentEmployment.student_id == student.id,
                PaymentAttempt.payment_link_id == payment_link_id,
            )
            .with_for_update()
        )
    ).one_or_none()
    if row is None:
        api_error(404, "payment_attempt_not_found", "Payment attempt was not found")

    attempt, installment = row
    if attempt.status is not PaymentAttemptStatus.PENDING:
        return

    attempt.status = PaymentAttemptStatus.FAILED
    attempt.payment_url = None
    if installment.status is PaymentInstallmentStatus.PENDING:
        installment.status = PaymentInstallmentStatus.SCHEDULED
    await session.commit()


async def create_admin_tochka_test_payment(
    session: AsyncSession,
    admin: User,
    *,
    email: str,
) -> AdminTochkaTestPaymentRead:
    test_payment_id = uuid4()
    payment_link_id = f"mpt_{test_payment_id.hex}"
    try:
        result = await TochkaPaymentService(get_settings()).create_payment_link(
            installment_id=test_payment_id,
            payment_link_id=payment_link_id,
            amount_kopecks=TOCHKA_TEST_PAYMENT_AMOUNT_KOPECKS,
            client_name=" ".join(filter(None, (admin.first_name, admin.last_name))),
            client_email=email,
            return_path="/admin/payments",
        )
    except TochkaError as error:
        api_error(502, "tochka_test_payment_link_failed", str(error))
    test_payment = TochkaTestPayment(
        id=test_payment_id,
        requested_by_user_id=admin.id,
        amount_kopecks=TOCHKA_TEST_PAYMENT_AMOUNT_KOPECKS,
        payment_link_id=result.payment_link_id,
        provider_operation_id=result.provider_operation_id,
        status=PaymentAttemptStatus.PENDING,
        payment_url=result.payment_url,
        raw_create_response=result.raw_response,
    )
    session.add(test_payment)
    await session.commit()
    await session.refresh(test_payment)
    return _tochka_test_payment_read(test_payment)


async def latest_admin_tochka_test_payment(
    session: AsyncSession,
    admin: User,
) -> AdminTochkaTestPaymentRead | None:
    payment = await session.scalar(
        select(TochkaTestPayment)
        .where(TochkaTestPayment.requested_by_user_id == admin.id)
        .order_by(TochkaTestPayment.created_at.desc())
        .limit(1)
    )
    return _tochka_test_payment_read(payment) if payment is not None else None


async def confirm_installment(
    session: AsyncSession, installment_id: UUID, admin: User
) -> StudentPaymentDashboard:
    installment = await session.scalar(
        select(PaymentInstallment).where(PaymentInstallment.id == installment_id).with_for_update()
    )
    if installment is None:
        api_error(404, "payment_installment_not_found", "Payment was not found")
    if installment.status is PaymentInstallmentStatus.CANCELLED:
        api_error(409, "payment_cancelled", "Cancelled payments cannot be confirmed")
    await mark_installment_paid(session, installment, confirmed_by=admin.id)
    employment = await session.get(StudentEmployment, installment.employment_id)
    if employment is None:
        api_error(404, "employment_not_found", "Employment was not found")
    await session.commit()
    return await payment_dashboard(session, admin, employment.student_id)


async def revoke_installment_payment(
    session: AsyncSession,
    installment_id: UUID,
    admin: User,
    payload: PaymentRevocationMutation,
) -> StudentPaymentDashboard:
    row = (
        await session.execute(
            select(PaymentInstallment, StudentEmployment)
            .join(StudentEmployment)
            .where(PaymentInstallment.id == installment_id)
            .with_for_update()
        )
    ).one_or_none()
    if row is None:
        api_error(404, "payment_installment_not_found", "Payment was not found")
    installment, employment = row
    if installment.status is not PaymentInstallmentStatus.PAID:
        api_error(409, "payment_not_paid", "Only a confirmed payment can be revoked")

    reward = await session.scalar(
        select(MentorReward).where(MentorReward.installment_id == installment.id).with_for_update()
    )
    if reward is not None and reward.voided_at is not None:
        reward = None
    if reward is not None:
        reserved = await _reserved_amounts_by_reward(session, [reward.id])
        if reward.paid_kopecks > 0 or reserved.get(reward.id, 0) > 0:
            api_error(
                409,
                "mentor_reward_already_distributed",
                "The payment cannot be revoked while the related mentor reward "
                "is reserved or already paid",
            )
        cancelled_allocations = list(
            await session.scalars(
                select(MentorPayoutAllocation)
                .join(MentorPayout)
                .where(
                    MentorPayoutAllocation.reward_id == reward.id,
                    MentorPayout.status == MentorPayoutStatus.CANCELLED,
                )
            )
        )
        for allocation in cancelled_allocations:
            await session.delete(allocation)
        await session.delete(reward)

    approved_attempts = list(
        await session.scalars(
            select(PaymentAttempt).where(
                PaymentAttempt.installment_id == installment.id,
                PaymentAttempt.status == PaymentAttemptStatus.APPROVED,
            )
        )
    )
    for attempt in approved_attempts:
        attempt.status = PaymentAttemptStatus.REVOKED

    installment.status = PaymentInstallmentStatus.SCHEDULED
    installment.paid_at = None
    installment.confirmed_by_user_id = None
    installment.revoked_at = datetime.now(UTC)
    installment.revoked_by_user_id = admin.id
    installment.revocation_reason = payload.reason
    await session.commit()
    return await payment_dashboard(session, admin, employment.student_id)


async def mark_installment_paid(
    session: AsyncSession,
    installment: PaymentInstallment,
    *,
    confirmed_by: UUID | None,
    approved_at: datetime | None = None,
) -> None:
    paid_at = approved_at or datetime.now(UTC)
    if installment.status is not PaymentInstallmentStatus.PAID:
        installment.status = PaymentInstallmentStatus.PAID
        installment.paid_at = paid_at
        installment.confirmed_by_user_id = confirmed_by
    employment = await session.get(StudentEmployment, installment.employment_id)
    if employment is None:
        return
    relation = await session.scalar(
        select(MentorStudent).where(MentorStudent.student_id == employment.student_id)
    )
    if relation is None or relation.reward_percent is None:
        return
    student = await session.get(User, employment.student_id)
    if student is None:
        return
    existing = await session.scalar(
        select(MentorReward).where(MentorReward.installment_id == installment.id)
    )
    if existing is None:
        session.add(
            MentorReward(
                installment_id=installment.id,
                student_id=employment.student_id,
                mentor_id=relation.mentor_id,
                kind=MentorRewardKind.EMPLOYMENT_PAYMENT,
                reward_percent=relation.reward_percent,
                basis_kopecks=installment.amount_kopecks,
                amount_kopecks=_proportional_mentor_reward(
                    installment.amount_kopecks,
                    relation.reward_percent,
                    student.repayment_percent,
                ),
            )
        )


async def remaining_repayment_percent(session: AsyncSession, student: User) -> Decimal:
    paid_percent = await session.scalar(
        select(func.coalesce(func.sum(PaymentInstallment.salary_percent), 0))
        .join(StudentEmployment, StudentEmployment.id == PaymentInstallment.employment_id)
        .where(
            StudentEmployment.student_id == student.id,
            PaymentInstallment.status == PaymentInstallmentStatus.PAID,
        )
    )
    return max(student.repayment_percent - Decimal(paid_percent or 0), Decimal("0"))


async def sync_one_time_mentor_rewards(session: AsyncSession, student_id: UUID) -> None:
    student = await session.get(User, student_id)
    relation = await session.scalar(
        select(MentorStudent).where(MentorStudent.student_id == student_id)
    )
    if student is None or relation is None:
        return
    if student.entry_payment_paid_at is not None:
        await _ensure_one_time_reward(
            session,
            student,
            relation,
            MentorRewardKind.ENTRY_PAYMENT,
            ENTRY_PAYMENT_MENTOR_REWARD_KOPECKS,
            basis_kopecks=student.entry_payment_kopecks,
        )
    else:
        await _remove_unpaid_one_time_reward(session, student.id, MentorRewardKind.ENTRY_PAYMENT)
    if student.program_excluded_at is not None:
        await _ensure_one_time_reward(
            session,
            student,
            relation,
            MentorRewardKind.PROGRAM_EXCLUSION,
            PROGRAM_EXCLUSION_MENTOR_REWARD_KOPECKS,
            basis_kopecks=None,
        )
    else:
        await _remove_unpaid_one_time_reward(
            session, student.id, MentorRewardKind.PROGRAM_EXCLUSION
        )


async def _ensure_one_time_reward(
    session: AsyncSession,
    student: User,
    relation: MentorStudent,
    kind: MentorRewardKind,
    amount_kopecks: int,
    *,
    basis_kopecks: int | None,
) -> None:
    existing = await session.scalar(
        select(MentorReward).where(
            MentorReward.student_id == student.id,
            MentorReward.kind == kind,
        )
    )
    if existing is None:
        session.add(
            MentorReward(
                installment_id=None,
                student_id=student.id,
                mentor_id=relation.mentor_id,
                kind=kind,
                reward_percent=None,
                basis_kopecks=basis_kopecks,
                amount_kopecks=amount_kopecks,
            )
        )
    elif existing.paid_at is None:
        existing.basis_kopecks = basis_kopecks
        existing.amount_kopecks = amount_kopecks


async def _remove_unpaid_one_time_reward(
    session: AsyncSession, student_id: UUID, kind: MentorRewardKind
) -> None:
    reward = await session.scalar(
        select(MentorReward).where(
            MentorReward.student_id == student_id,
            MentorReward.kind == kind,
        )
    )
    if reward is None:
        return
    if reward.voided_at is not None:
        return
    reserved = await _reserved_amounts_by_reward(session, [reward.id])
    if reward.paid_kopecks > 0 or reserved.get(reward.id, 0) > 0:
        api_error(
            409,
            "mentor_reward_already_paid",
            "The event cannot be cancelled after the reward was paid or requested",
        )
    await session.delete(reward)


async def admin_payment_page(
    session: AsyncSession,
    *,
    status: PaymentInstallmentStatus | None,
    limit: int,
    offset: int,
    overdue_only: bool = False,
) -> AdminPaymentPage:
    conditions = [] if status is None else [PaymentInstallment.status == status]
    if overdue_only:
        conditions.extend(
            [
                PaymentInstallment.status.in_(
                    [
                        PaymentInstallmentStatus.SCHEDULED,
                        PaymentInstallmentStatus.PENDING,
                    ]
                ),
                PaymentInstallment.due_date < date.today(),
            ]
        )
    total = int(
        await session.scalar(select(func.count(PaymentInstallment.id)).where(*conditions)) or 0
    )
    requires_manual_review = (
        select(PaymentAttempt.id)
        .where(
            PaymentAttempt.installment_id == PaymentInstallment.id,
            PaymentAttempt.status == PaymentAttemptStatus.MANUAL_REVIEW,
        )
        .exists()
    )
    rows = (
        await session.execute(
            select(
                PaymentInstallment,
                StudentEmployment,
                User,
                MentorStudent,
                MentorReward,
                requires_manual_review.label("requires_manual_review"),
            )
            .join(StudentEmployment, StudentEmployment.id == PaymentInstallment.employment_id)
            .join(User, User.id == StudentEmployment.student_id)
            .outerjoin(MentorStudent, MentorStudent.student_id == User.id)
            .outerjoin(
                MentorReward,
                (MentorReward.installment_id == PaymentInstallment.id)
                & MentorReward.voided_at.is_(None),
            )
            .where(*conditions)
            .order_by(PaymentInstallment.due_date, PaymentInstallment.sequence_number)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    mentor_ids = {
        reward.mentor_id if reward is not None else relation.mentor_id
        for _, _, _, relation, reward, _ in rows
        if reward is not None or relation is not None
    }
    mentors = (
        {
            user.id: user
            for user in await session.scalars(select(User).where(User.id.in_(mentor_ids)))
        }
        if mentor_ids
        else {}
    )
    items = [
        _admin_item(
            installment,
            employment,
            student,
            relation,
            reward,
            mentors,
            requires_review,
        )
        for installment, employment, student, relation, reward, requires_review in rows
    ]
    all_rows = (
        await session.execute(
            select(
                PaymentInstallment.status,
                PaymentInstallment.due_date,
                PaymentInstallment.amount_kopecks,
            )
        )
    ).all()
    rewards = list(
        await session.scalars(select(MentorReward).where(MentorReward.voided_at.is_(None)))
    )
    today = date.today()
    return AdminPaymentPage(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        scheduled_kopecks=sum(
            amount
            for item_status, _, amount in all_rows
            if item_status in {PaymentInstallmentStatus.SCHEDULED, PaymentInstallmentStatus.PENDING}
        ),
        paid_kopecks=sum(
            amount
            for item_status, _, amount in all_rows
            if item_status is PaymentInstallmentStatus.PAID
        ),
        overdue_kopecks=sum(
            amount
            for item_status, due, amount in all_rows
            if item_status in {PaymentInstallmentStatus.SCHEDULED, PaymentInstallmentStatus.PENDING}
            and due < today
        ),
        mentor_rewards_accrued_kopecks=sum(reward.amount_kopecks for reward in rewards),
        mentor_rewards_paid_kopecks=sum(reward.paid_kopecks for reward in rewards),
        mentor_rewards=await _mentor_reward_reads(session),
    )


async def admin_payment_student_page(
    session: AsyncSession,
    *,
    status: AdminEmploymentPaymentStatus,
    limit: int,
    offset: int,
) -> AdminPaymentStudentPage:
    unpaid_statuses = [
        PaymentInstallmentStatus.SCHEDULED,
        PaymentInstallmentStatus.PENDING,
    ]
    remaining = (
        select(func.coalesce(func.sum(PaymentInstallment.amount_kopecks), 0))
        .where(
            PaymentInstallment.employment_id == StudentEmployment.id,
            PaymentInstallment.status.in_(unpaid_statuses),
        )
        .correlate(StudentEmployment)
        .scalar_subquery()
    )
    paid = (
        select(func.coalesce(func.sum(PaymentInstallment.amount_kopecks), 0))
        .where(
            PaymentInstallment.employment_id == StudentEmployment.id,
            PaymentInstallment.status == PaymentInstallmentStatus.PAID,
        )
        .correlate(StudentEmployment)
        .scalar_subquery()
    )
    overdue = (
        select(func.coalesce(func.sum(PaymentInstallment.amount_kopecks), 0))
        .where(
            PaymentInstallment.employment_id == StudentEmployment.id,
            PaymentInstallment.status.in_(unpaid_statuses),
            PaymentInstallment.due_date < date.today(),
        )
        .correlate(StudentEmployment)
        .scalar_subquery()
    )
    overdue_count = (
        select(func.count(PaymentInstallment.id))
        .where(
            PaymentInstallment.employment_id == StudentEmployment.id,
            PaymentInstallment.status.in_(unpaid_statuses),
            PaymentInstallment.due_date < date.today(),
        )
        .correlate(StudentEmployment)
        .scalar_subquery()
    )
    next_payment = (
        select(func.min(PaymentInstallment.due_date))
        .where(
            PaymentInstallment.employment_id == StudentEmployment.id,
            PaymentInstallment.status.in_(unpaid_statuses),
        )
        .correlate(StudentEmployment)
        .scalar_subquery()
    )
    paid_count = (
        select(func.count(PaymentInstallment.id))
        .where(
            PaymentInstallment.employment_id == StudentEmployment.id,
            PaymentInstallment.status == PaymentInstallmentStatus.PAID,
        )
        .correlate(StudentEmployment)
        .scalar_subquery()
    )
    paid_salary_percent = (
        select(func.coalesce(func.sum(PaymentInstallment.salary_percent), 0))
        .where(
            PaymentInstallment.employment_id == StudentEmployment.id,
            PaymentInstallment.status == PaymentInstallmentStatus.PAID,
        )
        .correlate(StudentEmployment)
        .scalar_subquery()
    )
    installment_count = (
        select(func.count(PaymentInstallment.id))
        .where(
            PaymentInstallment.employment_id == StudentEmployment.id,
            PaymentInstallment.status != PaymentInstallmentStatus.CANCELLED,
        )
        .correlate(StudentEmployment)
        .scalar_subquery()
    )
    outstanding_condition = (StudentEmployment.status == StudentEmploymentStatus.ACTIVE) & (
        remaining > 0
    )
    paid_condition = (paid > 0) & (paid_salary_percent >= StudentEmployment.repayment_percent)
    if status is AdminEmploymentPaymentStatus.OUTSTANDING:
        conditions = [outstanding_condition]
    elif status is AdminEmploymentPaymentStatus.PAID:
        conditions = [paid_condition]
    else:
        conditions = []
    total = int(
        await session.scalar(select(func.count(StudentEmployment.id)).where(*conditions)) or 0
    )
    rows = (
        await session.execute(
            select(
                StudentEmployment,
                User,
                MentorStudent,
                remaining.label("remaining_kopecks"),
                paid.label("paid_kopecks"),
                overdue.label("overdue_kopecks"),
                overdue_count.label("overdue_payments"),
                next_payment.label("next_payment_date"),
                paid_count.label("paid_installments"),
                installment_count.label("total_installments"),
            )
            .join(User, User.id == StudentEmployment.student_id)
            .outerjoin(MentorStudent, MentorStudent.student_id == User.id)
            .where(*conditions)
            .order_by(
                (overdue > 0).desc(),
                next_payment,
                StudentEmployment.start_date.desc(),
                User.first_name,
                User.last_name,
            )
            .limit(limit)
            .offset(offset)
        )
    ).all()
    mentor_ids = {relation.mentor_id for _, _, relation, *_ in rows if relation is not None}
    mentors = (
        {
            mentor.id: mentor
            for mentor in await session.scalars(select(User).where(User.id.in_(mentor_ids)))
        }
        if mentor_ids
        else {}
    )
    items = [
        AdminPaymentStudentRead(
            employment_id=employment.id,
            student_id=student.id,
            student_name=" ".join(filter(None, (student.first_name, student.last_name))),
            student_telegram_username=student.telegram_username,
            mentor_id=relation.mentor_id if relation else None,
            mentor_name=(
                " ".join(
                    filter(
                        None,
                        (
                            mentors[relation.mentor_id].first_name,
                            mentors[relation.mentor_id].last_name,
                        ),
                    )
                )
                if relation and relation.mentor_id in mentors
                else None
            ),
            company_name=employment.company_name,
            employment_start_date=employment.start_date,
            net_salary_kopecks=employment.net_salary_kopecks,
            repayment_percent=employment.repayment_percent,
            total_owed_kopecks=_percent_of(
                employment.net_salary_kopecks,
                employment.repayment_percent,
            ),
            paid_kopecks=row_paid,
            remaining_kopecks=row_remaining,
            overdue_kopecks=row_overdue,
            overdue_payments=row_overdue_count,
            next_payment_date=row_next_payment,
            paid_installments=row_paid_count,
            total_installments=row_installment_count,
        )
        for (
            employment,
            student,
            relation,
            row_remaining,
            row_paid,
            row_overdue,
            row_overdue_count,
            row_next_payment,
            row_paid_count,
            row_installment_count,
        ) in rows
    ]
    today = date.today()
    aggregate = (
        await session.execute(
            select(
                func.coalesce(
                    func.sum(PaymentInstallment.amount_kopecks).filter(
                        PaymentInstallment.status.in_(unpaid_statuses)
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(PaymentInstallment.amount_kopecks).filter(
                        PaymentInstallment.status == PaymentInstallmentStatus.PAID
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(PaymentInstallment.amount_kopecks).filter(
                        PaymentInstallment.status.in_(unpaid_statuses),
                        PaymentInstallment.due_date < today,
                    ),
                    0,
                ),
            )
            .join(StudentEmployment)
            .where(*conditions)
        )
    ).one()
    return AdminPaymentStudentPage(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        total_remaining_kopecks=aggregate[0],
        total_paid_kopecks=aggregate[1],
        total_overdue_kopecks=aggregate[2],
    )


async def mentor_reward_summary(session: AsyncSession, mentor: User) -> MentorRewardSummary:
    rewards = list(
        await session.scalars(
            select(MentorReward)
            .where(
                MentorReward.mentor_id == mentor.id,
                MentorReward.voided_at.is_(None),
            )
            .order_by(MentorReward.created_at.desc())
        )
    )
    accrued = sum(reward.amount_kopecks for reward in rewards)
    paid = sum(reward.paid_kopecks for reward in rewards)
    reserved_by_reward = await _reserved_amounts_by_reward(
        session, [reward.id for reward in rewards]
    )
    reserved = sum(reserved_by_reward.values())
    return MentorRewardSummary(
        mentor_id=mentor.id,
        accrued_kopecks=accrued,
        paid_kopecks=paid,
        unpaid_kopecks=accrued - paid,
        reserved_kopecks=reserved,
        available_kopecks=max(accrued - paid - reserved, 0),
        rewards=await _mentor_reward_reads(session, mentor_id=mentor.id),
        payouts=await _payout_reads(session, mentor_id=mentor.id),
    )


async def _mentor_reward_reads(
    session: AsyncSession, *, mentor_id: UUID | None = None
) -> list[MentorRewardRead]:
    student_user = aliased(User)
    mentor_user = aliased(User)
    statement = (
        select(MentorReward, student_user, mentor_user, StudentEmployment)
        .join(student_user, student_user.id == MentorReward.student_id)
        .join(mentor_user, mentor_user.id == MentorReward.mentor_id)
        .outerjoin(PaymentInstallment, PaymentInstallment.id == MentorReward.installment_id)
        .outerjoin(StudentEmployment, StudentEmployment.id == PaymentInstallment.employment_id)
        .where(MentorReward.voided_at.is_(None))
        .order_by(MentorReward.created_at.desc())
    )
    if mentor_id is not None:
        statement = statement.where(MentorReward.mentor_id == mentor_id)
    rows = (await session.execute(statement)).all()
    reserved_by_reward = await _reserved_amounts_by_reward(
        session, [reward.id for reward, _, _, _ in rows]
    )
    return [
        MentorRewardRead(
            id=reward.id,
            kind=reward.kind,
            mentor_id=mentor.id,
            mentor_name=" ".join(filter(None, (mentor.first_name, mentor.last_name))),
            mentor_telegram_username=mentor.telegram_username,
            student_id=student.id,
            student_name=" ".join(filter(None, (student.first_name, student.last_name))),
            student_telegram_username=student.telegram_username,
            company_name=employment.company_name if employment else None,
            basis_kopecks=reward.basis_kopecks,
            reward_percent=reward.reward_percent,
            amount_kopecks=reward.amount_kopecks,
            paid_kopecks=reward.paid_kopecks,
            reserved_kopecks=reserved_by_reward.get(reward.id, 0),
            available_kopecks=max(
                reward.amount_kopecks - reward.paid_kopecks - reserved_by_reward.get(reward.id, 0),
                0,
            ),
            created_at=reward.created_at,
            paid_at=reward.paid_at,
        )
        for reward, student, mentor, employment in rows
    ]


async def mark_mentor_reward_paid(session: AsyncSession, reward_id: UUID, admin: User) -> None:
    reward = await session.scalar(select(MentorReward).where(MentorReward.id == reward_id))
    if reward is None:
        api_error(404, "mentor_reward_not_found", "Mentor reward was not found")
    if reward.voided_at is not None:
        api_error(409, "mentor_reward_voided", "A voided reward cannot be paid")
    await _lock_mentor(session, reward.mentor_id)
    reward = await session.scalar(
        select(MentorReward).where(MentorReward.id == reward_id).with_for_update()
    )
    if reward is None:
        api_error(404, "mentor_reward_not_found", "Mentor reward was not found")
    if reward.voided_at is not None:
        api_error(409, "mentor_reward_voided", "A voided reward cannot be paid")
    remaining = reward.amount_kopecks - reward.paid_kopecks
    if remaining <= 0:
        return
    reserved = await _reserved_amounts_by_reward(session, [reward.id])
    if reserved.get(reward.id, 0):
        api_error(
            409,
            "mentor_reward_reserved",
            "This reward is already included in a pending payout request",
        )
    payout = MentorPayout(
        mentor_id=reward.mentor_id,
        requested_by_user_id=admin.id,
        amount_kopecks=remaining,
        origin=MentorPayoutOrigin.ADMIN_DIRECT,
        status=MentorPayoutStatus.PAID,
        paid_by_user_id=admin.id,
        paid_at=datetime.now(UTC),
    )
    session.add(payout)
    await session.flush()
    session.add(
        MentorPayoutAllocation(
            payout_id=payout.id,
            reward_id=reward.id,
            amount_kopecks=remaining,
        )
    )
    reward.paid_kopecks += remaining
    reward.paid_at = payout.paid_at
    await session.commit()


async def void_mentor_reward(
    session: AsyncSession,
    admin: User,
    reward_id: UUID,
    reason: str,
) -> AdminMentorPayoutDashboard:
    reward = await session.scalar(select(MentorReward).where(MentorReward.id == reward_id))
    if reward is None:
        api_error(404, "mentor_reward_not_found", "Mentor reward was not found")
    await _lock_mentor(session, reward.mentor_id)
    reward = await session.scalar(
        select(MentorReward).where(MentorReward.id == reward_id).with_for_update()
    )
    if reward is None:
        api_error(404, "mentor_reward_not_found", "Mentor reward was not found")
    if reward.voided_at is not None:
        api_error(409, "mentor_reward_already_voided", "The reward is already voided")
    reserved = await _reserved_amounts_by_reward(session, [reward.id])
    if reward.paid_kopecks > 0:
        api_error(
            409,
            "mentor_reward_already_paid",
            "Cancel the related mentor payout before deleting this reward",
        )
    if reserved.get(reward.id, 0) > 0:
        api_error(
            409,
            "mentor_reward_reserved",
            "Cancel the mentor payout request before deleting this reward",
        )
    reward.voided_by_user_id = admin.id
    reward.voided_at = datetime.now(UTC)
    reward.void_reason = reason
    await session.commit()
    return await admin_mentor_payout_dashboard(session)


async def request_mentor_payout(
    session: AsyncSession, mentor: User, amount_kopecks: int
) -> MentorRewardSummary:
    await _lock_mentor(session, mentor.id)
    existing = await session.scalar(
        select(MentorPayout.id).where(
            MentorPayout.mentor_id == mentor.id,
            MentorPayout.status == MentorPayoutStatus.REQUESTED,
        )
    )
    if existing is not None:
        api_error(409, "mentor_payout_already_requested", "There is already an open payout request")
    payout = MentorPayout(
        mentor_id=mentor.id,
        requested_by_user_id=mentor.id,
        amount_kopecks=amount_kopecks,
        origin=MentorPayoutOrigin.MENTOR_REQUEST,
        status=MentorPayoutStatus.REQUESTED,
    )
    session.add(payout)
    await session.flush()
    await _allocate_available_rewards(session, payout, amount_kopecks)
    await session.commit()
    return await mentor_reward_summary(session, mentor)


async def create_admin_mentor_payout(
    session: AsyncSession,
    admin: User,
    mentor_id: UUID,
    amount_kopecks: int,
    payment_reference: str | None,
) -> AdminMentorPayoutDashboard:
    mentor = await _lock_mentor(session, mentor_id)
    payout = MentorPayout(
        mentor_id=mentor.id,
        requested_by_user_id=admin.id,
        amount_kopecks=amount_kopecks,
        origin=MentorPayoutOrigin.ADMIN_DIRECT,
        status=MentorPayoutStatus.PAID,
        payment_reference=payment_reference or None,
        paid_by_user_id=admin.id,
        paid_at=datetime.now(UTC),
    )
    session.add(payout)
    await session.flush()
    allocations = await _allocate_available_rewards(session, payout, amount_kopecks)
    _apply_paid_allocations(allocations, payout.paid_at)
    await session.commit()
    return await admin_mentor_payout_dashboard(session)


async def mark_mentor_payout_paid(
    session: AsyncSession,
    admin: User,
    payout_id: UUID,
    payment_reference: str | None,
) -> AdminMentorPayoutDashboard:
    payout = await _payout_model(session, payout_id, lock=True)
    if payout.status is not MentorPayoutStatus.REQUESTED:
        api_error(409, "mentor_payout_not_requested", "Only an open request can be paid")
    await _lock_mentor(session, payout.mentor_id)
    allocations = list(
        await session.scalars(
            select(MentorPayoutAllocation)
            .where(MentorPayoutAllocation.payout_id == payout.id)
            .order_by(MentorPayoutAllocation.created_at)
        )
    )
    rewards = {
        reward.id: reward
        for reward in await session.scalars(
            select(MentorReward)
            .where(MentorReward.id.in_([item.reward_id for item in allocations]))
            .with_for_update()
        )
    }
    now = datetime.now(UTC)
    _apply_paid_allocations(
        [(rewards[item.reward_id], item.amount_kopecks) for item in allocations],
        now,
    )
    payout.status = MentorPayoutStatus.PAID
    payout.paid_by_user_id = admin.id
    payout.paid_at = now
    payout.payment_reference = payment_reference or payout.payment_reference
    await session.commit()
    return await admin_mentor_payout_dashboard(session)


async def edit_mentor_payout(
    session: AsyncSession,
    admin: User,
    payout_id: UUID,
    *,
    amount_kopecks: int,
    payment_reference: str | None,
    paid_at: datetime | None,
    reason: str,
) -> AdminMentorPayoutDashboard:
    payout = await _payout_model(session, payout_id, lock=True)
    if payout.status is MentorPayoutStatus.CANCELLED:
        api_error(409, "mentor_payout_cancelled", "A cancelled payout cannot be edited")
    await _lock_mentor(session, payout.mentor_id)
    allocations, rewards = await _payout_allocations_and_rewards(session, payout.id)
    previous_amount = payout.amount_kopecks
    previous_reference = payout.payment_reference
    previous_paid_at = payout.paid_at

    if payout.status is MentorPayoutStatus.PAID:
        _reverse_paid_allocations(allocations, rewards)
    await session.execute(
        delete(MentorPayoutAllocation).where(MentorPayoutAllocation.payout_id == payout.id)
    )
    await session.flush()

    payout.amount_kopecks = amount_kopecks
    payout.payment_reference = payment_reference or None
    if payout.status is MentorPayoutStatus.PAID:
        payout.paid_at = paid_at or payout.paid_at or datetime.now(UTC)
    else:
        payout.paid_at = None
    payout.edited_by_user_id = admin.id
    payout.edited_at = datetime.now(UTC)
    payout.edit_reason = reason

    new_allocations = await _allocate_available_rewards(session, payout, amount_kopecks)
    if payout.status is MentorPayoutStatus.PAID:
        _apply_paid_allocations(new_allocations, payout.paid_at)
    session.add(
        MentorPayoutRevision(
            payout_id=payout.id,
            edited_by_user_id=admin.id,
            reason=reason,
            previous_amount_kopecks=previous_amount,
            new_amount_kopecks=amount_kopecks,
            previous_payment_reference=previous_reference,
            new_payment_reference=payout.payment_reference,
            previous_paid_at=previous_paid_at,
            new_paid_at=payout.paid_at,
        )
    )
    await session.commit()
    return await admin_mentor_payout_dashboard(session)


async def cancel_mentor_payout(
    session: AsyncSession,
    actor: User,
    payout_id: UUID,
    reason: str | None,
) -> None:
    payout = await _payout_model(session, payout_id, lock=True)
    if actor.role is not UserRole.ADMIN and payout.mentor_id != actor.id:
        api_error(404, "mentor_payout_not_found", "Payout request was not found")
    if payout.status is MentorPayoutStatus.CANCELLED:
        api_error(409, "mentor_payout_already_cancelled", "The payout is already cancelled")
    if payout.status is MentorPayoutStatus.PAID:
        if actor.role is not UserRole.ADMIN:
            api_error(409, "mentor_payout_already_paid", "A paid payout cannot be cancelled")
        if not reason or len(reason.strip()) < 3:
            api_error(
                422,
                "mentor_payout_cancellation_reason_required",
                "A reason is required to cancel a paid payout",
            )
        await _lock_mentor(session, payout.mentor_id)
        allocations, rewards = await _payout_allocations_and_rewards(session, payout.id)
        _reverse_paid_allocations(allocations, rewards)
    payout.status = MentorPayoutStatus.CANCELLED
    payout.cancelled_by_user_id = actor.id
    payout.cancelled_at = datetime.now(UTC)
    payout.cancellation_reason = reason or None
    await session.commit()


async def ensure_mentor_payout_receipt_upload_allowed(
    session: AsyncSession, mentor: User, payout_id: UUID
) -> None:
    payout = await _payout_model(session, payout_id)
    if payout.mentor_id != mentor.id:
        api_error(404, "mentor_payout_not_found", "Payout was not found")
    if payout.status is not MentorPayoutStatus.PAID:
        api_error(409, "mentor_payout_not_paid", "A receipt can be attached after payment")


async def admin_mentor_payout_dashboard(session: AsyncSession) -> AdminMentorPayoutDashboard:
    rewards = list(
        await session.scalars(select(MentorReward).where(MentorReward.voided_at.is_(None)))
    )
    reward_ids = [reward.id for reward in rewards]
    reserved_by_reward = await _reserved_amounts_by_reward(session, reward_ids)
    mentor_ids = {reward.mentor_id for reward in rewards}
    mentor_ids.update(await session.scalars(select(MentorPayout.mentor_id).distinct()))
    mentors = {
        mentor.id: mentor
        for mentor in await session.scalars(
            select(User).where(User.id.in_(mentor_ids)).order_by(User.first_name, User.last_name)
        )
    }
    balances: list[AdminMentorPayoutBalanceRead] = []
    for mentor_id, mentor in mentors.items():
        mentor_rewards = [reward for reward in rewards if reward.mentor_id == mentor_id]
        accrued = sum(reward.amount_kopecks for reward in mentor_rewards)
        paid = sum(reward.paid_kopecks for reward in mentor_rewards)
        reserved = sum(reserved_by_reward.get(reward.id, 0) for reward in mentor_rewards)
        balances.append(
            AdminMentorPayoutBalanceRead(
                mentor_id=mentor.id,
                mentor_name=" ".join(filter(None, (mentor.first_name, mentor.last_name))),
                mentor_telegram_username=mentor.telegram_username,
                accrued_kopecks=accrued,
                paid_kopecks=paid,
                reserved_kopecks=reserved,
                available_kopecks=max(accrued - paid - reserved, 0),
            )
        )
    return AdminMentorPayoutDashboard(
        balances=balances,
        payouts=await _payout_reads(session),
    )


async def admin_mentor_payout_detail(
    session: AsyncSession, mentor_id: UUID
) -> AdminMentorPayoutDetail:
    mentor = await session.get(User, mentor_id)
    if mentor is None:
        api_error(404, "mentor_not_found", "Mentor was not found")
    rewards = list(
        await session.scalars(
            select(MentorReward).where(
                MentorReward.mentor_id == mentor_id,
                MentorReward.voided_at.is_(None),
            )
        )
    )
    payouts = await _payout_reads(session, mentor_id=mentor_id)
    reserved_by_reward = await _reserved_amounts_by_reward(
        session, [reward.id for reward in rewards]
    )
    accrued = sum(reward.amount_kopecks for reward in rewards)
    paid = sum(reward.paid_kopecks for reward in rewards)
    reserved = sum(reserved_by_reward.values())
    return AdminMentorPayoutDetail(
        mentor_id=mentor.id,
        mentor_name=" ".join(filter(None, (mentor.first_name, mentor.last_name))),
        mentor_telegram_username=mentor.telegram_username,
        accrued_kopecks=accrued,
        paid_kopecks=paid,
        reserved_kopecks=reserved,
        available_kopecks=max(accrued - paid - reserved, 0),
        rewards=await _mentor_reward_reads(session, mentor_id=mentor_id),
        payouts=payouts,
    )


async def set_mentor_payout_receipt(
    session: AsyncSession, mentor: User, payout_id: UUID, upload: StoredUpload
) -> tuple[MentorRewardSummary, str | None]:
    payout = await _payout_model(session, payout_id, lock=True)
    if payout.mentor_id != mentor.id:
        api_error(404, "mentor_payout_not_found", "Payout was not found")
    if payout.status is not MentorPayoutStatus.PAID:
        api_error(409, "mentor_payout_not_paid", "A receipt can be attached after payment")
    previous_key = payout.receipt_storage_key
    payout.receipt_storage_key = upload.storage_key
    payout.receipt_filename = upload.filename
    payout.receipt_content_type = upload.content_type
    payout.receipt_size = upload.size
    payout.receipt_uploaded_at = datetime.now(UTC)
    await session.commit()
    return await mentor_reward_summary(session, mentor), previous_key


async def delete_mentor_payout_receipt(
    session: AsyncSession, mentor: User, payout_id: UUID
) -> tuple[MentorRewardSummary, str | None]:
    payout = await _payout_model(session, payout_id, lock=True)
    if payout.mentor_id != mentor.id:
        api_error(404, "mentor_payout_not_found", "Payout was not found")
    previous_key = payout.receipt_storage_key
    payout.receipt_storage_key = None
    payout.receipt_filename = None
    payout.receipt_content_type = None
    payout.receipt_size = None
    payout.receipt_uploaded_at = None
    await session.commit()
    return await mentor_reward_summary(session, mentor), previous_key


async def payout_receipt_upload(
    session: AsyncSession, viewer: User, payout_id: UUID
) -> StoredUpload:
    payout = await _payout_model(session, payout_id)
    if viewer.role is not UserRole.ADMIN and payout.mentor_id != viewer.id:
        api_error(404, "mentor_payout_not_found", "Payout was not found")
    if (
        payout.receipt_storage_key is None
        or payout.receipt_filename is None
        or payout.receipt_content_type is None
        or payout.receipt_size is None
    ):
        api_error(404, "mentor_payout_receipt_not_found", "Receipt was not found")
    return StoredUpload(
        storage_key=payout.receipt_storage_key,
        filename=payout.receipt_filename,
        content_type=payout.receipt_content_type,
        size=payout.receipt_size,
    )


async def _lock_mentor(session: AsyncSession, mentor_id: UUID) -> User:
    mentor = await session.scalar(select(User).where(User.id == mentor_id).with_for_update())
    if mentor is None or mentor.role not in {UserRole.MENTOR, UserRole.ADMIN}:
        api_error(404, "mentor_not_found", "Mentor was not found")
    return mentor


async def _payout_model(
    session: AsyncSession, payout_id: UUID, *, lock: bool = False
) -> MentorPayout:
    statement = select(MentorPayout).where(MentorPayout.id == payout_id)
    if lock:
        statement = statement.with_for_update()
    payout = await session.scalar(statement)
    if payout is None:
        api_error(404, "mentor_payout_not_found", "Payout was not found")
    return payout


async def _reserved_amounts_by_reward(
    session: AsyncSession, reward_ids: list[UUID]
) -> dict[UUID, int]:
    if not reward_ids:
        return {}
    rows = (
        await session.execute(
            select(
                MentorPayoutAllocation.reward_id,
                func.sum(MentorPayoutAllocation.amount_kopecks),
            )
            .join(MentorPayout, MentorPayout.id == MentorPayoutAllocation.payout_id)
            .where(
                MentorPayoutAllocation.reward_id.in_(reward_ids),
                MentorPayout.status == MentorPayoutStatus.REQUESTED,
            )
            .group_by(MentorPayoutAllocation.reward_id)
        )
    ).all()
    return {reward_id: int(amount) for reward_id, amount in rows}


async def _allocate_available_rewards(
    session: AsyncSession, payout: MentorPayout, amount_kopecks: int
) -> list[tuple[MentorReward, int]]:
    rewards = list(
        await session.scalars(
            select(MentorReward)
            .where(
                MentorReward.mentor_id == payout.mentor_id,
                MentorReward.voided_at.is_(None),
            )
            .order_by(MentorReward.created_at, MentorReward.id)
            .with_for_update()
        )
    )
    reserved = await _reserved_amounts_by_reward(session, [reward.id for reward in rewards])
    available_total = sum(
        max(reward.amount_kopecks - reward.paid_kopecks - reserved.get(reward.id, 0), 0)
        for reward in rewards
    )
    if amount_kopecks > available_total:
        api_error(
            409,
            "mentor_payout_exceeds_available",
            "Payout amount exceeds the mentor's available balance",
        )
    remaining = amount_kopecks
    allocations: list[tuple[MentorReward, int]] = []
    for reward in rewards:
        available = max(reward.amount_kopecks - reward.paid_kopecks - reserved.get(reward.id, 0), 0)
        allocated = min(available, remaining)
        if allocated <= 0:
            continue
        session.add(
            MentorPayoutAllocation(
                payout_id=payout.id,
                reward_id=reward.id,
                amount_kopecks=allocated,
            )
        )
        allocations.append((reward, allocated))
        remaining -= allocated
        if remaining == 0:
            break
    return allocations


def _apply_paid_allocations(
    allocations: list[tuple[MentorReward, int]], paid_at: datetime | None
) -> None:
    for reward, amount in allocations:
        reward.paid_kopecks += amount
        if reward.paid_kopecks == reward.amount_kopecks:
            reward.paid_at = paid_at


async def _payout_allocations_and_rewards(
    session: AsyncSession, payout_id: UUID
) -> tuple[list[MentorPayoutAllocation], dict[UUID, MentorReward]]:
    allocations = list(
        await session.scalars(
            select(MentorPayoutAllocation)
            .where(MentorPayoutAllocation.payout_id == payout_id)
            .order_by(MentorPayoutAllocation.created_at, MentorPayoutAllocation.id)
        )
    )
    if not allocations:
        return [], {}
    rewards = {
        reward.id: reward
        for reward in await session.scalars(
            select(MentorReward)
            .where(MentorReward.id.in_([allocation.reward_id for allocation in allocations]))
            .with_for_update()
        )
    }
    return allocations, rewards


def _reverse_paid_allocations(
    allocations: list[MentorPayoutAllocation], rewards: dict[UUID, MentorReward]
) -> None:
    for allocation in allocations:
        reward = rewards.get(allocation.reward_id)
        if reward is None or reward.paid_kopecks < allocation.amount_kopecks:
            raise RuntimeError("Mentor payout allocations are inconsistent with paid rewards")
        reward.paid_kopecks -= allocation.amount_kopecks
        if reward.paid_kopecks < reward.amount_kopecks:
            reward.paid_at = None


async def _payout_reads(
    session: AsyncSession, *, mentor_id: UUID | None = None
) -> list[MentorPayoutRead]:
    mentor_user = aliased(User)
    statement = (
        select(MentorPayout, mentor_user)
        .join(mentor_user, mentor_user.id == MentorPayout.mentor_id)
        .order_by(MentorPayout.created_at.desc())
    )
    if mentor_id is not None:
        statement = statement.where(MentorPayout.mentor_id == mentor_id)
    rows = (await session.execute(statement)).all()
    return [
        MentorPayoutRead(
            id=payout.id,
            mentor_id=mentor.id,
            mentor_name=" ".join(filter(None, (mentor.first_name, mentor.last_name))),
            mentor_telegram_username=mentor.telegram_username,
            amount_kopecks=payout.amount_kopecks,
            origin=payout.origin,
            status=payout.status,
            payment_reference=payout.payment_reference,
            created_at=payout.created_at,
            paid_at=payout.paid_at,
            cancelled_at=payout.cancelled_at,
            cancellation_reason=payout.cancellation_reason,
            edited_at=payout.edited_at,
            edit_reason=payout.edit_reason,
            receipt_filename=payout.receipt_filename,
            receipt_content_type=payout.receipt_content_type,
            receipt_size=payout.receipt_size,
            receipt_uploaded_at=payout.receipt_uploaded_at,
        )
        for payout, mentor in rows
    ]


async def _regenerate_unpaid_installments(
    session: AsyncSession, employment: StudentEmployment
) -> None:
    if employment.net_salary_kopecks is None:
        api_error(409, "employment_compensation_missing", "Net salary must be confirmed first")
    billing_start = employment.billing_started_at or employment.start_date
    if billing_start is None:
        api_error(409, "employment_start_missing", "Billing start date must be confirmed first")
    paid_count = int(
        await session.scalar(
            select(func.count(PaymentInstallment.id)).where(
                PaymentInstallment.employment_id == employment.id,
                PaymentInstallment.status == PaymentInstallmentStatus.PAID,
            )
        )
        or 0
    )
    if paid_count:
        await _reschedule_unpaid_installments(session, employment)
        return
    await session.execute(
        delete(PaymentInstallment).where(PaymentInstallment.employment_id == employment.id)
    )
    amounts = calculate_installment_amounts(
        employment.net_salary_kopecks, employment.repayment_percent
    )
    salary_percents = calculate_installment_percents(employment.repayment_percent)
    due_dates = calculate_due_dates(
        billing_start,
        (employment.payment_day_first, employment.payment_day_second),
        len(amounts),
    )
    session.add_all(
        [
            PaymentInstallment(
                employment_id=employment.id,
                sequence_number=index,
                due_date=due_date,
                amount_kopecks=amount,
                salary_percent=salary_percent,
            )
            for index, (due_date, amount, salary_percent) in enumerate(
                zip(due_dates, amounts, salary_percents, strict=True), 1
            )
        ]
    )


async def ensure_profile_billing_installments(
    session: AsyncSession,
    employment: StudentEmployment,
) -> None:
    """Hand a reviewed profile-employment case to the existing result-fee schedule.

    The existing installment table remains the single source of payment obligations.
    Replaying an assessment therefore cannot create a second schedule.
    """
    existing = await session.scalar(
        select(PaymentInstallment.id).where(PaymentInstallment.employment_id == employment.id)
    )
    if existing is not None:
        return
    await _regenerate_unpaid_installments(session, employment)


async def _recalculate_installments_after_salary_correction(
    session: AsyncSession,
    employment: StudentEmployment,
) -> None:
    if employment.net_salary_kopecks is None:
        api_error(409, "employment_compensation_missing", "Net salary must be confirmed first")
    billing_start = employment.billing_started_at or employment.start_date
    if billing_start is None:
        api_error(409, "employment_start_missing", "Billing start date must be confirmed first")
    installments = await _installments(session, employment.id)
    paid = [item for item in installments if item.status is PaymentInstallmentStatus.PAID]
    outstanding = [
        item
        for item in installments
        if item.status in {PaymentInstallmentStatus.SCHEDULED, PaymentInstallmentStatus.PENDING}
    ]
    total_owed = _percent_of(employment.net_salary_kopecks, employment.repayment_percent)
    already_paid = sum(item.amount_kopecks for item in paid)
    if already_paid > total_owed:
        api_error(
            409,
            "corrected_salary_below_paid_amount",
            "The corrected total obligation cannot be lower than the amount already paid",
        )

    paid_percent = _salary_percent(already_paid, employment.net_salary_kopecks)
    if already_paid == total_owed:
        paid_percent = employment.repayment_percent
    paid_percent = min(paid_percent, employment.repayment_percent)
    allocated_paid_percent = Decimal("0")
    for index, installment in enumerate(paid):
        if index == len(paid) - 1:
            installment.salary_percent = paid_percent - allocated_paid_percent
        else:
            installment_percent = min(
                _salary_percent(installment.amount_kopecks, employment.net_salary_kopecks),
                paid_percent - allocated_paid_percent,
            )
            installment.salary_percent = installment_percent
            allocated_paid_percent += installment_percent

    for installment in outstanding:
        attempts = list(
            await session.scalars(
                select(PaymentAttempt).where(
                    PaymentAttempt.installment_id == installment.id,
                    PaymentAttempt.status.in_(
                        [PaymentAttemptStatus.PENDING, PaymentAttemptStatus.MANUAL_REVIEW]
                    ),
                )
            )
        )
        for attempt in attempts:
            # A bank link contains the old amount. If it is paid later, its
            # webhook is deliberately routed to manual review.
            attempt.status = PaymentAttemptStatus.REVOKED
            attempt.payment_url = None

    remaining_amount = total_owed - already_paid
    regular_amount = _percent_of(employment.net_salary_kopecks, INSTALLMENT_PERCENT)
    desired_amounts: list[int] = []
    while remaining_amount > 0:
        amount = min(regular_amount, remaining_amount)
        desired_amounts.append(amount)
        remaining_amount -= amount

    remaining_percent = employment.repayment_percent - paid_percent
    desired_percents: list[Decimal] = []
    allocated_remaining_percent = Decimal("0")
    for index in range(len(desired_amounts)):
        if index == len(desired_amounts) - 1:
            installment_percent = remaining_percent - allocated_remaining_percent
        else:
            installment_percent = min(
                INSTALLMENT_PERCENT,
                remaining_percent - allocated_remaining_percent,
            )
        desired_percents.append(installment_percent)
        allocated_remaining_percent += installment_percent

    reused_count = min(len(outstanding), len(desired_amounts))
    for installment, amount, salary_percent in zip(
        outstanding[:reused_count],
        desired_amounts[:reused_count],
        desired_percents[:reused_count],
        strict=True,
    ):
        installment.amount_kopecks = amount
        installment.salary_percent = salary_percent
        installment.status = PaymentInstallmentStatus.SCHEDULED

    for installment in outstanding[reused_count:]:
        installment.status = PaymentInstallmentStatus.CANCELLED

    missing_count = len(desired_amounts) - reused_count
    if missing_count <= 0:
        return
    last_due_date = max(
        (item.due_date for item in installments),
        default=_add_month(billing_start) - timedelta(days=1),
    )
    due_dates = _payment_dates_on_or_after(
        last_due_date + timedelta(days=1),
        (employment.payment_day_first, employment.payment_day_second),
        missing_count,
    )
    next_sequence = max((item.sequence_number for item in installments), default=0) + 1
    session.add_all(
        [
            PaymentInstallment(
                employment_id=employment.id,
                sequence_number=next_sequence + index,
                due_date=due_date,
                amount_kopecks=amount,
                salary_percent=salary_percent,
            )
            for index, (due_date, amount, salary_percent) in enumerate(
                zip(
                    due_dates,
                    desired_amounts[reused_count:],
                    desired_percents[reused_count:],
                    strict=True,
                )
            )
        ]
    )


async def _reschedule_unpaid_installments(
    session: AsyncSession, employment: StudentEmployment
) -> None:
    installments = await _installments(session, employment.id)
    today = date.today()
    fixed = [
        item
        for item in installments
        if item.status in {PaymentInstallmentStatus.PAID, PaymentInstallmentStatus.CANCELLED}
        or item.due_date < today
    ]
    movable = [item for item in installments if item not in fixed]
    if not movable:
        return
    billing_start = employment.billing_started_at or employment.start_date
    if billing_start is None:
        api_error(409, "employment_start_missing", "Billing start date must be confirmed first")
    eligible = max(_add_month(billing_start), today)
    if fixed:
        eligible = max(eligible, max(item.due_date for item in fixed) + timedelta(days=1))
    due_dates = _payment_dates_on_or_after(
        eligible,
        (employment.payment_day_first, employment.payment_day_second),
        len(movable),
    )
    for installment, due_date in zip(movable, due_dates, strict=True):
        installment.due_date = due_date


async def _installments(session: AsyncSession, employment_id: UUID) -> list[PaymentInstallment]:
    return list(
        await session.scalars(
            select(PaymentInstallment)
            .where(PaymentInstallment.employment_id == employment_id)
            .order_by(PaymentInstallment.sequence_number)
        )
    )


async def _latest_attempts(
    session: AsyncSession, installment_ids: list[UUID]
) -> dict[UUID, PaymentAttempt]:
    if not installment_ids:
        return {}
    attempts = list(
        await session.scalars(
            select(PaymentAttempt)
            .where(PaymentAttempt.installment_id.in_(installment_ids))
            .order_by(PaymentAttempt.created_at.desc())
        )
    )
    result: dict[UUID, PaymentAttempt] = {}
    for attempt in attempts:
        result.setdefault(attempt.installment_id, attempt)
    return result


async def _latest_due_date_revisions(
    session: AsyncSession, installment_ids: list[UUID]
) -> dict[UUID, PaymentInstallmentDueDateRevision]:
    if not installment_ids:
        return {}
    revisions = list(
        await session.scalars(
            select(PaymentInstallmentDueDateRevision)
            .where(PaymentInstallmentDueDateRevision.installment_id.in_(installment_ids))
            .order_by(PaymentInstallmentDueDateRevision.created_at.desc())
        )
    )
    result: dict[UUID, PaymentInstallmentDueDateRevision] = {}
    for revision in revisions:
        result.setdefault(revision.installment_id, revision)
    return result


async def _resolve_company(
    session: AsyncSession, company_id: UUID | None, company_name: str
) -> Company:
    if company_id is None:
        return await get_or_create_company(session, company_name)
    company = await session.get(Company, company_id)
    if company is None:
        api_error(422, "invalid_company", "Selected company was not found")
    return company


def _employment_read(employment: StudentEmployment) -> EmploymentRead:
    return EmploymentRead(
        id=employment.id,
        company_id=employment.company_id,
        company_name=employment.company_name,
        start_date=employment.start_date,
        net_salary_kopecks=employment.net_salary_kopecks,
        repayment_percent=employment.repayment_percent,
        status=employment.status,
        ended_at=employment.ended_at,
        end_reason=employment.end_reason,
        payment_days=[employment.payment_day_first, employment.payment_day_second],
        total_owed_kopecks=(
            _percent_of(employment.net_salary_kopecks, employment.repayment_percent)
            if employment.net_salary_kopecks is not None
            else 0
        ),
        created_at=employment.created_at,
        updated_at=employment.updated_at,
    )


def _tochka_test_payment_read(payment: TochkaTestPayment) -> AdminTochkaTestPaymentRead:
    return AdminTochkaTestPaymentRead(
        id=payment.id,
        amount_kopecks=payment.amount_kopecks,
        status=payment.status,
        payment_url=payment.payment_url,
        provider_operation_id=payment.provider_operation_id,
        approved_at=payment.approved_at,
        created_at=payment.created_at,
    )


def _admin_item(
    installment: PaymentInstallment,
    employment: StudentEmployment,
    student: User,
    relation: MentorStudent | None,
    reward: MentorReward | None,
    mentors: dict[UUID, User],
    requires_manual_review: bool,
) -> AdminPaymentListItem:
    mentor_id = reward.mentor_id if reward is not None else relation.mentor_id if relation else None
    mentor = mentors.get(mentor_id) if mentor_id else None
    return AdminPaymentListItem(
        installment_id=installment.id,
        student_id=student.id,
        student_name=" ".join(filter(None, (student.first_name, student.last_name))),
        student_telegram_username=student.telegram_username,
        mentor_id=mentor.id if mentor else None,
        mentor_name=(
            " ".join(filter(None, (mentor.first_name, mentor.last_name))) if mentor else None
        ),
        company_name=employment.company_name,
        due_date=installment.due_date,
        amount_kopecks=installment.amount_kopecks,
        status=installment.status,
        paid_at=installment.paid_at,
        mentor_reward_kopecks=reward.amount_kopecks if reward else None,
        mentor_reward_id=reward.id if reward else None,
        mentor_reward_paid_at=reward.paid_at if reward else None,
        requires_manual_review=requires_manual_review,
    )


def _rubles_to_kopecks(value: Decimal) -> int:
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _percent_of(amount_kopecks: int, percent: Decimal) -> int:
    return int(
        (Decimal(amount_kopecks) * percent / Decimal(100)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


def _salary_percent(amount_kopecks: int, net_salary_kopecks: int) -> Decimal:
    if amount_kopecks <= 0:
        return Decimal("0")
    return (Decimal(amount_kopecks) * Decimal(100) / Decimal(net_salary_kopecks)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def _is_absolute_https_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme.lower() == "https"
        and parsed.hostname is not None
        and parsed.username is None
        and parsed.password is None
        and not parsed.fragment
    )


def _proportional_mentor_reward(
    student_payment_kopecks: int,
    mentor_salary_percent: Decimal,
    student_repayment_percent: Decimal,
) -> int:
    return int(
        (
            Decimal(student_payment_kopecks) * mentor_salary_percent / student_repayment_percent
        ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )


def _add_month(value: date) -> date:
    year = value.year + (1 if value.month == 12 else 0)
    month = 1 if value.month == 12 else value.month + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))
