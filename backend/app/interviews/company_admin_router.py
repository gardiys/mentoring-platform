from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AdminUser
from app.db.session import get_db_session
from app.interviews.companies import (
    CompanyAliasProposalView,
    list_company_alias_proposals,
    moderate_company_alias_proposal,
)
from app.interviews.models import CompanyAliasProposalStatus
from app.interviews.schemas import (
    AdminCompanyAliasProposalMutation,
    AdminCompanyAliasProposalPage,
    AdminCompanyAliasProposalRead,
)

router = APIRouter(
    prefix="/admin/interviews/company-alias-proposals",
    tags=["admin-company-aliases"],
)
Session = Annotated[AsyncSession, Depends(get_db_session)]


def _proposal_read(view: CompanyAliasProposalView) -> AdminCompanyAliasProposalRead:
    proposal = view.proposal
    suggested_by = view.suggested_by
    reviewed_by = view.reviewed_by
    conflict = view.conflicting_company
    return AdminCompanyAliasProposalRead(
        id=proposal.id,
        company_id=proposal.company_id,
        company_name=proposal.company_name,
        alias_name=proposal.name,
        suggested_by_user_id=proposal.suggested_by_user_id,
        suggested_by_name=suggested_by.first_name if suggested_by is not None else None,
        suggested_by_telegram_username=(
            suggested_by.telegram_username if suggested_by is not None else None
        ),
        status=proposal.status,
        conflicting_company_id=conflict.id if conflict is not None else None,
        conflicting_company_name=conflict.name if conflict is not None else None,
        reviewed_by_name=reviewed_by.first_name if reviewed_by is not None else None,
        reviewed_at=proposal.reviewed_at,
        rejection_reason=proposal.rejection_reason,
        created_at=proposal.created_at,
    )


@router.get("", response_model=AdminCompanyAliasProposalPage)
async def admin_company_alias_proposals(
    session: Session,
    _admin: AdminUser,
    status_filter: Literal["all", "pending", "approved", "rejected"] = Query(
        default="pending", alias="status"
    ),
    q: str | None = Query(default=None, max_length=240),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AdminCompanyAliasProposalPage:
    selected_status = None if status_filter == "all" else CompanyAliasProposalStatus(status_filter)
    views, total = await list_company_alias_proposals(
        session,
        selected_status,
        query=q,
        limit=limit,
        offset=offset,
    )
    return AdminCompanyAliasProposalPage(
        items=[_proposal_read(view) for view in views],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/{proposal_id}", response_model=AdminCompanyAliasProposalRead)
async def admin_moderate_company_alias_proposal(
    proposal_id: UUID,
    payload: AdminCompanyAliasProposalMutation,
    session: Session,
    admin: AdminUser,
) -> AdminCompanyAliasProposalRead:
    view = await moderate_company_alias_proposal(
        session,
        proposal_id,
        admin,
        action=payload.action,
        merge_conflicting_company=payload.merge_conflicting_company,
        rejection_reason=payload.rejection_reason,
    )
    return _proposal_read(view)
