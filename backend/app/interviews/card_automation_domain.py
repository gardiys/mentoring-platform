from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.interviews.card_automation_types import (
    CARD_ELIGIBLE_TYPES,
    CRITICAL_QUALITY_FLAGS,
    LearningObjectType,
    PairwiseCardMatchDecision,
    QuestionClusterStatus,
    QuestionOccurrenceStatus,
)
from app.interviews.intelligence_models import IntelligenceAssessment, IntelligenceQuestionKind
from app.interviews.models import InterviewReviewRating


@dataclass(frozen=True, slots=True)
class RoutingFallback:
    learning_object_type: LearningObjectType
    is_real_interviewer_question: bool
    is_standalone: bool
    quality_flags: tuple[str, ...]
    confidence: float
    reason: str


@dataclass(frozen=True, slots=True)
class MatchGate:
    accepted: bool
    reason: str


@dataclass(frozen=True, slots=True)
class PromotionResult:
    promoted: bool
    reason: str | None


_NOISE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"^\s*(меня|нас|вам)\s+(слышно|видно)\s*[?!.]*\s*$",
        r"^\s*(есть|будут)\s+ли\s+у\s+вас\s+вопросы\s*[?!.]*\s*$",
        r"^\s*(алло|hello|привет|добрый\s+(день|вечер))\s*[?!.]*\s*$",
    )
)
_ABOUT_SELF = re.compile(r"^\s*расскажите?\s+(немного\s+)?о\s+себе", re.IGNORECASE)
_CODE_HINTS = re.compile(r"(этот|данный)\s+(код|фрагмент)|на\s+(экране|схеме|картинке)", re.I)


def fallback_route(
    text: str,
    question_kind: IntelligenceQuestionKind,
    extraction_confidence: float,
) -> RoutingFallback:
    normalized = text.strip()
    if not normalized or any(pattern.search(normalized) for pattern in _NOISE_PATTERNS):
        return RoutingFallback(
            LearningObjectType.NOISE,
            False,
            False,
            ("rhetorical",),
            0.99,
            "Deterministic small-talk/noise rule",
        )
    if extraction_confidence < 0.45:
        return RoutingFallback(
            LearningObjectType.CONTEXT_DEPENDENT,
            True,
            False,
            ("bad_transcription",),
            1.0 - extraction_confidence,
            "Extraction confidence is below the safe routing threshold",
        )
    if _ABOUT_SELF.search(normalized):
        return RoutingFallback(
            LearningObjectType.BEHAVIORAL_QUESTION,
            True,
            True,
            (),
            0.96,
            "Deterministic behavioral question rule",
        )
    if question_kind is IntelligenceQuestionKind.HR:
        return RoutingFallback(
            LearningObjectType.BEHAVIORAL_QUESTION,
            True,
            True,
            (),
            0.95,
            "Existing extraction classification is HR",
        )
    if question_kind is IntelligenceQuestionKind.ORGANIZATIONAL:
        return RoutingFallback(
            LearningObjectType.ORGANIZATIONAL_QUESTION,
            True,
            True,
            (),
            0.95,
            "Existing extraction classification is organizational",
        )
    if _CODE_HINTS.search(normalized):
        return RoutingFallback(
            LearningObjectType.CONTEXT_DEPENDENT,
            True,
            False,
            ("depends_on_code",),
            0.9,
            "Question explicitly depends on missing visual context",
        )
    if question_kind is IntelligenceQuestionKind.TECHNICAL:
        return RoutingFallback(
            LearningObjectType.OPEN_TECHNICAL_QUESTION,
            True,
            True,
            (),
            max(0.5, extraction_confidence),
            "Existing extraction classification is technical",
        )
    return RoutingFallback(
        LearningObjectType.CONTEXT_DEPENDENT,
        True,
        False,
        ("missing_context",),
        0.55,
        "Question type cannot be determined safely by rules",
    )


_TRANSITIONS: dict[QuestionOccurrenceStatus, frozenset[QuestionOccurrenceStatus]] = {
    QuestionOccurrenceStatus.CREATED: frozenset(
        {QuestionOccurrenceStatus.ROUTING, QuestionOccurrenceStatus.FAILED}
    ),
    QuestionOccurrenceStatus.ROUTING: frozenset(
        {
            QuestionOccurrenceStatus.ROUTED,
            QuestionOccurrenceStatus.SEARCHING_CARD,
            QuestionOccurrenceStatus.AUTO_IGNORED,
            QuestionOccurrenceStatus.FAILED,
        }
    ),
    QuestionOccurrenceStatus.ROUTED: frozenset(
        {
            QuestionOccurrenceStatus.SEARCHING_CARD,
            QuestionOccurrenceStatus.PERSONAL_ONLY,
            QuestionOccurrenceStatus.FAILED,
        }
    ),
    QuestionOccurrenceStatus.SEARCHING_CARD: frozenset(
        {
            QuestionOccurrenceStatus.AUTO_LINKED,
            QuestionOccurrenceStatus.ROUTING,
            QuestionOccurrenceStatus.SEARCHING_CLUSTER,
            QuestionOccurrenceStatus.ROUTED,
            QuestionOccurrenceStatus.FAILED,
        }
    ),
    QuestionOccurrenceStatus.SEARCHING_CLUSTER: frozenset(
        {
            QuestionOccurrenceStatus.CLUSTERED,
            QuestionOccurrenceStatus.ROUTING,
            QuestionOccurrenceStatus.NEEDS_REVIEW,
            QuestionOccurrenceStatus.FAILED,
        }
    ),
    QuestionOccurrenceStatus.CLUSTERED: frozenset(
        {QuestionOccurrenceStatus.NEEDS_REVIEW, QuestionOccurrenceStatus.AUTO_LINKED}
    ),
    QuestionOccurrenceStatus.NEEDS_REVIEW: frozenset(
        {
            QuestionOccurrenceStatus.CLUSTERED,
            QuestionOccurrenceStatus.AUTO_LINKED,
            QuestionOccurrenceStatus.AUTO_IGNORED,
        }
    ),
    QuestionOccurrenceStatus.PERSONAL_ONLY: frozenset({QuestionOccurrenceStatus.AUTO_LINKED}),
    QuestionOccurrenceStatus.AUTO_IGNORED: frozenset(),
    QuestionOccurrenceStatus.AUTO_LINKED: frozenset(),
    QuestionOccurrenceStatus.FAILED: frozenset({QuestionOccurrenceStatus.ROUTING}),
}


def ensure_occurrence_transition(
    current: QuestionOccurrenceStatus,
    target: QuestionOccurrenceStatus,
    *,
    manual_reopen: bool = False,
) -> None:
    if current == target:
        return
    if manual_reopen and target in {
        QuestionOccurrenceStatus.CREATED,
        QuestionOccurrenceStatus.ROUTING,
    }:
        return
    if target not in _TRANSITIONS[current]:
        raise ValueError(f"Invalid occurrence transition: {current.value} -> {target.value}")


def match_gate(
    *,
    learning_object_type: LearningObjectType,
    quality_flags: Collection[str],
    semantic_score: float,
    second_score: float | None,
    semantic_threshold: float,
    judge_decision: PairwiseCardMatchDecision,
    judge_confidence: float,
    judge_threshold: float,
    score_gap_threshold: float,
    direction_matches: bool,
) -> MatchGate:
    if learning_object_type not in CARD_ELIGIBLE_TYPES:
        return MatchGate(False, "Learning object type is not eligible for a canonical card")
    critical = CRITICAL_QUALITY_FLAGS.intersection(quality_flags)
    if critical:
        return MatchGate(False, f"Critical quality flags: {', '.join(sorted(critical))}")
    if not direction_matches:
        return MatchGate(False, "Direction does not match")
    if semantic_score < semantic_threshold:
        return MatchGate(False, "Semantic score is below threshold")
    if second_score is not None and semantic_score - second_score < score_gap_threshold:
        return MatchGate(False, "Top candidates are ambiguous")
    if judge_decision is not PairwiseCardMatchDecision.SAME_CARD:
        return MatchGate(False, f"Pairwise judge returned {judge_decision.value}")
    if judge_confidence < judge_threshold:
        return MatchGate(False, "Pairwise judge confidence is below threshold")
    return MatchGate(True, "All conservative semantic auto-link checks passed")


def promotion_result(
    *,
    distinct_interviews: int,
    distinct_companies: int,
    failed_answers: int,
    min_interviews: int,
    min_companies: int,
    min_failures: int,
    manual_important: bool,
    coverage_gap: bool = False,
) -> PromotionResult:
    if manual_important:
        return PromotionResult(True, "manually_marked_important")
    if coverage_gap:
        return PromotionResult(True, "critical_topic_coverage_gap")
    if distinct_interviews >= min_interviews:
        return PromotionResult(True, "distinct_interviews_threshold")
    if distinct_companies >= min_companies:
        return PromotionResult(True, "distinct_companies_threshold")
    if failed_answers >= min_failures:
        return PromotionResult(True, "failed_answers_threshold")
    return PromotionResult(False, None)


def priority_score(
    *,
    occurrences: int,
    distinct_interviews: int,
    distinct_companies: int,
    failed_answers: int,
    last_seen_at: datetime,
    novelty: float,
    topic_importance: float,
    cluster_confidence: float,
    now: datetime | None = None,
) -> float:
    reference = now or datetime.now(UTC)
    if last_seen_at.tzinfo is None:
        last_seen_at = last_seen_at.replace(tzinfo=UTC)
    age_days = max((reference - last_seen_at).total_seconds() / 86_400, 0.0)
    recency = math.exp(-age_days / 30)
    value = (
        2.4 * math.log1p(max(distinct_interviews, 0))
        + 1.7 * math.log1p(max(distinct_companies, 0))
        + 1.9 * max(failed_answers, 0)
        + 0.4 * math.log1p(max(occurrences, 0))
        + 1.2 * recency
        + 1.0 * min(max(novelty, 0), 1)
        + 0.8 * min(max(topic_importance, 0), 1)
        + 0.8 * min(max(cluster_confidence, 0), 1)
    )
    return round(max(value, 0.0), 6)


def is_failed_answer(assessment: IntelligenceAssessment | None, answer_text: str | None) -> bool:
    if not (answer_text or "").strip():
        return True
    return assessment in {
        IntelligenceAssessment.PARTIAL,
        IntelligenceAssessment.MOSTLY_INCORRECT,
        IntelligenceAssessment.INCORRECT,
    }


def next_personal_review(
    rating: InterviewReviewRating,
    successful_reviews: int,
    *,
    now: datetime | None = None,
) -> tuple[datetime, int, bool]:
    reference = now or datetime.now(UTC)
    if rating is InterviewReviewRating.AGAIN:
        return reference + timedelta(minutes=10), 0, False
    success = successful_reviews + 1
    if rating is InterviewReviewRating.HARD:
        interval = max(1, success)
    elif rating is InterviewReviewRating.GOOD:
        interval = (1, 3, 7, 14, 30)[min(success - 1, 4)]
    elif rating is InterviewReviewRating.KNOWN:
        interval = 30
    else:
        interval = (3, 7, 14, 30, 60)[min(success - 1, 4)]
    return reference + timedelta(days=interval), success, success >= 4


def audit_sample(decision_id: UUID, percent: float) -> bool:
    bounded = min(max(percent, 0.0), 100.0)
    if bounded <= 0:
        return False
    if bounded >= 100:
        return True
    digest = hashlib.blake2b(decision_id.bytes, digest_size=8).digest()
    bucket = int.from_bytes(digest, "big") % 1_000_000
    return bucket < round(bounded * 10_000)


def cluster_allowed_actions(status: QuestionClusterStatus) -> tuple[str, ...]:
    if status in {QuestionClusterStatus.MERGED, QuestionClusterStatus.SPLIT}:
        return ("reopen",)
    if status is QuestionClusterStatus.IGNORED:
        return ("reopen",)
    if status is QuestionClusterStatus.DEFERRED:
        return ("reopen", "mark_important")
    if status in {QuestionClusterStatus.LINKED, QuestionClusterStatus.CARD_CREATED}:
        return ("reopen", "split", "merge")
    return (
        "update_draft",
        "link_card",
        "create_card",
        "split",
        "merge",
        "ignore",
        "defer",
        "mark_important",
    )
