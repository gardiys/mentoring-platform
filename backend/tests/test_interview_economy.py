import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from arq import Retry
from sqlalchemy import func, select

from app.interviews import intelligence_jobs, intelligence_operations_router
from app.interviews.ai_rate_limit import defer_model_cooldown
from app.interviews.intelligence_ai import FakeInterviewAIProvider, InterviewAIError
from app.interviews.intelligence_checkpoints import InterviewAICheckpoints
from app.interviews.intelligence_models import (
    IntelligenceAnswerReview,
    IntelligenceAttemptStatus,
    IntelligenceInterview,
    IntelligenceProcessingAttempt,
    IntelligenceProcessingStatus,
    IntelligenceQuestionKind,
)
from app.interviews.intelligence_request_policy import (
    INTERVIEW_STAGE_CONTINUE,
    interview_request_scope,
    interview_service_tier,
    review_request_policy,
)
from tests.conftest import TestSession, auth, test_engine
from tests.test_ai_cost_optimizations import SmallOutput, _provider, _response
from tests.test_card_automation_pipeline import _create_source
from tests.test_intelligence_restart import completed_analysis as completed_analysis_fixture

completed_analysis = completed_analysis_fixture


async def test_flex_restart_makes_durable_progress_without_failed_attempts(
    client, seeded, monkeypatch, completed_analysis
):
    interview_id, ctx, ai = completed_analysis
    monkeypatch.setattr(
        intelligence_operations_router, "enqueue_intelligence_job", AsyncMock(return_value="queued")
    )
    response = await client.post(
        f"/api/v1/admin/interviews/ai-operations/{interview_id}/restart",
        params={"force": True, "economy": True},
        headers=auth(seeded.admin_id),
    )
    assert response.status_code == 200, response.text
    assert response.json()["ai_service_tier"] == "flex"
    before = len(ai.extraction_calls), len(ai.review_calls)
    await intelligence_jobs.extract_interview_structure(ctx, str(interview_id), analysis_revision=2)
    # The fixture has two answers plus a summary: each new operation gets a worker pass.
    with pytest.raises(Retry):
        await intelligence_jobs.generate_answer_reviews(ctx, str(interview_id), analysis_revision=2)
    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, interview_id)
        assert interview.processing_status is IntelligenceProcessingStatus.ANALYZING
        assert interview.processing_error_code is None
        assert await session.scalar(select(func.count(IntelligenceAnswerReview.id))) == 1
        assert (
            await session.scalar(
                select(func.count(IntelligenceProcessingAttempt.id)).where(
                    IntelligenceProcessingAttempt.status != IntelligenceAttemptStatus.COMPLETED
                )
            )
            == 0
        )
    for _ in range(5):
        try:
            await intelligence_jobs.generate_answer_reviews(
                ctx, str(interview_id), analysis_revision=2
            )
        except Retry:
            continue
        break
    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, interview_id)
        assert interview.processing_status is IntelligenceProcessingStatus.READY
        assert await session.scalar(select(func.count(IntelligenceAnswerReview.id))) == 2
    assert len(ai.extraction_calls) - before[0] == 1
    assert len(ai.review_calls) - before[1] == 2
    assert interview_service_tier.get() == "default"


async def test_flex_checkpoint_budget_counts_only_uncached_operations(seeded):
    source = await _create_source(seeded, "Synthetic interview question")
    ai = FakeInterviewAIProvider()
    first = InterviewAICheckpoints(TestSession, source.interview_id, ai, service_tier="flex")
    await first.extract("first chunk", direction="python")
    await first.extract("first chunk", direction="python")
    with pytest.raises(InterviewAIError) as caught:
        await first.extract("second chunk", direction="python")
    assert caught.value.code == INTERVIEW_STAGE_CONTINUE
    resumed = InterviewAICheckpoints(TestSession, source.interview_id, ai, service_tier="flex")
    await resumed.extract("first chunk", direction="python")
    await resumed.extract("second chunk", direction="python")
    assert len(ai.extraction_calls) == 2
    # Changing only the price tier can reuse the same content.
    standard = InterviewAICheckpoints(TestSession, source.interview_id, ai)
    await standard.extract("second chunk", direction="python")
    assert len(ai.extraction_calls) == 2


async def test_flex_continuation_refunds_arq_retry_budget():
    redis = SimpleNamespace(eval=AsyncMock())
    with pytest.raises(Retry):
        await defer_model_cooldown(
            {"redis": redis, "job_id": "saved-interview"},
            InterviewAIError(
                INTERVIEW_STAGE_CONTINUE, "Continue", retryable=True, retry_after_seconds=1
            ),
        )
    redis.eval.assert_awaited_once()


async def test_concurrent_interviews_keep_their_own_tier_and_recovery_reasoning():
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(200, json=_response('{"value":1}', tier=body["service_tier"]))

    provider = await _provider(handler)

    async def run(tier):
        with interview_request_scope(tier):
            await asyncio.sleep(0)
            await provider._parse_user_facing_response(
                model="gpt-5-mini",
                prompt="test",
                user_content=tier,
                text_format=SmallOutput,
                max_output_tokens=1_000,
                validate=lambda value: None,
                operation="answer review",
                reasoning_effort="low",
            )

    try:
        await asyncio.gather(run("flex"), run("default"))
    finally:
        await provider.close()
    assert {body["service_tier"] for body in requests} == {"flex", "default"}
    for body in requests:
        assert body["input"][1]["content"] == body["service_tier"]
        assert body["reasoning"] == {"effort": "low"}
    assert interview_service_tier.get() == "default"


async def test_review_cache_separates_actual_model_and_reasoning(seeded):
    source = await _create_source(seeded, "Synthetic interview question")
    ai = FakeInterviewAIProvider()
    checkpoints = InterviewAICheckpoints(TestSession, source.interview_id, ai)
    args = dict(
        question_id=source.question_id,
        question="Чем отличается list от tuple в Python?",
        answer="Список изменяемый, кортеж неизменяемый.",
        category="python",
        question_kind=IntelligenceQuestionKind.TECHNICAL,
        context="",
        direction="python",
    )
    await checkpoints.review(**args)
    await checkpoints.review(**{**args, "question_id": uuid4()})
    assert len(ai.review_calls) == 1
    ai.review_reasoning_effort = "low"
    await checkpoints.review(**args)
    assert len(ai.review_calls) == 2
    ai.simple_review_enabled = True
    ai.simple_review_model = "experimental-model"
    await checkpoints.review(**args)
    await checkpoints.review(**args)
    assert len(ai.review_calls) == 3


@pytest.mark.parametrize(
    "enabled,question,context,expected",
    [
        (False, "Чем отличается list от tuple в Python?", "", "main"),
        (True, "Чем отличается list от tuple в Python?", "", "small"),
        (
            True,
            "Чем отличается list от tuple в Python?",
            "Transcription interpretation hints",
            "main",
        ),
        (True, "Чем отличается list от tuple в Python? И почему?", "", "main"),
        (True, "Объясните race condition", "", "main"),
    ],
)
def test_cheap_model_is_opt_in_and_only_for_narrow_unambiguous_questions(
    enabled, question, context, expected
):
    provider = SimpleNamespace(
        analysis_model="main", simple_review_model="small", simple_review_enabled=enabled
    )
    policy = review_request_policy(
        provider,
        IntelligenceQuestionKind.TECHNICAL,
        question,
        "Список изменяемый, кортеж неизменяемый.",
        context,
    )
    assert policy.model == expected


async def test_flex_rejects_unsafe_worker_timeout_before_request():
    provider = await _provider(lambda request: pytest.fail("No paid call expected"))
    provider.job_timeout_seconds = 120
    try:
        with interview_request_scope("flex"), pytest.raises(InterviewAIError) as caught:
            await provider._request(operation="extract", model="gpt-5-mini")
        assert caught.value.code == "OPENAI_CONFIG_ERROR"
    finally:
        await provider.close()


async def test_economy_migration_keeps_existing_analyses_on_standard(completed_analysis):
    interview_id, _, _ = completed_analysis
    path = (
        Path(__file__).parents[1] / "migrations/versions/20260922_0091_interview_ai_service_tier.py"
    )
    spec = importlib.util.spec_from_file_location("economy_migration", path)
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
        assert interview.ai_service_tier == "default"
        assert interview.processing_status is IntelligenceProcessingStatus.READY
        assert interview.ai_summary_payload


async def test_invalid_flex_compression_does_not_create_endless_continuations():
    from app.interviews.intelligence_summary_evidence import summarize_review_evidence
    from tests.test_interview_summary_evidence import evidence

    checkpoints = SimpleNamespace(
        service_tier="flex",
        summarize_evidence=AsyncMock(
            side_effect=InterviewAIError(
                "OPENAI_OUTPUT_TRUNCATED",
                "Invalid compact evidence",
                retryable=True,
            )
        ),
        summarize=AsyncMock(),
    )
    with pytest.raises(InterviewAIError) as caught:
        await summarize_review_evidence(checkpoints, [evidence(i, long=True) for i in range(25)])
    assert caught.value.code == "OPENAI_OUTPUT_TRUNCATED"
    checkpoints.summarize.assert_not_awaited()


async def test_synthetic_evaluation_records_failed_usage_and_enforces_call_limit():
    from app.interviews.intelligence_ai import ReviewOutput
    from app.interviews.intelligence_models import IntelligenceAssessment
    from app.scripts.evaluate_interview_reviews import CASES, EvaluationRecorder, quality_failures

    recorder = EvaluationRecorder(max_requests=1)
    call_id = await recorder.start("answer review", "gpt-5.6-luna", "default", False)
    await recorder.received(call_id, _response('{"value":1}'), "synthetic", "gpt-5-mini", "default")
    await recorder.failed(call_id, "ValidationError")
    row = recorder.report()[0]
    assert row["status"] == "error"
    assert row["output_tokens"] == 500
    assert row["reasoning_tokens"] == 400
    with pytest.raises(InterviewAIError) as caught:
        await recorder.start("answer review", "gpt-5.6-luna", "default", True)
    assert caught.value.code == "EVALUATION_CALL_LIMIT"
    # The harness cannot mistake a confident evaluation of damaged speech for success.
    failures = quality_failures(
        CASES[4],
        ReviewOutput(
            assessment=IntelligenceAssessment.CORRECT,
            score=1,
        ),
    )
    assert "unexpected_assessment" in failures


async def test_confidence_score_mistake_is_recovered_before_saving():
    from app.interviews.intelligence_ai import ReviewOutput
    from app.interviews.intelligence_models import IntelligenceAssessment

    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        output = ReviewOutput(
            assessment=IntelligenceAssessment.INCORRECT,
            score=1 if len(requests) == 1 else 0,
            summary="Ответ неверен: свойства типов перепутаны.",
        )
        return httpx.Response(200, json=_response(output.model_dump_json()))

    provider = await _provider(handler)
    provider.review_reasoning_effort = "low"
    try:
        with interview_request_scope("flex"):
            result = await provider.review(
                question="Чем отличается list от tuple в Python?",
                answer="Кортеж изменяем, а список неизменяем.",
                category="python",
                question_kind=IntelligenceQuestionKind.TECHNICAL,
                context="",
                direction="python",
            )
        assert result.output.score == 0
        assert len(requests) == 2
        assert all(body["service_tier"] == "flex" for body in requests)
        assert all(body["reasoning"] == {"effort": "low"} for body in requests)
    finally:
        await provider.close()
