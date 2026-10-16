from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AdminUser
from app.db.session import get_db_session
from app.opportunities import workspace_reads as reads
from app.opportunities.models import ConsultationType
from app.opportunities.workspace_commands import consultation_command, go_command
from app.opportunities.workspace_schemas import (
    AdminConsultationDetail,
    AdminGoTransitionDetail,
    AdminPythonRepeatDetail,
    ConsultationApproveCommand,
    ConsultationCancelCommand,
    ConsultationCompleteCommand,
    ConsultationScheduleCommand,
    ConsultationSummaryCommand,
    GoApproveCommand,
    InternalNoteCommand,
    MentorCommand,
    ReasonCommand,
    WorkspacePage,
    WorkspaceSettings,
)

Session = Annotated[AsyncSession, Depends(get_db_session)]
router = APIRouter(prefix="/admin/opportunities", tags=["admin-opportunity-workspace"])


@router.get("/inbox", response_model=WorkspacePage)
async def inbox(
    session: Session,
    _admin: AdminUser,
    product: reads.Product | None = None,
    q: str = "",
    stage: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> WorkspacePage:
    return await reads.workspace_page(
        session, product=product, q=q, stage=stage, page=page, page_size=page_size, inbox=True
    )


@router.get("/settings", response_model=WorkspaceSettings)
async def settings(session: Session, _admin: AdminUser) -> WorkspaceSettings:
    return await reads.settings_read(session)


@router.get("/consultations", response_model=WorkspacePage)
async def consultations(
    session: Session,
    _admin: AdminUser,
    group: reads.Group = "active",
    q: str = "",
    mentor_id: UUID | None = None,
    consultation_type: ConsultationType | None = None,
    stage: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> WorkspacePage:
    return await reads.workspace_page(
        session,
        product="consultations",
        group=group,
        q=q,
        mentor_id=mentor_id,
        consultation_type=consultation_type,
        stage=stage,
        page=page,
        page_size=page_size,
    )


@router.get("/go-transition", response_model=WorkspacePage)
async def go_applications(
    session: Session,
    _admin: AdminUser,
    group: reads.Group = "active",
    q: str = "",
    stage: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> WorkspacePage:
    return await reads.workspace_page(
        session,
        product="go_transition",
        group=group,
        q=q,
        stage=stage,
        page=page,
        page_size=page_size,
    )


@router.get("/python-repeat", response_model=WorkspacePage)
async def repeat_applications(
    session: Session,
    _admin: AdminUser,
    group: reads.Group = "active",
    q: str = "",
    stage: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> WorkspacePage:
    return await reads.workspace_page(
        session,
        product="python_repeat",
        group=group,
        q=q,
        stage=stage,
        page=page,
        page_size=page_size,
    )


@router.get("/consultations/{resource_id}", response_model=AdminConsultationDetail)
async def consultation(
    resource_id: UUID, session: Session, _admin: AdminUser
) -> AdminConsultationDetail:
    return await reads.consultation_detail(session, resource_id)


@router.get("/go-transition/{resource_id}", response_model=AdminGoTransitionDetail)
async def go_application(
    resource_id: UUID, session: Session, _admin: AdminUser
) -> AdminGoTransitionDetail:
    return await reads.go_detail(session, resource_id)


@router.get("/python-repeat/{resource_id}", response_model=AdminPythonRepeatDetail)
async def repeat_application(
    resource_id: UUID, session: Session, _admin: AdminUser
) -> AdminPythonRepeatDetail:
    return await reads.repeat_detail(session, resource_id)


@router.post("/consultations/{resource_id}/approve", response_model=AdminConsultationDetail)
async def approve_consultation(
    resource_id: UUID, body: ConsultationApproveCommand, session: Session, admin: AdminUser
) -> AdminConsultationDetail:
    await consultation_command(session, admin, resource_id, "approve", body.model_dump())
    return await reads.consultation_detail(session, resource_id)


@router.post("/consultations/{resource_id}/reject", response_model=AdminConsultationDetail)
async def reject_consultation(
    resource_id: UUID, body: ReasonCommand, session: Session, admin: AdminUser
) -> AdminConsultationDetail:
    await consultation_command(session, admin, resource_id, "reject", body.model_dump())
    return await reads.consultation_detail(session, resource_id)


@router.post("/consultations/{resource_id}/mentor", response_model=AdminConsultationDetail)
async def change_consultation_mentor(
    resource_id: UUID, body: MentorCommand, session: Session, admin: AdminUser
) -> AdminConsultationDetail:
    await consultation_command(session, admin, resource_id, "mentor", body.model_dump())
    return await reads.consultation_detail(session, resource_id)


@router.post("/consultations/{resource_id}/schedule", response_model=AdminConsultationDetail)
async def schedule_consultation(
    resource_id: UUID, body: ConsultationScheduleCommand, session: Session, admin: AdminUser
) -> AdminConsultationDetail:
    await consultation_command(session, admin, resource_id, "schedule", body.model_dump())
    return await reads.consultation_detail(session, resource_id)


@router.post("/consultations/{resource_id}/complete", response_model=AdminConsultationDetail)
async def complete_consultation(
    resource_id: UUID, body: ConsultationCompleteCommand, session: Session, admin: AdminUser
) -> AdminConsultationDetail:
    await consultation_command(session, admin, resource_id, "complete", body.model_dump())
    return await reads.consultation_detail(session, resource_id)


@router.patch("/consultations/{resource_id}/summary", response_model=AdminConsultationDetail)
async def edit_consultation_summary(
    resource_id: UUID, body: ConsultationSummaryCommand, session: Session, admin: AdminUser
) -> AdminConsultationDetail:
    await consultation_command(session, admin, resource_id, "summary", body.model_dump())
    return await reads.consultation_detail(session, resource_id)


@router.post("/consultations/{resource_id}/cancel", response_model=AdminConsultationDetail)
async def cancel_consultation(
    resource_id: UUID, body: ConsultationCancelCommand, session: Session, admin: AdminUser
) -> AdminConsultationDetail:
    await consultation_command(session, admin, resource_id, "cancel", body.model_dump())
    return await reads.consultation_detail(session, resource_id)


@router.patch("/consultations/{resource_id}/internal-note", response_model=AdminConsultationDetail)
async def consultation_internal_note(
    resource_id: UUID, body: InternalNoteCommand, session: Session, admin: AdminUser
) -> AdminConsultationDetail:
    await consultation_command(session, admin, resource_id, "internal-note", body.model_dump())
    return await reads.consultation_detail(session, resource_id)


@router.post("/go-transition/{resource_id}/approve", response_model=AdminGoTransitionDetail)
async def approve_go(
    resource_id: UUID, body: GoApproveCommand, session: Session, admin: AdminUser
) -> AdminGoTransitionDetail:
    await go_command(session, admin, resource_id, "approve", body.model_dump())
    return await reads.go_detail(session, resource_id)


@router.post("/go-transition/{resource_id}/reject", response_model=AdminGoTransitionDetail)
async def reject_go(
    resource_id: UUID, body: ReasonCommand, session: Session, admin: AdminUser
) -> AdminGoTransitionDetail:
    await go_command(session, admin, resource_id, "reject", body.model_dump())
    return await reads.go_detail(session, resource_id)


@router.post("/go-transition/{resource_id}/cancel", response_model=AdminGoTransitionDetail)
async def cancel_go(
    resource_id: UUID, body: ReasonCommand, session: Session, admin: AdminUser
) -> AdminGoTransitionDetail:
    await go_command(session, admin, resource_id, "cancel", body.model_dump())
    return await reads.go_detail(session, resource_id)


@router.post("/go-transition/{resource_id}/extend", response_model=AdminGoTransitionDetail)
async def extend_go(
    resource_id: UUID, session: Session, admin: AdminUser
) -> AdminGoTransitionDetail:
    await go_command(session, admin, resource_id, "extend", {})
    return await reads.go_detail(session, resource_id)


@router.patch("/go-transition/{resource_id}/internal-note", response_model=AdminGoTransitionDetail)
async def go_internal_note(
    resource_id: UUID, body: InternalNoteCommand, session: Session, admin: AdminUser
) -> AdminGoTransitionDetail:
    await go_command(session, admin, resource_id, "internal-note", body.model_dump())
    return await reads.go_detail(session, resource_id)
