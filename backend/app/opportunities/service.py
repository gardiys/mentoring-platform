from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.config import get_settings
from app.core.errors import api_error
from app.mentors.models import (
    MentorStudent,
    MentorTrackAssignment,
    StudentLearningStatus,
    StudentMentorshipState,
)
from app.opportunities.models import (
    ConsultationMentorSetting,
    ConsultationRequest,
    ConsultationStatus,
    ConsultationType,
    ConsultationTypeSetting,
    GoTransitionApplication,
    GoTransitionProgramSetting,
    GoTransitionStatus,
    OpportunityPaymentAttempt,
    ProgramCompletion,
)
from app.opportunities.schemas import (
    AdminConsultationMentorRead,
    AdminConsultationMutation,
    AdminConsultationRead,
    AdminConsultationTypeMutation,
    AdminGoTransitionProgramMutation,
    AdminGoTransitionRead,
    AdminOpportunitiesDashboard,
    AdminOpportunityStudentRead,
    ConsultationCreate,
    ConsultationRead,
    ConsultationTypeRead,
    GoTransitionCreate,
    GoTransitionRead,
    MentorOptionRead,
    MoneyRead,
    OpportunitiesDashboard,
    OpportunityPaymentLinkRead,
    OpportunityRead,
    OpportunitySegment,
)
from app.payments.models import (
    MentorReward,
    MentorRewardKind,
    PaymentAttemptStatus,
    PaymentInstallment,
    PaymentInstallmentStatus,
)
from app.payments.tochka import TochkaError, TochkaPaymentService
from app.tracks.models import LearningTrack, LearningTrackEnrollment
from app.users.models import MENTOR_CAPABLE_ROLES, User, UserRole

REGULAR_ALUMNI_CONSULTATION_PRICE_KOPECKS = 400_000
REGULAR_STANDARD_CONSULTATION_PRICE_KOPECKS = 500_000
REGULAR_CONSULTATION_MENTOR_REWARD_KOPECKS = 250_000
PREMIUM_ALUMNI_CONSULTATION_PRICE_KOPECKS = 600_000
PREMIUM_STANDARD_CONSULTATION_PRICE_KOPECKS = 700_000
PREMIUM_CONSULTATION_MENTOR_REWARD_KOPECKS = 300_000
ALUMNI_GO_UPFRONT_PRICE_KOPECKS = 3_000_000
STANDARD_GO_UPFRONT_PRICE_KOPECKS = 4_500_000
ALUMNI_GO_SUCCESS_FEE_PERCENT = 100
STANDARD_GO_SUCCESS_FEE_PERCENT = 150
ACTIVE_TRANSITION_STATUSES = (
    GoTransitionStatus.SUBMITTED,
    GoTransitionStatus.APPROVED,
    GoTransitionStatus.PAYMENT_PENDING,
    GoTransitionStatus.PAID,
)
DEFAULT_CONSULTATION_DURATION_MINUTES = 60
DEFAULT_GO_TRANSITION_DESCRIPTION_MARKDOWN = """## Что входит в программу

- язык Go, его идиомы, типизация и работа с ошибками;
- goroutine, каналы, конкурентность и устройство runtime;
- разработка backend-сервисов, базы данных и production-практики;
- поддержка ментора, практика и подготовка к Go-собеседованиям;
- сопровождение до выхода на Go-оффер по условиям программы.
"""

CONSULTATION_TYPES = (
    ConsultationTypeRead(
        code=ConsultationType.FREE_TOPIC,
        title="Свободная тема",
        description=(
            "Разберите карьерный, технический или организационный вопрос, "
            "который не подходит под готовые форматы."
        ),
        price_kopecks=REGULAR_ALUMNI_CONSULTATION_PRICE_KOPECKS,
        comparison_price_kopecks=REGULAR_STANDARD_CONSULTATION_PRICE_KOPECKS,
        mentor_reward_kopecks=REGULAR_CONSULTATION_MENTOR_REWARD_KOPECKS,
        duration_minutes=DEFAULT_CONSULTATION_DURATION_MINUTES,
    ),
    ConsultationTypeRead(
        code=ConsultationType.TECHNICAL_MOCK,
        title="Техническое мок-собеседование",
        description=(
            "Репетиция технического интервью с вопросами по вашему направлению "
            "и подробной обратной связью."
        ),
        price_kopecks=REGULAR_ALUMNI_CONSULTATION_PRICE_KOPECKS,
        comparison_price_kopecks=REGULAR_STANDARD_CONSULTATION_PRICE_KOPECKS,
        mentor_reward_kopecks=REGULAR_CONSULTATION_MENTOR_REWARD_KOPECKS,
        duration_minutes=DEFAULT_CONSULTATION_DURATION_MINUTES,
    ),
    ConsultationTypeRead(
        code=ConsultationType.LEGEND_MOCK,
        title="Мок-собеседование по легенде",
        description=(
            "Проверьте, насколько убедительно вы рассказываете об опыте, проектах "
            "и своей роли в команде."
        ),
        price_kopecks=REGULAR_ALUMNI_CONSULTATION_PRICE_KOPECKS,
        comparison_price_kopecks=REGULAR_STANDARD_CONSULTATION_PRICE_KOPECKS,
        mentor_reward_kopecks=REGULAR_CONSULTATION_MENTOR_REWARD_KOPECKS,
        duration_minutes=DEFAULT_CONSULTATION_DURATION_MINUTES,
    ),
    ConsultationTypeRead(
        code=ConsultationType.RESUME_LEGEND,
        title="Составление резюме и легенды",
        description=(
            "Соберите понятное резюме и согласованную профессиональную историю "
            "для откликов и интервью."
        ),
        price_kopecks=PREMIUM_ALUMNI_CONSULTATION_PRICE_KOPECKS,
        comparison_price_kopecks=PREMIUM_STANDARD_CONSULTATION_PRICE_KOPECKS,
        mentor_reward_kopecks=PREMIUM_CONSULTATION_MENTOR_REWARD_KOPECKS,
        duration_minutes=DEFAULT_CONSULTATION_DURATION_MINUTES,
    ),
    ConsultationTypeRead(
        code=ConsultationType.SYSTEM_DESIGN_MOCK,
        title="Мок-собеседование по системному дизайну",
        description=(
            "Потренируйте декомпозицию требований, архитектуру, компромиссы "
            "и защиту выбранного решения."
        ),
        price_kopecks=PREMIUM_ALUMNI_CONSULTATION_PRICE_KOPECKS,
        comparison_price_kopecks=PREMIUM_STANDARD_CONSULTATION_PRICE_KOPECKS,
        mentor_reward_kopecks=PREMIUM_CONSULTATION_MENTOR_REWARD_KOPECKS,
        duration_minutes=DEFAULT_CONSULTATION_DURATION_MINUTES,
    ),
    ConsultationTypeRead(
        code=ConsultationType.WORK_TASK,
        title="Помощь с рабочей задачей",
        description=(
            "Разберите сложную задачу с работы и получите помощь с планом решения "
            "без передачи конфиденциальных данных."
        ),
        price_kopecks=PREMIUM_ALUMNI_CONSULTATION_PRICE_KOPECKS,
        comparison_price_kopecks=PREMIUM_STANDARD_CONSULTATION_PRICE_KOPECKS,
        mentor_reward_kopecks=PREMIUM_CONSULTATION_MENTOR_REWARD_KOPECKS,
        duration_minutes=DEFAULT_CONSULTATION_DURATION_MINUTES,
    ),
)


async def _consultation_types(session: AsyncSession) -> list[ConsultationTypeRead]:
    settings = {
        item.consultation_type: item
        for item in await session.scalars(select(ConsultationTypeSetting))
    }
    return [
        item.model_copy(
            update={
                "price_kopecks": setting.alumni_price_kopecks,
                "comparison_price_kopecks": setting.standard_price_kopecks,
                "mentor_reward_kopecks": setting.mentor_reward_kopecks,
                "duration_minutes": setting.duration_minutes,
            }
        )
        if (setting := settings.get(item.code)) is not None
        else item
        for item in CONSULTATION_TYPES
    ]


async def _go_transition_description(session: AsyncSession) -> str:
    setting = await session.get(GoTransitionProgramSetting, 1)
    return (
        setting.description_markdown
        if setting is not None
        else DEFAULT_GO_TRANSITION_DESCRIPTION_MARKDOWN
    )


def _is_python(track: LearningTrack) -> bool:
    value = f"{track.slug} {track.title}".casefold()
    return "python" in value or "питон" in value


def _is_go(track: LearningTrack) -> bool:
    value = f"{track.slug} {track.title}".casefold()
    return track.slug.casefold() == "go" or value.startswith("go ") or " golang" in value


async def record_current_track_completions(
    session: AsyncSession,
    *,
    student_id: UUID,
    recorded_by_user_id: UUID | None,
    completed_at: datetime,
) -> None:
    track_ids = list(
        await session.scalars(
            select(LearningTrackEnrollment.track_id).where(
                LearningTrackEnrollment.user_id == student_id
            )
        )
    )
    existing = set(
        await session.scalars(
            select(ProgramCompletion.track_id).where(ProgramCompletion.user_id == student_id)
        )
    )
    session.add_all(
        ProgramCompletion(
            user_id=student_id,
            track_id=track_id,
            completed_at=completed_at,
            recorded_by_user_id=recorded_by_user_id,
        )
        for track_id in track_ids
        if track_id not in existing
    )


async def _track_state(
    session: AsyncSession, user_id: UUID
) -> tuple[list[LearningTrack], list[LearningTrack]]:
    enrolled = list(
        await session.scalars(
            select(LearningTrack)
            .join(LearningTrackEnrollment, LearningTrackEnrollment.track_id == LearningTrack.id)
            .where(LearningTrackEnrollment.user_id == user_id)
        )
    )
    completed_ids = set(
        await session.scalars(
            select(ProgramCompletion.track_id).where(ProgramCompletion.user_id == user_id)
        )
    )
    return [track for track in enrolled if track.id in completed_ids], [
        track for track in enrolled if track.id not in completed_ids
    ]


async def _student_has_overdue_obligations(session: AsyncSession, user_id: UUID) -> bool:
    # This uses the platform's real employment schedule. If more types of debt
    # are introduced later, they should be added here rather than in UI code.
    from app.payments.models import StudentEmployment

    return (
        await session.scalar(
            select(PaymentInstallment.id)
            .join(StudentEmployment, StudentEmployment.id == PaymentInstallment.employment_id)
            .where(
                StudentEmployment.student_id == user_id,
                PaymentInstallment.status.in_(
                    [PaymentInstallmentStatus.SCHEDULED, PaymentInstallmentStatus.PENDING]
                ),
                PaymentInstallment.due_date < datetime.now(UTC).date(),
            )
            .limit(1)
        )
        is not None
    )


async def _mentor_options(
    session: AsyncSession, completed_tracks: list[LearningTrack]
) -> list[MentorOptionRead]:
    track_ids = [track.id for track in completed_tracks]
    statement = (
        select(User)
        .join(
            ConsultationMentorSetting,
            ConsultationMentorSetting.mentor_id == User.id,
        )
        .where(
            User.role.in_(MENTOR_CAPABLE_ROLES),
            User.is_active.is_(True),
            ConsultationMentorSetting.is_enabled.is_(True),
        )
    )
    if track_ids:
        statement = statement.outerjoin(
            MentorTrackAssignment, MentorTrackAssignment.mentor_id == User.id
        ).where(
            or_(
                User.role == UserRole.ADMIN,
                MentorTrackAssignment.track_id.in_(track_ids),
            )
        )
    mentors = list(
        await session.scalars(
            statement.distinct().order_by(User.first_name, User.last_name, User.id)
        )
    )
    return [_mentor_read(mentor) for mentor in mentors]


def _mentor_read(mentor: User) -> MentorOptionRead:
    return MentorOptionRead(
        id=mentor.id,
        first_name=mentor.first_name,
        last_name=mentor.last_name,
        telegram_username=mentor.telegram_username,
    )


async def _consultation_read(session: AsyncSession, item: ConsultationRequest) -> ConsultationRead:
    mentor = await session.get(User, item.mentor_id) if item.mentor_id is not None else None
    if item.mentor_id is not None and mentor is None:
        raise RuntimeError("Consultation mentor was not found")
    return ConsultationRead(
        id=item.id,
        mentor=_mentor_read(mentor) if mentor is not None else None,
        consultation_type=item.consultation_type,
        brief=item.brief,
        price_kopecks=item.price_kopecks,
        mentor_reward_kopecks=item.mentor_reward_kopecks,
        duration_minutes=item.duration_minutes,
        status=item.status,
        scheduled_at=item.scheduled_at,
        paid_at=item.paid_at,
        completed_at=item.completed_at,
        admin_note=item.admin_note,
        written_summary=item.written_summary,
        created_at=item.created_at,
    )


def _transition_read(item: GoTransitionApplication) -> GoTransitionRead:
    return GoTransitionRead(
        id=item.id,
        motivation=item.motivation,
        status=item.status,
        upfront_price_kopecks=item.upfront_price_kopecks,
        success_fee_percent=item.success_fee_percent,
        approved_at=item.approved_at,
        terms_accepted_at=item.terms_accepted_at,
        paid_at=item.paid_at,
        admin_note=item.admin_note,
        created_at=item.created_at,
    )


async def opportunities_dashboard(session: AsyncSession, student: User) -> OpportunitiesDashboard:
    completed, active = await _track_state(session, student.id)
    python_alumni = any(_is_python(track) for track in completed)
    go_alumni = any(_is_go(track) for track in completed)
    if active:
        segment = OpportunitySegment.ACTIVE_STUDENT
    elif python_alumni and go_alumni:
        segment = OpportunitySegment.MULTI_ALUMNI
    elif python_alumni:
        segment = OpportunitySegment.PYTHON_ALUMNI
    elif go_alumni:
        segment = OpportunitySegment.GO_ALUMNI
    else:
        segment = OpportunitySegment.OTHER

    consultations = list(
        await session.scalars(
            select(ConsultationRequest)
            .where(ConsultationRequest.student_id == student.id)
            .order_by(ConsultationRequest.created_at.desc())
        )
    )
    applications = list(
        await session.scalars(
            select(GoTransitionApplication)
            .where(GoTransitionApplication.student_id == student.id)
            .order_by(GoTransitionApplication.created_at.desc())
        )
    )
    consultation_eligible = student.is_active and bool(completed) and not active
    consultation_mentors = (
        await _mentor_options(session, completed) if consultation_eligible else []
    )
    consultation_available = consultation_eligible and bool(consultation_mentors)
    has_go = any(_is_go(track) for track in [*completed, *active])
    active_application = any(item.status in ACTIVE_TRANSITION_STATUSES for item in applications)
    overdue = await _student_has_overdue_obligations(session, student.id)
    consultation_types = await _consultation_types(session)
    transition_available = all(
        (student.is_active, python_alumni, not has_go, not active_application, not overdue)
    )
    transition_reason = None
    if not student.is_active:
        transition_reason = "Доступ к аккаунту закрыт"
    elif not python_alumni:
        transition_reason = "Предложение доступно после завершения Python-направления"
    elif has_go:
        transition_reason = "Go-направление уже добавлено в ваш профиль"
    elif active_application:
        transition_reason = "У вас уже есть заявка на переход в Go"
    elif overdue:
        transition_reason = "Сначала погасите просроченные обязательства"

    return OpportunitiesDashboard(
        segment=segment,
        has_active_program=bool(active),
        has_alumni_access=bool(completed),
        opportunities=[
            OpportunityRead(
                code="ALUMNI_CONSULTATION",
                available=consultation_available,
                title="Консультация с ментором",
                unavailable_reason=(
                    None
                    if consultation_available
                    else (
                        "Сейчас нет доступных менторов для консультации"
                        if consultation_eligible
                        else "Платная консультация доступна выпускникам без активной программы"
                    )
                ),
                price=MoneyRead(
                    amount_kopecks=min(item.price_kopecks for item in consultation_types)
                ),
                comparison_price=MoneyRead(
                    amount_kopecks=min(item.comparison_price_kopecks for item in consultation_types)
                ),
            ),
            OpportunityRead(
                code="PYTHON_TO_GO_ALUMNI",
                available=transition_available,
                title="Переход Python → Go",
                unavailable_reason=transition_reason,
                upfront_price_kopecks=ALUMNI_GO_UPFRONT_PRICE_KOPECKS,
                success_fee_percent=ALUMNI_GO_SUCCESS_FEE_PERCENT,
                comparison_upfront_price_kopecks=STANDARD_GO_UPFRONT_PRICE_KOPECKS,
                comparison_success_fee_percent=STANDARD_GO_SUCCESS_FEE_PERCENT,
            ),
        ],
        mentors=consultation_mentors,
        consultation_types=consultation_types,
        go_transition_description_markdown=await _go_transition_description(session),
        consultations=[await _consultation_read(session, item) for item in consultations],
        go_transition_applications=[_transition_read(item) for item in applications],
    )


async def create_consultation(
    session: AsyncSession, student: User, payload: ConsultationCreate
) -> OpportunitiesDashboard:
    dashboard = await opportunities_dashboard(session, student)
    offer = next(item for item in dashboard.opportunities if item.code == "ALUMNI_CONSULTATION")
    if not offer.available:
        api_error(409, "consultation_not_available", offer.unavailable_reason or "Unavailable")
    if payload.mentor_id is not None and payload.mentor_id not in {
        mentor.id for mentor in dashboard.mentors
    }:
        api_error(422, "mentor_not_available", "Selected mentor is not available for this offer")
    consultation_type = next(
        item for item in dashboard.consultation_types if item.code == payload.consultation_type
    )
    session.add(
        ConsultationRequest(
            student_id=student.id,
            mentor_id=payload.mentor_id,
            consultation_type=payload.consultation_type,
            brief=payload.brief,
            price_kopecks=consultation_type.price_kopecks,
            mentor_reward_kopecks=consultation_type.mentor_reward_kopecks,
            duration_minutes=consultation_type.duration_minutes,
            status=ConsultationStatus.REQUESTED,
        )
    )
    await session.commit()
    return await opportunities_dashboard(session, student)


async def create_go_transition(
    session: AsyncSession, student: User, payload: GoTransitionCreate
) -> OpportunitiesDashboard:
    dashboard = await opportunities_dashboard(session, student)
    offer = next(item for item in dashboard.opportunities if item.code == "PYTHON_TO_GO_ALUMNI")
    if not offer.available:
        api_error(409, "go_transition_not_available", offer.unavailable_reason or "Unavailable")
    session.add(
        GoTransitionApplication(
            student_id=student.id,
            motivation=payload.motivation,
            status=GoTransitionStatus.SUBMITTED,
            upfront_price_kopecks=ALUMNI_GO_UPFRONT_PRICE_KOPECKS,
            success_fee_percent=ALUMNI_GO_SUCCESS_FEE_PERCENT,
        )
    )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        api_error(
            409,
            "go_transition_already_exists",
            "An active Go transition application already exists",
        )
    return await opportunities_dashboard(session, student)


async def accept_go_transition(
    session: AsyncSession, student: User, application_id: UUID
) -> OpportunitiesDashboard:
    item = await session.scalar(
        select(GoTransitionApplication)
        .where(
            GoTransitionApplication.id == application_id,
            GoTransitionApplication.student_id == student.id,
        )
        .with_for_update()
    )
    if item is None:
        api_error(404, "go_transition_not_found", "Application was not found")
    if item.status is not GoTransitionStatus.APPROVED:
        api_error(409, "go_transition_not_approved", "The application is not ready for acceptance")
    item.status = GoTransitionStatus.PAYMENT_PENDING
    item.terms_accepted_at = datetime.now(UTC)
    await session.commit()
    return await opportunities_dashboard(session, student)


async def _new_payment_link(
    session: AsyncSession,
    student: User,
    *,
    consultation: ConsultationRequest | None = None,
    transition: GoTransitionApplication | None = None,
) -> OpportunityPaymentLinkRead:
    resource_id = consultation.id if consultation is not None else transition.id  # type: ignore[union-attr]
    amount = (
        consultation.price_kopecks if consultation is not None else transition.upfront_price_kopecks  # type: ignore[union-attr]
    )
    statement = select(OpportunityPaymentAttempt).where(
        OpportunityPaymentAttempt.consultation_request_id
        == (consultation.id if consultation else None),
        OpportunityPaymentAttempt.transition_application_id
        == (transition.id if transition else None),
    )
    attempts = list(await session.scalars(statement.order_by(OpportunityPaymentAttempt.created_at)))
    if any(item.status is PaymentAttemptStatus.MANUAL_REVIEW for item in attempts):
        api_error(409, "payment_requires_manual_review", "Payment requires administrator review")
    for item in attempts:
        if item.status is PaymentAttemptStatus.PENDING:
            item.status = PaymentAttemptStatus.REVOKED
            item.payment_url = None
    payment_link_id = f"opp_{resource_id.hex}_r{len(attempts) + 1}"
    try:
        result = await TochkaPaymentService(get_settings()).create_payment_link(
            installment_id=resource_id,
            payment_link_id=payment_link_id,
            amount_kopecks=amount,
            client_name=" ".join(filter(None, (student.first_name, student.last_name))),
            client_email=student.email or "",
            return_path="/opportunities",
        )
    except TochkaError as error:
        api_error(502, "opportunity_payment_link_failed", str(error))
    session.add(
        OpportunityPaymentAttempt(
            consultation_request_id=consultation.id if consultation else None,
            transition_application_id=transition.id if transition else None,
            payment_link_id=result.payment_link_id,
            provider_operation_id=result.provider_operation_id,
            status=PaymentAttemptStatus.PENDING,
            payment_url=result.payment_url,
            raw_create_response=result.raw_response,
        )
    )
    await session.commit()
    return OpportunityPaymentLinkRead(
        payment_url=result.payment_url,
        payment_link_id=result.payment_link_id,
    )


async def consultation_payment_link(
    session: AsyncSession, student: User, request_id: UUID
) -> OpportunityPaymentLinkRead:
    item = await session.scalar(
        select(ConsultationRequest)
        .where(ConsultationRequest.id == request_id, ConsultationRequest.student_id == student.id)
        .with_for_update()
    )
    if item is None:
        api_error(404, "consultation_not_found", "Consultation was not found")
    if item.status is not ConsultationStatus.PAYMENT_PENDING:
        api_error(409, "consultation_not_payable", "Consultation is not ready for payment")
    return await _new_payment_link(session, student, consultation=item)


async def transition_payment_link(
    session: AsyncSession, student: User, application_id: UUID
) -> OpportunityPaymentLinkRead:
    item = await session.scalar(
        select(GoTransitionApplication)
        .where(
            GoTransitionApplication.id == application_id,
            GoTransitionApplication.student_id == student.id,
        )
        .with_for_update()
    )
    if item is None:
        api_error(404, "go_transition_not_found", "Application was not found")
    if item.status is not GoTransitionStatus.PAYMENT_PENDING:
        api_error(409, "go_transition_not_payable", "Application is not ready for payment")
    return await _new_payment_link(session, student, transition=item)


async def approve_opportunity_payment(
    session: AsyncSession,
    attempt: OpportunityPaymentAttempt,
    *,
    approved_at: datetime | None = None,
) -> None:
    now = approved_at or datetime.now(UTC)
    if attempt.status is PaymentAttemptStatus.APPROVED:
        return
    if attempt.status is PaymentAttemptStatus.REVOKED:
        attempt.status = PaymentAttemptStatus.MANUAL_REVIEW
        return
    attempt.status = PaymentAttemptStatus.APPROVED
    attempt.approved_at = now
    if attempt.consultation_request_id is not None:
        consultation = await session.get(ConsultationRequest, attempt.consultation_request_id)
        if consultation is None or consultation.status is not ConsultationStatus.PAYMENT_PENDING:
            attempt.status = PaymentAttemptStatus.MANUAL_REVIEW
            return
        if consultation.mentor_id is None:
            attempt.status = PaymentAttemptStatus.MANUAL_REVIEW
            return
        consultation.status = ConsultationStatus.PAID
        consultation.paid_at = now
        existing_reward = await session.scalar(
            select(MentorReward.id).where(MentorReward.consultation_request_id == consultation.id)
        )
        if existing_reward is None:
            session.add(
                MentorReward(
                    consultation_request_id=consultation.id,
                    student_id=consultation.student_id,
                    mentor_id=consultation.mentor_id,
                    kind=MentorRewardKind.CONSULTATION,
                    basis_kopecks=consultation.price_kopecks,
                    amount_kopecks=consultation.mentor_reward_kopecks,
                    paid_kopecks=0,
                )
            )
        return
    assert attempt.transition_application_id is not None
    transition = await session.get(GoTransitionApplication, attempt.transition_application_id)
    if transition is None or transition.status is not GoTransitionStatus.PAYMENT_PENDING:
        attempt.status = PaymentAttemptStatus.MANUAL_REVIEW
        return
    go_track = await session.scalar(
        select(LearningTrack).where(
            LearningTrack.is_published.is_(True),
            func.lower(LearningTrack.slug) == "go",
        )
    )
    if go_track is None:
        attempt.status = PaymentAttemptStatus.MANUAL_REVIEW
        return
    transition.status = GoTransitionStatus.PAID
    transition.paid_at = now
    enrollment = await session.get(
        LearningTrackEnrollment,
        {"user_id": transition.student_id, "track_id": go_track.id},
    )
    if enrollment is None:
        session.add(LearningTrackEnrollment(user_id=transition.student_id, track_id=go_track.id))
    student = await session.get(User, transition.student_id)
    if student is not None:
        student.repayment_percent = Decimal(transition.success_fee_percent)
        student.entry_payment_kopecks = transition.upfront_price_kopecks
        student.entry_payment_paid_at = now
    state = await session.get(StudentMentorshipState, transition.student_id)
    if state is not None:
        state.learning_status = StudentLearningStatus.LEARNING
        state.status_updated_at = now
    relation = await session.scalar(
        select(MentorStudent).where(MentorStudent.student_id == transition.student_id)
    )
    if relation is not None:
        relation.learning_status = StudentLearningStatus.LEARNING
        relation.status_updated_at = now


async def opportunity_payment_context(
    session: AsyncSession, attempt: OpportunityPaymentAttempt
) -> tuple[UUID, int] | None:
    if attempt.consultation_request_id is not None:
        consultation = await session.get(ConsultationRequest, attempt.consultation_request_id)
        return (consultation.id, consultation.price_kopecks) if consultation is not None else None
    if attempt.transition_application_id is not None:
        transition = await session.get(GoTransitionApplication, attempt.transition_application_id)
        return (transition.id, transition.upfront_price_kopecks) if transition is not None else None
    return None


async def development_complete_payment(
    session: AsyncSession, student: User, payment_link_id: str
) -> OpportunitiesDashboard:
    if get_settings().app_env != "development":
        api_error(404, "not_found", "Resource was not found")
    attempt = await session.scalar(
        select(OpportunityPaymentAttempt)
        .where(OpportunityPaymentAttempt.payment_link_id == payment_link_id)
        .with_for_update()
    )
    if attempt is None:
        api_error(404, "payment_attempt_not_found", "Payment attempt was not found")
    owner_id = None
    if attempt.consultation_request_id:
        owner_id = await session.scalar(
            select(ConsultationRequest.student_id).where(
                ConsultationRequest.id == attempt.consultation_request_id
            )
        )
    elif attempt.transition_application_id:
        owner_id = await session.scalar(
            select(GoTransitionApplication.student_id).where(
                GoTransitionApplication.id == attempt.transition_application_id
            )
        )
    if owner_id != student.id:
        api_error(404, "payment_attempt_not_found", "Payment attempt was not found")
    await approve_opportunity_payment(session, attempt)
    await session.commit()
    return await opportunities_dashboard(session, student)


async def admin_dashboard(session: AsyncSession) -> AdminOpportunitiesDashboard:
    mentor_rows = (
        await session.execute(
            select(User, ConsultationMentorSetting)
            .outerjoin(
                ConsultationMentorSetting,
                ConsultationMentorSetting.mentor_id == User.id,
            )
            .where(User.role.in_(MENTOR_CAPABLE_ROLES), User.is_active.is_(True))
            .order_by(User.first_name, User.last_name, User.id)
        )
    ).all()
    students = aliased(User)
    consultation_rows = (
        await session.execute(
            select(ConsultationRequest, students)
            .join(students, students.id == ConsultationRequest.student_id)
            .order_by(ConsultationRequest.created_at.desc())
            .limit(200)
        )
    ).all()
    transition_rows = (
        await session.execute(
            select(GoTransitionApplication, students)
            .join(students, students.id == GoTransitionApplication.student_id)
            .order_by(GoTransitionApplication.created_at.desc())
            .limit(200)
        )
    ).all()

    def student_read(student: User) -> AdminOpportunityStudentRead:
        return AdminOpportunityStudentRead(
            id=student.id,
            first_name=student.first_name,
            last_name=student.last_name,
            telegram_username=student.telegram_username,
            email=student.email,
        )

    consultations: list[AdminConsultationRead] = []
    for item, student in consultation_rows:
        base = await _consultation_read(session, item)
        consultations.append(
            AdminConsultationRead(**base.model_dump(), student=student_read(student))
        )
    return AdminOpportunitiesDashboard(
        consultation_types=await _consultation_types(session),
        go_transition_description_markdown=await _go_transition_description(session),
        consultation_mentors=[
            AdminConsultationMentorRead(
                **_mentor_read(mentor).model_dump(),
                is_enabled=setting.is_enabled if setting is not None else False,
            )
            for mentor, setting in mentor_rows
        ],
        consultations=consultations,
        go_transition_applications=[
            AdminGoTransitionRead(
                **_transition_read(item).model_dump(), student=student_read(student)
            )
            for item, student in transition_rows
        ],
    )


async def admin_update_consultation_type(
    session: AsyncSession,
    admin: User,
    consultation_type: ConsultationType,
    payload: AdminConsultationTypeMutation,
) -> AdminOpportunitiesDashboard:
    setting = await session.get(ConsultationTypeSetting, consultation_type)
    if setting is None:
        setting = ConsultationTypeSetting(
            consultation_type=consultation_type,
            alumni_price_kopecks=payload.price_kopecks,
            standard_price_kopecks=payload.comparison_price_kopecks,
            mentor_reward_kopecks=payload.mentor_reward_kopecks,
            duration_minutes=payload.duration_minutes,
            updated_by_user_id=admin.id,
        )
        session.add(setting)
    else:
        setting.alumni_price_kopecks = payload.price_kopecks
        setting.standard_price_kopecks = payload.comparison_price_kopecks
        setting.mentor_reward_kopecks = payload.mentor_reward_kopecks
        setting.duration_minutes = payload.duration_minutes
        setting.updated_by_user_id = admin.id
    await session.commit()
    return await admin_dashboard(session)


async def admin_update_go_transition_program(
    session: AsyncSession,
    admin: User,
    payload: AdminGoTransitionProgramMutation,
) -> AdminOpportunitiesDashboard:
    setting = await session.get(GoTransitionProgramSetting, 1)
    if setting is None:
        setting = GoTransitionProgramSetting(
            id=1,
            description_markdown=payload.description_markdown,
            updated_by_user_id=admin.id,
        )
        session.add(setting)
    else:
        setting.description_markdown = payload.description_markdown
        setting.updated_by_user_id = admin.id
    await session.commit()
    return await admin_dashboard(session)


async def admin_set_consultation_mentor(
    session: AsyncSession,
    admin: User,
    mentor_id: UUID,
    *,
    is_enabled: bool,
) -> AdminOpportunitiesDashboard:
    mentor = await session.get(User, mentor_id)
    if mentor is None or mentor.role not in MENTOR_CAPABLE_ROLES:
        api_error(404, "mentor_not_found", "Mentor was not found")
    if is_enabled and not mentor.is_active:
        api_error(409, "mentor_inactive", "Inactive mentor cannot accept consultations")
    setting = await session.get(ConsultationMentorSetting, mentor_id)
    if setting is None:
        setting = ConsultationMentorSetting(
            mentor_id=mentor_id,
            is_enabled=is_enabled,
            updated_by_user_id=admin.id,
        )
        session.add(setting)
    else:
        setting.is_enabled = is_enabled
        setting.updated_by_user_id = admin.id
    await session.commit()
    return await admin_dashboard(session)


async def admin_update_consultation(
    session: AsyncSession,
    request_id: UUID,
    payload: AdminConsultationMutation,
) -> AdminOpportunitiesDashboard:
    item = await session.scalar(
        select(ConsultationRequest).where(ConsultationRequest.id == request_id).with_for_update()
    )
    if item is None:
        api_error(404, "consultation_not_found", "Consultation was not found")
    allowed = {
        ConsultationStatus.REQUESTED: {
            ConsultationStatus.PAYMENT_PENDING,
            ConsultationStatus.CANCELLED,
        },
        ConsultationStatus.PAYMENT_PENDING: {ConsultationStatus.CANCELLED},
        ConsultationStatus.PAID: {
            ConsultationStatus.SCHEDULED,
            ConsultationStatus.COMPLETED,
        },
        ConsultationStatus.SCHEDULED: {
            ConsultationStatus.SCHEDULED,
            ConsultationStatus.COMPLETED,
        },
        ConsultationStatus.COMPLETED: {ConsultationStatus.COMPLETED},
        ConsultationStatus.CANCELLED: {ConsultationStatus.CANCELLED},
    }
    if payload.status is not item.status and payload.status not in allowed[item.status]:
        api_error(409, "invalid_consultation_transition", "Status transition is not allowed")
    if item.status is ConsultationStatus.REQUESTED:
        item.mentor_id = payload.mentor_id
    elif payload.mentor_id != item.mentor_id:
        api_error(409, "consultation_mentor_locked", "Mentor is locked after approval")
    if payload.status is ConsultationStatus.PAYMENT_PENDING:
        if item.mentor_id is None:
            api_error(422, "consultation_mentor_required", "Assign a mentor before approval")
        completed_tracks, _active_tracks = await _track_state(session, item.student_id)
        available_mentor_ids = {
            mentor.id for mentor in await _mentor_options(session, completed_tracks)
        }
        if item.mentor_id not in available_mentor_ids:
            api_error(
                422,
                "consultation_mentor_not_available",
                "Selected mentor is not available for this consultation",
            )
    item.status = payload.status
    item.scheduled_at = payload.scheduled_at
    item.admin_note = payload.admin_note
    item.written_summary = payload.written_summary
    if payload.status is ConsultationStatus.COMPLETED:
        item.completed_at = item.completed_at or datetime.now(UTC)
    await session.commit()
    return await admin_dashboard(session)


async def admin_decide_transition(
    session: AsyncSession,
    admin: User,
    application_id: UUID,
    *,
    approved: bool,
    admin_note: str | None,
) -> AdminOpportunitiesDashboard:
    item = await session.scalar(
        select(GoTransitionApplication)
        .where(GoTransitionApplication.id == application_id)
        .with_for_update()
    )
    if item is None:
        api_error(404, "go_transition_not_found", "Application was not found")
    if item.status is not GoTransitionStatus.SUBMITTED:
        api_error(409, "go_transition_already_decided", "Application was already processed")
    item.status = GoTransitionStatus.APPROVED if approved else GoTransitionStatus.REJECTED
    item.admin_note = admin_note
    if approved:
        item.approved_at = datetime.now(UTC)
        item.approved_by_user_id = admin.id
    await session.commit()
    return await admin_dashboard(session)


async def admin_confirm_opportunity_payment(
    session: AsyncSession, attempt_id: UUID
) -> AdminOpportunitiesDashboard:
    attempt = await session.scalar(
        select(OpportunityPaymentAttempt)
        .where(OpportunityPaymentAttempt.id == attempt_id)
        .with_for_update()
    )
    if attempt is None:
        api_error(404, "payment_attempt_not_found", "Payment attempt was not found")
    await approve_opportunity_payment(session, attempt)
    await session.commit()
    return await admin_dashboard(session)
