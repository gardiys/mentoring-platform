import asyncio
import importlib.util
from pathlib import Path
from uuid import UUID

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import func, select

from app.interviews import card_automation_jobs as jobs
from app.interviews.card_auto_publish import publish_validated_cluster
from app.interviews.card_automation_models import (
    AutomationDecision,
    CardAutomationSettings,
    QuestionCluster,
)
from app.interviews.card_automation_pipeline import recalculate_cluster_stats
from app.interviews.card_automation_types import (
    AnswerContractStatus,
    AutomationDecisionSource,
    AutomationDecisionType,
    LearningObjectType,
    QuestionClusterStatus,
    QuestionOccurrenceStatus,
)
from app.interviews.intelligence_ai import FakeInterviewAIProvider
from app.interviews.intelligence_models import (
    IntelligenceQuestion,
    IntelligenceQuestionModerationStatus,
)
from app.interviews.models import InterviewCard, InterviewCardOccurrence
from tests.conftest import TestSession, test_engine
from tests.test_card_automation_jobs import RecordingRedis
from tests.test_card_automation_pipeline import _create_card, _create_source


@pytest.fixture
async def ready(seeded, monkeypatch):
    monkeypatch.setattr(jobs, "async_session_factory", TestSession)
    source = await _create_source(seeded, "Как устроен сборщик мусора Python?")
    base = await _create_card(seeded, "Основы Python")
    # Numeric UUID components must not be redacted as phone/personal numbers.
    numeric_id = UUID("12345678-1234-4234-8234-123456789012")
    async with TestSession() as session:
        card = await session.get(InterviewCard, base.card_id)
        card.id = numeric_id
        await session.commit()
    base = type(base)(base.deck_id, numeric_id)
    reference = f"interview_card:{base.card_id}"
    async with TestSession() as session:
        settings = CardAutomationSettings(
            direction_id=seeded.python_track_id,
            enabled=True,
            shadow_mode=False,
            global_auto_publish_enabled=True,
            cluster_moderation_enabled=True,
        )
        session.add(settings)
        cluster = QuestionCluster(
            direction_id=seeded.python_track_id,
            status=QuestionClusterStatus.NEEDS_REVIEW,
            canonical_question="Как устроен сборщик мусора Python?",
            normalized_canonical_question="как устроен сборщик мусора python",
            learning_object_type=LearningObjectType.FLASHCARD,
            topic_name="Python",
            membership_revision=1,
            stats_revision=1,
            answer_contract={
                "short_answer": "Сборщик освобождает недостижимые циклические структуры.",
                "required_points": ["Учёт ссылок и циклы"],
                "difficulty": "middle",
                "source_references": [reference],
                "confidence": 0.95,
            },
            answer_validation={"supported": True, "confidence": 0.95},
            answer_status=AnswerContractStatus.GENERATED_FROM_SOURCES,
        )
        session.add(cluster)
        await session.flush()
        q = await session.get(IntelligenceQuestion, source.question_id)
        q.cluster_id = cluster.id
        q.automation_status = QuestionOccurrenceStatus.NEEDS_REVIEW
        q.is_standalone = q.is_real_interviewer_question = True
        q.routing_confidence = 0.95
        q.learning_object_type = LearningObjectType.FLASHCARD
        await session.commit()
    return cluster.id, source.question_id, base, reference


async def publish(ready, revision=1, references=None):
    async with TestSession() as session:
        card_id = await publish_validated_cluster(
            session, ready[0], revision, references if references is not None else {ready[3]}
        )
        await session.commit()
        return card_id


async def test_auto_publish_is_idempotent_and_does_not_forge_human_review(ready):
    results = await asyncio.gather(publish(ready), publish(ready))
    assert sum(result is not None for result in results) == 1
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        q = await session.get(IntelligenceQuestion, ready[1])
        card = await session.get(InterviewCard, cluster.linked_card_id)
        assert card.is_published and "Учёт ссылок" in card.answer_markdown
        assert cluster.status is QuestionClusterStatus.CARD_CREATED
        assert q.moderation_status is IntelligenceQuestionModerationStatus.APPROVED
        assert q.automation_status is QuestionOccurrenceStatus.AUTO_LINKED
        assert (
            not q.alias_human_confirmed
            and q.admin_reviewed_by_user_id is None
            and q.admin_reviewed_at is None
        )
        assert await session.scalar(select(func.count()).select_from(InterviewCard)) == 2
        assert await session.scalar(select(func.count()).select_from(InterviewCardOccurrence)) == 1
        decision = await session.scalar(
            select(AutomationDecision).where(
                AutomationDecision.decision_type == AutomationDecisionType.CARD_CREATED
            )
        )
        assert decision.decision_source is AutomationDecisionSource.RULE
        assert decision.selected_card_id == card.id
        sources = await jobs._trusted_sources(session, cluster)
        assert f"interview_card:{card.id}" not in {s["source_id"] for s in sources}


@pytest.mark.parametrize(
    "problem",
    [
        "low_confidence",
        "contradiction",
        "missing_points",
        "untrusted_source",
        "personal_data",
        "question_context",
        "uncertain_extraction",
        "human_rejected",
        "manual_draft",
        "missing_topic",
    ],
)
async def test_uncertain_cards_stay_for_review(ready, problem):
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        question = await session.get(IntelligenceQuestion, ready[1])
        if problem == "low_confidence":
            cluster.answer_validation = {"supported": True, "confidence": 0.5}
        elif problem == "contradiction":
            cluster.answer_validation = {
                "supported": True,
                "confidence": 0.99,
                "contradictions": ["Ошибка"],
            }
        elif problem == "missing_points":
            cluster.answer_validation = {
                "supported": True,
                "confidence": 0.99,
                "missing_required_points": ["Пропущен важный пункт"],
            }
        elif problem == "personal_data":
            cluster.canonical_question += " test@example.com"
        elif problem == "question_context":
            question.quality_flags = ["missing_context"]
        elif problem == "uncertain_extraction":
            question.confidence = 0.5
        elif problem == "human_rejected":
            question.moderation_status = IntelligenceQuestionModerationStatus.REJECTED
        elif problem == "manual_draft":
            session.add(
                AutomationDecision(
                    entity_type="cluster",
                    entity_id=cluster.id,
                    idempotency_key="manual-draft",
                    decision_type=AutomationDecisionType.MANUAL_OVERRIDE,
                    decision_source=AutomationDecisionSource.HUMAN,
                    reason="Исправлено",
                )
            )
        elif problem == "missing_topic":
            cluster.topic_name = "Неизвестная тема"
        await session.commit()
    assert await publish(ready, references=set() if problem == "untrusted_source" else None) is None
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        assert cluster.answer_status is AnswerContractStatus.NEEDS_MANUAL_REVIEW
        assert cluster.linked_card_id is None
        assert await session.scalar(select(func.count()).select_from(InterviewCard)) == 1
        if problem == "human_rejected":
            assert (
                await session.get(IntelligenceQuestion, ready[1])
            ).moderation_status is IntelligenceQuestionModerationStatus.REJECTED


@pytest.mark.parametrize("guard", ["disabled", "shadow", "flag_off", "stale", "deferred"])
async def test_settings_and_revisions_prevent_publication(ready, seeded, guard):
    async with TestSession() as session:
        settings = await session.get(CardAutomationSettings, seeded.python_track_id)
        if guard == "disabled":
            settings.enabled = False
        if guard == "shadow":
            settings.shadow_mode = True
        if guard == "flag_off":
            settings.global_auto_publish_enabled = False
        if guard == "deferred":
            (await session.get(QuestionCluster, ready[0])).status = QuestionClusterStatus.DEFERRED
        await session.commit()
    assert await publish(ready, revision=2 if guard == "stale" else 1) is None
    async with TestSession() as session:
        assert await session.scalar(select(func.count()).select_from(InterviewCard)) == 1


async def test_existing_exact_card_is_linked_without_creating_duplicate(ready):
    async with TestSession() as session:
        card = await session.get(InterviewCard, ready[2].card_id)
        card.question_markdown = "Как устроен сборщик мусора Python?"
        await session.commit()
    assert await publish(ready) == ready[2].card_id
    async with TestSession() as session:
        assert await session.scalar(select(func.count()).select_from(InterviewCard)) == 1
        assert (await session.get(QuestionCluster, ready[0])).status is QuestionClusterStatus.LINKED


async def test_busy_occurrence_is_retried_without_overwriting_review(ready):
    async with TestSession() as session:
        await session.get(IntelligenceQuestion, ready[1], with_for_update=True)
        assert await asyncio.wait_for(publish(ready), timeout=3) is None
        await session.rollback()
    assert await publish(ready) is not None


async def test_validation_job_publishes_and_reconciler_recovers_ready_backlog(ready):
    redis = RecordingRedis()
    ctx = {"redis": redis, "ai_provider": FakeInterviewAIProvider()}
    await jobs.reconcile_card_automation_jobs(ctx)
    assert any(
        name == "validate_cluster_answer" and args[0] == str(ready[0])
        for name, args, _ in redis.calls
    )
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        cluster.answer_status = None
        cluster.answer_validation = None
        await session.commit()
    await jobs.validate_cluster_answer(ctx, str(ready[0]), 1)
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        assert cluster.status is QuestionClusterStatus.CARD_CREATED


async def test_auto_mode_promotes_first_occurrence_and_reconciles_old_shadow(ready, seeded):
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        cluster.status = QuestionClusterStatus.SHADOW
        cluster.answer_status = None
        cluster.answer_contract = None
        cluster.answer_validation = None
        await session.commit()
    redis = RecordingRedis()
    await jobs.reconcile_card_automation_jobs({"redis": redis})
    assert any(
        name == "recalculate_cluster_stats" and args[0] == str(ready[0])
        for name, args, _ in redis.calls
    )
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        await recalculate_cluster_stats(session, cluster)
        assert cluster.status is QuestionClusterStatus.NEEDS_REVIEW
        assert cluster.distinct_interviews_count == 1


async def test_new_cluster_runs_generation_validation_and_publication(ready):
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        cluster.status = QuestionClusterStatus.SHADOW
        cluster.answer_contract = cluster.answer_validation = cluster.answer_status = None
        await session.commit()
    ai = FakeInterviewAIProvider()
    ctx = {"redis": RecordingRedis(), "ai_provider": ai}
    await jobs.recalculate_cluster_stats(ctx, str(ready[0]), 1)
    await jobs.generate_cluster_candidate(ctx, str(ready[0]), 1)
    await jobs.validate_cluster_answer(ctx, str(ready[0]), 1)
    async with TestSession() as session:
        assert (
            await session.get(QuestionCluster, ready[0])
        ).status is QuestionClusterStatus.CARD_CREATED


async def test_changed_sources_force_fresh_validation(ready):
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        cluster.answer_validation = cluster.answer_status = None
        settings = await session.get(CardAutomationSettings, cluster.direction_id)
        settings.global_auto_publish_enabled = False
        await session.commit()
    ai = FakeInterviewAIProvider()
    ctx = {"redis": RecordingRedis(), "ai_provider": ai}
    await jobs.validate_cluster_answer(ctx, str(ready[0]), 1)
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        settings = await session.get(CardAutomationSettings, cluster.direction_id)
        settings.global_auto_publish_enabled = True
        source = await session.get(InterviewCard, ready[2].card_id)
        source.answer_markdown = "Уточнённый материал о памяти Python."
        await session.commit()
    await jobs.validate_cluster_answer(ctx, str(ready[0]), 1)
    assert len(ai.answer_validation_calls) == 2
    async with TestSession() as session:
        assert (
            await session.get(QuestionCluster, ready[0])
        ).status is QuestionClusterStatus.CARD_CREATED


async def test_migration_enables_active_directions_and_preserves_published_cards(ready, seeded):
    spec = importlib.util.spec_from_file_location(
        "auto_publish_migration",
        Path(__file__).parents[1] / "migrations/versions/20260921_0088_card_auto_publish.py",
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def migrate(conn):
        with Operations.context(MigrationContext.configure(conn)):
            migration.downgrade()
            migration.upgrade()

    async with test_engine.begin() as conn:
        await conn.run_sync(migrate)
    async with TestSession() as session:
        settings = await session.get(CardAutomationSettings, seeded.python_track_id)
        assert (
            settings.enabled and settings.global_auto_publish_enabled and not settings.shadow_mode
        )
        assert await session.scalar(select(func.count()).select_from(InterviewCard)) == 1


@pytest.mark.parametrize("stage", ["generation", "validation"])
@pytest.mark.parametrize(
    "problem",
    ["no_sources", "missing_topic", "human", "uncertain", "personal_data", "duplicate", "linked"],
)
async def test_preflight_skips_paid_calls(ready, seeded, monkeypatch, stage, problem):
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        cluster.answer_status = cluster.answer_validation = None
        if stage == "generation":
            cluster.answer_contract = None
        if problem == "missing_topic":
            cluster.topic_name = "Неизвестная тема"
        elif problem == "linked":
            cluster.linked_card_id = ready[2].card_id
        elif problem == "human":
            session.add(
                AutomationDecision(
                    entity_type="cluster",
                    entity_id=cluster.id,
                    idempotency_key="preflight-human",
                    decision_type=AutomationDecisionType.MANUAL_OVERRIDE,
                    decision_source=AutomationDecisionSource.HUMAN,
                    reason="Изменено вручную",
                )
            )
        elif problem == "uncertain":
            (await session.get(IntelligenceQuestion, ready[1])).confidence = 0.5
        elif problem == "personal_data":
            cluster.canonical_question += " test@example.com"
        elif problem == "duplicate":
            (
                await session.get(InterviewCard, ready[2].card_id)
            ).question_markdown = cluster.canonical_question
        await session.commit()
    if problem == "duplicate":
        await _create_card(seeded, "Как устроен сборщик мусора Python?")
    if problem == "no_sources":

        async def empty_sources(session, cluster, **kwargs):
            return []

        monkeypatch.setattr(jobs, "load_trusted_sources", empty_sources)
    ai = FakeInterviewAIProvider()
    ctx = {"redis": RecordingRedis(), "ai_provider": ai}
    work = (
        jobs.generate_cluster_candidate if stage == "generation" else jobs.validate_cluster_answer
    )
    await work(ctx, str(ready[0]), 1)
    await work(ctx, str(ready[0]), 1)
    assert ai.answer_contract_calls == ai.answer_validation_calls == []
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        assert cluster.linked_card_id == (ready[2].card_id if problem == "linked" else None)
        assert cluster.answer_status is (
            AnswerContractStatus.NEEDS_EXPERT_SOURCE
            if problem == "no_sources"
            else AnswerContractStatus.NEEDS_MANUAL_REVIEW
        )
        decisions = list(
            await session.scalars(
                select(AutomationDecision).where(
                    AutomationDecision.entity_id == cluster.id,
                    AutomationDecision.decision_source == AutomationDecisionSource.RULE,
                )
            )
        )
        assert len(decisions) == 1
        assert decisions[0].judge_result["stage"] == "preflight"
        assert decisions[0].input_tokens is None


@pytest.mark.parametrize("change_during", ["generation", "validation"])
async def test_manual_change_during_ai_is_respected(ready, change_during):
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        cluster.answer_contract = cluster.answer_validation = cluster.answer_status = None
        await session.commit()

    async def reject_question():
        async with TestSession() as session:
            question = await session.get(IntelligenceQuestion, ready[1])
            question.moderation_status = IntelligenceQuestionModerationStatus.REJECTED
            await session.commit()

    class ChangingProvider(FakeInterviewAIProvider):
        async def generate_answer_contract(self, question, trusted_sources):
            result = await super().generate_answer_contract(question, trusted_sources)
            if change_during == "generation":
                await reject_question()
            return result

        async def validate_answer_contract(self, question, contract, trusted_sources):
            result = await super().validate_answer_contract(question, contract, trusted_sources)
            if change_during == "validation":
                await reject_question()
            return result

    ai = ChangingProvider()
    ctx = {"redis": RecordingRedis(), "ai_provider": ai}
    await jobs.generate_cluster_candidate(ctx, str(ready[0]), 1)
    await jobs.validate_cluster_answer(ctx, str(ready[0]), 1)
    assert len(ai.answer_contract_calls) == 1
    assert len(ai.answer_validation_calls) == (1 if change_during == "validation" else 0)
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        assert cluster.linked_card_id is None
        assert cluster.answer_status is AnswerContractStatus.NEEDS_MANUAL_REVIEW
        assert (
            await session.get(IntelligenceQuestion, ready[1])
        ).moderation_status is IntelligenceQuestionModerationStatus.REJECTED


async def test_explicit_manual_draft_can_run_after_preflight_deferral(ready):
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        cluster.answer_contract = cluster.answer_validation = None
        cluster.answer_status = AnswerContractStatus.NEEDS_MANUAL_REVIEW
        cluster.topic_name = "Неизвестная тема"
        session.add(
            AutomationDecision(
                entity_type="cluster",
                entity_id=cluster.id,
                idempotency_key="manual-draft-request",
                decision_type=AutomationDecisionType.MANUAL_OVERRIDE,
                decision_source=AutomationDecisionSource.HUMAN,
                reason="Запрошен AI-черновик",
            )
        )
        await session.commit()
    ai = FakeInterviewAIProvider()
    redis = RecordingRedis()
    ctx = {"redis": redis, "ai_provider": ai}
    await jobs.generate_cluster_candidate(ctx, str(ready[0]), 1, manual_draft=True)
    assert redis.calls[-1][2]["manual_draft"] is True
    assert redis.calls[-1][2]["_job_id"].endswith(":manual-draft")
    await jobs.validate_cluster_answer(ctx, str(ready[0]), 1, manual_draft=True)
    assert len(ai.answer_contract_calls) == len(ai.answer_validation_calls) == 1
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        assert cluster.answer_contract is not None
        assert cluster.answer_status is AnswerContractStatus.NEEDS_MANUAL_REVIEW
        assert cluster.linked_card_id is None
