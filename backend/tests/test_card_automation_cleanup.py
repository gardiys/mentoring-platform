from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.interviews import card_frequency
from app.interviews.card_automation_models import (
    AutomationDecision,
    CardAutomationSettings,
    PersonalReviewItem,
    QuestionCluster,
)
from app.interviews.card_automation_types import (
    AutomationDecisionSource,
    AutomationDecisionType,
    LearningObjectType,
    PersonalReviewStatus,
    QuestionClusterStatus,
    QuestionOccurrenceStatus,
)
from app.interviews.intelligence_models import (
    IntelligenceAnswer,
    IntelligenceDifficulty,
    IntelligenceInterview,
    IntelligenceInterviewType,
    IntelligenceQuestion,
    IntelligenceQuestionKind,
)
from app.interviews.intelligence_service import delete_intelligence_interview
from app.interviews.journal_service import delete_admin_process
from app.interviews.models import (
    Company,
    InterviewCard,
    InterviewCardFrequency,
    InterviewCardOccurrence,
    InterviewDeck,
    InterviewProcess,
    InterviewProcessStage,
    InterviewProcessStatus,
    InterviewStageType,
)
from app.users.models import User
from tests.conftest import SeededData, TestSession


@dataclass(frozen=True, slots=True)
class CleanupScenario:
    target_process_id: UUID
    target_stage_id: UUID
    target_interview_id: UUID
    target_question_id: UUID
    survivor_interview_id: UUID | None
    survivor_question_id: UUID | None
    card_id: UUID
    cluster_id: UUID
    personal_review_id: UUID


async def _seed_cleanup_scenario(
    seeded: SeededData,
    *,
    with_survivor: bool,
    personal_status: PersonalReviewStatus = PersonalReviewStatus.ACTIVE,
) -> CleanupScenario:
    now = datetime.now(UTC)
    target_company = Company(
        id=uuid4(),
        name="Delete Co",
        normalized_name=f"deleteco-{uuid4().hex}",
        transliterated_name="deleteco",
    )
    survivor_company = Company(
        id=uuid4(),
        name="Keep Co",
        normalized_name=f"keepco-{uuid4().hex}",
        transliterated_name="keepco",
    )
    target_process = InterviewProcess(
        id=uuid4(),
        user_id=seeded.student_id,
        track_id=seeded.python_track_id,
        company_id=target_company.id,
        company_name=target_company.name,
        status=InterviewProcessStatus.ACTIVE,
    )
    target_stage = InterviewProcessStage(
        id=uuid4(),
        process_id=target_process.id,
        stage_type=InterviewStageType.TECHNICAL_INTERVIEW,
        scheduled_at=now,
    )
    target_interview = IntelligenceInterview(
        id=uuid4(),
        stage_id=target_stage.id,
        student_id=seeded.student_id,
        interview_type=IntelligenceInterviewType.TECHNICAL,
    )
    survivor_process = InterviewProcess(
        id=uuid4(),
        user_id=seeded.student_id,
        track_id=seeded.python_track_id,
        company_id=survivor_company.id,
        company_name=survivor_company.name,
        status=InterviewProcessStatus.ACTIVE,
    )
    survivor_stage = InterviewProcessStage(
        id=uuid4(),
        process_id=survivor_process.id,
        stage_type=InterviewStageType.TECHNICAL_INTERVIEW,
        scheduled_at=now,
    )
    survivor_interview = IntelligenceInterview(
        id=uuid4(),
        stage_id=survivor_stage.id,
        student_id=seeded.student_id,
        interview_type=IntelligenceInterviewType.TECHNICAL,
    )
    deck = InterviewDeck(
        id=uuid4(),
        track_id=seeded.python_track_id,
        slug=f"cleanup-{uuid4().hex}",
        title="Cleanup",
        position=0,
        is_published=True,
    )
    card = InterviewCard(
        id=uuid4(),
        deck_id=deck.id,
        slug=f"cleanup-card-{uuid4().hex}",
        category="Python",
        companies="Delete Co, Keep Co" if with_survivor else "Delete Co",
        question_markdown="Что такое GIL?",
        answer_markdown="Глобальная блокировка интерпретатора.",
        frequency=InterviewCardFrequency.FREQUENT,
        position=0,
        is_published=True,
        asked_count=2 if with_survivor else 1,
    )
    cluster = QuestionCluster(
        id=uuid4(),
        direction_id=seeded.python_track_id,
        status=QuestionClusterStatus.CANDIDATE,
        canonical_question="Что такое GIL?",
        normalized_canonical_question="что такое gil",
        learning_object_type=LearningObjectType.FLASHCARD,
        linked_card_id=card.id,
        occurrences_count=2 if with_survivor else 1,
        distinct_interviews_count=2 if with_survivor else 1,
        distinct_companies_count=2 if with_survivor else 1,
        distinct_students_count=1,
        failed_answers_count=0,
        priority_score=10.0,
        quality_score=0.95,
        cluster_confidence=0.95,
        embedding=[1.0, 0.0],
        embedding_model="test-embedding",
        embedding_dimensions=2,
        embedding_source_hash="a" * 64,
        membership_revision=2,
        stats_revision=2,
    )
    target_question = IntelligenceQuestion(
        id=uuid4(),
        interview_id=target_interview.id,
        direction_id=seeded.python_track_id,
        sequence_number=0,
        question_text="Что такое GIL?",
        normalized_question_text="что такое gil",
        question_start_ms=0,
        question_end_ms=1_000,
        question_utterance_ids=[],
        answer_utterance_ids=[],
        category="Python",
        question_kind=IntelligenceQuestionKind.TECHNICAL,
        difficulty=IntelligenceDifficulty.MIDDLE,
        confidence=0.99,
        learning_object_type=LearningObjectType.FLASHCARD,
        routing_confidence=0.99,
        automation_status=QuestionOccurrenceStatus.CLUSTERED,
        cluster_id=cluster.id,
        published_card_id=card.id,
        question_embedding=[1.0, 0.0],
        question_embedding_model="test-embedding",
        question_embedding_dimensions=2,
        question_embedding_source_hash="a" * 64,
    )
    survivor_question = IntelligenceQuestion(
        id=uuid4(),
        interview_id=survivor_interview.id,
        direction_id=seeded.python_track_id,
        sequence_number=0,
        question_text="Объясните назначение GIL.",
        normalized_question_text="объясните назначение gil",
        question_start_ms=0,
        question_end_ms=1_000,
        question_utterance_ids=[],
        answer_utterance_ids=[],
        category="Python",
        question_kind=IntelligenceQuestionKind.TECHNICAL,
        difficulty=IntelligenceDifficulty.MIDDLE,
        confidence=0.75,
        learning_object_type=LearningObjectType.FLASHCARD,
        routing_confidence=0.75,
        automation_status=QuestionOccurrenceStatus.CLUSTERED,
        cluster_id=cluster.id,
        published_card_id=card.id,
        question_embedding=[0.2, 0.8],
        question_embedding_model="test-embedding",
        question_embedding_dimensions=2,
        question_embedding_source_hash="b" * 64,
    )
    target_occurrence = InterviewCardOccurrence(
        card_id=card.id,
        source_question_id=target_question.id,
        interview_id=target_interview.id,
        process_id=target_process.id,
        company_id=target_company.id,
        company_name=target_company.name,
        asked_at=now,
    )
    survivor_occurrence = InterviewCardOccurrence(
        card_id=card.id,
        source_question_id=survivor_question.id,
        interview_id=survivor_interview.id,
        process_id=survivor_process.id,
        company_id=survivor_company.id,
        company_name=survivor_company.name,
        asked_at=now,
    )
    personal_review = PersonalReviewItem(
        id=uuid4(),
        student_id=seeded.student_id,
        direction_id=seeded.python_track_id,
        source_occurrence_id=target_question.id,
        source_analysis_id=target_interview.id,
        question_text=target_question.question_text,
        status=personal_status,
        version=1,
    )

    async with TestSession() as session:
        session.add_all([target_company, survivor_company])
        await session.flush()
        session.add(target_process)
        if with_survivor:
            session.add(survivor_process)
        await session.flush()
        session.add(target_stage)
        if with_survivor:
            session.add(survivor_stage)
        await session.flush()
        session.add(target_interview)
        if with_survivor:
            session.add(survivor_interview)
        await session.flush()
        session.add(deck)
        await session.flush()
        session.add(card)
        await session.flush()
        session.add_all([cluster, CardAutomationSettings(direction_id=seeded.python_track_id)])
        await session.flush()
        session.add(target_question)
        if with_survivor:
            session.add(survivor_question)
        await session.flush()
        session.add(
            IntelligenceAnswer(
                question_id=target_question.id,
                student_id=seeded.student_id,
                answer_text="Ответ по GIL.",
            )
        )
        if with_survivor:
            session.add(
                IntelligenceAnswer(
                    question_id=survivor_question.id,
                    student_id=seeded.student_id,
                    answer_text="Оставшийся ответ по GIL.",
                )
            )
        await session.flush()
        session.add_all([target_occurrence, personal_review])
        if with_survivor:
            session.add(survivor_occurrence)
        await session.commit()

    return CleanupScenario(
        target_process_id=target_process.id,
        target_stage_id=target_stage.id,
        target_interview_id=target_interview.id,
        target_question_id=target_question.id,
        survivor_interview_id=survivor_interview.id if with_survivor else None,
        survivor_question_id=survivor_question.id if with_survivor else None,
        card_id=card.id,
        cluster_id=cluster.id,
        personal_review_id=personal_review.id,
    )


@pytest.mark.asyncio
async def test_intelligence_delete_recalculates_automation_evidence(
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(card_frequency, "frequent_occurrence_threshold", lambda: 2)
    scenario = await _seed_cleanup_scenario(seeded, with_survivor=True)

    async with TestSession() as session:
        admin = await session.get(User, seeded.admin_id)
        assert admin is not None
        assert (
            await delete_intelligence_interview(session, admin, scenario.target_interview_id) == []
        )

    async with TestSession() as session:
        card = await session.get(InterviewCard, scenario.card_id)
        cluster = await session.get(QuestionCluster, scenario.cluster_id)
        personal = await session.get(PersonalReviewItem, scenario.personal_review_id)
        assert card is not None
        assert cluster is not None
        assert personal is not None
        assert await session.get(IntelligenceInterview, scenario.target_interview_id) is None
        assert await session.get(InterviewProcess, scenario.target_process_id) is not None
        assert scenario.survivor_interview_id is not None
        assert await session.get(IntelligenceInterview, scenario.survivor_interview_id) is not None
        assert (
            await session.scalar(
                select(func.count(InterviewCardOccurrence.id)).where(
                    InterviewCardOccurrence.card_id == card.id
                )
            )
            == 1
        )
        assert card.asked_count == 1
        assert card.companies == "Keep Co"
        assert card.frequency is InterviewCardFrequency.OCCASIONAL
        assert cluster.occurrences_count == 1
        assert cluster.distinct_interviews_count == 1
        assert cluster.distinct_companies_count == 1
        assert cluster.distinct_students_count == 1
        assert cluster.failed_answers_count == 0
        assert cluster.quality_score == pytest.approx(0.75)
        assert cluster.cluster_confidence == pytest.approx(0.75)
        assert cluster.representative_occurrence_id == scenario.survivor_question_id
        assert cluster.embedding == pytest.approx([0.2, 0.8])
        assert cluster.embedding_source_hash == "b" * 64
        assert cluster.membership_revision == 3
        assert cluster.stats_revision == 3
        assert personal.status is PersonalReviewStatus.ARCHIVED
        assert personal.version == 2
        assert personal.source_occurrence_id is None
        assert personal.source_analysis_id is None
        audit = await session.scalar(
            select(AutomationDecision).where(
                AutomationDecision.entity_type == "personal_review_item",
                AutomationDecision.entity_id == personal.id,
                AutomationDecision.decision_type
                == AutomationDecisionType.PERSONAL_REVIEW_ARCHIVED,
            )
        )
        assert audit is not None
        assert audit.decision_source is AutomationDecisionSource.RULE
        assert audit.retrieval_scores["previous_status"] == PersonalReviewStatus.ACTIVE.value


@pytest.mark.asyncio
async def test_process_delete_cleans_cascaded_interview_automation_evidence(
    seeded: SeededData,
) -> None:
    scenario = await _seed_cleanup_scenario(seeded, with_survivor=False)

    async with TestSession() as session:
        assert await delete_admin_process(session, scenario.target_process_id) == []

    async with TestSession() as session:
        card = await session.get(InterviewCard, scenario.card_id)
        cluster = await session.get(QuestionCluster, scenario.cluster_id)
        personal = await session.get(PersonalReviewItem, scenario.personal_review_id)
        assert card is not None
        assert cluster is not None
        assert personal is not None
        assert await session.get(InterviewProcess, scenario.target_process_id) is None
        assert await session.get(InterviewProcessStage, scenario.target_stage_id) is None
        assert await session.get(IntelligenceInterview, scenario.target_interview_id) is None
        assert await session.get(IntelligenceQuestion, scenario.target_question_id) is None
        assert (
            await session.scalar(
                select(func.count(InterviewCardOccurrence.id)).where(
                    InterviewCardOccurrence.card_id == card.id
                )
            )
            == 0
        )
        assert card.asked_count == 0
        assert card.companies is None
        assert card.frequency is InterviewCardFrequency.OCCASIONAL
        assert cluster.status is QuestionClusterStatus.IGNORED
        assert cluster.occurrences_count == 0
        assert cluster.distinct_interviews_count == 0
        assert cluster.distinct_companies_count == 0
        assert cluster.distinct_students_count == 0
        assert cluster.failed_answers_count == 0
        assert cluster.priority_score == 0
        assert cluster.quality_score == 0
        assert cluster.cluster_confidence == 0
        assert cluster.embedding is None
        assert cluster.embedding_model is None
        assert cluster.embedding_dimensions is None
        assert cluster.embedding_source_hash is None
        assert cluster.membership_revision == 3
        assert cluster.stats_revision == 3
        assert personal.status is PersonalReviewStatus.ARCHIVED
        assert personal.version == 2
        assert personal.source_occurrence_id is None
        assert personal.source_analysis_id is None
        cluster_audit = await session.scalar(
            select(AutomationDecision).where(
                AutomationDecision.entity_type == "cluster",
                AutomationDecision.entity_id == cluster.id,
                AutomationDecision.decision_type == AutomationDecisionType.CLUSTER_IGNORED,
            )
        )
        assert cluster_audit is not None
        assert cluster_audit.decision_source is AutomationDecisionSource.RULE


@pytest.mark.asyncio
async def test_source_deletion_archives_mastered_personal_review_and_audits_transition(
    seeded: SeededData,
) -> None:
    scenario = await _seed_cleanup_scenario(
        seeded,
        with_survivor=False,
        personal_status=PersonalReviewStatus.MASTERED,
    )

    async with TestSession() as session:
        admin = await session.get(User, seeded.admin_id)
        assert admin is not None
        await delete_intelligence_interview(session, admin, scenario.target_interview_id)

    async with TestSession() as session:
        personal = await session.get(PersonalReviewItem, scenario.personal_review_id)
        assert personal is not None
        assert personal.status is PersonalReviewStatus.ARCHIVED
        assert personal.version == 2
        assert personal.source_occurrence_id is None
        assert personal.source_analysis_id is None
        audit = await session.scalar(
            select(AutomationDecision).where(
                AutomationDecision.entity_type == "personal_review_item",
                AutomationDecision.entity_id == personal.id,
                AutomationDecision.decision_type
                == AutomationDecisionType.PERSONAL_REVIEW_ARCHIVED,
            )
        )
        assert audit is not None
        assert audit.retrieval_scores["previous_status"] == PersonalReviewStatus.MASTERED.value
