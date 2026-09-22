"""Regression coverage for bounded admission, fresh publication checks and queue telemetry."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from redis.exceptions import ConnectionError
from sqlalchemy import select

from app.core.config import get_settings
from app.interviews import card_cluster_matching as matching
from app.interviews import card_queue_observability as telemetry
from app.interviews import card_review_recovery as recovery
from app.interviews.card_automation_models import (
    AutomationDecision,
    CardAutomationSettings,
    QuestionCluster,
)
from app.interviews.card_automation_schemas import QuestionClusterListFilters
from app.interviews.card_automation_service import list_question_clusters
from app.interviews.card_automation_types import (
    AnswerContractStatus as Status,
)
from app.interviews.card_automation_types import (
    AutomationDecisionSource as Source,
)
from app.interviews.card_automation_types import (
    AutomationDecisionType as Decision,
)
from app.interviews.card_automation_types import (
    QuestionClusterStatus as ClusterStatus,
)
from app.interviews.card_cluster_workflow import ai_processing_condition
from app.interviews.intelligence_queue import _priority_options
from app.interviews.models import InterviewCard
from app.users.models import User
from tests.conftest import TestSession
from tests.test_card_auto_publish import ready as ready_fixture
from tests.test_card_automation_service import _cluster

ready = ready_fixture


@pytest.mark.parametrize("occupied_status", [Status.REVIEW_PENDING, Status.WAITING_FOR_AI])
async def test_concurrent_admission_respects_capacity_and_resumes(
    ready, seeded, monkeypatch, occupied_status
):
    monkeypatch.setattr(
        recovery,
        "get_settings",
        lambda: get_settings().model_copy(update={"card_review_backlog_max_active": 3}),
    )
    async with TestSession() as session:
        (await session.get(QuestionCluster, ready[0])).answer_status = occupied_status
        for index in range(4):
            cluster = _cluster(seeded.python_track_id, index, status=ClusterStatus.NEEDS_REVIEW)
            cluster.answer_status = Status.NEEDS_MANUAL_REVIEW
            cluster.review_policy_version = 0
            session.add(cluster)
        await session.commit()
    counts = await asyncio.gather(
        recovery.queue_review_backlog(TestSession), recovery.queue_review_backlog(TestSession)
    )
    assert sum(counts) == 2
    assert await recovery.queue_review_backlog(TestSession) == 0
    async with TestSession() as session:
        (await session.get(QuestionCluster, ready[0])).status = ClusterStatus.IGNORED
        await session.commit()
    assert await recovery.queue_review_backlog(TestSession) == 1


async def test_disabled_admission_and_already_active_answer_are_not_reset(ready, monkeypatch):
    async with TestSession() as session:
        (await session.get(QuestionCluster, ready[0])).review_policy_version = 0
        await session.commit()
    monkeypatch.setattr(
        recovery,
        "get_settings",
        lambda: get_settings().model_copy(update={"card_review_backlog_max_active": 0}),
    )
    assert await recovery.queue_review_backlog(TestSession) == 0
    monkeypatch.setattr(recovery, "get_settings", get_settings)
    assert await recovery.queue_review_backlog(TestSession) == 0
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        assert cluster.review_policy_version == 0
        assert cluster.answer_status == Status.GENERATED_FROM_SOURCES


async def test_duplicate_lookup_reuses_transaction_but_refreshes_edits_and_next_transaction(
    ready, monkeypatch
):
    rank = Mock(wraps=matching.rank_question_candidates)
    monkeypatch.setattr(matching, "rank_question_candidates", rank)
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        settings = await session.get(CardAutomationSettings, cluster.direction_id)
        first = await matching.current_cluster_matches(session, cluster, settings)
        cards = await matching.publication_cards(session, cluster)
        assert await matching.current_cluster_matches(session, cluster, settings, cards) is first
        assert await matching.current_cluster_matches(session, cluster, settings) is first
        assert rank.call_count == 1
        async with TestSession() as editor:
            card = await editor.get(InterviewCard, ready[2].card_id)
            card.question_markdown = cluster.canonical_question
            await editor.commit()
        fresh = await matching.current_cluster_matches(session, cluster, settings, refresh=True)
        assert rank.call_count == 2
        assert any(match.card.id == ready[2].card_id for match in fresh)
        await session.commit()
        await matching.current_cluster_matches(session, cluster, settings)
        assert rank.call_count == 3


def test_priority_preserves_cooldowns_and_allows_old_work_to_age():
    now = datetime.now(UTC)
    fresh = _priority_options("extract_interview_structure", None)["_defer_until"]
    continuation = _priority_options("validate_cluster_answer", None)["_defer_until"]
    assert now - timedelta(minutes=16) < fresh < continuation < now
    assert _priority_options("review_cluster_for_automation", None) == {}
    assert _priority_options("extract_interview_structure", 120) == {"_defer_by": 120}
    assert _priority_options("validate_cluster_answer", 0) == {"_defer_by": 0}


async def test_telemetry_counts_distinct_running_clusters_and_not_other_jobs(monkeypatch):
    cluster_id = uuid4()
    redis = Mock()
    redis.exists = AsyncMock(return_value=True)
    redis.aclose = AsyncMock()

    async def keys(**kwargs):
        yield f"arq:in-progress:card-automation:{cluster_id}:validate_cluster_answer:v1".encode()
        yield f"arq:in-progress:card-automation:{cluster_id}:generate_cluster_candidate:v1".encode()
        yield f"arq:in-progress:card-automation:{uuid4()}:route_question_occurrence:v1".encode()

    redis.scan_iter = keys
    monkeypatch.setattr(telemetry.Redis, "from_url", lambda *a, **kw: redis)
    assert await telemetry.running_card_cluster_ids() == {cluster_id}
    redis.exists.side_effect = ConnectionError()
    assert await telemetry.running_card_cluster_ids() is None
    redis.exists.side_effect = None
    redis.exists.return_value = False
    assert await telemetry.running_card_cluster_ids() is None
    assert redis.aclose.await_count == 3


@pytest.mark.parametrize("available", [True, False])
async def test_page_separates_running_queued_and_direction_scoped_completions(
    ready, seeded, monkeypatch, available
):
    monkeypatch.setattr(
        telemetry,
        "running_card_cluster_ids",
        AsyncMock(return_value={ready[0], uuid4()} if available else None),
    )
    async with TestSession() as session:
        cluster = _cluster(seeded.python_track_id, 42, status=ClusterStatus.NEEDS_REVIEW)
        cluster.answer_status = Status.REPAIR_PENDING
        session.add(cluster)
        complete = _cluster(seeded.python_track_id, 43, status=ClusterStatus.CARD_CREATED)
        session.add(complete)
        await session.flush()
        for decision_type in (Decision.CARD_CREATED, Decision.CLUSTER_LINKED):
            session.add(
                AutomationDecision(
                    entity_type="cluster",
                    entity_id=complete.id,
                    idempotency_key=str(uuid4()),
                    decision_type=decision_type,
                    decision_source=Source.RULE,
                    reason="Test completion",
                )
            )
        await session.commit()
        admin = await session.get(User, seeded.admin_id)
        page = await list_question_clusters(
            session,
            admin,
            QuestionClusterListFilters(
                direction_id=seeded.python_track_id,
                statuses=[ClusterStatus.NEEDS_REVIEW],
            ),
        )
        assert page.ai_processing_total == 2
        assert page.ai_running_total == (1 if available else None)
        assert page.ai_queued_total == (1 if available else None)
        assert page.ai_repair_total == 1
        assert page.completed_last_hour == 1
        assert (
            len(
                list(
                    await session.scalars(
                        select(QuestionCluster.id).where(ai_processing_condition())
                    )
                )
            )
            == 2
        )
