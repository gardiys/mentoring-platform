import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from arq import Retry
from httpx import AsyncClient
from openai.lib._pydantic import to_strict_json_schema
from sqlalchemy import select

from app.interviews import intelligence_jobs
from app.interviews.intelligence_ai import (
    ANSWER_RECOVERY_PROMPT,
    AIAnswerRecoveryResult,
    AnswerRecoveryOutput,
    ExtractedQuestion,
    ExtractedSpeechSpan,
    FakeInterviewAIProvider,
    InterviewAIError,
    OpenAIInterviewAIProvider,
    RecoveredAnswer,
)
from app.interviews.intelligence_answer_recovery import recover_missing_answers
from app.interviews.intelligence_checkpoints import InterviewAICheckpoints
from app.interviews.intelligence_extraction_grounding import ground_question
from app.interviews.intelligence_models import (
    IntelligenceAIUsage,
    IntelligenceQuestionKind,
    IntelligenceSpeaker,
    IntelligenceUtterance,
)
from app.interviews.intelligence_providers import FakeTranscriptionProvider
from app.interviews.intelligence_service import select_candidate_speaker
from app.users.models import User
from tests.conftest import SeededData, TestSession, auth
from tests.test_intelligence_speaker_recovery import question, source
from tests.test_interview_intelligence_api import (
    RecordingRedis,
    StubUploadStore,
    create_analysis_from_journal,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid", ["unknown_id", "outside_context", "uncertain", "duplicate", "unknown_key"]
)
async def test_recovery_rejects_unverified_evidence(invalid: str) -> None:
    candidate, other = uuid4(), uuid4()
    rows = [source(f"Реплика {i}", other, i) for i in range(1, 25)]
    original = question(answer_utterance_ids=[])
    answer = RecoveredAnswer(
        question_key="Q001",
        answer_utterance_ids=["U002"],
        whole_answer_utterance_ids=["U002"],
        answer_attribution="clear",
        confidence=0.9,
    )
    if invalid in {"unknown_id", "outside_context"}:
        label = "U999" if invalid == "unknown_id" else "U024"
        answer.answer_utterance_ids = answer.whole_answer_utterance_ids = [label]
    if invalid == "uncertain":
        answer.answer_attribution = "uncertain"
    if invalid == "unknown_key":
        answer.question_key = "Q099"
    checkpoints = AsyncMock(spec=InterviewAICheckpoints)
    checkpoints.recover_answers.return_value = SimpleNamespace(
        output=AnswerRecoveryOutput(
            answers=[answer, answer] if invalid == "duplicate" else [answer]
        )
    )
    repaired = await recover_missing_answers(
        checkpoints, [original], rows, [row.text for row in rows], candidate, direction=None
    )
    assert repaired == [original]


@pytest.mark.asyncio
async def test_recovery_uses_next_chunk_and_shares_reply_between_questions() -> None:
    candidate, other = uuid4(), uuid4()
    rows = [source(f"Реплика {i}", other, i) for i in range(1, 43)]
    rows[39].speaker_id = candidate
    rows[40].text = "Я разработал LM Gitway. При изменении API сломал сервис и восстановил его."
    questions = [
        question(question=text, question_utterance_ids=["U040"], answer_utterance_ids=[])
        for text in ("Какие задачи были интересны?", "Какие были фейлы?")
    ]
    checkpoints = AsyncMock(spec=InterviewAICheckpoints)
    checkpoints.recover_answers.return_value = SimpleNamespace(
        output=AnswerRecoveryOutput(
            answers=[
                RecoveredAnswer(
                    question_key=f"Q{i:03d}",
                    answer_utterance_ids=["U041"],
                    whole_answer_utterance_ids=["U041"],
                    answer_attribution="clear",
                    confidence=0.9,
                )
                for i in (1, 2)
            ]
        )
    )
    repaired = await recover_missing_answers(
        checkpoints, questions, rows, [row.text for row in rows], candidate, direction="python"
    )
    payload = json.loads(checkpoints.recover_answers.call_args.args[0])
    assert rows[40].text in payload["questions"][0]["transcript"]
    for item in repaired:
        grounded = ground_question(
            item, {f"U{row.sequence_number:03d}": row for row in rows}, candidate
        )
        assert grounded is not None and not grounded.answer_unreliable
        assert grounded.answer_text == rows[40].text
    checkpoints.recover_answers.reset_mock()
    await recover_missing_answers(
        checkpoints, repaired, rows, [row.text for row in rows], candidate, direction="python"
    )
    checkpoints.recover_answers.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["missing", "bad_quotes", "unanchored"])
async def test_pipeline_recovers_reply_with_wrong_speaker_and_reuses_paid_extraction(
    client: AsyncClient, seeded: SeededData, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
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
    reply = (
        "А-а, моя задача была сделать общий интерфейс для LMмоделей. "
        "Фэйлы были: я изменил API, сервис рухнул, пришлось восстанавливать."
    )
    async with TestSession() as session:
        labelled_candidate = await session.scalar(
            select(IntelligenceSpeaker).where(
                IntelligenceSpeaker.interview_id == interview_id,
                IntelligenceSpeaker.provider_speaker_key == "A",
            )
        )
        rows = list(
            await session.scalars(
                select(IntelligenceUtterance)
                .where(
                    IntelligenceUtterance.interview_id == interview_id,
                )
                .order_by(IntelligenceUtterance.sequence_number)
            )
        )
        rows[0].text = "Какие задачи были интересными? Какие были фейлы?"
        rows[0].start_ms, rows[0].end_ms = 146_000, 157_000
        rows[1].text = reply
        rows[1].start_ms, rows[1].end_ms = 157_000, 222_000
        rows[2].text = "А версионирование добавляли?"
        rows[3].text = "Интервьюер: можно было добавить версию в URL."
        student = await session.get(User, seeded.student_id)
        await session.commit()
        await select_candidate_speaker(session, student, interview_id, labelled_candidate.id)

    extract = ai.extract
    recover = ai.recover_answers

    async def extract_broken(transcript: str, *, direction=None):
        result = await extract(transcript, direction=direction)
        result.output.questions = [
            ExtractedQuestion(
                question=text,
                question_utterance_ids=["U001"],
                answer_utterance_ids=[] if failure == "missing" else ["U002"],
                answer_spans=[
                    ExtractedSpeechSpan(
                        utterance_id="U002",
                        start_text="исправленная моделью цитата",
                        end_text="API",
                    )
                ]
                if failure == "bad_quotes"
                else [],
                question_kind=IntelligenceQuestionKind.HR,
                category="experience",
                confidence=0.95,
            )
            for text in ("Какие задачи были интересными?", "Какие были фейлы?")
        ]
        result.output.questions.append(
            question(
                question="А версионирование добавляли?",
                question_utterance_ids=["U003"],
                answer_utterance_ids=[],
            )
        )
        return result

    async def recover_reply(content: str, *, direction=None):
        result = await recover(content, direction=direction)
        if failure == "missing" and len(ai.answer_recovery_calls) == 1:
            raise InterviewAIError("OPENAI_RATE_LIMIT", "Transient failure", retryable=True)
        assert reply in content
        result.output.answers = [
            RecoveredAnswer(
                question_key=f"Q{i:03d}",
                answer_utterance_ids=["U002"],
                whole_answer_utterance_ids=["U002"],
                answer_attribution="clear",
                confidence=0.9,
            )
            for i in (1, 2)
        ]
        return result

    monkeypatch.setattr(ai, "extract", extract_broken)
    monkeypatch.setattr(ai, "recover_answers", recover_reply)
    if failure == "missing":
        with pytest.raises(Retry):
            await intelligence_jobs.extract_interview_structure(ctx, str(interview_id))
    await intelligence_jobs.extract_interview_structure(ctx, str(interview_id))
    await intelligence_jobs.generate_answer_reviews(ctx, str(interview_id))
    response = await client.get(
        f"/api/v1/interviews/{interview_id}", headers=auth(seeded.student_id)
    )
    assert response.status_code == 200
    detail = response.json()
    assert detail["processing_status"] == "ready"
    for item in detail["questions"][:2]:
        assert item["answer"]["answer_text"] == reply
        assert item["answer_start_ms"] == 157_000
        assert item["transcription_annotations"]["speaker_attribution_conflict"]
        assert not item["transcription_annotations"]["answer_unreliable"]
        assert item["answer"]["reviews"][0]["summary"] == (
            "Ответ можно сделать конкретнее и лучше связать с карьерной целью."
        )
    unanswered = detail["questions"][2]
    assert unanswered["answer"]["answer_text"] == ""
    assert unanswered["answer"]["reviews"][0]["assessment"] == "unable_to_assess"
    assert len(ai.extraction_calls) == 1
    assert len(ai.review_calls) == 2
    assert all(call["answer"] == reply for call in ai.review_calls)
    async with TestSession() as session:
        operations = list(
            await session.scalars(
                select(IntelligenceAIUsage.operation).where(
                    IntelligenceAIUsage.interview_id == interview_id,
                )
            )
        )
    assert operations.count("extraction") == 1
    assert operations.count("answer_recovery") == 1
    # Retrying the exact paid recovery consumes no additional request.
    checkpoints = InterviewAICheckpoints(TestSession, interview_id, ai)
    await checkpoints.recover_answers(ai.answer_recovery_calls[-1]["content"], direction="python")
    assert len(ai.answer_recovery_calls) == (2 if failure == "missing" else 1)


@pytest.mark.asyncio
async def test_openai_recovery_uses_structured_evidence_and_handles_invalid_response() -> None:
    provider = object.__new__(OpenAIInterviewAIProvider)
    provider.extraction_model, provider.extraction_max_output_tokens = "test-extraction", 8000
    provider._request = AsyncMock(
        return_value=SimpleNamespace(
            output_parsed=AnswerRecoveryOutput(answers=[]),
        )
    )
    result = await provider.recover_answers("source evidence", direction="python")
    assert isinstance(result, AIAnswerRecoveryResult)
    request = provider._request.call_args.kwargs
    assert request["text_format"] is AnswerRecoveryOutput
    assert request["input"][0]["content"].startswith(ANSWER_RECOVERY_PROMPT)
    assert request["input"][1]["content"] == "source evidence"
    schema = to_strict_json_schema(AnswerRecoveryOutput)
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["RecoveredAnswer"]["additionalProperties"] is False
    provider._request.return_value = SimpleNamespace(output_parsed=None)
    with pytest.raises(InterviewAIError, match="no answer recovery"):
        await provider.recover_answers("source evidence")
