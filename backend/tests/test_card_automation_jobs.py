from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from arq import Retry
from arq.connections import ArqRedis
from sqlalchemy import select

from app.interviews import card_automation_jobs, intelligence_jobs, intelligence_queue
from app.interviews.card_automation_models import (
    AutomationDecision,
    CardAutomationSettings,
    PersonalReviewItem,
    QuestionCluster,
)
from app.interviews.card_automation_types import (
    AnswerContractStatus,
    AutomationDecisionSource,
    AutomationDecisionType,
    LearningObjectType,
    PersonalReviewStatus,
    QuestionClusterStatus,
    QuestionOccurrenceStatus,
)
from app.interviews.intelligence_ai import (
    ANSWER_CONTRACT_SCHEMA_VERSION,
    ANSWER_VALIDATION_SCHEMA_VERSION,
    AIAnswerContractResult,
    AIAnswerValidationResult,
    AIQuestionRoutingResult,
    AnswerContract,
    FakeInterviewAIProvider,
    InterviewAIError,
    TrustedAnswerSource,
)
from app.interviews.intelligence_models import (
    IntelligenceAssessment,
    IntelligenceQuestion,
    IntelligenceQuestionModerationStatus,
)
from app.interviews.models import InterviewCard, InterviewCardOccurrence
from app.roadmaps.models import Topic
from tests.conftest import SeededData, TestSession
from tests.test_card_automation_pipeline import _create_card, _create_source, _process


@dataclass(frozen=True, slots=True)
class StubJob:
    job_id: str


class RecordingRedis:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, Any]]] = []

    async def enqueue_job(
        self,
        function: str,
        *args: object,
        **kwargs: Any,
    ) -> StubJob:
        self.calls.append((function, args, kwargs))
        return StubJob(cast(str, kwargs["_job_id"]))


class RetryValidationOnceProvider(FakeInterviewAIProvider):
    def __init__(self) -> None:
        super().__init__()
        self.validation_attempts = 0

    async def validate_answer_contract(
        self,
        question: str,
        contract: AnswerContract | Mapping[str, object],
        trusted_sources: Sequence[TrustedAnswerSource | Mapping[str, object]],
    ) -> AIAnswerValidationResult:
        self.validation_attempts += 1
        if self.validation_attempts == 1:
            raise InterviewAIError(
                "ANSWER_VALIDATION_TIMEOUT",
                "Answer validation timed out",
                retryable=True,
            )
        return await super().validate_answer_contract(question, contract, trusted_sources)


class NonRetryableGenerationProvider(FakeInterviewAIProvider):
    def __init__(self) -> None:
        super().__init__()
        self.generation_attempts = 0

    async def generate_answer_contract(
        self,
        question: str,
        trusted_sources: Sequence[TrustedAnswerSource | Mapping[str, object]],
    ) -> AIAnswerContractResult:
        del question, trusted_sources
        self.generation_attempts += 1
        raise InterviewAIError(
            "ANSWER_CONTRACT_INVALID",
            "Answer contract request was rejected",
            retryable=False,
        )


class NonRetryableValidationProvider(FakeInterviewAIProvider):
    def __init__(self) -> None:
        super().__init__()
        self.validation_attempts = 0

    async def validate_answer_contract(
        self,
        question: str,
        contract: AnswerContract | Mapping[str, object],
        trusted_sources: Sequence[TrustedAnswerSource | Mapping[str, object]],
    ) -> AIAnswerValidationResult:
        del question, contract, trusted_sources
        self.validation_attempts += 1
        raise InterviewAIError(
            "ANSWER_VALIDATION_INVALID",
            "Answer validation request was rejected",
            retryable=False,
        )


class RetryableAnswerProvider(FakeInterviewAIProvider):
    def __init__(self) -> None:
        super().__init__()
        self.generation_attempts = 0
        self.validation_attempts = 0

    async def generate_answer_contract(
        self,
        question: str,
        trusted_sources: Sequence[TrustedAnswerSource | Mapping[str, object]],
    ) -> AIAnswerContractResult:
        del question, trusted_sources
        self.generation_attempts += 1
        raise InterviewAIError(
            "ANSWER_CONTRACT_TIMEOUT",
            "Answer contract generation timed out",
            retryable=True,
        )

    async def validate_answer_contract(
        self,
        question: str,
        contract: AnswerContract | Mapping[str, object],
        trusted_sources: Sequence[TrustedAnswerSource | Mapping[str, object]],
    ) -> AIAnswerValidationResult:
        del question, contract, trusted_sources
        self.validation_attempts += 1
        raise InterviewAIError(
            "ANSWER_VALIDATION_TIMEOUT",
            "Answer contract validation timed out",
            retryable=True,
        )


class AlwaysRetryableRoutingProvider(FakeInterviewAIProvider):
    def __init__(self) -> None:
        super().__init__()
        self.routing_attempts = 0

    async def route_question(
        self,
        *,
        question: str,
        candidate_answer: str,
        context: str,
        available_broad_topics: list[str],
    ) -> AIQuestionRoutingResult:
        del question, candidate_answer, context, available_broad_topics
        self.routing_attempts += 1
        raise InterviewAIError(
            "ROUTING_TIMEOUT",
            "Routing provider timed out",
            retryable=True,
        )


async def _enable_cluster_automation(seeded: SeededData) -> None:
    async with TestSession() as session:
        session.add(
            CardAutomationSettings(
                direction_id=seeded.python_track_id,
                enabled=True,
                shadow_mode=True,
                cluster_moderation_enabled=True,
                legacy_queue_enabled=True,
                audit_sample_percent=100,
            )
        )
        await session.commit()


def _contract(source_id: str) -> dict[str, object]:
    return {
        "short_answer": "Типы задают допустимые операции над значениями.",
        "required_points": [],
        "optional_points": [],
        "common_mistakes": [],
        "unsupported_claims": [],
        "follow_up_questions": [],
        "difficulty": "mixed",
        "version_scope": [],
        "source_references": [source_id],
        "confidence": 0.9,
    }


async def _create_cluster(
    seeded: SeededData,
    *,
    question: str = "Как работают типы в Python?",
    status: QuestionClusterStatus = QuestionClusterStatus.NEEDS_REVIEW,
    membership_revision: int = 1,
    stats_revision: int | None = None,
    answer_contract: dict[str, object] | None = None,
    answer_status: AnswerContractStatus | None = None,
) -> UUID:
    unique = uuid4().hex
    cluster = QuestionCluster(
        id=uuid4(),
        direction_id=seeded.python_track_id,
        status=status,
        canonical_question=question,
        normalized_canonical_question=f"{question.casefold().rstrip('?')} {unique}",
        learning_object_type=LearningObjectType.FLASHCARD,
        answer_contract=answer_contract,
        answer_status=answer_status,
        membership_revision=membership_revision,
        stats_revision=(membership_revision if stats_revision is None else stats_revision),
    )
    async with TestSession() as session:
        session.add(cluster)
        await session.commit()
    return cluster.id


def _ctx(redis: RecordingRedis, ai: FakeInterviewAIProvider) -> dict[str, object]:
    return {
        "redis": cast(ArqRedis, redis),
        "ai_provider": ai,
        "job_try": 1,
    }


@pytest.mark.asyncio
async def test_validation_retry_reuses_generated_contract(
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _enable_cluster_automation(seeded)
    async with TestSession() as session:
        topic = await session.get(Topic, seeded.topic_ids[0])
        assert topic is not None
        topic.title = "Типы @private_user"
        topic.content_markdown = (
            "Автор: Мария Волкова. Связь: secret@example.com, "
            "+7 (999) 123-45-67, зарплата 350000 рублей."
        )
        await session.commit()
    cluster_id = await _create_cluster(seeded)
    redis = RecordingRedis()
    ai = RetryValidationOnceProvider()
    monkeypatch.setattr(card_automation_jobs, "async_session_factory", TestSession)

    await card_automation_jobs.generate_cluster_candidate(_ctx(redis, ai), str(cluster_id), 1)
    async with TestSession() as session:
        generated = await session.get(QuestionCluster, cluster_id)
        assert generated is not None
        assert generated.answer_contract is not None
        assert generated.answer_validation is None
        assert generated.answer_status is None
        original_contract = dict(generated.answer_contract)

    with pytest.raises(Retry):
        await card_automation_jobs.validate_cluster_answer(_ctx(redis, ai), str(cluster_id), 1)
    await card_automation_jobs.generate_cluster_candidate(_ctx(redis, ai), str(cluster_id), 1)
    await card_automation_jobs.validate_cluster_answer(_ctx(redis, ai), str(cluster_id), 1)
    await card_automation_jobs.validate_cluster_answer(_ctx(redis, ai), str(cluster_id), 1)

    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, cluster_id)
        decisions = list(
            await session.scalars(
                select(AutomationDecision)
                .where(AutomationDecision.entity_id == cluster_id)
                .order_by(AutomationDecision.created_at)
            )
        )
        assert cluster is not None
        assert cluster.answer_contract == original_contract
        assert cluster.answer_validation is not None
        assert cluster.answer_status is AnswerContractStatus.GENERATED_FROM_SOURCES
        assert [decision.decision_type for decision in decisions] == [
            AutomationDecisionType.ANSWER_CONTRACT_GENERATED,
            AutomationDecisionType.ANSWER_CONTRACT_VALIDATED,
        ]
        assert [decision.schema_version for decision in decisions] == [
            ANSWER_CONTRACT_SCHEMA_VERSION,
            ANSWER_VALIDATION_SCHEMA_VERSION,
        ]
        assert all(
            decision.latency_ms is not None and decision.latency_ms >= 0 for decision in decisions
        )
        assert all(decision.is_audit_sample for decision in decisions)
    assert len(ai.answer_contract_calls) == 1
    trusted_sources = str(ai.answer_contract_calls[0]["trusted_sources"])
    assert "secret@example.com" not in trusted_sources
    assert "@private_user" not in trusted_sources
    assert "999" not in trusted_sources
    assert "350000" not in trusted_sources
    assert "Мария" not in trusted_sources
    assert "Волкова" not in trusted_sources
    assert "[EMAIL]" in trusted_sources
    assert "[TELEGRAM]" in trusted_sources
    assert "[LONG_NUMBER]" in trusted_sources
    assert "[FINANCIAL]" in trusted_sources
    assert "[PERSON_NAME]" in trusted_sources
    assert ai.validation_attempts == 2
    assert len(ai.answer_validation_calls) == 1


@pytest.mark.asyncio
async def test_identical_answer_inputs_reuse_persisted_generation_and_validation(
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _enable_cluster_automation(seeded)
    first_cluster_id = await _create_cluster(seeded)
    second_cluster_id = await _create_cluster(seeded)
    redis = RecordingRedis()
    ai = FakeInterviewAIProvider()
    monkeypatch.setattr(card_automation_jobs, "async_session_factory", TestSession)

    for cluster_id in (first_cluster_id, second_cluster_id):
        await card_automation_jobs.generate_cluster_candidate(
            _ctx(redis, ai),
            str(cluster_id),
            1,
        )
    for cluster_id in (first_cluster_id, second_cluster_id):
        await card_automation_jobs.validate_cluster_answer(
            _ctx(redis, ai),
            str(cluster_id),
            1,
        )

    async with TestSession() as session:
        decisions = {
            (decision.entity_id, decision.decision_type): decision
            for decision in await session.scalars(
                select(AutomationDecision).where(
                    AutomationDecision.entity_id.in_([first_cluster_id, second_cluster_id])
                )
            )
        }
        second_generation = decisions[
            (second_cluster_id, AutomationDecisionType.ANSWER_CONTRACT_GENERATED)
        ]
        second_validation = decisions[
            (second_cluster_id, AutomationDecisionType.ANSWER_CONTRACT_VALIDATED)
        ]
        assert second_generation.decision_source is AutomationDecisionSource.RULE
        assert second_validation.decision_source is AutomationDecisionSource.RULE
        assert "reused" in second_generation.reason
        assert "reused" in second_validation.reason
        assert (
            second_generation.input_hash
            == decisions[
                (first_cluster_id, AutomationDecisionType.ANSWER_CONTRACT_GENERATED)
            ].input_hash
        )
        assert (
            second_validation.input_hash
            == decisions[
                (first_cluster_id, AutomationDecisionType.ANSWER_CONTRACT_VALIDATED)
            ].input_hash
        )
    assert len(ai.answer_contract_calls) == 1
    assert len(ai.answer_validation_calls) == 1


@pytest.mark.asyncio
async def test_generation_transfers_existing_ai_review_answer_into_cluster_draft(
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _enable_cluster_automation(seeded)
    source = await _create_source(
        seeded,
        "Что такое event loop?",
        answer_text="Не знаю.",
        assessment=IntelligenceAssessment.INCORRECT,
    )
    cluster_id = await _create_cluster(
        seeded,
        question="Что такое event loop?",
        status=QuestionClusterStatus.CANDIDATE,
    )
    async with TestSession() as session:
        question = await session.get_one(IntelligenceQuestion, source.question_id)
        question.cluster_id = cluster_id
        await session.commit()

    redis = RecordingRedis()
    ai = FakeInterviewAIProvider()
    monkeypatch.setattr(card_automation_jobs, "async_session_factory", TestSession)

    await card_automation_jobs.generate_cluster_candidate(
        _ctx(redis, ai),
        str(cluster_id),
        1,
    )

    async with TestSession() as session:
        cluster = await session.get_one(QuestionCluster, cluster_id)
        decision = await session.scalar(
            select(AutomationDecision).where(
                AutomationDecision.entity_id == cluster_id,
                AutomationDecision.decision_type
                == AutomationDecisionType.ANSWER_CONTRACT_GENERATED,
            )
        )
        assert cluster.answer_contract is not None
        assert cluster.answer_contract["short_answer"] == "Краткий корректный ответ."
        assert cluster.answer_contract["confidence"] == 0.5
        assert "требует проверки" in str(cluster.answer_contract["unsupported_claims"])
        assert decision is not None
        assert "transferred" in decision.reason
    assert ai.answer_contract_calls == []
    assert [(name, args) for name, args, _options in redis.calls] == [
        ("validate_cluster_answer", (str(cluster_id), 1))
    ]


@pytest.mark.asyncio
async def test_reconciler_restores_each_persisted_stage_and_retries_source_blocked_drafts(
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _enable_cluster_automation(seeded)
    source = await _create_source(seeded, "Как работает event loop?")
    routed_source = await _create_source(seeded, "Что уже является terminal proposal?")
    dirty_cluster_id = await _create_cluster(
        seeded,
        status=QuestionClusterStatus.SHADOW,
        membership_revision=2,
        stats_revision=1,
    )
    generation_cluster_id = await _create_cluster(seeded)
    validation_cluster_id = await _create_cluster(
        seeded,
        answer_contract=_contract(f"roadmap_topic:{seeded.topic_ids[0]}"),
    )
    terminal_cluster_id = await _create_cluster(
        seeded,
        question="Материал без подтверждённых источников?",
        answer_status=AnswerContractStatus.NEEDS_EXPERT_SOURCE,
    )
    async with TestSession() as session:
        question = await session.get(IntelligenceQuestion, source.question_id)
        assert question is not None
        question.direction_id = seeded.python_track_id
        question.automation_status = QuestionOccurrenceStatus.CREATED
        routed_question = await session.get(
            IntelligenceQuestion,
            routed_source.question_id,
        )
        assert routed_question is not None
        routed_question.automation_status = QuestionOccurrenceStatus.ROUTED
        expired_item = PersonalReviewItem(
            student_id=seeded.student_id,
            direction_id=seeded.python_track_id,
            source_occurrence_id=source.question_id,
            source_analysis_id=source.interview_id,
            question_text="Просроченный личный вопрос",
            status=PersonalReviewStatus.ACTIVE,
            due_at=datetime.now(UTC) - timedelta(days=2),
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
        active_item = PersonalReviewItem(
            student_id=seeded.student_id,
            direction_id=seeded.python_track_id,
            source_occurrence_id=None,
            source_analysis_id=source.interview_id,
            question_text="Актуальный личный вопрос",
            status=PersonalReviewStatus.ACTIVE,
            due_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        session.add_all([expired_item, active_item])
        await session.commit()

    redis = RecordingRedis()
    monkeypatch.setattr(card_automation_jobs, "async_session_factory", TestSession)
    await card_automation_jobs.reconcile_card_automation_jobs({"redis": cast(ArqRedis, redis)})

    queued = [(name, args) for name, args, _options in redis.calls]
    assert (
        "route_question_occurrence",
        (str(source.question_id), 1),
    ) in queued
    assert all(str(routed_source.question_id) not in args for _name, args in queued)
    assert (
        "recalculate_cluster_stats",
        (str(dirty_cluster_id), 2),
    ) in queued
    assert (
        "generate_cluster_candidate",
        (str(generation_cluster_id), 1),
    ) in queued
    assert (
        "validate_cluster_answer",
        (str(validation_cluster_id), 1),
    ) in queued
    assert (
        "generate_cluster_candidate",
        (str(terminal_cluster_id), 1),
    ) in queued
    assert len(queued) == 5
    async with TestSession() as session:
        archived = await session.get(PersonalReviewItem, expired_item.id)
        active = await session.get(PersonalReviewItem, active_item.id)
        archive_decision = await session.scalar(
            select(AutomationDecision).where(
                AutomationDecision.entity_id == expired_item.id,
                AutomationDecision.decision_type == AutomationDecisionType.PERSONAL_REVIEW_ARCHIVED,
            )
        )
        assert archived is not None
        assert active is not None
        assert archived.status is PersonalReviewStatus.ARCHIVED
        assert archived.version == 2
        assert active.status is PersonalReviewStatus.ACTIVE
        assert active.version == 1
        assert archive_decision is not None
        assert archive_decision.reason == "Personal review item expired and was archived"


@pytest.mark.asyncio
async def test_routing_retry_exhaustion_is_terminal_audited_and_not_reconciled(
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _enable_cluster_automation(seeded)
    source = await _create_source(seeded, "Что такое coroutine в Python?")
    redis = RecordingRedis()
    ai = AlwaysRetryableRoutingProvider()
    monkeypatch.setattr(card_automation_jobs, "async_session_factory", TestSession)

    first_context = _ctx(redis, ai)
    with pytest.raises(Retry):
        await card_automation_jobs.route_question_occurrence(
            first_context,
            str(source.question_id),
            1,
        )

    await card_automation_jobs.route_question_occurrence(
        {
            **first_context,
            "job_try": card_automation_jobs.CARD_AUTOMATION_JOB_MAX_TRIES,
        },
        str(source.question_id),
        1,
    )
    await card_automation_jobs.reconcile_card_automation_jobs({"redis": cast(ArqRedis, redis)})

    async with TestSession() as session:
        question = await session.get(IntelligenceQuestion, source.question_id)
        decisions = list(
            await session.scalars(
                select(AutomationDecision)
                .where(
                    AutomationDecision.entity_id == source.question_id,
                    AutomationDecision.decision_type == AutomationDecisionType.OCCURRENCE_FAILED,
                )
                .order_by(AutomationDecision.created_at, AutomationDecision.id)
            )
        )
        assert question is not None
        assert question.automation_status is QuestionOccurrenceStatus.FAILED
        assert question.automation_attempts == 2
        assert question.automation_error == (
            "ROUTING_TIMEOUT: Retry budget exhausted: Routing provider timed out"
        )
        assert len(decisions) == 2
        assert [decision.judge_result["retryable"] for decision in decisions] == [True, False]
        assert [decision.judge_result["terminal"] for decision in decisions] == [False, True]
        assert len({decision.idempotency_key for decision in decisions}) == 2
    assert ai.routing_attempts == 2
    assert all(
        not (name == "route_question_occurrence" and args == (str(source.question_id), 1))
        for name, args, _options in redis.calls
    )


@pytest.mark.asyncio
async def test_no_sources_generates_a_draft_and_requires_expert_review(
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _enable_cluster_automation(seeded)
    cluster_id = await _create_cluster(
        seeded,
        question="Квантовая хромодинамика адронов?",
    )
    redis = RecordingRedis()
    ai = FakeInterviewAIProvider()
    monkeypatch.setattr(card_automation_jobs, "async_session_factory", TestSession)

    await card_automation_jobs.generate_cluster_candidate(_ctx(redis, ai), str(cluster_id), 1)
    await card_automation_jobs.generate_cluster_candidate(_ctx(redis, ai), str(cluster_id), 1)
    await card_automation_jobs.validate_cluster_answer(_ctx(redis, ai), str(cluster_id), 1)
    await card_automation_jobs.reconcile_card_automation_jobs({"redis": cast(ArqRedis, redis)})

    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, cluster_id)
        decisions = list(
            await session.scalars(
                select(AutomationDecision)
                .where(AutomationDecision.entity_id == cluster_id)
                .order_by(AutomationDecision.created_at, AutomationDecision.id)
            )
        )
        assert cluster is not None
        assert cluster.answer_contract is not None
        assert cluster.answer_contract["short_answer"]
        assert cluster.answer_contract["source_references"] == []
        assert cluster.answer_status is AnswerContractStatus.NEEDS_EXPERT_SOURCE
        assert cluster.version == 3
        assert [decision.decision_type for decision in decisions] == [
            AutomationDecisionType.ANSWER_CONTRACT_GENERATED,
            AutomationDecisionType.ANSWER_CONTRACT_NEEDS_SOURCE,
        ]
        assert decisions[0].reason == (
            "Best-effort AI answer draft generated without internal sources; "
            "expert review is required"
        )
        assert decisions[1].judge_result == {
            "stage": "validation",
            "outcome": "needs_source",
            "error_code": "no_trusted_sources",
            "retryable": False,
            "terminal": True,
        }
    assert len(ai.answer_contract_calls) == 1
    assert [(name, args) for name, args, _options in redis.calls if str(cluster_id) in args] == [
        ("validate_cluster_answer", (str(cluster_id), 1))
    ]


@pytest.mark.asyncio
async def test_nonretryable_generation_and_validation_failures_are_terminal_and_audited(
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _enable_cluster_automation(seeded)
    generation_cluster_id = await _create_cluster(seeded)
    validation_cluster_id = await _create_cluster(
        seeded,
        answer_contract=_contract(f"roadmap_topic:{seeded.topic_ids[0]}"),
    )
    redis = RecordingRedis()
    generation_ai = NonRetryableGenerationProvider()
    validation_ai = NonRetryableValidationProvider()
    monkeypatch.setattr(card_automation_jobs, "async_session_factory", TestSession)

    await card_automation_jobs.generate_cluster_candidate(
        _ctx(redis, generation_ai), str(generation_cluster_id), 1
    )
    await card_automation_jobs.generate_cluster_candidate(
        _ctx(redis, generation_ai), str(generation_cluster_id), 1
    )
    await card_automation_jobs.validate_cluster_answer(
        _ctx(redis, validation_ai), str(validation_cluster_id), 1
    )
    await card_automation_jobs.validate_cluster_answer(
        _ctx(redis, validation_ai), str(validation_cluster_id), 1
    )

    async with TestSession() as session:
        clusters = {
            cluster.id: cluster
            for cluster in await session.scalars(
                select(QuestionCluster).where(
                    QuestionCluster.id.in_([generation_cluster_id, validation_cluster_id])
                )
            )
        }
        decisions = {
            decision.entity_id: decision
            for decision in await session.scalars(
                select(AutomationDecision).where(
                    AutomationDecision.entity_id.in_([generation_cluster_id, validation_cluster_id])
                )
            )
        }
        assert clusters[generation_cluster_id].answer_status is (
            AnswerContractStatus.NEEDS_MANUAL_REVIEW
        )
        assert clusters[validation_cluster_id].answer_status is (
            AnswerContractStatus.NEEDS_MANUAL_REVIEW
        )
        assert decisions[generation_cluster_id].decision_type is (
            AutomationDecisionType.ANSWER_CONTRACT_FAILED
        )
        assert decisions[generation_cluster_id].judge_result == {
            "stage": "generation",
            "outcome": "failed",
            "error_code": "ANSWER_CONTRACT_INVALID",
            "retryable": False,
            "terminal": True,
        }
        assert decisions[validation_cluster_id].decision_type is (
            AutomationDecisionType.ANSWER_VALIDATION_FAILED
        )
        assert decisions[validation_cluster_id].judge_result == {
            "stage": "validation",
            "outcome": "failed",
            "error_code": "ANSWER_VALIDATION_INVALID",
            "retryable": False,
            "terminal": True,
        }
    assert generation_ai.generation_attempts == 1
    assert validation_ai.validation_attempts == 1


@pytest.mark.asyncio
async def test_retryable_answer_failures_become_terminal_after_retry_budget(
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _enable_cluster_automation(seeded)
    generation_cluster_id = await _create_cluster(seeded)
    validation_cluster_id = await _create_cluster(
        seeded,
        answer_contract=_contract(f"roadmap_topic:{seeded.topic_ids[0]}"),
    )
    redis = RecordingRedis()
    ai = RetryableAnswerProvider()
    monkeypatch.setattr(card_automation_jobs, "async_session_factory", TestSession)

    first_attempt = _ctx(redis, ai)
    with pytest.raises(Retry):
        await card_automation_jobs.generate_cluster_candidate(
            first_attempt,
            str(generation_cluster_id),
            1,
        )
    with pytest.raises(Retry):
        await card_automation_jobs.validate_cluster_answer(
            first_attempt,
            str(validation_cluster_id),
            1,
        )

    final_attempt = {
        **first_attempt,
        "job_try": card_automation_jobs.ANSWER_JOB_MAX_TRIES,
    }
    await card_automation_jobs.generate_cluster_candidate(
        final_attempt,
        str(generation_cluster_id),
        1,
    )
    await card_automation_jobs.validate_cluster_answer(
        final_attempt,
        str(validation_cluster_id),
        1,
    )

    async with TestSession() as session:
        clusters = {
            cluster.id: cluster
            for cluster in await session.scalars(
                select(QuestionCluster).where(
                    QuestionCluster.id.in_([generation_cluster_id, validation_cluster_id])
                )
            )
        }
        decisions = {
            decision.entity_id: decision
            for decision in await session.scalars(
                select(AutomationDecision).where(
                    AutomationDecision.entity_id.in_([generation_cluster_id, validation_cluster_id])
                )
            )
        }
        assert all(
            cluster.answer_status is AnswerContractStatus.NEEDS_MANUAL_REVIEW
            for cluster in clusters.values()
        )
        assert decisions[generation_cluster_id].decision_type is (
            AutomationDecisionType.ANSWER_CONTRACT_FAILED
        )
        assert decisions[validation_cluster_id].decision_type is (
            AutomationDecisionType.ANSWER_VALIDATION_FAILED
        )
        assert all(
            decision.judge_result is not None
            and decision.judge_result["outcome"] == "retry_exhausted"
            and decision.judge_result["retryable"] is True
            and decision.judge_result["terminal"] is True
            for decision in decisions.values()
        )
    assert ai.generation_attempts == 2
    assert ai.validation_attempts == 2


@pytest.mark.asyncio
async def test_bounded_backfill_registers_and_enqueues_revision_aware_batches(
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _enable_cluster_automation(seeded)
    sources = [await _create_source(seeded, f"Legacy question {index}?") for index in range(2)]
    human_owned = await _create_source(seeded, "Human moderated question?")
    async with TestSession() as session:
        questions = list(
            await session.scalars(
                select(IntelligenceQuestion).where(
                    IntelligenceQuestion.id.in_(
                        [
                            *[source.question_id for source in sources],
                            human_owned.question_id,
                        ]
                    )
                )
            )
        )
        for question in questions:
            question.direction_id = seeded.python_track_id
        human_question = next(
            question for question in questions if question.id == human_owned.question_id
        )
        human_question.moderation_status = IntelligenceQuestionModerationStatus.MENTOR_APPROVED
        await session.commit()

    redis = RecordingRedis()
    monkeypatch.setattr(card_automation_jobs, "async_session_factory", TestSession)
    await card_automation_jobs.backfill_existing_questions(
        {"redis": cast(ArqRedis, redis)},
        str(seeded.python_track_id),
        batch_size=1,
    )
    await card_automation_jobs.backfill_existing_questions(
        {"redis": cast(ArqRedis, redis)},
        str(seeded.python_track_id),
        batch_size=1,
    )

    queued = [(name, args) for name, args, _options in redis.calls]
    assert {name for name, _args in queued} == {"route_question_occurrence"}
    assert {args for _name, args in queued} == {(str(source.question_id), 1) for source in sources}
    async with TestSession() as session:
        processed = list(
            await session.scalars(
                select(IntelligenceQuestion).where(
                    IntelligenceQuestion.id.in_([source.question_id for source in sources])
                )
            )
        )
        protected = await session.get(IntelligenceQuestion, human_owned.question_id)
        assert all(
            question.automation_status is QuestionOccurrenceStatus.ROUTING for question in processed
        )
        assert protected is not None
        assert protected.automation_status is QuestionOccurrenceStatus.CREATED
    assert "backfill_existing_questions" in intelligence_queue.OPENAI_FUNCTIONS
    assert card_automation_jobs.backfill_existing_questions in (
        intelligence_jobs.AIWorkerSettings.functions
    )


@pytest.mark.asyncio
async def test_reprocess_unlinks_automatic_card_and_cluster_and_reactivates_personal_item(
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _enable_cluster_automation(seeded)
    async with TestSession() as session:
        settings = await session.get(CardAutomationSettings, seeded.python_track_id)
        assert settings is not None
        settings.shadow_mode = False
        settings.auto_link_exact_enabled = True
        settings.personal_review_enabled = True
        await session.commit()
    card_fixture = await _create_card(seeded, "Что такое GIL?")
    source = await _create_source(
        seeded,
        "Что такое GIL?",
        answer_text="Не знаю.",
        assessment=IntelligenceAssessment.INCORRECT,
    )
    await _process(FakeInterviewAIProvider(), source.question_id)
    cluster_id = await _create_cluster(
        seeded,
        question="Что такое GIL?",
        status=QuestionClusterStatus.SHADOW,
    )
    personal = PersonalReviewItem(
        student_id=seeded.student_id,
        direction_id=seeded.python_track_id,
        source_occurrence_id=source.question_id,
        source_analysis_id=source.interview_id,
        canonical_card_id=card_fixture.card_id,
        replaced_by_card_id=card_fixture.card_id,
        question_text="Что такое GIL?",
        status=PersonalReviewStatus.REPLACED_BY_CANONICAL_CARD,
        due_at=datetime.now(UTC) + timedelta(days=10),
        expires_at=datetime.now(UTC) + timedelta(days=365),
    )
    async with TestSession() as session:
        question = await session.get(IntelligenceQuestion, source.question_id)
        cluster = await session.get(QuestionCluster, cluster_id)
        assert question is not None
        assert cluster is not None
        question.cluster_id = cluster.id
        cluster.representative_occurrence_id = question.id
        session.add(personal)
        await session.commit()

    redis = RecordingRedis()
    monkeypatch.setattr(card_automation_jobs, "async_session_factory", TestSession)
    await card_automation_jobs.reprocess_question_occurrence(
        _ctx(redis, FakeInterviewAIProvider()),
        str(source.question_id),
        1,
    )

    async with TestSession() as session:
        question = await session.get(IntelligenceQuestion, source.question_id)
        card = await session.get(InterviewCard, card_fixture.card_id)
        cluster = await session.get(QuestionCluster, cluster_id)
        personal_item = await session.get(PersonalReviewItem, personal.id)
        assert question is not None
        assert card is not None
        assert cluster is not None
        assert personal_item is not None
        assert question.automation_status is QuestionOccurrenceStatus.CREATED
        assert question.automation_revision == 2
        assert question.published_card_id is None
        assert question.cluster_id is None
        assert card.asked_count == 0
        assert card.companies is None
        assert cluster.status is QuestionClusterStatus.IGNORED
        assert cluster.occurrences_count == 0
        assert cluster.membership_revision == 2
        assert cluster.stats_revision == 2
        assert personal_item.status is PersonalReviewStatus.ACTIVE
        assert personal_item.canonical_card_id is None
        assert personal_item.replaced_by_card_id is None
        assert personal_item.version == 2
        assert (
            await session.scalar(
                select(InterviewCardOccurrence).where(
                    InterviewCardOccurrence.source_question_id == source.question_id
                )
            )
            is None
        )
    assert [(name, args) for name, args, _options in redis.calls] == [
        ("route_question_occurrence", (str(source.question_id), 2))
    ]
