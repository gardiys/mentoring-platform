import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from openai import APIConnectionError
from sqlalchemy import func, select

from app.core.config import get_settings
from app.interviews import card_auto_publish, card_automation_jobs
from app.interviews.ai_accounting import AIRequestRecorder
from app.interviews.card_ai_admission import defer_card_generation, select_card_candidates
from app.interviews.card_ai_budget import (
    card_budget_scope,
    release_validation_pledges,
    request_reserve,
    settle_card_request,
    validation_pledge,
)
from app.interviews.card_automation_models import (
    AutomationDecision,
    CardAICharge,
    CardAutomationSettings,
    QuestionCluster,
)
from app.interviews.card_automation_schemas import AnswerValidationResult
from app.interviews.card_automation_types import (
    AnswerContractStatus,
    AutomationDecisionSource,
    AutomationDecisionType,
    LearningObjectType,
    QuestionClusterStatus,
    QuestionOccurrenceStatus,
)
from app.interviews.card_cluster_workflow import ai_processing_condition, manual_review_condition
from app.interviews.intelligence_ai import FakeInterviewAIProvider, InterviewAIError
from app.interviews.intelligence_models import AIRequestLog, IntelligenceQuestion
from tests.conftest import TestSession
from tests.test_ai_cost_optimizations import SmallOutput, _provider, _response
from tests.test_card_automation_jobs import (
    RecordingRedis,
    _create_cluster,
    _enable_cluster_automation,
)
from tests.test_card_automation_pipeline import _configure, _create_source

REQUEST = {"input": "question", "text_format": SmallOutput, "max_output_tokens": 1000}


async def clusters(seeded, count=1, *, eligible=True):
    await _configure(
        seeded,
        min_distinct_interviews_for_promotion=1,
        global_auto_publish_enabled=True,
        cluster_moderation_enabled=True,
        card_ai_min_priority_score=0,
    )
    source = await _create_source(seeded, "Вопрос для бюджета")
    ids = []
    async with TestSession() as session:
        question = await session.get(IntelligenceQuestion, source.question_id)
        question.automation_status = QuestionOccurrenceStatus.CLUSTERED
        for index in range(count):
            cluster = QuestionCluster(
                id=uuid4(),
                direction_id=seeded.python_track_id,
                canonical_question=f"Вопрос {index}",
                normalized_canonical_question=f"вопрос {index}",
                learning_object_type=LearningObjectType.FLASHCARD,
                representative_occurrence_id=source.question_id,
                distinct_interviews_count=1 if eligible else 0,
                priority_score=10 + index,
                generation_source_interview_id=source.interview_id,
                generation_selected_revision=0,
            )
            session.add(cluster)
            ids.append(cluster.id)
        await session.commit()
    return source, ids


async def limits(seeded, **values):
    async with TestSession() as session:
        settings = await session.get(CardAutomationSettings, seeded.python_track_id)
        for name, value in values.items():
            setattr(settings, name, value)
        await session.commit()


async def reserve(
    cluster_id,
    operation="generate_answer_contract",
    *,
    manual=False,
    request=REQUEST,
    model="gpt-5-mini",
):
    with card_budget_scope(cluster_id, manual=manual):
        return await AIRequestRecorder(TestSession).start(
            operation, model, "flex", False, request=request
        )


async def paid(request_id):
    await AIRequestRecorder(TestSession).received(
        request_id, _response('{"value":1}', tier="flex"), "req_test", "gpt-5-mini", "flex"
    )


async def test_parallel_requests_wait_instead_of_terminal_budget_denial(seeded):
    _, ids = await clusters(seeded, 2)
    ceiling = request_reserve("gpt-5-mini", "flex", REQUEST) + validation_pledge(REQUEST, "flex")
    await limits(seeded, card_ai_budget_per_interview_usd=ceiling)
    results = await asyncio.gather(*(reserve(id) for id in ids), return_exceptions=True)
    assert sum(not isinstance(r, Exception) for r in results) == 1
    denied = next(r for r in results if isinstance(r, InterviewAIError))
    assert denied.code == "CARD_AI_RESERVATION_BUSY" and denied.retryable
    async with TestSession() as session:
        assert await session.scalar(select(func.sum(CardAICharge.amount_usd))) == ceiling


async def test_r1_four_typical_terra_requests_fit_or_wait(seeded, monkeypatch):
    _, ids = await clusters(seeded, 4)
    monkeypatch.setattr(get_settings(), "openai_analysis_model", "gpt-5.6-terra")
    from app.interviews.intelligence_ai import ANSWER_CONTRACT_PROMPT, AnswerContract

    request = {
        "max_output_tokens": 4000,
        "text_format": AnswerContract,
        "input": [
            {"role": "developer", "content": ANSWER_CONTRACT_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": "Что такое тип?",
                        "sources": [
                            {
                                "source_id": str(uuid4()),
                                "content": "Материал про операции с типами. " * 50,
                            }
                            for _ in range(8)
                        ],
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    }
    results = await asyncio.gather(
        *(reserve(id, request=request, model="gpt-5.6-terra") for id in ids), return_exceptions=True
    )
    assert sum(not isinstance(r, Exception) for r in results) >= 3
    assert all(
        not isinstance(r, Exception) or isinstance(r, InterviewAIError) and r.retryable
        for r in results
    )
    # Maximum output is reserved, rather than the average observed answer size.
    assert request_reserve("gpt-5.6-terra", "flex", request) / Decimal("0.011") <= 4


async def test_r2_budget_denial_is_policy_state_and_prevents_http(seeded, monkeypatch):
    _, ids = await clusters(seeded)
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ids[0])
        cluster.status = QuestionClusterStatus.NEEDS_REVIEW
        await session.commit()
    await limits(seeded, card_ai_daily_budget_usd=Decimal("0"))
    calls = []
    provider = await _provider(
        lambda request: calls.append(request) or httpx.Response(200, json=_response('{"value":1}'))
    )
    monkeypatch.setattr(card_automation_jobs, "async_session_factory", TestSession)
    monkeypatch.setattr(
        card_automation_jobs,
        "_trusted_sources",
        AsyncMock(
            return_value=[
                {
                    "source_id": str(uuid4()),
                    "content": "Тип определяет допустимые операции.",
                }
            ]
        ),
    )
    try:
        await card_automation_jobs.generate_cluster_candidate(
            {"ai_provider": provider, "job_try": 1, "redis": RecordingRedis()}, str(ids[0]), 0
        )
    finally:
        await provider.close()
    assert not calls
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ids[0])
        assert cluster.answer_status == AnswerContractStatus.NOT_SELECTED
        assert cluster.generation_deferred_reason == "CARD_AI_DAILY_BUDGET"
        assert cluster.generation_retry_after is not None
        assert not await session.scalar(
            select(QuestionCluster.id).where(
                QuestionCluster.id == cluster.id, manual_review_condition()
            )
        )
        assert not await session.scalar(
            select(QuestionCluster.id).where(
                QuestionCluster.id == cluster.id, ai_processing_condition()
            )
        )
        decision = await session.scalar(
            select(AutomationDecision)
            .where(AutomationDecision.entity_id == cluster.id)
            .order_by(AutomationDecision.created_at.desc())
            .limit(1)
        )
        assert decision.decision_type == AutomationDecisionType.CARD_AI_DEFERRED
        assert decision.decision_source.value == "rule"


async def test_r3_free_validation_rejection_restores_pledge(seeded):
    _, ids = await clusters(seeded, 2)
    generation = await reserve(ids[0])
    await paid(generation)
    validation_amount = request_reserve("gpt-5-mini", "flex", REQUEST)
    async with TestSession() as session:
        charge = await session.get(CardAICharge, generation)
        charge.amount_usd -= charge.validation_reserve_usd
        charge.validation_reserve_usd = validation_amount
        charge.amount_usd += validation_amount
        actual = charge.amount_usd - validation_amount
        await session.commit()
    await limits(
        seeded, card_ai_budget_per_interview_usd=actual + validation_amount * Decimal("2.5")
    )
    validation = await reserve(ids[0], "validate_answer_contract")
    await AIRequestRecorder(TestSession).failed(validation, "RateLimitError")
    with pytest.raises(InterviewAIError):
        await reserve(ids[1])
    retry = await reserve(ids[0], "validate_answer_contract")
    async with TestSession() as session:
        assert await session.get(CardAICharge, retry) is not None
        # Settlement is idempotent: a periodic reconciliation must not restore twice.
        await settle_card_request(session, validation)
        charge = await session.get(CardAICharge, generation)
        assert charge.validation_reserve_usd == 0


async def test_r4_manual_bypasses_interview_caps_but_counts_daily(seeded):
    _, ids = await clusters(seeded, 2)
    await limits(seeded, card_ai_max_topics_per_interview=1)
    await reserve(ids[0])
    with pytest.raises(InterviewAIError) as denied:
        await reserve(ids[1])
    assert denied.value.code == "CARD_AI_TOPIC_LIMIT"
    await limits(seeded, card_ai_budget_per_interview_usd=Decimal("0"))
    manual = await reserve(ids[1], manual=True)
    async with TestSession() as session:
        charge = await session.get(CardAICharge, manual)
        assert charge.manual and charge.amount_usd > 0
    await paid(manual)
    await limits(seeded, card_ai_daily_budget_usd=Decimal("0"))
    from app.interviews.card_ai_budget import precheck_manual_budget

    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ids[1])
        settings = await session.get(CardAutomationSettings, cluster.direction_id)
        with pytest.raises(HTTPException) as denied:
            await precheck_manual_budget(session, cluster, settings)
        assert denied.value.status_code == 409
        assert denied.value.detail["code"] == "CARD_AI_DAILY_BUDGET"


async def test_r5_two_pre_send_connection_errors_release_all_reserves(seeded):
    _, ids = await clusters(seeded)
    calls = 0

    def connect_error(request):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise httpx.ConnectError("offline connection refused", request=request)
        return httpx.Response(200, json=_response('{"value":1}', tier="flex"))

    provider = await _provider(connect_error)
    try:
        for _ in range(2):
            with card_budget_scope(ids[0]), pytest.raises(APIConnectionError):
                await provider._request(
                    operation="generate_answer_contract", model="gpt-5-mini", **REQUEST
                )
            async with TestSession() as session:
                assert await session.scalar(select(func.sum(CardAICharge.amount_usd))) == 0
        with card_budget_scope(ids[0]):
            await provider._request(
                operation="generate_answer_contract", model="gpt-5-mini", **REQUEST
            )
    finally:
        await provider.close()
    assert calls == 3


async def test_unknown_read_timeout_allows_only_one_unclosed_attempt(seeded):
    _, ids = await clusters(seeded)
    request_id = await reserve(ids[0])
    await AIRequestRecorder(TestSession).failed(request_id, "APITimeoutError")
    with pytest.raises(InterviewAIError) as denied:
        await reserve(ids[0])
    assert denied.value.code == "CARD_AI_RESERVATION_BUSY"
    async with TestSession() as session:
        charge = await session.get(CardAICharge, request_id)
        assert charge.status == "unknown" and charge.amount_usd > 0


async def test_validation_pledge_expires_but_unknown_request_cost_does_not(seeded):
    _, ids = await clusters(seeded)
    request_id = await reserve(ids[0])
    await paid(request_id)
    async with TestSession() as session:
        charge = await session.get(CardAICharge, request_id)
        charge.reserve_expires_at = datetime.now(UTC) - timedelta(hours=1)
        await session.commit()
    # Admission performs reconciliation before spending again.
    await reserve(ids[0], "validate_answer_contract")
    async with TestSession() as session:
        charge = await session.get(CardAICharge, request_id)
        log = await session.get(AIRequestLog, request_id)
        assert charge.validation_reserve_usd == 0
        assert charge.amount_usd == log.estimated_cost_usd


@pytest.mark.parametrize("count", [12, 70])
async def test_ranked_admission_picks_ten_highest_scores(seeded, count):
    _, ids = await clusters(seeded, count)
    async with TestSession() as session:
        await select_card_candidates(session)
        selected = set(
            await session.scalars(
                select(QuestionCluster.id).where(QuestionCluster.answer_status.is_(None))
            )
        )
        assert selected == set(ids[count - 10 :])
        assert (
            await session.scalar(
                select(func.count()).select_from(QuestionCluster).where(manual_review_condition())
            )
            == 0
        )
        assert (
            len(
                list(
                    await session.scalars(
                        select(QuestionCluster.id).where(
                            QuestionCluster.answer_status == AnswerContractStatus.NOT_SELECTED
                        )
                    )
                )
            )
            == count - 10
        )


async def test_human_review_theme_does_not_take_automatic_admission_slot(seeded):
    _, ids = await clusters(seeded, 3)
    await limits(seeded, card_ai_max_topics_per_interview=2)
    async with TestSession() as session:
        session.add(
            AutomationDecision(
                entity_type="cluster",
                entity_id=ids[2],
                idempotency_key="human-important-theme",
                decision_type=AutomationDecisionType.CLUSTER_MARKED_IMPORTANT,
                decision_source=AutomationDecisionSource.HUMAN,
                reason="Manual review",
                candidate_card_ids=[],
                candidate_cluster_ids=[],
                retrieval_scores={},
            )
        )
        await session.commit()
        assert await select_card_candidates(session) == 2
        selected = set(
            await session.scalars(
                select(QuestionCluster.id).where(
                    QuestionCluster.status == QuestionClusterStatus.NEEDS_REVIEW
                )
            )
        )
        assert selected == set(ids[:2])


async def test_own_routing_must_finish_before_paid_admission(seeded):
    source, ids = await clusters(seeded)
    async with TestSession() as session:
        question = await session.get(IntelligenceQuestion, source.question_id)
        question.automation_status = QuestionOccurrenceStatus.ROUTING
        cluster = await session.get(QuestionCluster, ids[0])
        cluster.generation_source_interview_id = None
        cluster.generation_selected_revision = None
        await session.commit()
        assert await select_card_candidates(session) == 0
        assert cluster.generation_selected_revision is None
        with pytest.raises(InterviewAIError) as error:
            await reserve(cluster.id)
        assert error.value.code == "CARD_AI_AWAITING_ADMISSION"
        question.automation_status = QuestionOccurrenceStatus.CLUSTERED
        await session.commit()
        assert await select_card_candidates(session) == 1
    assert await reserve(ids[0]) is not None


async def test_legacy_draft_validation_does_not_reenter_new_theme_admission(seeded):
    _, ids = await clusters(seeded, 2)
    await limits(
        seeded,
        card_ai_max_topics_per_interview=0,
        card_ai_budget_per_interview_usd=Decimal("0"),
    )
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ids[0])
        cluster.answer_contract = {"short_answer": "Existing paid draft"}
        cluster.priority_score = 0
        cluster.generation_backlog = True
        await session.commit()
        assert await select_card_candidates(session) == 1
        assert cluster.answer_status is None
        # Previously generated drafts also resume with pre-admission metadata.
        cluster.answer_status = AnswerContractStatus.GENERATED_FROM_SOURCES
        cluster.generation_source_interview_id = None
        cluster.generation_selected_revision = None
        await session.commit()
    request_id = await reserve(ids[0], "validate_answer_contract")
    async with TestSession() as session:
        charge = await session.get(CardAICharge, request_id)
        assert charge.maintenance and charge.amount_usd > 0


async def test_membership_growth_reattributes_unpaid_theme_and_day_reset_retries(seeded):
    _, ids = await clusters(seeded)
    new_source = await _create_source(seeded, "Новое появление темы")
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ids[0])
        settings = await session.get(CardAutomationSettings, cluster.direction_id)
        await defer_card_generation(session, cluster, settings, "CARD_AI_TOPIC_LIMIT", "limit")
        cluster.membership_revision = 1
        cluster.stats_revision = 1
        question = await session.get(IntelligenceQuestion, new_source.question_id)
        question.cluster_id = cluster.id
        question.automation_status = QuestionOccurrenceStatus.CLUSTERED
        await session.commit()
        await select_card_candidates(session)
        assert cluster.answer_status is None
        assert cluster.generation_source_interview_id == new_source.interview_id
        await defer_card_generation(session, cluster, settings, "CARD_AI_DAILY_BUDGET", "daily")
        cluster.generation_retry_after = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
        await select_card_candidates(session)
        assert cluster.answer_status is None


async def test_usage_survives_settlement_failure_and_is_reconciled(seeded, monkeypatch):
    from app.interviews import card_ai_budget

    _, ids = await clusters(seeded)
    request_id = await reserve(ids[0])
    original = card_ai_budget.settle_card_request
    monkeypatch.setattr(
        card_ai_budget,
        "settle_card_request",
        AsyncMock(side_effect=RuntimeError("settlement offline")),
    )
    await paid(request_id)
    async with TestSession() as session:
        log = await session.get(AIRequestLog, request_id)
        assert log.estimated_cost_usd is not None
        charge = await session.get(CardAICharge, request_id)
        assert charge.status == "reserved"
        await original(session, request_id)
        await session.commit()
        assert charge.amount_usd == log.estimated_cost_usd + charge.validation_reserve_usd


async def test_source_shortage_goes_to_manual_review_without_paid_regeneration(seeded, monkeypatch):
    class SourceShortageProvider(FakeInterviewAIProvider):
        async def validate_answer_contract(self, question, contract, trusted_sources):
            result = await super().validate_answer_contract(question, contract, trusted_sources)
            return replace(
                result,
                output=result.output.model_copy(
                    update={
                        "supported": False,
                        "requires_additional_sources": True,
                        "missing_required_points": [
                            "В имеющихся источниках не описана необходимая гарантия"
                        ],
                    }
                ),
            )

    await _enable_cluster_automation(seeded)
    cluster_id = await _create_cluster(seeded)
    async with TestSession() as session:
        settings = await session.get(CardAutomationSettings, seeded.python_track_id)
        settings.global_auto_publish_enabled = True
        settings.shadow_mode = False
        await session.commit()
    provider = SourceShortageProvider()
    monkeypatch.setattr(card_automation_jobs, "async_session_factory", TestSession)
    monkeypatch.setattr(
        card_auto_publish, "publication_preflight_reason", AsyncMock(return_value=None)
    )
    ctx = {"ai_provider": provider, "job_try": 1, "redis": RecordingRedis()}
    await card_automation_jobs.generate_cluster_candidate(ctx, str(cluster_id), 1)
    await card_automation_jobs.validate_cluster_answer(ctx, str(cluster_id), 1)
    assert await card_automation_jobs.schedule_answer_repairs() == 0
    await card_automation_jobs.generate_cluster_candidate(ctx, str(cluster_id), 1)
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, cluster_id)
        assert cluster.answer_status.value == "needs_manual_review"
        assert cluster.answer_contract is not None
    assert len(provider.answer_contract_calls) == 1
    assert len(provider.answer_validation_calls) == 1


async def test_validation_model_is_separate_and_actual_model_is_accounted():
    sent = []
    source_id = str(uuid4())
    output = AnswerValidationResult(
        supported=True, supporting_source_references=[source_id], confidence=0.95
    )

    def respond(request):
        sent.append(json.loads(request.content))
        body = _response(output.model_dump_json(), tier="flex")
        body["model"] = "gpt-5.6-luna-2026-09-01"
        body["usage"]["input_tokens_details"]["cache_write_tokens"] = 0
        return httpx.Response(200, json=body)

    provider = await _provider(respond)
    provider.card_validation_model = "gpt-5.6-luna"
    sources = [{"source_id": source_id, "content": "Тип определяет доступные операции."}]
    draft = await FakeInterviewAIProvider().generate_answer_contract("Что такое тип?", sources)
    try:
        validated = await provider.validate_answer_contract(
            "Что такое тип?",
            draft.output,
            sources,
        )
    finally:
        await provider.close()
    assert provider.analysis_model == "gpt-5-mini"
    assert sent[0]["model"] == "gpt-5.6-luna"
    assert validated.usage.model == "gpt-5.6-luna-2026-09-01"
    async with TestSession() as session:
        log = await session.scalar(select(AIRequestLog))
        assert log.model == validated.usage.model
        assert log.estimated_cost_usd is not None


async def test_manual_api_rejects_exhausted_daily_budget_before_queue(client, seeded, monkeypatch):
    from app.interviews import card_automation_service
    from tests.conftest import auth

    _, ids = await clusters(seeded)
    await limits(seeded, card_ai_daily_budget_usd=Decimal("0"))
    queued = AsyncMock()
    monkeypatch.setattr(card_automation_service, "enqueue_card_automation_job", queued)
    response = await client.post(
        f"/api/v1/admin/card-automation/clusters/{ids[0]}/generate-answer",
        headers={**auth(seeded.admin_id), "Idempotency-Key": "manual-exhausted"},
        json={"expected_version": 1},
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "CARD_AI_DAILY_BUDGET"
    queued.assert_not_awaited()


async def test_auto_publish_does_not_promote_below_thresholds(seeded):
    from app.interviews.card_automation_pipeline import recalculate_cluster_stats

    _, ids = await clusters(seeded)
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ids[0])
        settings = await session.get(CardAutomationSettings, seeded.python_track_id)
        settings.shadow_mode = False
        settings.min_distinct_interviews_for_promotion = 99
        settings.min_distinct_companies_for_promotion = 99
        settings.min_failed_answers_for_promotion = 99
        await recalculate_cluster_stats(session, cluster, settings)
        await select_card_candidates(session)
        assert cluster.status != QuestionClusterStatus.NEEDS_REVIEW
        assert cluster.answer_status == AnswerContractStatus.NOT_SELECTED
        assert not await session.scalar(select(QuestionCluster.id).where(ai_processing_condition()))


async def test_unrelated_routing_backlog_does_not_block_admission(seeded):
    _, ids = await clusters(seeded)
    await _create_source(seeded, "Старый вопрос другого интервью ещё в маршрутизации")
    async with TestSession() as session:
        assert await select_card_candidates(session) == 1
        cluster = await session.get(QuestionCluster, ids[0])
        assert cluster.status == QuestionClusterStatus.NEEDS_REVIEW


async def test_ordinary_interview_usage_never_reads_card_budget(monkeypatch):
    from app.interviews import card_ai_budget

    settlement = AsyncMock(
        side_effect=AssertionError("ordinary requests must not settle card charges")
    )
    monkeypatch.setattr(card_ai_budget, "settle_card_request", settlement)
    recorder = AIRequestRecorder(TestSession)
    request_id = await recorder.start("extract", "gpt-5-mini", "flex", False)
    await paid(request_id)
    settlement.assert_not_awaited()
    async with TestSession() as session:
        assert (await session.get(AIRequestLog, request_id)).estimated_cost_usd is not None


async def test_recent_migration_backlog_uses_maintenance_budget(seeded):
    _, ids = await clusters(seeded)
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ids[0])
        cluster.generation_backlog = True
        await session.commit()
    await limits(
        seeded, card_ai_budget_per_interview_usd=Decimal("0"), card_ai_legacy_backlog_enabled=True
    )
    request_id = await reserve(ids[0])
    async with TestSession() as session:
        charge = await session.get(CardAICharge, request_id)
        assert charge.maintenance and not charge.manual


async def test_validation_cache_and_preflight_release_collateral(seeded):
    _, ids = await clusters(seeded)
    request_id = await reserve(ids[0])
    await paid(request_id)
    async with TestSession() as session:
        await release_validation_pledges(session, ids[0])
        await session.commit()
        charge = await session.get(CardAICharge, request_id)
        log = await session.get(AIRequestLog, request_id)
        assert charge.validation_reserve_usd == 0
        assert charge.amount_usd == log.estimated_cost_usd


async def test_supported_card_revalidation_uses_maintenance_after_interview_cap(seeded):
    from app.interviews.card_automation_types import AutomationDecisionSource

    _, ids = await clusters(seeded)
    initial = await reserve(ids[0])
    await paid(initial)
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ids[0])
        session.add(
            AutomationDecision(
                entity_type="cluster",
                entity_id=cluster.id,
                idempotency_key="supported-card-validation",
                decision_type=AutomationDecisionType.ANSWER_CONTRACT_VALIDATED,
                decision_source=AutomationDecisionSource.RULE,
                reason="Previously supported answer",
                judge_result={"supported": True},
                candidate_card_ids=[],
                candidate_cluster_ids=[],
                retrieval_scores={},
            )
        )
        await session.commit()
    await limits(seeded, card_ai_budget_per_interview_usd=Decimal("0"))
    request_id = await reserve(ids[0], "validate_answer_contract")
    async with TestSession() as session:
        charge = await session.get(CardAICharge, request_id)
        assert charge.maintenance and charge.amount_usd > 0


async def test_read_only_economy_report_exposes_spend_and_deferral(seeded):
    from app.scripts.report_card_ai_economy import report

    _, ids = await clusters(seeded, 3)
    request_id = await reserve(ids[0], manual=True)
    await paid(request_id)
    await paid(await reserve(ids[1]))
    async with TestSession() as session:
        session.add(
            AutomationDecision(
                entity_type="cluster",
                entity_id=ids[0],
                idempotency_key="usable-card-for-report",
                decision_type=AutomationDecisionType.CARD_CREATED,
                decision_source=AutomationDecisionSource.RULE,
                reason="Usable card",
                candidate_card_ids=[],
                candidate_cluster_ids=[],
                retrieval_scores={},
            )
        )
        cluster = await session.get(QuestionCluster, ids[2])
        settings = await session.get(CardAutomationSettings, cluster.direction_id)
        await defer_card_generation(
            session, cluster, settings, "CARD_AI_TOPIC_LIMIT", "topic limit"
        )
        await session.commit()
    data = await report(session_factory=TestSession)
    assert data["card_ai_known_usd"] > 0
    assert data["not_selected_now"] == 1
    assert data["budget_refusals"]["CARD_AI_TOPIC_LIMIT"] == 1
    assert data["reserve_to_actual_ratio"]["measured"] == 2
    assert data["usable_new_cards"] == 1
    assert data["known_usd_per_usable_card"] == data["card_ai_known_usd"]
    assert data["card_ai_validation_pledges_usd"] > 0
    assert data["card_ai_reserves_usd"] == data["card_ai_validation_pledges_usd"]
    assert data["duration_by_tier"]["flex"]["median_minutes"] is None
