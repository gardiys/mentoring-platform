import asyncio
import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from httpx import AsyncClient
from sqlalchemy import delete, func, select

from app.interviews import intelligence_jobs, intelligence_operations_router, intelligence_service
from app.interviews.intelligence_ai import FakeInterviewAIProvider
from app.interviews.intelligence_models import (
    IntelligenceAICheckpoint,
    IntelligenceAIUsage,
    IntelligenceAnalysisArchive,
    IntelligenceAnswer,
    IntelligenceAnswerReview,
    IntelligenceInterview,
    IntelligenceMentorComment,
    IntelligenceProcessingStatus,
    IntelligenceQuestion,
    IntelligenceReviewSource,
    IntelligenceReviewStatus,
    IntelligenceSpeaker,
    IntelligenceUtterance,
)
from app.interviews.intelligence_providers import FakeTranscriptionProvider
from app.interviews.models import (
    InterviewCard,
    InterviewCardOccurrence,
    InterviewDeck,
    InterviewProcessStage,
)
from app.users.models import User
from tests.conftest import SeededData, TestSession, auth, test_engine
from tests.test_interview_intelligence_api import (
    RecordingRedis,
    StubUploadStore,
    create_analysis_from_journal,
)


@pytest.fixture
async def completed_analysis(
    client: AsyncClient, seeded: SeededData, monkeypatch: pytest.MonkeyPatch
):
    created, _, _ = await create_analysis_from_journal(client, seeded, monkeypatch)
    interview_id = UUID(created.json()["id"])
    monkeypatch.setattr(intelligence_jobs, "async_session_factory", TestSession)
    ai = FakeInterviewAIProvider()
    ctx = {
        "redis": RecordingRedis(),
        "ai_provider": ai,
        "transcription_provider": FakeTranscriptionProvider(),
        "upload_store": StubUploadStore(),
    }
    await intelligence_jobs.submit_transcription(ctx, str(interview_id))
    await intelligence_jobs.poll_transcription(ctx, str(interview_id))
    await intelligence_jobs.process_transcription_result(ctx, str(interview_id))
    async with TestSession() as session:
        candidate = await session.scalar(
            select(IntelligenceSpeaker).where(
                IntelligenceSpeaker.interview_id == interview_id,
                IntelligenceSpeaker.provider_speaker_key == "B",
            )
        )
        student = await session.get(User, seeded.student_id)
        await intelligence_service.select_candidate_speaker(
            session, student, interview_id, candidate.id
        )
    await intelligence_jobs.extract_interview_structure(ctx, str(interview_id))
    await intelligence_jobs.generate_answer_reviews(ctx, str(interview_id))
    return interview_id, ctx, ai


@pytest.mark.asyncio
async def test_restart_archives_reviews_preserves_cards_and_ignores_old_jobs(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
    completed_analysis,
) -> None:
    interview_id, ctx, ai = completed_analysis
    async with TestSession() as session:
        question = await session.scalar(
            select(IntelligenceQuestion)
            .where(IntelligenceQuestion.interview_id == interview_id)
            .order_by(IntelligenceQuestion.sequence_number)
        )
        review = await session.scalar(
            select(IntelligenceAnswerReview)
            .join(IntelligenceAnswer)
            .where(IntelligenceAnswer.question_id == question.id)
        )
        review.source = IntelligenceReviewSource.MENTOR
        review.status = IntelligenceReviewStatus.APPROVED
        review.summary = "Ручная рецензия, которую нужно сохранить"
        session.add(
            IntelligenceMentorComment(
                interview_id=interview_id,
                question_id=question.id,
                mentor_id=seeded.mentor_id,
                student_id=seeded.student_id,
                text="Комментарий к старому вопросу",
            )
        )
        deck = InterviewDeck(track_id=seeded.python_track_id, slug="restart-deck", title="Python")
        session.add(deck)
        await session.flush()
        card = InterviewCard(
            deck_id=deck.id,
            slug="restart-card",
            category="python",
            question_markdown="Вопрос",
            answer_markdown="Проверенный ответ",
            is_published=True,
            frequency="occasional",
        )
        session.add(card)
        await session.flush()
        question.published_card_id = card.id
        session.add(
            InterviewCardOccurrence(
                card_id=card.id,
                interview_id=interview_id,
                source_question_id=question.id,
                company_name="Nexara",
                asked_at=datetime.now(UTC),
            )
        )
        card_id = card.id
        usage_count = await session.scalar(select(func.count(IntelligenceAIUsage.id)))
        await session.commit()
    enqueue = AsyncMock(return_value="queued")
    monkeypatch.setattr(intelligence_operations_router, "enqueue_intelligence_job", enqueue)
    url = f"/api/v1/admin/interviews/ai-operations/{interview_id}/restart"
    response = await client.post(url, headers=auth(seeded.admin_id))
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["analysis_revision"] == 2
    assert detail["processing_status"] == "analyzing"
    assert detail["questions"] == []
    assert detail["overview"] is None
    assert len(detail["transcript"]) == 4
    archive = detail["analysis_archives"][0]
    enqueue.assert_awaited_once_with(
        "extract_interview_structure", str(interview_id), analysis_revision=2
    )
    assert (await client.post(url, headers=auth(seeded.admin_id))).status_code == 409
    archived = await client.get(
        f"/api/v1/admin/interviews/ai-operations/{interview_id}/archives/{archive['id']}",
        headers=auth(seeded.admin_id),
    )
    assert archived.status_code == 200
    assert (
        archived.json()["questions"][0]["answer"]["reviews"][0]["summary"]
        == "Ручная рецензия, которую нужно сохранить"
    )
    assert archived.json()["mentor_comments"][0]["text"] == "Комментарий к старому вопросу"
    async with TestSession() as session:
        card = await session.get(InterviewCard, card_id)
        assert card.is_published and card.answer_markdown == "Проверенный ответ"
        assert await session.scalar(select(func.count(IntelligenceAIUsage.id))) == usage_count
        assert await session.scalar(select(func.count(IntelligenceAICheckpoint.id))) == 0
        interview = await session.get(IntelligenceInterview, interview_id)
        stage = await session.get(InterviewProcessStage, interview.stage_id)
        assert stage.media_storage_key
        assert stage.ai_analysis_requested_at
    calls_before = len(ai.extraction_calls), len(ai.review_calls)
    await intelligence_jobs.extract_interview_structure(ctx, str(interview_id))
    await intelligence_jobs.refresh_interview_question_embeddings(ctx, str(interview_id))
    await intelligence_jobs.generate_answer_reviews(ctx, str(interview_id))
    assert calls_before == (len(ai.extraction_calls), len(ai.review_calls))
    await intelligence_jobs.reconcile_intelligence_jobs(ctx)
    assert ("extract_interview_structure", (str(interview_id), 2)) in ctx["redis"].jobs
    await intelligence_jobs.extract_interview_structure(ctx, str(interview_id), 2)
    await intelligence_jobs.refresh_interview_question_embeddings(ctx, str(interview_id), 2)
    await intelligence_jobs.generate_answer_reviews(ctx, str(interview_id), 2)
    final = await client.get(f"/api/v1/interviews/{interview_id}", headers=auth(seeded.admin_id))
    assert final.json()["processing_status"] == "ready"
    assert len(final.json()["questions"]) == 2
    assert len(final.json()["analysis_archives"]) == 1
    assert len(ai.extraction_calls) == calls_before[0] + 1


@pytest.mark.asyncio
async def test_restart_queue_failure_can_resume_without_another_reset(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
    completed_analysis,
) -> None:
    interview_id, _, _ = completed_analysis
    enqueue = AsyncMock(side_effect=RuntimeError("queue unavailable"))
    monkeypatch.setattr(intelligence_operations_router, "enqueue_intelligence_job", enqueue)
    response = await client.post(
        f"/api/v1/admin/interviews/ai-operations/{interview_id}/restart",
        headers=auth(seeded.admin_id),
    )
    assert response.status_code == 503
    enqueue.side_effect = None
    response = await client.post(
        f"/api/v1/admin/interviews/ai-operations/{interview_id}/requeue",
        headers=auth(seeded.admin_id),
    )
    assert response.status_code == 200
    assert len(response.json()["analysis_archives"]) == 1
    enqueue.assert_awaited_with(
        "extract_interview_structure", str(interview_id), analysis_revision=2
    )


@pytest.mark.asyncio
async def test_restart_and_archive_are_admin_only(
    client: AsyncClient,
    seeded: SeededData,
    completed_analysis,
) -> None:
    interview_id, _, _ = completed_analysis
    for user_id in (seeded.student_id, seeded.mentor_id):
        base = f"/api/v1/admin/interviews/ai-operations/{interview_id}"
        assert (await client.post(base + "/restart", headers=auth(user_id))).status_code == 403
        assert (
            await client.get(base + f"/archives/{uuid4()}", headers=auth(user_id))
        ).status_code == 403


@pytest.mark.asyncio
async def test_restart_rolls_back_archive_and_questions_on_reset_failure(
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
    completed_analysis,
) -> None:
    interview_id, _, _ = completed_analysis
    monkeypatch.setattr(
        intelligence_service,
        "finalize_automation_deletion",
        AsyncMock(side_effect=RuntimeError("cleanup")),
    )
    async with TestSession() as session:
        admin = await session.get(User, seeded.admin_id)
        with pytest.raises(RuntimeError, match="cleanup"):
            await intelligence_service.prepare_analysis_restart(session, admin, interview_id)
        await session.rollback()
    async with TestSession() as session:
        assert await session.scalar(select(func.count(IntelligenceAnalysisArchive.id))) == 0
        assert await session.scalar(select(func.count(IntelligenceQuestion.id))) == 2
        interview = await session.get(IntelligenceInterview, interview_id)
        assert interview.processing_status is IntelligenceProcessingStatus.READY
        assert interview.analysis_revision == 1


@pytest.mark.asyncio
async def test_simultaneous_restart_creates_only_one_revision(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
    completed_analysis,
) -> None:
    interview_id, _, _ = completed_analysis
    enqueue = AsyncMock(return_value="queued")
    monkeypatch.setattr(intelligence_operations_router, "enqueue_intelligence_job", enqueue)
    responses = await asyncio.gather(
        *[
            client.post(
                f"/api/v1/admin/interviews/ai-operations/{interview_id}/restart",
                headers=auth(seeded.admin_id),
            )
            for _ in range(2)
        ]
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert enqueue.await_count == 1
    async with TestSession() as session:
        assert await session.scalar(select(func.count(IntelligenceAnalysisArchive.id))) == 1


@pytest.mark.asyncio
async def test_restart_requires_saved_transcript(
    client: AsyncClient, seeded: SeededData, completed_analysis
) -> None:
    interview_id, _, _ = completed_analysis
    async with TestSession() as session:
        await session.execute(
            delete(IntelligenceUtterance).where(IntelligenceUtterance.interview_id == interview_id)
        )
        await session.commit()
    response = await client.post(
        f"/api/v1/admin/interviews/ai-operations/{interview_id}/restart",
        headers=auth(seeded.admin_id),
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "analysis_restart_no_transcript"


@pytest.mark.asyncio
async def test_restart_migration_preserves_existing_interview(completed_analysis) -> None:
    interview_id, _, _ = completed_analysis
    path = (
        Path(__file__).parents[1]
        / "migrations/versions/20260910_0086_interview_analysis_restart.py"
    )
    spec = importlib.util.spec_from_file_location("restart_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def migrate(connection):
        with Operations.context(MigrationContext.configure(connection)):
            module.downgrade()
            module.upgrade()

    async with test_engine.begin() as connection:
        await connection.run_sync(migrate)
    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, interview_id)
        assert interview.analysis_revision == 1
        assert interview.processing_status is IntelligenceProcessingStatus.READY
        assert await session.scalar(select(func.count(IntelligenceAnalysisArchive.id))) == 0
