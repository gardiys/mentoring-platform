import json
from uuid import UUID

import pytest
from sqlalchemy import select

from app.interviews import intelligence_jobs
from app.interviews.feedback_types import (
    CandidateQuestion,
    CommunicationDimension,
    CommunicationExercise,
)
from app.interviews.intelligence_ai import FakeInterviewAIProvider
from app.interviews.intelligence_models import IntelligenceSpeaker, IntelligenceUtterance
from app.interviews.intelligence_providers import FakeTranscriptionProvider
from app.interviews.intelligence_service import select_candidate_speaker
from app.users.models import User
from tests.conftest import TestSession, auth
from tests.test_interview_intelligence_api import (
    RecordingRedis,
    StubUploadStore,
    create_analysis_from_journal,
)


@pytest.fixture
async def grounded_interview(client, seeded, monkeypatch):
    created, _, _ = await create_analysis_from_journal(client, seeded, monkeypatch)
    id_ = UUID(created.json()["id"])
    ai = FakeInterviewAIProvider()
    original = ai.review

    async def review(**kwargs):
        result = await original(**kwargs)
        context = json.loads(kwargs["context"].splitlines()[-1])
        result.output.delivery_assessment = [
            CommunicationDimension(
                skill="structure",
                score=0.4,
                summary="Не уточнён результат работы.",
                evidence_quote=kwargs["answer"],
                evidence_utterance_ids=context["answer_utterance_ids"],
                confidence=0.9,
                exercise=CommunicationExercise(
                    task="Перескажи пример по структуре.",
                    success_criterion="Назови действия и результат.",
                ),
            )
        ]
        return result

    monkeypatch.setattr(ai, "review", review)
    monkeypatch.setattr(intelligence_jobs, "async_session_factory", TestSession)
    ctx = {
        "redis": RecordingRedis(),
        "transcription_provider": FakeTranscriptionProvider(),
        "ai_provider": ai,
        "upload_store": StubUploadStore(),
    }
    await intelligence_jobs.submit_transcription(ctx, str(id_))
    await intelligence_jobs.poll_transcription(ctx, str(id_))
    await intelligence_jobs.process_transcription_result(ctx, str(id_))
    async with TestSession() as session:
        speaker = await session.scalar(
            select(IntelligenceSpeaker).where(
                IntelligenceSpeaker.interview_id == id_,
                IntelligenceSpeaker.provider_speaker_key == "B",
            )
        )
        student = await session.get(User, seeded.student_id)
        await select_candidate_speaker(session, student, id_, speaker.id)
    async with TestSession() as session:
        interviewer = await session.scalar(
            select(IntelligenceSpeaker).where(
                IntelligenceSpeaker.interview_id == id_,
                IntelligenceSpeaker.provider_speaker_key == "A",
            )
        )
        session.add_all(
            [
                IntelligenceUtterance(
                    interview_id=id_,
                    speaker_id=speaker.id,
                    sequence_number=5,
                    start_ms=40000,
                    end_ms=42000,
                    text="Как устроено ревью кода в команде?",
                ),
                IntelligenceUtterance(
                    interview_id=id_,
                    speaker_id=interviewer.id,
                    sequence_number=6,
                    start_ms=42000,
                    end_ms=45000,
                    text="Каждый PR смотрит второй разработчик.",
                ),
            ]
        )
        await session.commit()
    original_extract = ai.extract

    async def extract(*args, **kwargs):
        result = await original_extract(*args, **kwargs)
        result.output.candidate_questions = [
            CandidateQuestion(
                question="Как устроено ревью кода в команде?",
                evidence_quote="Как устроено ревью кода в команде?",
                question_utterance_ids=["U005"],
                response_utterance_ids=["U006"],
            )
        ]
        return result

    monkeypatch.setattr(ai, "extract", extract)
    await intelligence_jobs.extract_interview_structure(ctx, str(id_))
    await intelligence_jobs.generate_answer_reviews(ctx, str(id_))
    return str(id_)


async def test_coaching_owner_progress_mentor_decisions_and_revision_guards(
    client, seeded, grounded_interview
):
    id_ = grounded_interview
    url = f"/api/v1/interviews/{id_}"
    detail = (await client.get(url, headers=auth(seeded.student_id))).json()
    assert len(detail["questions"]) == 2
    assert (
        detail["overview"]["candidate_questions"][0]["evidence_quote"]
        == "Как устроено ревью кода в команде?"
    )
    assert detail["overview"]["communication_grounded"]
    assert detail["overview"]["communication_score"] == 0.4
    assert detail["overview"]["technical_score"] is None
    endpoint = url + "/communication/structure"
    payload = {"revision": 1, "action": "complete"}
    done = await client.put(endpoint, headers=auth(seeded.student_id), json=payload)
    assert done.status_code == 200, done.text
    assert done.json()["completed_at"]
    assert (
        await client.put(endpoint, headers=auth(seeded.mentor_id), json=payload)
    ).status_code == 403
    assert (
        await client.put(
            endpoint, headers=auth(seeded.student_id), json={**payload, "revision": 99}
        )
    ).status_code == 409
    assert (
        await client.put(
            endpoint, headers=auth(seeded.student_id), json={**payload, "action": "reject"}
        )
    ).status_code == 403
    assert (
        await client.put(
            endpoint, headers=auth(seeded.other_mentor_id), json={**payload, "action": "reject"}
        )
    ).status_code == 404
    history = f"/api/v1/interviews/communication-history/{seeded.student_id}"
    before = await client.get(history, headers=auth(seeded.mentor_id))
    assert before.status_code == 200, before.text
    assert before.json()["observations"][0]["completed_at"]
    rejected = await client.put(
        endpoint, headers=auth(seeded.mentor_id), json={**payload, "action": "reject"}
    )
    assert rejected.status_code == 200, rejected.text
    after = (await client.get(url, headers=auth(seeded.student_id))).json()
    assert after["overview"]["communication_score"] is None
    assert (await client.get(history, headers=auth(seeded.student_id))).json()["observations"] == []
    assert (await client.get(history, headers=auth(seeded.other_mentor_id))).status_code == 404
    restored = await client.put(
        endpoint, headers=auth(seeded.mentor_id), json={**payload, "action": "approve"}
    )
    assert restored.status_code == 200, restored.text
    assert (
        len((await client.get(history, headers=auth(seeded.student_id))).json()["observations"])
        == 1
    )


async def test_add_technical_question_to_practice_is_owned_and_idempotent(
    client, seeded, grounded_interview
):
    url = f"/api/v1/interviews/{grounded_interview}"
    detail = (await client.get(url, headers=auth(seeded.student_id))).json()
    question = next(q for q in detail["questions"] if q["question_kind"] == "technical")
    endpoint = url + f"/questions/{question['id']}/practice"
    assert (await client.post(endpoint, headers=auth(seeded.mentor_id))).status_code == 403
    for _ in range(2):
        response = await client.post(endpoint, headers=auth(seeded.student_id))
        assert response.status_code == 200, response.text
    response = await client.get(
        "/api/v1/students/me/personal-review-items", headers=auth(seeded.student_id)
    )
    assert response.status_code == 200, response.text
    assert (
        len(
            [
                item
                for item in response.json()["items"]
                if item["source_occurrence_id"] == question["id"]
            ]
        )
        == 1
    )
