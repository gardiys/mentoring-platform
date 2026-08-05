import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AdminUser
from app.core.errors import api_error
from app.db.session import get_db_session
from app.interviews.intelligence_operations_service import (
    admin_intelligence_operations,
    prepare_admin_intelligence_requeue,
)
from app.interviews.intelligence_queue import enqueue_intelligence_job
from app.interviews.intelligence_schemas import (
    AdminIntelligenceOperationsRead,
    IntelligenceInterviewDetail,
)
from app.interviews.intelligence_service import intelligence_detail

router = APIRouter(prefix="/admin/interviews/ai-operations", tags=["admin-interviews"])
Session = Annotated[AsyncSession, Depends(get_db_session)]
logger = logging.getLogger(__name__)


@router.get("", response_model=AdminIntelligenceOperationsRead)
async def admin_ai_operations(
    session: Session,
    _admin: AdminUser,
) -> AdminIntelligenceOperationsRead:
    return await admin_intelligence_operations(session)


@router.post("/{interview_id}/requeue", response_model=IntelligenceInterviewDetail)
async def admin_requeue_ai_processing(
    interview_id: UUID,
    session: Session,
    admin: AdminUser,
) -> IntelligenceInterviewDetail:
    interview, job_name = await prepare_admin_intelligence_requeue(session, interview_id)
    try:
        if job_name == "generate_answer_reviews":
            await enqueue_intelligence_job(
                "refresh_interview_question_embeddings",
                str(interview.id),
            )
        await enqueue_intelligence_job(job_name, str(interview.id))
    except Exception:
        logger.exception(
            "Could not requeue interview processing interview_id=%s function=%s",
            interview.id,
            job_name,
        )
        api_error(503, "interview_processing_unavailable", "Processing queue is unavailable")
    return await intelligence_detail(session, admin, interview.id)
