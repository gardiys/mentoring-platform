from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import api_error
from app.interviews.companies import resolve_company
from app.interviews.intelligence_models import (
    IntelligenceAnswer,
    IntelligenceAnswerReview,
    IntelligenceAttemptStage,
    IntelligenceInterview,
    IntelligenceInterviewType,
    IntelligenceMentorComment,
    IntelligenceProcessingAttempt,
    IntelligenceProcessingStatus,
    IntelligenceQuestion,
    IntelligenceQuestionModerationStatus,
    IntelligenceReviewSource,
    IntelligenceReviewStatus,
    IntelligenceSpeaker,
    IntelligenceSpeakerRole,
    IntelligenceUtterance,
)
from app.interviews.intelligence_schemas import (
    IntelligenceAnswerRead,
    IntelligenceInterviewCreate,
    IntelligenceInterviewDetail,
    IntelligenceInterviewOverviewRead,
    IntelligenceInterviewSummary,
    IntelligenceMentorCommentMutation,
    IntelligenceMentorCommentRead,
    IntelligenceProcessingAttemptRead,
    IntelligenceProcessingRead,
    IntelligenceQuestionModerationMutation,
    IntelligenceQuestionRead,
    IntelligenceReviewEditMutation,
    IntelligenceReviewRead,
    IntelligenceSpeakerRead,
    IntelligenceUtteranceRead,
)
from app.interviews.models import (
    InterviewCard,
    InterviewCardProgress,
    InterviewDeck,
    InterviewProcess,
    InterviewProcessStage,
    InterviewProcessStatus,
    InterviewStageType,
    InterviewTopicSelection,
)
from app.mentors.models import MentorStudent
from app.tracks.access import has_track_access
from app.tracks.models import LearningTrack
from app.users.models import User, UserRole

settings = get_settings()


TYPE_TO_STAGE = {
    IntelligenceInterviewType.HR: InterviewStageType.SCREENING,
    IntelligenceInterviewType.SCREENING: InterviewStageType.TECHNICAL_SCREENING,
    IntelligenceInterviewType.TECHNICAL: InterviewStageType.TECHNICAL_INTERVIEW,
    IntelligenceInterviewType.FINAL: InterviewStageType.FINAL_INTERVIEW,
    IntelligenceInterviewType.SYSTEM_DESIGN: InterviewStageType.SYSTEM_DESIGN,
    IntelligenceInterviewType.LIVE_CODING: InterviewStageType.TECHNICAL_INTERVIEW,
    IntelligenceInterviewType.OTHER: InterviewStageType.OTHER,
}

STAGE_TO_TYPE = {
    InterviewStageType.SCREENING: IntelligenceInterviewType.HR,
    InterviewStageType.TECHNICAL_SCREENING: IntelligenceInterviewType.SCREENING,
    InterviewStageType.TECHNICAL_INTERVIEW: IntelligenceInterviewType.TECHNICAL,
    InterviewStageType.SYSTEM_DESIGN: IntelligenceInterviewType.SYSTEM_DESIGN,
    InterviewStageType.FINAL_INTERVIEW: IntelligenceInterviewType.FINAL,
    InterviewStageType.OTHER: IntelligenceInterviewType.OTHER,
}


async def start_stage_ai_analysis(
    session: AsyncSession,
    user: User,
    process_id: UUID,
    stage_id: UUID,
) -> IntelligenceInterview:
    stage = await session.scalar(
        select(InterviewProcessStage)
        .join(InterviewProcess, InterviewProcess.id == InterviewProcessStage.process_id)
        .where(
            InterviewProcessStage.id == stage_id,
            InterviewProcessStage.process_id == process_id,
            InterviewProcess.user_id == user.id,
        )
        .with_for_update()
    )
    if stage is None:
        api_error(404, "interview_stage_not_found", "Interview stage was not found")
    if (
        stage.media_storage_key is None
        or stage.media_filename is None
        or stage.media_content_type is None
        or stage.media_size is None
    ):
        api_error(409, "interview_recording_required", "Upload an interview recording first")
    if not stage.media_content_type.startswith(("audio/", "video/")):
        api_error(415, "unsupported_interview_file_type", "Select an audio or video recording")
    existing_id = await session.scalar(
        select(IntelligenceInterview.id).where(IntelligenceInterview.stage_id == stage.id)
    )
    if stage.ai_analysis_requested_at is not None or existing_id is not None:
        api_error(
            409,
            "interview_ai_analysis_already_requested",
            "AI analysis can only be requested once for an interview",
        )
    process = await session.get(InterviewProcess, process_id)
    assert process is not None
    interview = IntelligenceInterview(
        stage_id=stage.id,
        student_id=user.id,
        interview_type=STAGE_TO_TYPE[stage.stage_type],
        processing_status=IntelligenceProcessingStatus.UPLOADED,
    )
    stage.ai_analysis_requested_at = datetime.now(UTC)
    session.add(interview)
    await session.commit()
    await session.refresh(interview)
    return interview


async def create_intelligence_interview(
    session: AsyncSession,
    student: User,
    payload: IntelligenceInterviewCreate,
) -> IntelligenceInterviewDetail:
    if student.role is not UserRole.STUDENT:
        api_error(403, "student_access_required", "Only students can create AI interview reviews")
    if not await has_track_access(session, student, payload.track_id):
        api_error(422, "interview_direction_not_available", "Direction is not available")
    track = await session.get(LearningTrack, payload.track_id)
    if track is None or not track.is_published:
        api_error(422, "interview_direction_not_available", "Direction is not available")
    company = await resolve_company(
        session,
        payload.company_name,
        company_id=payload.company_id,
        raw_alias=payload.company_alias,
    )
    process = InterviewProcess(
        user_id=student.id,
        track_id=track.id,
        company_id=company.id,
        company_name=company.name,
        recruiter_telegram_usernames=[],
        status=InterviewProcessStatus.ACTIVE,
    )
    session.add(process)
    await session.flush()
    stage = InterviewProcessStage(
        process_id=process.id,
        stage_type=TYPE_TO_STAGE[payload.interview_type],
        scheduled_at=payload.interviewed_at,
    )
    session.add(stage)
    await session.flush()
    interview = IntelligenceInterview(
        stage_id=stage.id,
        student_id=student.id,
        position_name=payload.position_name,
        interview_type=payload.interview_type,
        processing_status=IntelligenceProcessingStatus.DRAFT,
    )
    session.add(interview)
    await session.commit()
    return await intelligence_detail(session, student, interview.id)


async def get_intelligence_interview(
    session: AsyncSession,
    user: User,
    interview_id: UUID,
    *,
    owner_only: bool = False,
    lock: bool = False,
) -> IntelligenceInterview:
    statement = select(IntelligenceInterview).where(IntelligenceInterview.id == interview_id)
    if user.role is UserRole.STUDENT or (owner_only and user.role is not UserRole.ADMIN):
        statement = statement.where(IntelligenceInterview.student_id == user.id)
    elif user.role is UserRole.MENTOR:
        statement = statement.where(
            or_(
                IntelligenceInterview.student_id == user.id,
                IntelligenceInterview.student_id.in_(
                    select(MentorStudent.student_id).where(MentorStudent.mentor_id == user.id)
                ),
            )
        )
    if lock:
        statement = statement.with_for_update()
    interview = await session.scalar(statement)
    if interview is None:
        api_error(404, "intelligence_interview_not_found", "Interview was not found")
    return interview


async def prepare_processing_retry(
    session: AsyncSession,
    user: User,
    interview_id: UUID,
) -> tuple[IntelligenceInterview, str]:
    interview = await get_intelligence_interview(session, user, interview_id, lock=True)
    if interview.processing_status is not IntelligenceProcessingStatus.FAILED:
        api_error(409, "interview_retry_not_available", "Interview processing has not failed")
    failed_stage = interview.failed_stage
    if failed_stage in {
        IntelligenceAttemptStage.NORMALIZE,
        IntelligenceAttemptStage.TRANSCRIPTION_SUBMIT,
        IntelligenceAttemptStage.TRANSCRIPTION_POLL,
        IntelligenceAttemptStage.TRANSCRIPTION_PARSE,
    }:
        interview.transcription_provider_job_id = None
        interview.transcription_provider_payload = None
        interview.processing_status = IntelligenceProcessingStatus.UPLOADED
        job_name = "submit_transcription"
    elif failed_stage is IntelligenceAttemptStage.AI_EXTRACT:
        interview.processing_status = IntelligenceProcessingStatus.ANALYZING
        job_name = "extract_interview_structure"
    elif failed_stage is IntelligenceAttemptStage.AI_REVIEW:
        interview.processing_status = IntelligenceProcessingStatus.ANALYZING
        job_name = "generate_answer_reviews"
    else:
        api_error(409, "interview_retry_not_available", "Failed stage cannot be retried")
    interview.processing_error_code = None
    interview.processing_error_message = None
    interview.failed_stage = None
    await session.commit()
    return interview, job_name


async def list_intelligence_interviews(
    session: AsyncSession,
    user: User,
    *,
    queue_filter: str = "all",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[IntelligenceInterviewSummary], int]:
    statement = select(IntelligenceInterview.id)
    if user.role is UserRole.STUDENT:
        statement = statement.where(IntelligenceInterview.student_id == user.id)
    elif user.role is UserRole.MENTOR:
        statement = statement.where(
            or_(
                IntelligenceInterview.student_id == user.id,
                IntelligenceInterview.student_id.in_(
                    select(MentorStudent.student_id).where(MentorStudent.mentor_id == user.id)
                ),
            )
        )
    if queue_filter == "processing":
        statement = statement.where(
            IntelligenceInterview.processing_status.not_in(
                [IntelligenceProcessingStatus.READY, IntelligenceProcessingStatus.FAILED]
            )
        )
    elif queue_filter == "needs_review":
        statement = statement.where(
            IntelligenceInterview.processing_status == IntelligenceProcessingStatus.READY,
            IntelligenceInterview.reviewed_at.is_(None),
        )
    elif queue_filter == "reviewed":
        statement = statement.where(
            IntelligenceInterview.processing_status == IntelligenceProcessingStatus.READY,
            IntelligenceInterview.reviewed_at.is_not(None),
        )
    total = int(await session.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    ids = list(
        await session.scalars(
            statement.order_by(IntelligenceInterview.created_at.desc()).limit(limit).offset(offset)
        )
    )
    return [await intelligence_summary(session, item) for item in ids], total


async def intelligence_summary(
    session: AsyncSession, interview_id: UUID
) -> IntelligenceInterviewSummary:
    row = (
        await session.execute(
            select(
                IntelligenceInterview,
                InterviewProcessStage,
                InterviewProcess,
                LearningTrack,
                User,
            )
            .join(InterviewProcessStage, InterviewProcessStage.id == IntelligenceInterview.stage_id)
            .join(InterviewProcess, InterviewProcess.id == InterviewProcessStage.process_id)
            .join(LearningTrack, LearningTrack.id == InterviewProcess.track_id)
            .join(User, User.id == IntelligenceInterview.student_id)
            .where(IntelligenceInterview.id == interview_id)
        )
    ).one()
    interview, stage, process, track, student = row
    question_count = int(
        await session.scalar(
            select(func.count(IntelligenceQuestion.id)).where(
                IntelligenceQuestion.interview_id == interview.id
            )
        )
        or 0
    )
    review_rows = (
        await session.execute(
            select(IntelligenceAnswerReview.status, func.count(IntelligenceAnswerReview.id))
            .join(IntelligenceAnswer, IntelligenceAnswer.id == IntelligenceAnswerReview.answer_id)
            .join(IntelligenceQuestion, IntelligenceQuestion.id == IntelligenceAnswer.question_id)
            .where(
                IntelligenceQuestion.interview_id == interview.id,
                IntelligenceAnswerReview.source == IntelligenceReviewSource.AI,
            )
            .group_by(IntelligenceAnswerReview.status)
        )
    ).all()
    review_counts: dict[IntelligenceReviewStatus, int] = {
        status: count for status, count in review_rows
    }
    return IntelligenceInterviewSummary(
        id=interview.id,
        stage_id=stage.id,
        process_id=process.id,
        student_id=interview.student_id,
        student_name=student.first_name,
        company_name=process.company_name,
        position_name=interview.position_name,
        track_id=track.id,
        track_slug=track.slug,
        track_title=track.title,
        interview_type=interview.interview_type,
        interviewed_at=stage.scheduled_at,
        processing_status=interview.processing_status,
        duration_ms=interview.duration_ms,
        question_count=question_count,
        suggested_review_count=review_counts.get(IntelligenceReviewStatus.SUGGESTED, 0),
        reviewed_count=sum(
            review_counts.get(status, 0)
            for status in (
                IntelligenceReviewStatus.APPROVED,
                IntelligenceReviewStatus.EDITED,
                IntelligenceReviewStatus.REJECTED,
            )
        ),
        reviewed_at=interview.reviewed_at,
        reviewed_by_user_id=interview.reviewed_by_user_id,
        created_at=interview.created_at,
        updated_at=interview.updated_at,
    )


async def intelligence_detail(
    session: AsyncSession, user: User, interview_id: UUID
) -> IntelligenceInterviewDetail:
    interview = await get_intelligence_interview(session, user, interview_id)
    summary = await intelligence_summary(session, interview.id)
    stage = await session.get(InterviewProcessStage, interview.stage_id)
    assert stage is not None

    speakers = list(
        await session.scalars(
            select(IntelligenceSpeaker)
            .where(IntelligenceSpeaker.interview_id == interview.id)
            .order_by(IntelligenceSpeaker.provider_speaker_key)
        )
    )
    utterances = list(
        await session.scalars(
            select(IntelligenceUtterance)
            .where(IntelligenceUtterance.interview_id == interview.id)
            .order_by(IntelligenceUtterance.sequence_number)
        )
    )
    speaker_by_id = {speaker.id: speaker for speaker in speakers}
    utterance_reads = [
        IntelligenceUtteranceRead(
            id=item.id,
            speaker_id=item.speaker_id,
            speaker_key=speaker_by_id[item.speaker_id].provider_speaker_key,
            speaker_role=speaker_by_id[item.speaker_id].role,
            sequence_number=item.sequence_number,
            start_ms=item.start_ms,
            end_ms=item.end_ms,
            text=item.text,
        )
        for item in utterances
    ]
    examples_by_speaker: dict[UUID, list[IntelligenceUtteranceRead]] = defaultdict(list)
    for item in utterance_reads:
        if len(examples_by_speaker[item.speaker_id]) < 4:
            examples_by_speaker[item.speaker_id].append(item)

    questions = list(
        await session.scalars(
            select(IntelligenceQuestion)
            .where(IntelligenceQuestion.interview_id == interview.id)
            .order_by(IntelligenceQuestion.sequence_number)
        )
    )
    answers = list(
        await session.scalars(
            select(IntelligenceAnswer)
            .join(IntelligenceQuestion, IntelligenceQuestion.id == IntelligenceAnswer.question_id)
            .where(IntelligenceQuestion.interview_id == interview.id)
        )
    )
    answers_by_question = {answer.question_id: answer for answer in answers}
    reviews = list(
        await session.scalars(
            select(IntelligenceAnswerReview)
            .join(IntelligenceAnswer, IntelligenceAnswer.id == IntelligenceAnswerReview.answer_id)
            .join(IntelligenceQuestion, IntelligenceQuestion.id == IntelligenceAnswer.question_id)
            .where(IntelligenceQuestion.interview_id == interview.id)
            .order_by(IntelligenceAnswerReview.created_at)
        )
    )
    reviews_by_answer: dict[UUID, list[IntelligenceAnswerReview]] = defaultdict(list)
    for review in reviews:
        reviews_by_answer[review.answer_id].append(review)

    comments = (
        await session.execute(
            select(IntelligenceMentorComment, User)
            .join(User, User.id == IntelligenceMentorComment.mentor_id)
            .where(IntelligenceMentorComment.interview_id == interview.id)
            .order_by(IntelligenceMentorComment.created_at)
        )
    ).all()
    attempts = list(
        await session.scalars(
            select(IntelligenceProcessingAttempt)
            .where(IntelligenceProcessingAttempt.interview_id == interview.id)
            .order_by(IntelligenceProcessingAttempt.started_at)
        )
    )
    review_reads = {
        answer.id: [_review_read(review) for review in reviews_by_answer[answer.id]]
        for answer in answers
    }
    question_reads: list[IntelligenceQuestionRead] = []
    for question in questions:
        answer = answers_by_question.get(question.id)
        question_reads.append(
            IntelligenceQuestionRead(
                id=question.id,
                sequence_number=question.sequence_number,
                question_text=question.question_text,
                question_start_ms=question.question_start_ms,
                question_end_ms=question.question_end_ms,
                answer_start_ms=question.answer_start_ms,
                answer_end_ms=question.answer_end_ms,
                category=question.category,
                question_kind=question.question_kind,
                subcategory=question.subcategory,
                difficulty=question.difficulty,
                confidence=question.confidence,
                is_low_confidence=(
                    question.confidence < settings.interview_ai_extraction_confidence_threshold
                ),
                moderation_status=question.moderation_status,
                published_card_id=question.published_card_id,
                answer=(
                    IntelligenceAnswerRead(
                        id=answer.id,
                        answer_text=answer.answer_text,
                        start_ms=answer.start_ms,
                        end_ms=answer.end_ms,
                        reviews=review_reads[answer.id],
                    )
                    if answer is not None
                    else None
                ),
            )
        )
    return IntelligenceInterviewDetail(
        **summary.model_dump(),
        media_filename=stage.media_filename,
        media_content_type=stage.media_content_type,
        media_size=stage.media_size,
        speakers=[
            IntelligenceSpeakerRead(
                id=speaker.id,
                provider_speaker_key=speaker.provider_speaker_key,
                role=speaker.role,
                display_name=speaker.display_name,
                examples=examples_by_speaker[speaker.id],
            )
            for speaker in speakers
        ],
        transcript=utterance_reads,
        questions=question_reads,
        mentor_comments=[
            IntelligenceMentorCommentRead(
                id=comment.id,
                mentor_id=comment.mentor_id,
                mentor_name=mentor.first_name,
                mentor_telegram_username=mentor.telegram_username,
                question_id=comment.question_id,
                timestamp_ms=comment.timestamp_ms,
                text=comment.text,
                created_at=comment.created_at,
                updated_at=comment.updated_at,
            )
            for comment, mentor in comments
        ],
        overview=(
            IntelligenceInterviewOverviewRead.model_validate(
                {
                    **interview.ai_summary_payload,
                    "model_name": interview.ai_summary_model,
                    "prompt_version": interview.ai_summary_prompt_version,
                }
            )
            if interview.ai_summary_payload is not None
            else None
        ),
        processing=IntelligenceProcessingRead(
            status=interview.processing_status,
            failed_stage=interview.failed_stage,
            error_code=interview.processing_error_code,
            error_message=interview.processing_error_message,
            transcribed=bool(utterances),
            candidate_selected=interview.candidate_speaker_id is not None,
            questions_found=len(questions),
            reviews_completed=sum(len(value) for value in review_reads.values()),
            attempts=[
                IntelligenceProcessingAttemptRead(
                    id=attempt.id,
                    stage=attempt.stage,
                    status=attempt.status,
                    attempt_number=attempt.attempt_number,
                    provider=attempt.provider,
                    error_code=attempt.error_code,
                    error_message=attempt.error_message,
                    started_at=attempt.started_at,
                    finished_at=attempt.finished_at,
                )
                for attempt in attempts
            ],
        ),
    )


async def select_candidate_speaker(
    session: AsyncSession, user: User, interview_id: UUID, speaker_id: UUID
) -> IntelligenceInterview:
    interview = await get_intelligence_interview(
        session, user, interview_id, owner_only=True, lock=True
    )
    speaker = await session.scalar(
        select(IntelligenceSpeaker).where(
            IntelligenceSpeaker.id == speaker_id,
            IntelligenceSpeaker.interview_id == interview.id,
        )
    )
    if speaker is None:
        api_error(422, "invalid_candidate_speaker", "Speaker does not belong to this interview")
    await session.execute(
        update(IntelligenceSpeaker)
        .where(IntelligenceSpeaker.interview_id == interview.id)
        .values(role=IntelligenceSpeakerRole.UNKNOWN)
    )
    speaker.role = IntelligenceSpeakerRole.CANDIDATE
    interview.candidate_speaker_id = speaker.id
    interview.processing_status = IntelligenceProcessingStatus.ANALYZING
    interview.processing_error_code = None
    interview.processing_error_message = None
    await session.commit()
    return interview


async def create_mentor_comment(
    session: AsyncSession,
    mentor: User,
    interview_id: UUID,
    payload: IntelligenceMentorCommentMutation,
) -> IntelligenceMentorCommentRead:
    interview = await get_intelligence_interview(session, mentor, interview_id)
    if payload.question_id is not None:
        question = await session.scalar(
            select(IntelligenceQuestion).where(
                IntelligenceQuestion.id == payload.question_id,
                IntelligenceQuestion.interview_id == interview.id,
            )
        )
        if question is None:
            api_error(422, "invalid_intelligence_question", "Question is not part of interview")
    if payload.timestamp_ms is not None and (
        interview.duration_ms is not None and payload.timestamp_ms > interview.duration_ms
    ):
        api_error(422, "invalid_interview_timestamp", "Timestamp is outside the recording")
    comment = IntelligenceMentorComment(
        mentor_id=mentor.id,
        student_id=interview.student_id,
        interview_id=interview.id,
        question_id=payload.question_id,
        timestamp_ms=payload.timestamp_ms,
        text=payload.text,
    )
    session.add(comment)
    await session.commit()
    await session.refresh(comment)
    return IntelligenceMentorCommentRead(
        id=comment.id,
        mentor_id=mentor.id,
        mentor_name=mentor.first_name,
        mentor_telegram_username=mentor.telegram_username,
        question_id=comment.question_id,
        timestamp_ms=comment.timestamp_ms,
        text=comment.text,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
    )


async def review_action(
    session: AsyncSession,
    mentor: User,
    interview_id: UUID,
    review_id: UUID,
    *,
    action: str,
    rejection_reason: str | None = None,
    edit: IntelligenceReviewEditMutation | None = None,
) -> IntelligenceReviewRead:
    interview = await get_intelligence_interview(session, mentor, interview_id)
    review = await session.scalar(
        select(IntelligenceAnswerReview)
        .join(IntelligenceAnswer, IntelligenceAnswer.id == IntelligenceAnswerReview.answer_id)
        .join(IntelligenceQuestion, IntelligenceQuestion.id == IntelligenceAnswer.question_id)
        .where(
            IntelligenceAnswerReview.id == review_id,
            IntelligenceQuestion.interview_id == interview.id,
            IntelligenceAnswerReview.source == IntelligenceReviewSource.AI,
        )
        .with_for_update()
    )
    if review is None:
        api_error(404, "intelligence_review_not_found", "AI review was not found")
    if action == "approve":
        review.status = IntelligenceReviewStatus.APPROVED
        result = review
    elif action == "reject":
        review.status = IntelligenceReviewStatus.REJECTED
        review.rejection_reason = rejection_reason or "other"
        result = review
    elif action == "edit" and edit is not None:
        review.status = IntelligenceReviewStatus.EDITED
        result = IntelligenceAnswerReview(
            answer_id=review.answer_id,
            parent_review_id=review.id,
            source=IntelligenceReviewSource.MENTOR,
            status=IntelligenceReviewStatus.APPROVED,
            assessment=edit.assessment,
            score=edit.score,
            summary=edit.summary,
            strengths=edit.strengths,
            problems=edit.problems,
            missing_points=edit.missing_points,
            incorrect_statements=edit.incorrect_statements,
            suggested_better_answer=edit.suggested_better_answer,
            created_by_user_id=mentor.id,
        )
        session.add(result)
    else:
        raise ValueError("Unknown review action")
    await session.commit()
    await session.refresh(result)
    return _review_read(result)


async def complete_interview_review(
    session: AsyncSession,
    reviewer: User,
    interview_id: UUID,
) -> IntelligenceInterview:
    interview = await get_intelligence_interview(session, reviewer, interview_id, lock=True)
    if interview.processing_status is not IntelligenceProcessingStatus.READY:
        api_error(409, "intelligence_review_not_ready", "Interview analysis is not ready")
    pending = int(
        await session.scalar(
            select(func.count(IntelligenceAnswerReview.id))
            .join(IntelligenceAnswer, IntelligenceAnswer.id == IntelligenceAnswerReview.answer_id)
            .join(IntelligenceQuestion, IntelligenceQuestion.id == IntelligenceAnswer.question_id)
            .where(
                IntelligenceQuestion.interview_id == interview.id,
                IntelligenceAnswerReview.source == IntelligenceReviewSource.AI,
                IntelligenceAnswerReview.status == IntelligenceReviewStatus.SUGGESTED,
            )
        )
        or 0
    )
    if pending:
        api_error(
            409,
            "intelligence_reviews_pending",
            "Resolve all AI recommendations before completing the review",
        )
    unmoderated_questions = int(
        await session.scalar(
            select(func.count(IntelligenceQuestion.id)).where(
                IntelligenceQuestion.interview_id == interview.id,
                IntelligenceQuestion.moderation_status.in_(
                    [
                        IntelligenceQuestionModerationStatus.PENDING,
                        IntelligenceQuestionModerationStatus.MENTOR_APPROVED,
                    ]
                ),
            )
        )
        or 0
    )
    if unmoderated_questions:
        api_error(
            409,
            "intelligence_questions_pending_moderation",
            "Approve or reject every extracted question before completing the review",
        )
    interview.reviewed_at = datetime.now(UTC)
    interview.reviewed_by_user_id = reviewer.id
    await session.commit()
    return interview


async def prepare_interview_overview_generation(
    session: AsyncSession,
    reviewer: User,
    interview_id: UUID,
) -> IntelligenceInterview:
    interview = await get_intelligence_interview(session, reviewer, interview_id, lock=True)
    if interview.processing_status is not IntelligenceProcessingStatus.READY:
        api_error(409, "intelligence_summary_not_ready", "Interview analysis is not ready")
    has_transcript = await session.scalar(
        select(IntelligenceUtterance.id)
        .where(IntelligenceUtterance.interview_id == interview.id)
        .limit(1)
    )
    if has_transcript is None or interview.candidate_speaker_id is None:
        api_error(
            409,
            "intelligence_summary_unavailable",
            "Transcript and candidate speaker are required",
        )
    interview.ai_summary_payload = None
    interview.ai_summary_model = None
    interview.ai_summary_prompt_version = None
    interview.processing_status = IntelligenceProcessingStatus.ANALYZING
    interview.failed_stage = None
    interview.processing_error_code = None
    interview.processing_error_message = None
    await session.commit()
    return interview


async def mark_upload_complete(
    session: AsyncSession,
    user: User,
    interview_id: UUID,
    *,
    storage_key: str,
    filename: str,
    content_type: str,
    size: int,
) -> str | None:
    interview = await get_intelligence_interview(
        session, user, interview_id, owner_only=True, lock=True
    )
    stage = await session.get(InterviewProcessStage, interview.stage_id, with_for_update=True)
    assert stage is not None
    previous_key = stage.media_storage_key
    stage.media_storage_key = storage_key
    stage.media_filename = filename
    stage.media_content_type = content_type
    stage.media_size = size
    interview.processing_status = IntelligenceProcessingStatus.UPLOADED
    interview.failed_stage = None
    interview.processing_error_code = None
    interview.processing_error_message = None
    await session.commit()
    return previous_key


async def delete_intelligence_interview(
    session: AsyncSession, user: User, interview_id: UUID
) -> list[str]:
    interview = await get_intelligence_interview(session, user, interview_id, owner_only=True)
    if user.role is not UserRole.ADMIN and interview.student_id != user.id:
        api_error(404, "intelligence_interview_not_found", "Interview was not found")
    keys = [interview.normalized_audio_key] if interview.normalized_audio_key else []
    await session.delete(interview)
    await session.commit()
    return keys


async def moderate_intelligence_question(
    session: AsyncSession,
    reviewer: User,
    interview_id: UUID,
    question_id: UUID,
    payload: IntelligenceQuestionModerationMutation,
) -> IntelligenceInterview:
    interview = await get_intelligence_interview(session, reviewer, interview_id)
    question = await session.scalar(
        select(IntelligenceQuestion)
        .where(
            IntelligenceQuestion.id == question_id,
            IntelligenceQuestion.interview_id == interview.id,
        )
        .with_for_update()
    )
    if question is None:
        api_error(404, "intelligence_question_not_found", "Question was not found")
    now = datetime.now(UTC)
    if payload.action == "recommend":
        question.moderation_status = IntelligenceQuestionModerationStatus.MENTOR_APPROVED
        question.mentor_reviewed_by_user_id = reviewer.id
        question.mentor_reviewed_at = now
    elif payload.action == "reject":
        question.moderation_status = IntelligenceQuestionModerationStatus.REJECTED
        if reviewer.role is UserRole.ADMIN:
            question.admin_reviewed_by_user_id = reviewer.id
            question.admin_reviewed_at = now
        else:
            question.mentor_reviewed_by_user_id = reviewer.id
            question.mentor_reviewed_at = now
    elif payload.action == "approve":
        if reviewer.role is not UserRole.ADMIN:
            api_error(403, "admin_access_required", "Only an admin can publish a question")
        question_text = (payload.question_markdown or question.question_text).strip()
        answer_text = (payload.answer_markdown or "").strip()
        category = (payload.category or question.category).strip()
        if not answer_text:
            api_error(422, "interview_card_answer_required", "A verified answer is required")
        stage = await session.get(InterviewProcessStage, interview.stage_id)
        if stage is None:
            api_error(409, "interview_process_missing", "Interview process was not found")
        process = await session.get(InterviewProcess, stage.process_id)
        if process is None:
            api_error(409, "interview_process_missing", "Interview process was not found")
        deck = await session.scalar(
            select(InterviewDeck)
            .where(InterviewDeck.track_id == process.track_id, InterviewDeck.is_published.is_(True))
            .order_by(InterviewDeck.position, InterviewDeck.created_at)
        )
        if deck is None:
            api_error(409, "interview_deck_missing", "Publish a question deck for this direction")
        card = await session.scalar(
            select(InterviewCard).where(
                InterviewCard.deck_id == deck.id,
                func.lower(func.trim(InterviewCard.question_markdown)) == question_text.casefold(),
            )
        )
        if card is None:
            max_position_value = await session.scalar(
                select(func.max(InterviewCard.position)).where(InterviewCard.deck_id == deck.id)
            )
            max_position = -1 if max_position_value is None else int(max_position_value)
            card = InterviewCard(
                deck_id=deck.id,
                slug=f"ai-{question.id.hex}",
                category=category,
                companies=process.company_name,
                question_markdown=question_text,
                answer_markdown=answer_text,
                frequency=payload.frequency,
                position=max_position + 1,
                is_published=True,
            )
            session.add(card)
            await session.flush()
        question.moderation_status = IntelligenceQuestionModerationStatus.APPROVED
        question.admin_reviewed_by_user_id = reviewer.id
        question.admin_reviewed_at = now
        question.published_card_id = card.id

        candidate_answer = await session.scalar(
            select(IntelligenceAnswer).where(IntelligenceAnswer.question_id == question.id)
        )
        if candidate_answer is None or not candidate_answer.answer_text.strip():
            selection = await session.get(
                InterviewTopicSelection,
                {"user_id": interview.student_id, "deck_id": deck.id, "category": card.category},
            )
            if selection is None:
                session.add(
                    InterviewTopicSelection(
                        user_id=interview.student_id,
                        deck_id=deck.id,
                        category=card.category,
                    )
                )
            progress = await session.get(
                InterviewCardProgress,
                {"user_id": interview.student_id, "card_id": card.id},
            )
            if progress is None:
                session.add(
                    InterviewCardProgress(
                        user_id=interview.student_id,
                        card_id=card.id,
                        repetitions=0,
                        interval_days=0,
                        due_at=now,
                    )
                )
    else:
        raise ValueError("Unknown moderation action")
    await session.commit()
    return interview


def _review_read(review: IntelligenceAnswerReview) -> IntelligenceReviewRead:
    return IntelligenceReviewRead(
        id=review.id,
        parent_review_id=review.parent_review_id,
        source=review.source,
        status=review.status,
        assessment=review.assessment,
        score=review.score,
        summary=review.summary,
        strengths=review.strengths,
        problems=review.problems,
        missing_points=review.missing_points,
        incorrect_statements=review.incorrect_statements,
        suggested_better_answer=review.suggested_better_answer,
        model_name=review.model_name,
        prompt_version=review.prompt_version,
        created_by_user_id=review.created_by_user_id,
        rejection_reason=review.rejection_reason,
        created_at=review.created_at,
    )


def safe_processing_message(code: str) -> str:
    messages = {
        "TRANSCRIPTION_TIMEOUT": "Сервис транскрибации не ответил вовремя.",
        "TRANSCRIPTION_PROVIDER_ERROR": "Не удалось обработать запись в сервисе транскрибации.",
        "TRANSCRIPTION_INVALID_RESPONSE": "Сервис транскрибации вернул некорректный результат.",
        "OPENAI_PROXY_ERROR": "Не удалось подключиться к сервису анализа.",
        "OPENAI_AUTH_ERROR": "Сервис анализа временно недоступен.",
        "OPENAI_QUOTA_EXCEEDED": "Квота сервиса анализа исчерпана. Обратитесь к администратору.",
        "OPENAI_RATE_LIMIT": "Сервис анализа перегружен. Повторите позднее.",
        "OPENAI_INVALID_RESPONSE": "Не удалось разобрать результат AI-анализа.",
        "STORAGE_ERROR": "Не удалось прочитать запись из хранилища.",
    }
    return messages.get(code, "Не удалось обработать интервью.")
