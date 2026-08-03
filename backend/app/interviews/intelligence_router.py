from __future__ import annotations

import logging
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AdminUser, CurrentUser, JournalUser, MentorUser
from app.core.config import get_settings
from app.core.errors import api_error
from app.db.session import get_db_session
from app.interviews.intelligence_queue import enqueue_intelligence_job
from app.interviews.intelligence_schemas import (
    AdminQuestionModerationDetail,
    AdminQuestionModerationPage,
    IntelligenceCandidateSpeakerMutation,
    IntelligenceInterviewDetail,
    IntelligenceMediaRead,
    IntelligenceMentorCommentMutation,
    IntelligenceMentorCommentRead,
    IntelligenceProcessingRead,
    IntelligenceQuestionModerationMutation,
    IntelligenceQuestionRead,
    IntelligenceReviewEditMutation,
    IntelligenceReviewQueuePage,
    IntelligenceReviewRead,
    IntelligenceReviewRejectMutation,
    IntelligenceSpeakerRead,
    IntelligenceUtteranceRead,
)
from app.interviews.intelligence_service import (
    complete_interview_review,
    create_mentor_comment,
    delete_intelligence_interview,
    get_admin_question_moderation,
    get_intelligence_interview,
    intelligence_detail,
    intelligence_processing,
    list_admin_question_moderation,
    list_intelligence_interviews,
    moderate_intelligence_question,
    prepare_interview_overview_generation,
    prepare_processing_retry,
    review_action,
    select_candidate_speaker,
)
from app.interviews.models import InterviewProcessStage
from app.interviews.uploads import InterviewUploadStore, StoredUpload

router = APIRouter(prefix="/interviews", tags=["interview-intelligence"])
mentor_router = APIRouter(prefix="/mentor/interviews", tags=["mentor-interview-intelligence"])
admin_router = APIRouter(
    prefix="/admin/interviews/question-moderation",
    tags=["admin-interview-question-moderation"],
)
Session = Annotated[AsyncSession, Depends(get_db_session)]
settings = get_settings()
store = InterviewUploadStore(settings)
logger = logging.getLogger(__name__)


@admin_router.get("", response_model=AdminQuestionModerationPage)
async def admin_question_moderation_queue(
    session: Session,
    _admin: AdminUser,
    queue_status: Literal["needs_review", "mentor_approved", "approved", "rejected", "all"] = Query(
        default="needs_review", alias="status"
    ),
    track_id: Annotated[UUID | None, Query()] = None,
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AdminQuestionModerationPage:
    return await list_admin_question_moderation(
        session,
        status=queue_status,
        track_id=track_id,
        query=q,
        limit=limit,
        offset=offset,
    )


@admin_router.get("/{question_id}", response_model=AdminQuestionModerationDetail)
async def admin_question_moderation_detail(
    question_id: UUID, session: Session, _admin: AdminUser
) -> AdminQuestionModerationDetail:
    return await get_admin_question_moderation(session, question_id)


async def _enqueue(function: str, interview_id: UUID) -> None:
    try:
        job_id = await enqueue_intelligence_job(function, str(interview_id))
    except Exception:
        logger.exception(
            "Could not enqueue interview processing interview_id=%s function=%s",
            interview_id,
            function,
        )
        api_error(503, "interview_processing_unavailable", "Processing queue is unavailable")
    if job_id is None:
        api_error(503, "interview_processing_unavailable", "Processing queue is unavailable")


@router.get("", response_model=IntelligenceReviewQueuePage)
async def interviews(
    session: Session,
    current_user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> IntelligenceReviewQueuePage:
    items, total = await list_intelligence_interviews(
        session, current_user, limit=limit, offset=offset
    )
    return IntelligenceReviewQueuePage(items=items, total=total, limit=limit, offset=offset)


@router.get("/{interview_id}/processing", response_model=IntelligenceProcessingRead)
async def interview_processing(
    interview_id: UUID, session: Session, current_user: CurrentUser
) -> IntelligenceProcessingRead:
    return await intelligence_processing(session, current_user, interview_id)


@router.get("/{interview_id}/speakers", response_model=list[IntelligenceSpeakerRead])
async def interview_speakers(
    interview_id: UUID, session: Session, current_user: CurrentUser
) -> list[IntelligenceSpeakerRead]:
    return (await intelligence_detail(session, current_user, interview_id)).speakers


@router.put("/{interview_id}/candidate-speaker", response_model=IntelligenceInterviewDetail)
async def interview_candidate_speaker(
    interview_id: UUID,
    payload: IntelligenceCandidateSpeakerMutation,
    session: Session,
    student: JournalUser,
) -> IntelligenceInterviewDetail:
    await select_candidate_speaker(session, student, interview_id, payload.speaker_id)
    await _enqueue("extract_interview_structure", interview_id)
    return await intelligence_detail(session, student, interview_id)


@router.get("/{interview_id}/transcript", response_model=list[IntelligenceUtteranceRead])
async def interview_transcript(
    interview_id: UUID, session: Session, current_user: CurrentUser
) -> list[IntelligenceUtteranceRead]:
    return (await intelligence_detail(session, current_user, interview_id)).transcript


@router.get("/{interview_id}/questions", response_model=list[IntelligenceQuestionRead])
async def interview_questions(
    interview_id: UUID, session: Session, current_user: CurrentUser
) -> list[IntelligenceQuestionRead]:
    return (await intelligence_detail(session, current_user, interview_id)).questions


@router.get("/{interview_id}/questions/{question_id}", response_model=IntelligenceQuestionRead)
async def interview_question(
    interview_id: UUID,
    question_id: UUID,
    session: Session,
    current_user: CurrentUser,
) -> IntelligenceQuestionRead:
    questions = (await intelligence_detail(session, current_user, interview_id)).questions
    for question in questions:
        if question.id == question_id:
            return question
    api_error(404, "intelligence_question_not_found", "Question was not found")


@router.get("/{interview_id}/media", response_model=IntelligenceMediaRead)
async def interview_media(
    interview_id: UUID, session: Session, current_user: CurrentUser
) -> IntelligenceMediaRead:
    interview = await get_intelligence_interview(session, current_user, interview_id)
    stage = await session.get(InterviewProcessStage, interview.stage_id)
    if (
        stage is None
        or stage.media_storage_key is None
        or stage.media_filename is None
        or stage.media_content_type is None
        or stage.media_size is None
    ):
        api_error(404, "interview_media_not_found", "Interview media was not found")
    upload = StoredUpload(
        storage_key=stage.media_storage_key,
        filename=stage.media_filename,
        content_type=stage.media_content_type,
        size=stage.media_size,
    )
    return IntelligenceMediaRead(
        url=store.download_url(upload, inline=True), content_type=upload.content_type
    )


@router.post("/{interview_id}/retry", response_model=IntelligenceInterviewDetail)
async def retry_interview(
    interview_id: UUID, session: Session, current_user: CurrentUser
) -> IntelligenceInterviewDetail:
    interview, job_name = await prepare_processing_retry(session, current_user, interview_id)
    await _enqueue(job_name, interview.id)
    return await intelligence_detail(session, current_user, interview.id)


@router.get("/{interview_id}", response_model=IntelligenceInterviewDetail)
async def interview(
    interview_id: UUID, session: Session, current_user: CurrentUser
) -> IntelligenceInterviewDetail:
    return await intelligence_detail(session, current_user, interview_id)


@router.delete("/{interview_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_interview(
    interview_id: UUID, session: Session, current_user: CurrentUser
) -> Response:
    keys = await delete_intelligence_interview(session, current_user, interview_id)
    for key in keys:
        await store.delete(key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@mentor_router.get("", response_model=IntelligenceReviewQueuePage)
async def mentor_interviews(
    session: Session,
    mentor: MentorUser,
    review_filter: Literal["needs_review", "reviewed", "processing", "all"] = Query(
        default="needs_review", alias="status"
    ),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> IntelligenceReviewQueuePage:
    items, total = await list_intelligence_interviews(
        session, mentor, queue_filter=review_filter, limit=limit, offset=offset
    )
    return IntelligenceReviewQueuePage(items=items, total=total, limit=limit, offset=offset)


@mentor_router.get("/{interview_id}", response_model=IntelligenceInterviewDetail)
async def mentor_interview(
    interview_id: UUID, session: Session, mentor: MentorUser
) -> IntelligenceInterviewDetail:
    return await intelligence_detail(session, mentor, interview_id)


@mentor_router.post("/{interview_id}/complete-review", response_model=IntelligenceInterviewDetail)
async def complete_review(
    interview_id: UUID, session: Session, mentor: MentorUser
) -> IntelligenceInterviewDetail:
    interview = await complete_interview_review(session, mentor, interview_id)
    return await intelligence_detail(session, mentor, interview.id)


@mentor_router.post("/{interview_id}/generate-overview", response_model=IntelligenceInterviewDetail)
async def generate_overview(
    interview_id: UUID, session: Session, mentor: MentorUser
) -> IntelligenceInterviewDetail:
    interview = await prepare_interview_overview_generation(session, mentor, interview_id)
    await _enqueue("generate_answer_reviews", interview.id)
    return await intelligence_detail(session, mentor, interview.id)


@mentor_router.post(
    "/{interview_id}/comments",
    response_model=IntelligenceMentorCommentRead,
    status_code=status.HTTP_201_CREATED,
)
async def mentor_comment(
    interview_id: UUID,
    payload: IntelligenceMentorCommentMutation,
    session: Session,
    mentor: MentorUser,
) -> IntelligenceMentorCommentRead:
    return await create_mentor_comment(session, mentor, interview_id, payload)


@mentor_router.patch("/{interview_id}/reviews/{review_id}", response_model=IntelligenceReviewRead)
async def mentor_edit_review(
    interview_id: UUID,
    review_id: UUID,
    payload: IntelligenceReviewEditMutation,
    session: Session,
    mentor: MentorUser,
) -> IntelligenceReviewRead:
    return await review_action(
        session, mentor, interview_id, review_id, action="edit", edit=payload
    )


@mentor_router.post(
    "/{interview_id}/questions/{question_id}/moderation",
    response_model=IntelligenceInterviewDetail,
)
async def moderate_question(
    interview_id: UUID,
    question_id: UUID,
    payload: IntelligenceQuestionModerationMutation,
    session: Session,
    mentor: MentorUser,
) -> IntelligenceInterviewDetail:
    interview = await moderate_intelligence_question(
        session, mentor, interview_id, question_id, payload
    )
    return await intelligence_detail(session, mentor, interview.id)


@mentor_router.post(
    "/{interview_id}/reviews/{review_id}/approve", response_model=IntelligenceReviewRead
)
async def mentor_approve_review(
    interview_id: UUID, review_id: UUID, session: Session, mentor: MentorUser
) -> IntelligenceReviewRead:
    return await review_action(session, mentor, interview_id, review_id, action="approve")


@mentor_router.post(
    "/{interview_id}/reviews/{review_id}/reject", response_model=IntelligenceReviewRead
)
async def mentor_reject_review(
    interview_id: UUID,
    review_id: UUID,
    payload: IntelligenceReviewRejectMutation,
    session: Session,
    mentor: MentorUser,
) -> IntelligenceReviewRead:
    return await review_action(
        session,
        mentor,
        interview_id,
        review_id,
        action="reject",
        rejection_reason=payload.reason,
    )
