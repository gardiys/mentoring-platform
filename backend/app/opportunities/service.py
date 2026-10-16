from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import api_error
from app.legal.catalog import financial_terms
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
    GoTransitionEnrollment,
    GoTransitionProgramSetting,
    GoTransitionStatus,
    OpportunityPaymentAttempt,
    ProgramCompletion,
    PythonRepeatProductOffer,
)
from app.opportunities.notifications import mark_payment_for_review, notify_admins
from app.opportunities.schemas import (
    AdminConsultationTypeMutation,
    AdminGoTransitionProgramMutation,
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
from app.opportunities.workspace_history import record_history
from app.opportunities.workspace_schemas import WorkspaceSettings
from app.payments.models import (
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
ALUMNI_GO_UPFRONT_PRICE_KOPECKS = financial_terms()["upfront_amount_minor"]
STANDARD_GO_UPFRONT_PRICE_KOPECKS = 4_500_000
ALUMNI_GO_SUCCESS_FEE_PERCENT = financial_terms()["success_fee_percent"]
STANDARD_GO_SUCCESS_FEE_PERCENT = 150
ACTIVE_TRANSITION_STATUSES = (
    GoTransitionStatus.SUBMITTED,
    GoTransitionStatus.APPROVED,
    GoTransitionStatus.PAYMENT_PENDING,
    GoTransitionStatus.PAID,
)
DEFAULT_CONSULTATION_DURATION_MINUTES = 60
GO_TRANSITION_TERMS_VERSION = 1
GO_TRANSITION_OFFER_VALID_DAYS = 14
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


def _go_transition_terms_snapshot() -> dict[str, object]:
    return {
        "product_code": "PYTHON_TO_GO_ALUMNI",
        "terms_version": GO_TRANSITION_TERMS_VERSION,
        "upfront_price_kopecks": ALUMNI_GO_UPFRONT_PRICE_KOPECKS,
        "success_fee_percent": ALUMNI_GO_SUCCESS_FEE_PERCENT,
        "comparison_upfront_price_kopecks": STANDARD_GO_UPFRONT_PRICE_KOPECKS,
        "comparison_success_fee_percent": STANDARD_GO_SUCCESS_FEE_PERCENT,
        "currency": "RUB",
    }


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


async def _consultation_read(
    session: AsyncSession, item: ConsultationRequest, *, include_draft_summary: bool = False
) -> ConsultationRead:
    mentor = await session.get(User, item.mentor_id) if item.mentor_id is not None else None
    if item.mentor_id is not None and mentor is None:
        raise RuntimeError("Consultation mentor was not found")
    return ConsultationRead(
        id=item.id,
        mentor=_mentor_read(mentor) if mentor is not None else None,
        consultation_type=item.consultation_type,
        brief=item.brief,
        price_kopecks=item.price_kopecks,
        duration_minutes=item.duration_minutes,
        status=item.status,
        scheduled_at=item.scheduled_at,
        paid_at=item.paid_at,
        completed_at=item.completed_at,
        admin_note=item.admin_note,
        written_summary=(
            item.written_summary
            if include_draft_summary or item.status is ConsultationStatus.COMPLETED
            else None
        ),
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
        terms_version=item.terms_version,
        terms_snapshot=item.terms_snapshot,
        terms_expires_at=item.terms_expires_at,
        accepted_terms_snapshot=item.accepted_terms_snapshot,
        created_at=item.created_at,
    )


async def opportunities_dashboard(session: AsyncSession, student: User) -> OpportunitiesDashboard:
    settings = get_settings()
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
    consultation_available = (
        settings.opportunities_enabled
        and settings.consultations_enabled
        and consultation_eligible
        and bool(consultation_mentors)
    )
    has_go = any(_is_go(track) for track in [*completed, *active])
    active_application = any(item.status in ACTIVE_TRANSITION_STATUSES for item in applications)
    overdue = await _student_has_overdue_obligations(session, student.id)
    consultation_types = await _consultation_types(session)
    transition_available = all(
        (
            settings.opportunities_enabled,
            settings.python_to_go_enabled,
            student.is_active,
            python_alumni,
            not has_go,
            not active_application,
            not overdue,
        )
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

    opportunity_items = (
        [
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
            )
        ]
        if settings.consultations_enabled and settings.opportunities_enabled
        else []
    )
    if settings.python_repeat_mentorship_enabled and settings.opportunities_enabled:
        # Imported lazily because the detailed product service reuses helpers from this module.
        from app.opportunities.python_repeat_service import python_repeat_eligibility

        repeat_eligibility = await python_repeat_eligibility(session, student)
        repeat_product = await session.scalar(
            select(PythonRepeatProductOffer)
            .where(PythonRepeatProductOffer.is_active.is_(True))
            .order_by(PythonRepeatProductOffer.version.desc())
            .limit(1)
        )
        if repeat_product is not None:
            opportunity_items.append(
                OpportunityRead(
                    code="PYTHON_REPEAT_MENTORSHIP",
                    available=repeat_eligibility.eligible,
                    title="Повторное менторство по Python",
                    unavailable_reason=(
                        None if repeat_eligibility.eligible else repeat_eligibility.message
                    ),
                    upfront_price_kopecks=repeat_product.upfront_price_kopecks,
                    success_fee_percent=repeat_product.success_fee_percent,
                )
            )
    if settings.python_to_go_enabled and settings.opportunities_enabled:
        opportunity_items.append(
            OpportunityRead(
                code="PYTHON_TO_GO_ALUMNI",
                available=transition_available,
                title="Переход Python → Go",
                unavailable_reason=transition_reason,
                upfront_price_kopecks=ALUMNI_GO_UPFRONT_PRICE_KOPECKS,
                success_fee_percent=ALUMNI_GO_SUCCESS_FEE_PERCENT,
                comparison_upfront_price_kopecks=STANDARD_GO_UPFRONT_PRICE_KOPECKS,
                comparison_success_fee_percent=STANDARD_GO_SUCCESS_FEE_PERCENT,
            )
        )

    return OpportunitiesDashboard(
        opportunities_enabled=settings.opportunities_enabled,
        consultations_enabled=settings.consultations_enabled,
        python_repeat_mentorship_enabled=settings.python_repeat_mentorship_enabled,
        python_to_go_enabled=settings.python_to_go_enabled,
        segment=segment,
        has_active_program=bool(active),
        has_alumni_access=bool(completed),
        opportunities=opportunity_items,
        mentors=consultation_mentors,
        consultation_types=consultation_types,
        go_transition_description_markdown=await _go_transition_description(session),
        consultations=[await _consultation_read(session, item) for item in consultations],
        go_transition_applications=[_transition_read(item) for item in applications],
    )


async def create_consultation(
    session: AsyncSession, student: User, payload: ConsultationCreate
) -> OpportunitiesDashboard:
    settings = get_settings()
    if not settings.opportunities_enabled or not settings.consultations_enabled:
        api_error(404, "consultations_disabled", "Consultations are disabled")
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
    item = ConsultationRequest(
        student_id=student.id,
        mentor_id=payload.mentor_id,
        consultation_type=payload.consultation_type,
        brief=payload.brief,
        price_kopecks=consultation_type.price_kopecks,
        mentor_reward_kopecks=consultation_type.mentor_reward_kopecks,
        duration_minutes=consultation_type.duration_minutes,
        status=ConsultationStatus.REQUESTED,
    )
    session.add(item)
    await session.flush()
    record_history(
        session,
        item,
        None,
        actor_id=student.id,
        snapshot={
            "requested_mentor_id": item.mentor_id,
            "consultation_type": str(item.consultation_type),
        },
    )
    identity = " ".join(
        value
        for value in [
            student.first_name,
            student.last_name,
            f"@{student.telegram_username}" if student.telegram_username else None,
        ]
        if value
    )
    mentor = await session.get(User, item.mentor_id) if item.mentor_id else None
    await notify_admins(
        session,
        event_key=f"consultation-requested:{item.id}",
        title="Новая заявка на консультацию",
        body=(
            f"{identity} · {consultation_type.title} · "
            f"ментор: {mentor.first_name if mentor else 'любой'}\n{item.brief[:300]}"
        ),
        link=f"/admin/opportunities?consultation={item.id}",
        actor_id=student.id,
    )
    await session.commit()
    return await opportunities_dashboard(session, student)


async def create_go_transition(
    session: AsyncSession, student: User, payload: GoTransitionCreate
) -> OpportunitiesDashboard:
    settings = get_settings()
    if not settings.opportunities_enabled or not settings.python_to_go_enabled:
        api_error(404, "python_to_go_disabled", "Python to Go transition is disabled")
    dashboard = await opportunities_dashboard(session, student)
    offer = next(item for item in dashboard.opportunities if item.code == "PYTHON_TO_GO_ALUMNI")
    if not offer.available:
        api_error(409, "go_transition_not_available", offer.unavailable_reason or "Unavailable")
    item = GoTransitionApplication(
        student_id=student.id,
        motivation=payload.motivation,
        status=GoTransitionStatus.SUBMITTED,
        upfront_price_kopecks=ALUMNI_GO_UPFRONT_PRICE_KOPECKS,
        success_fee_percent=ALUMNI_GO_SUCCESS_FEE_PERCENT,
        terms_version=GO_TRANSITION_TERMS_VERSION,
        terms_snapshot=_go_transition_terms_snapshot(),
    )
    session.add(item)
    try:
        await session.flush()
        record_history(session, item, None, actor_id=student.id)
        await notify_admins(
            session,
            event_key=f"go-transition-submitted:{item.id}",
            title="Новая заявка на переход в Go",
            body=f"{student.first_name} {student.last_name or ''}\n{item.motivation[:300]}",
            link=f"/admin/opportunities?go={item.id}",
            actor_id=student.id,
        )
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
    now = datetime.now(UTC)
    if item.terms_expires_at is not None and item.terms_expires_at < now:
        api_error(409, "go_transition_terms_expired", "The approved terms have expired")
    item.status = GoTransitionStatus.PAYMENT_PENDING
    item.terms_accepted_at = now
    item.accepted_terms_snapshot = dict(item.terms_snapshot)
    await session.commit()
    return await opportunities_dashboard(session, student)


async def _new_payment_link(
    session: AsyncSession,
    student: User,
    *,
    consultation: ConsultationRequest | None = None,
    transition: GoTransitionApplication | None = None,
) -> OpportunityPaymentLinkRead:
    if transition is not None:
        api_error(
            409,
            "legal_checkout_required",
            "Пройдите анкету и подтверждения на странице программы перед оплатой",
        )
    assert consultation is not None
    resource_id = consultation.id
    amount = consultation.price_kopecks
    statement = select(OpportunityPaymentAttempt).where(
        OpportunityPaymentAttempt.consultation_request_id == consultation.id,
        OpportunityPaymentAttempt.transition_application_id.is_(None),
    )
    attempts = list(await session.scalars(statement.order_by(OpportunityPaymentAttempt.created_at)))
    if any(item.status is PaymentAttemptStatus.MANUAL_REVIEW for item in attempts):
        api_error(409, "payment_requires_manual_review", "Payment requires administrator review")
    for item in attempts:
        if item.status is PaymentAttemptStatus.PENDING:
            item.status = PaymentAttemptStatus.REVOKED
            item.payment_url = None
    payment_link_id = f"opp_{resource_id.hex}_r{len(attempts) + 1}"
    if not student.email:
        api_error(
            422,
            "opportunity_payment_email_required",
            "Укажите email в профиле перед созданием платёжной ссылки.",
        )
    try:
        result = await TochkaPaymentService(get_settings()).create_payment_link(
            installment_id=resource_id,
            payment_link_id=payment_link_id,
            amount_kopecks=amount,
            client_name=" ".join(filter(None, (student.first_name, student.last_name))),
            client_email=student.email,
            return_path="/opportunities",
        )
    except TochkaError as error:
        api_error(502, "opportunity_payment_link_failed", str(error))
    if transition is not None:
        terms_snapshot = transition.accepted_terms_snapshot
    else:
        assert consultation is not None
        terms_snapshot = {
            "product_code": "ALUMNI_CONSULTATION",
            "price_kopecks": consultation.price_kopecks,
            "mentor_reward_kopecks": consultation.mentor_reward_kopecks,
            "duration_minutes": consultation.duration_minutes,
            "currency": "RUB",
        }
    session.add(
        OpportunityPaymentAttempt(
            consultation_request_id=consultation.id if consultation else None,
            transition_application_id=transition.id if transition else None,
            payment_link_id=result.payment_link_id,
            provider_operation_id=result.provider_operation_id,
            status=PaymentAttemptStatus.PENDING,
            payment_url=result.payment_url,
            terms_snapshot=terms_snapshot,
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


async def approve_opportunity_payment(
    session: AsyncSession,
    attempt: OpportunityPaymentAttempt,
    *,
    approved_at: datetime | None = None,
    verified_legal_payment: bool = False,
    provider_paid_at: datetime | None = None,
) -> None:
    now = approved_at or datetime.now(UTC)
    from app.legal.models import LegalCheckout
    from app.legal.service import finalize_contract

    legal_checkout = await session.scalar(
        select(LegalCheckout).where(LegalCheckout.payment_id == attempt.id)
    )
    if legal_checkout is not None:
        if not verified_legal_payment:
            api_error(
                409, "legal_payment_verification_required", "Требуется подтверждение платежа банком"
            )
        contract = await finalize_contract(
            session, attempt, provider_paid_at or now, now, provider_paid_at=provider_paid_at
        )
        if contract is None:
            return
    if attempt.status is PaymentAttemptStatus.APPROVED:
        return
    if attempt.status is PaymentAttemptStatus.REVOKED:
        await mark_payment_for_review(session, attempt)
        return
    if (
        attempt.python_repeat_application_id is not None
        or attempt.python_repeat_installment_id is not None
    ):
        from app.opportunities.python_repeat_service import approve_python_repeat_payment

        await approve_python_repeat_payment(session, attempt, approved_at=now)
        return
    attempt.status = PaymentAttemptStatus.APPROVED
    attempt.approved_at = now
    if attempt.consultation_request_id is not None:
        consultation = await session.scalar(
            select(ConsultationRequest)
            .where(ConsultationRequest.id == attempt.consultation_request_id)
            .with_for_update()
        )
        if consultation is None or consultation.status is not ConsultationStatus.PAYMENT_PENDING:
            await mark_payment_for_review(session, attempt)
            return
        if consultation.mentor_id is None:
            await mark_payment_for_review(session, attempt)
            return
        consultation.status = ConsultationStatus.PAID
        consultation.paid_at = now
        record_history(
            session,
            consultation,
            "payment_pending",
            snapshot={"action": "payment", "payment_attempt_id": attempt.id, "paid_at": now},
        )
        await notify_admins(
            session,
            event_key=f"consultation-paid:{consultation.id}",
            title="Консультация оплачена — согласуйте время",
            body=f"Заявка {consultation.id}",
            link=f"/admin/opportunities?consultation={consultation.id}",
        )
        return
    assert attempt.transition_application_id is not None
    transition = await session.scalar(
        select(GoTransitionApplication)
        .where(GoTransitionApplication.id == attempt.transition_application_id)
        .with_for_update()
    )
    if transition is None or transition.status is not GoTransitionStatus.PAYMENT_PENDING:
        await mark_payment_for_review(session, attempt)
        return
    go_track = await session.scalar(
        select(LearningTrack).where(
            LearningTrack.is_published.is_(True),
            func.lower(LearningTrack.slug) == "go",
        )
    )
    if go_track is None:
        await mark_payment_for_review(session, attempt)
        return
    completed_tracks, _active_tracks = await _track_state(session, transition.student_id)
    python_track = next((track for track in completed_tracks if _is_python(track)), None)
    if python_track is None or transition.accepted_terms_snapshot is None:
        await mark_payment_for_review(session, attempt)
        return
    transition.status = GoTransitionStatus.PAID
    transition.paid_at = now
    record_history(
        session,
        transition,
        "payment_pending",
        snapshot={"action": "payment", "payment_attempt_id": attempt.id, "paid_at": now},
    )
    enrollment = await session.get(
        LearningTrackEnrollment,
        {"user_id": transition.student_id, "track_id": go_track.id},
    )
    if enrollment is None:
        session.add(LearningTrackEnrollment(user_id=transition.student_id, track_id=go_track.id))
    source_enrollment = await session.scalar(
        select(GoTransitionEnrollment).where(GoTransitionEnrollment.application_id == transition.id)
    )
    if source_enrollment is None:
        session.add(
            GoTransitionEnrollment(
                application_id=transition.id,
                student_id=transition.student_id,
                track_id=go_track.id,
                previous_python_track_id=python_track.id,
                source="python_to_go",
                status="active",
                started_at=now,
                terms_snapshot=dict(transition.accepted_terms_snapshot),
            )
        )
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
        consultation = await session.scalar(
            select(ConsultationRequest)
            .where(ConsultationRequest.id == attempt.consultation_request_id)
            .with_for_update()
        )
        return (consultation.id, consultation.price_kopecks) if consultation is not None else None
    if attempt.transition_application_id is not None:
        transition = await session.scalar(
            select(GoTransitionApplication)
            .where(GoTransitionApplication.id == attempt.transition_application_id)
            .with_for_update()
        )
        return (transition.id, transition.upfront_price_kopecks) if transition is not None else None
    if attempt.python_repeat_application_id is not None:
        from app.opportunities.models import PythonRepeatApplication

        application = await session.get(
            PythonRepeatApplication, attempt.python_repeat_application_id
        )
        if application is None or application.terms_snapshot is None:
            return None
        amount = application.terms_snapshot.get("upfront_price_kopecks")
        if not isinstance(amount, int):
            return None
        return application.id, amount
    if attempt.python_repeat_installment_id is not None:
        from app.opportunities.models import PythonRepeatInstallment

        installment = await session.get(
            PythonRepeatInstallment, attempt.python_repeat_installment_id
        )
        return (installment.id, installment.amount_kopecks) if installment is not None else None
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
    elif attempt.python_repeat_application_id or attempt.python_repeat_installment_id:
        from app.opportunities.python_repeat_service import _attempt_owner

        owner_id = await _attempt_owner(session, attempt)
    if owner_id != student.id:
        api_error(404, "payment_attempt_not_found", "Payment attempt was not found")
    await approve_opportunity_payment(session, attempt, verified_legal_payment=True)
    await session.commit()
    return await opportunities_dashboard(session, student)


async def admin_update_consultation_type(
    session: AsyncSession,
    admin: User,
    consultation_type: ConsultationType,
    payload: AdminConsultationTypeMutation,
) -> WorkspaceSettings:
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
    from app.opportunities.workspace_reads import settings_read

    return await settings_read(session)


async def admin_update_go_transition_program(
    session: AsyncSession,
    admin: User,
    payload: AdminGoTransitionProgramMutation,
) -> WorkspaceSettings:
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
    from app.opportunities.workspace_reads import settings_read

    return await settings_read(session)


async def admin_set_consultation_mentor(
    session: AsyncSession,
    admin: User,
    mentor_id: UUID,
    *,
    is_enabled: bool,
) -> WorkspaceSettings:
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
    from app.opportunities.workspace_reads import settings_read

    return await settings_read(session)


async def admin_confirm_opportunity_payment(
    session: AsyncSession, attempt_id: UUID
) -> OpportunityPaymentAttempt:
    attempt = await session.scalar(
        select(OpportunityPaymentAttempt)
        .where(OpportunityPaymentAttempt.id == attempt_id)
        .with_for_update()
    )
    if attempt is None:
        api_error(404, "payment_attempt_not_found", "Payment attempt was not found")
    if attempt.status is not PaymentAttemptStatus.MANUAL_REVIEW:
        api_error(409, "payment_not_in_review", "Платёж не ожидает ручной проверки")
    await approve_opportunity_payment(session, attempt)
    if str(attempt.status) != PaymentAttemptStatus.APPROVED.value:
        api_error(
            409,
            "payment_review_unresolved",
            "Не удалось подтвердить оплату: проверьте состояние заявки и назначение ментора",
        )
    if attempt.consultation_request_id:
        await session.execute(
            update(OpportunityPaymentAttempt)
            .where(
                OpportunityPaymentAttempt.consultation_request_id
                == attempt.consultation_request_id,
                OpportunityPaymentAttempt.id != attempt.id,
                OpportunityPaymentAttempt.status == PaymentAttemptStatus.PENDING,
            )
            .values(status=PaymentAttemptStatus.REVOKED)
        )
    await session.commit()
    return attempt
