from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.interviews.card_automation_domain import (
    audit_sample,
    ensure_occurrence_transition,
    fallback_route,
    match_gate,
    priority_score,
    promotion_result,
)
from app.interviews.card_automation_types import (
    LearningObjectType,
    PairwiseCardMatchDecision,
    QuestionOccurrenceStatus,
)
from app.interviews.intelligence_models import IntelligenceQuestionKind


def test_fallback_routing_filters_noise_and_non_flashcards() -> None:
    noise = fallback_route("Меня слышно?", IntelligenceQuestionKind.OTHER, 0.98)
    assert noise.learning_object_type is LearningObjectType.NOISE
    assert not noise.is_real_interviewer_question

    hr = fallback_route("Почему ушли с работы?", IntelligenceQuestionKind.HR, 0.95)
    assert hr.learning_object_type is LearningObjectType.BEHAVIORAL_QUESTION
    assert hr.is_standalone


def test_semantic_gate_requires_every_conservative_signal() -> None:
    accepted = match_gate(
        learning_object_type=LearningObjectType.OPEN_TECHNICAL_QUESTION,
        quality_flags=(),
        semantic_score=0.96,
        second_score=0.80,
        semantic_threshold=0.90,
        judge_decision=PairwiseCardMatchDecision.SAME_CARD,
        judge_confidence=0.97,
        judge_threshold=0.92,
        score_gap_threshold=0.08,
        direction_matches=True,
    )
    assert accepted.accepted

    ambiguous = match_gate(
        learning_object_type=LearningObjectType.OPEN_TECHNICAL_QUESTION,
        quality_flags=(),
        semantic_score=0.96,
        second_score=0.91,
        semantic_threshold=0.90,
        judge_decision=PairwiseCardMatchDecision.SAME_CARD,
        judge_confidence=0.97,
        judge_threshold=0.92,
        score_gap_threshold=0.08,
        direction_matches=True,
    )
    assert not ambiguous.accepted
    assert "ambiguous" in ambiguous.reason

    context_dependent = match_gate(
        learning_object_type=LearningObjectType.OPEN_TECHNICAL_QUESTION,
        quality_flags=("depends_on_code",),
        semantic_score=0.99,
        second_score=None,
        semantic_threshold=0.90,
        judge_decision=PairwiseCardMatchDecision.SAME_CARD,
        judge_confidence=0.99,
        judge_threshold=0.92,
        score_gap_threshold=0.08,
        direction_matches=True,
    )
    assert not context_dependent.accepted


def test_promotion_counts_independent_sources() -> None:
    assert not promotion_result(
        distinct_interviews=2,
        distinct_companies=1,
        failed_answers=1,
        min_interviews=3,
        min_companies=2,
        min_failures=2,
        manual_important=False,
    ).promoted
    result = promotion_result(
        distinct_interviews=3,
        distinct_companies=1,
        failed_answers=1,
        min_interviews=3,
        min_companies=2,
        min_failures=2,
        manual_important=False,
    )
    assert result.promoted
    assert result.reason == "distinct_interviews_threshold"


def test_priority_score_is_deterministic_and_monotonic_for_failures() -> None:
    now = datetime(2026, 8, 16, tzinfo=UTC)
    base = priority_score(
        occurrences=3,
        distinct_interviews=3,
        distinct_companies=2,
        failed_answers=0,
        last_seen_at=now,
        novelty=1,
        topic_importance=0,
        cluster_confidence=0.9,
        now=now,
    )
    repeated = priority_score(
        occurrences=3,
        distinct_interviews=3,
        distinct_companies=2,
        failed_answers=0,
        last_seen_at=now,
        novelty=1,
        topic_importance=0,
        cluster_confidence=0.9,
        now=now,
    )
    with_failures = priority_score(
        occurrences=3,
        distinct_interviews=3,
        distinct_companies=2,
        failed_answers=2,
        last_seen_at=now,
        novelty=1,
        topic_importance=0,
        cluster_confidence=0.9,
        now=now,
    )
    assert base == repeated
    assert with_failures > base


def test_state_machine_blocks_impossible_transition_without_reopen() -> None:
    with pytest.raises(ValueError):
        ensure_occurrence_transition(
            QuestionOccurrenceStatus.AUTO_IGNORED,
            QuestionOccurrenceStatus.AUTO_LINKED,
        )
    ensure_occurrence_transition(
        QuestionOccurrenceStatus.AUTO_IGNORED,
        QuestionOccurrenceStatus.ROUTING,
        manual_reopen=True,
    )


@pytest.mark.parametrize(
    "terminal_status",
    [
        QuestionOccurrenceStatus.ROUTED,
        QuestionOccurrenceStatus.CLUSTERED,
        QuestionOccurrenceStatus.NEEDS_REVIEW,
        QuestionOccurrenceStatus.PERSONAL_ONLY,
    ],
)
def test_terminal_occurrence_requires_new_revision_to_route_again(
    terminal_status: QuestionOccurrenceStatus,
) -> None:
    with pytest.raises(ValueError):
        ensure_occurrence_transition(
            terminal_status,
            QuestionOccurrenceStatus.ROUTING,
        )
    ensure_occurrence_transition(
        terminal_status,
        QuestionOccurrenceStatus.CREATED,
        manual_reopen=True,
    )


def test_audit_sampling_is_reproducible() -> None:
    decision_id = UUID("00000000-0000-0000-0000-000000000123")
    assert audit_sample(decision_id, 5) == audit_sample(decision_id, 5)
    assert not audit_sample(decision_id, 0)
    assert audit_sample(decision_id, 100)
