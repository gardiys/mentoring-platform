"""Production regressions: evidence quality, bounded repair, and safe duplicate linking."""

import importlib.util
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from arq import Retry
from sqlalchemy import func, select

from app.interviews import card_automation_jobs as jobs
from app.interviews.card_answer_sources import load_trusted_sources
from app.interviews.card_automation_models import (
    AutomationDecision,
    CardAutomationSettings,
    QuestionCluster,
)
from app.interviews.card_automation_privacy import redact_untrusted_text
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
    PairwiseCardMatchDecision,
    QuestionClusterStatus,
)
from app.interviews.card_review_recovery import queue_review_backlog
from app.interviews.card_topic_resolution import resolved_topic
from app.interviews.intelligence_ai import FakeInterviewAIProvider, InterviewAIError
from app.interviews.intelligence_models import IntelligenceQuestion
from app.interviews.models import InterviewCard
from app.interviews.question_matching import normalize_question
from app.users.models import User
from tests.conftest import TestSession, test_engine
from tests.test_card_auto_publish import publish
from tests.test_card_auto_publish import ready as ready_fixture
from tests.test_card_automation_jobs import RecordingRedis

ready = ready_fixture


@pytest.mark.parametrize(
    "text",
    [
        "Что такое @staticmethod и @classmethod?",
        "Декораторы Python: @property, @dataclass, @lru_cache",
        "Разница между `@staticmethod` и `@classmethod`",
        "@custom_decorator\ndef example():\n    pass",
    ],
)
def test_code_decorators_survive_redaction(text):
    assert redact_untrusted_text(text) == text


@pytest.mark.parametrize(
    "text",
    [
        "Напишите @somebody",
        "Контакт: `@staticmethod`",
        "Python: telegram @classmethod",
        "Вопрос про Python: `@private_handle`",
        "Ник: @dataclass",
    ],
)
def test_real_contacts_still_redacted(text):
    assert "[TELEGRAM]" in redact_untrusted_text(text)


def test_topic_aliases_require_an_existing_unambiguous_category():
    assert resolved_topic("Apache Kafka", {"Брокеры сообщений", "Python"}) == "Брокеры сообщений"
    assert resolved_topic("asyncio", {"Конкурентность в Python"}) == "Конкурентность в Python"
    assert resolved_topic("Apache Kafka", {"Python"}) is None
    assert resolved_topic("Python", {"Основы Python", "Конкурентность в Python"}) is None


async def test_n_plus_one_retrieval_uses_original_question_and_relevant_long_excerpt(ready):
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        cluster.canonical_question = "Как решить проблему N+1 в базовом сценарии?"
        cluster.normalized_canonical_question = normalize_question(cluster.canonical_question)
        card = await session.get(InterviewCard, ready[2].card_id)
        card.question_markdown = "Проблема N+1 в ORM"
        card.answer_markdown = "Введение в работу с базами. " * 500 + (
            "N+1: используйте select_related для JOIN или prefetch_related для отдельного запроса."
        )
        await session.flush()
        sources = await load_trusted_sources(session, cluster)
        assert sources and sources[0]["source_id"] == ready[3]
        assert "select_related" in sources[0]["content"]
        assert len(sources[0]["content"]) <= 8000
        assert await load_trusted_sources(session, cluster, source_ids=[ready[3]]) == sources


def verified(**changes):
    return {
        "supported": True,
        "confidence": 0.98,
        "question_is_self_contained": True,
        "answer_is_substantive": True,
        "generator_warnings_resolved": True,
        **changes,
    }


async def test_independent_validation_can_resolve_generator_caveats(ready):
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        cluster.answer_contract = {
            **cluster.answer_contract,
            "confidence": 0.8,
            "unsupported_claims": ["Материалы не обсуждают различия версий, их нет и в ответе."],
        }
        cluster.answer_validation = verified()
        await session.commit()
    assert await publish(ready) is not None


@pytest.mark.parametrize(
    "problem",
    [
        {"answer_is_substantive": False},
        {"unverified_personal_claims": ["Я ускорил проект вдвое"]},
        {"contradictions": ["Ошибка"]},
        {"generator_warnings_resolved": False},
        {"confidence": 0.9},
    ],
)
async def test_independent_approval_never_bypasses_remaining_findings(ready, problem):
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        cluster.answer_contract = {**cluster.answer_contract, "confidence": 0.8}
        cluster.answer_validation = verified(**problem)
        await session.commit()
    assert await publish(ready) is None
    async with TestSession() as session:
        assert (await session.get(QuestionCluster, ready[0])).answer_status == Status.REVIEW_PENDING


@pytest.mark.parametrize(
    "flag,allowed",
    [("bad_transcription", True), ("missing_context", True), ("depends_on_code", False)],
)
async def test_canonical_question_can_clear_soft_flags_but_not_missing_code(ready, flag, allowed):
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        cluster.answer_validation = verified()
        question = await session.get(IntelligenceQuestion, ready[1])
        question.quality_flags = [flag]
        await session.commit()
    assert (await publish(ready) is not None) == allowed
    async with TestSession() as session:
        assert (await session.get(IntelligenceQuestion, ready[1])).quality_flags == [flag]


async def test_backlog_resets_budget_once_and_preserves_human_decisions(ready):
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        cluster.review_policy_version = 0
        cluster.answer_status = Status.NEEDS_MANUAL_REVIEW
        cluster.answer_repair_attempts = 2
        original_answer = cluster.answer_contract
        await session.commit()
    assert await queue_review_backlog(TestSession, limit=1) == 1
    assert await queue_review_backlog(TestSession, limit=1) == 0
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        assert cluster.answer_status == Status.REVIEW_PENDING
        assert cluster.answer_repair_attempts == 0
        assert cluster.answer_contract == original_answer
        cluster.review_policy_version = 0
        cluster.answer_status = Status.NEEDS_MANUAL_REVIEW
        session.add(
            AutomationDecision(
                entity_type="cluster",
                entity_id=cluster.id,
                idempotency_key="human-review",
                decision_type=Decision.MANUAL_OVERRIDE,
                decision_source=Source.HUMAN,
                reason="Keep for manual review",
            )
        )
        await session.commit()
    assert await queue_review_backlog(TestSession) == 0


async def test_recovery_repairs_a_failed_modern_answer_and_stops_after_budget(ready):
    ai, redis = FakeInterviewAIProvider(), RecordingRedis()
    ctx = {"ai_provider": ai, "redis": redis}
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        cluster.answer_status = Status.REVIEW_PENDING
        cluster.answer_validation = verified(answer_is_substantive=False)
        await session.commit()
    await jobs.review_cluster_for_automation(ctx, str(ready[0]), 1)
    assert [call[0] for call in redis.calls] == ["generate_cluster_candidate"]
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        assert cluster.answer_status == Status.REPAIR_PENDING
        cluster.answer_status = Status.REVIEW_PENDING
        cluster.answer_repair_attempts = 2
        await session.commit()
    await jobs.review_cluster_for_automation(ctx, str(ready[0]), 1)
    async with TestSession() as session:
        assert (
            await session.get(QuestionCluster, ready[0])
        ).answer_status == Status.NEEDS_MANUAL_REVIEW
    assert len(redis.calls) == 1
    assert not ai.answer_validation_calls and not ai.answer_contract_calls


class MatchAI(FakeInterviewAIProvider):
    decision = PairwiseCardMatchDecision.SAME_CARD

    async def judge_card_match(self, **kwargs):
        result = await super().judge_card_match(**kwargs)
        return replace(
            result,
            output=result.output.model_copy(
                update={
                    "decision": self.decision,
                    "confidence": 0.99,
                }
            ),
        )


async def setup_duplicate(ready):
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        cluster.answer_status = Status.REVIEW_PENDING
        card = await session.get(InterviewCard, ready[2].card_id)
        card.question_markdown = "Как работает сборщик мусора Python?"
        settings = await session.get(CardAutomationSettings, cluster.direction_id)
        settings.cluster_match_threshold = 0.4
        settings.auto_link_semantic_enabled = True
        original_answer = card.answer_markdown
        await session.commit()
        return original_answer


async def test_duplicate_verdict_survives_retry_and_links_without_answer_generation(ready):
    original = await setup_duplicate(ready)
    ai = MatchAI()
    ctx = {"ai_provider": ai, "redis": RecordingRedis()}
    with pytest.raises(Retry):
        await jobs.review_cluster_for_automation(ctx, str(ready[0]), 1)
    await jobs.review_cluster_for_automation(ctx, str(ready[0]), 1)
    async with TestSession() as session:
        assert (await session.get(QuestionCluster, ready[0])).linked_card_id == ready[2].card_id
        assert (await session.get(InterviewCard, ready[2].card_id)).answer_markdown == original
        assert await session.scalar(select(func.count()).select_from(InterviewCard)) == 1
    assert len(ai.card_match_calls) == 1
    assert not ai.answer_validation_calls and not ai.answer_contract_calls


async def test_edited_card_invalidates_saved_pairwise_verdict(ready):
    await setup_duplicate(ready)
    ai = MatchAI()
    ctx = {"ai_provider": ai, "redis": RecordingRedis()}
    with pytest.raises(Retry):
        await jobs.review_cluster_for_automation(ctx, str(ready[0]), 1)
    async with TestSession() as session:
        (await session.get(InterviewCard, ready[2].card_id)).answer_markdown += " Обновлено."
        await session.commit()
    with pytest.raises(Retry):
        await jobs.review_cluster_for_automation(ctx, str(ready[0]), 1)
    assert len(ai.card_match_calls) == 2
    async with TestSession() as session:
        assert (await session.get(QuestionCluster, ready[0])).linked_card_id is None


async def test_uncertain_duplicate_stays_manual_without_repeating_paid_check(ready):
    await setup_duplicate(ready)
    ai = MatchAI()
    ai.decision = PairwiseCardMatchDecision.UNCERTAIN
    ctx = {"ai_provider": ai, "redis": RecordingRedis()}
    with pytest.raises(Retry):
        await jobs.review_cluster_for_automation(ctx, str(ready[0]), 1)
    await jobs.review_cluster_for_automation(ctx, str(ready[0]), 1)
    await jobs.review_cluster_for_automation(ctx, str(ready[0]), 1)
    async with TestSession() as session:
        assert (
            await session.get(QuestionCluster, ready[0])
        ).answer_status == Status.NEEDS_MANUAL_REVIEW
    assert len(ai.card_match_calls) == 1


async def test_pairwise_rate_limit_resumes_review_stage(ready):
    await setup_duplicate(ready)

    class LimitedAI(MatchAI):
        async def judge_card_match(self, **kwargs):
            raise InterviewAIError("OPENAI_RATE_LIMIT", "Rate limited", retryable=True)

    await jobs.review_cluster_for_automation(
        {"ai_provider": LimitedAI(), "redis": RecordingRedis(), "job_try": 4}, str(ready[0]), 1
    )
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        assert cluster.answer_status == Status.WAITING_FOR_AI
        cluster.ai_retry_after = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    assert await jobs.resume_service_blocked_clusters() == 1
    async with TestSession() as session:
        assert (await session.get(QuestionCluster, ready[0])).answer_status == Status.REVIEW_PENDING


async def test_missing_sources_have_separate_actionable_queue(ready, seeded):
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        cluster.answer_status = Status.NEEDS_EXPERT_SOURCE
        cluster.ai_error_code = "no_trusted_sources"
        await session.commit()
        viewer = await session.get(User, seeded.admin_id)
        page = await list_question_clusters(
            session, viewer, QuestionClusterListFilters(sources_only=True)
        )
        assert page.total == page.waiting_for_sources_total == 1
        assert (
            page.manual_review_total == page.ai_processing_total == page.waiting_for_ai_total == 0
        )
        assert page.items[0].processing_state == "waiting_for_sources"


async def test_migration_marks_only_existing_rows_for_one_reconsideration(ready):
    path = Path(__file__).parents[1] / "migrations/versions/20260922_0092_card_review_policy.py"
    spec = importlib.util.spec_from_file_location("card_review_policy", path)
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
        cluster = await session.get(QuestionCluster, ready[0])
        assert cluster.review_policy_version == 0
        assert cluster.answer_status == Status.GENERATED_FROM_SOURCES
        assert cluster.linked_card_id is None
        from tests.test_card_automation_service import _cluster

        fresh = _cluster(cluster.direction_id, 2026, status=QuestionClusterStatus.NEEDS_REVIEW)
        session.add(fresh)
        await session.flush()
        assert fresh.review_policy_version == 1
        await session.commit()


@pytest.mark.parametrize("guard", ["human", "membership", "disabled", "deferred"])
async def test_saved_match_cannot_override_later_changes(ready, guard):
    await setup_duplicate(ready)
    ai = MatchAI()
    ctx = {"ai_provider": ai, "redis": RecordingRedis()}
    with pytest.raises(Retry):
        await jobs.review_cluster_for_automation(ctx, str(ready[0]), 1)
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        if guard == "human":
            session.add(
                AutomationDecision(
                    entity_type="cluster",
                    entity_id=cluster.id,
                    idempotency_key="manual-after-ai",
                    decision_type=Decision.MANUAL_OVERRIDE,
                    decision_source=Source.HUMAN,
                    reason="Retain manual decision",
                )
            )
        elif guard == "membership":
            cluster.membership_revision += 1
        elif guard == "disabled":
            (await session.get(CardAutomationSettings, cluster.direction_id)).enabled = False
        else:
            cluster.status = QuestionClusterStatus.DEFERRED
        await session.commit()
    await jobs.review_cluster_for_automation(ctx, str(ready[0]), 1)
    async with TestSession() as session:
        assert (await session.get(QuestionCluster, ready[0])).linked_card_id is None
    assert len(ai.card_match_calls) == 1


async def test_distinct_scope_proceeds_to_validation_without_merging(ready):
    await setup_duplicate(ready)
    ai = MatchAI()
    ai.decision = PairwiseCardMatchDecision.RELATED_DIFFERENT_SCOPE
    redis = RecordingRedis()
    ctx = {"ai_provider": ai, "redis": redis}
    with pytest.raises(Retry):
        await jobs.review_cluster_for_automation(ctx, str(ready[0]), 1)
    await jobs.review_cluster_for_automation(ctx, str(ready[0]), 1)
    assert [c[0] for c in redis.calls] == ["validate_cluster_answer"]
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        assert cluster.linked_card_id is None and cluster.answer_validation is None


async def test_more_than_three_candidates_never_start_an_unbounded_comparison(ready):
    await setup_duplicate(ready)
    # Four close but differently worded published cards require an editorial choice.
    async with TestSession() as session:
        base = await session.get(InterviewCard, ready[2].card_id)
        for index in range(3):
            session.add(
                InterviewCard(
                    deck_id=base.deck_id,
                    slug=f"similar-{index}",
                    category=base.category,
                    question_markdown=f"Как работает сборщик мусора Python {index}?",
                    answer_markdown="Опубликованный ответ",
                    is_published=True,
                    frequency=base.frequency,
                )
            )
        await session.commit()
    ai = MatchAI()
    await jobs.review_cluster_for_automation(
        {"ai_provider": ai, "redis": RecordingRedis()}, str(ready[0]), 1
    )
    assert not ai.card_match_calls
    async with TestSession() as session:
        assert (
            await session.get(QuestionCluster, ready[0])
        ).answer_status == Status.NEEDS_MANUAL_REVIEW


async def test_failed_validation_is_immediately_counted_as_ai_work(ready, seeded):
    class EmptyAnswerAI(FakeInterviewAIProvider):
        async def validate_answer_contract(self, **kwargs):
            result = await super().validate_answer_contract(**kwargs)
            return replace(
                result, output=result.output.model_copy(update={"answer_is_substantive": False})
            )

    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        cluster.answer_status = cluster.answer_validation = None
        await session.commit()
    await jobs.validate_cluster_answer(
        {"ai_provider": EmptyAnswerAI(), "redis": RecordingRedis()}, str(ready[0]), 1
    )
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        assert cluster.answer_status == Status.REVIEW_PENDING
        viewer = await session.get(User, seeded.admin_id)
        page = await list_question_clusters(
            session, viewer, QuestionClusterListFilters(processing_only=True)
        )
        assert page.ai_processing_total == 1 and page.manual_review_total == 0
    redis = RecordingRedis()
    await jobs.reconcile_card_automation_jobs({"redis": redis})
    assert any(
        c[0] == "review_cluster_for_automation" and c[1][0] == str(ready[0]) for c in redis.calls
    )
