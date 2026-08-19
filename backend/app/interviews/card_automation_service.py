from __future__ import annotations

import asyncio
import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import and_, delete, exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import api_error
from app.interviews.card_automation_cleanup import (
    sync_cluster_embedding_from_representative,
)
from app.interviews.card_automation_domain import cluster_allowed_actions, next_personal_review
from app.interviews.card_automation_models import (
    AutomationDecision,
    CardAutomationSettings,
    InterviewCardDuplicateReview,
    PersonalReviewItem,
    QuestionCluster,
)
from app.interviews.card_automation_pipeline import (
    analysis_answer_draft_for_cluster,
    answer_contract_from_analysis_draft,
    ensure_personal_review_for_occurrence,
    link_occurrence_to_card,
    recalculate_cluster_stats,
    record_automation_decision,
)
from app.interviews.card_automation_schemas import (
    AnswerContract,
    AnswerValidationResult,
    AutomationDecisionListFilters,
    AutomationDecisionOverrideMutation,
    AutomationDecisionPage,
    AutomationDecisionRead,
    AutomationDecisionReviewMutation,
    CardAutomationMetricsFilters,
    CardAutomationMetricsRead,
    CardAutomationSettingsList,
    CardAutomationSettingsRead,
    CardAutomationSettingsUpdate,
    InterviewCardDuplicateCandidateRead,
    InterviewCardDuplicateCardRead,
    InterviewCardDuplicateMergeMutation,
    InterviewCardDuplicateMutation,
    InterviewCardDuplicatePage,
    InterviewCardDuplicateReviewResult,
    PersonalReviewItemCorrectionMutation,
    PersonalReviewItemCorrectionResult,
    PersonalReviewItemListFilters,
    PersonalReviewItemPage,
    PersonalReviewItemRead,
    PersonalReviewItemReviewMutation,
    PersonalReviewItemReviewResult,
    QuestionClusterAction,
    QuestionClusterActionMutation,
    QuestionClusterAllowedActions,
    QuestionClusterAnswerGenerationMutation,
    QuestionClusterAnswerGenerationResult,
    QuestionClusterBulkAction,
    QuestionClusterBulkItemResult,
    QuestionClusterBulkMutation,
    QuestionClusterBulkResult,
    QuestionClusterCardMatch,
    QuestionClusterCompanyRead,
    QuestionClusterCreateCardMutation,
    QuestionClusterDetail,
    QuestionClusterDraftMutation,
    QuestionClusterInterviewRead,
    QuestionClusterLinkCardMutation,
    QuestionClusterListFilters,
    QuestionClusterManualHistoryRead,
    QuestionClusterMergeMutation,
    QuestionClusterMutationResult,
    QuestionClusterOccurrenceRead,
    QuestionClusterPage,
    QuestionClusterSplitMutation,
    QuestionClusterSummary,
    QuestionClusterTopicOption,
    QuestionClusterVariantRead,
    QuestionOccurrenceReprocessMutation,
    QuestionOccurrenceReprocessResult,
)
from app.interviews.card_automation_types import (
    AnswerContractStatus,
    AutomationDecisionSource,
    AutomationDecisionType,
    AutomationReviewResult,
    LearningObjectType,
    PairwiseCardMatchDecision,
    PersonalReviewStatus,
    QuestionClusterStatus,
    QuestionOccurrenceStatus,
)
from app.interviews.card_frequency import refresh_card_frequency
from app.interviews.intelligence_models import (
    IntelligenceAnswer,
    IntelligenceAnswerReview,
    IntelligenceInterview,
    IntelligenceQuestion,
    IntelligenceQuestionModerationStatus,
    IntelligenceReviewSource,
    IntelligenceReviewStatus,
)
from app.interviews.intelligence_queue import enqueue_card_automation_job
from app.interviews.models import (
    InterviewCard,
    InterviewCardFrequencyMode,
    InterviewCardOccurrence,
    InterviewCardProgress,
    InterviewDeck,
    InterviewProcess,
    InterviewProcessStage,
    InterviewTopicSelection,
)
from app.interviews.question_matching import (
    QuestionCandidate,
    QuestionVariant,
    RankedQuestionCandidate,
    normalize_question,
    question_retrieval_terms,
    rank_question_candidates,
)
from app.mentors.models import MentorStudent
from app.tracks.access import accessible_track_ids
from app.tracks.models import LearningTrack
from app.users.models import MENTOR_CAPABLE_ROLES, User, UserRole

_HUMAN_CLUSTER_OUTCOMES = frozenset(
    {
        AutomationDecisionType.CLUSTER_LINKED,
        AutomationDecisionType.CARD_CREATED,
        AutomationDecisionType.CLUSTER_SPLIT,
        AutomationDecisionType.CLUSTER_MERGED,
        AutomationDecisionType.CLUSTER_IGNORED,
        AutomationDecisionType.CLUSTER_DEFERRED,
        AutomationDecisionType.CLUSTER_REOPENED,
        AutomationDecisionType.CLUSTER_MARKED_IMPORTANT,
    }
)
_CARD_MATCH_DECISIONS = frozenset(
    {
        AutomationDecisionType.EXACT_CARD_MATCH,
        AutomationDecisionType.ALIAS_CARD_MATCH,
        AutomationDecisionType.SEMANTIC_CARD_MATCH,
        AutomationDecisionType.CLUSTER_LINKED,
        AutomationDecisionType.CARD_CREATED,
    }
)
_MENTOR_CLUSTER_ACTIONS = frozenset(
    {
        QuestionClusterAction.UPDATE_DRAFT,
        QuestionClusterAction.IGNORE,
        QuestionClusterAction.DEFER,
        QuestionClusterAction.MARK_IMPORTANT,
        QuestionClusterAction.REOPEN,
    }
)


@dataclass(frozen=True, slots=True)
class _ActionOutcome:
    cluster_id: UUID
    decision_id: UUID
    created_card_id: UUID | None = None
    affected_cluster_ids: tuple[UUID, ...] = ()


def _full_name(user: User) -> str:
    return " ".join(part for part in (user.first_name, user.last_name) if part)


def _require_moderator(viewer: User) -> None:
    if viewer.role not in MENTOR_CAPABLE_ROLES:
        api_error(403, "card_automation_forbidden", "Card automation access is required")


def _require_admin(viewer: User) -> None:
    if viewer.role is not UserRole.ADMIN:
        api_error(403, "admin_required", "Administrator access is required")


def _normalized_topic_label(value: str) -> str:
    return " ".join(value.split()).casefold()


async def _canonical_existing_topic(
    session: AsyncSession,
    *,
    direction_id: UUID,
    topic_name: str,
    deck_id: UUID | None = None,
) -> str:
    statement = (
        select(InterviewCard.category)
        .join(InterviewDeck, InterviewDeck.id == InterviewCard.deck_id)
        .where(
            InterviewDeck.track_id == direction_id,
            InterviewDeck.is_published.is_(True),
            InterviewCard.is_published.is_(True),
        )
        .distinct()
    )
    if deck_id is not None:
        statement = statement.where(InterviewDeck.id == deck_id)
    categories = list(await session.scalars(statement))
    normalized = _normalized_topic_label(topic_name)
    canonical = next(
        (item for item in categories if _normalized_topic_label(item) == normalized),
        None,
    )
    if canonical is None:
        api_error(
            422,
            "interview_card_topic_not_found",
            "Выберите широкую тему из уже существующих тем карточек",
        )
    return canonical


async def _allowed_track_ids(session: AsyncSession, viewer: User) -> set[UUID]:
    _require_moderator(viewer)
    return await accessible_track_ids(session, viewer)


def _allowed_cluster_actions(cluster: QuestionCluster, viewer: User) -> list[QuestionClusterAction]:
    actions = [QuestionClusterAction(value) for value in cluster_allowed_actions(cluster.status)]
    if viewer.role is UserRole.ADMIN:
        return actions
    if viewer.role is UserRole.MENTOR:
        return [action for action in actions if action in _MENTOR_CLUSTER_ACTIONS]
    return []


def _json_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str):
            text_value = item.strip()
        elif item is None:
            continue
        else:
            text_value = str(item).strip()
        if text_value:
            result.append(text_value)
    return result


def _bounded_score(value: object, *, default: float = 0.0) -> float:
    if isinstance(value, int | float | Decimal):
        return min(max(float(value), 0.0), 1.0)
    return default


def _answer_contract(payload: dict[str, object] | None) -> AnswerContract | None:
    if not payload:
        return None
    try:
        return AnswerContract.model_validate(payload)
    except ValidationError:
        short_answer_value = payload.get("short_answer")
        short_answer = (
            str(short_answer_value).strip()
            if short_answer_value is not None and str(short_answer_value).strip()
            else "Ответ требует экспертной проверки."
        )
        difficulty = str(payload.get("difficulty") or "mixed")
        if difficulty not in {"junior", "middle", "senior", "mixed"}:
            difficulty = "mixed"
        return AnswerContract(
            short_answer=short_answer,
            required_points=_json_strings(payload.get("required_points")),
            optional_points=_json_strings(payload.get("optional_points")),
            common_mistakes=_json_strings(payload.get("common_mistakes")),
            unsupported_claims=_json_strings(payload.get("unsupported_claims")),
            follow_up_questions=_json_strings(payload.get("follow_up_questions")),
            difficulty=cast(Any, difficulty),
            version_scope=_json_strings(payload.get("version_scope")),
            source_references=_json_strings(payload.get("source_references")),
            confidence=_bounded_score(payload.get("confidence")),
        )


def _answer_validation(payload: dict[str, object] | None) -> AnswerValidationResult | None:
    if not payload:
        return None
    try:
        return AnswerValidationResult.model_validate(payload)
    except ValidationError:
        return AnswerValidationResult(
            supported=bool(payload.get("supported", False)),
            unsupported_claims=_json_strings(payload.get("unsupported_claims")),
            contradictions=_json_strings(payload.get("contradictions")),
            missing_required_points=_json_strings(payload.get("missing_required_points")),
            version_sensitive_claims=_json_strings(payload.get("version_sensitive_claims")),
            confidence=_bounded_score(payload.get("confidence")),
        )


def _uuid_list(values: object) -> list[UUID]:
    if not isinstance(values, list):
        return []
    result: list[UUID] = []
    for value in values:
        try:
            result.append(UUID(str(value)))
        except (TypeError, ValueError, AttributeError):
            continue
    return result


def _score_for_card(decision: AutomationDecision, card_id: UUID) -> float:
    value = decision.retrieval_scores.get(str(card_id))
    if isinstance(value, dict):
        value = value.get("similarity") or value.get("score")
    return _bounded_score(value)


def _judge_values(
    payload: dict[str, object] | None,
) -> tuple[PairwiseCardMatchDecision | None, float | None, str | None]:
    if not payload:
        return None, None, None
    try:
        judge_decision = PairwiseCardMatchDecision(str(payload.get("decision")))
    except ValueError:
        judge_decision = None
    confidence_value = payload.get("confidence")
    judge_confidence = (
        _bounded_score(confidence_value)
        if isinstance(confidence_value, int | float | Decimal)
        else None
    )
    reason_value = payload.get("reasoning_summary") or payload.get("reason")
    judge_reason = str(reason_value) if reason_value is not None else None
    return judge_decision, judge_confidence, judge_reason


async def _latest_cluster_decisions(
    session: AsyncSession, cluster_ids: Sequence[UUID]
) -> dict[UUID, AutomationDecision]:
    if not cluster_ids:
        return {}
    ranked = (
        select(
            AutomationDecision.id.label("decision_id"),
            AutomationDecision.entity_id.label("cluster_id"),
            func.row_number()
            .over(
                partition_by=AutomationDecision.entity_id,
                order_by=(AutomationDecision.created_at.desc(), AutomationDecision.id.desc()),
            )
            .label("rank"),
        )
        .where(
            AutomationDecision.entity_type == "cluster",
            AutomationDecision.entity_id.in_(cluster_ids),
        )
        .subquery()
    )
    rows = (
        await session.execute(
            select(ranked.c.cluster_id, AutomationDecision)
            .join(AutomationDecision, AutomationDecision.id == ranked.c.decision_id)
            .where(ranked.c.rank == 1)
        )
    ).all()
    return {cluster_id: decision for cluster_id, decision in rows}


async def _latest_cluster_match_decisions(
    session: AsyncSession, cluster_ids: Sequence[UUID]
) -> dict[UUID, AutomationDecision]:
    if not cluster_ids:
        return {}
    ranked = (
        select(
            IntelligenceQuestion.cluster_id.label("cluster_id"),
            AutomationDecision.id.label("decision_id"),
            func.row_number()
            .over(
                partition_by=IntelligenceQuestion.cluster_id,
                order_by=(AutomationDecision.created_at.desc(), AutomationDecision.id.desc()),
            )
            .label("rank"),
        )
        .join(
            AutomationDecision,
            and_(
                AutomationDecision.entity_type == "occurrence",
                AutomationDecision.entity_id == IntelligenceQuestion.id,
            ),
        )
        .where(
            IntelligenceQuestion.cluster_id.in_(cluster_ids),
            AutomationDecision.decision_type.in_(_CARD_MATCH_DECISIONS),
            or_(
                AutomationDecision.selected_card_id.is_not(None),
                func.jsonb_array_length(AutomationDecision.candidate_card_ids) > 0,
            ),
        )
        .subquery()
    )
    rows = (
        await session.execute(
            select(ranked.c.cluster_id, AutomationDecision)
            .join(AutomationDecision, AutomationDecision.id == ranked.c.decision_id)
            .where(ranked.c.rank == 1)
        )
    ).all()
    return {cluster_id: decision for cluster_id, decision in rows}


async def _card_matches_for_decisions(
    session: AsyncSession, decisions: Iterable[AutomationDecision]
) -> dict[UUID, QuestionClusterCardMatch]:
    selection_by_decision: dict[UUID, tuple[AutomationDecision, UUID]] = {}
    for decision in decisions:
        candidate_ids = _uuid_list(decision.candidate_card_ids)
        card_id = decision.selected_card_id or (candidate_ids[0] if candidate_ids else None)
        if card_id is not None:
            selection_by_decision[decision.id] = (decision, card_id)
    if not selection_by_decision:
        return {}
    card_ids = {card_id for _, card_id in selection_by_decision.values()}
    cards = list(await session.scalars(select(InterviewCard).where(InterviewCard.id.in_(card_ids))))
    card_by_id = {card.id: card for card in cards}
    result: dict[UUID, QuestionClusterCardMatch] = {}
    for decision_id, (decision, card_id) in selection_by_decision.items():
        card = card_by_id.get(card_id)
        if card is None:
            continue
        judge_decision, judge_confidence, judge_reason = _judge_values(decision.judge_result)
        score = _score_for_card(decision, card.id)
        result[decision_id] = QuestionClusterCardMatch(
            card_id=card.id,
            question_markdown=card.question_markdown,
            answer_markdown=card.answer_markdown,
            category=card.category,
            semantic_score=score,
            combined_score=score,
            judge_decision=judge_decision,
            judge_confidence=judge_confidence,
            judge_reason=judge_reason,
            is_confirmed_alias=(
                decision.decision_source is AutomationDecisionSource.CONFIRMED_ALIAS
            ),
        )
    return result


async def _cluster_summaries(
    session: AsyncSession,
    viewer: User,
    rows: Sequence[tuple[QuestionCluster, LearningTrack]],
) -> list[QuestionClusterSummary]:
    cluster_ids = [cluster.id for cluster, _ in rows]
    latest_decisions = await _latest_cluster_decisions(session, cluster_ids)
    match_decisions = await _latest_cluster_match_decisions(session, cluster_ids)
    match_by_decision = await _card_matches_for_decisions(session, match_decisions.values())
    return [
        QuestionClusterSummary(
            id=cluster.id,
            direction_id=cluster.direction_id,
            direction_slug=track.slug,
            direction_title=track.title,
            status=cluster.status,
            canonical_question=cluster.canonical_question,
            learning_object_type=cluster.learning_object_type,
            deck_id=cluster.deck_id,
            topic_name=cluster.topic_name,
            subtopic_name=cluster.subtopic_name,
            topic_candidates=cluster.topic_candidates,
            linked_card_id=cluster.linked_card_id,
            best_match=(
                match_by_decision.get(match_decisions[cluster.id].id)
                if cluster.id in match_decisions
                else None
            ),
            last_decision_source=(
                latest_decisions[cluster.id].decision_source
                if cluster.id in latest_decisions
                else None
            ),
            occurrences_count=cluster.occurrences_count,
            distinct_interviews_count=cluster.distinct_interviews_count,
            distinct_companies_count=cluster.distinct_companies_count,
            distinct_students_count=cluster.distinct_students_count,
            failed_answers_count=cluster.failed_answers_count,
            priority_score=cluster.priority_score,
            quality_score=cluster.quality_score,
            cluster_confidence=cluster.cluster_confidence,
            first_seen_at=cluster.first_seen_at,
            last_seen_at=cluster.last_seen_at,
            manual_important=cluster.manual_important,
            version=cluster.version,
            allowed_actions=_allowed_cluster_actions(cluster, viewer),
        )
        for cluster, track in rows
    ]


def _cluster_scope_condition(track_ids: set[UUID]) -> Any:
    return QuestionCluster.direction_id.in_(track_ids)


def _decision_scope_condition(track_ids: set[UUID], viewer: User | None = None) -> Any:
    occurrence_scope = (
        select(IntelligenceQuestion.id)
        .join(
            IntelligenceInterview,
            IntelligenceInterview.id == IntelligenceQuestion.interview_id,
        )
        .where(
            IntelligenceQuestion.id == AutomationDecision.entity_id,
            IntelligenceQuestion.direction_id.in_(track_ids),
        )
    )
    if viewer is not None and viewer.role is UserRole.MENTOR:
        occurrence_scope = occurrence_scope.where(
            exists(
                select(MentorStudent.student_id).where(
                    MentorStudent.student_id == IntelligenceInterview.student_id,
                    MentorStudent.mentor_id == viewer.id,
                )
            )
        )
    occurrence_in_scope = exists(occurrence_scope)
    cluster_in_scope = exists(
        select(QuestionCluster.id).where(
            QuestionCluster.id == AutomationDecision.entity_id,
            QuestionCluster.direction_id.in_(track_ids),
        )
    )
    personal_scope = select(PersonalReviewItem.id).where(
        PersonalReviewItem.id == AutomationDecision.entity_id,
        PersonalReviewItem.direction_id.in_(track_ids),
    )
    if viewer is not None and viewer.role is UserRole.MENTOR:
        personal_scope = personal_scope.where(
            exists(
                select(MentorStudent.student_id).where(
                    MentorStudent.student_id == PersonalReviewItem.student_id,
                    MentorStudent.mentor_id == viewer.id,
                )
            )
        )
    personal_in_scope = exists(personal_scope)
    conditions = [
        and_(AutomationDecision.entity_type == "occurrence", occurrence_in_scope),
        and_(AutomationDecision.entity_type == "cluster", cluster_in_scope),
        and_(AutomationDecision.entity_type == "personal_review_item", personal_in_scope),
    ]
    # Settings mutations are platform-level administrative decisions. They are
    # intentionally visible only to administrators, while still participating
    # in the same direction-scoped audit log as the rest of the automation.
    if viewer is None or viewer.role is UserRole.ADMIN:
        conditions.append(
            and_(
                AutomationDecision.entity_type == "settings",
                AutomationDecision.entity_id.in_(track_ids),
            )
        )
    return or_(*conditions)


async def list_question_clusters(
    session: AsyncSession,
    viewer: User,
    filters: QuestionClusterListFilters,
) -> QuestionClusterPage:
    track_ids = await _allowed_track_ids(session, viewer)
    if filters.direction_id is not None:
        if filters.direction_id not in track_ids:
            api_error(404, "learning_track_not_found", "Learning track was not found")
        track_ids = {filters.direction_id}
    if not track_ids:
        return QuestionClusterPage(items=[], total=0, limit=filters.limit, offset=filters.offset)

    conditions: list[Any] = [_cluster_scope_condition(track_ids)]
    if filters.statuses:
        conditions.append(QuestionCluster.status.in_(filters.statuses))
    if filters.topic_name is not None:
        conditions.append(QuestionCluster.topic_name == filters.topic_name)
    if filters.learning_object_types:
        conditions.append(QuestionCluster.learning_object_type.in_(filters.learning_object_types))
    if filters.min_distinct_interviews is not None:
        conditions.append(
            QuestionCluster.distinct_interviews_count >= filters.min_distinct_interviews
        )
    if filters.min_distinct_companies is not None:
        conditions.append(
            QuestionCluster.distinct_companies_count >= filters.min_distinct_companies
        )
    if filters.has_failed_answers is True:
        conditions.append(QuestionCluster.failed_answers_count > 0)
    elif filters.has_failed_answers is False:
        conditions.append(QuestionCluster.failed_answers_count == 0)
    if filters.min_confidence is not None:
        conditions.append(QuestionCluster.cluster_confidence >= filters.min_confidence)
    if filters.max_confidence is not None:
        conditions.append(QuestionCluster.cluster_confidence <= filters.max_confidence)
    if filters.seen_from is not None:
        conditions.append(QuestionCluster.last_seen_at >= filters.seen_from)
    if filters.seen_to is not None:
        conditions.append(QuestionCluster.first_seen_at <= filters.seen_to)
    if filters.needs_action_only:
        conditions.append(QuestionCluster.status == QuestionClusterStatus.NEEDS_REVIEW)
    if filters.decision_source is not None:
        conditions.append(
            exists(
                select(AutomationDecision.id)
                .join(
                    IntelligenceQuestion,
                    IntelligenceQuestion.id == AutomationDecision.entity_id,
                )
                .where(
                    AutomationDecision.entity_type == "occurrence",
                    IntelligenceQuestion.cluster_id == QuestionCluster.id,
                    AutomationDecision.decision_source == filters.decision_source,
                )
            )
        )
    if filters.has_possible_duplicate is not None:
        possible_duplicate = exists(
            select(AutomationDecision.id)
            .join(
                IntelligenceQuestion,
                IntelligenceQuestion.id == AutomationDecision.entity_id,
            )
            .where(
                AutomationDecision.entity_type == "occurrence",
                IntelligenceQuestion.cluster_id == QuestionCluster.id,
                or_(
                    AutomationDecision.selected_card_id.is_not(None),
                    func.jsonb_array_length(AutomationDecision.candidate_card_ids) > 0,
                ),
            )
        )
        conditions.append(
            possible_duplicate
            if filters.has_possible_duplicate is not False
            else ~possible_duplicate
        )

    total = int(
        await session.scalar(select(func.count(QuestionCluster.id)).where(*conditions)) or 0
    )
    sort_columns = {
        "priority_score": QuestionCluster.priority_score,
        "last_seen_at": QuestionCluster.last_seen_at,
        "first_seen_at": QuestionCluster.first_seen_at,
        "occurrences_count": QuestionCluster.occurrences_count,
        "cluster_confidence": QuestionCluster.cluster_confidence,
    }
    sort_column = sort_columns[filters.sort_by]
    order = sort_column.asc() if filters.sort_order == "asc" else sort_column.desc()
    rows = list(
        (
            await session.execute(
                select(QuestionCluster, LearningTrack)
                .join(LearningTrack, LearningTrack.id == QuestionCluster.direction_id)
                .where(*conditions)
                .order_by(order, QuestionCluster.id)
                .limit(filters.limit)
                .offset(filters.offset)
            )
        ).tuples()
    )
    return QuestionClusterPage(
        items=await _cluster_summaries(session, viewer, rows),
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


async def _cluster_row(
    session: AsyncSession,
    viewer: User,
    cluster_id: UUID,
    *,
    lock: bool = False,
) -> tuple[QuestionCluster, LearningTrack]:
    track_ids = await _allowed_track_ids(session, viewer)
    statement = (
        select(QuestionCluster, LearningTrack)
        .join(LearningTrack, LearningTrack.id == QuestionCluster.direction_id)
        .where(QuestionCluster.id == cluster_id, QuestionCluster.direction_id.in_(track_ids))
    )
    if lock:
        statement = statement.with_for_update(of=QuestionCluster)
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        api_error(404, "question_cluster_not_found", "Question cluster was not found")
    return row[0], row[1]


async def _cluster_summaries_by_ids(
    session: AsyncSession, viewer: User, cluster_ids: Iterable[UUID]
) -> dict[UUID, QuestionClusterSummary]:
    ids = list(dict.fromkeys(cluster_ids))
    if not ids:
        return {}
    track_ids = await _allowed_track_ids(session, viewer)
    rows = list(
        (
            await session.execute(
                select(QuestionCluster, LearningTrack)
                .join(LearningTrack, LearningTrack.id == QuestionCluster.direction_id)
                .where(
                    QuestionCluster.id.in_(ids),
                    QuestionCluster.direction_id.in_(track_ids),
                )
            )
        ).tuples()
    )
    summaries = await _cluster_summaries(session, viewer, rows)
    return {summary.id: summary for summary in summaries}


async def _decision_reads(
    session: AsyncSession, decisions: Sequence[AutomationDecision]
) -> list[AutomationDecisionRead]:
    occurrence_ids = [item.entity_id for item in decisions if item.entity_type == "occurrence"]
    cluster_entity_ids = [item.entity_id for item in decisions if item.entity_type == "cluster"]
    personal_ids = [
        item.entity_id for item in decisions if item.entity_type == "personal_review_item"
    ]
    card_ids = {item.selected_card_id for item in decisions if item.selected_card_id is not None}
    selected_cluster_ids = {
        item.selected_cluster_id for item in decisions if item.selected_cluster_id is not None
    }
    user_ids = {
        user_id
        for item in decisions
        for user_id in (item.reviewed_by_user_id, item.overridden_by_user_id)
        if user_id is not None
    }

    questions = (
        list(
            await session.scalars(
                select(IntelligenceQuestion).where(IntelligenceQuestion.id.in_(occurrence_ids))
            )
        )
        if occurrence_ids
        else []
    )
    clusters = (
        list(
            await session.scalars(
                select(QuestionCluster).where(
                    QuestionCluster.id.in_({*cluster_entity_ids, *selected_cluster_ids})
                )
            )
        )
        if cluster_entity_ids or selected_cluster_ids
        else []
    )
    personal_items = (
        list(
            await session.scalars(
                select(PersonalReviewItem).where(PersonalReviewItem.id.in_(personal_ids))
            )
        )
        if personal_ids
        else []
    )
    cards = (
        list(await session.scalars(select(InterviewCard).where(InterviewCard.id.in_(card_ids))))
        if card_ids
        else []
    )
    users = (
        list(await session.scalars(select(User).where(User.id.in_(user_ids)))) if user_ids else []
    )
    question_by_id = {item.id: item for item in questions}
    cluster_by_id = {item.id: item for item in clusters}
    personal_by_id = {item.id: item for item in personal_items}
    card_by_id = {item.id: item for item in cards}
    user_by_id = {item.id: item for item in users}

    result: list[AutomationDecisionRead] = []
    for decision in decisions:
        question_text: str | None = None
        entity_version: int | None = None
        if decision.entity_type == "occurrence" and decision.entity_id in question_by_id:
            question = question_by_id[decision.entity_id]
            question_text = question.question_text
            entity_version = question.automation_revision
        elif decision.entity_type == "cluster" and decision.entity_id in cluster_by_id:
            cluster = cluster_by_id[decision.entity_id]
            question_text = cluster.canonical_question
            entity_version = cluster.version
        elif (
            decision.entity_type == "personal_review_item" and decision.entity_id in personal_by_id
        ):
            personal_item = personal_by_id[decision.entity_id]
            question_text = personal_item.question_text
            entity_version = personal_item.version
        selected_card = (
            card_by_id.get(decision.selected_card_id)
            if decision.selected_card_id is not None
            else None
        )
        selected_cluster = (
            cluster_by_id.get(decision.selected_cluster_id)
            if decision.selected_cluster_id is not None
            else None
        )
        similarity_score = (
            _score_for_card(decision, decision.selected_card_id)
            if decision.selected_card_id is not None
            else None
        )
        reviewed_by = (
            user_by_id.get(decision.reviewed_by_user_id)
            if decision.reviewed_by_user_id is not None
            else None
        )
        overridden_by = (
            user_by_id.get(decision.overridden_by_user_id)
            if decision.overridden_by_user_id is not None
            else None
        )
        result.append(
            AutomationDecisionRead(
                id=decision.id,
                entity_type=decision.entity_type,
                entity_id=decision.entity_id,
                entity_version=entity_version,
                question_text=question_text,
                decision_type=decision.decision_type,
                decision_source=decision.decision_source,
                selected_card_id=decision.selected_card_id,
                selected_card_question=(
                    selected_card.question_markdown if selected_card is not None else None
                ),
                selected_cluster_id=decision.selected_cluster_id,
                selected_cluster_question=(
                    selected_cluster.canonical_question if selected_cluster is not None else None
                ),
                candidate_card_ids=_uuid_list(decision.candidate_card_ids),
                candidate_cluster_ids=_uuid_list(decision.candidate_cluster_ids),
                retrieval_scores=decision.retrieval_scores,
                judge_result=decision.judge_result,
                confidence=decision.confidence,
                similarity_score=similarity_score,
                reason=decision.reason,
                model_provider=decision.model_provider,
                model_name=decision.model_name,
                prompt_version=decision.prompt_version,
                schema_version=decision.schema_version,
                input_tokens=decision.input_tokens,
                output_tokens=decision.output_tokens,
                cost=decision.cost,
                latency_ms=decision.latency_ms,
                is_audit_sample=decision.is_audit_sample,
                review_result=decision.review_result,
                reviewed_by_user_id=decision.reviewed_by_user_id,
                reviewed_by_name=_full_name(reviewed_by) if reviewed_by is not None else None,
                reviewed_at=decision.reviewed_at,
                review_reason=decision.review_reason,
                is_overridden=decision.is_overridden,
                overridden_by_user_id=decision.overridden_by_user_id,
                overridden_by_name=(
                    _full_name(overridden_by) if overridden_by is not None else None
                ),
                override_reason=decision.override_reason,
                overridden_at=decision.overridden_at,
                created_at=decision.created_at,
            )
        )
    return result


async def _top_card_matches(
    session: AsyncSession,
    cluster: QuestionCluster,
    occurrence_ids: Sequence[UUID],
) -> list[QuestionClusterCardMatch]:
    conditions = [
        and_(
            AutomationDecision.entity_type == "cluster",
            AutomationDecision.entity_id == cluster.id,
        )
    ]
    if occurrence_ids:
        conditions.append(
            and_(
                AutomationDecision.entity_type == "occurrence",
                AutomationDecision.entity_id.in_(occurrence_ids),
            )
        )
    decisions = list(
        await session.scalars(
            select(AutomationDecision)
            .where(
                or_(*conditions),
                AutomationDecision.decision_type.in_(_CARD_MATCH_DECISIONS),
            )
            .order_by(AutomationDecision.created_at.desc())
            .limit(100)
        )
    )
    score_by_card: dict[UUID, float] = {}
    decision_by_card: dict[UUID, AutomationDecision] = {}
    excluded_card_ids = {cluster.linked_card_id} if cluster.linked_card_id is not None else set()
    for decision in decisions:
        candidate_ids = _uuid_list(decision.candidate_card_ids)
        if decision.selected_card_id is not None:
            candidate_ids.insert(0, decision.selected_card_id)
        for card_id in candidate_ids:
            if card_id in excluded_card_ids:
                continue
            score = _score_for_card(decision, card_id)
            if card_id not in score_by_card or score > score_by_card[card_id]:
                score_by_card[card_id] = score
                decision_by_card[card_id] = decision

    cards = list(
        await session.scalars(
            select(InterviewCard)
            .join(InterviewDeck, InterviewDeck.id == InterviewCard.deck_id)
            .where(
                InterviewDeck.track_id == cluster.direction_id,
                InterviewDeck.is_published.is_(True),
                InterviewCard.is_published.is_(True),
                InterviewCard.slug != f"cluster-{cluster.id}",
            )
            .order_by(InterviewDeck.position, InterviewCard.position, InterviewCard.id)
        )
    )
    if not cards:
        return []

    aliases = list(
        await session.scalars(
            select(IntelligenceQuestion)
            .where(
                IntelligenceQuestion.published_card_id.in_([card.id for card in cards]),
                IntelligenceQuestion.moderation_status
                == IntelligenceQuestionModerationStatus.APPROVED,
                IntelligenceQuestion.alias_human_confirmed.is_(True),
            )
            .order_by(IntelligenceQuestion.created_at, IntelligenceQuestion.id)
        )
    )
    aliases_by_card: dict[UUID, list[IntelligenceQuestion]] = defaultdict(list)
    for alias in aliases:
        if alias.published_card_id is not None:
            aliases_by_card[alias.published_card_id].append(alias)

    cluster_embedding = tuple(cluster.embedding) if cluster.embedding else None
    dynamic_matches = rank_question_candidates(
        cluster.canonical_question,
        cluster_embedding,
        [
            QuestionCandidate(
                card_id=card.id,
                asked_count=card.asked_count,
                variants=(
                    QuestionVariant(
                        text=card.question_markdown,
                        embedding=(
                            tuple(card.question_embedding)
                            if cluster_embedding is not None
                            and card.question_embedding is not None
                            and card.question_embedding_model == cluster.embedding_model
                            and card.question_embedding_dimensions == cluster.embedding_dimensions
                            else None
                        ),
                        source="card",
                    ),
                    *(
                        QuestionVariant(
                            text=alias.question_text,
                            embedding=(
                                tuple(alias.question_embedding)
                                if cluster_embedding is not None
                                and alias.question_embedding is not None
                                and alias.question_embedding_model == cluster.embedding_model
                                and alias.question_embedding_dimensions
                                == cluster.embedding_dimensions
                                else None
                            ),
                            source="approved_alias",
                        )
                        for alias in aliases_by_card[card.id]
                    ),
                ),
            )
            for card in cards
            if card.id not in excluded_card_ids
        ],
        limit=10,
    )
    dynamic_by_card: dict[UUID, RankedQuestionCandidate] = {
        item.card_id: item for item in dynamic_matches
    }
    for match in dynamic_matches:
        score_by_card[match.card_id] = max(
            score_by_card.get(match.card_id, 0.0),
            match.similarity,
        )
    if not score_by_card:
        return []

    card_by_id = {item.id: item for item in cards}
    result: list[QuestionClusterCardMatch] = []
    ranked_cards = sorted(score_by_card.items(), key=lambda item: item[1], reverse=True)[:10]
    for card_id, score in ranked_cards:
        card = card_by_id.get(card_id)
        if card is None:
            continue
        selected_decision = decision_by_card.get(card_id)
        judge_decision, judge_confidence, judge_reason = _judge_values(
            selected_decision.judge_result if selected_decision is not None else None
        )
        dynamic_match = dynamic_by_card.get(card_id)
        result.append(
            QuestionClusterCardMatch(
                card_id=card.id,
                question_markdown=card.question_markdown,
                answer_markdown=card.answer_markdown,
                category=card.category,
                semantic_score=score,
                combined_score=score,
                judge_decision=judge_decision,
                judge_confidence=judge_confidence,
                judge_reason=judge_reason,
                is_confirmed_alias=(
                    (
                        selected_decision is not None
                        and selected_decision.decision_source
                        is AutomationDecisionSource.CONFIRMED_ALIAS
                    )
                    or (
                        dynamic_match is not None
                        and dynamic_match.matched_source == "approved_alias"
                    )
                ),
            )
        )
    return result


async def get_question_cluster_detail(
    session: AsyncSession,
    viewer: User,
    cluster_id: UUID,
) -> QuestionClusterDetail:
    cluster, track = await _cluster_row(session, viewer, cluster_id)
    latest_assessment = (
        select(IntelligenceAnswerReview.assessment)
        .where(
            IntelligenceAnswerReview.answer_id == IntelligenceAnswer.id,
            IntelligenceAnswerReview.status != IntelligenceReviewStatus.REJECTED,
        )
        .order_by(
            (IntelligenceAnswerReview.source == IntelligenceReviewSource.MENTOR).desc(),
            IntelligenceAnswerReview.created_at.desc(),
        )
        .limit(1)
        .correlate(IntelligenceAnswer)
        .scalar_subquery()
    )
    occurrences_statement = (
        select(
            IntelligenceQuestion,
            IntelligenceInterview,
            InterviewProcessStage,
            InterviewProcess,
            User,
            IntelligenceAnswer,
            latest_assessment.label("answer_assessment"),
        )
        .join(
            IntelligenceInterview,
            IntelligenceInterview.id == IntelligenceQuestion.interview_id,
        )
        .join(InterviewProcessStage, InterviewProcessStage.id == IntelligenceInterview.stage_id)
        .join(InterviewProcess, InterviewProcess.id == InterviewProcessStage.process_id)
        .join(User, User.id == IntelligenceInterview.student_id)
        .outerjoin(IntelligenceAnswer, IntelligenceAnswer.question_id == IntelligenceQuestion.id)
        .where(IntelligenceQuestion.cluster_id == cluster.id)
        .order_by(IntelligenceQuestion.created_at, IntelligenceQuestion.id)
    )
    if viewer.role is UserRole.MENTOR:
        occurrences_statement = occurrences_statement.where(
            exists(
                select(MentorStudent.student_id).where(
                    MentorStudent.student_id == IntelligenceInterview.student_id,
                    MentorStudent.mentor_id == viewer.id,
                )
            )
        )
    occurrence_rows = (await session.execute(occurrences_statement)).all()
    occurrences: list[QuestionClusterOccurrenceRead] = []
    variant_stats: dict[str, tuple[str, int, datetime, datetime]] = {}
    company_stats: dict[tuple[UUID | None, str], int] = defaultdict(int)
    interview_stats: dict[UUID, tuple[UUID | None, str, datetime, int]] = {}
    for question, interview, stage, process, student, answer, assessment in occurrence_rows:
        occurrences.append(
            QuestionClusterOccurrenceRead(
                id=question.id,
                interview_id=interview.id,
                student_id=student.id,
                student_name=_full_name(student),
                company_id=process.company_id,
                company_name=process.company_name,
                interviewed_at=stage.scheduled_at,
                question_text=question.question_text,
                canonical_question_candidate=question.canonical_question_candidate,
                source_context=question.source_context,
                answer_text=answer.answer_text if answer is not None else None,
                answer_assessment=assessment.value if assessment is not None else None,
                learning_object_type=question.learning_object_type,
                routing_confidence=question.routing_confidence,
                quality_flags=question.quality_flags,
                automation_status=question.automation_status,
                automation_revision=question.automation_revision,
                automation_error=question.automation_error,
                created_at=question.created_at,
            )
        )
        variant = variant_stats.get(question.normalized_question_text)
        if variant is None:
            variant_stats[question.normalized_question_text] = (
                question.question_text,
                1,
                question.created_at,
                question.created_at,
            )
        else:
            variant_stats[question.normalized_question_text] = (
                variant[0],
                variant[1] + 1,
                min(variant[2], question.created_at),
                max(variant[3], question.created_at),
            )
        company_stats[(process.company_id, process.company_name)] += 1
        interview_stat = interview_stats.get(interview.id)
        if interview_stat is None:
            interview_stats[interview.id] = (
                process.company_id,
                process.company_name,
                stage.scheduled_at,
                1,
            )
        else:
            interview_stats[interview.id] = (*interview_stat[:3], interview_stat[3] + 1)

    decisions = list(
        await session.scalars(
            select(AutomationDecision)
            .where(
                or_(
                    and_(
                        AutomationDecision.entity_type == "cluster",
                        AutomationDecision.entity_id == cluster.id,
                    ),
                    and_(
                        AutomationDecision.entity_type == "occurrence",
                        AutomationDecision.entity_id.in_([item.id for item in occurrences]),
                    ),
                )
            )
            .order_by(AutomationDecision.created_at.desc(), AutomationDecision.id.desc())
        )
    )
    decision_reads = await _decision_reads(session, decisions)
    manual_history = [
        QuestionClusterManualHistoryRead(
            id=decision.id,
            action=decision.decision_type.value,
            actor_user_id=decision.reviewed_by_user_id or decision.overridden_by_user_id,
            actor_name=decision.reviewed_by_name or decision.overridden_by_name,
            reason=decision.override_reason or decision.review_reason or decision.reason,
            changes=decision.retrieval_scores,
            created_at=decision.created_at,
        )
        for decision in decision_reads
        if decision.decision_source is AutomationDecisionSource.HUMAN
    ]
    summary = (await _cluster_summaries(session, viewer, [(cluster, track)]))[0]
    topic_rows = (
        await session.execute(
            select(InterviewDeck.id, InterviewDeck.title, InterviewCard.category)
            .join(InterviewCard, InterviewCard.deck_id == InterviewDeck.id)
            .where(
                InterviewDeck.track_id == cluster.direction_id,
                InterviewDeck.is_published.is_(True),
                InterviewCard.is_published.is_(True),
            )
            .order_by(InterviewDeck.position, InterviewDeck.title, InterviewCard.category)
        )
    ).all()
    topics_by_deck: dict[tuple[UUID, str], dict[str, str]] = {}
    for option_deck_id, deck_title, category in topic_rows:
        topics_by_deck.setdefault((option_deck_id, deck_title), {}).setdefault(
            _normalized_topic_label(category), category
        )
    return QuestionClusterDetail(
        **summary.model_dump(),
        normalized_canonical_question=cluster.normalized_canonical_question,
        representative_occurrence_id=cluster.representative_occurrence_id,
        merged_into_cluster_id=cluster.merged_into_cluster_id,
        parent_cluster_id=cluster.parent_cluster_id,
        question_variants=[
            QuestionClusterVariantRead(
                question_text=value[0],
                normalized_question_text=normalized,
                occurrences_count=value[1],
                first_seen_at=value[2],
                last_seen_at=value[3],
            )
            for normalized, value in sorted(
                variant_stats.items(), key=lambda item: item[1][1], reverse=True
            )
        ],
        companies=[
            QuestionClusterCompanyRead(
                company_id=company_id,
                company_name=company_name,
                occurrences_count=count,
            )
            for (company_id, company_name), count in sorted(
                company_stats.items(), key=lambda item: (-item[1], item[0][1])
            )
        ],
        interviews=[
            QuestionClusterInterviewRead(
                interview_id=interview_id,
                company_id=value[0],
                company_name=value[1],
                interviewed_at=value[2],
                occurrences_count=value[3],
            )
            for interview_id, value in sorted(
                interview_stats.items(), key=lambda item: item[1][2], reverse=True
            )
        ],
        occurrences=occurrences,
        top_card_matches=await _top_card_matches(
            session, cluster, [item.id for item in occurrences]
        ),
        answer_contract=_answer_contract(cluster.answer_contract),
        answer_validation=_answer_validation(cluster.answer_validation),
        answer_status=cluster.answer_status,
        decisions=decision_reads,
        manual_history=manual_history,
        topic_options=[
            QuestionClusterTopicOption(
                deck_id=option_deck_id,
                deck_title=deck_title,
                topics=sorted(categories.values(), key=str.casefold),
            )
            for (option_deck_id, deck_title), categories in topics_by_deck.items()
        ],
        promoted_at=cluster.promoted_at,
        promotion_reason=cluster.promotion_reason,
        membership_revision=cluster.membership_revision,
        stats_revision=cluster.stats_revision,
    )


async def get_question_cluster_allowed_actions(
    session: AsyncSession, viewer: User, cluster_id: UUID
) -> QuestionClusterAllowedActions:
    cluster, _ = await _cluster_row(session, viewer, cluster_id)
    return QuestionClusterAllowedActions(
        cluster_id=cluster.id,
        version=cluster.version,
        actions=_allowed_cluster_actions(cluster, viewer),
    )


async def reprocess_question_occurrence(
    session: AsyncSession,
    viewer: User,
    question_id: UUID,
    payload: QuestionOccurrenceReprocessMutation,
) -> QuestionOccurrenceReprocessResult:
    """Audit and enqueue one explicit, revision-safe occurrence retry."""

    track_ids = await _allowed_track_ids(session, viewer)
    conditions: list[Any] = [
        IntelligenceQuestion.id == question_id,
        IntelligenceQuestion.direction_id.in_(track_ids),
    ]
    if viewer.role is UserRole.MENTOR:
        conditions.append(
            exists(
                select(IntelligenceInterview.id)
                .join(
                    MentorStudent,
                    MentorStudent.student_id == IntelligenceInterview.student_id,
                )
                .where(
                    IntelligenceInterview.id == IntelligenceQuestion.interview_id,
                    MentorStudent.mentor_id == viewer.id,
                )
            )
        )
    question = await session.scalar(
        select(IntelligenceQuestion).where(*conditions).with_for_update()
    )
    if question is None or question.direction_id is None:
        api_error(404, "question_occurrence_not_found", "Question occurrence was not found")
    resolved_question_id = question.id

    idempotency_key = f"manual:occurrence:{question.id}:reprocess:v{payload.expected_revision}"
    existing = await _existing_action_decision(session, idempotency_key)
    if existing is not None:
        if existing.reason != payload.reason or existing.retrieval_scores.get(
            "actor_user_id"
        ) != str(viewer.id):
            api_error(
                409,
                "question_occurrence_reprocess_conflict",
                "This occurrence revision was already reprocessed differently",
            )
        await session.commit()
    else:
        if question.automation_revision != payload.expected_revision:
            api_error(
                409,
                "question_occurrence_revision_conflict",
                "Question occurrence changed; reload it and try again",
            )
        if question.alias_human_confirmed:
            api_error(
                409,
                "question_occurrence_alias_confirmed",
                "A human-confirmed alias cannot be reprocessed without an explicit override",
            )
        if question.moderation_status is not IntelligenceQuestionModerationStatus.PENDING:
            api_error(
                409,
                "question_occurrence_human_moderated",
                "A human-moderated occurrence must be changed through override or reopen",
            )
        settings = await _settings_model(session, question.direction_id)
        decision = await record_automation_decision(
            session,
            entity_type="occurrence",
            entity_id=question.id,
            idempotency_key=idempotency_key,
            decision_type=AutomationDecisionType.OCCURRENCE_REPROCESSED,
            decision_source=AutomationDecisionSource.HUMAN,
            reason=payload.reason,
            confidence=1.0,
            settings=settings,
            selected_card_id=question.published_card_id,
            selected_cluster_id=question.cluster_id,
            retrieval_scores={
                "actor_user_id": str(viewer.id),
                "requested_revision": payload.expected_revision,
                "previous_status": question.automation_status.value,
                "previous_error": question.automation_error,
            },
        )
        decision.reviewed_by_user_id = viewer.id
        decision.reviewed_at = datetime.now(UTC)
        decision.review_result = AutomationReviewResult.CORRECT
        decision.review_reason = payload.reason
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            api_error(
                409,
                "question_occurrence_reprocess_conflict",
                "Question occurrence retry conflicts with another request",
            )

    try:
        job_id = await enqueue_card_automation_job(
            "reprocess_question_occurrence",
            str(resolved_question_id),
            payload.expected_revision,
        )
    except Exception:
        api_error(
            503,
            "question_occurrence_reprocess_queue_unavailable",
            "Retry was audited but the processing queue is temporarily unavailable",
        )
    return QuestionOccurrenceReprocessResult(
        question_id=resolved_question_id,
        revision=payload.expected_revision,
        job_id=job_id,
    )


async def request_question_cluster_answer_generation(
    session: AsyncSession,
    viewer: User,
    cluster_id: UUID,
    payload: QuestionClusterAnswerGenerationMutation,
) -> QuestionClusterAnswerGenerationResult:
    """Queue an explicit AI answer draft request from the moderation screen."""

    _require_admin(viewer)
    cluster, _track = await _cluster_row(session, viewer, cluster_id)
    locked_cluster = await session.scalar(
        select(QuestionCluster)
        .where(QuestionCluster.id == cluster.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked_cluster is None:
        api_error(404, "question_cluster_not_found", "Кластер вопросов не найден")
    cluster = locked_cluster
    if cluster.version != payload.expected_version:
        api_error(
            409,
            "question_cluster_version_conflict",
            "Кластер уже изменился — обновите страницу",
        )
    if cluster.status not in {
        QuestionClusterStatus.SHADOW,
        QuestionClusterStatus.CANDIDATE,
        QuestionClusterStatus.NEEDS_REVIEW,
    }:
        api_error(
            409,
            "question_cluster_answer_generation_unavailable",
            "AI-ответ нельзя сформировать для уже закрытого кластера",
        )
    if cluster.answer_contract is not None:
        api_error(
            409,
            "question_cluster_answer_already_generated",
            "AI-ответ уже сформирован",
        )
    if cluster.answer_status not in {
        None,
        AnswerContractStatus.NEEDS_EXPERT_SOURCE,
    }:
        api_error(
            409,
            "question_cluster_answer_generation_failed",
            "Предыдущая генерация завершилась ошибкой — проверьте технические детали",
        )
    settings = await _settings_model(session, cluster.direction_id)
    analysis_draft = await analysis_answer_draft_for_cluster(session, cluster.id)
    if analysis_draft is not None:
        contract = answer_contract_from_analysis_draft(analysis_draft)
        cluster.answer_contract = contract
        cluster.answer_validation = None
        cluster.answer_status = None
        cluster.version += 1
        await record_automation_decision(
            session,
            entity_type="cluster",
            entity_id=cluster.id,
            idempotency_key=(
                f"cluster:{cluster.id}:analysis-answer-transfer:{cluster.membership_revision}"
            ),
            decision_type=AutomationDecisionType.ANSWER_CONTRACT_GENERATED,
            decision_source=AutomationDecisionSource.RULE,
            reason=(
                "Answer draft transferred from the latest non-rejected AI interview review; "
                "human verification is required"
            ),
            confidence=0.5,
            settings=settings,
            selected_cluster_id=cluster.id,
            judge_result=contract,
        )
        await session.commit()
        return QuestionClusterAnswerGenerationResult(
            cluster_id=cluster.id,
            version=cluster.version,
            job_id=f"analysis-draft:{cluster.id}:v{cluster.version}",
        )
    if not settings.enabled or not settings.cluster_moderation_enabled:
        api_error(
            409,
            "question_cluster_answer_generation_disabled",
            "Включите автоматизацию и модерацию кластеров для этого направления",
        )
    try:
        job_id = await enqueue_card_automation_job(
            "generate_cluster_candidate",
            str(cluster.id),
            cluster.membership_revision,
        )
    except Exception:
        api_error(
            503,
            "question_cluster_answer_generation_queue_unavailable",
            "Не удалось поставить генерацию ответа в очередь",
        )
    return QuestionClusterAnswerGenerationResult(
        cluster_id=cluster.id,
        version=cluster.version,
        job_id=job_id,
    )


def _new_settings(direction_id: UUID) -> CardAutomationSettings:
    return CardAutomationSettings(
        direction_id=direction_id,
        enabled=False,
        shadow_mode=True,
        auto_ignore_noise_enabled=False,
        auto_link_exact_enabled=False,
        auto_link_alias_enabled=False,
        auto_link_semantic_enabled=False,
        semantic_similarity_threshold=0.90,
        pairwise_judge_confidence_threshold=0.92,
        candidate_score_gap_threshold=0.08,
        cluster_match_threshold=0.86,
        min_distinct_interviews_for_promotion=3,
        min_distinct_companies_for_promotion=2,
        min_failed_answers_for_promotion=2,
        audit_sample_percent=5.0,
        personal_review_enabled=False,
        global_auto_publish_enabled=False,
        cluster_moderation_enabled=False,
        legacy_queue_enabled=True,
        version=1,
    )


async def _settings_model(
    session: AsyncSession, direction_id: UUID, *, lock: bool = False
) -> CardAutomationSettings:
    statement = select(CardAutomationSettings).where(
        CardAutomationSettings.direction_id == direction_id
    )
    if lock:
        statement = statement.with_for_update()
    settings = await session.scalar(statement)
    if settings is None:
        settings = _new_settings(direction_id)
        session.add(settings)
        await session.flush()
    return settings


def _settings_read(
    settings: CardAutomationSettings, track: LearningTrack
) -> CardAutomationSettingsRead:
    return CardAutomationSettingsRead(
        direction_id=track.id,
        direction_slug=track.slug,
        direction_title=track.title,
        enabled=settings.enabled,
        shadow_mode=settings.shadow_mode,
        auto_ignore_noise_enabled=settings.auto_ignore_noise_enabled,
        auto_link_exact_enabled=settings.auto_link_exact_enabled,
        auto_link_alias_enabled=settings.auto_link_alias_enabled,
        auto_link_semantic_enabled=settings.auto_link_semantic_enabled,
        semantic_similarity_threshold=settings.semantic_similarity_threshold,
        pairwise_judge_confidence_threshold=settings.pairwise_judge_confidence_threshold,
        candidate_score_gap_threshold=settings.candidate_score_gap_threshold,
        cluster_match_threshold=settings.cluster_match_threshold,
        min_distinct_interviews_for_promotion=settings.min_distinct_interviews_for_promotion,
        min_distinct_companies_for_promotion=settings.min_distinct_companies_for_promotion,
        min_failed_answers_for_promotion=settings.min_failed_answers_for_promotion,
        audit_sample_percent=settings.audit_sample_percent,
        personal_review_enabled=settings.personal_review_enabled,
        global_auto_publish_enabled=settings.global_auto_publish_enabled,
        cluster_moderation_enabled=settings.cluster_moderation_enabled,
        legacy_queue_enabled=settings.legacy_queue_enabled,
        version=settings.version,
        updated_at=settings.updated_at,
    )


async def list_card_automation_settings(
    session: AsyncSession, viewer: User
) -> CardAutomationSettingsList:
    _require_admin(viewer)
    track_ids = await _allowed_track_ids(session, viewer)
    tracks = list(
        await session.scalars(
            select(LearningTrack)
            .where(LearningTrack.id.in_(track_ids))
            .order_by(LearningTrack.position, LearningTrack.title)
        )
    )
    settings_rows = list(
        await session.scalars(
            select(CardAutomationSettings).where(
                CardAutomationSettings.direction_id.in_([track.id for track in tracks])
            )
        )
    )
    settings_by_track = {item.direction_id: item for item in settings_rows}
    created = False
    for track in tracks:
        if track.id not in settings_by_track:
            settings = _new_settings(track.id)
            session.add(settings)
            settings_by_track[track.id] = settings
            created = True
    if created:
        await session.commit()
    return CardAutomationSettingsList(
        items=[_settings_read(settings_by_track[track.id], track) for track in tracks]
    )


async def update_card_automation_settings(
    session: AsyncSession,
    viewer: User,
    payload: CardAutomationSettingsUpdate,
    idempotency_key: str,
) -> CardAutomationSettingsRead:
    _require_admin(viewer)
    track = await session.get(LearningTrack, payload.direction_id, with_for_update=True)
    if track is None:
        api_error(404, "learning_track_not_found", "Learning track was not found")
    settings = await _settings_model(session, track.id, lock=True)
    payload_fingerprint = hashlib.sha256(
        json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    request_fingerprint = hashlib.sha256(idempotency_key.encode()).hexdigest()
    decision_key = (
        f"manual:settings:{track.id}:v{payload.expected_version}:"
        f"{request_fingerprint[:16]}:{payload_fingerprint[:16]}"
    )
    existing = await _existing_action_decision(session, decision_key)
    if existing is not None:
        if existing.retrieval_scores.get("after") != _settings_audit_values(settings):
            api_error(
                409,
                "card_automation_idempotency_result_superseded",
                "The idempotent settings result has since been superseded",
            )
        return _settings_read(settings, track)
    if settings.version != payload.expected_version:
        api_error(
            409,
            "card_automation_version_conflict",
            "Automation settings changed; reload them and try again",
        )
    before = _settings_audit_values(settings)
    settings.enabled = payload.enabled
    settings.shadow_mode = payload.shadow_mode
    settings.auto_ignore_noise_enabled = payload.auto_ignore_noise_enabled
    settings.auto_link_exact_enabled = payload.auto_link_exact_enabled
    settings.auto_link_alias_enabled = payload.auto_link_alias_enabled
    settings.auto_link_semantic_enabled = payload.auto_link_semantic_enabled
    settings.semantic_similarity_threshold = payload.semantic_similarity_threshold
    settings.pairwise_judge_confidence_threshold = payload.pairwise_judge_confidence_threshold
    settings.candidate_score_gap_threshold = payload.candidate_score_gap_threshold
    settings.cluster_match_threshold = payload.cluster_match_threshold
    settings.min_distinct_interviews_for_promotion = payload.min_distinct_interviews_for_promotion
    settings.min_distinct_companies_for_promotion = payload.min_distinct_companies_for_promotion
    settings.min_failed_answers_for_promotion = payload.min_failed_answers_for_promotion
    settings.audit_sample_percent = payload.audit_sample_percent
    settings.personal_review_enabled = payload.personal_review_enabled
    settings.global_auto_publish_enabled = False
    settings.cluster_moderation_enabled = payload.cluster_moderation_enabled
    settings.legacy_queue_enabled = payload.legacy_queue_enabled
    settings.version += 1
    after = _settings_audit_values(settings)
    decision = await record_automation_decision(
        session,
        entity_type="settings",
        entity_id=track.id,
        idempotency_key=decision_key,
        decision_type=AutomationDecisionType.MANUAL_OVERRIDE,
        decision_source=AutomationDecisionSource.HUMAN,
        reason="Administrator updated card automation settings",
        confidence=1.0,
        settings=settings,
        retrieval_scores={
            "actor_user_id": str(viewer.id),
            "request_fingerprint": request_fingerprint,
            "payload_fingerprint": payload_fingerprint,
            "before": before,
            "after": after,
        },
    )
    decision.reviewed_by_user_id = viewer.id
    decision.reviewed_at = datetime.now(UTC)
    decision.review_result = AutomationReviewResult.CORRECT
    decision.review_reason = decision.reason
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        api_error(409, "card_automation_settings_conflict", "Automation settings conflict")
    await session.refresh(settings)
    return _settings_read(settings, track)


def _settings_audit_values(settings: CardAutomationSettings) -> dict[str, object]:
    return {
        "enabled": settings.enabled,
        "shadow_mode": settings.shadow_mode,
        "auto_ignore_noise_enabled": settings.auto_ignore_noise_enabled,
        "auto_link_exact_enabled": settings.auto_link_exact_enabled,
        "auto_link_alias_enabled": settings.auto_link_alias_enabled,
        "auto_link_semantic_enabled": settings.auto_link_semantic_enabled,
        "semantic_similarity_threshold": settings.semantic_similarity_threshold,
        "pairwise_judge_confidence_threshold": (settings.pairwise_judge_confidence_threshold),
        "candidate_score_gap_threshold": settings.candidate_score_gap_threshold,
        "cluster_match_threshold": settings.cluster_match_threshold,
        "min_distinct_interviews_for_promotion": (settings.min_distinct_interviews_for_promotion),
        "min_distinct_companies_for_promotion": settings.min_distinct_companies_for_promotion,
        "min_failed_answers_for_promotion": settings.min_failed_answers_for_promotion,
        "audit_sample_percent": settings.audit_sample_percent,
        "personal_review_enabled": settings.personal_review_enabled,
        "global_auto_publish_enabled": settings.global_auto_publish_enabled,
        "cluster_moderation_enabled": settings.cluster_moderation_enabled,
        "legacy_queue_enabled": settings.legacy_queue_enabled,
        "version": settings.version,
    }


def _action_key(
    cluster_id: UUID,
    action: str,
    expected_version: int,
    *parts: object,
) -> str:
    base = f"manual:cluster:{cluster_id}:{action}:v{expected_version}"
    if not parts:
        return base
    fingerprint = hashlib.sha256()
    for part in parts:
        fingerprint.update(str(part).encode())
        fingerprint.update(b"\0")
    return f"{base}:{fingerprint.hexdigest()[:20]}"


async def _existing_action_decision(
    session: AsyncSession, idempotency_key: str
) -> AutomationDecision | None:
    return cast(
        AutomationDecision | None,
        await session.scalar(
            select(AutomationDecision).where(AutomationDecision.idempotency_key == idempotency_key)
        ),
    )


def _outcome_from_decision(cluster_id: UUID, decision: AutomationDecision) -> _ActionOutcome:
    affected = _uuid_list(decision.retrieval_scores.get("affected_cluster_ids"))
    if cluster_id not in affected:
        affected.insert(0, cluster_id)
    created_card_id = (
        decision.selected_card_id
        if decision.decision_type is AutomationDecisionType.CARD_CREATED
        else None
    )
    return _ActionOutcome(
        cluster_id=cluster_id,
        decision_id=decision.id,
        created_card_id=created_card_id,
        affected_cluster_ids=tuple(affected),
    )


async def _prepare_cluster_action(
    session: AsyncSession,
    viewer: User,
    cluster_id: UUID,
    expected_version: int,
    idempotency_key: str,
) -> tuple[QuestionCluster, CardAutomationSettings, AutomationDecision | None]:
    cluster, _ = await _cluster_row(session, viewer, cluster_id, lock=True)
    existing = await _existing_action_decision(session, idempotency_key)
    if existing is not None:
        return cluster, await _settings_model(session, cluster.direction_id), existing
    if cluster.version != expected_version:
        api_error(
            409,
            "question_cluster_version_conflict",
            "Question cluster changed; reload it and try again",
        )
    return cluster, await _settings_model(session, cluster.direction_id), None


def _ensure_action_allowed(cluster: QuestionCluster, action: QuestionClusterAction) -> None:
    if action.value not in cluster_allowed_actions(cluster.status):
        api_error(
            409,
            "question_cluster_action_not_allowed",
            f"Action {action.value} is not allowed for cluster status {cluster.status.value}",
        )


async def _record_cluster_decision(
    session: AsyncSession,
    *,
    cluster: QuestionCluster,
    settings: CardAutomationSettings,
    idempotency_key: str,
    decision_type: AutomationDecisionType,
    reason: str,
    viewer: User,
    selected_card_id: UUID | None = None,
    selected_cluster_id: UUID | None = None,
    candidate_card_ids: list[UUID] | None = None,
    candidate_cluster_ids: list[UUID] | None = None,
    retrieval_scores: dict[str, object] | None = None,
) -> AutomationDecision:
    changes = dict(retrieval_scores or {})
    changes.setdefault("actor_user_id", str(viewer.id))
    decision = await record_automation_decision(
        session,
        entity_type="cluster",
        entity_id=cluster.id,
        idempotency_key=idempotency_key,
        decision_type=decision_type,
        decision_source=AutomationDecisionSource.HUMAN,
        reason=reason,
        confidence=1.0,
        settings=settings,
        selected_card_id=selected_card_id,
        selected_cluster_id=selected_cluster_id,
        candidate_card_ids=candidate_card_ids,
        candidate_cluster_ids=candidate_cluster_ids,
        retrieval_scores=changes,
    )
    decision.reviewed_by_user_id = viewer.id
    decision.reviewed_at = datetime.now(UTC)
    decision.review_result = AutomationReviewResult.CORRECT
    decision.review_reason = reason
    await session.flush()
    return decision


async def _questions_in_cluster(
    session: AsyncSession, cluster_id: UUID, *, lock: bool = False
) -> list[IntelligenceQuestion]:
    statement = select(IntelligenceQuestion).where(IntelligenceQuestion.cluster_id == cluster_id)
    if lock:
        statement = statement.with_for_update()
    return list(await session.scalars(statement.order_by(IntelligenceQuestion.id)))


async def _unlink_occurrence_card(
    session: AsyncSession, question: IntelligenceQuestion
) -> UUID | None:
    old_card_id = question.published_card_id
    if old_card_id is None:
        return None
    await session.execute(
        delete(InterviewCardOccurrence).where(
            InterviewCardOccurrence.source_question_id == question.id
        )
    )
    question.published_card_id = None
    question.alias_human_confirmed = False
    return old_card_id


async def _refresh_card_stats(session: AsyncSession, card_ids: Iterable[UUID]) -> None:
    for card_id in set(card_ids):
        card = await session.get(InterviewCard, card_id, with_for_update=True)
        if card is None:
            continue
        card.asked_count = int(
            await session.scalar(
                select(func.count(InterviewCardOccurrence.id)).where(
                    InterviewCardOccurrence.card_id == card.id
                )
            )
            or 0
        )
        company_names = list(
            await session.scalars(
                select(InterviewCardOccurrence.company_name)
                .where(InterviewCardOccurrence.card_id == card.id)
                .distinct()
                .order_by(InterviewCardOccurrence.company_name)
            )
        )
        card.companies = ", ".join(company_names) or None
        refresh_card_frequency(card)


@dataclass(frozen=True, slots=True)
class _DuplicateCardContext:
    card: InterviewCard
    deck: InterviewDeck
    track: LearningTrack
    aliases: tuple[IntelligenceQuestion, ...] = ()


# The duplicate queue is an interactive moderation tool, so candidate retrieval
# must remain bounded.  The former implementation ran the expensive matcher for
# every possible pair (N²) before applying pagination and could monopolise the
# only ASGI event loop on production.
_DUPLICATE_RETRIEVAL_TERMS_PER_CARD = 12
_DUPLICATE_RETRIEVAL_CANDIDATES_PER_CARD = 64
_DUPLICATE_RETRIEVAL_POSTING_SCAN = 192
_DUPLICATE_RETRIEVAL_POSTING_NEIGHBOURS = 24


def _ordered_card_ids(left_card_id: UUID, right_card_id: UUID) -> tuple[UUID, UUID]:
    left, right = sorted((left_card_id, right_card_id), key=str)
    return left, right


def _duplicate_pair_key(left_card_id: UUID, right_card_id: UUID) -> str:
    left, right = _ordered_card_ids(left_card_id, right_card_id)
    return f"{left}:{right}"


def _compatible_embedding(
    query: InterviewCard,
    embedding: Sequence[float] | None,
    model: str | None,
    dimensions: int | None,
) -> tuple[float, ...] | None:
    if (
        query.question_embedding is None
        or query.question_embedding_model is None
        or query.question_embedding_dimensions is None
        or embedding is None
        or model != query.question_embedding_model
        or dimensions != query.question_embedding_dimensions
    ):
        return None
    return tuple(embedding)


def _candidate_for_duplicate(
    query: InterviewCard, target: _DuplicateCardContext
) -> QuestionCandidate:
    variants = [
        QuestionVariant(
            text=target.card.question_markdown,
            embedding=_compatible_embedding(
                query,
                target.card.question_embedding,
                target.card.question_embedding_model,
                target.card.question_embedding_dimensions,
            ),
            source="card",
        )
    ]
    variants.extend(
        QuestionVariant(
            text=alias.question_text,
            embedding=_compatible_embedding(
                query,
                alias.question_embedding,
                alias.question_embedding_model,
                alias.question_embedding_dimensions,
            ),
            source="approved_alias",
        )
        for alias in target.aliases
    )
    return QuestionCandidate(
        card_id=target.card.id,
        asked_count=target.card.asked_count,
        variants=tuple(variants),
    )


def _duplicate_pair_match(
    left: _DuplicateCardContext, right: _DuplicateCardContext
) -> RankedQuestionCandidate | None:
    matches = rank_question_candidates(
        left.card.question_markdown,
        tuple(left.card.question_embedding) if left.card.question_embedding else None,
        [_candidate_for_duplicate(left.card, right)],
        limit=1,
    )
    reverse_matches = rank_question_candidates(
        right.card.question_markdown,
        tuple(right.card.question_embedding) if right.card.question_embedding else None,
        [_candidate_for_duplicate(right.card, left)],
        limit=1,
    )
    candidates = [*matches, *reverse_matches]
    return max(candidates, key=lambda item: item.similarity, default=None)


def _duplicate_context_variants(context: _DuplicateCardContext) -> tuple[str, ...]:
    return (context.card.question_markdown, *(alias.question_text for alias in context.aliases))


def _bounded_posting_candidates(
    posting: Sequence[UUID],
    *,
    card_id: UUID,
    position_by_id: dict[UUID, int],
    popular_ids: Sequence[UUID],
) -> set[UUID]:
    if len(posting) <= _DUPLICATE_RETRIEVAL_POSTING_SCAN:
        return set(posting)

    position = position_by_id[card_id]
    radius = _DUPLICATE_RETRIEVAL_POSTING_NEIGHBOURS
    start = max(0, position - radius)
    end = min(len(posting), position + radius + 1)
    return {*posting[start:end], *popular_ids}


def _duplicate_candidate_pairs(
    contexts: Sequence[_DuplicateCardContext],
) -> set[tuple[UUID, UUID]]:
    """Build a bounded lexical shortlist before running the expensive matcher."""

    contexts_by_id = {context.card.id: context for context in contexts}
    terms_by_id: dict[UUID, frozenset[str]] = {}
    normalized_variants: defaultdict[tuple[UUID, str], list[UUID]] = defaultdict(list)
    postings: defaultdict[tuple[UUID, str], list[UUID]] = defaultdict(list)

    for context in contexts:
        variants = _duplicate_context_variants(context)
        terms = frozenset(
            term for variant in variants for term in question_retrieval_terms(variant)
        )
        terms_by_id[context.card.id] = terms
        for variant in variants:
            normalized = normalize_question(variant)
            if normalized:
                normalized_variants[(context.track.id, normalized)].append(context.card.id)
        for term in terms:
            postings[(context.track.id, term)].append(context.card.id)

    posting_positions: dict[tuple[UUID, str], dict[UUID, int]] = {}
    posting_popular: dict[tuple[UUID, str], tuple[UUID, ...]] = {}
    for key, card_ids in postings.items():
        card_ids.sort(
            key=lambda card_id: (
                normalize_question(contexts_by_id[card_id].card.question_markdown),
                str(card_id),
            )
        )
        posting_positions[key] = {
            posting_card_id: index for index, posting_card_id in enumerate(card_ids)
        }
        posting_popular[key] = tuple(
            sorted(
                card_ids,
                key=lambda candidate_id: (
                    -contexts_by_id[candidate_id].card.asked_count,
                    str(candidate_id),
                ),
            )[:_DUPLICATE_RETRIEVAL_POSTING_NEIGHBOURS]
        )

    pairs: set[tuple[UUID, UUID]] = set()
    # Never lose exact matches, even when their wording has no useful terms.
    for card_ids in normalized_variants.values():
        unique_ids = set(card_ids)
        if len(unique_ids) < 2:
            continue
        anchor_id = min(
            unique_ids,
            key=lambda candidate_id: (
                -contexts_by_id[candidate_id].card.asked_count,
                str(candidate_id),
            ),
        )
        pairs.update(
            _ordered_card_ids(anchor_id, candidate_id)
            for candidate_id in unique_ids
            if candidate_id != anchor_id
        )

    for context in contexts:
        card_id = context.card.id
        ranked_terms = sorted(
            terms_by_id[card_id],
            key=lambda term: (len(postings[(context.track.id, term)]), term),
        )[:_DUPLICATE_RETRIEVAL_TERMS_PER_CARD]
        shared_term_counts: defaultdict[UUID, int] = defaultdict(int)
        for term in ranked_terms:
            key = (context.track.id, term)
            for candidate_id in _bounded_posting_candidates(
                postings[key],
                card_id=card_id,
                position_by_id=posting_positions[key],
                popular_ids=posting_popular[key],
            ):
                if candidate_id != card_id:
                    shared_term_counts[candidate_id] += 1

        candidates = sorted(
            shared_term_counts,
            key=lambda candidate_id: (
                -shared_term_counts[candidate_id],
                -contexts_by_id[candidate_id].card.asked_count,
                str(candidate_id),
            ),
        )[:_DUPLICATE_RETRIEVAL_CANDIDATES_PER_CARD]
        pairs.update(_ordered_card_ids(card_id, candidate_id) for candidate_id in candidates)
    return pairs


def _rank_duplicate_pairs(
    contexts: Sequence[_DuplicateCardContext],
    reviewed_pairs: set[tuple[UUID, UUID]],
    minimum_similarity: float,
) -> list[InterviewCardDuplicateCandidateRead]:
    contexts_by_id = {context.card.id: context for context in contexts}
    candidates: list[InterviewCardDuplicateCandidateRead] = []
    for pair_ids in _duplicate_candidate_pairs(contexts):
        if pair_ids in reviewed_pairs:
            continue
        left = contexts_by_id[pair_ids[0]]
        right = contexts_by_id[pair_ids[1]]
        match = _duplicate_pair_match(left, right)
        if match is None or match.similarity < minimum_similarity:
            continue
        candidates.append(
            InterviewCardDuplicateCandidateRead(
                pair_key=_duplicate_pair_key(*pair_ids),
                similarity=match.similarity,
                matched_source=match.matched_source,
                matched_text=match.matched_text,
                left=_duplicate_card_read(left),
                right=_duplicate_card_read(right),
            )
        )
    candidates.sort(
        key=lambda item: (
            -item.similarity,
            -(item.left.asked_count + item.right.asked_count),
            item.pair_key,
        )
    )
    return candidates


async def _load_duplicate_card_contexts(
    session: AsyncSession,
    *,
    card_ids: Sequence[UUID] | None = None,
    direction_id: UUID | None = None,
    lock: bool = False,
) -> list[_DuplicateCardContext]:
    statement = (
        select(InterviewCard, InterviewDeck, LearningTrack)
        .join(InterviewDeck, InterviewDeck.id == InterviewCard.deck_id)
        .join(LearningTrack, LearningTrack.id == InterviewDeck.track_id)
        .where(InterviewCard.is_published.is_(True))
        .order_by(LearningTrack.position, InterviewCard.id)
    )
    if card_ids is not None:
        statement = statement.where(InterviewCard.id.in_(card_ids))
    if direction_id is not None:
        statement = statement.where(LearningTrack.id == direction_id)
    if lock:
        statement = statement.with_for_update(of=InterviewCard)
    rows = list((await session.execute(statement)).tuples())
    loaded_ids = [card.id for card, _, _ in rows]
    aliases_by_card: defaultdict[UUID, list[IntelligenceQuestion]] = defaultdict(list)
    if loaded_ids:
        aliases = list(
            await session.scalars(
                select(IntelligenceQuestion).where(
                    IntelligenceQuestion.published_card_id.in_(loaded_ids),
                    IntelligenceQuestion.alias_human_confirmed.is_(True),
                )
            )
        )
        for alias in aliases:
            if alias.published_card_id is not None:
                aliases_by_card[alias.published_card_id].append(alias)
    return [
        _DuplicateCardContext(
            card=card,
            deck=deck,
            track=track,
            aliases=tuple(aliases_by_card[card.id]),
        )
        for card, deck, track in rows
    ]


def _duplicate_card_read(context: _DuplicateCardContext) -> InterviewCardDuplicateCardRead:
    card = context.card
    return InterviewCardDuplicateCardRead(
        id=card.id,
        deck_id=context.deck.id,
        deck_title=context.deck.title,
        direction_id=context.track.id,
        direction_slug=context.track.slug,
        direction_title=context.track.title,
        category=card.category,
        subcategory=card.subcategory,
        question_markdown=card.question_markdown,
        answer_markdown=card.answer_markdown,
        companies=card.companies,
        asked_count=card.asked_count,
        frequency=card.frequency,
        updated_at=card.updated_at,
    )


async def list_interview_card_duplicates(
    session: AsyncSession,
    *,
    direction_id: UUID | None,
    minimum_similarity: float,
    limit: int,
    offset: int,
) -> InterviewCardDuplicatePage:
    contexts = await _load_duplicate_card_contexts(session, direction_id=direction_id)
    reviewed_pairs = set(
        (
            await session.execute(
                select(
                    InterviewCardDuplicateReview.left_card_id,
                    InterviewCardDuplicateReview.right_card_id,
                )
            )
        ).tuples()
    )
    # Matching is CPU-bound. Keep it off the asyncio event loop so unrelated
    # requests such as /api/v1/me remain responsive while the queue is built.
    candidates = await asyncio.to_thread(
        _rank_duplicate_pairs,
        contexts,
        reviewed_pairs,
        minimum_similarity,
    )
    total = len(candidates)
    return InterviewCardDuplicatePage(
        items=candidates[offset : offset + limit],
        total=total,
        limit=limit,
        offset=offset,
    )


def _card_snapshot(context: _DuplicateCardContext) -> dict[str, object]:
    card = context.card
    return {
        "id": str(card.id),
        "deck_id": str(card.deck_id),
        "deck_title": context.deck.title,
        "direction_id": str(context.track.id),
        "direction_slug": context.track.slug,
        "slug": card.slug,
        "category": card.category,
        "subcategory": card.subcategory,
        "question_markdown": card.question_markdown,
        "answer_markdown": card.answer_markdown,
        "companies": card.companies,
        "asked_count": card.asked_count,
        "frequency": card.frequency.value,
        "updated_at": card.updated_at.isoformat(),
    }


def _assert_duplicate_payload_is_current(
    payload: InterviewCardDuplicateMutation,
    contexts: dict[UUID, _DuplicateCardContext],
) -> None:
    left = contexts.get(payload.left_card_id)
    right = contexts.get(payload.right_card_id)
    if left is None or right is None:
        api_error(404, "interview_card_not_found", "One of the cards was not found")
    if left.track.id != right.track.id:
        api_error(422, "different_card_directions", "Cards from different directions cannot merge")
    if (
        left.card.updated_at != payload.expected_left_updated_at
        or right.card.updated_at != payload.expected_right_updated_at
    ):
        api_error(
            409,
            "interview_card_changed",
            "One of the cards changed; reload the duplicate list and review it again",
        )


async def _reviewed_duplicate_pair(
    session: AsyncSession, left_card_id: UUID, right_card_id: UUID
) -> InterviewCardDuplicateReview | None:
    left, right = _ordered_card_ids(left_card_id, right_card_id)
    return cast(
        InterviewCardDuplicateReview | None,
        await session.scalar(
            select(InterviewCardDuplicateReview).where(
                InterviewCardDuplicateReview.left_card_id == left,
                InterviewCardDuplicateReview.right_card_id == right,
            )
        )
    )


async def dismiss_interview_card_duplicate(
    session: AsyncSession,
    admin: User,
    payload: InterviewCardDuplicateMutation,
) -> InterviewCardDuplicateReviewResult:
    _require_admin(admin)
    contexts_list = await _load_duplicate_card_contexts(
        session,
        card_ids=[payload.left_card_id, payload.right_card_id],
        lock=True,
    )
    contexts = {item.card.id: item for item in contexts_list}
    _assert_duplicate_payload_is_current(payload, contexts)
    existing = await _reviewed_duplicate_pair(session, payload.left_card_id, payload.right_card_id)
    if existing is not None:
        api_error(409, "duplicate_pair_reviewed", "This pair has already been reviewed")
    left_id, right_id = _ordered_card_ids(payload.left_card_id, payload.right_card_id)
    left = contexts[left_id]
    right = contexts[right_id]
    match = _duplicate_pair_match(left, right)
    review = InterviewCardDuplicateReview(
        left_card_id=left_id,
        right_card_id=right_id,
        primary_card_id=None,
        decision="not_duplicate",
        similarity=match.similarity if match is not None else 0.0,
        reason=payload.reason,
        left_snapshot=_card_snapshot(left),
        right_snapshot=_card_snapshot(right),
        merge_summary=None,
        reviewed_by_user_id=admin.id,
    )
    session.add(review)
    await session.commit()
    return InterviewCardDuplicateReviewResult(
        review_id=review.id,
        decision="not_duplicate",
    )


def _max_datetime(*values: datetime | None) -> datetime | None:
    present = [value for value in values if value is not None]
    return max(present, default=None)


def _min_datetime(*values: datetime | None) -> datetime | None:
    present = [value for value in values if value is not None]
    return min(present, default=None)


async def _merge_card_progress(
    session: AsyncSession, source: InterviewCard, target: InterviewCard
) -> int:
    source_progress = list(
        await session.scalars(
            select(InterviewCardProgress)
            .where(InterviewCardProgress.card_id == source.id)
            .with_for_update()
        )
    )
    for progress in source_progress:
        target_progress = await session.get(
            InterviewCardProgress,
            {"user_id": progress.user_id, "card_id": target.id},
            with_for_update=True,
        )
        if target_progress is None:
            session.add(
                InterviewCardProgress(
                    user_id=progress.user_id,
                    card_id=target.id,
                    repetitions=progress.repetitions,
                    interval_days=progress.interval_days,
                    ease_factor=progress.ease_factor,
                    lapses=progress.lapses,
                    due_at=progress.due_at,
                    first_learned_at=progress.first_learned_at,
                    last_reviewed_at=progress.last_reviewed_at,
                    last_rating=progress.last_rating,
                )
            )
        else:
            source_is_latest = (
                progress.last_reviewed_at is not None
                and (
                    target_progress.last_reviewed_at is None
                    or progress.last_reviewed_at > target_progress.last_reviewed_at
                )
            )
            if source_is_latest:
                target_progress.last_rating = progress.last_rating
            target_progress.repetitions = max(
                target_progress.repetitions, progress.repetitions
            )
            target_progress.interval_days = max(
                target_progress.interval_days, progress.interval_days
            )
            target_progress.ease_factor = max(
                target_progress.ease_factor, progress.ease_factor
            )
            target_progress.lapses = max(target_progress.lapses, progress.lapses)
            target_progress.due_at = max(target_progress.due_at, progress.due_at)
            target_progress.first_learned_at = _min_datetime(
                target_progress.first_learned_at, progress.first_learned_at
            )
            target_progress.last_reviewed_at = _max_datetime(
                target_progress.last_reviewed_at, progress.last_reviewed_at
            )
        await session.delete(progress)
    return len(source_progress)


async def _preserve_topic_access(
    session: AsyncSession, source: InterviewCard, target: InterviewCard
) -> int:
    if source.deck_id == target.deck_id and source.category == target.category:
        return 0
    selections = list(
        await session.scalars(
            select(InterviewTopicSelection).where(
                InterviewTopicSelection.deck_id == source.deck_id,
                InterviewTopicSelection.category == source.category,
            )
        )
    )
    created = 0
    for selection in selections:
        target_key = {
            "user_id": selection.user_id,
            "deck_id": target.deck_id,
            "category": target.category,
        }
        if await session.get(InterviewTopicSelection, target_key) is None:
            session.add(InterviewTopicSelection(**target_key))
            created += 1
    return created


async def merge_interview_card_duplicate(
    session: AsyncSession,
    admin: User,
    payload: InterviewCardDuplicateMergeMutation,
) -> InterviewCardDuplicateReviewResult:
    _require_admin(admin)
    contexts_list = await _load_duplicate_card_contexts(
        session,
        card_ids=[payload.left_card_id, payload.right_card_id],
        lock=True,
    )
    contexts = {item.card.id: item for item in contexts_list}
    _assert_duplicate_payload_is_current(payload, contexts)
    existing = await _reviewed_duplicate_pair(session, payload.left_card_id, payload.right_card_id)
    if existing is not None:
        api_error(409, "duplicate_pair_reviewed", "This pair has already been reviewed")

    primary = contexts[payload.primary_card_id]
    source_id = (
        payload.right_card_id
        if payload.primary_card_id == payload.left_card_id
        else payload.left_card_id
    )
    source = contexts[source_id]
    left_id, right_id = _ordered_card_ids(payload.left_card_id, payload.right_card_id)
    left_snapshot = _card_snapshot(contexts[left_id])
    right_snapshot = _card_snapshot(contexts[right_id])
    match = _duplicate_pair_match(contexts[left_id], contexts[right_id])

    target_interview_ids = set(
        await session.scalars(
            select(InterviewCardOccurrence.interview_id).where(
                InterviewCardOccurrence.card_id == primary.card.id,
                InterviewCardOccurrence.interview_id.is_not(None),
            )
        )
    )
    source_occurrences = list(
        await session.scalars(
            select(InterviewCardOccurrence)
            .where(InterviewCardOccurrence.card_id == source.card.id)
            .with_for_update()
        )
    )
    moved_occurrences = 0
    deduplicated_occurrences = 0
    for occurrence in source_occurrences:
        if occurrence.interview_id is not None and occurrence.interview_id in target_interview_ids:
            await session.delete(occurrence)
            deduplicated_occurrences += 1
        else:
            occurrence.card_id = primary.card.id
            moved_occurrences += 1

    questions = list(
        await session.scalars(
            select(IntelligenceQuestion)
            .where(IntelligenceQuestion.published_card_id == source.card.id)
            .with_for_update()
        )
    )
    for question in questions:
        question.published_card_id = primary.card.id

    clusters = list(
        await session.scalars(
            select(QuestionCluster)
            .where(QuestionCluster.linked_card_id == source.card.id)
            .with_for_update()
        )
    )
    for cluster in clusters:
        cluster.linked_card_id = primary.card.id
        cluster.version += 1

    decisions = list(
        await session.scalars(
            select(AutomationDecision)
            .where(
                or_(
                    AutomationDecision.selected_card_id == source.card.id,
                    AutomationDecision.candidate_card_ids.contains([str(source.card.id)]),
                )
            )
            .with_for_update()
        )
    )
    source_key = str(source.card.id)
    target_key = str(primary.card.id)
    for decision in decisions:
        if decision.selected_card_id == source.card.id:
            decision.selected_card_id = primary.card.id
        replaced_ids = [
            target_key if str(card_id) == source_key else str(card_id)
            for card_id in decision.candidate_card_ids
        ]
        decision.candidate_card_ids = list(dict.fromkeys(replaced_ids))
        retrieval_scores = dict(decision.retrieval_scores)
        source_score = retrieval_scores.pop(source_key, None)
        if source_score is not None and target_key not in retrieval_scores:
            retrieval_scores[target_key] = source_score
        decision.retrieval_scores = retrieval_scores

    personal_items = list(
        await session.scalars(
            select(PersonalReviewItem)
            .where(
                or_(
                    PersonalReviewItem.canonical_card_id == source.card.id,
                    PersonalReviewItem.replaced_by_card_id == source.card.id,
                )
            )
            .with_for_update()
        )
    )
    for item in personal_items:
        if item.canonical_card_id == source.card.id:
            item.canonical_card_id = primary.card.id
        if item.replaced_by_card_id == source.card.id:
            item.replaced_by_card_id = primary.card.id
        item.version += 1

    merged_progress_records = await _merge_card_progress(
        session, source.card, primary.card
    )
    preserved_topic_selections = await _preserve_topic_access(
        session, source.card, primary.card
    )
    source.card.is_published = False
    await session.flush()
    await _refresh_card_stats(session, [source.card.id, primary.card.id])

    merge_summary: dict[str, object] = {
        "archived_card_id": str(source.card.id),
        "moved_occurrences": moved_occurrences,
        "deduplicated_occurrences": deduplicated_occurrences,
        "updated_questions": len(questions),
        "updated_clusters": len(clusters),
        "updated_decisions": len(decisions),
        "updated_personal_review_items": len(personal_items),
        "merged_progress_records": merged_progress_records,
        "preserved_topic_selections": preserved_topic_selections,
    }
    review = InterviewCardDuplicateReview(
        left_card_id=left_id,
        right_card_id=right_id,
        primary_card_id=primary.card.id,
        decision="merged",
        similarity=match.similarity if match is not None else 0.0,
        reason=payload.reason,
        left_snapshot=left_snapshot,
        right_snapshot=right_snapshot,
        merge_summary=merge_summary,
        reviewed_by_user_id=admin.id,
    )
    session.add(review)
    await session.commit()
    return InterviewCardDuplicateReviewResult(
        review_id=review.id,
        decision="merged",
        primary_card_id=primary.card.id,
        archived_card_id=source.card.id,
        moved_occurrences=moved_occurrences,
        deduplicated_occurrences=deduplicated_occurrences,
        merged_progress_records=merged_progress_records,
    )


async def _card_in_direction(
    session: AsyncSession, card_id: UUID, direction_id: UUID
) -> InterviewCard:
    card = await session.scalar(
        select(InterviewCard)
        .join(InterviewDeck, InterviewDeck.id == InterviewCard.deck_id)
        .where(InterviewCard.id == card_id, InterviewDeck.track_id == direction_id)
        .with_for_update(of=InterviewCard)
    )
    if card is None:
        api_error(404, "interview_card_not_found", "Interview card was not found")
    return card


async def _replace_personal_items(
    session: AsyncSession, occurrence_ids: Sequence[UUID], card_id: UUID
) -> None:
    if not occurrence_ids:
        return
    items = list(
        await session.scalars(
            select(PersonalReviewItem)
            .where(PersonalReviewItem.source_occurrence_id.in_(occurrence_ids))
            .with_for_update()
        )
    )
    for item in items:
        if (
            item.status is PersonalReviewStatus.REPLACED_BY_CANONICAL_CARD
            and item.replaced_by_card_id == card_id
        ):
            continue
        item.canonical_card_id = card_id
        item.replaced_by_card_id = card_id
        item.status = PersonalReviewStatus.REPLACED_BY_CANONICAL_CARD
        item.version += 1


async def _reactivate_personal_items(session: AsyncSession, occurrence_ids: Sequence[UUID]) -> None:
    if not occurrence_ids:
        return
    items = list(
        await session.scalars(
            select(PersonalReviewItem)
            .where(
                PersonalReviewItem.source_occurrence_id.in_(occurrence_ids),
                PersonalReviewItem.status == PersonalReviewStatus.REPLACED_BY_CANONICAL_CARD,
            )
            .with_for_update()
        )
    )
    now = datetime.now(UTC)
    for item in items:
        item.canonical_card_id = None
        item.replaced_by_card_id = None
        item.status = PersonalReviewStatus.ACTIVE
        item.due_at = now
        item.version += 1


async def _apply_cluster_card_link(
    session: AsyncSession,
    viewer: User,
    cluster: QuestionCluster,
    card: InterviewCard,
    settings: CardAutomationSettings,
    *,
    reason: str,
    confirm_alias: bool,
) -> list[UUID]:
    questions = await _questions_in_cluster(session, cluster.id, lock=True)
    old_card_ids: list[UUID] = []
    now = datetime.now(UTC)
    for question in questions:
        if question.published_card_id is not None and question.published_card_id != card.id:
            old_card_id = await _unlink_occurrence_card(session, question)
            if old_card_id is not None:
                old_card_ids.append(old_card_id)
        await link_occurrence_to_card(
            session,
            question,
            card.id,
            AutomationDecisionSource.HUMAN,
            reason,
            manual_override=True,
        )
        await ensure_personal_review_for_occurrence(session, question, settings, card.id)
        # Invalidate every already-claimed automation snapshot before exposing
        # the manual link. This is required even when the wording is not being
        # confirmed as an alias.
        question.automation_revision += 1
        if confirm_alias:
            question.alias_human_confirmed = True
            question.moderation_status = IntelligenceQuestionModerationStatus.APPROVED
        if viewer.role is UserRole.ADMIN:
            question.admin_reviewed_by_user_id = viewer.id
            question.admin_reviewed_at = now
        else:
            question.mentor_reviewed_by_user_id = viewer.id
            question.mentor_reviewed_at = now
    await _replace_personal_items(session, [question.id for question in questions], card.id)
    if old_card_ids:
        await _refresh_card_stats(session, old_card_ids)
    cluster.linked_card_id = card.id
    cluster.deck_id = card.deck_id
    cluster.topic_name = card.category
    cluster.subtopic_name = card.subcategory
    return [question.id for question in questions]


async def _render_outcome(
    session: AsyncSession, viewer: User, outcome: _ActionOutcome
) -> QuestionClusterMutationResult:
    summaries = await _cluster_summaries_by_ids(session, viewer, [outcome.cluster_id])
    cluster = summaries.get(outcome.cluster_id)
    if cluster is None:
        api_error(404, "question_cluster_not_found", "Question cluster was not found")
    return QuestionClusterMutationResult(
        cluster=cluster,
        decision_id=outcome.decision_id,
        created_card_id=outcome.created_card_id,
        affected_cluster_ids=list(outcome.affected_cluster_ids),
    )


async def _commit_cluster_action(session: AsyncSession) -> None:
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        api_error(409, "question_cluster_action_conflict", "Question cluster action conflicts")


async def link_question_cluster_card(
    session: AsyncSession,
    viewer: User,
    cluster_id: UUID,
    payload: QuestionClusterLinkCardMutation,
) -> QuestionClusterMutationResult:
    _require_admin(viewer)
    key = _action_key(
        cluster_id,
        QuestionClusterAction.LINK_CARD.value,
        payload.expected_version,
        payload.card_id,
        payload.confirm_alias,
        payload.reason,
    )
    cluster, settings, existing = await _prepare_cluster_action(
        session, viewer, cluster_id, payload.expected_version, key
    )
    if existing is not None:
        return await _render_outcome(session, viewer, _outcome_from_decision(cluster.id, existing))
    _ensure_action_allowed(cluster, QuestionClusterAction.LINK_CARD)
    card = await _card_in_direction(session, payload.card_id, cluster.direction_id)
    occurrence_ids = await _apply_cluster_card_link(
        session,
        viewer,
        cluster,
        card,
        settings,
        reason=payload.reason,
        confirm_alias=payload.confirm_alias,
    )
    cluster.status = QuestionClusterStatus.LINKED
    cluster.version += 1
    decision = await _record_cluster_decision(
        session,
        cluster=cluster,
        settings=settings,
        idempotency_key=key,
        decision_type=AutomationDecisionType.CLUSTER_LINKED,
        reason=payload.reason,
        viewer=viewer,
        selected_card_id=card.id,
        candidate_card_ids=[card.id],
        retrieval_scores={
            "confirm_alias": payload.confirm_alias,
            "occurrence_ids": [str(item) for item in occurrence_ids],
            "affected_cluster_ids": [str(cluster.id)],
        },
    )
    await _commit_cluster_action(session)
    return await _render_outcome(
        session,
        viewer,
        _ActionOutcome(cluster.id, decision.id, affected_cluster_ids=(cluster.id,)),
    )


async def update_question_cluster_draft(
    session: AsyncSession,
    viewer: User,
    cluster_id: UUID,
    payload: QuestionClusterDraftMutation,
    *,
    idempotency_key: str | None = None,
) -> QuestionClusterMutationResult:
    """Persist a reviewed cluster draft without publishing a global card."""

    _require_moderator(viewer)
    request_payload = payload.model_dump(mode="json", exclude_unset=True)
    request_json = json.dumps(request_payload, ensure_ascii=False, sort_keys=True)
    request_hash = hashlib.sha256(request_json.encode()).hexdigest()
    key = (
        f"manual:cluster:{cluster_id}:update-draft:"
        f"{hashlib.sha256(idempotency_key.encode()).hexdigest()[:20]}"
        if idempotency_key is not None
        else _action_key(
            cluster_id,
            QuestionClusterAction.UPDATE_DRAFT.value,
            payload.expected_version,
            request_hash,
        )
    )
    cluster, settings, existing = await _prepare_cluster_action(
        session, viewer, cluster_id, payload.expected_version, key
    )
    if existing is not None:
        if existing.retrieval_scores.get("request_hash") != request_hash:
            api_error(
                409,
                "idempotency_key_reused",
                "Idempotency-Key was already used with a different request",
            )
        if existing.retrieval_scores.get("after") != _cluster_draft_audit_values(cluster):
            api_error(
                409,
                "question_cluster_idempotency_result_superseded",
                "The idempotent cluster draft result has since been superseded",
            )
        return await _render_outcome(
            session,
            viewer,
            _outcome_from_decision(cluster.id, existing),
        )
    _ensure_action_allowed(cluster, QuestionClusterAction.UPDATE_DRAFT)

    provided = payload.model_fields_set
    old_normalized = cluster.normalized_canonical_question
    canonical_question = cluster.canonical_question
    normalized_question = old_normalized
    if "canonical_question" in provided:
        assert payload.canonical_question is not None
        if "\x00" in payload.canonical_question:
            api_error(
                422,
                "invalid_canonical_question",
                "Canonical question cannot contain null characters",
            )
        canonical_question = payload.canonical_question
        normalized_question = normalize_question(canonical_question)
        if not normalized_question:
            api_error(
                422,
                "invalid_canonical_question",
                "Canonical question must contain searchable text",
            )

    topic_name = cluster.topic_name
    if "topic_name" in provided:
        topic_name = (
            await _canonical_existing_topic(
                session,
                direction_id=cluster.direction_id,
                topic_name=payload.topic_name,
                deck_id=cluster.deck_id,
            )
            if payload.topic_name is not None
            else None
        )

    subtopic_name = cluster.subtopic_name
    if "subtopic_name" in provided:
        subtopic_name = payload.subtopic_name

    answer_contract = cluster.answer_contract
    if "answer_contract" in provided:
        assert payload.answer_contract is not None
        answer_contract = cast(
            dict[str, object],
            payload.answer_contract.model_dump(mode="json"),
        )

    canonical_changed = canonical_question != cluster.canonical_question
    semantics_changed = normalized_question != old_normalized
    topic_changed = topic_name != cluster.topic_name
    subtopic_changed = subtopic_name != cluster.subtopic_name
    contract_changed = answer_contract != cluster.answer_contract
    changed_fields = [
        field
        for field, changed in (
            ("canonical_question", canonical_changed),
            ("topic_name", topic_changed),
            ("subtopic_name", subtopic_changed),
            ("answer_contract", contract_changed),
        )
        if changed
    ]
    if not changed_fields:
        api_error(
            422,
            "question_cluster_draft_unchanged",
            "Cluster draft does not contain any changes",
        )
    if payload.preserve_answer_status and semantics_changed:
        api_error(
            422,
            "unsafe_answer_status_preservation",
            "Answer status cannot be preserved after changing question semantics",
        )

    before = _cluster_draft_audit_values(cluster)
    cluster.canonical_question = canonical_question
    cluster.normalized_canonical_question = normalized_question
    cluster.topic_name = topic_name
    cluster.subtopic_name = subtopic_name
    cluster.answer_contract = answer_contract
    if semantics_changed:
        # The previous vector represents different semantics. A later embedding
        # refresh may repopulate it, but stale retrieval is less safe than no
        # semantic candidate in the meantime.
        cluster.embedding = None
        cluster.embedding_model = None
        cluster.embedding_dimensions = None
        cluster.embedding_source_hash = None
    if (
        not payload.preserve_answer_status
        and (semantics_changed or contract_changed)
        and cluster.answer_contract is not None
    ):
        cluster.answer_status = AnswerContractStatus.NEEDS_MANUAL_REVIEW
        cluster.answer_validation = None
    cluster.version += 1
    after = _cluster_draft_audit_values(cluster)
    decision = await _record_cluster_decision(
        session,
        cluster=cluster,
        settings=settings,
        idempotency_key=key,
        decision_type=AutomationDecisionType.MANUAL_OVERRIDE,
        reason=payload.reason,
        viewer=viewer,
        selected_cluster_id=cluster.id,
        retrieval_scores={
            "action": "cluster_draft_updated",
            "request_hash": request_hash,
            "changed_fields": changed_fields,
            "preserve_answer_status": payload.preserve_answer_status,
            "before": before,
            "after": after,
            "affected_cluster_ids": [str(cluster.id)],
        },
    )
    await _commit_cluster_action(session)
    return await _render_outcome(
        session,
        viewer,
        _ActionOutcome(cluster.id, decision.id, affected_cluster_ids=(cluster.id,)),
    )


def _cluster_draft_audit_values(cluster: QuestionCluster) -> dict[str, object]:
    return {
        "version": cluster.version,
        "canonical_question": cluster.canonical_question,
        "normalized_canonical_question": cluster.normalized_canonical_question,
        "topic_name": cluster.topic_name,
        "subtopic_name": cluster.subtopic_name,
        "answer_contract": cluster.answer_contract,
        "answer_status": cluster.answer_status.value if cluster.answer_status else None,
    }


async def create_question_cluster_card(
    session: AsyncSession,
    viewer: User,
    cluster_id: UUID,
    payload: QuestionClusterCreateCardMutation,
) -> QuestionClusterMutationResult:
    _require_admin(viewer)
    key = _action_key(
        cluster_id,
        QuestionClusterAction.CREATE_CARD.value,
        payload.expected_version,
        payload.deck_id,
        payload.category,
        payload.subcategory,
        payload.question_markdown,
        payload.answer_markdown,
        payload.frequency,
        payload.frequency_mode,
        payload.reason,
    )
    cluster, settings, existing = await _prepare_cluster_action(
        session, viewer, cluster_id, payload.expected_version, key
    )
    if existing is not None:
        return await _render_outcome(session, viewer, _outcome_from_decision(cluster.id, existing))
    _ensure_action_allowed(cluster, QuestionClusterAction.CREATE_CARD)
    deck = await session.scalar(
        select(InterviewDeck)
        .where(
            InterviewDeck.id == payload.deck_id,
            InterviewDeck.track_id == cluster.direction_id,
            InterviewDeck.is_published.is_(True),
        )
        .with_for_update()
    )
    if deck is None:
        api_error(404, "interview_deck_not_found", "Interview deck was not found")
    category = await _canonical_existing_topic(
        session,
        direction_id=cluster.direction_id,
        deck_id=deck.id,
        topic_name=payload.category,
    )
    slug = f"cluster-{cluster.id}"
    card = await session.scalar(
        select(InterviewCard).where(InterviewCard.slug == slug).with_for_update()
    )
    if card is not None and cluster.linked_card_id != card.id:
        api_error(409, "interview_card_slug_conflict", "Generated card slug is already in use")
    if card is None:
        position = (
            int(
                await session.scalar(
                    select(func.coalesce(func.max(InterviewCard.position), -1)).where(
                        InterviewCard.deck_id == deck.id
                    )
                )
                or 0
            )
            + 1
        )
        card = InterviewCard(
            deck_id=deck.id,
            slug=slug,
            category=category,
            subcategory=payload.subcategory,
            question_markdown=payload.question_markdown,
            answer_markdown=payload.answer_markdown,
            frequency=payload.frequency,
            frequency_override=(
                payload.frequency
                if payload.frequency_mode is InterviewCardFrequencyMode.MANUAL
                else None
            ),
            position=position,
            is_published=True,
            asked_count=0,
        )
        refresh_card_frequency(card)
        session.add(card)
        await session.flush()
    occurrence_ids = await _apply_cluster_card_link(
        session,
        viewer,
        cluster,
        card,
        settings,
        reason=payload.reason,
        confirm_alias=True,
    )
    cluster.status = QuestionClusterStatus.CARD_CREATED
    cluster.answer_status = AnswerContractStatus.APPROVED
    cluster.version += 1
    decision = await _record_cluster_decision(
        session,
        cluster=cluster,
        settings=settings,
        idempotency_key=key,
        decision_type=AutomationDecisionType.CARD_CREATED,
        reason=payload.reason,
        viewer=viewer,
        selected_card_id=card.id,
        candidate_card_ids=[card.id],
        retrieval_scores={
            "occurrence_ids": [str(item) for item in occurrence_ids],
            "affected_cluster_ids": [str(cluster.id)],
            "deck_id": str(card.deck_id),
            "category": card.category,
            "subcategory": card.subcategory,
            "question_sha256": hashlib.sha256(card.question_markdown.encode()).hexdigest(),
            "answer_sha256": hashlib.sha256(card.answer_markdown.encode()).hexdigest(),
            "frequency": card.frequency.value,
            "frequency_mode": payload.frequency_mode.value,
        },
    )
    await _commit_cluster_action(session)
    return await _render_outcome(
        session,
        viewer,
        _ActionOutcome(
            cluster.id,
            decision.id,
            created_card_id=card.id,
            affected_cluster_ids=(cluster.id,),
        ),
    )


async def split_question_cluster(
    session: AsyncSession,
    viewer: User,
    cluster_id: UUID,
    payload: QuestionClusterSplitMutation,
) -> QuestionClusterMutationResult:
    _require_admin(viewer)
    selected_ids = sorted(payload.occurrence_ids, key=str)
    key = _action_key(
        cluster_id,
        QuestionClusterAction.SPLIT.value,
        payload.expected_version,
        payload.new_canonical_question,
        payload.new_topic_name,
        payload.new_subtopic_name,
        payload.reason,
        *selected_ids,
    )
    cluster, settings, existing = await _prepare_cluster_action(
        session, viewer, cluster_id, payload.expected_version, key
    )
    if existing is not None:
        return await _render_outcome(session, viewer, _outcome_from_decision(cluster.id, existing))
    _ensure_action_allowed(cluster, QuestionClusterAction.SPLIT)
    questions = await _questions_in_cluster(session, cluster.id, lock=True)
    question_by_id = {item.id: item for item in questions}
    if any(item not in question_by_id for item in selected_ids):
        api_error(
            422,
            "question_cluster_split_occurrence_invalid",
            "Every selected occurrence must belong to the source cluster",
        )
    if len(selected_ids) >= len(questions):
        api_error(
            422,
            "question_cluster_split_requires_remainder",
            "At least one occurrence must remain in the source cluster",
        )
    normalized = normalize_question(payload.new_canonical_question)
    if not normalized:
        api_error(
            422,
            "question_cluster_split_canonical_invalid",
            "The new canonical question must contain searchable text",
        )
    conflict = await session.scalar(
        select(QuestionCluster.id).where(
            QuestionCluster.direction_id == cluster.direction_id,
            QuestionCluster.learning_object_type == cluster.learning_object_type,
            QuestionCluster.normalized_canonical_question == normalized,
        )
    )
    if conflict is not None:
        api_error(
            409,
            "question_cluster_split_conflict",
            "A cluster with this canonical question already exists",
        )
    requested_topic_name = payload.new_topic_name or cluster.topic_name
    if requested_topic_name is None:
        api_error(
            422,
            "question_cluster_topic_required",
            "Выберите широкую тему для нового кластера",
        )
    new_topic_name = await _canonical_existing_topic(
        session,
        direction_id=cluster.direction_id,
        deck_id=cluster.deck_id,
        topic_name=requested_topic_name,
    )
    selected_id_set = set(selected_ids)
    remaining_questions = [item for item in questions if item.id not in selected_id_set]
    original_representative_id = cluster.representative_occurrence_id
    new_representative_id = (
        original_representative_id
        if original_representative_id in selected_id_set
        else selected_ids[0]
    )
    new_cluster = QuestionCluster(
        direction_id=cluster.direction_id,
        status=QuestionClusterStatus.NEEDS_REVIEW,
        canonical_question=payload.new_canonical_question,
        normalized_canonical_question=normalized,
        learning_object_type=cluster.learning_object_type,
        deck_id=cluster.deck_id,
        topic_name=new_topic_name,
        subtopic_name=payload.new_subtopic_name or cluster.subtopic_name,
        topic_candidates=list(cluster.topic_candidates),
        representative_occurrence_id=new_representative_id,
        answer_status=AnswerContractStatus.NEEDS_MANUAL_REVIEW,
        cluster_confidence=0.0,
        quality_score=0.0,
        parent_cluster_id=cluster.id,
        membership_revision=len(selected_ids),
        stats_revision=0,
        version=1,
    )
    session.add(new_cluster)
    await session.flush()
    old_card_ids: list[UUID] = []
    for occurrence_id in selected_ids:
        question = question_by_id[occurrence_id]
        old_card_id = await _unlink_occurrence_card(session, question)
        if old_card_id is not None:
            old_card_ids.append(old_card_id)
        question.cluster_id = new_cluster.id
        question.automation_status = QuestionOccurrenceStatus.NEEDS_REVIEW
        question.automation_decision_source = AutomationDecisionSource.HUMAN
        question.automation_decision_reason = payload.reason
        question.automation_revision += 1
    await _reactivate_personal_items(session, selected_ids)
    await _refresh_card_stats(session, old_card_ids)
    if cluster.representative_occurrence_id not in {item.id for item in remaining_questions}:
        cluster.representative_occurrence_id = remaining_questions[0].id
    sync_cluster_embedding_from_representative(
        cluster,
        question_by_id.get(cluster.representative_occurrence_id)
        if cluster.representative_occurrence_id is not None
        else None,
    )
    sync_cluster_embedding_from_representative(
        new_cluster,
        question_by_id.get(new_cluster.representative_occurrence_id)
        if new_cluster.representative_occurrence_id is not None
        else None,
    )
    cluster.membership_revision += len(selected_ids)
    cluster.version += 1
    # These are membership-derived aggregates and must be allowed to decrease
    # after a split; recalculate_cluster_stats deliberately preserves a prior
    # confidence unless callers invalidate it first.
    cluster.quality_score = 0.0
    cluster.cluster_confidence = 0.0
    await recalculate_cluster_stats(session, cluster, settings)
    await recalculate_cluster_stats(session, new_cluster, settings)
    decision = await _record_cluster_decision(
        session,
        cluster=cluster,
        settings=settings,
        idempotency_key=key,
        decision_type=AutomationDecisionType.CLUSTER_SPLIT,
        reason=payload.reason,
        viewer=viewer,
        selected_cluster_id=new_cluster.id,
        candidate_cluster_ids=[new_cluster.id],
        retrieval_scores={
            "moved_occurrence_ids": [str(item) for item in selected_ids],
            "affected_cluster_ids": [str(cluster.id), str(new_cluster.id)],
            "new_canonical_question": payload.new_canonical_question,
        },
    )
    await _commit_cluster_action(session)
    return await _render_outcome(
        session,
        viewer,
        _ActionOutcome(
            cluster.id,
            decision.id,
            affected_cluster_ids=(cluster.id, new_cluster.id),
        ),
    )


async def merge_question_clusters(
    session: AsyncSession,
    viewer: User,
    cluster_id: UUID,
    payload: QuestionClusterMergeMutation,
) -> QuestionClusterMutationResult:
    _require_admin(viewer)
    if cluster_id == payload.target_cluster_id:
        api_error(422, "question_cluster_merge_self", "A cluster cannot be merged into itself")
    key = _action_key(
        cluster_id,
        QuestionClusterAction.MERGE.value,
        payload.expected_version,
        payload.target_cluster_id,
        payload.target_expected_version,
        payload.reason,
    )
    # Lock in stable UUID order to prevent reciprocal merges from deadlocking.
    lock_ids = sorted((cluster_id, payload.target_cluster_id), key=str)
    track_ids = await _allowed_track_ids(session, viewer)
    locked = list(
        await session.scalars(
            select(QuestionCluster)
            .where(
                QuestionCluster.id.in_(lock_ids),
                QuestionCluster.direction_id.in_(track_ids),
            )
            .order_by(QuestionCluster.id)
            .with_for_update()
        )
    )
    by_id = {item.id: item for item in locked}
    cluster = by_id.get(cluster_id)
    target = by_id.get(payload.target_cluster_id)
    if cluster is None or target is None:
        api_error(404, "question_cluster_not_found", "Question cluster was not found")
    existing = await _existing_action_decision(session, key)
    if existing is not None:
        return await _render_outcome(session, viewer, _outcome_from_decision(cluster.id, existing))
    if (
        cluster.version != payload.expected_version
        or target.version != payload.target_expected_version
    ):
        api_error(
            409,
            "question_cluster_version_conflict",
            "One of the question clusters changed; reload and try again",
        )
    _ensure_action_allowed(cluster, QuestionClusterAction.MERGE)
    _ensure_action_allowed(target, QuestionClusterAction.MERGE)
    if cluster.direction_id != target.direction_id:
        api_error(
            422,
            "question_cluster_direction_mismatch",
            "Clusters from different learning tracks cannot be merged",
        )
    if cluster.learning_object_type is not target.learning_object_type:
        api_error(
            422,
            "question_cluster_type_mismatch",
            "Clusters with different learning object types cannot be merged",
        )
    if (
        cluster.linked_card_id is not None
        and target.linked_card_id is not None
        and cluster.linked_card_id != target.linked_card_id
    ):
        api_error(
            409,
            "question_cluster_card_conflict",
            "Clusters linked to different cards cannot be merged",
        )
    settings = await _settings_model(session, cluster.direction_id)
    questions = await _questions_in_cluster(session, cluster.id, lock=True)
    target_questions = await _questions_in_cluster(session, target.id, lock=True)
    target_card_id = target.linked_card_id or cluster.linked_card_id
    revision_bumped_ids: set[UUID] = set()
    if target_card_id is not None:
        card = await _card_in_direction(session, target_card_id, target.direction_id)
        # A merged cluster exposes one canonical card, so every occurrence on both
        # sides must be linked before the source membership is moved.
        revision_bumped_ids.update(
            await _apply_cluster_card_link(
                session,
                viewer,
                target,
                card,
                settings,
                reason=payload.reason,
                confirm_alias=True,
            )
        )
        revision_bumped_ids.update(
            await _apply_cluster_card_link(
                session,
                viewer,
                cluster,
                card,
                settings,
                reason=payload.reason,
                confirm_alias=True,
            )
        )
        target.linked_card_id = card.id
        target.deck_id = card.deck_id
        target.topic_name = target.topic_name or card.category
        target.status = QuestionClusterStatus.LINKED
    for question in questions:
        question.cluster_id = target.id
        question.automation_decision_source = AutomationDecisionSource.HUMAN
        question.automation_decision_reason = payload.reason
        if question.id not in revision_bumped_ids:
            question.automation_revision += 1
    source_question_ids = {item.id for item in questions}
    if cluster.representative_occurrence_id not in source_question_ids and questions:
        # Keep the source representative so a later reopen can restore an
        # intelligible source cluster without guessing from the target.
        cluster.representative_occurrence_id = questions[0].id
    target_member_ids = {item.id for item in target_questions} | source_question_ids
    if target.representative_occurrence_id not in target_member_ids:
        target.representative_occurrence_id = (
            target_questions[0].id if target_questions else cluster.representative_occurrence_id
        )
    question_by_id = {item.id: item for item in [*target_questions, *questions]}
    sync_cluster_embedding_from_representative(
        cluster,
        question_by_id.get(cluster.representative_occurrence_id)
        if cluster.representative_occurrence_id is not None
        else None,
    )
    sync_cluster_embedding_from_representative(
        target,
        question_by_id.get(target.representative_occurrence_id)
        if target.representative_occurrence_id is not None
        else None,
    )
    cluster.status = QuestionClusterStatus.MERGED
    cluster.merged_into_cluster_id = target.id
    cluster.membership_revision += len(questions)
    cluster.version += 1
    target.membership_revision += len(questions)
    target.version += 1
    cluster.quality_score = 0.0
    cluster.cluster_confidence = 0.0
    target.quality_score = 0.0
    target.cluster_confidence = 0.0
    await recalculate_cluster_stats(session, cluster, settings)
    await recalculate_cluster_stats(session, target, settings)
    decision = await _record_cluster_decision(
        session,
        cluster=cluster,
        settings=settings,
        idempotency_key=key,
        decision_type=AutomationDecisionType.CLUSTER_MERGED,
        reason=payload.reason,
        viewer=viewer,
        selected_cluster_id=target.id,
        candidate_cluster_ids=[target.id],
        retrieval_scores={
            "moved_occurrence_ids": [str(item.id) for item in questions],
            "affected_cluster_ids": [str(cluster.id), str(target.id)],
        },
    )
    await _commit_cluster_action(session)
    return await _render_outcome(
        session,
        viewer,
        _ActionOutcome(
            cluster.id,
            decision.id,
            affected_cluster_ids=(cluster.id, target.id),
        ),
    )


async def _simple_cluster_action(
    session: AsyncSession,
    viewer: User,
    cluster_id: UUID,
    payload: QuestionClusterActionMutation,
    action: QuestionClusterAction,
) -> QuestionClusterMutationResult:
    _require_moderator(viewer)
    if viewer.role is UserRole.MENTOR and action not in _MENTOR_CLUSTER_ACTIONS:
        api_error(403, "admin_required", "Administrator access is required for this action")
    key = _action_key(cluster_id, action.value, payload.expected_version, payload.reason)
    cluster, settings, existing = await _prepare_cluster_action(
        session, viewer, cluster_id, payload.expected_version, key
    )
    if existing is not None:
        return await _render_outcome(session, viewer, _outcome_from_decision(cluster.id, existing))
    _ensure_action_allowed(cluster, action)
    decision_types = {
        QuestionClusterAction.IGNORE: AutomationDecisionType.CLUSTER_IGNORED,
        QuestionClusterAction.DEFER: AutomationDecisionType.CLUSTER_DEFERRED,
        QuestionClusterAction.MARK_IMPORTANT: AutomationDecisionType.CLUSTER_MARKED_IMPORTANT,
        QuestionClusterAction.REOPEN: AutomationDecisionType.CLUSTER_REOPENED,
    }
    old_status = cluster.status
    retrieval_scores: dict[str, object] = {
        "old_status": old_status.value,
        "affected_cluster_ids": [str(cluster.id)],
    }
    if action is QuestionClusterAction.IGNORE:
        cluster.status = QuestionClusterStatus.IGNORED
        questions = await _questions_in_cluster(session, cluster.id, lock=True)
        for question in questions:
            if question.published_card_id is None:
                question.automation_status = QuestionOccurrenceStatus.AUTO_IGNORED
                question.automation_decision_source = AutomationDecisionSource.HUMAN
                question.automation_decision_reason = payload.reason
                question.automation_revision += 1
    elif action is QuestionClusterAction.DEFER:
        cluster.status = QuestionClusterStatus.DEFERRED
    elif action is QuestionClusterAction.MARK_IMPORTANT:
        cluster.manual_important = True
        if cluster.status in {
            QuestionClusterStatus.SHADOW,
            QuestionClusterStatus.CANDIDATE,
            QuestionClusterStatus.DEFERRED,
        }:
            cluster.status = QuestionClusterStatus.NEEDS_REVIEW
            cluster.promoted_at = datetime.now(UTC)
            cluster.promotion_reason = "Manually marked important"
        await recalculate_cluster_stats(session, cluster, settings)
    elif action is QuestionClusterAction.REOPEN:
        cluster.status = QuestionClusterStatus.NEEDS_REVIEW
        if old_status is QuestionClusterStatus.MERGED:
            merge_decision = await session.scalar(
                select(AutomationDecision)
                .where(
                    AutomationDecision.entity_type == "cluster",
                    AutomationDecision.entity_id == cluster.id,
                    AutomationDecision.decision_type == AutomationDecisionType.CLUSTER_MERGED,
                )
                .order_by(AutomationDecision.created_at.desc())
            )
            moved_ids = (
                _uuid_list(merge_decision.retrieval_scores.get("moved_occurrence_ids"))
                if merge_decision is not None
                else []
            )
            if moved_ids:
                questions = list(
                    await session.scalars(
                        select(IntelligenceQuestion)
                        .where(
                            IntelligenceQuestion.id.in_(moved_ids),
                            IntelligenceQuestion.cluster_id == cluster.merged_into_cluster_id,
                        )
                        .with_for_update()
                    )
                )
                old_card_ids: list[UUID] = []
                for question in questions:
                    old_card_id = await _unlink_occurrence_card(session, question)
                    if old_card_id is not None:
                        old_card_ids.append(old_card_id)
                    question.cluster_id = cluster.id
                    question.automation_status = QuestionOccurrenceStatus.NEEDS_REVIEW
                    question.automation_decision_source = AutomationDecisionSource.HUMAN
                    question.automation_decision_reason = payload.reason
                    question.automation_revision += 1
                await _reactivate_personal_items(session, moved_ids)
                await _refresh_card_stats(session, old_card_ids)
                restored_ids = {item.id for item in questions}
                if cluster.representative_occurrence_id not in restored_ids and questions:
                    cluster.representative_occurrence_id = questions[0].id
                cluster.membership_revision += len(questions)
                if cluster.merged_into_cluster_id is not None:
                    target = await session.get(
                        QuestionCluster,
                        cluster.merged_into_cluster_id,
                        with_for_update=True,
                    )
                    if target is not None:
                        remaining_target_questions = await _questions_in_cluster(
                            session, target.id, lock=True
                        )
                        remaining_target_ids = {
                            item.id
                            for item in remaining_target_questions
                            if item.id not in restored_ids
                        }
                        if target.representative_occurrence_id not in remaining_target_ids:
                            target.representative_occurrence_id = next(
                                iter(sorted(remaining_target_ids, key=str)), None
                            )
                        target_representative = next(
                            (
                                item
                                for item in remaining_target_questions
                                if item.id == target.representative_occurrence_id
                            ),
                            None,
                        )
                        sync_cluster_embedding_from_representative(target, target_representative)
                        target.membership_revision += len(questions)
                        target.version += 1
                        target.quality_score = 0.0
                        target.cluster_confidence = 0.0
                        await recalculate_cluster_stats(session, target, settings)
                retrieval_scores["restored_occurrence_ids"] = [str(item.id) for item in questions]
            cluster.linked_card_id = None
            cluster.merged_into_cluster_id = None
        elif old_status is QuestionClusterStatus.IGNORED:
            questions = await _questions_in_cluster(session, cluster.id, lock=True)
            for question in questions:
                question.automation_status = QuestionOccurrenceStatus.NEEDS_REVIEW
                question.automation_decision_source = AutomationDecisionSource.HUMAN
                question.automation_decision_reason = payload.reason
                question.automation_revision += 1
        elif old_status in {QuestionClusterStatus.LINKED, QuestionClusterStatus.CARD_CREATED}:
            questions = await _questions_in_cluster(session, cluster.id, lock=True)
            old_card_ids = [
                old_card_id
                for question in questions
                if (old_card_id := await _unlink_occurrence_card(session, question)) is not None
            ]
            for question in questions:
                question.automation_status = QuestionOccurrenceStatus.NEEDS_REVIEW
                question.automation_decision_source = AutomationDecisionSource.HUMAN
                question.automation_decision_reason = payload.reason
                question.automation_revision += 1
            await _reactivate_personal_items(session, [item.id for item in questions])
            await _refresh_card_stats(session, old_card_ids)
            cluster.linked_card_id = None
        representative = (
            await session.get(IntelligenceQuestion, cluster.representative_occurrence_id)
            if cluster.representative_occurrence_id is not None
            else None
        )
        sync_cluster_embedding_from_representative(cluster, representative)
        cluster.quality_score = 0.0
        cluster.cluster_confidence = 0.0
        await recalculate_cluster_stats(session, cluster, settings)
    else:
        api_error(422, "question_cluster_action_invalid", "Unsupported cluster action")
    cluster.version += 1
    retrieval_scores["new_status"] = cluster.status.value
    decision = await _record_cluster_decision(
        session,
        cluster=cluster,
        settings=settings,
        idempotency_key=key,
        decision_type=decision_types[action],
        reason=payload.reason,
        viewer=viewer,
        retrieval_scores=retrieval_scores,
    )
    await _commit_cluster_action(session)
    return await _render_outcome(
        session,
        viewer,
        _ActionOutcome(cluster.id, decision.id, affected_cluster_ids=(cluster.id,)),
    )


async def ignore_question_cluster(
    session: AsyncSession,
    viewer: User,
    cluster_id: UUID,
    payload: QuestionClusterActionMutation,
) -> QuestionClusterMutationResult:
    return await _simple_cluster_action(
        session, viewer, cluster_id, payload, QuestionClusterAction.IGNORE
    )


async def defer_question_cluster(
    session: AsyncSession,
    viewer: User,
    cluster_id: UUID,
    payload: QuestionClusterActionMutation,
) -> QuestionClusterMutationResult:
    return await _simple_cluster_action(
        session, viewer, cluster_id, payload, QuestionClusterAction.DEFER
    )


async def mark_question_cluster_important(
    session: AsyncSession,
    viewer: User,
    cluster_id: UUID,
    payload: QuestionClusterActionMutation,
) -> QuestionClusterMutationResult:
    return await _simple_cluster_action(
        session, viewer, cluster_id, payload, QuestionClusterAction.MARK_IMPORTANT
    )


async def reopen_question_cluster(
    session: AsyncSession,
    viewer: User,
    cluster_id: UUID,
    payload: QuestionClusterActionMutation,
) -> QuestionClusterMutationResult:
    return await _simple_cluster_action(
        session, viewer, cluster_id, payload, QuestionClusterAction.REOPEN
    )


async def _apply_cluster_topic(
    session: AsyncSession,
    viewer: User,
    cluster_id: UUID,
    expected_version: int,
    topic_name: str,
    reason: str,
) -> QuestionClusterMutationResult:
    _require_admin(viewer)
    key = _action_key(cluster_id, "apply_topic", expected_version, topic_name, reason)
    cluster, settings, existing = await _prepare_cluster_action(
        session, viewer, cluster_id, expected_version, key
    )
    if existing is not None:
        return await _render_outcome(session, viewer, _outcome_from_decision(cluster.id, existing))
    canonical_topic = await _canonical_existing_topic(
        session,
        direction_id=cluster.direction_id,
        deck_id=cluster.deck_id,
        topic_name=topic_name,
    )
    old_topic = cluster.topic_name
    cluster.topic_name = canonical_topic
    cluster.version += 1
    decision = await _record_cluster_decision(
        session,
        cluster=cluster,
        settings=settings,
        idempotency_key=key,
        decision_type=AutomationDecisionType.MANUAL_OVERRIDE,
        reason=reason,
        viewer=viewer,
        retrieval_scores={
            "field": "topic_name",
            "old_value": old_topic,
            "new_value": canonical_topic,
            "affected_cluster_ids": [str(cluster.id)],
        },
    )
    await _commit_cluster_action(session)
    return await _render_outcome(
        session,
        viewer,
        _ActionOutcome(cluster.id, decision.id, affected_cluster_ids=(cluster.id,)),
    )


def _http_error_parts(error: HTTPException) -> tuple[str, str]:
    if isinstance(error.detail, dict):
        code = str(error.detail.get("code") or "card_automation_action_failed")
        message = str(error.detail.get("message") or "Card automation action failed")
        return code, message
    return "card_automation_action_failed", str(error.detail)


async def bulk_update_question_clusters(
    session: AsyncSession,
    viewer: User,
    payload: QuestionClusterBulkMutation,
) -> QuestionClusterBulkResult:
    _require_moderator(viewer)
    admin_actions = {
        QuestionClusterBulkAction.CONFIRM_EXACT_MATCHES,
        QuestionClusterBulkAction.CONFIRM_HIGH_CONFIDENCE_MATCHES,
        QuestionClusterBulkAction.LINK_CARD,
        QuestionClusterBulkAction.APPLY_TOPIC,
    }
    if payload.action in admin_actions:
        _require_admin(viewer)

    track_ids = await _allowed_track_ids(session, viewer)
    clusters = list(
        await session.scalars(
            select(QuestionCluster).where(
                QuestionCluster.id.in_(payload.cluster_ids),
                QuestionCluster.direction_id.in_(track_ids),
            )
        )
    )
    cluster_info = {
        item.id: (item.learning_object_type, item.occurrences_count, item.direction_id)
        for item in clusters
    }
    match_decisions = (
        await _latest_cluster_match_decisions(session, payload.cluster_ids)
        if payload.action
        in {
            QuestionClusterBulkAction.CONFIRM_EXACT_MATCHES,
            QuestionClusterBulkAction.CONFIRM_HIGH_CONFIDENCE_MATCHES,
        }
        else {}
    )
    match_info = {
        cluster_id: (
            decision.decision_type,
            decision.selected_card_id,
            tuple(_uuid_list(decision.candidate_card_ids)),
            *_judge_values(decision.judge_result)[:2],
        )
        for cluster_id, decision in match_decisions.items()
    }
    settings_by_direction: dict[UUID, CardAutomationSettings] = {}
    if match_info:
        direction_ids = {item[2] for item in cluster_info.values()}
        settings_rows = list(
            await session.scalars(
                select(CardAutomationSettings).where(
                    CardAutomationSettings.direction_id.in_(direction_ids)
                )
            )
        )
        settings_by_direction = {item.direction_id: item for item in settings_rows}
    items: list[QuestionClusterBulkItemResult] = []
    for cluster_id in payload.cluster_ids:
        info = cluster_info.get(cluster_id)
        if info is None:
            items.append(
                QuestionClusterBulkItemResult(
                    cluster_id=cluster_id,
                    succeeded=False,
                    error_code="question_cluster_not_found",
                    error_message="Question cluster was not found",
                )
            )
            continue
        try:
            expected_version = payload.expected_versions[cluster_id]
            result: QuestionClusterMutationResult
            if payload.action is QuestionClusterBulkAction.IGNORE_NOISE:
                if info[0] is not LearningObjectType.NOISE:
                    api_error(
                        422,
                        "question_cluster_not_noise",
                        "Only noise clusters can be ignored by this bulk action",
                    )
                result = await ignore_question_cluster(
                    session,
                    viewer,
                    cluster_id,
                    QuestionClusterActionMutation(
                        expected_version=expected_version,
                        reason=payload.reason,
                    ),
                )
            elif payload.action is QuestionClusterBulkAction.DEFER_SINGLETONS:
                if info[1] > 1:
                    api_error(
                        422,
                        "question_cluster_not_singleton",
                        "Only one-off clusters can be deferred by this bulk action",
                    )
                result = await defer_question_cluster(
                    session,
                    viewer,
                    cluster_id,
                    QuestionClusterActionMutation(
                        expected_version=expected_version,
                        reason=payload.reason,
                    ),
                )
            elif payload.action is QuestionClusterBulkAction.LINK_CARD:
                if payload.card_id is None:
                    api_error(422, "interview_card_required", "A target card is required")
                result = await link_question_cluster_card(
                    session,
                    viewer,
                    cluster_id,
                    QuestionClusterLinkCardMutation(
                        card_id=payload.card_id,
                        expected_version=expected_version,
                        reason=payload.reason,
                        confirm_alias=True,
                    ),
                )
            elif payload.action is QuestionClusterBulkAction.APPLY_TOPIC:
                if payload.topic_name is None:
                    api_error(422, "topic_name_required", "A topic is required")
                result = await _apply_cluster_topic(
                    session,
                    viewer,
                    cluster_id,
                    expected_version,
                    payload.topic_name,
                    payload.reason,
                )
            else:
                match = match_info.get(cluster_id)
                if match is None:
                    api_error(
                        409,
                        "question_cluster_match_missing",
                        "The cluster has no card suggestion to confirm",
                    )
                if payload.action is QuestionClusterBulkAction.CONFIRM_EXACT_MATCHES:
                    if match[0] not in {
                        AutomationDecisionType.EXACT_CARD_MATCH,
                        AutomationDecisionType.ALIAS_CARD_MATCH,
                    }:
                        api_error(
                            409,
                            "question_cluster_match_not_exact",
                            "The current card suggestion is not an exact or alias match",
                        )
                elif (
                    match[0] is not AutomationDecisionType.SEMANTIC_CARD_MATCH
                    or match[3] is not PairwiseCardMatchDecision.SAME_CARD
                    or match[4] is None
                    or match[4]
                    < (
                        settings_by_direction[info[2]].pairwise_judge_confidence_threshold
                        if info[2] in settings_by_direction
                        else 0.92
                    )
                ):
                    api_error(
                        409,
                        "question_cluster_match_not_high_confidence",
                        "The current card suggestion is not a reviewed semantic match",
                    )
                card_id = match[1] or (match[2][0] if match[2] else None)
                if card_id is None:
                    api_error(
                        409,
                        "question_cluster_match_missing",
                        "The card suggestion has no target card",
                    )
                result = await link_question_cluster_card(
                    session,
                    viewer,
                    cluster_id,
                    QuestionClusterLinkCardMutation(
                        card_id=card_id,
                        expected_version=expected_version,
                        reason=payload.reason,
                        confirm_alias=True,
                    ),
                )
            items.append(
                QuestionClusterBulkItemResult(
                    cluster_id=cluster_id,
                    succeeded=True,
                    cluster=result.cluster,
                    decision_id=result.decision_id,
                )
            )
        except HTTPException as error:
            await session.rollback()
            code, message = _http_error_parts(error)
            items.append(
                QuestionClusterBulkItemResult(
                    cluster_id=cluster_id,
                    succeeded=False,
                    error_code=code,
                    error_message=message,
                )
            )
    succeeded = sum(item.succeeded for item in items)
    return QuestionClusterBulkResult(
        requested_count=len(items),
        succeeded_count=succeeded,
        failed_count=len(items) - succeeded,
        items=items,
    )


async def list_automation_decisions(
    session: AsyncSession,
    viewer: User,
    filters: AutomationDecisionListFilters,
) -> AutomationDecisionPage:
    track_ids = await _allowed_track_ids(session, viewer)
    if filters.direction_id is not None:
        if filters.direction_id not in track_ids:
            api_error(404, "learning_track_not_found", "Learning track was not found")
        track_ids = {filters.direction_id}
    if not track_ids:
        return AutomationDecisionPage(items=[], total=0, limit=filters.limit, offset=filters.offset)
    conditions: list[Any] = [_decision_scope_condition(track_ids, viewer)]
    if filters.entity_type is not None:
        conditions.append(AutomationDecision.entity_type == filters.entity_type)
    if filters.decision_types:
        conditions.append(AutomationDecision.decision_type.in_(filters.decision_types))
    if filters.decision_sources:
        conditions.append(AutomationDecision.decision_source.in_(filters.decision_sources))
    if filters.is_audit_sample is not None:
        conditions.append(AutomationDecision.is_audit_sample.is_(filters.is_audit_sample))
    if filters.is_reviewed is True:
        conditions.append(AutomationDecision.reviewed_at.is_not(None))
    elif filters.is_reviewed is False:
        conditions.append(AutomationDecision.reviewed_at.is_(None))
    if filters.is_overridden is not None:
        conditions.append(AutomationDecision.is_overridden.is_(filters.is_overridden))
    if filters.created_from is not None:
        conditions.append(AutomationDecision.created_at >= filters.created_from)
    if filters.created_to is not None:
        conditions.append(AutomationDecision.created_at <= filters.created_to)
    total = int(
        await session.scalar(select(func.count(AutomationDecision.id)).where(*conditions)) or 0
    )
    order = (
        AutomationDecision.created_at.asc()
        if filters.sort_order == "asc"
        else AutomationDecision.created_at.desc()
    )
    decisions = list(
        await session.scalars(
            select(AutomationDecision)
            .where(*conditions)
            .order_by(order, AutomationDecision.id)
            .limit(filters.limit)
            .offset(filters.offset)
        )
    )
    return AutomationDecisionPage(
        items=await _decision_reads(session, decisions),
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


async def _decision_direction_id(
    session: AsyncSession, decision: AutomationDecision
) -> UUID | None:
    if decision.entity_type == "settings":
        return decision.entity_id
    if decision.entity_type == "occurrence":
        return cast(
            UUID | None,
            await session.scalar(
                select(IntelligenceQuestion.direction_id).where(
                    IntelligenceQuestion.id == decision.entity_id
                )
            ),
        )
    if decision.entity_type == "cluster":
        return cast(
            UUID | None,
            await session.scalar(
                select(QuestionCluster.direction_id).where(QuestionCluster.id == decision.entity_id)
            ),
        )
    if decision.entity_type == "personal_review_item":
        return cast(
            UUID | None,
            await session.scalar(
                select(PersonalReviewItem.direction_id).where(
                    PersonalReviewItem.id == decision.entity_id
                )
            ),
        )
    return None


async def _scoped_decision(
    session: AsyncSession,
    viewer: User,
    decision_id: UUID,
    *,
    lock: bool = False,
) -> tuple[AutomationDecision, UUID]:
    _require_moderator(viewer)
    statement = select(AutomationDecision).where(AutomationDecision.id == decision_id)
    if lock:
        statement = statement.with_for_update()
    decision = await session.scalar(statement)
    if decision is None:
        api_error(404, "automation_decision_not_found", "Automation decision was not found")
    direction_id = await _decision_direction_id(session, decision)
    track_ids = await accessible_track_ids(session, viewer)
    if direction_id is None or direction_id not in track_ids:
        api_error(404, "automation_decision_not_found", "Automation decision was not found")
    visible_decision_id = await session.scalar(
        select(AutomationDecision.id).where(
            AutomationDecision.id == decision.id,
            _decision_scope_condition({direction_id}, viewer),
        )
    )
    if visible_decision_id is None:
        api_error(404, "automation_decision_not_found", "Automation decision was not found")
    return decision, direction_id


async def review_automation_decision(
    session: AsyncSession,
    viewer: User,
    decision_id: UUID,
    payload: AutomationDecisionReviewMutation,
) -> AutomationDecisionRead:
    decision, _ = await _scoped_decision(session, viewer, decision_id, lock=True)
    if decision.reviewed_at is not None:
        if decision.review_result is payload.result and decision.review_reason == payload.reason:
            return (await _decision_reads(session, [decision]))[0]
        api_error(
            409,
            "automation_decision_already_reviewed",
            "Automation decision has already been reviewed",
        )
    decision.review_result = payload.result
    decision.review_reason = payload.reason
    decision.reviewed_by_user_id = viewer.id
    decision.reviewed_at = datetime.now(UTC)
    await session.commit()
    return (await _decision_reads(session, [decision]))[0]


async def _restore_occurrence_to_review(
    session: AsyncSession,
    question: IntelligenceQuestion,
    reason: str,
) -> None:
    old_card_id = await _unlink_occurrence_card(session, question)
    old_cluster_id = question.cluster_id
    question.cluster_id = None
    question.automation_status = QuestionOccurrenceStatus.NEEDS_REVIEW
    question.automation_decision_source = AutomationDecisionSource.HUMAN
    question.automation_decision_reason = reason
    question.automation_revision += 1
    await _reactivate_personal_items(session, [question.id])
    if old_card_id is not None:
        await _refresh_card_stats(session, [old_card_id])
    if old_cluster_id is not None:
        cluster = await session.get(QuestionCluster, old_cluster_id, with_for_update=True)
        if cluster is not None:
            cluster.membership_revision += 1
            cluster.version += 1
            await recalculate_cluster_stats(
                session, cluster, await _settings_model(session, cluster.direction_id)
            )


async def _apply_occurrence_override(
    session: AsyncSession,
    viewer: User,
    question: IntelligenceQuestion,
    payload: AutomationDecisionOverrideMutation,
    direction_id: UUID,
) -> None:
    settings = await _settings_model(session, direction_id)
    if payload.selected_card_id is not None:
        card = await _card_in_direction(session, payload.selected_card_id, direction_id)
        old_cluster_id = question.cluster_id
        if question.published_card_id is not None and question.published_card_id != card.id:
            old_card_id = await _unlink_occurrence_card(session, question)
            if old_card_id is not None:
                await _refresh_card_stats(session, [old_card_id])
        question.cluster_id = None
        await link_occurrence_to_card(
            session,
            question,
            card.id,
            AutomationDecisionSource.HUMAN,
            payload.reason,
            manual_override=True,
        )
        await ensure_personal_review_for_occurrence(session, question, settings, card.id)
        await _replace_personal_items(session, [question.id], card.id)
        reviewed_at = datetime.now(UTC)
        if viewer.role is UserRole.ADMIN:
            question.alias_human_confirmed = True
            question.moderation_status = IntelligenceQuestionModerationStatus.APPROVED
            question.admin_reviewed_by_user_id = viewer.id
            question.admin_reviewed_at = reviewed_at
        elif viewer.role is UserRole.MENTOR:
            question.mentor_reviewed_by_user_id = viewer.id
            question.mentor_reviewed_at = reviewed_at
        question.automation_revision += 1
        if old_cluster_id is not None:
            old_cluster = await session.get(QuestionCluster, old_cluster_id, with_for_update=True)
            if old_cluster is not None:
                old_cluster.membership_revision += 1
                old_cluster.version += 1
                await recalculate_cluster_stats(session, old_cluster, settings)
        return
    if payload.selected_cluster_id is not None:
        target = await session.scalar(
            select(QuestionCluster)
            .where(
                QuestionCluster.id == payload.selected_cluster_id,
                QuestionCluster.direction_id == direction_id,
            )
            .with_for_update()
        )
        if target is None:
            api_error(404, "question_cluster_not_found", "Question cluster was not found")
        if target.status in {
            QuestionClusterStatus.DEFERRED,
            QuestionClusterStatus.IGNORED,
            QuestionClusterStatus.SPLIT,
            QuestionClusterStatus.MERGED,
        }:
            api_error(
                409,
                "question_cluster_target_not_active",
                "An occurrence can only be assigned to an active cluster",
            )
        old_card_id = await _unlink_occurrence_card(session, question)
        old_cluster_id = question.cluster_id
        question.cluster_id = target.id
        if target.linked_card_id is not None:
            card = await _card_in_direction(session, target.linked_card_id, direction_id)
            await link_occurrence_to_card(
                session,
                question,
                card.id,
                AutomationDecisionSource.HUMAN,
                payload.reason,
                manual_override=True,
            )
            await ensure_personal_review_for_occurrence(session, question, settings, card.id)
            await _replace_personal_items(session, [question.id], card.id)
            if viewer.role is UserRole.ADMIN:
                question.alias_human_confirmed = True
                question.moderation_status = IntelligenceQuestionModerationStatus.APPROVED
        else:
            question.automation_status = (
                QuestionOccurrenceStatus.NEEDS_REVIEW
                if target.status is QuestionClusterStatus.NEEDS_REVIEW
                else QuestionOccurrenceStatus.CLUSTERED
            )
            question.automation_decision_source = AutomationDecisionSource.HUMAN
            question.automation_decision_reason = payload.reason
            await _reactivate_personal_items(session, [question.id])
        question.automation_revision += 1
        if old_cluster_id != target.id:
            target.membership_revision += 1
            target.version += 1
        await recalculate_cluster_stats(session, target, settings)
        if old_cluster_id is not None and old_cluster_id != target.id:
            old_cluster = await session.get(QuestionCluster, old_cluster_id, with_for_update=True)
            if old_cluster is not None:
                old_cluster.membership_revision += 1
                old_cluster.version += 1
                await recalculate_cluster_stats(session, old_cluster, settings)
        if old_card_id is not None:
            await _refresh_card_stats(session, [old_card_id])
        return
    if payload.replacement_decision_type is AutomationDecisionType.ROUTED_AS_NOISE:
        old_card_id = await _unlink_occurrence_card(session, question)
        old_cluster_id = question.cluster_id
        question.cluster_id = None
        question.learning_object_type = LearningObjectType.NOISE
        question.automation_status = QuestionOccurrenceStatus.AUTO_IGNORED
        question.automation_decision_source = AutomationDecisionSource.HUMAN
        question.automation_decision_reason = payload.reason
        question.automation_revision += 1
        if old_card_id is not None:
            await _refresh_card_stats(session, [old_card_id])
        await _reactivate_personal_items(session, [question.id])
        if old_cluster_id is not None:
            old_cluster = await session.get(QuestionCluster, old_cluster_id, with_for_update=True)
            if old_cluster is not None:
                old_cluster.membership_revision += 1
                old_cluster.version += 1
                await recalculate_cluster_stats(session, old_cluster, settings)
        return
    await _restore_occurrence_to_review(session, question, payload.reason)


async def _apply_cluster_override(
    session: AsyncSession,
    viewer: User,
    cluster: QuestionCluster,
    payload: AutomationDecisionOverrideMutation,
    original: AutomationDecision,
) -> None:
    settings = await _settings_model(session, cluster.direction_id)
    if payload.selected_card_id is not None:
        _require_admin(viewer)
        card = await _card_in_direction(session, payload.selected_card_id, cluster.direction_id)
        await _apply_cluster_card_link(
            session,
            viewer,
            cluster,
            card,
            settings,
            reason=payload.reason,
            confirm_alias=True,
        )
        cluster.status = QuestionClusterStatus.LINKED
        cluster.version += 1
        return
    if payload.selected_cluster_id is not None:
        _require_admin(viewer)
        target = await session.scalar(
            select(QuestionCluster)
            .where(
                QuestionCluster.id == payload.selected_cluster_id,
                QuestionCluster.direction_id == cluster.direction_id,
            )
            .with_for_update()
        )
        if target is None or target.id == cluster.id:
            api_error(404, "question_cluster_not_found", "Question cluster was not found")
        _ensure_action_allowed(target, QuestionClusterAction.MERGE)
        if target.learning_object_type is not cluster.learning_object_type:
            api_error(
                422,
                "question_cluster_type_mismatch",
                "Clusters with different learning object types cannot be merged",
            )
        questions = await _questions_in_cluster(session, cluster.id, lock=True)
        for question in questions:
            question.cluster_id = target.id
            question.automation_decision_source = AutomationDecisionSource.HUMAN
            question.automation_decision_reason = payload.reason
            question.automation_revision += 1
        cluster.status = QuestionClusterStatus.MERGED
        cluster.merged_into_cluster_id = target.id
        cluster.membership_revision += len(questions)
        cluster.version += 1
        target.membership_revision += len(questions)
        target.version += 1
        await recalculate_cluster_stats(session, cluster, settings)
        await recalculate_cluster_stats(session, target, settings)
        return
    if cluster.status is QuestionClusterStatus.MERGED:
        merge_decision = (
            original
            if original.decision_type is AutomationDecisionType.CLUSTER_MERGED
            else await session.scalar(
                select(AutomationDecision)
                .where(
                    AutomationDecision.entity_type == "cluster",
                    AutomationDecision.entity_id == cluster.id,
                    AutomationDecision.decision_type == AutomationDecisionType.CLUSTER_MERGED,
                )
                .order_by(AutomationDecision.created_at.desc())
            )
        )
        moved_ids = (
            _uuid_list(merge_decision.retrieval_scores.get("moved_occurrence_ids"))
            if merge_decision is not None
            else []
        )
        questions = (
            list(
                await session.scalars(
                    select(IntelligenceQuestion)
                    .where(
                        IntelligenceQuestion.id.in_(moved_ids),
                        IntelligenceQuestion.cluster_id == cluster.merged_into_cluster_id,
                    )
                    .with_for_update()
                )
            )
            if moved_ids
            else []
        )
        old_card_ids: list[UUID] = []
        for question in questions:
            old_card_id = await _unlink_occurrence_card(session, question)
            if old_card_id is not None:
                old_card_ids.append(old_card_id)
            question.cluster_id = cluster.id
            question.automation_status = QuestionOccurrenceStatus.NEEDS_REVIEW
            question.automation_decision_source = AutomationDecisionSource.HUMAN
            question.automation_decision_reason = payload.reason
            question.automation_revision += 1
        await _reactivate_personal_items(session, moved_ids)
        await _refresh_card_stats(session, old_card_ids)
        cluster.membership_revision += len(questions)
        if cluster.merged_into_cluster_id is not None:
            previous_target = await session.get(
                QuestionCluster,
                cluster.merged_into_cluster_id,
                with_for_update=True,
            )
            if previous_target is not None:
                previous_target.membership_revision += len(questions)
                previous_target.version += 1
                await recalculate_cluster_stats(session, previous_target, settings)
        cluster.linked_card_id = None
    elif cluster.status in {QuestionClusterStatus.LINKED, QuestionClusterStatus.CARD_CREATED}:
        questions = await _questions_in_cluster(session, cluster.id, lock=True)
        linked_card_ids: list[UUID] = []
        for question in questions:
            old_card_id = await _unlink_occurrence_card(session, question)
            if old_card_id is not None:
                linked_card_ids.append(old_card_id)
            question.automation_status = QuestionOccurrenceStatus.NEEDS_REVIEW
            question.automation_decision_source = AutomationDecisionSource.HUMAN
            question.automation_decision_reason = payload.reason
            question.automation_revision += 1
        await _reactivate_personal_items(session, [item.id for item in questions])
        await _refresh_card_stats(session, linked_card_ids)
        cluster.linked_card_id = None
    cluster.status = QuestionClusterStatus.NEEDS_REVIEW
    cluster.merged_into_cluster_id = None
    cluster.version += 1


def _ensure_override_compatible(
    original: AutomationDecision,
    payload: AutomationDecisionOverrideMutation,
) -> None:
    has_card = payload.selected_card_id is not None
    has_cluster = payload.selected_cluster_id is not None
    replacement = payload.replacement_decision_type
    if original.entity_type == "occurrence":
        if has_card:
            allowed_replacements = {
                AutomationDecisionType.EXACT_CARD_MATCH,
                AutomationDecisionType.ALIAS_CARD_MATCH,
                AutomationDecisionType.SEMANTIC_CARD_MATCH,
                AutomationDecisionType.MANUAL_OVERRIDE,
            }
        elif has_cluster:
            allowed_replacements = {
                AutomationDecisionType.CLUSTER_MATCH,
                AutomationDecisionType.MANUAL_OVERRIDE,
            }
        else:
            allowed_replacements = {
                AutomationDecisionType.MANUAL_OVERRIDE,
                AutomationDecisionType.QUESTION_ROUTED,
                AutomationDecisionType.ROUTED_AS_NOISE,
            }
        if replacement not in allowed_replacements:
            api_error(
                422,
                "automation_override_incompatible",
                "The replacement type is incompatible with this occurrence target",
            )
        return
    if original.entity_type == "cluster":
        if has_card:
            allowed_replacements = {
                AutomationDecisionType.CLUSTER_LINKED,
                AutomationDecisionType.MANUAL_OVERRIDE,
            }
        elif has_cluster:
            allowed_replacements = {
                AutomationDecisionType.CLUSTER_MERGED,
                AutomationDecisionType.MANUAL_OVERRIDE,
            }
        else:
            allowed_replacements = {
                AutomationDecisionType.MANUAL_OVERRIDE,
                AutomationDecisionType.CLUSTER_REOPENED,
            }
        if replacement not in allowed_replacements:
            api_error(
                422,
                "automation_override_incompatible",
                "The replacement type is incompatible with this cluster target",
            )
        return
    if original.entity_type == "personal_review_item" and (
        has_cluster or replacement is not AutomationDecisionType.MANUAL_OVERRIDE
    ):
        api_error(
            422,
            "automation_override_incompatible",
            "A personal review override supports only a manual reset or canonical card",
        )


async def override_automation_decision(
    session: AsyncSession,
    viewer: User,
    decision_id: UUID,
    payload: AutomationDecisionOverrideMutation,
) -> AutomationDecisionRead:
    original, direction_id = await _scoped_decision(session, viewer, decision_id, lock=True)
    _ensure_override_compatible(original, payload)
    key = f"manual:decision:{original.id}:override"
    existing = await _existing_action_decision(session, key)
    if existing is not None:
        expected_replacement = existing.retrieval_scores.get("replacement_decision_type")
        if (
            expected_replacement != payload.replacement_decision_type.value
            or existing.selected_card_id != payload.selected_card_id
            or existing.selected_cluster_id != payload.selected_cluster_id
            or existing.reason != payload.reason
        ):
            api_error(
                409,
                "automation_decision_already_overridden",
                "Automation decision has already been overridden differently",
            )
        return (await _decision_reads(session, [existing]))[0]
    if original.is_overridden:
        api_error(
            409,
            "automation_decision_already_overridden",
            "Automation decision has already been overridden",
        )
    superseding_decision_id = await session.scalar(
        select(AutomationDecision.id)
        .where(
            AutomationDecision.entity_type == original.entity_type,
            AutomationDecision.entity_id == original.entity_id,
            AutomationDecision.id != original.id,
            AutomationDecision.is_overridden.is_(False),
            AutomationDecision.created_at >= original.created_at,
        )
        .limit(1)
    )
    if superseding_decision_id is not None:
        api_error(
            409,
            "automation_decision_superseded",
            "A newer decision exists for this entity; reload the audit log",
        )
    if original.entity_type == "occurrence":
        question = await session.get(IntelligenceQuestion, original.entity_id, with_for_update=True)
        if question is None:
            api_error(404, "automation_decision_entity_not_found", "Decision entity disappeared")
        if question.automation_revision != payload.expected_entity_version:
            api_error(
                409,
                "automation_decision_entity_version_conflict",
                "The question occurrence changed; reload the audit log",
            )
        await _apply_occurrence_override(session, viewer, question, payload, direction_id)
    elif original.entity_type == "cluster":
        cluster = await session.get(QuestionCluster, original.entity_id, with_for_update=True)
        if cluster is None:
            api_error(404, "automation_decision_entity_not_found", "Decision entity disappeared")
        if cluster.version != payload.expected_entity_version:
            api_error(
                409,
                "automation_decision_entity_version_conflict",
                "The question cluster changed; reload the audit log",
            )
        await _apply_cluster_override(session, viewer, cluster, payload, original)
    elif original.entity_type == "personal_review_item":
        item = await session.get(PersonalReviewItem, original.entity_id, with_for_update=True)
        if item is None:
            api_error(404, "automation_decision_entity_not_found", "Decision entity disappeared")
        if item.version != payload.expected_entity_version:
            api_error(
                409,
                "automation_decision_entity_version_conflict",
                "The personal review item changed; reload the audit log",
            )
        if payload.selected_card_id is not None:
            await _card_in_direction(session, payload.selected_card_id, direction_id)
            item.canonical_card_id = payload.selected_card_id
            item.replaced_by_card_id = payload.selected_card_id
            item.status = PersonalReviewStatus.REPLACED_BY_CANONICAL_CARD
        elif payload.selected_cluster_id is not None:
            api_error(
                422,
                "automation_override_target_invalid",
                "A personal review item cannot target a cluster",
            )
        else:
            item.status = PersonalReviewStatus.ACTIVE
            item.canonical_card_id = None
            item.replaced_by_card_id = None
        item.version += 1
    else:
        api_error(422, "automation_decision_entity_invalid", "Unsupported decision entity")

    original.is_overridden = True
    original.overridden_by_user_id = viewer.id
    original.overridden_at = datetime.now(UTC)
    original.override_reason = payload.reason
    settings = await _settings_model(session, direction_id)
    manual = await record_automation_decision(
        session,
        entity_type=original.entity_type,
        entity_id=original.entity_id,
        idempotency_key=key,
        decision_type=AutomationDecisionType.MANUAL_OVERRIDE,
        decision_source=AutomationDecisionSource.HUMAN,
        reason=payload.reason,
        confidence=1.0,
        settings=settings,
        selected_card_id=payload.selected_card_id,
        selected_cluster_id=payload.selected_cluster_id,
        candidate_card_ids=(
            [payload.selected_card_id] if payload.selected_card_id is not None else None
        ),
        candidate_cluster_ids=(
            [payload.selected_cluster_id] if payload.selected_cluster_id is not None else None
        ),
        retrieval_scores={
            "overrides_decision_id": str(original.id),
            "replacement_decision_type": payload.replacement_decision_type.value,
            "actor_user_id": str(viewer.id),
        },
    )
    manual.reviewed_by_user_id = viewer.id
    manual.reviewed_at = datetime.now(UTC)
    manual.review_result = AutomationReviewResult.CORRECT
    manual.review_reason = payload.reason
    await session.commit()
    return (await _decision_reads(session, [manual]))[0]


def _personal_review_read(item: PersonalReviewItem, track: LearningTrack) -> PersonalReviewItemRead:
    return PersonalReviewItemRead(
        id=item.id,
        direction_id=item.direction_id,
        direction_slug=track.slug,
        direction_title=track.title,
        source_occurrence_id=item.source_occurrence_id,
        source_analysis_id=item.source_analysis_id,
        source_analysis_url=(
            f"/interviews/analysis/{item.source_analysis_id}"
            if item.source_analysis_id is not None
            else None
        ),
        canonical_card_id=item.canonical_card_id,
        replaced_by_card_id=item.replaced_by_card_id,
        question_text=item.question_text,
        answer_summary=item.answer_summary,
        answer_contract=_answer_contract(item.answer_contract),
        status=item.status,
        due_at=item.due_at,
        last_reviewed_at=item.last_reviewed_at,
        successful_reviews_count=item.successful_reviews_count,
        expires_at=item.expires_at,
        version=item.version,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _personal_review_snapshot(item: PersonalReviewItem) -> dict[str, object]:
    return {
        "question_text": item.question_text,
        "answer_summary": item.answer_summary,
        "answer_contract": item.answer_contract,
        "status": item.status.value,
        "due_at": item.due_at.isoformat(),
        "last_reviewed_at": (
            item.last_reviewed_at.isoformat() if item.last_reviewed_at is not None else None
        ),
        "successful_reviews_count": item.successful_reviews_count,
        "version": item.version,
    }


def _personal_correction_changes(
    payload: PersonalReviewItemCorrectionMutation,
) -> dict[str, object]:
    changes: dict[str, object] = {}
    editable_fields = {
        "question_text",
        "answer_summary",
        "answer_contract",
        "due_at",
        "status",
    }
    for field_name in payload.model_fields_set & editable_fields:
        value = getattr(payload, field_name)
        if isinstance(value, AnswerContract):
            changes[field_name] = value.model_dump(mode="json")
        elif isinstance(value, datetime):
            changes[field_name] = value.isoformat()
        elif isinstance(value, PersonalReviewStatus):
            changes[field_name] = value.value
        else:
            changes[field_name] = value
    return changes


async def _managed_personal_track_ids(
    session: AsyncSession, viewer: User, student_id: UUID
) -> set[UUID]:
    track_ids = await _allowed_track_ids(session, viewer)
    student_exists = await session.scalar(select(User.id).where(User.id == student_id))
    if student_exists is None:
        api_error(404, "student_not_found", "Student was not found")
    if viewer.role is UserRole.MENTOR:
        assignment = await session.scalar(
            select(MentorStudent.student_id).where(
                MentorStudent.mentor_id == viewer.id,
                MentorStudent.student_id == student_id,
            )
        )
        if assignment is None:
            api_error(404, "student_not_found", "Student was not found")
    return track_ids


async def list_personal_review_items(
    session: AsyncSession,
    viewer: User,
    filters: PersonalReviewItemListFilters,
) -> PersonalReviewItemPage:
    conditions: list[Any] = [PersonalReviewItem.student_id == viewer.id]
    if filters.direction_id is not None:
        conditions.append(PersonalReviewItem.direction_id == filters.direction_id)
    if filters.statuses:
        conditions.append(PersonalReviewItem.status.in_(filters.statuses))
    if filters.due_only:
        conditions.extend(
            [
                PersonalReviewItem.status == PersonalReviewStatus.ACTIVE,
                PersonalReviewItem.due_at <= (filters.due_before or datetime.now(UTC)),
            ]
        )
    elif filters.due_before is not None:
        conditions.append(PersonalReviewItem.due_at <= filters.due_before)
    total = int(
        await session.scalar(select(func.count(PersonalReviewItem.id)).where(*conditions)) or 0
    )
    order = (
        PersonalReviewItem.due_at.asc()
        if filters.sort_order == "asc"
        else PersonalReviewItem.due_at.desc()
    )
    rows = list(
        (
            await session.execute(
                select(PersonalReviewItem, LearningTrack)
                .join(LearningTrack, LearningTrack.id == PersonalReviewItem.direction_id)
                .where(*conditions)
                .order_by(order, PersonalReviewItem.id)
                .limit(filters.limit)
                .offset(filters.offset)
            )
        ).tuples()
    )
    return PersonalReviewItemPage(
        items=[_personal_review_read(item, track) for item, track in rows],
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


async def list_managed_personal_review_items(
    session: AsyncSession,
    viewer: User,
    student_id: UUID,
    filters: PersonalReviewItemListFilters,
) -> PersonalReviewItemPage:
    track_ids = await _managed_personal_track_ids(session, viewer, student_id)
    if filters.direction_id is not None:
        if filters.direction_id not in track_ids:
            api_error(404, "learning_track_not_found", "Learning track was not found")
        track_ids = {filters.direction_id}
    if not track_ids:
        return PersonalReviewItemPage(items=[], total=0, limit=filters.limit, offset=filters.offset)
    conditions: list[Any] = [
        PersonalReviewItem.student_id == student_id,
        PersonalReviewItem.direction_id.in_(track_ids),
    ]
    if filters.statuses:
        conditions.append(PersonalReviewItem.status.in_(filters.statuses))
    if filters.due_only:
        conditions.extend(
            [
                PersonalReviewItem.status == PersonalReviewStatus.ACTIVE,
                PersonalReviewItem.due_at <= (filters.due_before or datetime.now(UTC)),
            ]
        )
    elif filters.due_before is not None:
        conditions.append(PersonalReviewItem.due_at <= filters.due_before)
    total = int(
        await session.scalar(select(func.count(PersonalReviewItem.id)).where(*conditions)) or 0
    )
    order = (
        PersonalReviewItem.due_at.asc()
        if filters.sort_order == "asc"
        else PersonalReviewItem.due_at.desc()
    )
    rows = list(
        (
            await session.execute(
                select(PersonalReviewItem, LearningTrack)
                .join(LearningTrack, LearningTrack.id == PersonalReviewItem.direction_id)
                .where(*conditions)
                .order_by(order, PersonalReviewItem.id)
                .limit(filters.limit)
                .offset(filters.offset)
            )
        ).tuples()
    )
    return PersonalReviewItemPage(
        items=[_personal_review_read(item, track) for item, track in rows],
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


async def correct_personal_review_item(
    session: AsyncSession,
    viewer: User,
    student_id: UUID,
    item_id: UUID,
    payload: PersonalReviewItemCorrectionMutation,
) -> PersonalReviewItemCorrectionResult:
    track_ids = await _managed_personal_track_ids(session, viewer, student_id)
    row = (
        await session.execute(
            select(PersonalReviewItem, LearningTrack)
            .join(LearningTrack, LearningTrack.id == PersonalReviewItem.direction_id)
            .where(
                PersonalReviewItem.id == item_id,
                PersonalReviewItem.student_id == student_id,
                PersonalReviewItem.direction_id.in_(track_ids),
            )
            .with_for_update(of=PersonalReviewItem)
        )
    ).one_or_none()
    if row is None:
        api_error(404, "personal_review_item_not_found", "Personal review item was not found")
    item, track = row
    requested_changes = _personal_correction_changes(payload)
    idempotency_key = f"manual:personal-review:{item.id}:correct:v{payload.expected_version}"
    existing = await _existing_action_decision(session, idempotency_key)
    if existing is not None:
        if (
            existing.reason != payload.reason
            or existing.retrieval_scores.get("actor_user_id") != str(viewer.id)
            or existing.retrieval_scores.get("requested_changes") != requested_changes
        ):
            api_error(
                409,
                "personal_review_item_correction_conflict",
                "This item version was already corrected differently",
            )
        await session.commit()
        await session.refresh(item)
        return PersonalReviewItemCorrectionResult(
            item=_personal_review_read(item, track),
            decision_id=existing.id,
        )
    if item.version != payload.expected_version:
        api_error(
            409,
            "personal_review_item_version_conflict",
            "Personal review item changed; reload it and try again",
        )

    before = _personal_review_snapshot(item)
    changed_fields = payload.model_fields_set
    if "question_text" in changed_fields:
        if payload.question_text is None:
            api_error(422, "personal_review_question_invalid", "Question text cannot be empty")
        item.question_text = payload.question_text
    if "answer_summary" in changed_fields:
        item.answer_summary = payload.answer_summary
    if "answer_contract" in changed_fields:
        item.answer_contract = (
            payload.answer_contract.model_dump(mode="json")
            if payload.answer_contract is not None
            else None
        )
    if "due_at" in changed_fields:
        if payload.due_at is None:
            api_error(422, "personal_review_due_at_invalid", "Due date cannot be empty")
        item.due_at = payload.due_at
    if "status" in changed_fields:
        if payload.status is None:
            api_error(422, "personal_review_status_invalid", "Status cannot be empty")
        if (
            payload.status is PersonalReviewStatus.REPLACED_BY_CANONICAL_CARD
            and item.canonical_card_id is None
            and item.replaced_by_card_id is None
        ):
            api_error(
                422,
                "personal_review_replacement_card_required",
                "A replacement status requires a canonical card",
            )
        item.status = payload.status
        if payload.status is not PersonalReviewStatus.REPLACED_BY_CANONICAL_CARD:
            item.canonical_card_id = None
            item.replaced_by_card_id = None
    item.version += 1
    after = _personal_review_snapshot(item)
    settings = await _settings_model(session, item.direction_id)
    decision = await record_automation_decision(
        session,
        entity_type="personal_review_item",
        entity_id=item.id,
        idempotency_key=idempotency_key,
        decision_type=AutomationDecisionType.MANUAL_OVERRIDE,
        decision_source=AutomationDecisionSource.HUMAN,
        reason=payload.reason,
        confidence=1.0,
        settings=settings,
        selected_card_id=item.canonical_card_id,
        retrieval_scores={
            "actor_user_id": str(viewer.id),
            "student_id": str(student_id),
            "operation": "personal_review_correction",
            "requested_changes": requested_changes,
            "before": before,
            "after": after,
        },
    )
    decision.reviewed_by_user_id = viewer.id
    decision.reviewed_at = datetime.now(UTC)
    decision.review_result = AutomationReviewResult.CORRECT
    decision.review_reason = payload.reason
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        api_error(
            409,
            "personal_review_item_correction_conflict",
            "Personal review correction conflicts with another request",
        )
    await session.refresh(item)
    return PersonalReviewItemCorrectionResult(
        item=_personal_review_read(item, track),
        decision_id=decision.id,
    )


async def review_personal_review_item(
    session: AsyncSession,
    viewer: User,
    item_id: UUID,
    payload: PersonalReviewItemReviewMutation,
) -> PersonalReviewItemReviewResult:
    row = (
        await session.execute(
            select(PersonalReviewItem, LearningTrack)
            .join(LearningTrack, LearningTrack.id == PersonalReviewItem.direction_id)
            .where(
                PersonalReviewItem.id == item_id,
                PersonalReviewItem.student_id == viewer.id,
            )
            .with_for_update(of=PersonalReviewItem)
        )
    ).one_or_none()
    if row is None:
        api_error(404, "personal_review_item_not_found", "Personal review item was not found")
    item, track = row
    idempotency_key = (
        f"manual:personal-review:{item.id}:review:"
        f"v{payload.expected_version}:{payload.rating.value}"
    )
    existing = await _existing_action_decision(session, idempotency_key)
    if existing is not None:
        if (
            existing.retrieval_scores.get("actor_user_id") != str(viewer.id)
            or existing.retrieval_scores.get("rating") != payload.rating.value
        ):
            api_error(
                409,
                "personal_review_item_review_conflict",
                "This review version was already submitted differently",
            )
        became_mastered = existing.retrieval_scores.get("became_mastered") is True
        await session.commit()
        await session.refresh(item)
        return PersonalReviewItemReviewResult(
            item=_personal_review_read(item, track),
            rating=payload.rating,
            became_mastered=became_mastered,
        )
    if item.version != payload.expected_version:
        api_error(
            409,
            "personal_review_item_version_conflict",
            "Personal review item changed; reload it and try again",
        )
    if item.status is not PersonalReviewStatus.ACTIVE:
        api_error(
            409,
            "personal_review_item_not_active",
            "Only active personal review items can be reviewed",
        )
    before = _personal_review_snapshot(item)
    now = datetime.now(UTC)
    due_at, successful_count, mastered = next_personal_review(
        payload.rating,
        item.successful_reviews_count,
        now=now,
    )
    item.due_at = due_at
    item.successful_reviews_count = successful_count
    item.last_reviewed_at = now
    item.version += 1
    if mastered:
        item.status = PersonalReviewStatus.MASTERED
    after = _personal_review_snapshot(item)
    settings = await _settings_model(session, item.direction_id)
    reason = f"Student reviewed personal item as {payload.rating.value}"
    decision = await record_automation_decision(
        session,
        entity_type="personal_review_item",
        entity_id=item.id,
        idempotency_key=idempotency_key,
        decision_type=AutomationDecisionType.PERSONAL_REVIEW_REVIEWED,
        decision_source=AutomationDecisionSource.HUMAN,
        reason=reason,
        confidence=1.0,
        settings=settings,
        selected_card_id=item.canonical_card_id,
        retrieval_scores={
            "actor_user_id": str(viewer.id),
            "rating": payload.rating.value,
            "became_mastered": mastered,
            "before": before,
            "after": after,
        },
    )
    decision.reviewed_by_user_id = viewer.id
    decision.reviewed_at = now
    decision.review_result = AutomationReviewResult.CORRECT
    decision.review_reason = reason
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        api_error(
            409,
            "personal_review_item_review_conflict",
            "Personal review conflicts with another request",
        )
    await session.refresh(item)
    return PersonalReviewItemReviewResult(
        item=_personal_review_read(item, track),
        rating=payload.rating,
        became_mastered=mastered,
    )


def _period_bounds(period_from: date, period_to: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(period_from, time.min, tzinfo=UTC),
        datetime.combine(period_to + timedelta(days=1), time.min, tzinfo=UTC),
    )


async def _decision_count(
    session: AsyncSession,
    conditions: Sequence[Any],
    *extra_conditions: Any,
    distinct_entities: bool = False,
) -> int:
    count_expression = (
        func.count(func.distinct(AutomationDecision.entity_id))
        if distinct_entities
        else func.count(AutomationDecision.id)
    )
    return int(
        await session.scalar(select(count_expression).where(*conditions, *extra_conditions)) or 0
    )


async def get_card_automation_metrics(
    session: AsyncSession,
    viewer: User,
    filters: CardAutomationMetricsFilters,
) -> CardAutomationMetricsRead:
    track_ids = await _allowed_track_ids(session, viewer)
    direction_slug: str | None = None
    if filters.direction_id is not None:
        if filters.direction_id not in track_ids:
            api_error(404, "learning_track_not_found", "Learning track was not found")
        track_ids = {filters.direction_id}
        direction_slug = await session.scalar(
            select(LearningTrack.slug).where(LearningTrack.id == filters.direction_id)
        )
    start_at, end_at = _period_bounds(filters.period_from, filters.period_to)
    question_conditions = [
        IntelligenceQuestion.direction_id.in_(track_ids),
        IntelligenceQuestion.created_at >= start_at,
        IntelligenceQuestion.created_at < end_at,
    ]
    extracted_questions_total = int(
        await session.scalar(
            select(func.count(IntelligenceQuestion.id)).where(*question_conditions)
        )
        or 0
    )
    interview_conditions = [
        InterviewProcess.track_id.in_(track_ids),
        IntelligenceInterview.created_at >= start_at,
        IntelligenceInterview.created_at < end_at,
    ]
    interviews_total = int(
        await session.scalar(
            select(func.count(IntelligenceInterview.id))
            .join(InterviewProcessStage, InterviewProcessStage.id == IntelligenceInterview.stage_id)
            .join(InterviewProcess, InterviewProcess.id == InterviewProcessStage.process_id)
            .where(*interview_conditions)
        )
        or 0
    )
    decision_conditions = [
        _decision_scope_condition(track_ids),
        AutomationDecision.created_at >= start_at,
        AutomationDecision.created_at < end_at,
    ]
    routed_as_noise_total = await _decision_count(
        session,
        decision_conditions,
        AutomationDecision.decision_type == AutomationDecisionType.ROUTED_AS_NOISE,
    )
    routed_as_non_flashcard_total = await _decision_count(
        session,
        decision_conditions,
        AutomationDecision.decision_type == AutomationDecisionType.ROUTED_AS_NON_FLASHCARD,
    )
    auto_linked_exact_total = await _decision_count(
        session,
        decision_conditions,
        AutomationDecision.decision_type == AutomationDecisionType.EXACT_CARD_MATCH,
        AutomationDecision.retrieval_scores.contains({"applied": True}),
    )
    auto_linked_alias_total = await _decision_count(
        session,
        decision_conditions,
        AutomationDecision.decision_type == AutomationDecisionType.ALIAS_CARD_MATCH,
        AutomationDecision.retrieval_scores.contains({"applied": True}),
    )
    auto_linked_semantic_total = await _decision_count(
        session,
        decision_conditions,
        AutomationDecision.decision_type == AutomationDecisionType.SEMANTIC_CARD_MATCH,
        AutomationDecision.selected_card_id.is_not(None),
        AutomationDecision.retrieval_scores.contains({"applied": True}),
    )
    shadow_clusters_created_total = await _decision_count(
        session,
        decision_conditions,
        AutomationDecision.decision_type == AutomationDecisionType.SHADOW_CLUSTER_CREATED,
    )
    clusters_promoted_total = await _decision_count(
        session,
        decision_conditions,
        AutomationDecision.decision_type == AutomationDecisionType.CLUSTER_PROMOTED,
    )
    clusters_reviewed_total = await _decision_count(
        session,
        decision_conditions,
        AutomationDecision.decision_source == AutomationDecisionSource.HUMAN,
        AutomationDecision.decision_type.in_(_HUMAN_CLUSTER_OUTCOMES),
        distinct_entities=True,
    )
    personal_review_items_created_total = int(
        await session.scalar(
            select(func.count(PersonalReviewItem.id)).where(
                PersonalReviewItem.direction_id.in_(track_ids),
                PersonalReviewItem.created_at >= start_at,
                PersonalReviewItem.created_at < end_at,
            )
        )
        or 0
    )
    auto_conditions = [
        *decision_conditions,
        AutomationDecision.decision_source != AutomationDecisionSource.HUMAN,
    ]
    automatic_decisions_total = await _decision_count(session, auto_conditions)
    overridden_total = await _decision_count(
        session, auto_conditions, AutomationDecision.is_overridden.is_(True)
    )
    reviewed_merge_total = await _decision_count(
        session,
        decision_conditions,
        AutomationDecision.decision_type.in_(
            {AutomationDecisionType.CLUSTER_MATCH, AutomationDecisionType.CLUSTER_MERGED}
        ),
        AutomationDecision.reviewed_at.is_not(None),
    )
    false_merge_total = await _decision_count(
        session,
        decision_conditions,
        AutomationDecision.decision_type.in_(
            {AutomationDecisionType.CLUSTER_MATCH, AutomationDecisionType.CLUSTER_MERGED}
        ),
        AutomationDecision.review_result == AutomationReviewResult.MERGE_ERROR,
    )
    reviewed_noise_total = await _decision_count(
        session,
        decision_conditions,
        AutomationDecision.decision_type == AutomationDecisionType.ROUTED_AS_NOISE,
        AutomationDecision.reviewed_at.is_not(None),
    )
    false_noise_total = await _decision_count(
        session,
        decision_conditions,
        AutomationDecision.decision_type == AutomationDecisionType.ROUTED_AS_NOISE,
        AutomationDecision.review_result == AutomationReviewResult.CLASSIFICATION_ERROR,
    )
    average_moderation = await session.scalar(
        select(
            func.avg(
                func.extract("epoch", AutomationDecision.created_at - QuestionCluster.promoted_at)
            )
        )
        .join(
            QuestionCluster,
            and_(
                AutomationDecision.entity_type == "cluster",
                AutomationDecision.entity_id == QuestionCluster.id,
            ),
        )
        .where(
            QuestionCluster.direction_id.in_(track_ids),
            QuestionCluster.promoted_at.is_not(None),
            AutomationDecision.decision_source == AutomationDecisionSource.HUMAN,
            AutomationDecision.decision_type.in_(_HUMAN_CLUSTER_OUTCOMES),
            AutomationDecision.created_at >= start_at,
            AutomationDecision.created_at < end_at,
        )
    )
    oldest_promoted_at = await session.scalar(
        select(func.min(QuestionCluster.promoted_at)).where(
            QuestionCluster.direction_id.in_(track_ids),
            QuestionCluster.status == QuestionClusterStatus.NEEDS_REVIEW,
            QuestionCluster.promoted_at.is_not(None),
        )
    )
    total_ai_cost = cast(
        Decimal | None,
        await session.scalar(
            select(func.sum(AutomationDecision.cost)).where(
                *decision_conditions,
                AutomationDecision.cost.is_not(None),
            )
        ),
    ) or Decimal("0")
    now = datetime.now(UTC)
    oldest_age = (
        max((now - oldest_promoted_at).total_seconds(), 0.0)
        if oldest_promoted_at is not None
        else 0.0
    )

    def rate(numerator: int, denominator: int) -> float:
        return numerator / denominator if denominator else 0.0

    def average_cost(denominator: int) -> Decimal:
        return total_ai_cost / denominator if denominator else Decimal("0")

    return CardAutomationMetricsRead(
        period_from=filters.period_from,
        period_to=filters.period_to,
        direction_id=filters.direction_id,
        direction_slug=direction_slug,
        extracted_questions_total=extracted_questions_total,
        routed_as_noise_total=routed_as_noise_total,
        routed_as_non_flashcard_total=routed_as_non_flashcard_total,
        auto_linked_exact_total=auto_linked_exact_total,
        auto_linked_alias_total=auto_linked_alias_total,
        auto_linked_semantic_total=auto_linked_semantic_total,
        shadow_clusters_created_total=shadow_clusters_created_total,
        clusters_promoted_total=clusters_promoted_total,
        clusters_reviewed_total=clusters_reviewed_total,
        personal_review_items_created_total=personal_review_items_created_total,
        manual_tasks_per_100_interviews=(
            clusters_promoted_total * 100 / interviews_total if interviews_total else 0.0
        ),
        average_cluster_moderation_time=float(average_moderation or 0.0),
        oldest_moderation_task_age=oldest_age,
        automatic_decision_override_rate=rate(overridden_total, automatic_decisions_total),
        false_merge_rate=rate(false_merge_total, reviewed_merge_total),
        noise_false_positive_rate=rate(false_noise_total, reviewed_noise_total),
        average_ai_cost_per_interview=average_cost(interviews_total),
        average_ai_cost_per_question=average_cost(extracted_questions_total),
        average_ai_cost_per_promoted_cluster=average_cost(clusters_promoted_total),
        generated_at=now,
    )
