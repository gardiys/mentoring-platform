from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import BigInteger, String, and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.errors import api_error
from app.opportunities.models import (
    ConsultationMentorSetting,
    ConsultationRequest,
    GoTransitionApplication,
    OpportunityPaymentAttempt,
    PythonRepeatApplication,
)
from app.opportunities.schemas import (
    AdminConsultationMentorRead,
    AdminOpportunityStudentRead,
)
from app.opportunities.service import (
    CONSULTATION_TYPES,
    _consultation_read,
    _consultation_types,
    _go_transition_description,
    _mentor_options,
    _mentor_read,
    _track_state,
    _transition_read,
)
from app.opportunities.stages import needs_action_sql, overdue_sql, stage_info, stage_rows
from app.opportunities.workspace_commands import go_payment_block_reason
from app.opportunities.workspace_models import (
    ConsultationRequestHistory,
    GoTransitionApplicationHistory,
)
from app.opportunities.workspace_schemas import (
    AdminConsultationDetail,
    AdminGoTransitionDetail,
    AdminPythonRepeatDetail,
    WorkspaceHistoryRead,
    WorkspaceItem,
    WorkspacePage,
    WorkspacePaymentRead,
    WorkspaceSettings,
)
from app.users.models import MENTOR_CAPABLE_ROLES, User

Product = Literal["consultations", "go_transition", "python_repeat"]
Group = Literal["active", "needs_action", "waiting", "completed", "cancelled", "all"]


def student_read(user: User) -> AdminOpportunityStudentRead:
    return AdminOpportunityStudentRead(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        telegram_username=user.telegram_username,
        email=user.email,
    )


async def workspace_page(
    session: AsyncSession,
    *,
    product: Product | None = None,
    q: str = "",
    group: Group = "active",
    stage: str | None = None,
    mentor_id: UUID | None = None,
    consultation_type: str | None = None,
    page: int = 1,
    page_size: int = 25,
    inbox: bool = False,
) -> WorkspacePage:
    at = datetime.now(UTC)
    rows = stage_rows(at)
    mentor = aliased(User)
    query = (
        select(
            rows,
            User,
            mentor,
            ConsultationRequest.consultation_type,
            case(
                (rows.c.product == "consultations", ConsultationRequest.price_kopecks),
                (rows.c.product == "go_transition", GoTransitionApplication.upfront_price_kopecks),
                else_=PythonRepeatApplication.terms_snapshot["upfront_price_kopecks"].astext.cast(
                    BigInteger
                ),
            ).label("amount"),
        )
        .join(User, User.id == rows.c.student_id)
        .outerjoin(
            ConsultationRequest,
            and_(rows.c.product == "consultations", ConsultationRequest.id == rows.c.id),
        )
    )
    query = (
        query.outerjoin(mentor, mentor.id == ConsultationRequest.mentor_id)
        .outerjoin(
            GoTransitionApplication,
            and_(rows.c.product == "go_transition", GoTransitionApplication.id == rows.c.id),
        )
        .outerjoin(
            PythonRepeatApplication,
            and_(rows.c.product == "python_repeat", PythonRepeatApplication.id == rows.c.id),
        )
    )
    if product:
        query = query.where(rows.c.product == product)
    if q.strip():
        term = f"%{q.strip().lstrip('@')}%"
        query = query.where(
            or_(
                User.first_name.ilike(term),
                User.last_name.ilike(term),
                User.telegram_username.ilike(term),
                User.email.ilike(term),
                rows.c.id.cast(String).ilike(term),
                func.concat(User.first_name, " ", User.last_name).ilike(term),
            )
        )
    if mentor_id:
        query = query.where(ConsultationRequest.mentor_id == mentor_id)
    if consultation_type:
        query = query.where(ConsultationRequest.consultation_type == consultation_type)
    terminal = rows.c.stage.in_(["completed", "cancelled", "closed", "enrolled"])
    if inbox or group == "needs_action":
        query = query.where(needs_action_sql(rows))
    elif group == "active":
        query = query.where(~terminal)
    elif group == "waiting":
        query = query.where(~needs_action_sql(rows), ~terminal)
    elif group == "completed":
        query = query.where(rows.c.stage.in_(["completed", "enrolled"]))
    elif group == "cancelled":
        query = query.where(rows.c.stage.in_(["cancelled", "closed"]))
    count_rows = query.with_only_columns(rows.c.stage, maintain_column_froms=True).subquery()
    counts = {
        stage: count
        for stage, count in await session.execute(
            select(count_rows.c.stage, func.count()).group_by(count_rows.c.stage)
        )
    }
    if stage:
        query = query.where(rows.c.stage == stage)
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    if inbox:
        query = query.order_by(
            overdue_sql(rows, at).desc(), rows.c.waiting_since.asc().nulls_last(), rows.c.id
        )
    else:
        query = query.order_by(rows.c.key_date.desc().nulls_last(), rows.c.id)
    data = (await session.execute(query.offset((page - 1) * page_size).limit(page_size))).all()
    titles = {str(item.code): item.title for item in CONSULTATION_TYPES}
    items = []
    for row in data:
        # Seven stage columns, then student, mentor, format and amount.
        (
            product_code,
            item_id,
            _student_id,
            status,
            stage_code,
            waiting,
            key_date,
            user,
            assigned,
            format_code,
            amount,
        ) = row
        info = stage_info(product_code, stage_code, waiting, at)
        title = (
            titles.get(str(format_code), "Консультация")
            if product_code == "consultations"
            else (
                "Переход Python → Go"
                if product_code == "go_transition"
                else "Повторное менторство по Python"
            )
        )
        action = info.next_action
        if stage_code in {"scheduled", "awaiting_student"} and key_date:
            action += f" · {key_date:%d.%m.%Y}"
        items.append(
            WorkspaceItem(
                product=product_code,
                id=item_id,
                student=student_read(user),
                title=title,
                status=status,
                key_date=key_date,
                amount_kopecks=amount,
                mentor=_mentor_read(assigned) if assigned else None,
                **{**asdict(info), "next_action": action},
            )
        )
    return WorkspacePage(items=items, total=total, counts=counts, page=page, page_size=page_size)


async def settings_read(session: AsyncSession) -> WorkspaceSettings:
    mentors = (
        await session.execute(
            select(User, ConsultationMentorSetting)
            .outerjoin(ConsultationMentorSetting, ConsultationMentorSetting.mentor_id == User.id)
            .where(User.is_active.is_(True), User.role.in_(MENTOR_CAPABLE_ROLES))
            .order_by(User.first_name, User.id)
        )
    ).all()
    return WorkspaceSettings(
        consultation_types=await _consultation_types(session),
        go_transition_description_markdown=await _go_transition_description(session),
        consultation_mentors=[
            AdminConsultationMentorRead(
                **_mentor_read(user).model_dump(),
                is_enabled=setting.is_enabled if setting else False,
            )
            for user, setting in mentors
        ],
    )


async def payment_read(
    session: AsyncSession, item: ConsultationRequest | GoTransitionApplication
) -> WorkspacePaymentRead | None:
    column = (
        OpportunityPaymentAttempt.consultation_request_id
        if isinstance(item, ConsultationRequest)
        else OpportunityPaymentAttempt.transition_application_id
    )
    payment = await session.scalar(
        select(OpportunityPaymentAttempt)
        .where(column == item.id)
        .order_by(
            (OpportunityPaymentAttempt.status == "manual_review").desc(),
            (OpportunityPaymentAttempt.status == "approved").desc(),
            OpportunityPaymentAttempt.created_at.desc(),
            OpportunityPaymentAttempt.id.desc(),
        )
        .limit(1)
    )
    return (
        WorkspacePaymentRead(
            attempt_id=payment.id, status=str(payment.status), created_at=payment.created_at
        )
        if payment
        else None
    )


async def history_read(
    session: AsyncSession, item: ConsultationRequest | GoTransitionApplication
) -> list[WorkspaceHistoryRead]:
    model: type[ConsultationRequestHistory] | type[GoTransitionApplicationHistory]
    if isinstance(item, ConsultationRequest):
        model, column = (
            ConsultationRequestHistory,
            ConsultationRequestHistory.consultation_request_id,
        )
    else:
        model, column = (
            GoTransitionApplicationHistory,
            GoTransitionApplicationHistory.application_id,
        )
    data = (
        await session.execute(
            select(model, User)
            .outerjoin(User, User.id == model.actor_user_id)
            .where(column == item.id)
            .order_by(model.created_at, model.id)
        )
    ).all()
    history = [
        WorkspaceHistoryRead(
            id=event.id,
            old_status=event.old_status,
            new_status=event.new_status,
            actor_user_id=event.actor_user_id,
            actor_name=" ".join(value for value in [actor.first_name, actor.last_name] if value)
            if actor
            else None,
            comment=event.comment,
            snapshot=event.snapshot,
            created_at=event.created_at,
        )
        for event, actor in data
    ]
    if not any(event.old_status is None for event in history):
        history.append(
            WorkspaceHistoryRead(
                new_status="requested" if isinstance(item, ConsultationRequest) else "submitted",
                comment="Заявка создана",
                created_at=item.created_at,
            )
        )
    for field, status, label in [
        ("paid_at", "paid", "Оплата подтверждена"),
        ("completed_at", "completed", "Консультация завершена"),
    ]:
        date = getattr(item, field, None)
        if date and not any(event.new_status == status for event in history):
            history.append(WorkspaceHistoryRead(new_status=status, comment=label, created_at=date))
    return sorted(history, key=lambda event: event.created_at)


async def consultation_detail(session: AsyncSession, resource_id: UUID) -> AdminConsultationDetail:
    mentor = aliased(User)
    record = (
        await session.execute(
            select(ConsultationRequest, User, mentor)
            .join(User, User.id == ConsultationRequest.student_id)
            .outerjoin(mentor, mentor.id == ConsultationRequest.mentor_id)
            .where(ConsultationRequest.id == resource_id)
        )
    ).one_or_none()
    if record is None:
        api_error(404, "consultation_not_found", "Консультация не найдена")
    item, student, _mentor = record
    payment = await payment_read(session, item)
    from app.opportunities.stages import consultation_stage

    info = consultation_stage(
        item,
        manual_review_at=payment.created_at
        if payment and payment.status == "manual_review"
        else None,
    )
    history = await history_read(session, item)
    initial = next((event for event in history if "requested_mentor_id" in event.snapshot), None)
    requested_mentor = None
    if initial and initial.snapshot["requested_mentor_id"]:
        requested_id = UUID(str(initial.snapshot["requested_mentor_id"]))
        requested_mentor = await session.get(User, requested_id)
    refunds = [
        event.snapshot.get("refund_required")
        for event in history
        if event.snapshot.get("action") == "cancel"
    ]
    base = await _consultation_read(session, item, include_draft_summary=True)
    tracks, _active = await _track_state(session, item.student_id)
    return AdminConsultationDetail(
        **base.model_dump(),
        available_mentors=await _mentor_options(session, tracks),
        requested_mentor=_mentor_read(requested_mentor) if requested_mentor else None,
        requested_mentor_known=initial is not None,
        **asdict(info),
        student=student_read(student),
        mentor_reward_kopecks=item.mentor_reward_kopecks,
        internal_note=item.internal_note,
        updated_at=item.updated_at,
        last_payment=payment,
        history=history,
        refund_required=refunds[-1] if refunds else None,
    )


async def go_detail(session: AsyncSession, resource_id: UUID) -> AdminGoTransitionDetail:
    record = (
        await session.execute(
            select(GoTransitionApplication, User)
            .join(User, User.id == GoTransitionApplication.student_id)
            .where(GoTransitionApplication.id == resource_id)
        )
    ).one_or_none()
    if record is None:
        api_error(404, "go_transition_not_found", "Заявка не найдена")
    item, student = record
    from app.opportunities.stages import go_transition_stage

    return AdminGoTransitionDetail(
        **_transition_read(item).model_dump(),
        **asdict(go_transition_stage(item)),
        student=student_read(student),
        internal_note=item.internal_note,
        updated_at=item.updated_at,
        last_payment=await payment_read(session, item),
        payment_block_reason=await go_payment_block_reason(session, item.id),
        history=await history_read(session, item),
    )


async def repeat_detail(session: AsyncSession, resource_id: UUID) -> AdminPythonRepeatDetail:
    from app.opportunities.python_repeat_service import admin_dashboard
    from app.opportunities.stages import python_repeat_stage

    result = await admin_dashboard(session, application_ids=[resource_id])
    if not result.applications:
        api_error(404, "python_repeat_not_found", "Заявка не найдена")
    base = result.applications[0]
    item = await session.get(PythonRepeatApplication, resource_id)
    assert item is not None
    from app.opportunities.models import PythonRepeatEnrollment

    enrollment = (
        await session.get(PythonRepeatEnrollment, base.enrollment.id) if base.enrollment else None
    )
    dates = [
        offer.submitted_at or offer.created_at
        for offer in base.offers
        if str(offer.status) == "submitted"
    ]
    info = python_repeat_stage(
        item, enrollment=enrollment, submitted_offer_at=min(dates) if dates else None
    )
    return AdminPythonRepeatDetail(**base.model_dump(), **asdict(info))
