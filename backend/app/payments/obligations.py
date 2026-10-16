"""Contract-scoped repayment accounting. A previous contract never pays for a new one."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.errors import api_error
from app.legal.models import ContractAcceptance, LegalCheckout
from app.opportunities.models import GoTransitionEnrollment
from app.payments.models import (
    EmploymentCaseStatus,
    PaymentInstallment,
    PaymentInstallmentStatus,
    StudentEmployment,
    StudentEmploymentStatus,
    StudentPaymentObligation,
)
from app.users.models import User


async def go_obligation(
    session: AsyncSession,
    student_id: UUID,
    *,
    track_id: UUID | None = None,
    contract: ContractAcceptance | None = None,
) -> StudentPaymentObligation | None:
    query = (
        select(ContractAcceptance, GoTransitionEnrollment.track_id)
        .join(LegalCheckout, LegalCheckout.id == ContractAcceptance.checkout_session_id)
        .join(
            GoTransitionEnrollment,
            GoTransitionEnrollment.application_id == LegalCheckout.application_id,
        )
        .where(
            ContractAcceptance.user_id == student_id,
            ContractAcceptance.product_code == "python_to_go_transition",
            GoTransitionEnrollment.student_id == student_id,
        )
        .order_by(
            (ContractAcceptance.status == "active").desc(),
            ContractAcceptance.accepted_at.desc(),
            ContractAcceptance.id.desc(),
        )
        .limit(1)
    )
    if track_id is not None:
        query = query.where(GoTransitionEnrollment.track_id == track_id)
    if contract is not None:
        query = query.where(ContractAcceptance.id == contract.id)
    row = (await session.execute(query)).one_or_none()
    if row is None:
        return None
    accepted, go_track_id = row
    result = await session.scalar(
        select(StudentPaymentObligation).where(StudentPaymentObligation.contract_id == accepted.id)
    )
    if result is None:
        await session.execute(
            insert(StudentPaymentObligation)
            .values(
                student_id=student_id,
                contract_id=accepted.id,
                track_id=go_track_id,
                repayment_percent=Decimal(
                    str(accepted.snapshot["financial_terms"]["success_fee_percent"])
                ),
                terms_snapshot=dict(accepted.snapshot["financial_terms"]),
            )
            .on_conflict_do_nothing()
        )
        result = await session.scalar(
            select(StudentPaymentObligation).where(
                StudentPaymentObligation.contract_id == accepted.id
            )
        )
    return result


async def legacy_obligation(session: AsyncSession, student: User) -> StudentPaymentObligation:
    result = await session.scalar(
        select(StudentPaymentObligation).where(
            StudentPaymentObligation.student_id == student.id,
            StudentPaymentObligation.contract_id.is_(None),
        )
    )
    if result is None:
        original = await session.scalar(
            select(StudentEmployment.repayment_percent)
            .where(
                StudentEmployment.student_id == student.id,
                StudentEmployment.obligation_id.is_(None),
            )
            .order_by(StudentEmployment.created_at, StudentEmployment.id)
            .limit(1)
        )
        await session.execute(
            insert(StudentPaymentObligation)
            .values(
                student_id=student.id,
                repayment_percent=original or student.repayment_percent,
                terms_snapshot={},
            )
            .on_conflict_do_nothing()
        )
        result = await session.scalar(
            select(StudentPaymentObligation).where(
                StudentPaymentObligation.student_id == student.id,
                StudentPaymentObligation.contract_id.is_(None),
            )
        )
    assert result is not None
    return result


async def current_obligation(session: AsyncSession, student: User) -> StudentPaymentObligation:
    return await go_obligation(session, student.id) or await legacy_obligation(session, student)


async def employment_obligation(
    session: AsyncSession, employment: StudentEmployment
) -> StudentPaymentObligation:
    if employment.obligation_id is not None:
        result = await session.get(StudentPaymentObligation, employment.obligation_id)
        assert result is not None
        return result
    student = await session.get(User, employment.student_id)
    assert student is not None
    result = await legacy_obligation(session, student)
    employment.obligation_id = result.id
    return result


def employment_scope(obligation: StudentPaymentObligation) -> ColumnElement[bool]:
    condition = StudentEmployment.obligation_id == obligation.id
    if obligation.contract_id is None:
        condition = or_(condition, StudentEmployment.obligation_id.is_(None))
    return (StudentEmployment.student_id == obligation.student_id) & condition


async def paid_percent(session: AsyncSession, obligation: StudentPaymentObligation) -> Decimal:
    value = await session.scalar(
        select(func.coalesce(func.sum(PaymentInstallment.salary_percent), 0))
        .join(StudentEmployment, StudentEmployment.id == PaymentInstallment.employment_id)
        .where(
            employment_scope(obligation), PaymentInstallment.status == PaymentInstallmentStatus.PAID
        )
    )
    return Decimal(value or 0)


async def remaining_percent(session: AsyncSession, obligation: StudentPaymentObligation) -> Decimal:
    return max(obligation.repayment_percent - await paid_percent(session, obligation), Decimal(0))


async def complete_paid_previous_employment(
    session: AsyncSession, obligation: StudentPaymentObligation
) -> None:
    """Archive a fully paid financial case without inventing an employment end date."""
    if obligation.contract_id is None:
        return
    active = await session.scalar(
        select(StudentEmployment)
        .where(
            StudentEmployment.student_id == obligation.student_id,
            StudentEmployment.status == StudentEmploymentStatus.ACTIVE,
        )
        .with_for_update()
    )
    if active is None or active.obligation_id == obligation.id:
        return
    installments = list(
        await session.scalars(
            select(PaymentInstallment).where(PaymentInstallment.employment_id == active.id)
        )
    )
    if not installments or any(
        row.status in {PaymentInstallmentStatus.SCHEDULED, PaymentInstallmentStatus.PENDING}
        for row in installments
    ):
        return
    paid = sum(
        (row.salary_percent for row in installments if row.status == PaymentInstallmentStatus.PAID),
        Decimal(0),
    )
    if paid < active.repayment_percent:
        return
    active.status = StudentEmploymentStatus.COMPLETED
    active.closed_at = datetime.now(UTC)
    if active.case_status is not None:
        active.case_status = EmploymentCaseStatus.CLOSED
    await session.flush()


async def require_billable_go_contract(
    session: AsyncSession,
    obligation: StudentPaymentObligation,
    started_at: date | None,
    confirmed: bool,
) -> ContractAcceptance | None:
    if obligation.contract_id is None:
        return None
    contract = await session.get(ContractAcceptance, obligation.contract_id)
    if contract is None or contract.status != "active":
        api_error(409, "go_contract_inactive", "Договор Go не действует")
    if not confirmed:
        api_error(
            422,
            "go_contract_billing_confirmation_required",
            "Подтвердите, что новая работа подпадает под условия договора Go",
        )
    if started_at is None or started_at < contract.accepted_at.date():
        api_error(
            422,
            "go_employment_predates_contract",
            "Дата новой работы не может предшествовать акцепту договора Go",
        )
    return contract
