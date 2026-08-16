from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.interviews.card_automation_models import (
    AutomationDecision,
    CardAutomationSettings,
    QuestionCluster,
)
from app.interviews.card_automation_types import (
    AutomationDecisionSource,
    AutomationDecisionType,
    LearningObjectType,
    QuestionClusterStatus,
    QuestionOccurrenceStatus,
)
from app.interviews.intelligence_models import (
    IntelligenceQuestion,
    IntelligenceQuestionKind,
    IntelligenceQuestionModerationStatus,
)
from app.scripts import backfill_card_automation, reprocess_missing_card_topics
from app.scripts.backfill_card_automation import BackfillOptions
from app.scripts.evaluate_card_automation import (
    GroundTruthKind,
    HistoricalAlias,
    HistoricalCard,
    HistoricalDataset,
    HistoricalDecision,
    HistoricalQuestion,
    PredictionKind,
    evaluate_dataset,
    predict_historical_outcome,
)
from app.scripts.reprocess_missing_card_topics import (
    ClusterCandidate,
    ReprocessMissingTopicsOptions,
)
from tests.conftest import SeededData, TestSession
from tests.test_card_automation_pipeline import _create_card, _create_source


@pytest.mark.parametrize(
    "module_name",
    (
        "app.scripts.backfill_card_automation",
        "app.scripts.evaluate_card_automation",
        "app.scripts.reprocess_missing_card_topics",
    ),
)
def test_standalone_script_registers_all_foreign_key_metadata(module_name: str) -> None:
    """CLI imports must resolve every FK without pytest's global model imports."""

    backend_dir = Path(__file__).resolve().parents[1]
    code = (
        f"import {module_name}; "
        "from app.db.base import Base; "
        "assert 'users' in Base.metadata.tables; "
        "[foreign_key.column for table in Base.metadata.tables.values() "
        "for foreign_key in table.foreign_keys]"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=backend_dir,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def _historical_question(
    *,
    question_id: UUID,
    text: str,
    labeled_at: datetime,
    ground_truth: GroundTruthKind,
    correct_card_id: UUID | None,
) -> HistoricalQuestion:
    return HistoricalQuestion(
        id=question_id,
        direction="python",
        question_text=text,
        normalized_question_text=text.casefold().rstrip("?"),
        category="Python",
        question_kind=IntelligenceQuestionKind.TECHNICAL,
        extraction_confidence=0.95,
        embedding=None,
        created_at=labeled_at - timedelta(days=1),
        labeled_at=labeled_at,
        ground_truth=ground_truth,
        correct_card_id=correct_card_id,
    )


def test_temporal_evaluation_uses_historical_evidence_without_label_leakage() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    existing_direct_id = UUID(int=101)
    existing_alias_id = UUID(int=102)
    wrong_id = UUID(int=103)
    future_alias_target_id = UUID(int=104)
    direct_question_id = UUID(int=201)
    alias_question_id = UUID(int=202)
    new_question_id = UUID(int=203)
    noise_question_id = UUID(int=204)
    semantic_error_id = UUID(int=205)
    future_alias_question_id = UUID(int=206)

    questions = (
        _historical_question(
            question_id=direct_question_id,
            text="Что такое GIL?",
            labeled_at=base + timedelta(days=5),
            ground_truth=GroundTruthKind.EXISTING_CARD,
            correct_card_id=existing_direct_id,
        ),
        _historical_question(
            question_id=alias_question_id,
            text="Как устроена глобальная блокировка интерпретатора?",
            labeled_at=base + timedelta(days=6),
            ground_truth=GroundTruthKind.EXISTING_CARD,
            correct_card_id=existing_alias_id,
        ),
        _historical_question(
            question_id=new_question_id,
            text="Совершенно новый вопрос?",
            labeled_at=base + timedelta(days=7),
            ground_truth=GroundTruthKind.NEW_CARD,
            correct_card_id=new_question_id,
        ),
        _historical_question(
            question_id=noise_question_id,
            text="Меня слышно?",
            labeled_at=base + timedelta(days=8),
            ground_truth=GroundTruthKind.REJECTED,
            correct_card_id=None,
        ),
        _historical_question(
            question_id=semantic_error_id,
            text="Чем отличается список от кортежа?",
            labeled_at=base + timedelta(days=9),
            ground_truth=GroundTruthKind.EXISTING_CARD,
            correct_card_id=existing_direct_id,
        ),
        _historical_question(
            question_id=future_alias_question_id,
            text="Будущий alias",
            labeled_at=base + timedelta(days=10),
            ground_truth=GroundTruthKind.EXISTING_CARD,
            correct_card_id=future_alias_target_id,
        ),
    )
    cards = (
        HistoricalCard(
            id=existing_direct_id,
            direction="python",
            slug="gil",
            question_text="Что такое GIL?",
            asked_count=10,
            embedding=None,
            created_at=base,
            available_for_matching=True,
        ),
        HistoricalCard(
            id=existing_alias_id,
            direction="python",
            slug="interpreter-lock",
            question_text="Что блокирует интерпретатор?",
            asked_count=5,
            embedding=None,
            created_at=base,
            available_for_matching=True,
        ),
        HistoricalCard(
            id=wrong_id,
            direction="python",
            slug="wrong",
            question_text="Ошибочная карточка",
            asked_count=1,
            embedding=None,
            created_at=base,
            available_for_matching=True,
        ),
        HistoricalCard(
            id=future_alias_target_id,
            direction="python",
            slug="future-alias-target",
            question_text="Канонический будущий alias",
            asked_count=1,
            embedding=None,
            created_at=base,
            available_for_matching=True,
        ),
        HistoricalCard(
            id=new_question_id,
            direction="python",
            slug=f"ai-{new_question_id.hex}",
            question_text="Совершенно новый вопрос?",
            asked_count=1,
            embedding=None,
            created_at=base + timedelta(days=7),
            available_for_matching=True,
        ),
    )
    aliases = (
        HistoricalAlias(
            question_id=UUID(int=301),
            card_id=existing_alias_id,
            direction="python",
            question_text="Как устроена глобальная блокировка интерпретатора?",
            embedding=None,
            confirmed_at=base + timedelta(days=2),
        ),
        HistoricalAlias(
            question_id=UUID(int=302),
            card_id=future_alias_target_id,
            direction="python",
            question_text="Будущий alias",
            embedding=None,
            confirmed_at=base + timedelta(days=11),
        ),
        # Even a human-confirmed row cannot reveal the answer to its own
        # historical example.
        HistoricalAlias(
            question_id=new_question_id,
            card_id=new_question_id,
            direction="python",
            question_text="Совершенно новый вопрос?",
            embedding=None,
            confirmed_at=base + timedelta(days=7),
        ),
    )
    decisions = (
        HistoricalDecision(
            id=UUID(int=401),
            question_id=semantic_error_id,
            decision_type=AutomationDecisionType.QUESTION_ROUTED,
            decision_source=AutomationDecisionSource.AI_ROUTING,
            selected_card_id=None,
            selected_cluster_id=None,
            retrieval_scores={},
            judge_result={"topic_candidates": ["Concurrency"]},
            confidence=0.98,
            reason="Saved routing",
            created_at=base + timedelta(days=8),
        ),
        HistoricalDecision(
            id=UUID(int=402),
            question_id=semantic_error_id,
            decision_type=AutomationDecisionType.SEMANTIC_CARD_MATCH,
            decision_source=AutomationDecisionSource.SEMANTIC_JUDGE,
            selected_card_id=wrong_id,
            selected_cluster_id=None,
            retrieval_scores={str(wrong_id): 0.96},
            judge_result={"decision": "same_card"},
            confidence=0.97,
            reason="All conservative semantic auto-link checks passed",
            created_at=base + timedelta(days=8, hours=1),
        ),
        # It was created after the human label and must not improve the score.
        HistoricalDecision(
            id=UUID(int=403),
            question_id=future_alias_question_id,
            decision_type=AutomationDecisionType.EXACT_CARD_MATCH,
            decision_source=AutomationDecisionSource.EXACT,
            selected_card_id=future_alias_target_id,
            selected_cluster_id=None,
            retrieval_scores={str(future_alias_target_id): 1.0},
            judge_result=None,
            confidence=1.0,
            reason="Future decision",
            created_at=base + timedelta(days=11),
        ),
    )

    dataset = HistoricalDataset(
        questions=questions,
        cards=cards,
        aliases=aliases,
        decisions=decisions,
        loaded_human_examples=6,
        excluded_examples=0,
    )
    report = evaluate_dataset(dataset)

    assert report["examples"] == 6
    assert report["ground_truth_existing_card"] == 4
    assert report["ground_truth_new_card"] == 1
    assert report["ground_truth_rejected"] == 1
    assert report["predicted_links"] == 3
    assert report["auto_link_coverage"] == 0.75
    assert report["auto_link_precision"] == 0.666667
    assert report["auto_link_recall"] == 0.5
    assert report["false_merge_rate"] == 0.333333
    assert report["false_split_rate"] == 0.5
    assert report["noise_precision"] == 1.0
    assert report["noise_recall"] == 1.0
    assert report["saved_semantic_predictions_evaluated"] == 1
    assert report["topic_match_rate"] == 0.0
    assert report["estimated_manual_tasks_after"] == 2
    assert report["estimated_queue_reduction"] == 0.666667
    assert any(item["error_type"] == "false_merge" for item in report["errors"])
    assert any(item["error_type"] == "false_split" for item in report["errors"])

    self_prediction = predict_historical_outcome(questions[2], cards, aliases, prior_decisions=())
    future_prediction = predict_historical_outcome(questions[5], cards, aliases, prior_decisions=())
    assert self_prediction.kind is PredictionKind.ABSTAIN
    assert future_prediction.kind is PredictionKind.ABSTAIN

    failed_gate_prediction = predict_historical_outcome(
        questions[4],
        cards,
        aliases,
        prior_decisions=(
            HistoricalDecision(
                id=UUID(int=404),
                question_id=semantic_error_id,
                decision_type=AutomationDecisionType.SEMANTIC_CARD_MATCH,
                decision_source=AutomationDecisionSource.SEMANTIC_JUDGE,
                selected_card_id=wrong_id,
                selected_cluster_id=None,
                retrieval_scores={str(wrong_id): 0.96},
                judge_result={"decision": "related_different_scope"},
                confidence=0.99,
                reason="Pairwise judge returned related_different_scope",
                created_at=base + timedelta(days=8),
            ),
        ),
    )
    assert failed_gate_prediction.kind is PredictionKind.ABSTAIN
    assert failed_gate_prediction.selected_card_id == wrong_id


async def _cluster_source_with_topic(
    seeded: SeededData,
    topic_name: str | None,
    *,
    subtopic_name: str | None,
    moderation_status: IntelligenceQuestionModerationStatus = (
        IntelligenceQuestionModerationStatus.PENDING
    ),
) -> tuple[UUID, UUID]:
    unique = uuid4().hex
    source = await _create_source(seeded, f"Topic reprocess {topic_name or 'empty'}?")
    cluster = QuestionCluster(
        direction_id=seeded.python_track_id,
        status=QuestionClusterStatus.NEEDS_REVIEW,
        canonical_question=f"Cluster {topic_name or 'empty'} {unique}",
        normalized_canonical_question=f"cluster {topic_name or 'empty'} {unique}".casefold(),
        learning_object_type=LearningObjectType.OPEN_TECHNICAL_QUESTION,
        topic_name=topic_name,
        subtopic_name=subtopic_name,
        membership_revision=1,
        stats_revision=1,
    )
    async with TestSession() as session:
        session.add(cluster)
        await session.flush()
        question = await session.get_one(IntelligenceQuestion, source.question_id)
        question.cluster_id = cluster.id
        question.automation_status = QuestionOccurrenceStatus.NEEDS_REVIEW
        question.moderation_status = moderation_status
        await session.commit()
    return cluster.id, source.question_id


@pytest.mark.asyncio
async def test_missing_topic_reprocess_is_dry_run_safe_and_skips_human_work(
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _create_card(seeded, "Existing Python core topic?", category="Python core")
    invalid_cluster_id, invalid_question_id = await _cluster_source_with_topic(
        seeded,
        "Invented legacy topic",
        subtopic_name="Legacy detail",
    )
    empty_cluster_id, empty_question_id = await _cluster_source_with_topic(
        seeded,
        None,
        subtopic_name=None,
    )
    subtopic_cluster_id, subtopic_question_id = await _cluster_source_with_topic(
        seeded,
        "Python core",
        subtopic_name=None,
    )
    await _cluster_source_with_topic(
        seeded,
        "Python core",
        subtopic_name="Descriptors",
    )
    _approved_cluster_id, approved_question_id = await _cluster_source_with_topic(
        seeded,
        "Another invented topic",
        subtopic_name=None,
        moderation_status=IntelligenceQuestionModerationStatus.APPROVED,
    )
    async with TestSession() as session:
        session.add(
            CardAutomationSettings(
                direction_id=seeded.python_track_id,
                enabled=True,
                shadow_mode=True,
                cluster_moderation_enabled=True,
                legacy_queue_enabled=True,
            )
        )
        await session.commit()

    enqueued: list[tuple[str, str, int]] = []

    async def record_enqueue(function: str, question_id: str, revision: int) -> str:
        enqueued.append((function, question_id, revision))
        return f"job:{question_id}:v{revision}"

    monkeypatch.setattr(
        reprocess_missing_card_topics,
        "async_session_factory",
        TestSession,
    )
    monkeypatch.setattr(
        reprocess_missing_card_topics,
        "enqueue_card_automation_job",
        record_enqueue,
    )

    dry_result = await reprocess_missing_card_topics.run(
        ReprocessMissingTopicsOptions(
            direction="python",
            batch_size=10,
            execute=False,
            include_missing_subtopics=False,
            max_ai_requests=None,
        )
    )
    assert dry_result == {
        "examined_clusters": 2,
        "examined_occurrences": 2,
        "prepared_clusters": 2,
        "prepared_occurrences": 2,
        "enqueued": 0,
        "budget_blocked_clusters": 0,
        "reserved_ai_requests": 32,
    }
    assert enqueued == []

    live_result = await reprocess_missing_card_topics.run(
        ReprocessMissingTopicsOptions(
            direction="python",
            batch_size=2,
            execute=True,
            include_missing_subtopics=True,
            max_ai_requests=48,
        )
    )
    assert live_result == {
        "examined_clusters": 3,
        "examined_occurrences": 3,
        "prepared_clusters": 3,
        "prepared_occurrences": 3,
        "enqueued": 3,
        "budget_blocked_clusters": 0,
        "reserved_ai_requests": 48,
    }
    assert {UUID(question_id) for _function, question_id, _revision in enqueued} == {
        invalid_question_id,
        empty_question_id,
        subtopic_question_id,
    }
    assert all(function == "reprocess_question_occurrence" for function, *_rest in enqueued)

    async with TestSession() as session:
        decisions = list(
            await session.scalars(
                select(AutomationDecision).where(
                    AutomationDecision.entity_id.in_(
                        [invalid_question_id, empty_question_id, subtopic_question_id]
                    ),
                    AutomationDecision.decision_type
                    == AutomationDecisionType.OCCURRENCE_REPROCESSED,
                )
            )
        )
        approved = await session.get_one(IntelligenceQuestion, approved_question_id)
        assert len(decisions) == 3
        assert {decision.selected_cluster_id for decision in decisions} == {
            invalid_cluster_id,
            empty_cluster_id,
            subtopic_cluster_id,
        }
        assert approved.moderation_status is IntelligenceQuestionModerationStatus.APPROVED


@pytest.mark.asyncio
async def test_missing_topic_execute_requires_shadow_mode(
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _cluster_source_with_topic(seeded, None, subtopic_name=None)
    async with TestSession() as session:
        session.add(
            CardAutomationSettings(
                direction_id=seeded.python_track_id,
                enabled=True,
                shadow_mode=False,
                cluster_moderation_enabled=True,
                legacy_queue_enabled=True,
            )
        )
        await session.commit()
    monkeypatch.setattr(
        reprocess_missing_card_topics,
        "async_session_factory",
        TestSession,
    )

    with pytest.raises(RuntimeError, match="shadow_mode=true"):
        await reprocess_missing_card_topics.run(
            ReprocessMissingTopicsOptions(
                direction="python",
                batch_size=10,
                execute=True,
                include_missing_subtopics=False,
                max_ai_requests=16,
            )
        )


def test_missing_topic_budget_never_splits_a_cluster() -> None:
    large = ClusterCandidate(cluster_id=UUID(int=1), occurrence_count=3)
    small = ClusterCandidate(cluster_id=UUID(int=2), occurrence_count=1)

    selected, blocked = reprocess_missing_card_topics._select_complete_clusters(
        [large, small],
        max_occurrences=1,
    )

    assert selected == [small]
    assert blocked == 1


@pytest.mark.asyncio
async def test_backfill_is_dry_run_safe_bounded_and_skips_all_human_decisions(
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pending_one = await _create_source(seeded, "Pending one?")
    pending_two = await _create_source(seeded, "Pending two?")
    approved = await _create_source(seeded, "Approved must stay untouched?")
    rejected = await _create_source(seeded, "Rejected must stay untouched?")
    mentor_approved = await _create_source(seeded, "Mentor decision must stay untouched?")
    async with TestSession() as session:
        (
            await session.get(IntelligenceQuestion, approved.question_id)
        ).moderation_status = IntelligenceQuestionModerationStatus.APPROVED
        (
            await session.get(IntelligenceQuestion, rejected.question_id)
        ).moderation_status = IntelligenceQuestionModerationStatus.REJECTED
        (
            await session.get(IntelligenceQuestion, mentor_approved.question_id)
        ).moderation_status = IntelligenceQuestionModerationStatus.MENTOR_APPROVED
        await session.commit()

    enqueued: list[tuple[str, str, int]] = []

    async def record_enqueue(function: str, question_id: str, revision: int) -> None:
        enqueued.append((function, question_id, revision))

    monkeypatch.setattr(backfill_card_automation, "async_session_factory", TestSession)
    monkeypatch.setattr(
        backfill_card_automation,
        "enqueue_card_automation_job",
        record_enqueue,
    )
    options = BackfillOptions(
        direction="python",
        batch_size=100,
        dry_run=True,
        unreviewed_only=True,
        max_ai_requests=backfill_card_automation.AI_REQUEST_RESERVATION_PER_OCCURRENCE,
    )
    dry_result = await backfill_card_automation.run(options)
    assert dry_result == {
        "examined": 1,
        "prepared": 1,
        "enqueued": 0,
        "reserved_ai_requests": 8,
    }
    assert enqueued == []

    live_result = await backfill_card_automation.run(
        BackfillOptions(
            direction="python",
            batch_size=100,
            dry_run=False,
            unreviewed_only=False,
            max_ai_requests=8,
        )
    )
    assert live_result == {
        "examined": 1,
        "prepared": 1,
        "enqueued": 1,
        "reserved_ai_requests": 8,
    }
    assert len(enqueued) == 1
    assert enqueued[0][0] == "route_question_occurrence"
    assert UUID(enqueued[0][1]) in {pending_one.question_id, pending_two.question_id}

    async with TestSession() as session:
        assert (
            await session.get(IntelligenceQuestion, approved.question_id)
        ).moderation_status is IntelligenceQuestionModerationStatus.APPROVED
        assert (
            await session.get(IntelligenceQuestion, rejected.question_id)
        ).moderation_status is IntelligenceQuestionModerationStatus.REJECTED
        assert (
            await session.get(IntelligenceQuestion, mentor_approved.question_id)
        ).moderation_status is IntelligenceQuestionModerationStatus.MENTOR_APPROVED


@pytest.mark.asyncio
async def test_budgeted_backfill_rejects_answer_generation_mode(
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with TestSession() as session:
        session.add(
            CardAutomationSettings(
                direction_id=seeded.python_track_id,
                enabled=True,
                shadow_mode=True,
                cluster_moderation_enabled=True,
                legacy_queue_enabled=True,
            )
        )
        await session.commit()
    monkeypatch.setattr(backfill_card_automation, "async_session_factory", TestSession)

    with pytest.raises(RuntimeError, match="cluster_moderation_enabled=false"):
        await backfill_card_automation.run(
            BackfillOptions(
                direction="python",
                batch_size=10,
                dry_run=False,
                unreviewed_only=True,
                max_ai_requests=8,
            )
        )
