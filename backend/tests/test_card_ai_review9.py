"""Repeat-review N1–N6: finite unknown costs and ranked reuse admission."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select

from app.interviews import card_automation_jobs as jobs
from app.interviews.ai_accounting import AIRequestRecorder
from app.interviews.card_ai_admission import defer_card_generation, select_card_candidates
from app.interviews.card_ai_budget import (
    budget_snapshot,
    card_budget_scope,
    reconcile_card_charges,
    request_reserve,
    validation_pledge,
)
from app.interviews.card_automation_models import (
    AutomationDecision,
    CardAICharge,
    CardAutomationSettings,
    QuestionCluster,
)
from app.interviews.card_automation_types import (
    AnswerContractStatus,
    AutomationDecisionType,
    QuestionClusterStatus,
)
from app.interviews.intelligence_ai import InterviewAIError
from app.interviews.intelligence_models import AIRequestLog
from tests.conftest import TestSession
from tests.test_ai_cost_optimizations import _provider, _response
from tests.test_card_ai_budget import REQUEST, clusters, limits, paid, reserve
from tests.test_card_automation_jobs import RecordingRedis


async def age_request(request_id, days=30):
    async with TestSession() as session:
        charge = await session.get_one(CardAICharge, request_id)
        charge.created_at -= timedelta(days=days)
        charge.reserve_expires_at -= timedelta(days=days)
        log = await session.get_one(AIRequestLog, request_id)
        log.created_at -= timedelta(days=days)
        await session.commit()


async def unknown_request(cluster_id):
    request_id = await reserve(cluster_id)
    await AIRequestRecorder(TestSession).failed(request_id, "APITimeoutError")
    await age_request(request_id)
    return request_id


async def test_n1_historical_timeout_does_not_consume_today(seeded):
    _, ids = await clusters(seeded, 2)
    original = await unknown_request(ids[0])
    required = request_reserve("gpt-5-mini", "flex", REQUEST) + validation_pledge(REQUEST, "flex")
    await limits(seeded, card_ai_daily_budget_usd=required + required / 2)
    assert await reserve(ids[1]) is not None
    async with TestSession() as session:
        assert (await session.get_one(CardAICharge, original)).amount_usd > 0


@pytest.mark.parametrize("manual", [False, True])
async def test_n2_historical_unknown_allows_bounded_repeat_and_keeps_interview_cost(seeded, manual):
    _, ids = await clusters(seeded)
    original = await unknown_request(ids[0])
    assert await reserve(ids[0], manual=manual) is not None
    async with TestSession() as session:
        old = await session.get_one(CardAICharge, original)
        cluster = await session.get_one(QuestionCluster, ids[0])
        settings = await session.get_one(CardAutomationSettings, cluster.direction_id)
        snapshot = await budget_snapshot(session, cluster, settings)
        assert old.status == "unknown" and old.amount_usd > 0
        assert Decimal(snapshot["interview_remaining_usd"]) == Decimal("0.4") - old.amount_usd


async def test_n3_reconcile_closes_interrupted_started_request(seeded):
    _, ids = await clusters(seeded, 2)
    request_id = await reserve(ids[0])
    await age_request(request_id)
    assert await reserve(ids[1]) is not None
    async with TestSession() as session:
        old = await session.get_one(CardAICharge, request_id)
        log = await session.get_one(AIRequestLog, request_id)
        assert old.status == "unknown" and old.reason == "interrupted"
        assert log.status == "interrupted" and log.estimated_cost_usd is None
        assert log.finished_at is not None
    assert await reserve(ids[0]) is not None


async def test_cancellation_is_recorded_and_propagated(seeded):
    _, ids = await clusters(seeded)
    entered = asyncio.Event()

    async def handler(request):
        entered.set()
        await asyncio.Event().wait()

    provider = await _provider(handler)

    async def request():
        with card_budget_scope(ids[0]):
            await provider._request(
                operation="generate_answer_contract", model="gpt-5-mini", **REQUEST
            )

    try:
        task = asyncio.create_task(request())
        await asyncio.wait_for(entered.wait(), timeout=10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        await provider.close()
    async with TestSession() as session:
        log = await session.scalar(select(AIRequestLog))
        charge = await session.get_one(CardAICharge, log.id)
        assert log.status == "interrupted" and log.error_code == "interrupted"
        assert charge.status == "unknown" and charge.amount_usd > 0


async def test_n4_two_unknowns_stop_retries_and_record_one_decision(seeded, monkeypatch):
    _, ids = await clusters(seeded)
    await unknown_request(ids[0])
    await unknown_request(ids[0])
    async with TestSession() as session:
        cluster = await session.get_one(QuestionCluster, ids[0])
        cluster.status = QuestionClusterStatus.NEEDS_REVIEW
        await session.commit()
    calls = []
    provider = await _provider(
        lambda request: calls.append(request) or httpx.Response(200, json=_response('{"value":1}'))
    )
    monkeypatch.setattr(jobs, "async_session_factory", TestSession)
    monkeypatch.setattr(
        jobs,
        "_trusted_sources",
        AsyncMock(
            return_value=[
                {"source_id": str(uuid4()), "content": "Достаточное основание для ответа."}
            ]
        ),
    )
    try:
        for _ in range(3):
            await jobs.generate_cluster_candidate(
                {"ai_provider": provider, "job_try": 4, "redis": RecordingRedis()}, str(ids[0]), 0
            )
            async with TestSession() as session:
                assert await select_card_candidates(session) == 0
    finally:
        await provider.close()
    assert not calls
    async with TestSession() as session:
        cluster = await session.get_one(QuestionCluster, ids[0])
        assert cluster.answer_status == AnswerContractStatus.NOT_SELECTED
        assert cluster.generation_deferred_reason == "CARD_AI_COST_UNKNOWN"
        assert cluster.generation_retry_after is None
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AutomationDecision)
                .where(AutomationDecision.decision_type == AutomationDecisionType.CARD_AI_DEFERRED)
            )
            == 1
        )


async def test_n6_reused_drafts_share_ranked_top_ten_with_blank_best_topic(seeded):
    _, ids = await clusters(seeded, 13)
    async with TestSession() as session:
        for id in ids[:12]:
            (await session.get_one(QuestionCluster, id)).answer_contract = {
                "short_answer": "Personal analysis draft"
            }
        await session.commit()
        assert await select_card_candidates(session) == 10
        selected = set(
            await session.scalars(
                select(QuestionCluster.id).where(QuestionCluster.answer_status.is_(None))
            )
        )
        assert selected == set(ids[3:])
    # Validation jobs precede generation, and even a stale job for a rejected
    # draft must not claim a topic slot from the chosen highest-score blank.
    for id in ids[:3]:
        with pytest.raises(InterviewAIError):
            await reserve(id, "validate_answer_contract")
    for id in reversed(ids[3:12]):
        await paid(await reserve(id, "validate_answer_contract"))
    await paid(await reserve(ids[12]))
    async with TestSession() as session:
        charged = set(
            await session.scalars(
                select(CardAICharge.cluster_id).where(CardAICharge.amount_usd > 0)
            )
        )
        assert charged == set(ids[3:])


async def test_freed_unpaid_slot_reconsiders_next_ranked_topic(seeded):
    _, ids = await clusters(seeded, 3)
    await limits(seeded, card_ai_max_topics_per_interview=1)
    async with TestSession() as session:
        assert await select_card_candidates(session) == 1
        highest = await session.get_one(QuestionCluster, ids[2])
        highest.status = QuestionClusterStatus.IGNORED
        await session.commit()
        assert await select_card_candidates(session) == 1
        second = await session.get_one(QuestionCluster, ids[1])
        assert second.answer_status is None


async def test_old_blank_backlog_is_opt_in(seeded):
    _, ids = await clusters(seeded)
    async with TestSession() as session:
        cluster = await session.get_one(QuestionCluster, ids[0])
        cluster.generation_backlog = True
        await session.commit()
        assert await select_card_candidates(session) == 0
        assert cluster.generation_deferred_reason == "CARD_AI_BACKLOG_DISABLED"
    with pytest.raises(InterviewAIError):
        await reserve(ids[0])


async def test_admin_write_off_is_audited_idempotent_and_unblocks_repeat(client, seeded):
    from app.interviews.card_ai_budget import acquire_card_budget_lock
    from app.scripts.report_card_ai_economy import report
    from tests.test_card_automation_api import auth

    _, ids = await clusters(seeded)
    original = await unknown_request(ids[0])
    await unknown_request(ids[0])
    async with TestSession() as session:
        cluster = await session.get_one(QuestionCluster, ids[0])
        cluster.status = QuestionClusterStatus.NEEDS_REVIEW
        settings = await session.get_one(CardAutomationSettings, cluster.direction_id)
        await defer_card_generation(
            session, cluster, settings, "CARD_AI_COST_UNKNOWN", "Two unknowns"
        )
        await session.commit()
        version = cluster.version
    path = f"/api/v1/admin/card-automation/clusters/{ids[0]}/write-off-ai-cost"
    payload = dict(
        expected_version=version,
        request_id=str(original),
        reason="Принять консервативную сумму резерва",
    )
    response = await client.post(
        path, json=payload, headers={**auth(seeded.admin_id), "Idempotency-Key": str(uuid4())}
    )
    assert response.status_code == 200, response.text
    repeated = await client.post(
        path, json=payload, headers={**auth(seeded.admin_id), "Idempotency-Key": str(uuid4())}
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["decision_id"] == response.json()["decision_id"]
    async with TestSession() as session:
        await acquire_card_budget_lock(session, "test_reconcile")
        await reconcile_card_charges(session)
        await session.commit()
        charge = await session.get_one(CardAICharge, original)
        log = await session.get_one(AIRequestLog, original)
        decision = await session.get_one(AutomationDecision, UUID(response.json()["decision_id"]))
        assert charge.status == "written_off" and charge.validation_reserve_usd == 0
        assert log.estimated_cost_usd is None
        assert decision.reviewed_by_user_id == seeded.admin_id
        assert decision.retrieval_scores["cost_basis"] == "reservation"
    detail = await client.get(
        f"/api/v1/admin/card-automation/clusters/{ids[0]}", headers=auth(seeded.admin_id)
    )
    assert len(detail.json()["card_ai_unknown_costs"]) == 1
    page = await client.get("/api/v1/admin/card-automation/clusters", headers=auth(seeded.admin_id))
    assert page.json()["unknown_cost_total"] == 1
    assert await reserve(ids[0]) is not None
    # A later real receipt replaces the assumption without deleting its audit.
    await paid(original)
    async with TestSession() as session:
        assert (await session.get_one(CardAICharge, original)).status == "settled"
    data = await report(session_factory=TestSession)
    assert data["card_ai_written_off_usd"] == 0


async def test_active_unknown_cannot_be_written_off_and_student_is_forbidden(client, seeded):
    from tests.test_card_automation_api import auth

    _, ids = await clusters(seeded)
    request_id = await reserve(ids[0])
    await AIRequestRecorder(TestSession).failed(request_id, "APITimeoutError")
    async with TestSession() as session:
        version = (await session.get_one(QuestionCluster, ids[0])).version
    path = f"/api/v1/admin/card-automation/clusters/{ids[0]}/write-off-ai-cost"
    payload = dict(expected_version=version, request_id=str(request_id), reason="Write off")
    response = await client.post(
        path, json=payload, headers={**auth(seeded.admin_id), "Idempotency-Key": str(uuid4())}
    )
    assert response.status_code == 409, response.text
    response = await client.post(
        path, json=payload, headers={**auth(seeded.student_id), "Idempotency-Key": str(uuid4())}
    )
    assert response.status_code == 403, response.text


async def test_n5_priority_floor_is_tunable_and_top_n_is_primary(seeded):
    from app.interviews.card_ai_budget import eligible
    from app.interviews.card_automation_domain import priority_score

    _, ids = await clusters(seeded)
    async with TestSession() as session:
        cluster = await session.get_one(QuestionCluster, ids[0])
        settings = await session.get_one(CardAutomationSettings, cluster.direction_id)
        score = priority_score(
            occurrences=1,
            distinct_interviews=1,
            distinct_companies=1,
            failed_answers=0,
            last_seen_at=datetime.now(UTC),
            novelty=1,
            topic_importance=0,
            cluster_confidence=0.95,
        )
        assert 4 < score < 6.5
        cluster.priority_score = score
        settings.card_ai_min_priority_score = 6.5
        assert not eligible(cluster, settings)
        cluster.priority_score += 1.9
        assert eligible(cluster, settings)


async def test_write_off_report_excludes_pledge_returned_by_free_validation(client, seeded):
    from app.core.config import get_settings
    from app.scripts.report_card_ai_economy import report
    from tests.test_card_automation_api import auth

    _, ids = await clusters(seeded)
    original = await reserve(ids[0])
    await AIRequestRecorder(TestSession).failed(original, "APITimeoutError")
    async with TestSession() as session:
        charge = await session.get_one(CardAICharge, original)
        charge.created_at -= timedelta(seconds=get_settings().openai_job_timeout_seconds + 61)
        pledged = charge.validation_reserve_usd
        booked = charge.amount_usd - pledged
        version = (await session.get_one(QuestionCluster, ids[0])).version
        await session.commit()
    validation = await reserve(ids[0], "validate_answer_contract")
    response = await client.post(
        f"/api/v1/admin/card-automation/clusters/{ids[0]}/write-off-ai-cost",
        json={"expected_version": version, "request_id": str(original), "reason": "Book reserve"},
        headers={**auth(seeded.admin_id), "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 200, response.text
    # The in-flight retry can fail for free after its parent is written off.
    await AIRequestRecorder(TestSession).failed(validation, "RateLimitError")
    async with TestSession() as session:
        charge = await session.get_one(CardAICharge, original)
        assert charge.status == "written_off"
        assert charge.validation_reserve_usd == pledged
    data = await report(session_factory=TestSession)
    assert data["card_ai_known_usd"] == data["card_ai_written_off_usd"] == booked
    assert data["card_ai_validation_pledges_usd"] == pledged
