from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from openai import AsyncOpenAI, RateLimitError
from pydantic import BaseModel, SecretStr, ValidationError
from sqlalchemy import func, select

from app.core.config import Settings
from app.interviews.ai_accounting import AIRequestRecorder, estimated_cost
from app.interviews.card_automation_models import AutomationDecision
from app.interviews.card_automation_types import AutomationDecisionSource, AutomationDecisionType
from app.interviews.intelligence_ai import FakeInterviewAIProvider, OpenAIInterviewAIProvider
from app.interviews.intelligence_checkpoints import InterviewAICheckpoints
from app.interviews.intelligence_jobs import _interview
from app.interviews.intelligence_models import (
    AIRequestLog,
    IntelligenceAICheckpoint,
    IntelligenceAIUsage,
    IntelligenceInterview,
    IntelligenceQuestion,
    IntelligenceSpeaker,
    IntelligenceUtterance,
)
from app.interviews.models import InterviewCard
from app.scripts.report_ai_costs import daily_report
from tests.conftest import SeededData, TestSession
from tests.test_card_automation_pipeline import (
    _configure,
    _create_card,
    _create_source,
    _process,
)


class SmallOutput(BaseModel):
    value: int


def _response(text: str, *, tier: str = "default", number: int = 1) -> dict[str, object]:
    return {
        "id": f"resp_{number}",
        "object": "response",
        "created_at": 1,
        "status": "completed",
        "model": "gpt-5-mini-2025-08-07",
        "service_tier": tier,
        "output": [
            {
                "type": "message",
                "id": f"msg_{number}",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        ],
        "usage": {
            "input_tokens": 1_000,
            "output_tokens": 500,
            "total_tokens": 1_500,
            "input_tokens_details": {"cached_tokens": 800},
            "output_tokens_details": {"reasoning_tokens": 400},
        },
    }


async def _provider(handler: object) -> OpenAIInterviewAIProvider:
    settings = Settings(
        _env_file=None,
        openai_api_key=SecretStr("offline-test-key"),
        openai_analysis_model="gpt-5-mini",
        openai_extraction_model="gpt-5-mini",
        openai_background_service_tier="flex",
        openai_proxy_url=None,
    )
    provider = OpenAIInterviewAIProvider(settings)
    await provider.close()
    provider.client = AsyncOpenAI(
        api_key="offline-test-key",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    provider.request_recorder = AIRequestRecorder(TestSession)
    return provider


async def test_invalid_structured_output_still_records_all_paid_usage() -> None:
    provider = await _provider(
        lambda request: httpx.Response(
            200,
            json=_response('{"value":"invalid"}', tier="flex"),
            headers={"x-request-id": "req_bad_schema"},
        )
    )
    try:
        with pytest.raises(ValidationError):
            await provider._request(
                operation="route_question",
                model="gpt-5-mini",
                input="test",
                text_format=SmallOutput,
                max_output_tokens=1_000,
            )
    finally:
        await provider.close()
    async with TestSession() as session:
        row = await session.scalar(select(AIRequestLog))
        assert row is not None
        assert row.provider_request_id == "req_bad_schema"
        assert row.status == "error"
        assert (row.input_tokens, row.cached_input_tokens) == (1_000, 800)
        assert (row.output_tokens, row.reasoning_tokens) == (500, 400)
        assert row.estimated_cost_usd == Decimal("0.000535")


async def test_recovery_keeps_both_paid_attempts() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        value = -1 if len(requests) == 1 else 2
        return httpx.Response(
            200, json=_response(json.dumps({"value": value}), number=len(requests))
        )

    def validate(output: SmallOutput) -> None:
        if output.value < 0:
            raise ValueError("Invalid user-facing output")

    provider = await _provider(handler)
    try:
        _, result = await provider._parse_user_facing_response(
            model="gpt-5-mini",
            prompt="test",
            user_content="test",
            text_format=SmallOutput,
            max_output_tokens=1_000,
            validate=validate,
            operation="answer review",
        )
        assert result.value == 2
    finally:
        await provider.close()
    async with TestSession() as session:
        rows = list(await session.scalars(select(AIRequestLog).order_by(AIRequestLog.created_at)))
        assert len(rows) == 2
        assert [row.recovery for row in rows] == [False, True]
        assert sum(row.output_tokens for row in rows) == 1_000
        assert sum(row.estimated_cost_usd for row in rows) == Decimal("0.00214")
    assert [request["max_output_tokens"] for request in requests] == [1_000, 2_000]


async def test_flex_only_changes_background_tier_and_timeout() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append((body, request.extensions["timeout"]))
        return httpx.Response(200, json=_response('{"value":1}', tier=body["service_tier"]))

    provider = await _provider(handler)
    try:
        for operation in ("route_question", "extract"):
            await provider._request(
                operation=operation,
                model="gpt-5-mini",
                input="same evidence",
                text_format=SmallOutput,
                max_output_tokens=1_000,
            )
    finally:
        await provider.close()
    assert [body["service_tier"] for body, _ in requests] == ["flex", "default"]
    assert requests[0][1]["read"] == 900
    assert requests[0][0]["input"] == requests[1][0]["input"]
    assert requests[0][0]["text"] == requests[1][0]["text"]


async def test_flex_unavailable_never_silently_falls_back_to_standard() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            429,
            json={
                "error": {
                    "message": "Resource unavailable",
                    "code": "resource_unavailable",
                }
            },
        )

    provider = await _provider(handler)
    try:
        with pytest.raises(RateLimitError):
            await provider._request(
                operation="route_question",
                model="gpt-5-mini",
                input="test",
                text_format=SmallOutput,
                max_output_tokens=1_000,
            )
    finally:
        await provider.close()
    assert len(requests) == 1
    assert requests[0]["service_tier"] == "flex"
    async with TestSession() as session:
        row = await session.scalar(select(AIRequestLog))
        assert row.status == "error"
        assert row.input_tokens is None


def test_unknown_prices_remain_unknown() -> None:
    assert estimated_cost("other-model", "default", 1_000, 0, 500) is None
    assert estimated_cost("gpt-5-mini", "unknown-tier", 1_000, 0, 500) is None


async def test_embeddings_pay_once_for_duplicates_and_restore_original_order() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "object": "list",
                "model": "text-embedding-3-small",
                "data": [
                    {"index": 0, "object": "embedding", "embedding": [1.0, 0.0]},
                    {"index": 1, "object": "embedding", "embedding": [0.0, 1.0]},
                ],
                "usage": {"prompt_tokens": 100, "total_tokens": 100},
            },
        )

    provider = await _provider(handler)
    try:
        result = await provider.embed(["GIL", "Go", "GIL"])
    finally:
        await provider.close()
    assert requests[0]["input"] == ["GIL", "Go"]
    assert "service_tier" not in requests[0]
    assert result.embeddings == [[1.0, 0.0], [0.0, 1.0], [1.0, 0.0]]
    assert result.usage.input_tokens == 100
    async with TestSession() as session:
        row = await session.scalar(select(AIRequestLog))
        assert row.operation == "embed"
        assert row.estimated_cost_usd == Decimal("0.000002")


async def test_daily_report_uses_local_day_and_exposes_unknown_costs() -> None:
    async with TestSession() as session:
        for timestamp in (
            datetime(2026, 9, 7, 20, 59, tzinfo=UTC),
            datetime(2026, 9, 7, 21, 0, tzinfo=UTC),
        ):
            session.add(
                AIRequestLog(
                    operation="extract",
                    model="gpt-5-mini",
                    service_tier="default",
                    status="started",
                    recovery=False,
                    created_at=timestamp,
                )
            )
        await session.commit()
    report = await daily_report(date(2026, 9, 8), "Europe/Moscow", TestSession)
    group = report["groups"][0]
    assert group["attempts"] == 1
    assert group["unknown_usage_attempts"] == 1
    assert group["unpriced_attempts"] == 1
    assert group["known_estimated_cost_usd"] is None


async def test_checkpoint_survives_outer_rollback_and_invalidates_changed_inputs(
    seeded: SeededData,
) -> None:
    source = await _create_source(seeded, "Что такое GIL?")
    ai = FakeInterviewAIProvider()
    checkpoints = InterviewAICheckpoints(TestSession, source.interview_id, ai)
    content = "[U001] Interviewer: Что такое GIL?\n[U002] Candidate: Блокировка."
    async with TestSession() as session:
        # This timeout also detects incompatible FK locks / checkpoint deadlocks.
        async with asyncio.timeout(5):
            await _interview(session, source.interview_id, lock=True)
            await checkpoints.extract(content, direction="python")
        await session.rollback()
    restarted = InterviewAICheckpoints(TestSession, source.interview_id, ai)
    cached = await restarted.extract(content, direction="python")
    assert cached.usage.input_tokens == 0
    assert len(ai.extraction_calls) == 1
    await restarted.extract(content, direction="go")
    await restarted.extract(content.replace("Candidate", "Interviewer"), direction="python")
    assert len(ai.extraction_calls) == 3
    async with TestSession() as session:
        assert await session.scalar(select(func.count(IntelligenceAICheckpoint.id))) == 3
        assert await session.scalar(select(func.count(IntelligenceAIUsage.id))) == 3


@pytest.mark.parametrize(
    "confidence, source_speaker, quality_flag, expected_calls",
    [
        (0.95, "interviewer", None, 0),
        (0.8, "interviewer", None, 1),
        (0.95, "candidate", None, 1),
        (0.95, "unknown", None, 1),
        (0.95, "interviewer", "depends_on_previous_answer", 1),
    ],
)
async def test_trusted_exact_match_skips_routing_only_at_high_confidence(
    seeded: SeededData,
    confidence: float,
    source_speaker: str,
    quality_flag: str | None,
    expected_calls: int,
) -> None:
    await _configure(seeded, shadow_mode=False, auto_link_exact_enabled=True)
    card = await _create_card(seeded, "Что такое GIL?")
    source = await _create_source(seeded, "Что такое GIL?", confidence=confidence)
    async with TestSession() as session:
        candidate = IntelligenceSpeaker(
            id=uuid4(),
            interview_id=source.interview_id,
            provider_speaker_key="candidate",
        )
        interviewer = IntelligenceSpeaker(
            id=uuid4(),
            interview_id=source.interview_id,
            provider_speaker_key="interviewer",
        )
        session.add_all([candidate, interviewer])
        await session.flush()
        interview = await session.get(IntelligenceInterview, source.interview_id)
        interview.candidate_speaker_id = candidate.id
        utterance = IntelligenceUtterance(
            id=uuid4(),
            interview_id=source.interview_id,
            speaker_id=candidate.id if source_speaker == "candidate" else interviewer.id,
            sequence_number=0,
            start_ms=0,
            end_ms=1_000,
            text="Что такое GIL?",
        )
        session.add(utterance)
        await session.flush()
        question = await session.get(IntelligenceQuestion, source.question_id)
        question.question_utterance_ids = [] if source_speaker == "unknown" else [utterance.id]
        question.quality_flags = [quality_flag] if quality_flag else []
        await session.commit()
    ai = FakeInterviewAIProvider()
    await _process(ai, source.question_id)
    assert len(ai.routing_calls) == expected_calls
    async with TestSession() as session:
        question = await session.get(IntelligenceQuestion, source.question_id)
        if source_speaker == "interviewer" and quality_flag is None:
            assert question.published_card_id == card.card_id


async def test_ambiguous_semantic_candidates_skip_judge_but_record_reason(
    seeded: SeededData,
) -> None:
    await _configure(seeded, semantic_similarity_threshold=0.8, candidate_score_gap_threshold=0.1)
    await _create_card(seeded, "Что такое GIL?", embedding=[1.0, 0.0])
    await _create_card(seeded, "Что такое CPU-bound?", embedding=[1.0, 0.0])
    source = await _create_source(
        seeded, "Как GIL влияет на потоки?", question_embedding=[1.0, 0.0]
    )
    ai = FakeInterviewAIProvider()
    await _process(ai, source.question_id)
    assert ai.card_match_calls == []
    async with TestSession() as session:
        decision = await session.scalar(
            select(AutomationDecision).where(
                AutomationDecision.entity_id == source.question_id,
                AutomationDecision.decision_type == AutomationDecisionType.SEMANTIC_CARD_MATCH,
            )
        )
        assert decision.decision_source is AutomationDecisionSource.RULE
        assert decision.reason == "Top candidates are ambiguous"
        question = await session.get(IntelligenceQuestion, source.question_id)
        assert question.published_card_id is None
        assert question.cluster_id is not None


async def test_caches_reuse_identical_transmitted_payload_despite_discarded_suffixes(
    seeded: SeededData,
) -> None:
    await _configure(seeded, semantic_similarity_threshold=0.8)
    card = await _create_card(seeded, "Что такое GIL?", embedding=[1.0, 0.0])
    ai = FakeInterviewAIProvider()
    for suffix in ("first", "second"):
        async with TestSession() as session:
            row = await session.get(InterviewCard, card.card_id)
            row.answer_markdown = "а" * 8_000 + suffix
            await session.commit()
        source = await _create_source(
            seeded,
            "Как GIL влияет на CPU-bound потоки?",
            answer_text="б" * 6_000 + suffix,
            question_embedding=[1.0, 0.0],
        )
        await _process(ai, source.question_id)
    assert len(ai.routing_calls) == 1
    assert len(ai.card_match_calls) == 1
