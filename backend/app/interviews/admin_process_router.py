from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AdminUser
from app.core.config import get_settings
from app.db.session import get_db_session
from app.interviews.journal_service import delete_admin_process, list_admin_processes
from app.interviews.models import InterviewProcessStatus
from app.interviews.schemas import AdminInterviewProcessPage
from app.interviews.upload_cleanup import delete_upload_if_unreferenced
from app.interviews.uploads import InterviewUploadStore

router = APIRouter(prefix="/admin/interviews/processes", tags=["admin-interviews"])
Session = Annotated[AsyncSession, Depends(get_db_session)]
store = InterviewUploadStore(get_settings())


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
    return await list_admin_processes(session, selected_status, limit=limit, offset=offset)


@router.delete(
    "/{process_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def admin_delete_interview_process(
    process_id: UUID,
    session: Session,
    _admin: AdminUser,
) -> Response:
    storage_keys = await delete_admin_process(session, process_id)
    for storage_key in storage_keys:
        await delete_upload_if_unreferenced(session, store, storage_key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
