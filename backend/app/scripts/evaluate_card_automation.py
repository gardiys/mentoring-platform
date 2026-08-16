from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.db import models as _db_models  # noqa: F401
from app.db.session import async_session_factory
from app.interviews.card_automation_domain import fallback_route
from app.interviews.card_automation_models import AutomationDecision, QuestionCluster
from app.interviews.card_automation_types import (
    CARD_ELIGIBLE_TYPES,
    AutomationDecisionSource,
    AutomationDecisionType,
    LearningObjectType,
)
from app.interviews.intelligence_models import (
    IntelligenceInterview,
    IntelligenceQuestion,
    IntelligenceQuestionKind,
    IntelligenceQuestionModerationStatus,
)
from app.interviews.models import (
    InterviewCard,
    InterviewDeck,
    InterviewProcess,
    InterviewProcessStage,
)
from app.interviews.question_matching import (
    QuestionCandidate,
    QuestionVariant,
    normalize_question,
    rank_question_candidates,
)
from app.tracks.models import LearningTrack


class GroundTruthKind(StrEnum):
    EXISTING_CARD = "existing_card"
    NEW_CARD = "new_card"
    REJECTED = "rejected"


class PredictionKind(StrEnum):
    LINK = "link"
    NOISE = "noise"
    NON_FLASHCARD = "non_flashcard"
    ABSTAIN = "abstain"


@dataclass(frozen=True, slots=True)
class HistoricalQuestion:
    id: UUID
    direction: str
    question_text: str
    normalized_question_text: str
    category: str
    question_kind: IntelligenceQuestionKind
    extraction_confidence: float
    embedding: tuple[float, ...] | None
    created_at: datetime
    labeled_at: datetime
    ground_truth: GroundTruthKind
    correct_card_id: UUID | None


@dataclass(frozen=True, slots=True)
class HistoricalCard:
    id: UUID
    direction: str
    slug: str
    question_text: str
    asked_count: int
    embedding: tuple[float, ...] | None
    created_at: datetime
    available_for_matching: bool


@dataclass(frozen=True, slots=True)
class HistoricalAlias:
    question_id: UUID
    card_id: UUID
    direction: str
    question_text: str
    embedding: tuple[float, ...] | None
    confirmed_at: datetime


@dataclass(frozen=True, slots=True)
class HistoricalDecision:
    id: UUID
    question_id: UUID
    decision_type: AutomationDecisionType
    decision_source: AutomationDecisionSource
    selected_card_id: UUID | None
    selected_cluster_id: UUID | None
    retrieval_scores: dict[str, object]
    judge_result: dict[str, object] | None
    confidence: float | None
    reason: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class HistoricalClusterSplit:
    cluster_id: UUID
    moved_occurrence_ids: tuple[UUID, ...]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class HistoricalDataset:
    questions: tuple[HistoricalQuestion, ...]
    cards: tuple[HistoricalCard, ...]
    aliases: tuple[HistoricalAlias, ...]
    decisions: tuple[HistoricalDecision, ...]
    loaded_human_examples: int
    excluded_examples: int
    human_cluster_splits: tuple[HistoricalClusterSplit, ...] = ()


@dataclass(frozen=True, slots=True)
class Prediction:
    kind: PredictionKind
    source: str
    selected_card_id: UUID | None = None
    selected_cluster_id: UUID | None = None
    similarity: float | None = None
    judge_decision: str | None = None
    confidence: float | None = None
    reason: str = ""


MATCH_DECISIONS = frozenset(
    {
        AutomationDecisionType.EXACT_CARD_MATCH,
        AutomationDecisionType.ALIAS_CARD_MATCH,
        AutomationDecisionType.SEMANTIC_CARD_MATCH,
    }
)
FILTER_DECISIONS = frozenset(
    {
        AutomationDecisionType.ROUTED_AS_NOISE,
        AutomationDecisionType.ROUTED_AS_NON_FLASHCARD,
    }
)
CLUSTER_DECISIONS = frozenset(
    {
        AutomationDecisionType.CLUSTER_MATCH,
        AutomationDecisionType.SHADOW_CLUSTER_CREATED,
    }
)
DECISIVE_TYPES = MATCH_DECISIONS | FILTER_DECISIONS


async def evaluate(
    *,
    from_date: date | None,
    to_date: date | None,
    direction: str | None,
    error_limit: int = 50,
) -> dict[str, Any]:
    """Evaluate saved/rule predictions against historical human labels.

    This function intentionally performs SELECT statements only. It never runs
    a model, creates an embedding, changes an occurrence, or writes a decision.
    """

    dataset = await load_historical_dataset(
        from_date=from_date,
        to_date=to_date,
        direction=direction,
    )
    return evaluate_dataset(dataset, error_limit=error_limit)


async def load_historical_dataset(
    *,
    from_date: date | None,
    to_date: date | None,
    direction: str | None,
) -> HistoricalDataset:
    async with async_session_factory() as session:
        statement = (
            select(IntelligenceQuestion, LearningTrack.slug)
            .join(
                IntelligenceInterview,
                IntelligenceInterview.id == IntelligenceQuestion.interview_id,
            )
            .join(
                InterviewProcessStage,
                InterviewProcessStage.id == IntelligenceInterview.stage_id,
            )
            .join(InterviewProcess, InterviewProcess.id == InterviewProcessStage.process_id)
            .join(LearningTrack, LearningTrack.id == InterviewProcess.track_id)
            .where(
                IntelligenceQuestion.moderation_status.in_(
                    {
                        IntelligenceQuestionModerationStatus.APPROVED,
                        IntelligenceQuestionModerationStatus.REJECTED,
                    }
                )
            )
            .order_by(IntelligenceQuestion.created_at, IntelligenceQuestion.id)
        )
        if from_date is not None:
            statement = statement.where(
                IntelligenceQuestion.created_at >= datetime.combine(from_date, time.min, tzinfo=UTC)
            )
        if to_date is not None:
            statement = statement.where(
                IntelligenceQuestion.created_at
                < datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=UTC)
            )
        if direction is not None:
            statement = statement.where(LearningTrack.slug == direction)
        question_rows = (await session.execute(statement)).all()

        card_statement = (
            select(InterviewCard, InterviewDeck, LearningTrack.slug)
            .join(InterviewDeck, InterviewDeck.id == InterviewCard.deck_id)
            .join(LearningTrack, LearningTrack.id == InterviewDeck.track_id)
        )
        if direction is not None:
            card_statement = card_statement.where(LearningTrack.slug == direction)
        card_rows = (await session.execute(card_statement)).all()
        cards = tuple(
            HistoricalCard(
                id=card.id,
                direction=slug,
                slug=card.slug,
                question_text=card.question_markdown,
                asked_count=card.asked_count,
                embedding=tuple(card.question_embedding) if card.question_embedding else None,
                created_at=_aware(card.created_at),
                available_for_matching=card.is_published and deck.is_published,
            )
            for card, deck, slug in card_rows
        )
        cards_by_id = {card.id: card for card in cards}

        loaded_human_examples = len(question_rows)
        excluded_examples = 0
        questions: list[HistoricalQuestion] = []
        for question, slug in question_rows:
            labeled_at = _aware(
                question.admin_reviewed_at
                or question.mentor_reviewed_at
                or question.updated_at
                or question.created_at
            )
            correct_card_id = question.published_card_id
            if question.moderation_status is IntelligenceQuestionModerationStatus.REJECTED:
                ground_truth = GroundTruthKind.REJECTED
                correct_card_id = None
            elif correct_card_id is None or correct_card_id not in cards_by_id:
                # An approved row without its canonical card cannot provide a
                # reliable link/new-card label (for example after legacy data
                # cleanup with an old SET NULL foreign key).
                excluded_examples += 1
                continue
            elif cards_by_id[correct_card_id].slug == f"ai-{question.id.hex}":
                ground_truth = GroundTruthKind.NEW_CARD
            else:
                ground_truth = GroundTruthKind.EXISTING_CARD
            questions.append(
                HistoricalQuestion(
                    id=question.id,
                    direction=slug,
                    question_text=question.question_text,
                    normalized_question_text=normalize_question(question.question_text),
                    category=question.category,
                    question_kind=question.question_kind,
                    extraction_confidence=question.confidence,
                    embedding=(
                        tuple(question.question_embedding) if question.question_embedding else None
                    ),
                    created_at=_aware(question.created_at),
                    labeled_at=labeled_at,
                    ground_truth=ground_truth,
                    correct_card_id=correct_card_id,
                )
            )

        alias_statement = (
            select(IntelligenceQuestion, LearningTrack.slug)
            .join(LearningTrack, LearningTrack.id == IntelligenceQuestion.direction_id)
            .where(
                IntelligenceQuestion.moderation_status
                == IntelligenceQuestionModerationStatus.APPROVED,
                IntelligenceQuestion.alias_human_confirmed.is_(True),
                IntelligenceQuestion.published_card_id.is_not(None),
            )
        )
        if direction is not None:
            alias_statement = alias_statement.where(LearningTrack.slug == direction)
        alias_rows = (await session.execute(alias_statement)).all()
        aliases = tuple(
            HistoricalAlias(
                question_id=alias.id,
                card_id=alias.published_card_id,
                direction=slug,
                question_text=alias.question_text,
                embedding=tuple(alias.question_embedding) if alias.question_embedding else None,
                confirmed_at=_aware(
                    alias.admin_reviewed_at
                    or alias.mentor_reviewed_at
                    or alias.updated_at
                    or alias.created_at
                ),
            )
            for alias, slug in alias_rows
            if alias.published_card_id is not None
        )

        question_ids = [question.id for question in questions]
        decision_rows: list[AutomationDecision] = []
        # Keep the expanding IN parameter bounded for large historical sets.
        for chunk_start in range(0, len(question_ids), 1_000):
            chunk = question_ids[chunk_start : chunk_start + 1_000]
            decision_rows.extend(
                await session.scalars(
                    select(AutomationDecision)
                    .where(
                        AutomationDecision.entity_type == "occurrence",
                        AutomationDecision.entity_id.in_(chunk),
                        AutomationDecision.decision_source != AutomationDecisionSource.HUMAN,
                    )
                    .order_by(AutomationDecision.created_at, AutomationDecision.id)
                )
            )
        decisions = tuple(
            HistoricalDecision(
                id=item.id,
                question_id=item.entity_id,
                decision_type=item.decision_type,
                decision_source=item.decision_source,
                selected_card_id=item.selected_card_id,
                selected_cluster_id=item.selected_cluster_id,
                retrieval_scores=dict(item.retrieval_scores),
                judge_result=(dict(item.judge_result) if item.judge_result else None),
                confidence=item.confidence,
                reason=item.reason,
                created_at=_aware(item.created_at),
            )
            for item in decision_rows
        )

        split_statement = (
            select(AutomationDecision)
            .join(QuestionCluster, QuestionCluster.id == AutomationDecision.entity_id)
            .join(LearningTrack, LearningTrack.id == QuestionCluster.direction_id)
            .where(
                AutomationDecision.entity_type == "cluster",
                AutomationDecision.decision_type == AutomationDecisionType.CLUSTER_SPLIT,
                AutomationDecision.decision_source == AutomationDecisionSource.HUMAN,
            )
            .order_by(AutomationDecision.created_at, AutomationDecision.id)
        )
        if from_date is not None:
            split_statement = split_statement.where(
                AutomationDecision.created_at >= datetime.combine(from_date, time.min, tzinfo=UTC)
            )
        if to_date is not None:
            split_statement = split_statement.where(
                AutomationDecision.created_at
                < datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=UTC)
            )
        if direction is not None:
            split_statement = split_statement.where(LearningTrack.slug == direction)
        split_rows = list(await session.scalars(split_statement))
        human_cluster_splits = tuple(
            HistoricalClusterSplit(
                cluster_id=item.entity_id,
                moved_occurrence_ids=_uuid_tuple(item.retrieval_scores.get("moved_occurrence_ids")),
                created_at=_aware(item.created_at),
            )
            for item in split_rows
        )

    return HistoricalDataset(
        questions=tuple(questions),
        cards=cards,
        aliases=aliases,
        decisions=decisions,
        loaded_human_examples=loaded_human_examples,
        excluded_examples=excluded_examples,
        human_cluster_splits=human_cluster_splits,
    )


def evaluate_dataset(
    dataset: HistoricalDataset,
    *,
    error_limit: int = 50,
) -> dict[str, Any]:
    if error_limit < 0:
        raise ValueError("error_limit must not be negative")

    cards_by_id = {card.id: card for card in dataset.cards}
    cards_by_direction: dict[str, list[HistoricalCard]] = defaultdict(list)
    aliases_by_direction: dict[str, list[HistoricalAlias]] = defaultdict(list)
    decisions_by_question: dict[UUID, list[HistoricalDecision]] = defaultdict(list)
    for card in dataset.cards:
        cards_by_direction[card.direction].append(card)
    for alias in dataset.aliases:
        aliases_by_direction[alias.direction].append(alias)
    for decision in dataset.decisions:
        decisions_by_question[decision.question_id].append(decision)
    for decisions in decisions_by_question.values():
        decisions.sort(key=lambda item: (item.created_at, str(item.id)))

    predicted_links = 0
    links_on_existing = 0
    correct_links = 0
    false_merges = 0
    false_splits = 0
    predicted_noise = 0
    correct_noise = 0
    predicted_non_flashcard = 0
    auto_filtered_rejections = 0
    saved_predictions = 0
    deterministic_predictions = 0
    semantic_predictions = 0
    topic_examples = 0
    correct_topics = 0
    error_buckets: dict[str, list[dict[str, object]]] = defaultdict(list)
    abstained_clusters: dict[str, list[HistoricalQuestion]] = defaultdict(list)

    existing_count = sum(
        item.ground_truth is GroundTruthKind.EXISTING_CARD for item in dataset.questions
    )
    new_card_count = sum(
        item.ground_truth is GroundTruthKind.NEW_CARD for item in dataset.questions
    )
    rejected_count = sum(
        item.ground_truth is GroundTruthKind.REJECTED for item in dataset.questions
    )

    for example in dataset.questions:
        prior_decisions = [
            item
            for item in decisions_by_question.get(example.id, [])
            if item.created_at < example.labeled_at
        ]
        prediction = predict_historical_outcome(
            example,
            cards_by_direction.get(example.direction, ()),
            aliases_by_direction.get(example.direction, ()),
            prior_decisions,
        )
        if prediction.source.startswith("saved_"):
            saved_predictions += 1
        else:
            deterministic_predictions += 1
        if prediction.source == "saved_semantic_card_match":
            semantic_predictions += 1

        routing_decision = next(
            (
                item
                for item in reversed(prior_decisions)
                if item.decision_type is AutomationDecisionType.QUESTION_ROUTED
            ),
            None,
        )
        topic_candidates = _topic_candidates(routing_decision)
        if topic_candidates:
            topic_examples += 1
            expected_topic = normalize_question(example.category)
            if expected_topic in {
                normalize_question(item) for item in topic_candidates if item.strip()
            }:
                correct_topics += 1
            else:
                _record_error(
                    error_buckets,
                    error_limit,
                    _error(
                        "wrong_topic",
                        example,
                        prediction,
                        cards_by_id,
                        reason=(
                            f"Predicted topics {topic_candidates!r} do not contain "
                            f"human topic {example.category!r}"
                        ),
                    ),
                )

        link_is_correct = bool(
            prediction.kind is PredictionKind.LINK
            and example.ground_truth is GroundTruthKind.EXISTING_CARD
            and prediction.selected_card_id == example.correct_card_id
        )
        if prediction.kind is PredictionKind.LINK:
            predicted_links += 1
            if example.ground_truth is GroundTruthKind.EXISTING_CARD:
                links_on_existing += 1
            if link_is_correct:
                correct_links += 1
            else:
                false_merges += 1
                _record_error(
                    error_buckets,
                    error_limit,
                    _error(
                        "false_merge",
                        example,
                        prediction,
                        cards_by_id,
                        reason=prediction.reason,
                    ),
                )

        if example.ground_truth is GroundTruthKind.EXISTING_CARD and not link_is_correct:
            false_splits += 1
            if prediction.kind is not PredictionKind.LINK:
                hint = candidate_hint(
                    example,
                    cards_by_direction.get(example.direction, ()),
                    aliases_by_direction.get(example.direction, ()),
                )
                _record_error(
                    error_buckets,
                    error_limit,
                    _error(
                        "false_split",
                        example,
                        hint or prediction,
                        cards_by_id,
                        reason=(hint.reason if hint is not None else prediction.reason),
                    ),
                )

        if prediction.kind is PredictionKind.NOISE:
            predicted_noise += 1
            if example.ground_truth is GroundTruthKind.REJECTED:
                correct_noise += 1
                auto_filtered_rejections += 1
            else:
                _record_error(
                    error_buckets,
                    error_limit,
                    _error(
                        "noise_false_positive",
                        example,
                        prediction,
                        cards_by_id,
                        reason=prediction.reason,
                    ),
                )
        elif prediction.kind is PredictionKind.NON_FLASHCARD:
            predicted_non_flashcard += 1
            if example.ground_truth is GroundTruthKind.REJECTED:
                auto_filtered_rejections += 1

        if example.ground_truth is GroundTruthKind.REJECTED and prediction.kind not in {
            PredictionKind.NOISE,
            PredictionKind.NON_FLASHCARD,
        }:
            _record_error(
                error_buckets,
                error_limit,
                _error(
                    "noise_false_negative",
                    example,
                    prediction,
                    cards_by_id,
                    reason="Legacy human rejection was not filtered automatically",
                ),
            )

        if prediction.kind is PredictionKind.ABSTAIN:
            cluster_key = (
                f"saved:{prediction.selected_cluster_id}"
                if prediction.selected_cluster_id is not None
                else _fallback_cluster_key(example)
            )
            abstained_clusters[cluster_key].append(example)

    purity_numerator = 0
    purity_denominator = 0
    impure_clusters = 0
    for members in abstained_clusters.values():
        labels = [
            item.correct_card_id
            for item in members
            if item.correct_card_id is not None
            and item.ground_truth in {GroundTruthKind.EXISTING_CARD, GroundTruthKind.NEW_CARD}
        ]
        if not labels:
            continue
        counts = Counter(labels)
        purity_numerator += counts.most_common(1)[0][1]
        purity_denominator += len(labels)
        if len(counts) > 1:
            impure_clusters += 1

    total = len(dataset.questions)
    manual_after = len(abstained_clusters)
    return {
        "evaluation_mode": "temporal_read_only_high_precision",
        "read_only": True,
        "examples": total,
        "loaded_human_examples": dataset.loaded_human_examples,
        "excluded_examples": dataset.excluded_examples,
        "ground_truth_existing_card": existing_count,
        "ground_truth_new_card": new_card_count,
        "ground_truth_rejected": rejected_count,
        "auto_link_coverage": _ratio(links_on_existing, existing_count),
        "auto_link_precision": _ratio(correct_links, predicted_links),
        "auto_link_recall": _ratio(correct_links, existing_count),
        "false_merge_rate": _ratio(false_merges, predicted_links),
        "false_split_rate": _ratio(false_splits, existing_count),
        "noise_precision": _ratio(correct_noise, predicted_noise),
        "noise_recall": _ratio(correct_noise, rejected_count),
        "cluster_purity": _ratio(purity_numerator, purity_denominator),
        "manual_tasks_before": total,
        "estimated_manual_tasks_after": manual_after,
        "estimated_queue_reduction": (round(1.0 - manual_after / total, 6) if total else 0.0),
        "predicted_links": predicted_links,
        "predicted_noise": predicted_noise,
        "predicted_non_flashcard": predicted_non_flashcard,
        "auto_filtered_rejection_recall": _ratio(auto_filtered_rejections, rejected_count),
        "saved_automation_predictions_used": saved_predictions,
        "deterministic_predictions_used": deterministic_predictions,
        "saved_semantic_predictions_evaluated": semantic_predictions,
        "topic_examples_with_saved_prediction": topic_examples,
        "topic_match_rate": _ratio(correct_topics, topic_examples),
        "estimated_shadow_clusters": manual_after,
        "impure_shadow_clusters": impure_clusters,
        "human_cluster_split_decisions": len(dataset.human_cluster_splits),
        "human_cluster_split_occurrences": sum(
            len(item.moved_occurrence_ids) for item in dataset.human_cluster_splits
        ),
        "methodology": {
            "card_availability": (
                "Only currently published cards/decks created no later than the human "
                "decision are candidates. The card created from the same occurrence is "
                "always excluded."
            ),
            "alias_availability": (
                "Only aliases confirmed by a human before the human decision are "
                "candidates; the evaluated occurrence itself is excluded."
            ),
            "semantic_and_judge": (
                "Semantic links are counted only when a saved pre-label automation "
                "decision exists. The evaluator never fabricates a pairwise judge result "
                "and never calls an LLM."
            ),
            "clustering": (
                "Saved pre-label cluster decisions are reused. Otherwise exact normalized "
                "wording is a conservative lower-bound cluster estimate."
            ),
            "rejection_label": (
                "Legacy rejection is used as a proxy for noise/non-card ground truth because "
                "the old queue did not store a structured rejection reason."
            ),
        },
        "metric_definitions": {
            "auto_link_coverage": (
                "existing-card labels receiving any link proposal / existing-card labels"
            ),
            "auto_link_precision": "correct existing-card links / all link proposals",
            "auto_link_recall": "correct existing-card links / existing-card labels",
            "false_merge_rate": (
                "wrong links, including links for rejected/new-card labels, / all links"
            ),
            "false_split_rate": (
                "existing-card labels not linked to the correct card / existing-card labels"
            ),
            "cluster_purity": (
                "majority human card label per unresolved predicted cluster / labeled members"
            ),
        },
        "errors": _balanced_errors(error_buckets, error_limit),
    }


def predict_historical_outcome(
    example: HistoricalQuestion,
    cards: Iterable[HistoricalCard],
    aliases: Iterable[HistoricalAlias],
    prior_decisions: Iterable[HistoricalDecision],
) -> Prediction:
    decisions = sorted(prior_decisions, key=lambda item: (item.created_at, str(item.id)))
    cluster_decision = next(
        (item for item in reversed(decisions) if item.decision_type in CLUSTER_DECISIONS),
        None,
    )
    decisive = next(
        (item for item in reversed(decisions) if item.decision_type in DECISIVE_TYPES),
        None,
    )
    if decisive is not None:
        return _prediction_from_saved(decisive, cluster_decision)

    routing = fallback_route(
        example.question_text,
        example.question_kind,
        example.extraction_confidence,
    )
    if routing.learning_object_type not in CARD_ELIGIBLE_TYPES and routing.confidence >= 0.9:
        return Prediction(
            kind=(
                PredictionKind.NOISE
                if routing.learning_object_type is LearningObjectType.NOISE
                else PredictionKind.NON_FLASHCARD
            ),
            source="deterministic_routing",
            selected_cluster_id=(
                cluster_decision.selected_cluster_id if cluster_decision else None
            ),
            confidence=routing.confidence,
            reason=routing.reason,
        )

    exact = _exact_historical_match(example, cards, aliases)
    if exact is not None:
        return exact
    return Prediction(
        kind=PredictionKind.ABSTAIN,
        source="deterministic_abstain",
        selected_cluster_id=(cluster_decision.selected_cluster_id if cluster_decision else None),
        reason=(
            "No exact canonical/prior-confirmed alias match; semantic auto-link is "
            "not inferred without a saved pairwise decision"
        ),
    )


def candidate_hint(
    example: HistoricalQuestion,
    cards: Iterable[HistoricalCard],
    aliases: Iterable[HistoricalAlias],
) -> Prediction | None:
    eligible_cards, eligible_aliases = _eligible_evidence(example, cards, aliases)
    aliases_by_card: dict[UUID, list[HistoricalAlias]] = defaultdict(list)
    for alias in eligible_aliases:
        aliases_by_card[alias.card_id].append(alias)
    ranked = rank_question_candidates(
        example.question_text,
        example.embedding,
        (
            QuestionCandidate(
                card_id=card.id,
                asked_count=card.asked_count,
                variants=(
                    QuestionVariant(card.question_text, card.embedding, "card"),
                    *(
                        QuestionVariant(alias.question_text, alias.embedding, "approved_alias")
                        for alias in aliases_by_card.get(card.id, ())
                    ),
                ),
            )
            for card in eligible_cards
        ),
        limit=1,
    )
    if not ranked:
        return None
    candidate = ranked[0]
    return Prediction(
        kind=PredictionKind.ABSTAIN,
        source="offline_candidate_only",
        selected_card_id=candidate.card_id,
        similarity=candidate.similarity,
        judge_decision="not_run_offline",
        reason=(
            "A similar candidate exists, but deterministic evaluation abstains because "
            "there is no saved pre-label pairwise judge decision"
        ),
    )


def _prediction_from_saved(
    decision: HistoricalDecision,
    cluster_decision: HistoricalDecision | None,
) -> Prediction:
    source = f"saved_{decision.decision_type.value}"
    if (
        decision.decision_type is AutomationDecisionType.SEMANTIC_CARD_MATCH
        and not _saved_semantic_gate_passed(decision)
    ):
        return Prediction(
            kind=PredictionKind.ABSTAIN,
            source=source,
            selected_card_id=decision.selected_card_id,
            selected_cluster_id=(
                cluster_decision.selected_cluster_id if cluster_decision else None
            ),
            similarity=_selected_score(decision),
            judge_decision=_judge_decision(decision.judge_result),
            confidence=decision.confidence,
            reason=(
                "Saved semantic candidate did not pass all original conservative gates: "
                f"{decision.reason}"
            ),
        )
    if decision.decision_type in MATCH_DECISIONS and decision.selected_card_id is not None:
        return Prediction(
            kind=PredictionKind.LINK,
            source=source,
            selected_card_id=decision.selected_card_id,
            selected_cluster_id=(
                cluster_decision.selected_cluster_id if cluster_decision else None
            ),
            similarity=_selected_score(decision),
            judge_decision=_judge_decision(decision.judge_result),
            confidence=decision.confidence,
            reason=decision.reason,
        )
    if decision.decision_type is AutomationDecisionType.ROUTED_AS_NOISE:
        kind = PredictionKind.NOISE
    elif decision.decision_type is AutomationDecisionType.ROUTED_AS_NON_FLASHCARD:
        kind = PredictionKind.NON_FLASHCARD
    else:
        kind = PredictionKind.ABSTAIN
    return Prediction(
        kind=kind,
        source=source,
        selected_cluster_id=(cluster_decision.selected_cluster_id if cluster_decision else None),
        confidence=decision.confidence,
        reason=decision.reason,
    )


def _saved_semantic_gate_passed(decision: HistoricalDecision) -> bool:
    return (
        _judge_decision(decision.judge_result) == "same_card"
        and decision.reason == "All conservative semantic auto-link checks passed"
    )


def _exact_historical_match(
    example: HistoricalQuestion,
    cards: Iterable[HistoricalCard],
    aliases: Iterable[HistoricalAlias],
) -> Prediction | None:
    eligible_cards, eligible_aliases = _eligible_evidence(example, cards, aliases)
    sources_by_card: dict[UUID, str] = {}
    for card in eligible_cards:
        if normalize_question(card.question_text) == example.normalized_question_text:
            sources_by_card[card.id] = "card"
    for alias in eligible_aliases:
        if normalize_question(alias.question_text) == example.normalized_question_text:
            sources_by_card.setdefault(alias.card_id, "approved_alias")
    if not sources_by_card:
        return None
    cards_by_id = {card.id: card for card in eligible_cards}
    selected_card_id = sorted(
        sources_by_card,
        key=lambda card_id: (-cards_by_id[card_id].asked_count, str(card_id)),
    )[0]
    source = sources_by_card[selected_card_id]
    return Prediction(
        kind=PredictionKind.LINK,
        source=(
            "deterministic_exact_card" if source == "card" else "deterministic_confirmed_alias"
        ),
        selected_card_id=selected_card_id,
        similarity=1.0,
        confidence=1.0,
        reason=(
            "Exact normalized canonical wording"
            if source == "card"
            else "Exact wording of a previously human-confirmed alias"
        ),
    )


def _eligible_evidence(
    example: HistoricalQuestion,
    cards: Iterable[HistoricalCard],
    aliases: Iterable[HistoricalAlias],
) -> tuple[list[HistoricalCard], list[HistoricalAlias]]:
    eligible_cards = [
        card
        for card in cards
        if card.direction == example.direction
        and card.available_for_matching
        and card.created_at <= example.labeled_at
        and card.slug != f"ai-{example.id.hex}"
    ]
    card_ids = {card.id for card in eligible_cards}
    eligible_aliases = [
        alias
        for alias in aliases
        if alias.direction == example.direction
        and alias.card_id in card_ids
        and alias.question_id != example.id
        and alias.confirmed_at < example.labeled_at
    ]
    return eligible_cards, eligible_aliases


def _fallback_cluster_key(example: HistoricalQuestion) -> str:
    normalized = example.normalized_question_text
    if not normalized:
        return f"singleton:{example.id}"
    return f"exact:{example.direction}:{normalized}"


def _selected_score(decision: HistoricalDecision) -> float | None:
    if decision.selected_card_id is None:
        return None
    value = decision.retrieval_scores.get(str(decision.selected_card_id))
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _judge_decision(value: dict[str, object] | None) -> str | None:
    if value is None:
        return None
    decision = value.get("decision")
    return decision if isinstance(decision, str) else None


def _topic_candidates(decision: HistoricalDecision | None) -> list[str]:
    if decision is None or decision.judge_result is None:
        return []
    value = decision.judge_result.get("topic_candidates")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _uuid_tuple(value: object) -> tuple[UUID, ...]:
    if not isinstance(value, list):
        return ()
    result: list[UUID] = []
    for item in value:
        try:
            result.append(UUID(str(item)))
        except (TypeError, ValueError):
            continue
    return tuple(result)


def _error(
    kind: str,
    example: HistoricalQuestion,
    prediction: Prediction,
    cards_by_id: dict[UUID, HistoricalCard],
    *,
    reason: str,
) -> dict[str, object]:
    selected = cards_by_id.get(prediction.selected_card_id) if prediction.selected_card_id else None
    correct = cards_by_id.get(example.correct_card_id) if example.correct_card_id else None
    return {
        "error_type": kind,
        "question_id": str(example.id),
        "question": example.question_text,
        "direction": example.direction,
        "ground_truth": example.ground_truth.value,
        "selected_card_id": (
            str(prediction.selected_card_id) if prediction.selected_card_id else None
        ),
        "selected_card_question": selected.question_text if selected else None,
        "correct_card_id": str(example.correct_card_id) if example.correct_card_id else None,
        "correct_card_question": correct.question_text if correct else None,
        "similarity": prediction.similarity,
        "judge_decision": prediction.judge_decision,
        "confidence": prediction.confidence,
        "prediction_source": prediction.source,
        "reason": reason,
    }


def _record_error(
    buckets: dict[str, list[dict[str, object]]],
    error_limit: int,
    error: dict[str, object],
) -> None:
    if error_limit == 0:
        return
    kind = str(error["error_type"])
    if len(buckets[kind]) < error_limit:
        buckets[kind].append(error)


def _balanced_errors(
    buckets: dict[str, list[dict[str, object]]], error_limit: int
) -> list[dict[str, object]]:
    if error_limit == 0:
        return []
    priority = (
        "false_merge",
        "noise_false_positive",
        "false_split",
        "noise_false_negative",
        "wrong_topic",
    )
    kinds = [kind for kind in priority if buckets.get(kind)]
    kinds.extend(sorted(set(buckets) - set(kinds)))
    result: list[dict[str, object]] = []
    index = 0
    while len(result) < error_limit:
        added = False
        for kind in kinds:
            if index < len(buckets[kind]):
                result.append(buckets[kind][index])
                added = True
                if len(result) == error_limit:
                    break
        if not added:
            break
        index += 1
    return result


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only temporal evaluation of card automation on human ground truth"
    )
    parser.add_argument("--from-date", type=date.fromisoformat)
    parser.add_argument("--to-date", type=date.fromisoformat)
    parser.add_argument("--direction", choices=("python", "go"))
    parser.add_argument("--error-limit", type=int, default=50)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.error_limit < 0:
        raise SystemExit("--error-limit must not be negative")
    report = asyncio.run(
        evaluate(
            from_date=args.from_date,
            to_date=args.to_date,
            direction=args.direction,
            error_limit=args.error_limit,
        )
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
