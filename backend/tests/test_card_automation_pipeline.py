from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, func, select

from app.interviews import card_automation_service
from app.interviews.card_automation_models import (
    AutomationDecision,
    CardAutomationSettings,
    PersonalReviewItem,
    QuestionCluster,
)
from app.interviews.card_automation_pipeline import (
    process_question_occurrence,
    recalculate_cluster_stats,
)
from app.interviews.card_automation_privacy import redact_untrusted_text
from app.interviews.card_automation_types import (
    AutomationDecisionSource,
    AutomationDecisionType,
    LearningObjectType,
    PairwiseCardMatchDecision,
    PersonalReviewStatus,
    QuestionClusterStatus,
    QuestionOccurrenceStatus,
)
from app.interviews.intelligence_ai import (
    PAIRWISE_CARD_MATCH_SCHEMA_VERSION,
    AIPairwiseCardMatchResult,
    AIQuestionRoutingResult,
    FakeInterviewAIProvider,
    InterviewAIError,
)
from app.interviews.intelligence_models import (
    IntelligenceAnswer,
    IntelligenceAnswerReview,
    IntelligenceAssessment,
    IntelligenceDifficulty,
    IntelligenceInterview,
    IntelligenceInterviewType,
    IntelligenceQuestion,
    IntelligenceQuestionKind,
    IntelligenceQuestionModerationStatus,
    IntelligenceReviewSource,
    IntelligenceReviewStatus,
)
from app.interviews.intelligence_service import list_admin_question_moderation
from app.interviews.models import (
    Company,
    InterviewCard,
    InterviewCardFrequency,
    InterviewCardOccurrence,
    InterviewCardProgress,
    InterviewDeck,
    InterviewProcess,
    InterviewProcessStage,
    InterviewProcessStatus,
    InterviewStageType,
    InterviewTopicSelection,
)
from app.interviews.question_matching import normalize_question
from app.users.models import User
from tests.conftest import SeededData, TestSession, test_engine


@dataclass(frozen=True, slots=True)
class SourceFixture:
    process_id: UUID
    interview_id: UUID
    question_id: UUID
    answer_id: UUID
    company_name: str


@dataclass(frozen=True, slots=True)
class CardFixture:
    deck_id: UUID
    card_id: UUID


class ScopedRoutingProvider(FakeInterviewAIProvider):
    async def route_question(
        self,
        *,
        question: str,
        candidate_answer: str,
        context: str,
        available_broad_topics: list[str],
    ) -> AIQuestionRoutingResult:
        result = await super().route_question(
            question=question,
            candidate_answer=candidate_answer,
            context=context,
            available_broad_topics=available_broad_topics,
        )
        scope = (
            ["определение GIL"]
            if question.startswith("Что такое")
            else ["влияние GIL на CPU-bound потоки"]
        )
        return AIQuestionRoutingResult(
            output=result.output.model_copy(
                update={
                    "answer_scope": scope,
                    "topic_candidates": ["GIL"],
                }
            ),
            usage=result.usage,
        )


class ExistingTopicRoutingProvider(FakeInterviewAIProvider):
    async def route_question(
        self,
        *,
        question: str,
        candidate_answer: str,
        context: str,
        available_broad_topics: list[str],
    ) -> AIQuestionRoutingResult:
        result = await super().route_question(
            question=question,
            candidate_answer=candidate_answer,
            context=context,
            available_broad_topics=available_broad_topics,
        )
        assert available_broad_topics == ["Python core", "Python ООП"]
        return AIQuestionRoutingResult(
            output=result.output.model_copy(
                update={
                    "broad_topic": "Python ООП",
                    "detailed_subtopic": "Дескрипторы и протокол атрибутов",
                    "topic_candidates": ["дескрипторы", "__get__"],
                }
            ),
            usage=result.usage,
        )


class FinalizationRaceProvider(FakeInterviewAIProvider):
    def __init__(self, mutation: Callable[[], Awaitable[None]]) -> None:
        super().__init__()
        self.mutation = mutation

    async def judge_card_match(
        self,
        *,
        question: str,
        answer_scope: list[str],
        candidate_question: str,
        candidate_answer: str,
    ) -> AIPairwiseCardMatchResult:
        result = await super().judge_card_match(
            question=question,
            answer_scope=answer_scope,
            candidate_question=candidate_question,
            candidate_answer=candidate_answer,
        )
        await self.mutation()
        return AIPairwiseCardMatchResult(
            output=result.output.model_copy(
                update={
                    "decision": PairwiseCardMatchDecision.SAME_CARD,
                    "confidence": 0.99,
                }
            ),
            usage=result.usage,
        )


class AcceptedSemanticProvider(FakeInterviewAIProvider):
    async def judge_card_match(
        self,
        *,
        question: str,
        answer_scope: list[str],
        candidate_question: str,
        candidate_answer: str,
    ) -> AIPairwiseCardMatchResult:
        result = await super().judge_card_match(
            question=question,
            answer_scope=answer_scope,
            candidate_question=candidate_question,
            candidate_answer=candidate_answer,
        )
        return AIPairwiseCardMatchResult(
            output=result.output.model_copy(
                update={
                    "decision": PairwiseCardMatchDecision.SAME_CARD,
                    "confidence": 0.99,
                }
            ),
            usage=result.usage,
        )


class RoutingFinalizationRaceProvider(FakeInterviewAIProvider):
    def __init__(self, mutation: Callable[[], Awaitable[None]]) -> None:
        super().__init__()
        self.mutation = mutation

    async def route_question(
        self,
        *,
        question: str,
        candidate_answer: str,
        context: str,
        available_broad_topics: list[str],
    ) -> AIQuestionRoutingResult:
        result = await super().route_question(
            question=question,
            candidate_answer=candidate_answer,
            context=context,
            available_broad_topics=available_broad_topics,
        )
        await self.mutation()
        return result


class SequencedRoutingFailureProvider(FakeInterviewAIProvider):
    def __init__(self) -> None:
        super().__init__()
        self.failures = [
            InterviewAIError("ROUTING_TIMEOUT", "Routing timed out", retryable=True),
            InterviewAIError("ROUTING_INVALID", "Routing response was invalid", retryable=False),
        ]

    async def route_question(
        self,
        *,
        question: str,
        candidate_answer: str,
        context: str,
        available_broad_topics: list[str],
    ) -> AIQuestionRoutingResult:
        del available_broad_topics
        self.routing_calls.append(
            {
                "question": question,
                "candidate_answer": candidate_answer,
                "context": context,
            }
        )
        raise self.failures.pop(0)


async def _configure(
    seeded: SeededData,
    **overrides: object,
) -> None:
    settings = CardAutomationSettings(
        direction_id=seeded.python_track_id,
        enabled=True,
        shadow_mode=True,
        audit_sample_percent=0,
    )
    for name, value in overrides.items():
        setattr(settings, name, value)
    async with TestSession() as session:
        session.add(settings)
        await session.commit()


async def _create_source(
    seeded: SeededData,
    question_text: str,
    *,
    company_name: str | None = None,
    answer_text: str = "Содержательный ответ кандидата.",
    question_embedding: list[float] | None = None,
    confidence: float = 0.95,
    published_card_id: UUID | None = None,
    approved_alias: bool = False,
    assessment: IntelligenceAssessment | None = None,
) -> SourceFixture:
    unique = uuid4().hex
    selected_company_name = company_name or f"Company {unique[:8]}"
    company = Company(
        id=uuid4(),
        name=selected_company_name,
        normalized_name=f"company-{unique}",
        transliterated_name=f"company-{unique}",
    )
    process = InterviewProcess(
        id=uuid4(),
        user_id=seeded.student_id,
        track_id=seeded.python_track_id,
        company_id=company.id,
        company_name=company.name,
        status=InterviewProcessStatus.ACTIVE,
    )
    stage = InterviewProcessStage(
        id=uuid4(),
        process_id=process.id,
        stage_type=InterviewStageType.TECHNICAL_INTERVIEW,
        scheduled_at=datetime.now(UTC),
    )
    interview = IntelligenceInterview(
        id=uuid4(),
        stage_id=stage.id,
        student_id=seeded.student_id,
        interview_type=IntelligenceInterviewType.TECHNICAL,
    )
    question = IntelligenceQuestion(
        id=uuid4(),
        interview_id=interview.id,
        direction_id=seeded.python_track_id,
        sequence_number=0,
        question_text=question_text,
        normalized_question_text=question_text.casefold().rstrip("?"),
        question_embedding=question_embedding,
        question_embedding_model="test-embedding" if question_embedding else None,
        question_embedding_dimensions=len(question_embedding) if question_embedding else None,
        question_embedding_source_hash="b" * 64 if question_embedding else None,
        question_start_ms=0,
        question_end_ms=1_000,
        question_utterance_ids=[],
        answer_utterance_ids=[],
        category="Python",
        question_kind=IntelligenceQuestionKind.TECHNICAL,
        difficulty=IntelligenceDifficulty.MIDDLE,
        confidence=confidence,
        automation_status=QuestionOccurrenceStatus.CREATED,
        moderation_status=(
            IntelligenceQuestionModerationStatus.APPROVED
            if approved_alias
            else IntelligenceQuestionModerationStatus.PENDING
        ),
        published_card_id=published_card_id,
        alias_human_confirmed=approved_alias,
    )
    answer = IntelligenceAnswer(
        id=uuid4(),
        question_id=question.id,
        student_id=seeded.student_id,
        answer_text=answer_text,
        start_ms=1_001,
        end_ms=2_000,
    )
    async with TestSession() as session:
        session.add(company)
        await session.flush()
        session.add(process)
        await session.flush()
        session.add(stage)
        await session.flush()
        session.add(interview)
        await session.flush()
        session.add(question)
        await session.flush()
        session.add(answer)
        await session.flush()
        if assessment is not None:
            session.add(
                IntelligenceAnswerReview(
                    answer_id=answer.id,
                    source=IntelligenceReviewSource.AI,
                    status=IntelligenceReviewStatus.SUGGESTED,
                    assessment=assessment,
                    score=0.2,
                    summary="В ответе есть существенные пробелы.",
                    strengths=[],
                    problems=[
                        {
                            "problem": "Ключевой механизм не объяснён",
                            "explanation": "Ответ не раскрывает суть вопроса",
                        }
                    ],
                    missing_points=["Объяснить ключевой механизм"],
                    incorrect_statements=[],
                    suggested_better_answer="Краткий корректный ответ.",
                )
            )
        await session.commit()
    return SourceFixture(
        process_id=process.id,
        interview_id=interview.id,
        question_id=question.id,
        answer_id=answer.id,
        company_name=company.name,
    )


async def _add_question_to_interview(
    seeded: SeededData,
    interview_id: UUID,
    question_text: str,
    *,
    sequence_number: int,
) -> UUID:
    question = IntelligenceQuestion(
        id=uuid4(),
        interview_id=interview_id,
        direction_id=seeded.python_track_id,
        sequence_number=sequence_number,
        question_text=question_text,
        normalized_question_text=question_text.casefold().rstrip("?"),
        question_start_ms=sequence_number * 2_000,
        question_end_ms=sequence_number * 2_000 + 1_000,
        question_utterance_ids=[],
        answer_utterance_ids=[],
        category="Python",
        question_kind=IntelligenceQuestionKind.TECHNICAL,
        difficulty=IntelligenceDifficulty.MIDDLE,
        confidence=0.95,
        automation_status=QuestionOccurrenceStatus.CREATED,
    )
    async with TestSession() as session:
        session.add(question)
        await session.flush()
        session.add(
            IntelligenceAnswer(
                question_id=question.id,
                student_id=seeded.student_id,
                answer_text="Второй ответ в том же интервью.",
            )
        )
        await session.commit()
    return question.id


async def _create_card(
    seeded: SeededData,
    question: str,
    *,
    embedding: list[float] | None = None,
    category: str = "Python",
) -> CardFixture:
    unique = uuid4().hex
    deck = InterviewDeck(
        id=uuid4(),
        track_id=seeded.python_track_id,
        slug=f"pipeline-{unique}",
        title="Pipeline",
        position=0,
        is_published=True,
    )
    card = InterviewCard(
        id=uuid4(),
        deck_id=deck.id,
        slug=f"pipeline-card-{unique}",
        category=category,
        question_markdown=question,
        answer_markdown="Проверенный ответ карточки.",
        frequency=InterviewCardFrequency.OCCASIONAL,
        question_embedding=embedding,
        question_embedding_model="test-embedding" if embedding else None,
        question_embedding_dimensions=len(embedding) if embedding else None,
        question_embedding_source_hash="c" * 64 if embedding else None,
        position=0,
        is_published=True,
        asked_count=0,
    )
    async with TestSession() as session:
        session.add(deck)
        await session.flush()
        session.add(card)
        await session.commit()
    return CardFixture(deck.id, card.id)


async def _process(ai: FakeInterviewAIProvider, question_id: UUID) -> None:
    await process_question_occurrence(TestSession, ai, question_id, 1)


@pytest.mark.asyncio
async def test_exact_auto_link_is_idempotent_and_counts_one_occurrence_per_interview(
    seeded: SeededData,
) -> None:
    await _configure(
        seeded,
        shadow_mode=False,
        auto_link_exact_enabled=True,
    )
    card_fixture = await _create_card(seeded, "Что такое GIL?")
    source = await _create_source(seeded, "Что такое GIL?", company_name="Exact Co")
    second_question_id = await _add_question_to_interview(
        seeded,
        source.interview_id,
        "Что такое GIL?",
        sequence_number=1,
    )
    ai = FakeInterviewAIProvider()

    await _process(ai, source.question_id)
    await _process(ai, source.question_id)
    await _process(ai, second_question_id)
    await _process(ai, second_question_id)

    async with TestSession() as session:
        questions = list(
            await session.scalars(
                select(IntelligenceQuestion)
                .where(IntelligenceQuestion.id.in_([source.question_id, second_question_id]))
                .order_by(IntelligenceQuestion.sequence_number)
            )
        )
        card = await session.get(InterviewCard, card_fixture.card_id)
        occurrences = list(
            await session.scalars(
                select(InterviewCardOccurrence).where(
                    InterviewCardOccurrence.card_id == card_fixture.card_id
                )
            )
        )
        decisions = list(
            await session.scalars(
                select(AutomationDecision).where(
                    AutomationDecision.entity_id.in_([source.question_id, second_question_id])
                )
            )
        )
        assert card is not None
        assert len(questions) == 2
        assert all(
            item.automation_status is QuestionOccurrenceStatus.AUTO_LINKED for item in questions
        )
        assert all(item.published_card_id == card.id for item in questions)
        assert all(item.automation_attempts == 1 for item in questions)
        assert len(occurrences) == 1
        assert occurrences[0].interview_id == source.interview_id
        assert card.asked_count == 1
        assert card.companies == "Exact Co"
        exact_decisions = [
            item
            for item in decisions
            if item.decision_type is AutomationDecisionType.EXACT_CARD_MATCH
        ]
        assert len(exact_decisions) == 2
        assert all(
            item.decision_source is AutomationDecisionSource.EXACT for item in exact_decisions
        )
        assert all(item.retrieval_scores["applied"] is True for item in exact_decisions)
        assert len({item.idempotency_key for item in decisions}) == len(decisions) == 4


@pytest.mark.asyncio
async def test_only_human_confirmed_alias_can_auto_link(
    seeded: SeededData,
) -> None:
    await _configure(
        seeded,
        shadow_mode=False,
        auto_link_exact_enabled=False,
        auto_link_alias_enabled=True,
    )
    card_fixture = await _create_card(seeded, "Что блокирует параллелизм в CPython?")
    await _create_source(
        seeded,
        "Как работает GIL?",
        published_card_id=card_fixture.card_id,
        approved_alias=True,
    )
    source = await _create_source(seeded, "Как работает GIL?", company_name="Alias Co")

    await _process(FakeInterviewAIProvider(), source.question_id)

    async with TestSession() as session:
        question = await session.get(IntelligenceQuestion, source.question_id)
        decision = await session.scalar(
            select(AutomationDecision).where(
                AutomationDecision.entity_id == source.question_id,
                AutomationDecision.decision_type == AutomationDecisionType.ALIAS_CARD_MATCH,
            )
        )
        assert question is not None
        assert decision is not None
        assert question.automation_status is QuestionOccurrenceStatus.AUTO_LINKED
        assert question.published_card_id == card_fixture.card_id
        assert question.alias_human_confirmed is False
        assert decision.decision_source is AutomationDecisionSource.CONFIRMED_ALIAS


@pytest.mark.asyncio
async def test_exact_match_with_live_link_disabled_is_one_terminal_proposal(
    seeded: SeededData,
) -> None:
    await _configure(
        seeded,
        shadow_mode=False,
        auto_link_exact_enabled=False,
    )
    card_fixture = await _create_card(seeded, "Что такое GIL?")
    source = await _create_source(seeded, "Что такое GIL?")
    ai = FakeInterviewAIProvider()

    await _process(ai, source.question_id)
    await _process(ai, source.question_id)

    async with TestSession() as session:
        question = await session.get(IntelligenceQuestion, source.question_id)
        decisions = list(
            await session.scalars(
                select(AutomationDecision).where(
                    AutomationDecision.entity_id == source.question_id,
                    AutomationDecision.decision_type == AutomationDecisionType.EXACT_CARD_MATCH,
                )
            )
        )
        assert question is not None
        assert question.automation_status is QuestionOccurrenceStatus.ROUTED
        assert question.automation_attempts == 1
        assert question.published_card_id is None
        assert question.cluster_id is None
        assert len(decisions) == 1
        assert decisions[0].selected_card_id == card_fixture.card_id
        assert decisions[0].retrieval_scores["applied"] is False
        assert await session.scalar(select(func.count(QuestionCluster.id))) == 0
        assert await session.scalar(select(func.count(InterviewCardOccurrence.id))) == 0
    assert len(ai.routing_calls) == 1


@pytest.mark.asyncio
async def test_obvious_noise_is_ignored_without_ai_or_cluster(
    seeded: SeededData,
) -> None:
    await _configure(
        seeded,
        shadow_mode=False,
        auto_ignore_noise_enabled=True,
    )
    source = await _create_source(seeded, "Меня слышно?")
    ai = FakeInterviewAIProvider()

    await _process(ai, source.question_id)

    async with TestSession() as session:
        question = await session.get(IntelligenceQuestion, source.question_id)
        decisions = list(
            await session.scalars(
                select(AutomationDecision).where(AutomationDecision.entity_id == source.question_id)
            )
        )
        assert question is not None
        assert question.learning_object_type is LearningObjectType.NOISE
        assert question.automation_status is QuestionOccurrenceStatus.AUTO_IGNORED
        assert question.automation_decision_source is AutomationDecisionSource.RULE
        assert [item.decision_type for item in decisions] == [
            AutomationDecisionType.ROUTED_AS_NOISE
        ]
        assert await session.scalar(select(func.count(QuestionCluster.id))) == 0
        assert await session.scalar(select(func.count(InterviewCardOccurrence.id))) == 0
    assert ai.routing_calls == []


@pytest.mark.asyncio
async def test_semantic_related_different_scope_is_not_linked(
    seeded: SeededData,
) -> None:
    await _configure(
        seeded,
        shadow_mode=False,
        auto_link_semantic_enabled=True,
        semantic_similarity_threshold=0.8,
        pairwise_judge_confidence_threshold=0.8,
    )
    card_fixture = await _create_card(seeded, "Что такое GIL?", embedding=[1.0, 0.0])
    source = await _create_source(
        seeded,
        "Как GIL влияет на CPU-bound потоки?",
        question_embedding=[1.0, 0.0],
    )
    ai = FakeInterviewAIProvider()

    await _process(ai, source.question_id)

    async with TestSession() as session:
        question = await session.get(IntelligenceQuestion, source.question_id)
        card = await session.get(InterviewCard, card_fixture.card_id)
        semantic = await session.scalar(
            select(AutomationDecision).where(
                AutomationDecision.entity_id == source.question_id,
                AutomationDecision.decision_type == AutomationDecisionType.SEMANTIC_CARD_MATCH,
            )
        )
        assert question is not None
        assert card is not None
        assert semantic is not None
        assert semantic.judge_result is not None
        assert semantic.schema_version == PAIRWISE_CARD_MATCH_SCHEMA_VERSION
        assert semantic.latency_ms is not None
        assert semantic.latency_ms >= 0
        assert (
            semantic.judge_result["decision"] == PairwiseCardMatchDecision.RELATED_DIFFERENT_SCOPE
        )
        assert question.published_card_id is None
        assert question.automation_status is QuestionOccurrenceStatus.CLUSTERED
        assert question.cluster_id is not None
        assert card.asked_count == 0
        assert await session.scalar(select(func.count(InterviewCardOccurrence.id))) == 0
    assert len(ai.card_match_calls) == 1


@pytest.mark.asyncio
async def test_accepted_semantic_match_is_terminal_proposal_when_live_link_disabled(
    seeded: SeededData,
) -> None:
    await _configure(
        seeded,
        shadow_mode=False,
        auto_link_semantic_enabled=False,
        semantic_similarity_threshold=0.8,
        pairwise_judge_confidence_threshold=0.8,
    )
    card_fixture = await _create_card(seeded, "Что такое GIL?", embedding=[1.0, 0.0])
    source = await _create_source(
        seeded,
        "Рекрутер Мария Волкова попросила объяснить назначение GIL.",
        question_embedding=[1.0, 0.0],
    )
    ai = AcceptedSemanticProvider()

    await _process(ai, source.question_id)
    await _process(ai, source.question_id)

    async with TestSession() as session:
        question = await session.get(IntelligenceQuestion, source.question_id)
        decision = await session.scalar(
            select(AutomationDecision).where(
                AutomationDecision.entity_id == source.question_id,
                AutomationDecision.decision_type == AutomationDecisionType.SEMANTIC_CARD_MATCH,
            )
        )
        assert question is not None
        assert decision is not None
        assert question.automation_status is QuestionOccurrenceStatus.ROUTED
        assert question.automation_attempts == 1
        assert question.published_card_id is None
        assert question.cluster_id is None
        assert decision.selected_card_id == card_fixture.card_id
        assert decision.retrieval_scores["applied"] is False
        assert await session.scalar(select(func.count(QuestionCluster.id))) == 0
        assert await session.scalar(select(func.count(InterviewCardOccurrence.id))) == 0
    assert len(ai.routing_calls) == 1
    assert len(ai.card_match_calls) == 1
    pairwise_payload = str(ai.card_match_calls[0])
    assert "Мария" not in pairwise_payload
    assert "Волкова" not in pairwise_payload
    assert "[PERSON_NAME]" in pairwise_payload


@pytest.mark.asyncio
async def test_singleton_stays_in_one_shadow_cluster_on_retry(
    seeded: SeededData,
) -> None:
    await _configure(seeded)
    source = await _create_source(seeded, "Что такое дескриптор в Python?")
    ai = FakeInterviewAIProvider()

    await _process(ai, source.question_id)
    await _process(ai, source.question_id)

    async with TestSession() as session:
        question = await session.get(IntelligenceQuestion, source.question_id)
        clusters = list(await session.scalars(select(QuestionCluster)))
        decisions = list(
            await session.scalars(
                select(AutomationDecision).where(AutomationDecision.entity_id == source.question_id)
            )
        )
        assert question is not None
        assert question.automation_status is QuestionOccurrenceStatus.CLUSTERED
        assert question.automation_attempts == 1
        assert len(clusters) == 1
        assert clusters[0].status is QuestionClusterStatus.SHADOW
        assert clusters[0].occurrences_count == 1
        assert clusters[0].distinct_interviews_count == 1
        assert clusters[0].membership_revision == 1
        assert clusters[0].stats_revision == 1
        assert len(decisions) == 2
        assert len({item.idempotency_key for item in decisions}) == 2
    assert len(ai.routing_calls) == 1


@pytest.mark.asyncio
async def test_routing_uses_existing_broad_topic_and_persists_detailed_subtopic(
    seeded: SeededData,
) -> None:
    await _configure(seeded)
    await _create_card(seeded, "Что такое контекстный менеджер?", category="Python core")
    await _create_card(seeded, "Что такое наследование?", category="Python ООП")
    source = await _create_source(
        seeded,
        "Как работают дескрипторы в Python?",
        assessment=IntelligenceAssessment.INCORRECT,
    )
    ai = ExistingTopicRoutingProvider()

    await _process(ai, source.question_id)

    async with TestSession() as session:
        question = await session.get_one(IntelligenceQuestion, source.question_id)
        cluster = await session.get_one(QuestionCluster, question.cluster_id)

        assert question.category == "Python ООП"
        assert question.subcategory == "Дескрипторы и протокол атрибутов"
        assert question.topic_candidates == ["Python ООП", "дескрипторы", "__get__"]
        assert cluster.topic_name == "Python ООП"
        assert cluster.subtopic_name == "Дескрипторы и протокол атрибутов"
        assert cluster.answer_contract is not None
        assert cluster.answer_contract["short_answer"] == "Краткий корректный ответ."
        assert "требует проверки" in str(cluster.answer_contract["unsupported_claims"])


@pytest.mark.asyncio
async def test_independent_interviews_promote_exactly_one_cluster(
    seeded: SeededData,
) -> None:
    await _configure(
        seeded,
        min_distinct_interviews_for_promotion=3,
        min_distinct_companies_for_promotion=99,
        min_failed_answers_for_promotion=99,
    )
    sources = [
        await _create_source(
            seeded,
            "Что такое context manager в Python?",
            company_name=f"Independent {index}",
        )
        for index in range(3)
    ]
    ai = FakeInterviewAIProvider()

    for source in sources:
        await _process(ai, source.question_id)

    async with TestSession() as session:
        clusters = list(await session.scalars(select(QuestionCluster)))
        questions = list(
            await session.scalars(
                select(IntelligenceQuestion).where(
                    IntelligenceQuestion.id.in_([source.question_id for source in sources])
                )
            )
        )
        promotions = list(
            await session.scalars(
                select(AutomationDecision).where(
                    AutomationDecision.decision_type == AutomationDecisionType.CLUSTER_PROMOTED
                )
            )
        )
        assert len(clusters) == 1
        cluster = clusters[0]
        assert cluster.status is QuestionClusterStatus.NEEDS_REVIEW
        assert cluster.occurrences_count == 3
        assert cluster.distinct_interviews_count == 3
        assert cluster.distinct_companies_count == 3
        assert cluster.membership_revision == 3
        assert cluster.stats_revision == 3
        assert {question.cluster_id for question in questions} == {cluster.id}
        assert (
            sum(
                question.automation_status is QuestionOccurrenceStatus.NEEDS_REVIEW
                for question in questions
            )
            == 1
        )
        assert len(promotions) == 1
        assert promotions[0].selected_cluster_id == cluster.id


@pytest.mark.asyncio
async def test_weak_answer_creates_one_private_review_item(
    seeded: SeededData,
) -> None:
    await _configure(seeded, personal_review_enabled=True)
    source = await _create_source(
        seeded,
        "Что такое транзакция в PostgreSQL?",
        answer_text="Не знаю.",
        assessment=IntelligenceAssessment.INCORRECT,
    )
    ai = FakeInterviewAIProvider()

    await _process(ai, source.question_id)
    await _process(ai, source.question_id)

    async with TestSession() as session:
        items = list(
            await session.scalars(
                select(PersonalReviewItem).where(
                    PersonalReviewItem.source_occurrence_id == source.question_id
                )
            )
        )
        decisions = list(
            await session.scalars(
                select(AutomationDecision).where(
                    AutomationDecision.decision_type
                    == AutomationDecisionType.PERSONAL_REVIEW_CREATED
                )
            )
        )
        assert len(items) == 1
        item = items[0]
        assert item.student_id == seeded.student_id
        assert item.source_analysis_id == source.interview_id
        assert item.status is PersonalReviewStatus.ACTIVE
        assert item.answer_summary == "В ответе есть существенные пробелы."
        assert item.answer_contract is not None
        assert item.answer_contract["required_points"] == ["Объяснить ключевой механизм"]
        assert len(decisions) == 1


@pytest.mark.asyncio
async def test_disabled_feature_flag_leaves_occurrence_untouched(
    seeded: SeededData,
) -> None:
    await _configure(seeded, enabled=False, shadow_mode=False)
    source = await _create_source(seeded, "Что такое event loop?")
    ai = FakeInterviewAIProvider()

    await _process(ai, source.question_id)

    async with TestSession() as session:
        question = await session.get(IntelligenceQuestion, source.question_id)
        assert question is not None
        assert question.automation_status is QuestionOccurrenceStatus.CREATED
        assert question.automation_attempts == 0
        assert question.direction_id == seeded.python_track_id
        assert await session.scalar(select(func.count(AutomationDecision.id))) == 0
        assert await session.scalar(select(func.count(QuestionCluster.id))) == 0
        assert await session.scalar(select(func.count(InterviewCardOccurrence.id))) == 0
        assert await session.scalar(select(func.count(PersonalReviewItem.id))) == 0
        assert await session.scalar(select(func.count(InterviewTopicSelection.user_id))) == 0
        assert await session.scalar(select(func.count(InterviewCardProgress.user_id))) == 0
    assert ai.routing_calls == []


@pytest.mark.asyncio
async def test_legacy_queue_feature_flags_gate_automation_owned_occurrences(
    seeded: SeededData,
) -> None:
    sources = {
        status: await _create_source(seeded, f"Question for {status.value}?")
        for status in (
            QuestionOccurrenceStatus.CREATED,
            QuestionOccurrenceStatus.AUTO_LINKED,
            QuestionOccurrenceStatus.AUTO_IGNORED,
            QuestionOccurrenceStatus.CLUSTERED,
            QuestionOccurrenceStatus.NEEDS_REVIEW,
            QuestionOccurrenceStatus.PERSONAL_ONLY,
        )
    }
    async with TestSession() as session:
        for status, source in sources.items():
            question = await session.get(IntelligenceQuestion, source.question_id)
            assert question is not None
            question.automation_status = status
        await session.commit()

    async def visible_question_ids() -> set[UUID]:
        async with TestSession() as session:
            page = await list_admin_question_moderation(
                session,
                status="needs_review",
                track_id=seeded.python_track_id,
                query=None,
                limit=50,
                offset=0,
            )
        return {item.question_id for item in page.items}

    legacy_visible = {
        sources[status].question_id
        for status in (
            QuestionOccurrenceStatus.CREATED,
            QuestionOccurrenceStatus.CLUSTERED,
            QuestionOccurrenceStatus.NEEDS_REVIEW,
            QuestionOccurrenceStatus.PERSONAL_ONLY,
        )
    }
    assert await visible_question_ids() == legacy_visible

    await _configure(
        seeded,
        cluster_moderation_enabled=False,
        legacy_queue_enabled=True,
    )
    assert await visible_question_ids() == legacy_visible

    async with TestSession() as session:
        settings = await session.get(CardAutomationSettings, seeded.python_track_id)
        assert settings is not None
        settings.cluster_moderation_enabled = True
        await session.commit()
    assert await visible_question_ids() == {sources[QuestionOccurrenceStatus.CREATED].question_id}

    async with TestSession() as session:
        settings = await session.get(CardAutomationSettings, seeded.python_track_id)
        assert settings is not None
        settings.legacy_queue_enabled = False
        await session.commit()
    assert await visible_question_ids() == set()


@pytest.mark.asyncio
async def test_concurrent_paraphrases_create_one_semantic_cluster(
    seeded: SeededData,
) -> None:
    await _configure(seeded)
    sources = [
        await _create_source(
            seeded,
            question_text,
            company_name=f"Concurrent {index}",
            question_embedding=[1.0, 0.0],
        )
        for index, question_text in enumerate(
            (
                "Что такое asyncio Task в Python?",
                "Как в Python устроена задача asyncio?",
            )
        )
    ]
    ai = FakeInterviewAIProvider()

    await asyncio.gather(*(_process(ai, source.question_id) for source in sources))

    async with TestSession() as session:
        clusters = list(await session.scalars(select(QuestionCluster)))
        questions = list(
            await session.scalars(
                select(IntelligenceQuestion).where(
                    IntelligenceQuestion.id.in_([source.question_id for source in sources])
                )
            )
        )
        assert len(clusters) == 1
        assert clusters[0].occurrences_count == 2
        assert clusters[0].membership_revision == 2
        assert {question.cluster_id for question in questions} == {clusters[0].id}
        assert len({question.normalized_question_text for question in questions}) == 2


@pytest.mark.asyncio
async def test_related_questions_with_different_answer_scope_form_separate_clusters(
    seeded: SeededData,
) -> None:
    await _configure(
        seeded,
        cluster_match_threshold=0.8,
        candidate_score_gap_threshold=0.05,
    )
    definition = await _create_source(
        seeded,
        "Что такое GIL?",
        question_embedding=[1.0, 0.0],
    )
    impact = await _create_source(
        seeded,
        "Как GIL влияет на CPU-bound потоки?",
        question_embedding=[1.0, 0.0],
    )
    ai = ScopedRoutingProvider()

    await _process(ai, definition.question_id)
    await _process(ai, impact.question_id)

    async with TestSession() as session:
        clusters = list(await session.scalars(select(QuestionCluster)))
        definition_question = await session.get(
            IntelligenceQuestion,
            definition.question_id,
        )
        impact_question = await session.get(IntelligenceQuestion, impact.question_id)
        impact_decision = await session.scalar(
            select(AutomationDecision).where(
                AutomationDecision.entity_id == impact.question_id,
                AutomationDecision.decision_type == AutomationDecisionType.SHADOW_CLUSTER_CREATED,
            )
        )
        assert len(clusters) == 2
        assert definition_question is not None
        assert impact_question is not None
        assert impact_decision is not None
        assert definition_question.cluster_id != impact_question.cluster_id
        assert len(impact_decision.candidate_cluster_ids) == 1
        assert list(impact_decision.retrieval_scores.values()) == [1.0]
        assert "answer scopes are incompatible" in impact_decision.reason


@pytest.mark.parametrize(
    ("mutation_kind", "expected_reason"),
    [
        ("shadow", "Shadow/proposal only"),
        ("semantic_disabled", "Live auto-link disabled before finalization"),
        ("card_changed", "Candidate card changed before finalization"),
    ],
)
@pytest.mark.asyncio
async def test_semantic_finalization_rechecks_settings_and_card_snapshot(
    seeded: SeededData,
    mutation_kind: str,
    expected_reason: str,
) -> None:
    await _configure(
        seeded,
        shadow_mode=False,
        auto_link_semantic_enabled=True,
        semantic_similarity_threshold=0.8,
        pairwise_judge_confidence_threshold=0.8,
    )
    card_fixture = await _create_card(seeded, "Что такое GIL?", embedding=[1.0, 0.0])
    source = await _create_source(
        seeded,
        "Объясните назначение GIL.",
        question_embedding=[1.0, 0.0],
    )

    async def mutate_during_ai() -> None:
        async with TestSession() as session:
            if mutation_kind == "shadow":
                settings = await session.get(CardAutomationSettings, seeded.python_track_id)
                assert settings is not None
                settings.shadow_mode = True
            elif mutation_kind == "semantic_disabled":
                settings = await session.get(CardAutomationSettings, seeded.python_track_id)
                assert settings is not None
                settings.auto_link_semantic_enabled = False
            else:
                card = await session.get(InterviewCard, card_fixture.card_id)
                assert card is not None
                card.answer_markdown = "Ответ был изменён администратором."
            await session.commit()

    await _process(FinalizationRaceProvider(mutate_during_ai), source.question_id)

    async with TestSession() as session:
        question = await session.get(IntelligenceQuestion, source.question_id)
        card = await session.get(InterviewCard, card_fixture.card_id)
        assert question is not None
        assert card is not None
        assert question.automation_status is QuestionOccurrenceStatus.ROUTED
        assert question.published_card_id is None
        assert question.automation_decision_reason is not None
        assert question.automation_decision_reason.startswith(expected_reason)
        assert card.asked_count == 0
        assert await session.scalar(select(func.count(InterviewCardOccurrence.id))) == 0


@pytest.mark.asyncio
async def test_manual_cluster_link_invalidates_claimed_automation_snapshot(
    seeded: SeededData,
) -> None:
    await _configure(seeded, shadow_mode=False)
    card_fixture = await _create_card(seeded, "Что такое GIL?")
    source = await _create_source(seeded, "Как устроен GIL?")
    cluster = QuestionCluster(
        direction_id=seeded.python_track_id,
        status=QuestionClusterStatus.SHADOW,
        canonical_question="Как устроен GIL?",
        normalized_canonical_question=normalize_question("Как устроен GIL?"),
        learning_object_type=LearningObjectType.FLASHCARD,
        representative_occurrence_id=source.question_id,
        membership_revision=1,
        stats_revision=1,
    )
    async with TestSession() as session:
        session.add(cluster)
        await session.flush()
        question = await session.get(IntelligenceQuestion, source.question_id)
        assert question is not None
        question.cluster_id = cluster.id
        await session.commit()

    async def link_manually_during_routing() -> None:
        async with TestSession() as session:
            admin = await session.get_one(User, seeded.admin_id)
            stored_cluster = await session.get_one(QuestionCluster, cluster.id)
            card = await session.get_one(InterviewCard, card_fixture.card_id)
            settings = await session.get_one(CardAutomationSettings, seeded.python_track_id)
            await card_automation_service._apply_cluster_card_link(
                session,
                admin,
                stored_cluster,
                card,
                settings,
                reason="Manual decision won the race",
                confirm_alias=False,
            )
            await session.commit()

    await _process(
        RoutingFinalizationRaceProvider(link_manually_during_routing),
        source.question_id,
    )

    async with TestSession() as session:
        question = await session.get(IntelligenceQuestion, source.question_id)
        assert question is not None
        assert question.automation_revision == 2
        assert question.automation_status is QuestionOccurrenceStatus.AUTO_LINKED
        assert question.automation_decision_source is AutomationDecisionSource.HUMAN
        assert question.automation_decision_reason == "Manual decision won the race"
        assert question.published_card_id == card_fixture.card_id
        assert question.alias_human_confirmed is False
        assert (
            await session.scalar(
                select(func.count(AutomationDecision.id)).where(
                    AutomationDecision.entity_id == source.question_id,
                    AutomationDecision.decision_type == AutomationDecisionType.QUESTION_ROUTED,
                )
            )
            == 0
        )


@pytest.mark.asyncio
async def test_retryable_then_terminal_ai_failure_keeps_both_audit_decisions(
    seeded: SeededData,
) -> None:
    await _configure(seeded)
    source = await _create_source(seeded, "Что такое coroutine в Python?")
    ai = SequencedRoutingFailureProvider()

    with pytest.raises(InterviewAIError, match="Routing timed out"):
        await _process(ai, source.question_id)
    with pytest.raises(InterviewAIError, match="Routing response was invalid"):
        await _process(ai, source.question_id)

    async with TestSession() as session:
        question = await session.get(IntelligenceQuestion, source.question_id)
        decisions = list(
            await session.scalars(
                select(AutomationDecision)
                .where(
                    AutomationDecision.entity_id == source.question_id,
                    AutomationDecision.decision_type == AutomationDecisionType.OCCURRENCE_FAILED,
                )
                .order_by(AutomationDecision.created_at)
            )
        )
        assert question is not None
        assert question.automation_status is QuestionOccurrenceStatus.FAILED
        assert question.automation_error == ("ROUTING_INVALID: Routing response was invalid")
        assert question.automation_attempts == 2
        assert len(decisions) == 2
        assert [decision.judge_result["error_code"] for decision in decisions] == [
            "ROUTING_TIMEOUT",
            "ROUTING_INVALID",
        ]
        assert [decision.judge_result["terminal"] for decision in decisions] == [
            False,
            True,
        ]
        assert len({decision.idempotency_key for decision in decisions}) == 2


@pytest.mark.asyncio
async def test_routing_provider_receives_redacted_untrusted_text(
    seeded: SeededData,
) -> None:
    await _configure(seeded)
    async with TestSession() as session:
        student = await session.get(User, seeded.student_id)
        assert student is not None
        student.last_name = "Секретов"
        student.email = "profile@example.com"
        student.telegram_username = "student_private"
        student.telegram_id = 9876543210
        await session.commit()
    source = await _create_source(
        seeded,
        (
            "Иван Секретов и рекрутер Мария Волкова спрашивают: что такое GIL? "
            "Пишите на profile@example.com, secret@example.com или @private_user"
        ),
        answer_text=(
            "Интервьюер: Алексей Смирнов. Мой Telegram student_private и id 9876543210. "
            "Телефон +7 (999) 123-45-67, зарплата 350000 рублей."
        ),
    )
    ai = FakeInterviewAIProvider()

    await _process(ai, source.question_id)

    assert len(ai.routing_calls) == 1
    payload = ai.routing_calls[0]
    combined = " ".join(str(value) for value in payload.values())
    assert "secret@example.com" not in combined
    assert "profile@example.com" not in combined
    assert "Иван" not in combined
    assert "Секретов" not in combined
    assert "student_private" not in combined
    assert "9876543210" not in combined
    assert "Мария" not in combined
    assert "Волкова" not in combined
    assert "Алексей" not in combined
    assert "Смирнов" not in combined
    assert "@private_user" not in combined
    assert "999" not in combined
    assert "350000" not in combined
    assert "[EMAIL]" in combined
    assert "[TELEGRAM]" in combined
    assert "[LONG_NUMBER]" in combined
    assert "[FINANCIAL]" in combined
    assert "[PROFILE_IDENTIFIER]" in combined
    assert "[PERSON_NAME]" in combined
    assert redact_untrusted_text("https://t.me/private_user") == "[TELEGRAM]"
    assert redact_untrusted_text("Напишите @private_user.") == "Напишите [TELEGRAM]."
    assert redact_untrusted_text("Используйте @functools.wraps(original_function)") == (
        "Используйте @functools.wraps(original_function)"
    )
    assert redact_untrusted_text("Декоратор @pytest.mark.asyncio") == (
        "Декоратор @pytest.mark.asyncio"
    )
    assert redact_untrusted_text("Apache Kafka и Spring Boot") == ("Apache Kafka и Spring Boot")


@pytest.mark.asyncio
async def test_terminal_cluster_does_not_block_a_new_active_cluster_with_same_key(
    seeded: SeededData,
) -> None:
    await _configure(seeded)
    question_text = "Что такое Python descriptor?"
    terminal = QuestionCluster(
        direction_id=seeded.python_track_id,
        status=QuestionClusterStatus.LINKED,
        canonical_question=question_text,
        normalized_canonical_question=normalize_question(question_text),
        learning_object_type=LearningObjectType.FLASHCARD,
    )
    async with TestSession() as session:
        session.add(terminal)
        await session.commit()

    source = await _create_source(seeded, question_text)
    await _process(FakeInterviewAIProvider(), source.question_id)

    async with TestSession() as session:
        clusters = list(
            await session.scalars(
                select(QuestionCluster).order_by(QuestionCluster.created_at, QuestionCluster.id)
            )
        )
        question = await session.get(IntelligenceQuestion, source.question_id)
        assert question is not None
        assert len(clusters) == 2
        assert {cluster.status for cluster in clusters} == {
            QuestionClusterStatus.LINKED,
            QuestionClusterStatus.SHADOW,
        }
        active = next(
            cluster for cluster in clusters if cluster.status is QuestionClusterStatus.SHADOW
        )
        assert question.cluster_id == active.id
        assert question.automation_status is QuestionOccurrenceStatus.CLUSTERED


@pytest.mark.asyncio
async def test_new_occurrence_reopens_one_deferred_cluster_with_audit(
    seeded: SeededData,
) -> None:
    await _configure(seeded)
    question_text = "Что такое Python iterator?"
    deferred = QuestionCluster(
        direction_id=seeded.python_track_id,
        status=QuestionClusterStatus.DEFERRED,
        canonical_question=question_text,
        normalized_canonical_question=normalize_question(question_text),
        learning_object_type=LearningObjectType.FLASHCARD,
    )
    async with TestSession() as session:
        session.add(deferred)
        await session.commit()

    source = await _create_source(seeded, question_text)
    await _process(FakeInterviewAIProvider(), source.question_id)

    async with TestSession() as session:
        clusters = list(await session.scalars(select(QuestionCluster)))
        question = await session.get(IntelligenceQuestion, source.question_id)
        decisions = list(
            await session.scalars(
                select(AutomationDecision).where(
                    AutomationDecision.entity_id == deferred.id,
                    AutomationDecision.decision_type == AutomationDecisionType.CLUSTER_REOPENED,
                )
            )
        )
        assert question is not None
        assert len(clusters) == 1
        assert clusters[0].id == deferred.id
        assert clusters[0].status is QuestionClusterStatus.NEEDS_REVIEW
        assert clusters[0].membership_revision == 1
        assert clusters[0].stats_revision == 1
        assert question.cluster_id == deferred.id
        assert question.automation_status is QuestionOccurrenceStatus.NEEDS_REVIEW
        assert len(decisions) == 1


@pytest.mark.asyncio
async def test_cluster_stats_batches_latest_reviews_with_mentor_priority(
    seeded: SeededData,
) -> None:
    await _configure(
        seeded,
        min_distinct_interviews_for_promotion=99,
        min_distinct_companies_for_promotion=99,
        min_failed_answers_for_promotion=99,
    )
    mentor_correct = await _create_source(
        seeded,
        "Что такое protocol?",
        assessment=IntelligenceAssessment.INCORRECT,
    )
    mentor_incorrect = await _create_source(
        seeded,
        "Что такое structural typing?",
        assessment=IntelligenceAssessment.CORRECT,
    )
    cluster = QuestionCluster(
        direction_id=seeded.python_track_id,
        status=QuestionClusterStatus.SHADOW,
        canonical_question="Что такое typing protocol?",
        normalized_canonical_question=f"typing protocol {uuid4().hex}",
        learning_object_type=LearningObjectType.FLASHCARD,
        representative_occurrence_id=mentor_correct.question_id,
        membership_revision=2,
        stats_revision=0,
    )
    async with TestSession() as session:
        session.add(cluster)
        await session.flush()
        first = await session.get(IntelligenceQuestion, mentor_correct.question_id)
        second = await session.get(IntelligenceQuestion, mentor_incorrect.question_id)
        assert first is not None
        assert second is not None
        first.cluster_id = cluster.id
        second.cluster_id = cluster.id
        session.add_all(
            [
                IntelligenceAnswerReview(
                    answer_id=mentor_correct.answer_id,
                    source=IntelligenceReviewSource.MENTOR,
                    status=IntelligenceReviewStatus.APPROVED,
                    assessment=IntelligenceAssessment.CORRECT,
                    score=0.9,
                    strengths=[],
                    problems=[],
                    missing_points=[],
                    incorrect_statements=[],
                ),
                IntelligenceAnswerReview(
                    answer_id=mentor_incorrect.answer_id,
                    source=IntelligenceReviewSource.MENTOR,
                    status=IntelligenceReviewStatus.APPROVED,
                    assessment=IntelligenceAssessment.INCORRECT,
                    score=0.1,
                    strengths=[],
                    problems=[],
                    missing_points=[],
                    incorrect_statements=[],
                ),
            ]
        )
        await session.commit()

    review_queries: list[str] = []

    def capture_review_query(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        if "intelligence_answer_reviews" in statement:
            review_queries.append(statement)

    event.listen(test_engine.sync_engine, "before_cursor_execute", capture_review_query)
    try:
        async with TestSession() as session:
            stored_cluster = await session.get(QuestionCluster, cluster.id)
            assert stored_cluster is not None
            await recalculate_cluster_stats(session, stored_cluster)
            await session.commit()
    finally:
        event.remove(test_engine.sync_engine, "before_cursor_execute", capture_review_query)

    async with TestSession() as session:
        stored_cluster = await session.get(QuestionCluster, cluster.id)
        assert stored_cluster is not None
        assert stored_cluster.failed_answers_count == 1
    assert len(review_queries) == 1


@pytest.mark.asyncio
async def test_weak_answer_with_existing_card_schedules_one_audited_review(
    seeded: SeededData,
) -> None:
    await _configure(
        seeded,
        shadow_mode=False,
        auto_link_exact_enabled=True,
        personal_review_enabled=True,
    )
    card_fixture = await _create_card(seeded, "Что такое GIL?")
    source = await _create_source(
        seeded,
        "Что такое GIL?",
        answer_text="Не знаю.",
        assessment=IntelligenceAssessment.INCORRECT,
    )
    ai = FakeInterviewAIProvider()

    await _process(ai, source.question_id)
    await _process(ai, source.question_id)

    async with TestSession() as session:
        progress = await session.get(
            InterviewCardProgress,
            {"user_id": seeded.student_id, "card_id": card_fixture.card_id},
        )
        decisions = list(
            await session.scalars(
                select(AutomationDecision).where(
                    AutomationDecision.entity_id == source.question_id,
                    AutomationDecision.decision_type
                    == AutomationDecisionType.PERSONAL_REVIEW_CREATED,
                )
            )
        )
        assert progress is not None
        assert progress.repetitions == 0
        assert len(decisions) == 1
        assert decisions[0].selected_card_id == card_fixture.card_id
        assert decisions[0].reason == ("Existing canonical card scheduled for personal review")
