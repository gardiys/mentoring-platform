"""N7/N8 and admission cost with a large historical queue."""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from time import perf_counter
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import event, func, select

from app.interviews import card_ai_admission as admission
from app.interviews import card_automation_jobs as jobs
from app.interviews.card_automation_models import (
    CardAICharge,
    CardAutomationSettings,
    QuestionCluster,
)
from app.interviews.card_automation_types import (
    AnswerContractStatus,
    LearningObjectType,
    QuestionClusterStatus,
    QuestionOccurrenceStatus,
)
from app.interviews.intelligence_models import IntelligenceQuestion
from tests.conftest import TestSession, test_engine
from tests.test_ai_cost_optimizations import _provider, _response
from tests.test_card_ai_budget import clusters, limits, reserve
from tests.test_card_automation_jobs import RecordingRedis, _contract
from tests.test_card_automation_pipeline import _create_source


async def test_n7_repeated_unpaid_draft_waits_for_new_admission(seeded, monkeypatch):
    source, ids = await clusters(seeded)
    cluster_id = ids[0]
    reference = f"topic:{seeded.topic_ids[0]}"
    async with TestSession() as session:
        cluster = await session.get_one(QuestionCluster, cluster_id)
        cluster.answer_contract = _contract(reference)
        await session.commit()
        assert await admission.select_card_candidates(session) == 1
        selected_revision = cluster.generation_selected_revision
    new_source = await _create_source(seeded, "Тот же вопрос в новом интервью")
    async with TestSession() as session:
        question = await session.get_one(IntelligenceQuestion, new_source.question_id)
        question.cluster_id = cluster_id
        question.automation_status = QuestionOccurrenceStatus.ROUTING
        cluster = await session.get_one(QuestionCluster, cluster_id)
        cluster.membership_revision += 1
        cluster.stats_revision = cluster.membership_revision
        await session.commit()
        revision = cluster.membership_revision
    monkeypatch.setattr(jobs, "async_session_factory", TestSession)
    monkeypatch.setattr(jobs, "_defer_unpublishable_answer", AsyncMock(return_value=False))
    monkeypatch.setattr(
        jobs,
        "_validation_sources",
        AsyncMock(return_value=[{"source_id": reference, "content": "Типы определяют операции."}]),
    )
    redis = RecordingRedis()
    await jobs.reconcile_card_automation_jobs({"redis": redis})
    assert not any(name == "validate_cluster_answer" for name, _, _ in redis.calls)

    # A task already in Redis still passes through the financial gate before HTTP.
    calls = []
    provider = await _provider(
        lambda request: calls.append(request) or httpx.Response(200, json=_response("{}"))
    )
    try:
        await jobs.validate_cluster_answer(
            {"redis": redis, "ai_provider": provider, "job_try": 4}, str(cluster_id), revision
        )
    finally:
        await provider.close()
    assert not calls
    async with TestSession() as session:
        cluster = await session.get_one(QuestionCluster, cluster_id)
        assert cluster.answer_status is None
        assert cluster.generation_deferred_reason == "CARD_AI_AWAITING_ADMISSION"
        assert cluster.generation_selected_revision == selected_revision
        question = await session.get_one(IntelligenceQuestion, new_source.question_id)
        question.automation_status = QuestionOccurrenceStatus.CLUSTERED
        await session.commit()
        assert await admission.select_card_candidates(session) == 1
        assert cluster.generation_selected_revision == revision
        assert cluster.generation_source_interview_id == new_source.interview_id
        assert cluster.generation_deferred_reason is None
    request_id = await reserve(cluster_id, "validate_answer_contract")
    async with TestSession() as session:
        assert (
            await session.get_one(CardAICharge, request_id)
        ).interview_id == new_source.interview_id


@pytest.mark.parametrize("reason", ["CARD_AI_NOT_SELECTED", "CARD_AI_TOPIC_LIMIT"])
async def test_n8_settings_request_one_reassessment(seeded, monkeypatch, reason):
    _, ids = await clusters(seeded, 2, eligible=reason != "CARD_AI_NOT_SELECTED")
    if reason == "CARD_AI_TOPIC_LIMIT":
        await limits(seeded, card_ai_max_topics_per_interview=0)
    async with TestSession() as session:
        assert await admission.select_card_candidates(session) == 0
        settings = await session.get_one(CardAutomationSettings, seeded.python_track_id)
        settings.version += 1
        for id in ids:
            cluster = await session.get_one(QuestionCluster, id)
            assert cluster.generation_deferred_reason == reason
            # Same marker as saving direction settings through the admin API.
            cluster.generation_retry_after = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    eligible = Mock(wraps=admission.eligible)
    monkeypatch.setattr(admission, "eligible", eligible)
    for _ in range(3):
        async with TestSession() as session:
            assert await admission.select_card_candidates(session) == 0
    assert eligible.call_count == 2
    async with TestSession() as session:
        rows = list(await session.scalars(select(QuestionCluster)))
        assert all(cluster.generation_retry_after is None for cluster in rows)
        assert all(cluster.generation_deferred_reason == reason for cluster in rows)


@pytest.mark.parametrize("paid_slots", [True, False])
async def test_two_thousand_full_interview_deferrals_need_constant_queries(
    seeded, monkeypatch, caplog, paid_slots
):
    source, ids = await clusters(seeded, 10)
    async with TestSession() as session:
        assert await admission.select_card_candidates(session) == 10
        if paid_slots:
            for id in ids:
                (await session.get_one(QuestionCluster, id)).status = QuestionClusterStatus.IGNORED
                session.add(
                    CardAICharge(
                        request_id=uuid4(),
                        cluster_id=id,
                        interview_id=source.interview_id,
                        direction_id=seeded.python_track_id,
                        amount_usd=Decimal("0.001"),
                        status="settled",
                    )
                )
        session.add_all(
            [
                QuestionCluster(
                    id=uuid4(),
                    direction_id=seeded.python_track_id,
                    canonical_question=f"Отложенная тема {index}",
                    normalized_canonical_question=f"отложенная тема {index}",
                    learning_object_type=LearningObjectType.FLASHCARD,
                    distinct_interviews_count=1,
                    priority_score=5 + index / 1_000,
                    representative_occurrence_id=source.question_id,
                    generation_source_interview_id=source.interview_id,
                    generation_selected_revision=0,
                    answer_status=AnswerContractStatus.NOT_SELECTED,
                    generation_deferred_reason="CARD_AI_TOPIC_LIMIT",
                )
                for index in range(2_000)
            ]
        )
        await session.commit()
    eligible = Mock(wraps=admission.eligible)
    monkeypatch.setattr(admission, "eligible", eligible)
    measurements = []
    caplog.set_level(logging.INFO, logger=admission.__name__)
    for _ in range(3):
        queries = []

        def capture_sql(_connection, _cursor, statement, *_args, recorded=queries):
            recorded.append(statement)

        event.listen(test_engine.sync_engine, "before_cursor_execute", capture_sql)
        started = perf_counter()
        try:
            async with TestSession() as session:
                assert await admission.select_card_candidates(session) == (0 if paid_slots else 10)
        finally:
            event.remove(test_engine.sync_engine, "before_cursor_execute", capture_sql)
        measurements.append((len(queries), (perf_counter() - started) * 1_000))
        assert len(queries) <= 14
    assert eligible.call_count == (0 if paid_slots else 30)
    assert len({queries for queries, _ in measurements}) == 1
    logging.getLogger(__name__).info(
        "Admission benchmark paid_slots=%s query_count_and_ms=%s", paid_slots, measurements
    )
    assert any("evaluated=" in record.message for record in caplog.records)
    # Excluding history must preserve recovery when an unpaid selection frees a slot.
    if not paid_slots:
        async with TestSession() as session:
            (await session.get_one(QuestionCluster, ids[-1])).status = QuestionClusterStatus.IGNORED
            await session.commit()
            assert await admission.select_card_candidates(session) == 10
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(QuestionCluster)
                    .where(QuestionCluster.answer_status == AnswerContractStatus.NOT_SELECTED)
                )
                == 1_999
            )


@pytest.mark.parametrize("new_limit", [0, 1, 3])
async def test_unpaid_slot_cache_respects_changed_topic_limit(seeded, new_limit):
    _, ids = await clusters(seeded, 3)
    await limits(seeded, card_ai_max_topics_per_interview=2)
    async with TestSession() as session:
        assert await admission.select_card_candidates(session) == 2
    await limits(seeded, card_ai_max_topics_per_interview=new_limit)
    async with TestSession() as session:
        assert await admission.select_card_candidates(session) == new_limit
        selected = set(
            await session.scalars(
                select(QuestionCluster.id).where(QuestionCluster.answer_status.is_(None))
            )
        )
        expected = set(ids[3 - new_limit :]) if new_limit else set()
        assert selected == expected
