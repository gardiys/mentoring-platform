"""Regression scenarios from the 20-card production audit (no production data)."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.interviews import card_automation_jobs as jobs
from app.interviews.card_answer_sources import load_trusted_sources
from app.interviews.card_automation_models import AutomationDecision, QuestionCluster
from app.interviews.card_automation_schemas import (
    AnswerValidationResult,
    QuestionClusterListFilters,
)
from app.interviews.card_automation_service import list_question_clusters
from app.interviews.card_automation_types import (
    AnswerContractStatus,
    AutomationDecisionSource,
    AutomationDecisionType,
    QuestionClusterStatus,
)
from app.interviews.card_cluster_workflow import ai_processing_condition, manual_review_condition
from app.interviews.intelligence_ai import FakeInterviewAIProvider, InterviewAIError
from app.interviews.intelligence_models import IntelligenceQuestion
from app.interviews.models import InterviewCard, InterviewCardFrequency
from app.users.models import User
from tests.conftest import TestSession
from tests.test_card_auto_publish import publish
from tests.test_card_auto_publish import ready as ready_fixture
from tests.test_card_automation_jobs import RecordingRedis

ready = ready_fixture


class QuotaProvider(FakeInterviewAIProvider):
    async def generate_answer_contract(self, **kwargs):
        raise InterviewAIError("OPENAI_QUOTA_EXCEEDED", "Quota", retryable=False)

    async def validate_answer_contract(self, **kwargs):
        raise InterviewAIError("OPENAI_QUOTA_EXCEEDED", "Quota", retryable=False)


@pytest.mark.parametrize("stage", ["generation", "validation"])
async def test_quota_waits_outside_manual_queue_and_resumes_saved_stage(ready, stage, seeded):
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        cluster.answer_status = cluster.answer_validation = None
        if stage == "generation":
            cluster.answer_contract = None
        original = cluster.answer_contract
        await session.commit()
    handler = (
        jobs.generate_cluster_candidate if stage == "generation" else jobs.validate_cluster_answer
    )
    await handler({"redis": RecordingRedis(), "ai_provider": QuotaProvider()}, str(ready[0]), 1)
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        assert cluster.answer_status == AnswerContractStatus.WAITING_FOR_AI
        assert cluster.answer_contract == original
        assert cluster.ai_error_code == "OPENAI_QUOTA_EXCEEDED"
        assert cluster.ai_retry_after > datetime.now(UTC)
        assert not await session.scalar(select(QuestionCluster.id).where(manual_review_condition()))
        assert not await session.scalar(select(QuestionCluster.id).where(ai_processing_condition()))
        admin = await session.get(User, seeded.admin_id)
        page = await list_question_clusters(
            session, admin, QuestionClusterListFilters(waiting_only=True)
        )
        assert page.total == page.waiting_for_ai_total == 1
        assert page.manual_review_total == page.ai_processing_total == 0
        assert page.items[0].processing_state == "waiting_for_ai"
    assert await jobs.resume_service_blocked_clusters() == 0
    async with TestSession() as session:
        (await session.get(QuestionCluster, ready[0])).ai_retry_after = datetime.now(
            UTC
        ) - timedelta(seconds=1)
        await session.commit()
    assert await jobs.resume_service_blocked_clusters() == 1
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        assert cluster.answer_contract == original
        assert cluster.answer_status is None
    redis = RecordingRedis()
    await jobs.reconcile_card_automation_jobs({"redis": redis})
    expected = "generate_cluster_candidate" if stage == "generation" else "validate_cluster_answer"
    assert any(name == expected for name, _, _ in redis.calls)


async def rejected_draft(ready, *, self_contained=True):
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        cluster.answer_status = AnswerContractStatus.NEEDS_EXPERT_SOURCE
        cluster.answer_validation = {
            "supported": False,
            "confidence": 0.95,
            "question_is_self_contained": self_contained,
            "unsupported_claims": ["Remove an unsupported optional assertion"],
        }
        await session.commit()


async def test_repaired_answer_is_independently_validated_before_publication(ready):
    await rejected_draft(ready)
    assert await jobs.schedule_answer_repairs() == 1
    async with TestSession() as session:
        assert await session.scalar(select(QuestionCluster.id).where(ai_processing_condition()))
    ai = FakeInterviewAIProvider()
    ctx = {"redis": RecordingRedis(), "ai_provider": ai}
    await jobs.generate_cluster_candidate(ctx, str(ready[0]), 1)
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        assert cluster.answer_repair_attempts == 1
        assert cluster.answer_validation is None
        assert cluster.linked_card_id is None
    await jobs.validate_cluster_answer(ctx, str(ready[0]), 1)
    assert len(ai.answer_validation_calls) == 1
    async with TestSession() as session:
        assert (
            await session.get(QuestionCluster, ready[0])
        ).status == QuestionClusterStatus.CARD_CREATED


async def test_repair_budget_prevents_endless_paid_rewrites(ready):
    ai = FakeInterviewAIProvider()
    ctx = {"redis": RecordingRedis(), "ai_provider": ai}
    for _ in range(2):
        await rejected_draft(ready)
        assert await jobs.schedule_answer_repairs() == 1
        await jobs.generate_cluster_candidate(ctx, str(ready[0]), 1)
    await rejected_draft(ready)
    assert await jobs.schedule_answer_repairs() == 0
    assert len(ai.answer_contract_calls) == 2
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        assert cluster.answer_repair_attempts == 2
        assert cluster.linked_card_id is None


@pytest.mark.parametrize("blocker", ["context", "human", "code"])
async def test_repairs_never_invent_context_or_override_humans(ready, blocker):
    await rejected_draft(ready, self_contained=blocker != "context")
    async with TestSession() as session:
        if blocker == "human":
            session.add(
                AutomationDecision(
                    entity_type="cluster",
                    entity_id=ready[0],
                    idempotency_key=str(uuid4()),
                    decision_type=AutomationDecisionType.MANUAL_OVERRIDE,
                    decision_source=AutomationDecisionSource.HUMAN,
                    reason="Keep for review",
                )
            )
        if blocker == "code":
            (await session.get(IntelligenceQuestion, ready[1])).quality_flags = ["depends_on_code"]
        await session.commit()
    assert await jobs.schedule_answer_repairs() == 0


@pytest.mark.parametrize("independent_check", [True, False])
async def test_uncertain_speaker_requires_independent_question_check(ready, independent_check):
    async with TestSession() as session:
        question = await session.get(IntelligenceQuestion, ready[1])
        question.confidence = 0.5
        question.transcription_annotations = {
            "uncertain_utterance_ids": ["U001"],
            "speaker_attribution_conflict": True,
        }
        cluster = await session.get(QuestionCluster, ready[0])
        cluster.answer_validation = {
            **cluster.answer_validation,
            "question_is_self_contained": independent_check,
        }
        await session.commit()
    assert (await publish(ready) is not None) is independent_check
    async with TestSession() as session:
        question = await session.get(IntelligenceQuestion, ready[1])
        assert question.confidence == 0.5
        assert question.transcription_annotations["speaker_attribution_conflict"] is True


@pytest.mark.parametrize("blocking", [True, False])
async def test_version_warning_is_distinct_from_unresolved_version_problem(ready, blocking):
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        field = "version_sensitive_claims" if blocking else "version_warnings"
        cluster.answer_validation = {**cluster.answer_validation, field: ["Version scope"]}
        await session.commit()
    assert (await publish(ready) is not None) is not blocking


async def test_source_search_finds_body_and_inflections_outside_old_top_100(ready):
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        cluster.canonical_question = "Как устроены составные индексы?"
        cluster.normalized_canonical_question = "как устроены составные индексы"
        source = await session.get(InterviewCard, ready[2].card_id)
        source.question_markdown = "Оптимизация хранилища"
        source.category = "Базы данных"
        source.answer_markdown = "Составной индекс содержит несколько колонок."
        session.add_all(
            [
                InterviewCard(
                    deck_id=source.deck_id,
                    slug=f"popular-{i}",
                    category="Разное",
                    question_markdown=f"Как устроены генераторы номер {i}?",
                    answer_markdown="Что такое генератор и зачем он нужен.",
                    frequency=InterviewCardFrequency.OCCASIONAL,
                    asked_count=100,
                    is_published=True,
                )
                for i in range(110)
            ]
        )
        await session.commit()
        sources = await load_trusted_sources(session, cluster)
        assert sources[0]["source_id"] == ready[3]
        assert len(sources) == 1


async def test_source_search_does_not_fill_context_with_common_question_words(ready):
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        cluster.canonical_question = "Что это такое и как оно работает?"
        cluster.normalized_canonical_question = "что это такое и как оно работает"
        assert await load_trusted_sources(session, cluster) == []


async def test_current_validation_rejects_missing_context_even_if_provider_says_supported(ready):
    class InconsistentProvider(FakeInterviewAIProvider):
        async def validate_answer_contract(self, *args, **kwargs):
            result = await super().validate_answer_contract(*args, **kwargs)
            return replace(
                result,
                output=AnswerValidationResult(
                    supported=True,
                    confidence=0.99,
                    question_is_self_contained=False,
                ),
            )

    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        cluster.answer_status = cluster.answer_validation = None
        await session.commit()
    await jobs.validate_cluster_answer(
        {"redis": RecordingRedis(), "ai_provider": InconsistentProvider()}, str(ready[0]), 1
    )
    async with TestSession() as session:
        assert (await session.get(QuestionCluster, ready[0])).linked_card_id is None
    assert await jobs.schedule_answer_repairs() == 0


async def test_outage_migration_moves_only_latest_technical_failures(ready, seeded):
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    from tests.conftest import test_engine
    from tests.test_card_automation_service import _cluster

    async with TestSession() as session:
        target = await session.get(QuestionCluster, ready[0])
        target.answer_status = AnswerContractStatus.NEEDS_MANUAL_REVIEW
        target.answer_validation = None
        saved_answer = target.answer_contract
        protected = _cluster(seeded.python_track_id, 97, status=QuestionClusterStatus.NEEDS_REVIEW)
        protected.answer_status = AnswerContractStatus.NEEDS_MANUAL_REVIEW
        session.add(protected)
        await session.flush()
        for cluster in (target, protected):
            session.add(
                AutomationDecision(
                    entity_type="cluster",
                    entity_id=cluster.id,
                    idempotency_key=str(uuid4()),
                    decision_type=AutomationDecisionType.ANSWER_VALIDATION_FAILED,
                    decision_source=AutomationDecisionSource.SEMANTIC_JUDGE,
                    reason="Quota exceeded",
                    judge_result={"error_code": "OPENAI_QUOTA_EXCEEDED"},
                )
            )
        session.add(
            AutomationDecision(
                entity_type="cluster",
                entity_id=protected.id,
                idempotency_key=str(uuid4()),
                decision_type=AutomationDecisionType.MANUAL_OVERRIDE,
                decision_source=AutomationDecisionSource.HUMAN,
                reason="Keep manual",
            )
        )
        await session.commit()
    spec = importlib.util.spec_from_file_location(
        "review_workflow_migration",
        Path(__file__).parents[1] / "migrations/versions/20260922_0090_card_review_workflow.py",
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def migrate(connection):
        context = MigrationContext.configure(connection)
        with context.begin_transaction(), Operations.context(context):
            migration.downgrade()
            migration.upgrade()

    async with test_engine.connect() as connection:
        await connection.run_sync(migrate)
    async with TestSession() as session:
        target = await session.get(QuestionCluster, ready[0])
        assert target.answer_status == AnswerContractStatus.WAITING_FOR_AI
        assert target.answer_contract == saved_answer
        assert target.answer_validation is None
        assert target.ai_retry_after > datetime.now(UTC)
        assert (
            await session.get(QuestionCluster, protected.id)
        ).answer_status == AnswerContractStatus.NEEDS_MANUAL_REVIEW


async def test_old_supported_version_caveat_rechecks_without_regenerating(ready):
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        original = cluster.answer_contract
        cluster.answer_status = AnswerContractStatus.NEEDS_MANUAL_REVIEW
        cluster.answer_validation = {
            "supported": True,
            "confidence": 0.97,
            "version_sensitive_claims": ["Applies to the stated version"],
        }
        await session.commit()
    assert await jobs.schedule_answer_repairs() == 1
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        assert cluster.answer_contract == original
        assert cluster.answer_validation is None
        assert cluster.answer_status is None
        assert cluster.answer_repair_attempts == 0
    ai = FakeInterviewAIProvider()
    await jobs.validate_cluster_answer(
        {"redis": RecordingRedis(), "ai_provider": ai}, str(ready[0]), 1
    )
    assert not ai.answer_contract_calls
    assert len(ai.answer_validation_calls) == 1


async def test_provider_outage_holds_shadow_backfill(ready, seeded):
    from tests.test_card_automation_service import _cluster

    async with TestSession() as session:
        waiting = await session.get(QuestionCluster, ready[0])
        waiting.answer_status = AnswerContractStatus.WAITING_FOR_AI
        waiting.ai_retry_after = datetime.now(UTC) + timedelta(hours=1)
        shadow = _cluster(seeded.python_track_id, 95, status=QuestionClusterStatus.SHADOW)
        shadow.membership_revision = shadow.stats_revision = 1
        session.add(shadow)
        await session.commit()
    redis = RecordingRedis()
    await jobs.reconcile_card_automation_jobs({"redis": redis})
    assert not any(
        name == "recalculate_cluster_stats" and args[0] == str(shadow.id)
        for name, args, _ in redis.calls
    )
