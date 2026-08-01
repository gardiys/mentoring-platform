from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AdminUser
from app.db.session import get_db_session
from app.interviews.journal_service import list_admin_processes
from app.interviews.models import InterviewProcessStatus
from app.interviews.schemas import AdminInterviewProcessPage

router = APIRouter(prefix="/admin/interviews/processes", tags=["admin-interviews"])
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("", response_model=AdminInterviewProcessPage)
async def admin_interview_processes(
    session: Session,
    _admin: AdminUser,
    status_filter: Literal["all", "active", "closed", "offer"] = Query(
        default="all", alias="status"
    ),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AdminInterviewProcessPage:
    selected_status = None if status_filter == "all" else InterviewProcessStatus(status_filter)
    return await list_admin_processes(
        session, selected_status, limit=limit, offset=offset
    )
