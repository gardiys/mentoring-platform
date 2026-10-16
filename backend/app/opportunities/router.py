from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AdminUser, CurrentUser, StudentUser
from app.core.errors import api_error
from app.db.session import get_db_session
from app.legal.schemas import CheckoutConfirmation
from app.legal.service import checkout_payment_link
from app.opportunities.models import (
    ConsultationType,
    PythonRepeatEnrollment,
    PythonRepeatInstallment,
    PythonRepeatSuccessFeeObligation,
)
from app.opportunities.notifications import opportunity_summary
from app.opportunities.schemas import (
    AdminConsultationMentorMutation,
    AdminConsultationTypeMutation,
    AdminGoTransitionProgramMutation,
    ConsultationCreate,
    GoTransitionCreate,
    GoTransitionTermsAcceptance,
    OpportunitiesDashboard,
    OpportunityPaymentLinkRead,
)
from app.opportunities.service import (
    accept_go_transition,
    admin_confirm_opportunity_payment,
    admin_set_consultation_mentor,
    admin_update_consultation_type,
    admin_update_go_transition_program,
    consultation_payment_link,
    create_consultation,
    create_go_transition,
    development_complete_payment,
    opportunities_dashboard,
)
from app.opportunities.workspace_reads import consultation_detail, go_detail, repeat_detail
from app.opportunities.workspace_schemas import (
    AdminConsultationDetail,
    AdminGoTransitionDetail,
    AdminPythonRepeatDetail,
    OpportunitySummary,
    WorkspaceSettings,
)

Session = Annotated[AsyncSession, Depends(get_db_session)]
router = APIRouter(prefix="/opportunities", tags=["opportunities"])
admin_router = APIRouter(prefix="/admin/opportunities", tags=["admin-opportunities"])


@admin_router.get("/summary", response_model=OpportunitySummary)
async def summary(session: Session, _admin: AdminUser) -> OpportunitySummary:
    return await opportunity_summary(session)


@router.get("/me", response_model=OpportunitiesDashboard)
async def my_opportunities(session: Session, user: CurrentUser) -> OpportunitiesDashboard:
    return await opportunities_dashboard(session, user)


@router.post("/consultations", response_model=OpportunitiesDashboard)
async def request_consultation(
    payload: ConsultationCreate, session: Session, student: StudentUser
) -> OpportunitiesDashboard:
    return await create_consultation(session, student, payload)


@router.post(
    "/consultations/{request_id}/payment-link",
    response_model=OpportunityPaymentLinkRead,
)
async def consultation_link(
    request_id: UUID, session: Session, student: StudentUser
) -> OpportunityPaymentLinkRead:
    return await consultation_payment_link(session, student, request_id)


@router.post("/go-transition", response_model=OpportunitiesDashboard)
async def request_go_transition(
    payload: GoTransitionCreate, session: Session, student: StudentUser
) -> OpportunitiesDashboard:
    return await create_go_transition(session, student, payload)


@router.post(
    "/go-transition/{application_id}/accept",
    response_model=OpportunitiesDashboard,
)
async def accept_transition(
    application_id: UUID,
    _payload: GoTransitionTermsAcceptance,
    session: Session,
    student: StudentUser,
) -> OpportunitiesDashboard:
    return await accept_go_transition(session, student, application_id)


@router.post(
    "/go-transition/{application_id}/payment-link",
    response_model=OpportunityPaymentLinkRead,
)
async def transition_link(
    application_id: UUID,
    payload: CheckoutConfirmation,
    request: Request,
    session: Session,
    student: StudentUser,
) -> OpportunityPaymentLinkRead:
    return await checkout_payment_link(
        session,
        student,
        "python_to_go_transition",
        application_id,
        payload,
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
    )


@router.post(
    "/payments/{payment_link_id}/development/complete",
    response_model=OpportunitiesDashboard,
)
async def complete_development_payment(
    payment_link_id: str, session: Session, student: StudentUser
) -> OpportunitiesDashboard:
    return await development_complete_payment(session, student, payment_link_id)


@admin_router.patch(
    "/consultation-types/{consultation_type}",
    response_model=WorkspaceSettings,
)
async def update_consultation_type(
    consultation_type: ConsultationType,
    payload: AdminConsultationTypeMutation,
    session: Session,
    admin: AdminUser,
) -> WorkspaceSettings:
    return await admin_update_consultation_type(
        session,
        admin,
        consultation_type,
        payload,
    )


@admin_router.patch(
    "/consultation-mentors/{mentor_id}",
    response_model=WorkspaceSettings,
)
async def set_consultation_mentor(
    mentor_id: UUID,
    payload: AdminConsultationMentorMutation,
    session: Session,
    admin: AdminUser,
) -> WorkspaceSettings:
    return await admin_set_consultation_mentor(
        session,
        admin,
        mentor_id,
        is_enabled=payload.is_enabled,
    )


@admin_router.patch(
    "/go-transition-program",
    response_model=WorkspaceSettings,
)
async def update_go_transition_program(
    payload: AdminGoTransitionProgramMutation,
    session: Session,
    admin: AdminUser,
) -> WorkspaceSettings:
    return await admin_update_go_transition_program(session, admin, payload)


@admin_router.post(
    "/payments/{attempt_id}/confirm",
    response_model=AdminConsultationDetail | AdminGoTransitionDetail | AdminPythonRepeatDetail,
)
async def confirm_opportunity_payment(
    attempt_id: UUID, session: Session, _admin: AdminUser
) -> AdminConsultationDetail | AdminGoTransitionDetail | AdminPythonRepeatDetail:
    attempt = await admin_confirm_opportunity_payment(session, attempt_id)
    if attempt.consultation_request_id:
        return await consultation_detail(session, attempt.consultation_request_id)
    if attempt.transition_application_id:
        return await go_detail(session, attempt.transition_application_id)
    application_id = attempt.python_repeat_application_id
    if application_id is None:
        application_id = await session.scalar(
            select(PythonRepeatEnrollment.application_id)
            .join(
                PythonRepeatSuccessFeeObligation,
                PythonRepeatSuccessFeeObligation.enrollment_id == PythonRepeatEnrollment.id,
            )
            .join(
                PythonRepeatInstallment,
                PythonRepeatInstallment.obligation_id == PythonRepeatSuccessFeeObligation.id,
            )
            .where(PythonRepeatInstallment.id == attempt.python_repeat_installment_id)
        )
    if application_id is None:
        api_error(404, "application_not_found", "Заявка не найдена")
    return await repeat_detail(session, application_id)
