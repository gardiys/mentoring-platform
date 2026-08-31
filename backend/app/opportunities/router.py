from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AdminUser, CurrentUser, StudentUser
from app.db.session import get_db_session
from app.opportunities.models import ConsultationType
from app.opportunities.schemas import (
    AdminConsultationMentorMutation,
    AdminConsultationMutation,
    AdminConsultationTypeMutation,
    AdminGoTransitionProgramMutation,
    AdminOpportunitiesDashboard,
    AdminTransitionMutation,
    ConsultationCreate,
    GoTransitionCreate,
    GoTransitionTermsAcceptance,
    OpportunitiesDashboard,
    OpportunityPaymentLinkRead,
)
from app.opportunities.service import (
    accept_go_transition,
    admin_confirm_opportunity_payment,
    admin_dashboard,
    admin_decide_transition,
    admin_set_consultation_mentor,
    admin_update_consultation,
    admin_update_consultation_type,
    admin_update_go_transition_program,
    consultation_payment_link,
    create_consultation,
    create_go_transition,
    development_complete_payment,
    opportunities_dashboard,
    transition_payment_link,
)

Session = Annotated[AsyncSession, Depends(get_db_session)]
router = APIRouter(prefix="/opportunities", tags=["opportunities"])
admin_router = APIRouter(prefix="/admin/opportunities", tags=["admin-opportunities"])


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
    application_id: UUID, session: Session, student: StudentUser
) -> OpportunityPaymentLinkRead:
    return await transition_payment_link(session, student, application_id)


@router.post(
    "/payments/{payment_link_id}/development/complete",
    response_model=OpportunitiesDashboard,
)
async def complete_development_payment(
    payment_link_id: str, session: Session, student: StudentUser
) -> OpportunitiesDashboard:
    return await development_complete_payment(session, student, payment_link_id)


@admin_router.get("", response_model=AdminOpportunitiesDashboard)
async def list_admin_opportunities(
    session: Session, _admin: AdminUser
) -> AdminOpportunitiesDashboard:
    return await admin_dashboard(session)


@admin_router.patch(
    "/consultation-types/{consultation_type}",
    response_model=AdminOpportunitiesDashboard,
)
async def update_consultation_type(
    consultation_type: ConsultationType,
    payload: AdminConsultationTypeMutation,
    session: Session,
    admin: AdminUser,
) -> AdminOpportunitiesDashboard:
    return await admin_update_consultation_type(
        session,
        admin,
        consultation_type,
        payload,
    )


@admin_router.patch(
    "/consultation-mentors/{mentor_id}",
    response_model=AdminOpportunitiesDashboard,
)
async def set_consultation_mentor(
    mentor_id: UUID,
    payload: AdminConsultationMentorMutation,
    session: Session,
    admin: AdminUser,
) -> AdminOpportunitiesDashboard:
    return await admin_set_consultation_mentor(
        session,
        admin,
        mentor_id,
        is_enabled=payload.is_enabled,
    )


@admin_router.patch(
    "/go-transition-program",
    response_model=AdminOpportunitiesDashboard,
)
async def update_go_transition_program(
    payload: AdminGoTransitionProgramMutation,
    session: Session,
    admin: AdminUser,
) -> AdminOpportunitiesDashboard:
    return await admin_update_go_transition_program(session, admin, payload)


@admin_router.patch("/consultations/{request_id}", response_model=AdminOpportunitiesDashboard)
async def update_consultation(
    request_id: UUID,
    payload: AdminConsultationMutation,
    session: Session,
    _admin: AdminUser,
) -> AdminOpportunitiesDashboard:
    return await admin_update_consultation(session, request_id, payload)


@admin_router.patch("/go-transition/{application_id}", response_model=AdminOpportunitiesDashboard)
async def decide_transition(
    application_id: UUID,
    payload: AdminTransitionMutation,
    session: Session,
    admin: AdminUser,
) -> AdminOpportunitiesDashboard:
    return await admin_decide_transition(
        session,
        admin,
        application_id,
        approved=payload.approved,
        admin_note=payload.admin_note,
    )


@admin_router.post("/payments/{attempt_id}/confirm", response_model=AdminOpportunitiesDashboard)
async def confirm_opportunity_payment(
    attempt_id: UUID, session: Session, _admin: AdminUser
) -> AdminOpportunitiesDashboard:
    return await admin_confirm_opportunity_payment(session, attempt_id)
