"""Regression coverage for stable evidence and recovery of historical source mismatches."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.interviews import card_automation_jobs as jobs
from app.interviews.card_automation_models import (
    AutomationDecision,
    CardAutomationSettings,
    QuestionCluster,
)
from app.interviews.card_automation_schemas import QuestionClusterListFilters
from app.interviews.card_automation_service import list_question_clusters
from app.interviews.card_automation_types import (
    AnswerContractStatus,
    AutomationDecisionSource,
    AutomationDecisionType,
    QuestionClusterStatus,
)
from app.interviews.intelligence_ai import FakeInterviewAIProvider
from app.interviews.models import InterviewCard, InterviewCardFrequency, InterviewDeck
from app.users.models import User
from tests.conftest import TestSession
from tests.test_card_auto_publish import ready as ready_fixture
from tests.test_card_automation_jobs import RecordingRedis
from tests.test_card_automation_service import _cluster

ready = ready_fixture


async def hide_reference_from_ranking(ready):
    async with TestSession() as session:
        session.add_all(
            [
                InterviewCard(
                    deck_id=ready[2].deck_id,
                    slug=f"ranked-{index}",
                    category="Python",
                    question_markdown=f"Python unrelated topic {index}",
                    answer_markdown="A different concept.",
                    frequency=InterviewCardFrequency.OCCASIONAL,
                    is_published=True,
                    asked_count=100,
                )
                for index in range(101)
            ]
        )
        cluster = await session.get(QuestionCluster, ready[0])
        cluster.answer_validation = cluster.answer_status = None
        await session.commit()
        assert ready[3] not in {
            s["source_id"] for s in await jobs._trusted_sources(session, cluster)
        }


async def test_legacy_reference_outside_retrieval_is_validated_and_published(ready):
    await hide_reference_from_ranking(ready)
    ai = FakeInterviewAIProvider()
    await jobs.validate_cluster_answer(
        {"redis": RecordingRedis(), "ai_provider": ai}, str(ready[0]), 1
    )
    assert not ai.answer_contract_calls
    assert len(ai.answer_validation_calls) == 1
    assert ready[3] in {s["source_id"] for s in ai.answer_validation_calls[0]["trusted_sources"]}
    async with TestSession() as session:
        assert (
            await session.get(QuestionCluster, ready[0])
        ).status == QuestionClusterStatus.CARD_CREATED


async def test_generation_and_validation_pin_sources_despite_ranking_changes(ready):
    ai = FakeInterviewAIProvider()
    ctx = {"redis": RecordingRedis(), "ai_provider": ai}
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        cluster.answer_contract = cluster.answer_validation = cluster.answer_status = None
        settings = await session.get(CardAutomationSettings, cluster.direction_id)
        settings.global_auto_publish_enabled = False
        await session.commit()
    await jobs.generate_cluster_candidate(ctx, str(ready[0]), 1)
    await hide_reference_from_ranking(ready)
    await jobs.validate_cluster_answer(ctx, str(ready[0]), 1)
    assert (
        ai.answer_validation_calls[0]["trusted_sources"]
        == ai.answer_contract_calls[0]["trusted_sources"]
    )
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        settings = await session.get(CardAutomationSettings, cluster.direction_id)
        settings.global_auto_publish_enabled = True
        # Further ranking drift between validation and publication must not trigger another call.
        (await session.get(InterviewCard, ready[2].card_id)).asked_count = 200
        await session.commit()
    await jobs.validate_cluster_answer(ctx, str(ready[0]), 1)
    assert len(ai.answer_validation_calls) == 1
    async with TestSession() as session:
        assert (
            await session.get(QuestionCluster, ready[0])
        ).status == QuestionClusterStatus.CARD_CREATED


@pytest.mark.parametrize("problem", ["unpublished", "wrong_direction", "automatic", "deleted"])
async def test_pinned_reference_never_bypasses_trust_checks(ready, seeded, problem):
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        cluster.answer_validation = cluster.answer_status = None
        card = await session.get(InterviewCard, ready[2].card_id)
        if problem == "unpublished":
            card.is_published = False
        elif problem == "wrong_direction":
            (await session.get(InterviewDeck, card.deck_id)).track_id = seeded.go_track_id
        elif problem == "deleted":
            await session.delete(card)
        else:
            session.add(
                AutomationDecision(
                    entity_type="cluster",
                    entity_id=uuid4(),
                    idempotency_key="automatic-source",
                    decision_type=AutomationDecisionType.CARD_CREATED,
                    decision_source=AutomationDecisionSource.RULE,
                    selected_card_id=card.id,
                    reason="Automatically published",
                )
            )
        await session.commit()
        assert await jobs.load_trusted_sources(session, cluster, source_ids=[ready[3]]) == []
    ai = FakeInterviewAIProvider()
    await jobs.validate_cluster_answer(
        {"redis": RecordingRedis(), "ai_provider": ai}, str(ready[0]), 1
    )
    assert not ai.answer_validation_calls
    async with TestSession() as session:
        assert (await session.get(QuestionCluster, ready[0])).linked_card_id is None


@pytest.mark.parametrize("problem", [None, "human", "unavailable", "different_failure"])
async def test_repair_only_known_source_failure_once_without_regeneration(ready, problem):
    await hide_reference_from_ranking(ready)
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        original_contract = cluster.answer_contract
        cluster.answer_status = AnswerContractStatus.NEEDS_EXPERT_SOURCE
        cluster.answer_validation = {
            "supported": False,
            "confidence": 0.9,
            "unsupported_claims": [
                jobs.MISSING_REFERENCE_FINDING
                if problem != "different_failure"
                else "Unsupported fact"
            ],
        }
        original_validation = cluster.answer_validation
        if problem == "human":
            session.add(
                AutomationDecision(
                    entity_type="cluster",
                    entity_id=cluster.id,
                    idempotency_key="human-decision",
                    decision_type=AutomationDecisionType.MANUAL_OVERRIDE,
                    decision_source=AutomationDecisionSource.HUMAN,
                    reason="Keep for review",
                )
            )
        elif problem == "unavailable":
            (await session.get(InterviewCard, ready[2].card_id)).is_published = False
        await session.commit()
    assert await jobs.repair_missing_source_validations() == (1 if problem is None else 0)
    assert await jobs.repair_missing_source_validations() == 0
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        assert cluster.answer_contract == original_contract
        assert cluster.answer_validation == (None if problem is None else original_validation)
        assert cluster.linked_card_id is None
        assert await session.scalar(
            select(func.count())
            .select_from(AutomationDecision)
            .where(AutomationDecision.retrieval_scores["source_repair_version"].as_integer() == 1)
        ) == (1 if problem in (None, "unavailable") else 0)
    if problem is None:
        ai = FakeInterviewAIProvider()
        ctx = {"redis": RecordingRedis(), "ai_provider": ai}
        await jobs.reconcile_card_automation_jobs(ctx)
        assert any(name == "validate_cluster_answer" for name, _, _ in ctx["redis"].calls)
        await jobs.validate_cluster_answer(ctx, str(ready[0]), 1)
        assert len(ai.answer_validation_calls) == 1
        assert not ai.answer_contract_calls
        async with TestSession() as session:
            assert (await session.get(QuestionCluster, ready[0])).linked_card_id is not None


async def test_workflow_counts_are_scoped_and_separate_pending_from_human_review(ready, seeded):
    async with TestSession() as session:
        pending = _cluster(seeded.python_track_id, 1, status=QuestionClusterStatus.NEEDS_REVIEW)
        failed = _cluster(seeded.python_track_id, 2, status=QuestionClusterStatus.NEEDS_REVIEW)
        failed.answer_status = AnswerContractStatus.NEEDS_EXPERT_SOURCE
        manual = _cluster(seeded.python_track_id, 3, status=QuestionClusterStatus.NEEDS_REVIEW)
        shadow = _cluster(seeded.python_track_id, 4, status=QuestionClusterStatus.SHADOW)
        other = _cluster(seeded.go_track_id, 5, status=QuestionClusterStatus.NEEDS_REVIEW)
        session.add_all([pending, failed, manual, shadow, other])
        session.add(
            AutomationDecision(
                entity_type="cluster",
                entity_id=manual.id,
                idempotency_key="manual-review",
                decision_type=AutomationDecisionType.MANUAL_OVERRIDE,
                decision_source=AutomationDecisionSource.HUMAN,
                reason="Manual decision",
            )
        )
        await session.commit()
        viewer = await session.get(User, seeded.admin_id)
        for processing in (False, True):
            page = await list_question_clusters(
                session,
                viewer,
                QuestionClusterListFilters(
                    direction_id=seeded.python_track_id,
                    needs_action_only=not processing,
                    processing_only=processing,
                    limit=1,
                ),
            )
            assert page.total == page.ai_processing_total == page.manual_review_total == 2
            assert len(page.items) == 1
            assert page.items[0].processing_state == (
                "ai_processing" if processing else "manual_review"
            )
        settings = await session.get(CardAutomationSettings, seeded.python_track_id)
        settings.enabled = False
        await session.flush()
        page = await list_question_clusters(
            session,
            viewer,
            QuestionClusterListFilters(
                direction_id=seeded.python_track_id,
                needs_action_only=True,
            ),
        )
        assert page.ai_processing_total == 0
        assert page.total == page.manual_review_total == 4


async def test_reconciler_holds_shadow_backfill_and_prioritizes_existing_answers(ready, seeded):
    async with TestSession() as session:
        shadow = _cluster(seeded.python_track_id, 10, status=QuestionClusterStatus.SHADOW)
        shadow.membership_revision = shadow.stats_revision = 1
        pending = _cluster(seeded.python_track_id, 11, status=QuestionClusterStatus.NEEDS_REVIEW)
        pending.membership_revision = pending.stats_revision = 1
        session.add_all([shadow, pending])
        await session.commit()
    redis = RecordingRedis()
    await jobs.reconcile_card_automation_jobs({"redis": redis})
    assert not any(
        name == "recalculate_cluster_stats" and args[0] == str(shadow.id)
        for name, args, _ in redis.calls
    )
    answer_jobs = [
        name
        for name, _, _ in redis.calls
        if name in {"validate_cluster_answer", "generate_cluster_candidate"}
    ]
    assert answer_jobs == ["validate_cluster_answer", "generate_cluster_candidate"]
