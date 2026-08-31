from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AdminUser, StudentUser
from app.db.session import get_db_session
from app.opportunities.python_repeat_schemas import (
    AdminPythonRepeatDashboard,
    AdminPythonRepeatMentorAssignment,
    AdminPythonRepeatOfferDecision,
    AdminPythonRepeatOverride,
    AdminPythonRepeatTransition,
    PythonRepeatApplicationCreate,
    PythonRepeatDashboard,
    PythonRepeatEligibilityRead,
    PythonRepeatOfferCreate,
    PythonRepeatTermsAcceptance,
)
from app.opportunities.python_repeat_service import (
    accept_terms,
    admin_dashboard,
    admin_transition_application,
    assign_mentor,
    checkout,
    create_application,
    create_offer,
    dashboard,
    decide_offer,
    development_complete,
    development_fail,
    development_refund,
    eligibility_override,
    installment_checkout,
    python_repeat_eligibility,
    submit_application,
    submit_offer,
    update_application,
)
from app.opportunities.schemas import OpportunityPaymentLinkRead

Session = Annotated[AsyncSession, Depends(get_db_session)]
router = APIRouter(prefix="/opportunities/python-repeat", tags=["python-repeat"])
admin_router = APIRouter(prefix="/admin/opportunities/python-repeat", tags=["admin-python-repeat"])


@router.get("", response_model=PythonRepeatDashboard)
async def my_python_repeat(session: Session, student: StudentUser) -> PythonRepeatDashboard:
    return await dashboard(session, student)


@router.get("/eligibility", response_model=PythonRepeatEligibilityRead)
async def my_python_repeat_eligibility(
    session: Session, student: StudentUser
) -> PythonRepeatEligibilityRead:
    return await python_repeat_eligibility(session, student)


@router.post("/applications", response_model=PythonRepeatDashboard)
async def start_python_repeat_application(
    payload: PythonRepeatApplicationCreate, session: Session, student: StudentUser
) -> PythonRepeatDashboard:
    return await create_application(session, student, payload)


@router.patch("/applications/{application_id}", response_model=PythonRepeatDashboard)
async def edit_python_repeat_application(
    application_id: UUID,
    payload: PythonRepeatApplicationCreate,
    session: Session,
    student: StudentUser,
) -> PythonRepeatDashboard:
    return await update_application(session, student, application_id, payload)


@router.post("/applications/{application_id}/submit", response_model=PythonRepeatDashboard)
async def submit_python_repeat_application(
    application_id: UUID, session: Session, student: StudentUser
) -> PythonRepeatDashboard:
    return await submit_application(session, student, application_id)


@router.post("/applications/{application_id}/accept-terms", response_model=PythonRepeatDashboard)
async def accept_python_repeat_terms(
    application_id: UUID,
    payload: PythonRepeatTermsAcceptance,
    request: Request,
    session: Session,
    student: StudentUser,
) -> PythonRepeatDashboard:
    del payload
    return await accept_terms(
        session,
        student,
        application_id,
        ip_address=request.client.host if request.client is not None else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.post("/applications/{application_id}/checkout", response_model=OpportunityPaymentLinkRead)
async def checkout_python_repeat(
    application_id: UUID, session: Session, student: StudentUser
) -> OpportunityPaymentLinkRead:
    return await checkout(session, student, application_id)


@router.post("/offers", response_model=PythonRepeatDashboard)
async def add_python_repeat_offer(
    payload: PythonRepeatOfferCreate, session: Session, student: StudentUser
) -> PythonRepeatDashboard:
    return await create_offer(session, student, payload)


@router.post("/offers/{offer_id}/submit", response_model=PythonRepeatDashboard)
async def submit_python_repeat_offer(
    offer_id: UUID, session: Session, student: StudentUser
) -> PythonRepeatDashboard:
    return await submit_offer(session, student, offer_id)


@router.post("/installments/{installment_id}/checkout", response_model=OpportunityPaymentLinkRead)
async def checkout_python_repeat_installment(
    installment_id: UUID, session: Session, student: StudentUser
) -> OpportunityPaymentLinkRead:
    return await installment_checkout(session, student, installment_id)


@router.post(
    "/development/payments/{payment_link_id}/succeed", response_model=PythonRepeatDashboard
)
async def development_succeed_python_repeat_payment(
    payment_link_id: str, session: Session, student: StudentUser
) -> PythonRepeatDashboard:
    return await development_complete(session, student, payment_link_id)


@router.post("/development/payments/{payment_link_id}/fail", response_model=PythonRepeatDashboard)
async def development_fail_python_repeat_payment(
    payment_link_id: str, session: Session, student: StudentUser
) -> PythonRepeatDashboard:
    return await development_fail(session, student, payment_link_id)


@router.post(
    "/development/installments/{installment_id}/refund", response_model=PythonRepeatDashboard
)
async def development_refund_python_repeat_payment(
    installment_id: UUID, session: Session, student: StudentUser
) -> PythonRepeatDashboard:
    return await development_refund(session, student, installment_id)


@admin_router.get("", response_model=AdminPythonRepeatDashboard)
async def list_python_repeat_applications(
    session: Session, _admin: AdminUser
) -> AdminPythonRepeatDashboard:
    return await admin_dashboard(session)


@admin_router.post(
    "/applications/{application_id}/transition", response_model=AdminPythonRepeatDashboard
)
async def transition_python_repeat_application(
    application_id: UUID,
    payload: AdminPythonRepeatTransition,
    session: Session,
    admin: AdminUser,
) -> AdminPythonRepeatDashboard:
    return await admin_transition_application(session, admin, application_id, payload)


@admin_router.post(
    "/applications/{application_id}/eligibility-override", response_model=AdminPythonRepeatDashboard
)
async def override_python_repeat_eligibility(
    application_id: UUID,
    payload: AdminPythonRepeatOverride,
    session: Session,
    admin: AdminUser,
) -> AdminPythonRepeatDashboard:
    return await eligibility_override(session, admin, application_id, payload.reason)


@admin_router.post(
    "/enrollments/{enrollment_id}/assign-mentor", response_model=AdminPythonRepeatDashboard
)
async def assign_python_repeat_mentor(
    enrollment_id: UUID,
    payload: AdminPythonRepeatMentorAssignment,
    session: Session,
    admin: AdminUser,
) -> AdminPythonRepeatDashboard:
    return await assign_mentor(session, admin, enrollment_id, payload.mentor_id)


@admin_router.post("/offers/{offer_id}/decision", response_model=AdminPythonRepeatDashboard)
async def decide_python_repeat_offer(
    offer_id: UUID,
    payload: AdminPythonRepeatOfferDecision,
    session: Session,
    admin: AdminUser,
) -> AdminPythonRepeatDashboard:
    return await decide_offer(session, admin, offer_id, payload)
