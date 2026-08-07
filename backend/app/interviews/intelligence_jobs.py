from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from arq import Retry, cron
from arq import func as arq_func
from arq.connections import RedisSettings
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db import models as _db_models  # noqa: F401
from app.db.session import async_session_factory
from app.interviews.intelligence_ai import (
    LIGHT_REVIEW_PROMPT_VERSION,
    SUMMARY_PROMPT_VERSION,
    TECHNICAL_REVIEW_PROMPT_VERSION,
    CommunicationDimension,
    InterviewAIError,
    InterviewAIProvider,
    InterviewSummaryOutput,
    build_ai_provider,
    transcript_chunks,
)
from app.interviews.intelligence_models import (
    IntelligenceAIUsage,
    IntelligenceAnswer,
    IntelligenceAnswerReview,
    IntelligenceAttemptStage,
    IntelligenceAttemptStatus,
    IntelligenceInterview,
    IntelligenceProcessingAttempt,
    IntelligenceProcessingStatus,
    IntelligenceQuestion,
    IntelligenceQuestionKind,
    IntelligenceReviewSource,
    IntelligenceReviewStatus,
    IntelligenceSpeaker,
    IntelligenceSpeakerRole,
    IntelligenceTranscriptionUsage,
    IntelligenceUtterance,
)
from app.interviews.intelligence_providers import (
    TranscriptionJobState,
    TranscriptionProvider,
    TranscriptionProviderError,
    TranscriptionResult,
    build_transcription_provider,
)
from app.interviews.intelligence_queue import (
    OPENAI_QUEUE_NAME,
    TRANSCRIPTION_QUEUE_NAME,
    enqueue_intelligence_job,
)
from app.interviews.intelligence_recovery import (
    intelligence_recovery_job_name as _recovery_job_name,
)
from app.interviews.intelligence_service import safe_processing_message
from app.interviews.media_guardrails import (
    MediaGuardrailError,
    StagingCapacityError,
    StagingGuard,
    cleanup_stale_staging_directories,
    probe_media_async,
    stage_media_file,
)
from app.interviews.models import (
    InterviewProcess,
    InterviewProcessStage,
    InterviewStageComment,
)
from app.interviews.question_embeddings import refresh_track_question_embeddings
from app.interviews.uploads import (
    InterviewStorageReadError,
    InterviewUploadStore,
    StoredUpload,
)

logger = logging.getLogger(__name__)
settings = get_settings()
MAX_JOB_TRIES = 4
DEFAULT_TRANSCRIPTION_POLL_DEADLINE_SECONDS = 6 * 60 * 60
TRANSCRIPTION_POLL_INTERVAL_SECONDS = 60
POLL_MAX_TRIES = 10_000
RECONCILIATION_MINUTES = set(range(0, 60, 5))
WORKER_HEALTH_CHECK_INTERVAL_SECONDS = 30


async def startup(ctx: dict[str, Any]) -> None:
    ctx["transcription_provider"] = build_transcription_provider(settings)
    ctx["ai_provider"] = build_ai_provider(settings)
    ctx["upload_store"] = InterviewUploadStore(settings)
    _configure_media_staging(ctx)


async def shutdown(ctx: dict[str, Any]) -> None:
    await _transcription(ctx).close()
    await _ai(ctx).close()


async def transcription_startup(ctx: dict[str, Any]) -> None:
    ctx["transcription_provider"] = build_transcription_provider(settings)
    ctx["upload_store"] = InterviewUploadStore(settings)
    _configure_media_staging(ctx)


async def transcription_shutdown(ctx: dict[str, Any]) -> None:
    await _transcription(ctx).close()


async def ai_startup(ctx: dict[str, Any]) -> None:
    ctx["ai_provider"] = build_ai_provider(settings)


async def ai_shutdown(ctx: dict[str, Any]) -> None:
    await _ai(ctx).close()


async def reconcile_intelligence_jobs(ctx: dict[str, Any]) -> None:
    """Re-enqueue recoverable DB states after a worker/Redis interruption."""
    completed_extraction = (
        select(IntelligenceProcessingAttempt.id)
        .where(
            IntelligenceProcessingAttempt.interview_id == IntelligenceInterview.id,
            IntelligenceProcessingAttempt.stage == IntelligenceAttemptStage.AI_EXTRACT,
            IntelligenceProcessingAttempt.status == IntelligenceAttemptStatus.COMPLETED,
        )
        .exists()
    )
    recoverable_statuses = (
        IntelligenceProcessingStatus.UPLOADED,
        IntelligenceProcessingStatus.TRANSCRIPTION_SUBMITTED,
        IntelligenceProcessingStatus.TRANSCRIBING,
        IntelligenceProcessingStatus.TRANSCRIPT_READY,
        IntelligenceProcessingStatus.ANALYZING,
    )
    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(
                    IntelligenceInterview.id,
                    IntelligenceInterview.processing_status,
                    IntelligenceInterview.transcription_provider_job_id,
                    IntelligenceInterview.candidate_speaker_id,
                    completed_extraction.label("completed_extraction"),
                )
                .where(IntelligenceInterview.processing_status.in_(recoverable_statuses))
                .order_by(IntelligenceInterview.updated_at, IntelligenceInterview.id)
            )
        ).all()

    scheduled = 0
    for (
        interview_id,
        status,
        transcription_provider_job_id,
        candidate_speaker_id,
        extraction_completed,
    ) in rows:
        function = _recovery_job_name(
            status,
            transcription_provider_job_id=transcription_provider_job_id,
            candidate_speaker_selected=candidate_speaker_id is not None,
            extraction_completed=bool(extraction_completed),
        )
        if function is None:
            continue
        if function == "generate_answer_reviews":
            await _enqueue(ctx, "refresh_interview_question_embeddings", str(interview_id))
        await _enqueue(ctx, function, str(interview_id))
        scheduled += 1
    if scheduled:
        logger.info("Reconciled interview processing jobs count=%s", scheduled)


async def submit_transcription(ctx: dict[str, Any], interview_id: str) -> None:
    parsed_id = UUID(interview_id)
    async with async_session_factory() as session:
        interview = await _interview(session, parsed_id, lock=True)
        if interview.processing_status in {
            IntelligenceProcessingStatus.AWAITING_CANDIDATE_SPEAKER,
            IntelligenceProcessingStatus.ANALYZING,
            IntelligenceProcessingStatus.READY,
            IntelligenceProcessingStatus.FAILED,
        }:
            return
        if interview.transcription_provider_job_id:
            await _enqueue(ctx, "poll_transcription", interview_id)
            return
        stage = await session.get(InterviewProcessStage, interview.stage_id)
        if (
            stage is None
            or stage.media_storage_key is None
            or stage.media_filename is None
            or stage.media_content_type is None
        ):
            await _fail(
                session,
                interview,
                IntelligenceAttemptStage.TRANSCRIPTION_SUBMIT,
                "STORAGE_ERROR",
            )
            return
        attempt = await _start_attempt(
            session,
            interview.id,
            IntelligenceAttemptStage.TRANSCRIPTION_SUBMIT,
            _transcription(ctx).name,
        )
        upload = StoredUpload(
            storage_key=stage.media_storage_key,
            filename=stage.media_filename,
            content_type=stage.media_content_type,
            size=stage.media_size or 0,
        )
        try:
            provider = _transcription(ctx)
            if provider.requires_file_upload:
                upload = await _store(ctx).resolve_upload_size(upload)
                if stage.media_size != upload.size:
                    stage.media_size = upload.size
                # Legacy migrated recordings can be filed as .mp3 while actually
                # being an m4a/ALAC container; correct the declared type before
                # probing so it isn't rejected as a MEDIA_CONTENT_TYPE_MISMATCH.
                playable = await _store(ctx).ensure_browser_playable(upload)
                if playable != upload:
                    stage.media_storage_key = playable.storage_key
                    stage.media_filename = playable.filename
                    stage.media_content_type = playable.content_type
                    stage.media_size = playable.size
                    upload = playable
                maximum_bytes = _media_size_limit(upload.content_type)
                if upload.size <= 0:
                    raise MediaGuardrailError("invalid_media_file", "Interview recording is empty")
                if upload.size > maximum_bytes:
                    raise MediaGuardrailError(
                        "media_file_too_large", "Interview recording is too large"
                    )
                async with stage_media_file(
                    _staging_guard(ctx),
                    filename=upload.filename,
                    maximum_bytes=upload.size,
                    expected_bytes=upload.size,
                    download=partial(_store(ctx).download_to_path, upload),
                    staging_root=_staging_root(),
                ) as file_path:
                    probe = await probe_media_async(
                        file_path,
                        declared_content_type=upload.content_type,
                        max_duration_seconds=settings.interview_media_max_duration_seconds,
                        max_file_bytes=upload.size,
                        timeout_seconds=settings.interview_media_probe_timeout_seconds,
                    )
                    interview.duration_ms = round(probe.duration_seconds * 1_000)
                    job = await provider.submit(
                        file_url=None,
                        file_path=file_path,
                        language=None,
                        diarization=True,
                        timestamps=True,
                    )
            else:
                job = await provider.submit(
                    file_url=_store(ctx).download_url(upload, inline=True),
                    file_path=None,
                    language=None,
                    diarization=True,
                    timestamps=True,
                )
        except StagingCapacityError as error:
            provider_error = TranscriptionProviderError(
                "STAGING_CAPACITY_EXCEEDED",
                (
                    f"Interview staging capacity is unavailable: {error.reason}; "
                    f"required={error.required_bytes}; available={error.available_bytes}"
                ),
                retryable=True,
            )
            will_retry = _will_retry(ctx, provider_error.retryable)
            await _provider_failure(
                session, interview, attempt, provider_error, retryable=will_retry
            )
            if will_retry:
                raise Retry(defer=_retry_delay(ctx, 60)) from error
            return
        except MediaGuardrailError as error:
            retryable = error.code in {"media_probe_timeout", "media_probe_unavailable"}
            provider_error = TranscriptionProviderError(
                error.code.upper(),
                str(error),
                retryable=retryable,
            )
            will_retry = _will_retry(ctx, provider_error.retryable)
            await _provider_failure(
                session, interview, attempt, provider_error, retryable=will_retry
            )
            if will_retry:
                raise Retry(defer=_retry_delay(ctx, 60)) from error
            return
        except InterviewStorageReadError as error:
            provider_error = TranscriptionProviderError(
                "STORAGE_ERROR",
                "Interview recording could not be read from storage",
                retryable=True,
            )
            will_retry = _will_retry(ctx, provider_error.retryable)
            await _provider_failure(
                session, interview, attempt, provider_error, retryable=will_retry
            )
            if will_retry:
                raise Retry(defer=_retry_delay(ctx, 60)) from error
            return
        except TranscriptionProviderError as error:
            will_retry = _will_retry(ctx, error.retryable)
            await _provider_failure(session, interview, attempt, error, retryable=will_retry)
            if will_retry:
                raise Retry(defer=_retry_delay(ctx, 60)) from error
            return
        interview.transcription_provider = _transcription(ctx).name
        interview.transcription_provider_job_id = job.provider_job_id
        interview.transcription_provider_payload = job.raw_payload
        interview.processing_status = IntelligenceProcessingStatus.TRANSCRIPTION_SUBMITTED
        attempt.external_request_id = job.provider_job_id
        _complete_attempt(attempt)
        await session.commit()
    await _enqueue(ctx, "poll_transcription", interview_id, defer_seconds=30)


async def poll_transcription(ctx: dict[str, Any], interview_id: str) -> None:
    parsed_id = UUID(interview_id)
    async with async_session_factory() as session:
        interview = await _interview(session, parsed_id, lock=True)
        if interview.processing_status in {
            IntelligenceProcessingStatus.AWAITING_CANDIDATE_SPEAKER,
            IntelligenceProcessingStatus.ANALYZING,
            IntelligenceProcessingStatus.READY,
            IntelligenceProcessingStatus.FAILED,
        }:
            return
        provider_job_id = interview.transcription_provider_job_id
        if not provider_job_id:
            await _enqueue(ctx, "submit_transcription", interview_id)
            return
        deadline_at = await _transcription_poll_deadline_at(session, interview)
        if _deadline_reached(deadline_at):
            await _fail(
                session,
                interview,
                IntelligenceAttemptStage.TRANSCRIPTION_POLL,
                "TRANSCRIPTION_TIMEOUT",
            )
            return
        attempt = await _start_attempt(
            session,
            interview.id,
            IntelligenceAttemptStage.TRANSCRIPTION_POLL,
            _transcription(ctx).name,
        )
        try:
            job = await _transcription(ctx).get_status(provider_job_id)
        except TranscriptionProviderError as error:
            if _deadline_reached(deadline_at):
                await _record_failure(
                    session,
                    interview,
                    attempt,
                    "TRANSCRIPTION_TIMEOUT",
                    safe_processing_message("TRANSCRIPTION_TIMEOUT"),
                    False,
                )
                return
            will_retry = error.retryable
            await _provider_failure(session, interview, attempt, error, retryable=will_retry)
            if will_retry:
                raise Retry(
                    defer=_bounded_poll_delay(deadline_at, _retry_delay(ctx, 120))
                ) from error
            return
        interview.transcription_provider_payload = job.raw_payload
        if job.status in {TranscriptionJobState.QUEUED, TranscriptionJobState.PROCESSING}:
            if _deadline_reached(deadline_at):
                await _record_failure(
                    session,
                    interview,
                    attempt,
                    "TRANSCRIPTION_TIMEOUT",
                    safe_processing_message("TRANSCRIPTION_TIMEOUT"),
                    False,
                )
                return
            interview.processing_status = IntelligenceProcessingStatus.TRANSCRIBING
            _complete_attempt(attempt)
            await session.commit()
            raise Retry(
                defer=_bounded_poll_delay(
                    deadline_at,
                    TRANSCRIPTION_POLL_INTERVAL_SECONDS,
                )
            )
        _complete_attempt(attempt)
        await session.commit()
    await _enqueue(ctx, "process_transcription_result", interview_id)


async def process_transcription_result(ctx: dict[str, Any], interview_id: str) -> None:
    parsed_id = UUID(interview_id)
    async with async_session_factory() as session:
        interview = await _interview(session, parsed_id, lock=True)
        if interview.processing_status in {
            IntelligenceProcessingStatus.AWAITING_CANDIDATE_SPEAKER,
            IntelligenceProcessingStatus.ANALYZING,
            IntelligenceProcessingStatus.READY,
            IntelligenceProcessingStatus.FAILED,
        }:
            return
        existing = await session.scalar(
            select(func.count(IntelligenceUtterance.id)).where(
                IntelligenceUtterance.interview_id == interview.id
            )
        )
        if existing:
            interview.processing_status = IntelligenceProcessingStatus.AWAITING_CANDIDATE_SPEAKER
            await session.commit()
            return
        if not interview.transcription_provider_job_id:
            await _enqueue(ctx, "submit_transcription", interview_id)
            return
        attempt = await _start_attempt(
            session,
            interview.id,
            IntelligenceAttemptStage.TRANSCRIPTION_PARSE,
            _transcription(ctx).name,
        )
        try:
            result = await _transcription(ctx).get_result(interview.transcription_provider_job_id)
            await _save_transcript(session, interview, result)
        except TranscriptionProviderError as error:
            will_retry = _will_retry(ctx, error.retryable)
            await _provider_failure(session, interview, attempt, error, retryable=will_retry)
            if will_retry:
                raise Retry(defer=_retry_delay(ctx, 120)) from error
            return
        interview.duration_ms = result.duration_ms
        interview.transcription_provider_payload = result.raw_payload
        interview.processing_status = IntelligenceProcessingStatus.AWAITING_CANDIDATE_SPEAKER
        interview.failed_stage = None
        interview.processing_error_code = None
        interview.processing_error_message = None
        session.add(
            IntelligenceTranscriptionUsage(
                interview_id=interview.id,
                provider=_transcription(ctx).name,
                duration_ms=result.duration_ms,
                provider_job_id=interview.transcription_provider_job_id,
            )
        )
        _complete_attempt(attempt)
        await session.commit()


async def extract_interview_structure(ctx: dict[str, Any], interview_id: str) -> None:
    parsed_id = UUID(interview_id)
    async with async_session_factory() as session:
        interview = await _interview(session, parsed_id, lock=True)
        if interview.processing_status in {
            IntelligenceProcessingStatus.READY,
            IntelligenceProcessingStatus.FAILED,
        }:
            return
        if interview.candidate_speaker_id is None:
            return
        existing_questions = await session.scalar(
            select(func.count(IntelligenceQuestion.id)).where(
                IntelligenceQuestion.interview_id == interview.id
            )
        )
        if existing_questions:
            await _enqueue(ctx, "refresh_interview_question_embeddings", interview_id)
            await _enqueue(ctx, "generate_answer_reviews", interview_id)
            return
        attempt = await _start_attempt(
            session,
            interview.id,
            IntelligenceAttemptStage.AI_EXTRACT,
            _ai(ctx).name,
        )
        utterances = list(
            await session.scalars(
                select(IntelligenceUtterance)
                .where(IntelligenceUtterance.interview_id == interview.id)
                .order_by(IntelligenceUtterance.sequence_number)
            )
        )
        speakers = {
            speaker.id: speaker
            for speaker in await session.scalars(
                select(IntelligenceSpeaker).where(IntelligenceSpeaker.interview_id == interview.id)
            )
        }
        blocks = [
            _utterance_block(
                item,
                "Candidate"
                if item.speaker_id == interview.candidate_speaker_id
                else f"Speaker {speakers[item.speaker_id].provider_speaker_key}",
            )
            for item in utterances
        ]
        extracted = []
        usages = []
        try:
            for chunk in transcript_chunks(blocks):
                result = await _ai(ctx).extract(chunk)
                extracted.extend(result.output.questions)
                usages.append(result.usage)
        except InterviewAIError as error:
            will_retry = _will_retry(ctx, error.retryable)
            await _ai_failure(session, interview, attempt, error, retryable=will_retry)
            if will_retry:
                raise Retry(defer=_retry_delay(ctx, 60)) from error
            return
        by_label = {f"U{item.sequence_number:03d}": item for item in utterances}
        seen_ranges: set[tuple[str, ...]] = set()
        sequence = 0
        for item in extracted:
            range_key = tuple(item.question_utterance_ids)
            if range_key in seen_ranges:
                continue
            question_utterances = [
                by_label[key] for key in item.question_utterance_ids if key in by_label
            ]
            answer_utterances = [
                by_label[key] for key in item.answer_utterance_ids if key in by_label
            ]
            if len(question_utterances) != len(item.question_utterance_ids):
                continue
            if any(row.speaker_id == interview.candidate_speaker_id for row in question_utterances):
                continue
            answer_utterances = [
                row for row in answer_utterances if row.speaker_id == interview.candidate_speaker_id
            ]
            sequence += 1
            seen_ranges.add(range_key)
            question = IntelligenceQuestion(
                interview_id=interview.id,
                sequence_number=sequence,
                question_text=item.question,
                question_start_ms=min(row.start_ms for row in question_utterances),
                question_end_ms=max(row.end_ms for row in question_utterances),
                answer_start_ms=(
                    min(row.start_ms for row in answer_utterances) if answer_utterances else None
                ),
                answer_end_ms=(
                    max(row.end_ms for row in answer_utterances) if answer_utterances else None
                ),
                question_utterance_ids=[row.id for row in question_utterances],
                answer_utterance_ids=[row.id for row in answer_utterances],
                category=item.category.casefold(),
                question_kind=item.question_kind,
                subcategory=item.subcategory,
                difficulty=item.difficulty,
                confidence=item.confidence,
            )
            session.add(question)
            await session.flush()
            session.add(
                IntelligenceAnswer(
                    question_id=question.id,
                    student_id=interview.student_id,
                    answer_text="\n".join(row.text for row in answer_utterances),
                    start_ms=question.answer_start_ms,
                    end_ms=question.answer_end_ms,
                )
            )
        for usage in usages:
            session.add(
                IntelligenceAIUsage(
                    interview_id=interview.id,
                    provider=_ai(ctx).name,
                    model=usage.model,
                    operation="extraction",
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    provider_request_id=usage.provider_request_id,
                )
            )
        interview.processing_status = IntelligenceProcessingStatus.ANALYZING
        _complete_attempt(attempt)
        await session.commit()
    await _enqueue(ctx, "refresh_interview_question_embeddings", interview_id)
    await _enqueue(ctx, "generate_answer_reviews", interview_id)


async def refresh_interview_question_embeddings(ctx: dict[str, Any], interview_id: str) -> None:
    """Refresh cached question vectors without affecting the main AI pipeline state."""

    parsed_id = UUID(interview_id)
    async with async_session_factory() as session:
        interview = await session.get(IntelligenceInterview, parsed_id)
        if interview is None:
            return
        stage = await session.get(InterviewProcessStage, interview.stage_id)
        process = await session.get(InterviewProcess, stage.process_id) if stage else None
        if process is None:
            logger.warning(
                "Question embedding refresh skipped interview_id=%s reason=process_missing",
                parsed_id,
            )
            return
        questions = list(
            await session.scalars(
                select(IntelligenceQuestion)
                .where(IntelligenceQuestion.interview_id == parsed_id)
                .order_by(IntelligenceQuestion.sequence_number, IntelligenceQuestion.id)
            )
        )
        if not questions:
            return
        try:
            refresh = await refresh_track_question_embeddings(
                session,
                _ai(ctx),
                process.track_id,
                questions,
            )
        except InterviewAIError as error:
            await session.rollback()
            will_retry = _will_retry(ctx, error.retryable)
            logger.warning(
                "Question embedding refresh failed interview_id=%s code=%s retryable=%s",
                parsed_id,
                error.code,
                will_retry,
            )
            if will_retry:
                raise Retry(defer=_retry_delay(ctx, 60)) from error
            return
        for usage in refresh.usages:
            session.add(
                IntelligenceAIUsage(
                    interview_id=interview.id,
                    provider=_ai(ctx).name,
                    model=usage.model,
                    operation="embedding",
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    provider_request_id=usage.provider_request_id,
                )
            )
        await session.commit()


async def generate_answer_reviews(ctx: dict[str, Any], interview_id: str) -> None:
    parsed_id = UUID(interview_id)
    async with async_session_factory() as session:
        interview = await _interview(session, parsed_id, lock=True)
        if interview.processing_status in {
            IntelligenceProcessingStatus.READY,
            IntelligenceProcessingStatus.FAILED,
        }:
            return
        attempt = await _start_attempt(
            session,
            interview.id,
            IntelligenceAttemptStage.AI_REVIEW,
            _ai(ctx).name,
        )
        rows = (
            await session.execute(
                select(IntelligenceQuestion, IntelligenceAnswer)
                .join(IntelligenceAnswer, IntelligenceAnswer.question_id == IntelligenceQuestion.id)
                .where(IntelligenceQuestion.interview_id == interview.id)
                .order_by(IntelligenceQuestion.sequence_number)
            )
        ).all()
        utterances = list(
            await session.scalars(
                select(IntelligenceUtterance)
                .where(IntelligenceUtterance.interview_id == interview.id)
                .order_by(IntelligenceUtterance.sequence_number)
            )
        )
        speakers = {
            speaker.id: speaker
            for speaker in await session.scalars(
                select(IntelligenceSpeaker).where(IntelligenceSpeaker.interview_id == interview.id)
            )
        }
        summary_usages = []
        try:
            for question, answer in rows:
                exists = await session.scalar(
                    select(IntelligenceAnswerReview.id).where(
                        IntelligenceAnswerReview.answer_id == answer.id,
                        IntelligenceAnswerReview.source == IntelligenceReviewSource.AI,
                    )
                )
                if exists is not None:
                    continue
                context = (
                    _neighbor_context(
                        question,
                        utterances,
                        speakers,
                        interview.candidate_speaker_id,
                    )
                    if question.question_kind is IntelligenceQuestionKind.TECHNICAL
                    else ""
                )
                result = await _ai(ctx).review(
                    question=question.question_text,
                    answer=answer.answer_text,
                    category=question.category,
                    question_kind=question.question_kind,
                    context=context,
                )
                review = result.output
                session.add(
                    IntelligenceAnswerReview(
                        answer_id=answer.id,
                        source=IntelligenceReviewSource.AI,
                        status=IntelligenceReviewStatus.SUGGESTED,
                        assessment=review.assessment,
                        score=review.score,
                        summary=review.summary,
                        strengths=[item.model_dump(mode="json") for item in review.strengths],
                        problems=[item.model_dump(mode="json") for item in review.problems],
                        missing_points=review.missing_points,
                        incorrect_statements=[
                            item.model_dump(mode="json") for item in review.incorrect_statements
                        ],
                        suggested_better_answer=review.suggested_better_answer,
                        model_name=result.usage.model,
                        prompt_version=(
                            TECHNICAL_REVIEW_PROMPT_VERSION
                            if question.question_kind is IntelligenceQuestionKind.TECHNICAL
                            else LIGHT_REVIEW_PROMPT_VERSION
                        ),
                    )
                )
                session.add(
                    IntelligenceAIUsage(
                        interview_id=interview.id,
                        question_id=question.id,
                        provider=_ai(ctx).name,
                        model=result.usage.model,
                        operation=(
                            "technical_evaluation"
                            if question.question_kind is IntelligenceQuestionKind.TECHNICAL
                            else "light_evaluation"
                        ),
                        input_tokens=result.usage.input_tokens,
                        output_tokens=result.usage.output_tokens,
                        provider_request_id=result.usage.provider_request_id,
                    )
                )
            if interview.ai_summary_payload is None:
                blocks = [
                    _utterance_block(
                        item,
                        "Candidate"
                        if item.speaker_id == interview.candidate_speaker_id
                        else f"Speaker {speakers[item.speaker_id].provider_speaker_key}",
                    )
                    for item in utterances
                ]
                summary_results = [
                    await _ai(ctx).summarize(chunk) for chunk in transcript_chunks(blocks)
                ]
                if summary_results:
                    overview = _merge_interview_summaries(
                        [result.output for result in summary_results]
                    )
                    summary_usages = [result.usage for result in summary_results]
                    interview.ai_summary_payload = overview.model_dump(mode="json")
                    interview.ai_summary_model = summary_usages[-1].model
                    interview.ai_summary_prompt_version = SUMMARY_PROMPT_VERSION
        except InterviewAIError as error:
            will_retry = _will_retry(ctx, error.retryable)
            await _ai_failure(session, interview, attempt, error, retryable=will_retry)
            if will_retry:
                raise Retry(defer=_retry_delay(ctx, 60)) from error
            return
        for usage in summary_usages:
            session.add(
                IntelligenceAIUsage(
                    interview_id=interview.id,
                    provider=_ai(ctx).name,
                    model=usage.model,
                    operation="summary",
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    provider_request_id=usage.provider_request_id,
                )
            )
        interview.processing_status = IntelligenceProcessingStatus.READY
        interview.failed_stage = None
        interview.processing_error_code = None
        interview.processing_error_message = None
        await session.flush()
        await _upsert_ai_stage_comment(session, interview)
        _complete_attempt(attempt)
        await session.commit()


def _neighbor_context(
    question: IntelligenceQuestion,
    utterances: list[IntelligenceUtterance],
    speakers: dict[UUID, IntelligenceSpeaker],
    candidate_speaker_id: UUID | None,
    *,
    limit: int = 3,
) -> str:
    included_ids = set(question.question_utterance_ids) | set(question.answer_utterance_ids)
    included_positions = [
        index for index, utterance in enumerate(utterances) if utterance.id in included_ids
    ]
    if not included_positions:
        return ""
    first = min(included_positions)
    last = max(included_positions)
    selected: list[int] = []
    distance = 1
    while len(selected) < limit and (first - distance >= 0 or last + distance < len(utterances)):
        left = first - distance
        right = last + distance
        if left >= 0 and utterances[left].id not in included_ids:
            selected.append(left)
        if (
            len(selected) < limit
            and right < len(utterances)
            and utterances[right].id not in included_ids
        ):
            selected.append(right)
        distance += 1
    blocks = []
    for index in sorted(selected):
        utterance = utterances[index]
        speaker = speakers.get(utterance.speaker_id)
        label = (
            "Candidate"
            if utterance.speaker_id == candidate_speaker_id
            else f"Speaker {speaker.provider_speaker_key if speaker else 'unknown'}"
        )
        blocks.append(_utterance_block(utterance, label))
    return "\n\n".join(blocks)


async def _upsert_ai_stage_comment(session: AsyncSession, interview: IntelligenceInterview) -> None:
    overview = interview.ai_summary_payload or {}
    parts = ["AI-разбор собеседования"]
    overall_summary = str(overview.get("overall_summary") or "").strip()
    if overall_summary:
        parts.extend(["", "Общее резюме", overall_summary])
    communication_summary = str(overview.get("communication_summary") or "").strip()
    if communication_summary:
        parts.extend(["", "Коммуникация и soft skills", communication_summary])

    rows = (
        await session.execute(
            select(IntelligenceQuestion, IntelligenceAnswer, IntelligenceAnswerReview)
            .outerjoin(
                IntelligenceAnswer,
                IntelligenceAnswer.question_id == IntelligenceQuestion.id,
            )
            .outerjoin(
                IntelligenceAnswerReview,
                (IntelligenceAnswerReview.answer_id == IntelligenceAnswer.id)
                & (IntelligenceAnswerReview.source == IntelligenceReviewSource.AI),
            )
            .where(IntelligenceQuestion.interview_id == interview.id)
            .order_by(
                IntelligenceQuestion.sequence_number,
                IntelligenceAnswerReview.created_at.desc(),
            )
        )
    ).all()
    seen: set[UUID] = set()
    question_lines: list[str] = []
    for question, answer, review in rows:
        if question.id in seen:
            continue
        seen.add(question.id)
        question_lines.append(f"{question.sequence_number}. {question.question_text}")
        if answer is None or not answer.answer_text.strip():
            question_lines.append("Ответ кандидата не найден.")
        if review is not None:
            feedback = (review.summary or review.suggested_better_answer or "").strip()
            if feedback:
                question_lines.append(feedback)
    if question_lines:
        parts.extend(["", "Вопросы и ответы", *question_lines])

    body = "\n".join(parts).strip()[:50_000]
    comment = await session.scalar(
        select(InterviewStageComment).where(
            InterviewStageComment.intelligence_interview_id == interview.id
        )
    )
    if comment is None:
        session.add(
            InterviewStageComment(
                stage_id=interview.stage_id,
                user_id=None,
                body=body,
                is_ai_feedback=True,
                intelligence_interview_id=interview.id,
            )
        )
    else:
        comment.body = body
        comment.is_ai_feedback = True


async def _save_transcript(
    session: AsyncSession,
    interview: IntelligenceInterview,
    result: TranscriptionResult,
) -> None:
    await session.execute(
        delete(IntelligenceSpeaker).where(IntelligenceSpeaker.interview_id == interview.id)
    )
    speaker_by_key: dict[str, IntelligenceSpeaker] = {}
    for row in result.utterances:
        if row.speaker not in speaker_by_key:
            speaker = IntelligenceSpeaker(
                interview_id=interview.id,
                provider_speaker_key=row.speaker,
                role=IntelligenceSpeakerRole.UNKNOWN,
            )
            session.add(speaker)
            await session.flush()
            speaker_by_key[row.speaker] = speaker
    for sequence, row in enumerate(result.utterances, start=1):
        session.add(
            IntelligenceUtterance(
                interview_id=interview.id,
                speaker_id=speaker_by_key[row.speaker].id,
                sequence_number=sequence,
                start_ms=row.start_ms,
                end_ms=row.end_ms,
                text=row.text,
            )
        )


async def _transcription_poll_deadline_at(
    session: AsyncSession,
    interview: IntelligenceInterview,
) -> datetime:
    submitted_at = await session.scalar(
        select(func.max(IntelligenceProcessingAttempt.started_at)).where(
            IntelligenceProcessingAttempt.interview_id == interview.id,
            IntelligenceProcessingAttempt.stage == IntelligenceAttemptStage.TRANSCRIPTION_SUBMIT,
            IntelligenceProcessingAttempt.status == IntelligenceAttemptStatus.COMPLETED,
        )
    )
    started_at = submitted_at or interview.created_at
    return _as_utc(started_at) + timedelta(seconds=_transcription_poll_deadline_seconds())


def _transcription_poll_deadline_seconds() -> int:
    configured = getattr(
        settings,
        "transcription_poll_deadline_seconds",
        DEFAULT_TRANSCRIPTION_POLL_DEADLINE_SECONDS,
    )
    return max(int(configured), 1)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _deadline_reached(deadline_at: datetime, *, now: datetime | None = None) -> bool:
    current = _as_utc(now or datetime.now(UTC))
    return current >= _as_utc(deadline_at)


def _bounded_poll_delay(
    deadline_at: datetime,
    requested_seconds: int,
    *,
    now: datetime | None = None,
) -> int:
    current = _as_utc(now or datetime.now(UTC))
    remaining_seconds = int((_as_utc(deadline_at) - current).total_seconds())
    return max(1, min(requested_seconds, remaining_seconds))


async def _start_attempt(
    session: AsyncSession,
    interview_id: UUID,
    stage: IntelligenceAttemptStage,
    provider: str | None,
) -> IntelligenceProcessingAttempt:
    number = (
        int(
            await session.scalar(
                select(func.count(IntelligenceProcessingAttempt.id)).where(
                    IntelligenceProcessingAttempt.interview_id == interview_id,
                    IntelligenceProcessingAttempt.stage == stage,
                )
            )
            or 0
        )
        + 1
    )
    attempt = IntelligenceProcessingAttempt(
        interview_id=interview_id,
        stage=stage,
        status=IntelligenceAttemptStatus.STARTED,
        attempt_number=number,
        provider=provider,
    )
    session.add(attempt)
    await session.flush()
    return attempt


def _complete_attempt(attempt: IntelligenceProcessingAttempt) -> None:
    attempt.status = IntelligenceAttemptStatus.COMPLETED
    attempt.finished_at = datetime.now(UTC)


async def _provider_failure(
    session: AsyncSession,
    interview: IntelligenceInterview,
    attempt: IntelligenceProcessingAttempt,
    error: TranscriptionProviderError,
    *,
    retryable: bool,
) -> None:
    await _record_failure(session, interview, attempt, error.code, error.safe_message, retryable)


async def _ai_failure(
    session: AsyncSession,
    interview: IntelligenceInterview,
    attempt: IntelligenceProcessingAttempt,
    error: InterviewAIError,
    *,
    retryable: bool,
) -> None:
    await _record_failure(session, interview, attempt, error.code, error.safe_message, retryable)


def _will_retry(ctx: dict[str, Any], retryable: bool) -> bool:
    job_try = int(ctx.get("job_try", 1))
    return retryable and job_try < MAX_JOB_TRIES


def _retry_delay(ctx: dict[str, Any], base_seconds: int) -> int:
    job_try = max(int(ctx.get("job_try", 1)), 1)
    capped_delay = int(min(base_seconds * (2 ** (job_try - 1)), 600))
    job_id = ctx.get("job_id")
    if not job_id:
        return capped_delay
    digest = hashlib.blake2s(
        f"{job_id}:{job_try}".encode(),
        digest_size=8,
    ).digest()
    jitter_fraction = int.from_bytes(digest) / ((1 << 64) - 1)
    return max(1, int(capped_delay * (0.5 + jitter_fraction / 2)))


def _merge_interview_summaries(
    summaries: list[InterviewSummaryOutput],
) -> InterviewSummaryOutput:
    if not summaries:
        raise ValueError("At least one interview summary is required")

    dimensions: dict[str, list[CommunicationDimension]] = {}
    for summary in summaries:
        for dimension in summary.communication_dimensions:
            dimensions.setdefault(dimension.name.casefold(), []).append(dimension)

    merged_dimensions: list[CommunicationDimension] = []
    for rows in dimensions.values():
        scores = [row.score for row in rows if row.score is not None]
        merged_dimensions.append(
            CommunicationDimension(
                name=rows[0].name,
                score=sum(scores) / len(scores) if scores else None,
                summary=" ".join(_unique(row.summary for row in rows)),
                evidence_utterance_ids=_unique(
                    evidence for row in rows for evidence in row.evidence_utterance_ids
                ),
                confidence=sum(row.confidence for row in rows) / len(rows),
            )
        )

    communication_scores = [
        summary.communication_score
        for summary in summaries
        if summary.communication_score is not None
    ]
    return InterviewSummaryOutput(
        overall_summary="\n\n".join(_unique(item.overall_summary for item in summaries)),
        key_topics=_unique(topic for item in summaries for topic in item.key_topics),
        communication_summary=" ".join(_unique(item.communication_summary for item in summaries)),
        communication_score=(
            sum(communication_scores) / len(communication_scores) if communication_scores else None
        ),
        communication_dimensions=merged_dimensions,
        communication_strengths=_unique(
            value for item in summaries for value in item.communication_strengths
        ),
        communication_growth_areas=_unique(
            value for item in summaries for value in item.communication_growth_areas
        ),
        caveats=_unique(value for item in summaries for value in item.caveats),
    )


def _unique(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip()
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


async def _record_failure(
    session: AsyncSession,
    interview: IntelligenceInterview,
    attempt: IntelligenceProcessingAttempt,
    code: str,
    diagnostic: str,
    retryable: bool,
) -> None:
    attempt.status = IntelligenceAttemptStatus.FAILED
    attempt.error_code = code
    attempt.error_message = diagnostic[:2_000]
    attempt.finished_at = datetime.now(UTC)
    interview.failed_stage = attempt.stage
    interview.processing_error_code = code
    interview.processing_error_message = safe_processing_message(code)
    if not retryable:
        interview.processing_status = IntelligenceProcessingStatus.FAILED
    logger.warning(
        "Interview processing failed interview_id=%s stage=%s code=%s retryable=%s",
        interview.id,
        attempt.stage,
        code,
        retryable,
    )
    await session.commit()


async def _fail(
    session: AsyncSession,
    interview: IntelligenceInterview,
    stage: IntelligenceAttemptStage,
    code: str,
) -> None:
    attempt = await _start_attempt(session, interview.id, stage, None)
    await _record_failure(session, interview, attempt, code, safe_processing_message(code), False)


async def _interview(
    session: AsyncSession, interview_id: UUID, *, lock: bool
) -> IntelligenceInterview:
    statement = select(IntelligenceInterview).where(IntelligenceInterview.id == interview_id)
    if lock:
        statement = statement.with_for_update()
    interview = await session.scalar(statement)
    if interview is None:
        raise RuntimeError(f"Interview {interview_id} no longer exists")
    return interview


def _utterance_block(item: IntelligenceUtterance, speaker: str) -> str:
    return (
        f"[U{item.sequence_number:03d}] "
        f"[{_timestamp(item.start_ms)} - {_timestamp(item.end_ms)}] {speaker}:\n{item.text}"
    )


def _timestamp(milliseconds: int) -> str:
    total_seconds, millis = divmod(milliseconds, 1_000)
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def _transcription(ctx: dict[str, Any]) -> TranscriptionProvider:
    return cast(TranscriptionProvider, ctx["transcription_provider"])


def _ai(ctx: dict[str, Any]) -> InterviewAIProvider:
    return cast(InterviewAIProvider, ctx["ai_provider"])


def _store(ctx: dict[str, Any]) -> InterviewUploadStore:
    return cast(InterviewUploadStore, ctx["upload_store"])


def _staging_root() -> Path:
    return Path(settings.interview_staging_directory)


def _media_size_limit(content_type: str) -> int:
    normalized = content_type.split(";", 1)[0].strip().lower()
    if normalized.startswith("video/"):
        return settings.interview_video_max_bytes
    if normalized.startswith("audio/"):
        return settings.interview_audio_max_bytes
    raise MediaGuardrailError("unsupported_media_type", "Interview recording is not audio or video")


def _configure_media_staging(ctx: dict[str, Any]) -> None:
    root = _staging_root()
    removed = cleanup_stale_staging_directories(
        root,
        older_than_seconds=settings.interview_staging_cleanup_age_seconds,
    )
    if removed:
        logger.info("Removed stale interview staging directories count=%s", removed)
    ctx["media_staging_guard"] = StagingGuard(
        max_concurrency=settings.interview_staging_max_concurrency,
        min_free_bytes=settings.interview_staging_min_free_bytes,
        max_reserved_bytes=settings.interview_staging_max_reserved_bytes,
    )


def _staging_guard(ctx: dict[str, Any]) -> StagingGuard:
    return cast(StagingGuard, ctx["media_staging_guard"])


async def _enqueue(
    ctx: dict[str, Any],
    function: str,
    interview_id: str,
    *,
    defer_seconds: int | float | None = None,
) -> str:
    return await enqueue_intelligence_job(
        function,
        interview_id,
        defer_seconds=defer_seconds,
        redis=ctx["redis"],
    )


class WorkerSettings:
    functions = [
        submit_transcription,
        arq_func(poll_transcription, max_tries=POLL_MAX_TRIES),
        process_transcription_result,
        extract_interview_structure,
        refresh_interview_question_embeddings,
        generate_answer_reviews,
    ]
    cron_jobs = [
        cron(
            reconcile_intelligence_jobs,
            minute=RECONCILIATION_MINUTES,
            run_at_startup=True,
            max_tries=1,
            keep_result=0,
        )
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = max(settings.transcription_max_concurrency, settings.openai_max_concurrency)
    job_timeout = max(
        settings.transcription_job_timeout_seconds,
        settings.openai_job_timeout_seconds,
    )
    max_tries = MAX_JOB_TRIES
    keep_result = 0


class TranscriptionWorkerSettings:
    functions = [
        submit_transcription,
        arq_func(poll_transcription, max_tries=POLL_MAX_TRIES),
        process_transcription_result,
    ]
    cron_jobs = WorkerSettings.cron_jobs
    on_startup = transcription_startup
    on_shutdown = transcription_shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    queue_name = TRANSCRIPTION_QUEUE_NAME
    max_jobs = settings.transcription_max_concurrency
    job_timeout = settings.transcription_job_timeout_seconds
    max_tries = MAX_JOB_TRIES
    keep_result = 0
    health_check_interval = WORKER_HEALTH_CHECK_INTERVAL_SECONDS


class AIWorkerSettings:
    functions = [
        extract_interview_structure,
        refresh_interview_question_embeddings,
        generate_answer_reviews,
    ]
    cron_jobs: list[Any] = []
    on_startup = ai_startup
    on_shutdown = ai_shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    queue_name = OPENAI_QUEUE_NAME
    max_jobs = settings.openai_max_concurrency
    job_timeout = settings.openai_job_timeout_seconds
    max_tries = MAX_JOB_TRIES
    keep_result = 0
    health_check_interval = WORKER_HEALTH_CHECK_INTERVAL_SECONDS
