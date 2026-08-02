from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.interviews import intelligence_jobs, intelligence_router, journal_router
from app.interviews.intelligence_ai import FakeInterviewAIProvider
from app.interviews.intelligence_models import (
    IntelligenceAIUsage,
    IntelligenceAnswer,
    IntelligenceInterview,
    IntelligenceProcessingStatus,
    IntelligenceQuestion,
    IntelligenceQuestionKind,
    IntelligenceSpeaker,
)
from app.interviews.intelligence_providers import FakeTranscriptionProvider
from app.interviews.intelligence_service import select_candidate_speaker
from app.interviews.models import (
    InterviewCard,
    InterviewCardOccurrence,
    InterviewCardProgress,
    InterviewDeck,
    InterviewProcessStage,
    InterviewTopicSelection,
)
from app.tracks.models import LearningTrackEnrollment
from app.users.models import User, UserRole
from tests.conftest import SeededData, TestSession, auth


class RecordingRedis:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple[object, ...]]] = []

    async def enqueue_job(self, name: str, *args: object, **kwargs: object) -> None:
        del kwargs
        self.jobs.append((name, args))


class StubUploadStore:
    def download_url(self, upload: object, *, inline: bool = False) -> str:
        del upload, inline
        return "https://storage.example/recording.mp3?signed=redacted"


async def create_analysis_from_journal(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
    *,
    company_name: str = "Nexara",
) -> tuple[Any, UUID, UUID]:
    async def fake_enqueue(_: UUID) -> None:
        return None

    monkeypatch.setattr(journal_router, "_enqueue_ai_analysis", fake_enqueue)
    process_response = await client.post(
        "/api/v1/interviews/journal/tracks",
        headers=auth(seeded.student_id),
        json={"company_name": company_name, "track_id": str(seeded.python_track_id)},
    )
    assert process_response.status_code == 201, process_response.text
    process_id = UUID(process_response.json()["id"])
    stage_response = await client.post(
        f"/api/v1/interviews/journal/tracks/{process_id}/stages",
        headers=auth(seeded.student_id),
        json={
            "stage_type": "technical_interview",
            "scheduled_at": "2026-08-02T10:00:00Z",
        },
    )
    assert stage_response.status_code == 200, stage_response.text
    stage_id = UUID(stage_response.json()["stages"][0]["id"])
    async with TestSession() as session:
        stage = await session.get(InterviewProcessStage, stage_id)
        assert stage is not None
        stage.media_storage_key = "interview-media/student/recording"
        stage.media_filename = "recording.mp3"
        stage.media_content_type = "audio/mpeg"
        stage.media_size = 1_024
        await session.commit()
    created = await client.post(
        f"/api/v1/interviews/journal/tracks/{process_id}/stages/{stage_id}/ai-analysis",
        headers=auth(seeded.student_id),
    )
    return created, process_id, stage_id


@pytest.mark.asyncio
async def test_student_creates_and_roles_only_see_authorized_interview(
    client: AsyncClient, seeded: SeededData, monkeypatch: pytest.MonkeyPatch
) -> None:
    response, process_id, stage_id = await create_analysis_from_journal(
        client, seeded, monkeypatch, company_name="ООО Nexara"
    )
    assert response.status_code == 201, response.text
    interview_id = response.json()["id"]
    assert response.json()["company_name"] == "Nexara"
    assert response.json()["processing_status"] == "uploaded"

    own = await client.get(f"/api/v1/interviews/{interview_id}", headers=auth(seeded.student_id))
    assert own.status_code == 200

    assigned_mentor = await client.get(
        f"/api/v1/mentor/interviews/{interview_id}", headers=auth(seeded.mentor_id)
    )
    assert assigned_mentor.status_code == 200

    unrelated_mentor = await client.get(
        f"/api/v1/mentor/interviews/{interview_id}",
        headers=auth(seeded.other_mentor_id),
    )
    assert unrelated_mentor.status_code == 404

    admin = await client.get(f"/api/v1/interviews/{interview_id}", headers=auth(seeded.admin_id))
    assert admin.status_code == 200
    duplicate = await client.post(
        f"/api/v1/interviews/journal/tracks/{process_id}/stages/{stage_id}/ai-analysis",
        headers=auth(seeded.student_id),
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "interview_ai_analysis_already_requested"


@pytest.mark.asyncio
async def test_student_cannot_open_another_students_interview(
    client: AsyncClient, seeded: SeededData, monkeypatch: pytest.MonkeyPatch
) -> None:
    created, _, _ = await create_analysis_from_journal(
        client, seeded, monkeypatch, company_name="Yandex"
    )
    interview_id = created.json()["id"]

    other_student_id = uuid4()
    async with TestSession() as session:
        session.add(User(id=other_student_id, first_name="Другой", role=UserRole.STUDENT))
        await session.flush()
        session.add(
            LearningTrackEnrollment(
                user_id=other_student_id,
                track_id=seeded.python_track_id,
            )
        )
        await session.commit()

    response = await client.get(
        f"/api/v1/interviews/{interview_id}", headers=auth(other_student_id)
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_standalone_intelligence_upload_endpoint_is_disabled(
    client: AsyncClient, seeded: SeededData
) -> None:
    response = await client.post(
        "/api/v1/interviews",
        headers=auth(seeded.mentor_id),
        json={
            "company_name": "Ozon",
            "track_id": str(seeded.python_track_id),
            "interview_type": "technical",
            "interviewed_at": "2026-08-02T10:00:00Z",
        },
    )

    assert response.status_code == 405


@pytest.mark.asyncio
async def test_fake_processing_pipeline_reaches_ready(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created, _, _ = await create_analysis_from_journal(client, seeded, monkeypatch)
    interview_id = UUID(created.json()["id"])

    monkeypatch.setattr(intelligence_jobs, "async_session_factory", TestSession)
    queue = RecordingRedis()
    fake_ai = FakeInterviewAIProvider()
    context: dict[str, Any] = {
        "redis": queue,
        "transcription_provider": FakeTranscriptionProvider(),
        "ai_provider": fake_ai,
        "upload_store": StubUploadStore(),
    }

    await intelligence_jobs.submit_transcription(context, str(interview_id))
    await intelligence_jobs.poll_transcription(context, str(interview_id))
    await intelligence_jobs.process_transcription_result(context, str(interview_id))

    async with TestSession() as session:
        candidate = await session.scalar(
            select(IntelligenceSpeaker).where(
                IntelligenceSpeaker.interview_id == interview_id,
                IntelligenceSpeaker.provider_speaker_key == "B",
            )
        )
        student = await session.get(User, seeded.student_id)
        assert candidate is not None and student is not None
        await select_candidate_speaker(session, student, interview_id, candidate.id)

    await intelligence_jobs.extract_interview_structure(context, str(interview_id))
    await intelligence_jobs.generate_answer_reviews(context, str(interview_id))

    response = await client.get(
        f"/api/v1/interviews/{interview_id}", headers=auth(seeded.student_id)
    )
    assert response.status_code == 200
    detail = response.json()
    assert detail["processing_status"] == "ready"
    assert len(detail["transcript"]) == 4
    assert len(detail["questions"]) == 2
    assert [question["question_kind"] for question in detail["questions"]] == [
        "technical",
        "hr",
    ]
    assert detail["questions"][0]["answer"]["reviews"][0]["source"] == "ai"
    assert detail["overview"]["overall_summary"]
    assert detail["overview"]["communication_score"] == 0.78
    assert detail["overview"]["communication_dimensions"][0]["name"] == "clarity"
    assert [call["question_kind"] for call in fake_ai.review_calls] == [
        IntelligenceQuestionKind.TECHNICAL,
        IntelligenceQuestionKind.HR,
    ]
    assert "U003" in str(fake_ai.review_calls[0]["context"])
    assert fake_ai.review_calls[1]["context"] == ""
    async with TestSession() as session:
        operations = list(
            await session.scalars(
                select(IntelligenceAIUsage.operation)
                .where(IntelligenceAIUsage.interview_id == interview_id)
                .order_by(IntelligenceAIUsage.operation)
            )
        )
    assert "technical_evaluation" in operations
    assert "light_evaluation" in operations
    journal = await client.get(
        f"/api/v1/interviews/journal/tracks/{detail['process_id']}",
        headers=auth(seeded.student_id),
    )
    ai_comments = [
        comment
        for stage in journal.json()["stages"]
        for comment in stage["comments"]
        if comment["is_ai_feedback"]
    ]
    assert len(ai_comments) == 1
    assert ai_comments[0]["author"] is None

    async with TestSession() as session:
        deck = InterviewDeck(
            track_id=seeded.python_track_id,
            slug="python-ai-moderation",
            title="Python",
            position=0,
            is_published=True,
        )
        session.add(deck)
        existing_card = InterviewCard(
            deck=deck,
            slug="existing-gil-question",
            category="python",
            companies="Ozon",
            question_markdown="## Как работает GIL в Python?",
            answer_markdown="Проверенный существующий ответ",
            frequency="frequent",
            position=0,
            is_published=True,
            asked_count=4,
        )
        session.add(existing_card)
        missed_question_id = UUID(detail["questions"][-1]["id"])
        missed_answer = await session.scalar(
            select(IntelligenceAnswer).where(
                IntelligenceAnswer.question_id == missed_question_id
            )
        )
        assert missed_answer is not None
        missed_answer.answer_text = ""
        await session.commit()
        deck_id = deck.id

    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, interview_id)
        assert interview is not None
        interview.ai_summary_payload = None
        interview.ai_summary_model = None
        interview.ai_summary_prompt_version = None
        await session.commit()

    enqueued: list[tuple[str, UUID]] = []

    async def fake_enqueue(function: str, queued_interview_id: UUID) -> None:
        enqueued.append((function, queued_interview_id))

    monkeypatch.setattr(intelligence_router, "_enqueue", fake_enqueue)
    requested_summary = await client.post(
        f"/api/v1/mentor/interviews/{interview_id}/generate-overview",
        headers=auth(seeded.admin_id),
    )
    assert requested_summary.status_code == 200, requested_summary.text
    assert requested_summary.json()["processing_status"] == "analyzing"
    assert enqueued == [("generate_answer_reviews", interview_id)]

    await intelligence_jobs.generate_answer_reviews(context, str(interview_id))
    refreshed = await client.get(
        f"/api/v1/interviews/{interview_id}", headers=auth(seeded.student_id)
    )
    detail = refreshed.json()
    assert detail["processing_status"] == "ready"
    assert detail["overview"]["overall_summary"]

    first_question_id = detail["questions"][0]["id"]
    forbidden_moderation = await client.post(
        f"/api/v1/mentor/interviews/{interview_id}/questions/{first_question_id}/moderation",
        headers=auth(seeded.student_id),
        json={"action": "recommend"},
    )
    assert forbidden_moderation.status_code == 403
    recommended = await client.post(
        f"/api/v1/mentor/interviews/{interview_id}/questions/{first_question_id}/moderation",
        headers=auth(seeded.mentor_id),
        json={"action": "recommend"},
    )
    assert recommended.status_code == 200, recommended.text
    assert recommended.json()["questions"][0]["moderation_status"] == "mentor_approved"

    queue = await client.get(
        "/api/v1/admin/interviews/question-moderation?status=needs_review",
        headers=auth(seeded.admin_id),
    )
    assert queue.status_code == 200, queue.text
    assert {item["question_id"] for item in queue.json()["items"]} == {
        question["id"] for question in detail["questions"]
    }
    queue_detail = await client.get(
        f"/api/v1/admin/interviews/question-moderation/{first_question_id}",
        headers=auth(seeded.admin_id),
    )
    assert queue_detail.status_code == 200, queue_detail.text
    assert queue_detail.json()["matched_card_id"] == str(existing_card.id)
    assert queue_detail.json()["matched_card_asked_count"] == 4

    ai_reviews = [
        question["answer"]["reviews"][0]
        for question in detail["questions"]
        if question["answer"]["reviews"]
    ]
    edited = await client.patch(
        f"/api/v1/mentor/interviews/{interview_id}/reviews/{ai_reviews[0]['id']}",
        headers=auth(seeded.admin_id),
        json={
            "assessment": "correct",
            "score": 0.9,
            "summary": "Уточнённая оценка администратора",
            "strengths": [],
            "problems": [],
            "missing_points": [],
            "incorrect_statements": [],
            "suggested_better_answer": None,
        },
    )
    assert edited.status_code == 200, edited.text
    for review in ai_reviews[1:]:
        approved = await client.post(
            f"/api/v1/mentor/interviews/{interview_id}/reviews/{review['id']}/approve",
            headers=auth(seeded.admin_id),
        )
        assert approved.status_code == 200, approved.text

    completed = await client.post(
        f"/api/v1/mentor/interviews/{interview_id}/complete-review",
        headers=auth(seeded.admin_id),
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["reviewed_at"] is not None

    for question in detail["questions"]:
        review = question["answer"]["reviews"][-1] if question["answer"] else None
        moderated = await client.post(
            f"/api/v1/mentor/interviews/{interview_id}/questions/{question['id']}/moderation",
            headers=auth(seeded.admin_id),
            json={
                "action": "approve",
                "question_markdown": question["question_text"],
                "answer_markdown": (
                        review["suggested_better_answer"]
                        if review and review["suggested_better_answer"]
                        else question["answer"]["answer_text"]
                        or "Проверенный ответ администратора"
                ),
                "category": question["category"],
                "frequency": "occasional",
            },
        )
        assert moderated.status_code == 200, moderated.text

    repeated = await client.post(
        f"/api/v1/mentor/interviews/{interview_id}/questions/{first_question_id}/moderation",
        headers=auth(seeded.admin_id),
        json={
            "action": "approve",
            "question_markdown": "Как работает GIL в Python?",
            "answer_markdown": "Проверенный существующий ответ",
            "category": "python",
            "frequency": "frequent",
        },
    )
    assert repeated.status_code == 200, repeated.text

    async with TestSession() as session:
        existing_card = await session.scalar(
            select(InterviewCard).where(InterviewCard.slug == "existing-gil-question")
        )
        assert existing_card is not None
        assert existing_card.asked_count == 5
        assert existing_card.companies is not None
        assert "Ozon" in existing_card.companies
        assert detail["company_name"] in existing_card.companies
        occurrences = list(
            await session.scalars(
                select(InterviewCardOccurrence).where(
                    InterviewCardOccurrence.card_id == existing_card.id
                )
            )
        )
        assert len(occurrences) == 1
        assert occurrences[0].company_name == detail["company_name"]
        missed_question = await session.get(IntelligenceQuestion, missed_question_id)
        assert missed_question is not None and missed_question.published_card_id is not None
        progress = await session.get(
            InterviewCardProgress,
            {
                "user_id": seeded.student_id,
                "card_id": missed_question.published_card_id,
            },
        )
        selection = await session.get(
            InterviewTopicSelection,
            {
                "user_id": seeded.student_id,
                "deck_id": deck_id,
                "category": missed_question.category,
            },
        )
        assert progress is not None and progress.repetitions == 0
        assert selection is not None

    reviewed = await client.get(
        "/api/v1/mentor/interviews?status=reviewed", headers=auth(seeded.admin_id)
    )
    needs_review = await client.get(
        "/api/v1/mentor/interviews?status=needs_review", headers=auth(seeded.admin_id)
    )
    assert [item["id"] for item in reviewed.json()["items"]] == [str(interview_id)]
    assert str(interview_id) not in [item["id"] for item in needs_review.json()["items"]]


@pytest.mark.asyncio
async def test_admin_can_delete_stuck_intelligence_interview(
    client: AsyncClient, seeded: SeededData, monkeypatch: pytest.MonkeyPatch
) -> None:
    created, process_id, stage_id = await create_analysis_from_journal(
        client, seeded, monkeypatch, company_name="Stuck AI"
    )
    interview_id = UUID(created.json()["id"])
    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, interview_id)
        assert interview is not None
        interview.processing_status = IntelligenceProcessingStatus.ANALYZING
        await session.commit()

    deleted = await client.delete(
        f"/api/v1/interviews/{interview_id}", headers=auth(seeded.admin_id)
    )

    assert deleted.status_code == 204, deleted.text
    missing = await client.get(
        f"/api/v1/interviews/{interview_id}", headers=auth(seeded.admin_id)
    )
    assert missing.status_code == 404
    journal = await client.get(
        f"/api/v1/interviews/journal/tracks/{process_id}",
        headers=auth(seeded.student_id),
    )
    assert journal.status_code == 200
    assert journal.json()["stages"][0]["id"] == str(stage_id)
    assert journal.json()["stages"][0]["media"]["filename"] == "recording.mp3"
    assert journal.json()["stages"][0]["ai_analysis_requested_at"] is not None
    duplicate = await client.post(
        f"/api/v1/interviews/journal/tracks/{process_id}/stages/{stage_id}/ai-analysis",
        headers=auth(seeded.student_id),
    )
    assert duplicate.status_code == 409
