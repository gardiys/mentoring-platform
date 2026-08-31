from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.mentors.models import MentorStudent, StudentLearningStatus, StudentMentorshipState
from app.opportunities.models import (
    ProgramCompletion,
    PythonRepeatApplication,
    PythonRepeatApplicationStatus,
    PythonRepeatEmploymentOffer,
    PythonRepeatEmploymentStatus,
    PythonRepeatEnrollment,
    PythonRepeatEnrollmentStatus,
    PythonRepeatInstallment,
    PythonRepeatInstallmentStatus,
    PythonRepeatObligationStatus,
    PythonRepeatOfferStatus,
    PythonRepeatProductOffer,
    PythonRepeatReason,
    PythonRepeatSearchMode,
    PythonRepeatSuccessFeeObligation,
)
from app.payments.models import (
    MentorReward,
    MentorRewardKind,
    PaymentInstallment,
    PaymentInstallmentStatus,
    StudentEmployment,
    StudentEmploymentStatus,
)
from app.tracks.models import LearningTrackEnrollment
from app.users.models import User, UserRole

ACTIVE_PROGRAM_ALUMNI_ID = UUID("20000000-0000-4000-8000-000000000003")
DEBT_ALUMNI_ID = UUID("20000000-0000-4000-8000-000000000004")
APPROVED_ALUMNI_ID = UUID("20000000-0000-4000-8000-000000000005")
REPEAT_ALUMNI_ID = UUID("20000000-0000-4000-8000-000000000006")

DEBT_EMPLOYMENT_ID = UUID("72000000-0000-4000-8000-000000000001")
DEBT_INSTALLMENT_ID = UUID("72000000-0000-4000-8000-000000000002")
APPROVED_APPLICATION_ID = UUID("73000000-0000-4000-8000-000000000001")
REPEAT_APPLICATION_ID = UUID("73000000-0000-4000-8000-000000000002")
REPEAT_ENROLLMENT_ID = UUID("73000000-0000-4000-8000-000000000003")
REPEAT_OFFER_ID = UUID("73000000-0000-4000-8000-000000000004")
REPEAT_OBLIGATION_ID = UUID("73000000-0000-4000-8000-000000000005")
REPEAT_INSTALLMENT_IDS = tuple(
    UUID(f"73000000-0000-4000-8000-{index:012d}") for index in range(6, 10)
)
REPEAT_FIXED_REWARD_ID = UUID("73000000-0000-4000-8000-000000000010")
REPEAT_VARIABLE_REWARD_ID = UUID("73000000-0000-4000-8000-000000000011")


def _snapshot(product: PythonRepeatProductOffer) -> dict[str, object]:
    return {
        "product_code": "PYTHON_REPEAT_MENTORSHIP",
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


async def _student(session: AsyncSession, user_id: UUID, first_name: str) -> User:
    student = await session.get(User, user_id)
    if student is None:
        student = User(
            id=user_id,
            first_name=first_name,
            last_name="Демо",
            email=f"python-repeat-{user_id.hex[-8:]}@example.com",
            role=UserRole.STUDENT,
        )
        session.add(student)
    student.is_active = True
    student.onboarding_completed_at = student.onboarding_completed_at or datetime.now(UTC)
    student.learning_start_date = student.learning_start_date or date.today()
    return student


async def _complete_python(
    session: AsyncSession,
    *,
    user_id: UUID,
    python_track_id: UUID,
    admin_id: UUID,
) -> None:
    if await session.get(LearningTrackEnrollment, (user_id, python_track_id)) is None:
        session.add(LearningTrackEnrollment(user_id=user_id, track_id=python_track_id))
    if await session.get(ProgramCompletion, (user_id, python_track_id)) is None:
        session.add(
            ProgramCompletion(
                user_id=user_id,
                track_id=python_track_id,
                completed_at=datetime.now(UTC) - timedelta(days=180),
                recorded_by_user_id=admin_id,
            )
        )
    state = await session.get(StudentMentorshipState, user_id)
    if state is None:
        session.add(
            StudentMentorshipState(
                student_id=user_id,
                learning_status=StudentLearningStatus.FINISHED,
                status_updated_at=datetime.now(UTC) - timedelta(days=180),
            )
        )
    else:
        state.learning_status = StudentLearningStatus.FINISHED


def _application_values(student_id: UUID) -> dict[str, object]:
    return {
        "student_id": student_id,
        "employment_status": PythonRepeatEmploymentStatus.EMPLOYED,
        "reason": PythonRepeatReason.WANTS_HIGHER_SALARY,
        "current_position": "Python Developer",
        "current_company": "Demo Company",
        "current_stack": "Python, FastAPI, PostgreSQL",
        "target_position": "Senior Python Backend Developer",
        "target_salary_kopecks": 30_000_000,
        "technical_gaps": "System Design и алгоритмы",
        "hours_per_week": 10,
        "search_mode": PythonRepeatSearchMode.SEARCH_WHILE_EMPLOYED,
    }


async def seed_python_repeat_demo(
    session: AsyncSession,
    *,
    python_track_id: UUID,
    mentor_id: UUID,
    admin_id: UUID,
) -> None:
    """Seed deterministic development examples for eligibility and finance states."""
    product = await session.scalar(
        select(PythonRepeatProductOffer).where(PythonRepeatProductOffer.version == 2)
    )
    if product is None:
        raise RuntimeError("Run Alembic migrations before the development seed")
    terms = _snapshot(product)
    now = datetime.now(UTC)

    active_program = await _student(
        session, ACTIVE_PROGRAM_ALUMNI_ID, "Выпускник с активной программой"
    )
    if await session.get(LearningTrackEnrollment, (active_program.id, python_track_id)) is None:
        session.add(LearningTrackEnrollment(user_id=active_program.id, track_id=python_track_id))

    debt_student = await _student(session, DEBT_ALUMNI_ID, "Выпускник с задолженностью")
    await _complete_python(
        session,
        user_id=debt_student.id,
        python_track_id=python_track_id,
        admin_id=admin_id,
    )
    if await session.get(StudentEmployment, DEBT_EMPLOYMENT_ID) is None:
        session.add(
            StudentEmployment(
                id=DEBT_EMPLOYMENT_ID,
                student_id=debt_student.id,
                company_name="Legacy Employer",
                start_date=date.today() - timedelta(days=120),
                net_salary_kopecks=20_000_000,
                repayment_percent=Decimal("100"),
                status=StudentEmploymentStatus.ACTIVE,
                payment_day_first=10,
                payment_day_second=25,
                recorded_by_user_id=admin_id,
            )
        )
    if await session.get(PaymentInstallment, DEBT_INSTALLMENT_ID) is None:
        session.add(
            PaymentInstallment(
                id=DEBT_INSTALLMENT_ID,
                employment_id=DEBT_EMPLOYMENT_ID,
                sequence_number=1,
                due_date=date.today() - timedelta(days=30),
                amount_kopecks=5_000_000,
                salary_percent=Decimal("25"),
                status=PaymentInstallmentStatus.SCHEDULED,
            )
        )

    approved_student = await _student(session, APPROVED_ALUMNI_ID, "Одобренный выпускник")
    await _complete_python(
        session,
        user_id=approved_student.id,
        python_track_id=python_track_id,
        admin_id=admin_id,
    )
    if await session.get(PythonRepeatApplication, APPROVED_APPLICATION_ID) is None:
        session.add(
            PythonRepeatApplication(
                id=APPROVED_APPLICATION_ID,
                **_application_values(approved_student.id),
                status=PythonRepeatApplicationStatus.APPROVED,
                responsible_user_id=admin_id,
                product_offer_id=product.id,
                terms_version=product.version,
                terms_snapshot=terms,
                approved_at=now,
                offer_expires_at=now + timedelta(days=product.offer_valid_days),
                admin_comment="Демо: условия одобрены, ожидается принятие выпускником.",
            )
        )

    repeat_student = await _student(session, REPEAT_ALUMNI_ID, "Повторный выпускник")
    await _complete_python(
        session,
        user_id=repeat_student.id,
        python_track_id=python_track_id,
        admin_id=admin_id,
    )
    if await session.get(PythonRepeatApplication, REPEAT_APPLICATION_ID) is None:
        session.add(
            PythonRepeatApplication(
                id=REPEAT_APPLICATION_ID,
                **_application_values(repeat_student.id),
                status=PythonRepeatApplicationStatus.ENROLLED,
                responsible_user_id=admin_id,
                product_offer_id=product.id,
                terms_version=product.version,
                terms_snapshot=terms,
                approved_at=now - timedelta(days=45),
                offer_expires_at=now - timedelta(days=31),
                accepted_at=now - timedelta(days=44),
                accepted_by_user_id=repeat_student.id,
                paid_at=now - timedelta(days=43),
                admin_comment="Демо: вступительный платёж оплачен.",
            )
        )
    enrollment_snapshot = {
        **terms,
        "application_id": str(REPEAT_APPLICATION_ID),
        "previous_enrollment_id": {
            "user_id": str(repeat_student.id),
            "track_id": str(python_track_id),
        },
    }
    repeat_enrollment = await session.get(PythonRepeatEnrollment, REPEAT_ENROLLMENT_ID)
    if repeat_enrollment is None:
        repeat_enrollment = PythonRepeatEnrollment(
            id=REPEAT_ENROLLMENT_ID,
            application_id=REPEAT_APPLICATION_ID,
            student_id=repeat_student.id,
            track_id=python_track_id,
            previous_track_id=python_track_id,
            mentor_id=mentor_id,
            mentor_assigned_at=now - timedelta(days=42),
            mentor_assigned_by_user_id=admin_id,
            status=PythonRepeatEnrollmentStatus.ACTIVE,
            started_at=now - timedelta(days=43),
            personal_plan_markdown="System Design, алгоритмы и два мок-собеседования.",
            terms_snapshot=enrollment_snapshot,
        )
        session.add(repeat_enrollment)
    else:
        repeat_enrollment.terms_snapshot = enrollment_snapshot
    if await session.get(MentorStudent, (mentor_id, repeat_student.id)) is None:
        session.add(MentorStudent(mentor_id=mentor_id, student_id=repeat_student.id))
    if await session.get(PythonRepeatEmploymentOffer, REPEAT_OFFER_ID) is None:
        session.add(
            PythonRepeatEmploymentOffer(
                id=REPEAT_OFFER_ID,
                enrollment_id=REPEAT_ENROLLMENT_ID,
                student_id=repeat_student.id,
                position="Senior Python Backend Developer",
                company="New Demo Company",
                technology_direction="Python Backend",
                fixed_monthly_salary_kopecks=25_000_000,
                currency="RUB",
                employment_type="Трудовой договор",
                received_at=now - timedelta(days=7),
                expected_start_date=now + timedelta(days=7),
                status=PythonRepeatOfferStatus.VERIFIED,
                submitted_at=now - timedelta(days=6),
                verified_at=now - timedelta(days=5),
                verified_by_user_id=admin_id,
                verification_comment="Демо-оффер подтверждён.",
            )
        )
    if await session.get(PythonRepeatSuccessFeeObligation, REPEAT_OBLIGATION_ID) is None:
        session.add(
            PythonRepeatSuccessFeeObligation(
                id=REPEAT_OBLIGATION_ID,
                enrollment_id=REPEAT_ENROLLMENT_ID,
                verified_offer_id=REPEAT_OFFER_ID,
                salary_base_kopecks=25_000_000,
                success_fee_percent=100,
                total_amount_kopecks=25_000_000,
                installments_count=4,
                status=PythonRepeatObligationStatus.ACTIVE,
                terms_snapshot=terms,
            )
        )
    for index, installment_id in enumerate(REPEAT_INSTALLMENT_IDS, start=1):
        if await session.get(PythonRepeatInstallment, installment_id) is None:
            paid = index == 1
            session.add(
                PythonRepeatInstallment(
                    id=installment_id,
                    obligation_id=REPEAT_OBLIGATION_ID,
                    sequence_number=index,
                    amount_kopecks=6_250_000,
                    salary_percent=25,
                    due_at=now + timedelta(days=30 * index),
                    status=(
                        PythonRepeatInstallmentStatus.PAID
                        if paid
                        else PythonRepeatInstallmentStatus.SCHEDULED
                    ),
                    paid_at=now - timedelta(days=1) if paid else None,
                    actual_received_kopecks=6_250_000 if paid else None,
                )
            )
    if await session.get(MentorReward, REPEAT_FIXED_REWARD_ID) is None:
        session.add(
            MentorReward(
                id=REPEAT_FIXED_REWARD_ID,
                python_repeat_enrollment_id=REPEAT_ENROLLMENT_ID,
                student_id=repeat_student.id,
                mentor_id=mentor_id,
                kind=MentorRewardKind.PYTHON_REPEAT_FIXED,
                basis_kopecks=3_000_000,
                amount_kopecks=1_000_000,
                paid_kopecks=0,
            )
        )
    if await session.get(MentorReward, REPEAT_VARIABLE_REWARD_ID) is None:
        session.add(
            MentorReward(
                id=REPEAT_VARIABLE_REWARD_ID,
                python_repeat_installment_id=REPEAT_INSTALLMENT_IDS[0],
                student_id=repeat_student.id,
                mentor_id=mentor_id,
                kind=MentorRewardKind.PYTHON_REPEAT_SUCCESS_FEE,
                reward_percent=Decimal("30"),
                basis_kopecks=6_250_000,
                amount_kopecks=1_875_000,
                paid_kopecks=0,
            )
        )
