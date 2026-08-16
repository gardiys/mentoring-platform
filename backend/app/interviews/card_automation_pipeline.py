from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.interviews.card_automation_domain import (
    audit_sample,
    ensure_occurrence_transition,
    fallback_route,
    is_failed_answer,
    match_gate,
    priority_score,
    promotion_result,
)
from app.interviews.card_automation_models import (
    AutomationDecision,
    CardAutomationSettings,
    PersonalReviewItem,
    QuestionCluster,
)
from app.interviews.card_automation_privacy import redact_untrusted_text
from app.interviews.card_automation_schemas import AnswerContract
from app.interviews.card_automation_types import (
    ALLOWED_QUALITY_FLAGS,
    CARD_ELIGIBLE_TYPES,
    AutomationDecisionSource,
    AutomationDecisionType,
    LearningObjectType,
    PersonalReviewStatus,
    QuestionClusterStatus,
    QuestionOccurrenceStatus,
)
from app.interviews.card_frequency import refresh_card_frequency
from app.interviews.intelligence_ai import (
    PAIRWISE_CARD_MATCH_PROMPT_VERSION,
    PAIRWISE_CARD_MATCH_SCHEMA_VERSION,
    QUESTION_ROUTING_PROMPT_VERSION,
    QUESTION_ROUTING_SCHEMA_VERSION,
    InterviewAIError,
    InterviewAIProvider,
)
from app.interviews.intelligence_models import (
    IntelligenceAnswer,
    IntelligenceAnswerReview,
    IntelligenceAssessment,
    IntelligenceInterview,
    IntelligenceQuestion,
    IntelligenceQuestionModerationStatus,
    IntelligenceReviewSource,
    IntelligenceReviewStatus,
    IntelligenceUtterance,
)
from app.interviews.models import (
    InterviewCard,
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
    normalize_question,
    rank_question_candidates,
)
from app.users.models import User

logger = logging.getLogger(__name__)
AUTOMATION_SCHEMA_VERSION = "card-automation-v1"
OCCURRENCE_ACCEPTING_CLUSTER_STATUSES = frozenset(
    {
        QuestionClusterStatus.SHADOW,
        QuestionClusterStatus.CANDIDATE,
        QuestionClusterStatus.NEEDS_REVIEW,
        QuestionClusterStatus.DEFERRED,
    }
)


@dataclass(frozen=True, slots=True)
class OccurrenceSnapshot:
    question_id: UUID
    revision: int
    interview_id: UUID
    student_id: UUID
    direction_id: UUID
    question_text: str
    answer_text: str
    source_context: str
    question_kind: Any
    extraction_confidence: float
    sensitive_values: tuple[str, ...]
    available_broad_topics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RoutingData:
    learning_object_type: LearningObjectType
    is_real_interviewer_question: bool
    is_standalone: bool
    canonical_text: str | None
    answer_scope: tuple[str, ...]
    broad_topic: str | None
    detailed_subtopic: str | None
    topic_candidates: tuple[str, ...]
    quality_flags: tuple[str, ...]
    confidence: float
    reasoning_summary: str
    decision_source: AutomationDecisionSource
    usage: Any | None
    prompt_version: str | None
    schema_version: str | None
    input_hash: str
    latency_ms: int | None


@dataclass(frozen=True, slots=True)
class CardCandidateSnapshot:
    card_id: UUID
    deck_id: UUID
    question: str
    answer: str
    category: str
    score: float
    match_type: str
    matched_source: str
    matched_text: str


@dataclass(frozen=True, slots=True)
class JudgedMatch:
    result: Any
    input_hash: str
    latency_ms: int | None


def answer_contract_from_analysis_draft(answer: str) -> dict[str, object]:
    """Build an explicitly unverified moderation draft from interview AI feedback."""

    return AnswerContract(
        short_answer=answer,
        required_points=[],
        optional_points=[],
        common_mistakes=[],
        unsupported_claims=["Ответ перенесён из AI-разбора собеседования и требует проверки."],
        follow_up_questions=[],
        difficulty="mixed",
        version_scope=[],
        source_references=[],
        confidence=0.5,
    ).model_dump(mode="json")


async def process_question_occurrence(
    session_factory: async_sessionmaker[AsyncSession],
    ai: InterviewAIProvider,
    question_id: UUID,
    revision: int,
    *,
    retryable_failure_is_terminal: bool = False,
) -> None:
    """Run one occurrence through the safe, resumable automation pipeline.

    Provider calls happen only after the claiming transaction has committed.
    Each finalize step compares ``automation_revision`` so an admin reprocess or
    override cannot be overwritten by a stale worker.
    """

    snapshot = await _claim_occurrence(session_factory, question_id, revision)
    if snapshot is None:
        return
    ai_stage = "routing"
    try:
        routing = await _route(session_factory, ai, snapshot)
        phase = await _store_routing(session_factory, snapshot, routing)
        if phase != "search_card":
            return
        candidates, settings = await _card_candidates(session_factory, snapshot)
        exact = next((item for item in candidates if item.match_type == "exact"), None)
        if exact is not None:
            source = (
                AutomationDecisionSource.CONFIRMED_ALIAS
                if exact.matched_source == "approved_alias"
                else AutomationDecisionSource.EXACT
            )
            decision_type = (
                AutomationDecisionType.ALIAS_CARD_MATCH
                if source is AutomationDecisionSource.CONFIRMED_ALIAS
                else AutomationDecisionType.EXACT_CARD_MATCH
            )
            enabled = (
                settings.auto_link_alias_enabled
                if source is AutomationDecisionSource.CONFIRMED_ALIAS
                else settings.auto_link_exact_enabled
            )
            await _record_card_match(
                session_factory,
                snapshot,
                exact,
                candidates,
                settings,
                decision_type=decision_type,
                decision_source=source,
                reason="Exact normalized match with a trusted card wording",
                confidence=1.0,
                apply_link=enabled and not settings.shadow_mode,
            )
            # An exact trusted wording is already represented by this card.
            # When live linking is disabled it remains a terminal proposal;
            # creating a duplicate shadow cluster would be misleading.
            return

        semantic = [item for item in candidates if item.match_type != "exact"]
        if semantic and semantic[0].score >= settings.semantic_similarity_threshold:
            top = semantic[0]
            second_score = semantic[1].score if len(semantic) > 1 else None
            ai_stage = "pairwise_card_match"
            judged = await _cached_or_judged_match(
                session_factory,
                ai,
                snapshot,
                top,
                settings,
            )
            output = judged.result.output
            gate = match_gate(
                learning_object_type=routing.learning_object_type,
                quality_flags=routing.quality_flags,
                semantic_score=top.score,
                second_score=second_score,
                semantic_threshold=settings.semantic_similarity_threshold,
                judge_decision=output.decision,
                judge_confidence=output.confidence,
                judge_threshold=settings.pairwise_judge_confidence_threshold,
                score_gap_threshold=settings.candidate_score_gap_threshold,
                direction_matches=True,
            )
            await _record_card_match(
                session_factory,
                snapshot,
                top,
                semantic,
                settings,
                decision_type=AutomationDecisionType.SEMANTIC_CARD_MATCH,
                decision_source=AutomationDecisionSource.SEMANTIC_JUDGE,
                reason=gate.reason,
                confidence=output.confidence,
                apply_link=(
                    gate.accepted
                    and settings.auto_link_semantic_enabled
                    and not settings.shadow_mode
                ),
                finalize_proposal=gate.accepted,
                judge_result=output.model_dump(mode="json"),
                usage=judged.result.usage,
                ai_tier="light",
                prompt_version=getattr(judged.result, "prompt_version", None),
                schema_version=getattr(judged.result, "schema_version", None),
                input_hash=judged.input_hash,
                latency_ms=judged.latency_ms,
            )
            # A judge-confirmed semantic match is already represented by the
            # existing card. With live linking disabled it is a terminal
            # proposal, not a reason to create a duplicate shadow cluster.
            if gate.accepted:
                return

        await _cluster_occurrence(session_factory, snapshot, settings)
    except InterviewAIError as error:
        retry_budget_exhausted = error.retryable and retryable_failure_is_terminal
        await _mark_failed(
            session_factory,
            snapshot,
            reason=(
                f"{error.code}: Retry budget exhausted: {error.safe_message}"
                if retry_budget_exhausted
                else f"{error.code}: {error.safe_message}"
            ),
            error_code=error.code,
            retryable=error.retryable and not retry_budget_exhausted,
            decision_source=(
                AutomationDecisionSource.AI_ROUTING
                if ai_stage == "routing"
                else AutomationDecisionSource.SEMANTIC_JUDGE
            ),
            schema_version=(
                QUESTION_ROUTING_SCHEMA_VERSION
                if ai_stage == "routing"
                else PAIRWISE_CARD_MATCH_SCHEMA_VERSION
            ),
            stage=ai_stage,
        )
        raise
    except Exception:
        logger.exception("Card automation failed question_id=%s revision=%s", question_id, revision)
        await _mark_failed(
            session_factory,
            snapshot,
            reason="automation_processing_failed: Automation processing failed",
            error_code="automation_processing_failed",
            retryable=False,
            decision_source=AutomationDecisionSource.RULE,
            schema_version=None,
            stage="pipeline",
        )
        raise


async def _claim_occurrence(
    session_factory: async_sessionmaker[AsyncSession], question_id: UUID, revision: int
) -> OccurrenceSnapshot | None:
    async with session_factory() as session:
        question = await session.scalar(
            select(IntelligenceQuestion)
            .where(IntelligenceQuestion.id == question_id)
            .with_for_update()
        )
        if question is None or question.automation_revision != revision:
            return None
        if question.automation_status in {
            QuestionOccurrenceStatus.AUTO_LINKED,
            QuestionOccurrenceStatus.AUTO_IGNORED,
            QuestionOccurrenceStatus.ROUTED,
            QuestionOccurrenceStatus.CLUSTERED,
            QuestionOccurrenceStatus.NEEDS_REVIEW,
            QuestionOccurrenceStatus.PERSONAL_ONLY,
        }:
            return None
        if (
            question.moderation_status is not IntelligenceQuestionModerationStatus.PENDING
            or question.alias_human_confirmed
        ):
            return None
        interview = await session.get(IntelligenceInterview, question.interview_id)
        stage = await session.get(InterviewProcessStage, interview.stage_id) if interview else None
        process = await session.get(InterviewProcess, stage.process_id) if stage else None
        if interview is None or process is None:
            _set_occurrence_status(question, QuestionOccurrenceStatus.FAILED)
            question.automation_error = "Interview process is missing"
            await session.commit()
            return None
        settings = await _settings(session, process.track_id)
        if not settings.enabled:
            return None
        answer = await session.scalar(
            select(IntelligenceAnswer).where(IntelligenceAnswer.question_id == question.id)
        )
        student = await session.get(User, interview.student_id)
        sensitive_values = _student_sensitive_values(student)
        context = await _minimal_context(session, question)
        available_broad_topics = tuple(
            dict.fromkeys(
                await session.scalars(
                    select(InterviewCard.category)
                    .join(InterviewDeck, InterviewDeck.id == InterviewCard.deck_id)
                    .where(
                        InterviewDeck.track_id == process.track_id,
                        InterviewDeck.is_published.is_(True),
                        InterviewCard.is_published.is_(True),
                    )
                    .order_by(InterviewCard.category)
                )
            )
        )
        question.direction_id = process.track_id
        question.normalized_question_text = normalize_question(question.question_text)
        question.source_context = context
        _set_occurrence_status(question, QuestionOccurrenceStatus.ROUTING)
        question.automation_error = None
        question.automation_attempts += 1
        await session.commit()
        return OccurrenceSnapshot(
            question_id=question.id,
            revision=question.automation_revision,
            interview_id=question.interview_id,
            student_id=interview.student_id,
            direction_id=process.track_id,
            question_text=question.question_text,
            answer_text=answer.answer_text if answer else "",
            source_context=context,
            question_kind=question.question_kind,
            extraction_confidence=question.confidence,
            sensitive_values=sensitive_values,
            available_broad_topics=available_broad_topics,
        )


async def _route(
    session_factory: async_sessionmaker[AsyncSession],
    ai: InterviewAIProvider,
    snapshot: OccurrenceSnapshot,
) -> RoutingData:
    safe_question = redact_untrusted_text(
        snapshot.question_text,
        snapshot.sensitive_values,
    )
    safe_answer = redact_untrusted_text(
        snapshot.answer_text,
        snapshot.sensitive_values,
    )
    safe_context = redact_untrusted_text(
        snapshot.source_context,
        snapshot.sensitive_values,
    )
    input_hash = _hash(
        safe_question,
        safe_answer,
        safe_context,
        "\n".join(snapshot.available_broad_topics),
        QUESTION_ROUTING_PROMPT_VERSION,
        QUESTION_ROUTING_SCHEMA_VERSION,
        _provider_model_name(ai, "light"),
    )
    fallback = fallback_route(
        snapshot.question_text,
        snapshot.question_kind,
        snapshot.extraction_confidence,
    )
    # High-confidence deterministic filters avoid paying for obvious noise and
    # already classified HR/organizational content.
    if fallback.learning_object_type not in CARD_ELIGIBLE_TYPES and fallback.confidence >= 0.9:
        return RoutingData(
            fallback.learning_object_type,
            fallback.is_real_interviewer_question,
            fallback.is_standalone,
            None,
            (),
            None,
            None,
            (),
            fallback.quality_flags,
            fallback.confidence,
            fallback.reason,
            AutomationDecisionSource.RULE,
            None,
            None,
            None,
            input_hash,
            None,
        )
    async with session_factory() as session:
        cached = await session.scalar(
            select(AutomationDecision)
            .where(
                AutomationDecision.input_hash == input_hash,
                AutomationDecision.decision_type.in_(
                    {
                        AutomationDecisionType.QUESTION_ROUTED,
                        AutomationDecisionType.ROUTED_AS_NOISE,
                        AutomationDecisionType.ROUTED_AS_NON_FLASHCARD,
                    }
                ),
                AutomationDecision.decision_source == AutomationDecisionSource.AI_ROUTING,
                AutomationDecision.is_overridden.is_(False),
                AutomationDecision.judge_result.is_not(None),
            )
            .order_by(AutomationDecision.created_at.desc())
        )
    if cached is not None and isinstance(cached.judge_result, dict):
        payload = cached.judge_result
        try:
            return RoutingData(
                LearningObjectType(str(payload["learning_object_type"])),
                bool(payload["is_real_interviewer_question"]),
                bool(payload["is_standalone"]),
                str(payload["canonical_text"]) if payload.get("canonical_text") else None,
                _string_tuple(payload.get("answer_scope")),
                (str(payload["broad_topic"]) if payload.get("broad_topic") else None),
                (str(payload["detailed_subtopic"]) if payload.get("detailed_subtopic") else None),
                _string_tuple(payload.get("topic_candidates")),
                tuple(
                    item
                    for item in _string_tuple(payload.get("quality_flags"))
                    if item in ALLOWED_QUALITY_FLAGS
                ),
                float(cached.confidence or 0),
                cached.reason,
                AutomationDecisionSource.AI_ROUTING,
                None,
                cached.prompt_version,
                cached.schema_version,
                input_hash,
                None,
            )
        except (KeyError, TypeError, ValueError):
            logger.warning(
                "Ignoring invalid cached routing decision decision_id=%s",
                cached.id,
            )
    started_at = time.perf_counter()
    result = await ai.route_question(
        question=safe_question[:4_000],
        candidate_answer=safe_answer[:6_000],
        context=safe_context[:6_000],
        available_broad_topics=list(snapshot.available_broad_topics),
    )
    latency_ms = _elapsed_ms(started_at)
    output = result.output
    flags = tuple(flag for flag in output.quality_flags if flag in ALLOWED_QUALITY_FLAGS)
    available_by_normalized = {
        _normalized_topic(item): item for item in snapshot.available_broad_topics
    }
    broad_topic = (
        available_by_normalized.get(_normalized_topic(output.broad_topic))
        if output.broad_topic
        else None
    )
    detailed_subtopic = output.detailed_subtopic.strip() if output.detailed_subtopic else None
    if (
        detailed_subtopic
        and broad_topic
        and _normalized_topic(detailed_subtopic) == _normalized_topic(broad_topic)
    ):
        detailed_subtopic = None
    topic_candidates = _unique_topic_labels(
        ([broad_topic] if broad_topic else [])
        + (list(output.topic_candidates) if broad_topic else [])
    )
    return RoutingData(
        output.learning_object_type,
        output.is_real_interviewer_question,
        output.is_standalone,
        output.canonical_text,
        tuple(output.answer_scope),
        broad_topic,
        detailed_subtopic,
        topic_candidates,
        flags,
        output.confidence,
        output.reasoning_summary,
        AutomationDecisionSource.AI_ROUTING,
        result.usage,
        getattr(result, "prompt_version", None),
        getattr(result, "schema_version", None),
        input_hash,
        latency_ms,
    )


async def _store_routing(
    session_factory: async_sessionmaker[AsyncSession],
    snapshot: OccurrenceSnapshot,
    routing: RoutingData,
) -> str:
    async with session_factory() as session:
        question = await _locked_current(session, snapshot)
        if question is None:
            return "stale"
        settings = await _settings(session, snapshot.direction_id)
        question.learning_object_type = routing.learning_object_type
        question.is_real_interviewer_question = routing.is_real_interviewer_question
        question.is_standalone = routing.is_standalone
        question.canonical_question_candidate = routing.canonical_text
        question.answer_scope = list(routing.answer_scope)
        question.topic_candidates = list(routing.topic_candidates)
        if routing.broad_topic is not None:
            question.category = routing.broad_topic
        question.subcategory = routing.detailed_subtopic
        question.quality_flags = list(routing.quality_flags)
        question.routing_confidence = routing.confidence
        question.automation_decision_source = routing.decision_source
        question.automation_decision_reason = routing.reasoning_summary

        if (
            routing.learning_object_type not in CARD_ELIGIBLE_TYPES
            or not routing.is_real_interviewer_question
            or not routing.is_standalone
        ):
            is_noise = routing.learning_object_type is LearningObjectType.NOISE
            live_ignore = not settings.shadow_mode and (
                not is_noise or settings.auto_ignore_noise_enabled
            )
            target_status = (
                QuestionOccurrenceStatus.AUTO_IGNORED
                if live_ignore
                else QuestionOccurrenceStatus.ROUTED
            )
            _set_occurrence_status(question, target_status)
            question.processed_at = datetime.now(UTC)
            decision_type = (
                AutomationDecisionType.ROUTED_AS_NOISE
                if is_noise
                else AutomationDecisionType.ROUTED_AS_NON_FLASHCARD
            )
        else:
            _set_occurrence_status(question, QuestionOccurrenceStatus.SEARCHING_CARD)
            decision_type = AutomationDecisionType.QUESTION_ROUTED
        await record_automation_decision(
            session,
            entity_type="occurrence",
            entity_id=question.id,
            idempotency_key=(f"occurrence:{question.id}:revision:{snapshot.revision}:routing"),
            decision_type=decision_type,
            decision_source=routing.decision_source,
            reason=routing.reasoning_summary,
            confidence=routing.confidence,
            settings=settings,
            judge_result={
                "learning_object_type": routing.learning_object_type.value,
                "is_real_interviewer_question": routing.is_real_interviewer_question,
                "is_standalone": routing.is_standalone,
                "canonical_text": routing.canonical_text,
                "answer_scope": list(routing.answer_scope),
                "broad_topic": routing.broad_topic,
                "detailed_subtopic": routing.detailed_subtopic,
                "topic_candidates": list(routing.topic_candidates),
                "quality_flags": list(routing.quality_flags),
            },
            usage=routing.usage,
            ai_tier="light" if routing.usage is not None else None,
            prompt_version=routing.prompt_version,
            schema_version=routing.schema_version,
            input_hash=routing.input_hash,
            latency_ms=routing.latency_ms,
        )
        await session.commit()
        return (
            "search_card"
            if question.automation_status is QuestionOccurrenceStatus.SEARCHING_CARD
            else "done"
        )


async def _card_candidates(
    session_factory: async_sessionmaker[AsyncSession], snapshot: OccurrenceSnapshot
) -> tuple[list[CardCandidateSnapshot], CardAutomationSettings]:
    async with session_factory() as session:
        settings = await _settings(session, snapshot.direction_id)
        question = await session.get(IntelligenceQuestion, snapshot.question_id)
        if question is None:
            return [], settings
        cards = list(
            await session.scalars(
                select(InterviewCard)
                .join(InterviewDeck, InterviewDeck.id == InterviewCard.deck_id)
                .where(
                    InterviewDeck.track_id == snapshot.direction_id,
                    InterviewDeck.is_published.is_(True),
                    InterviewCard.is_published.is_(True),
                )
            )
        )
        if not cards:
            return [], settings
        aliases = list(
            await session.scalars(
                select(IntelligenceQuestion).where(
                    IntelligenceQuestion.published_card_id.in_([card.id for card in cards]),
                    IntelligenceQuestion.moderation_status
                    == IntelligenceQuestionModerationStatus.APPROVED,
                    IntelligenceQuestion.alias_human_confirmed.is_(True),
                )
            )
        )
        aliases_by_card: dict[UUID, list[IntelligenceQuestion]] = {}
        for alias in aliases:
            if alias.published_card_id is not None:
                aliases_by_card.setdefault(alias.published_card_id, []).append(alias)
        ranked = rank_question_candidates(
            question.question_text,
            question.question_embedding,
            [
                QuestionCandidate(
                    card_id=card.id,
                    asked_count=card.asked_count,
                    variants=(
                        QuestionVariant(
                            card.question_markdown,
                            tuple(card.question_embedding) if card.question_embedding else None,
                            "card",
                        ),
                        *(
                            QuestionVariant(
                                alias.question_text,
                                tuple(alias.question_embedding)
                                if alias.question_embedding
                                else None,
                                "approved_alias",
                            )
                            for alias in aliases_by_card.get(card.id, [])
                        ),
                    ),
                )
                for card in cards
            ],
            limit=5,
        )
        by_id = {card.id: card for card in cards}
        return [
            CardCandidateSnapshot(
                card_id=item.card_id,
                deck_id=by_id[item.card_id].deck_id,
                question=by_id[item.card_id].question_markdown,
                answer=by_id[item.card_id].answer_markdown,
                category=by_id[item.card_id].category,
                score=item.similarity,
                match_type=item.match_type,
                matched_source=item.matched_source,
                matched_text=item.matched_text,
            )
            for item in ranked
        ], settings


async def _cached_or_judged_match(
    session_factory: async_sessionmaker[AsyncSession],
    ai: InterviewAIProvider,
    snapshot: OccurrenceSnapshot,
    candidate: CardCandidateSnapshot,
    settings: CardAutomationSettings,
) -> JudgedMatch:
    safe_question = redact_untrusted_text(
        snapshot.question_text,
        snapshot.sensitive_values,
    )
    safe_scope = [
        redact_untrusted_text(item, snapshot.sensitive_values)
        for item in await _answer_scope(session_factory, snapshot.question_id)
    ]
    safe_candidate_question = redact_untrusted_text(
        candidate.question,
        snapshot.sensitive_values,
    )
    safe_candidate_answer = redact_untrusted_text(
        candidate.answer,
        snapshot.sensitive_values,
    )
    input_hash = _hash(
        safe_question,
        "\n".join(safe_scope),
        safe_candidate_question,
        safe_candidate_answer,
        PAIRWISE_CARD_MATCH_PROMPT_VERSION,
        PAIRWISE_CARD_MATCH_SCHEMA_VERSION,
        _provider_model_name(ai, "light"),
    )
    async with session_factory() as session:
        cached = await session.scalar(
            select(AutomationDecision)
            .where(
                AutomationDecision.input_hash == input_hash,
                AutomationDecision.decision_type == AutomationDecisionType.SEMANTIC_CARD_MATCH,
                AutomationDecision.is_overridden.is_(False),
                AutomationDecision.judge_result.is_not(None),
            )
            .order_by(AutomationDecision.created_at.desc())
        )
    if cached is not None:
        from app.interviews.intelligence_ai import (
            AIPairwiseCardMatchResult,
            AIUsageResult,
            PairwiseCardMatchResult,
        )

        return JudgedMatch(
            result=AIPairwiseCardMatchResult(
                output=PairwiseCardMatchResult.model_validate(cached.judge_result),
                usage=AIUsageResult(None, cached.model_name or "cached", 0, 0),
                prompt_version=cached.prompt_version or "cached",
            ),
            input_hash=input_hash,
            latency_ms=None,
        )
    started_at = time.perf_counter()
    result = await ai.judge_card_match(
        question=safe_question[:4_000],
        answer_scope=[item[:1_000] for item in safe_scope[:50]],
        candidate_question=safe_candidate_question[:4_000],
        candidate_answer=safe_candidate_answer[:8_000],
    )
    return JudgedMatch(
        result=result,
        input_hash=input_hash,
        latency_ms=_elapsed_ms(started_at),
    )


async def _record_card_match(
    session_factory: async_sessionmaker[AsyncSession],
    snapshot: OccurrenceSnapshot,
    selected: CardCandidateSnapshot,
    candidates: list[CardCandidateSnapshot],
    settings: CardAutomationSettings,
    *,
    decision_type: AutomationDecisionType,
    decision_source: AutomationDecisionSource,
    reason: str,
    confidence: float,
    apply_link: bool,
    judge_result: dict[str, object] | None = None,
    usage: Any | None = None,
    ai_tier: Literal["light", "analysis"] | None = None,
    prompt_version: str | None = None,
    schema_version: str | None = None,
    input_hash: str | None = None,
    latency_ms: int | None = None,
    finalize_proposal: bool = True,
) -> None:
    async with session_factory() as session:
        question = await _locked_current(session, snapshot)
        if question is None:
            return
        current_settings = await session.get(CardAutomationSettings, snapshot.direction_id)
        card_row = (
            await session.execute(
                select(InterviewCard, InterviewDeck)
                .join(InterviewDeck, InterviewDeck.id == InterviewCard.deck_id)
                .where(InterviewCard.id == selected.card_id)
                .with_for_update()
            )
        ).one_or_none()
        current_card, current_deck = card_row if card_row is not None else (None, None)
        card_is_current = bool(
            current_card is not None
            and current_deck is not None
            and current_card.is_published
            and current_deck.is_published
            and current_deck.track_id == snapshot.direction_id
            and current_card.deck_id == selected.deck_id
            and current_card.question_markdown == selected.question
            and current_card.answer_markdown == selected.answer
        )
        live_enabled = bool(
            current_settings is not None
            and current_settings.enabled
            and not current_settings.shadow_mode
            and (
                (
                    decision_type is AutomationDecisionType.EXACT_CARD_MATCH
                    and current_settings.auto_link_exact_enabled
                )
                or (
                    decision_type is AutomationDecisionType.ALIAS_CARD_MATCH
                    and current_settings.auto_link_alias_enabled
                )
                or (
                    decision_type is AutomationDecisionType.SEMANTIC_CARD_MATCH
                    and current_settings.auto_link_semantic_enabled
                )
            )
        )
        effective_apply_link = apply_link and live_enabled and card_is_current
        decision_settings = current_settings or settings
        decision = await record_automation_decision(
            session,
            entity_type="occurrence",
            entity_id=question.id,
            idempotency_key=(
                f"occurrence:{question.id}:revision:{snapshot.revision}:{decision_type.value}"
            ),
            decision_type=decision_type,
            decision_source=decision_source,
            reason=reason,
            confidence=confidence,
            settings=decision_settings,
            selected_card_id=selected.card_id,
            candidate_card_ids=[item.card_id for item in candidates],
            retrieval_scores={
                **{str(item.card_id): item.score for item in candidates},
                "applied": effective_apply_link,
            },
            judge_result=judge_result,
            usage=usage,
            ai_tier=ai_tier,
            prompt_version=prompt_version,
            schema_version=schema_version,
            input_hash=input_hash,
            latency_ms=latency_ms,
        )
        if effective_apply_link:
            await link_occurrence_to_card(
                session,
                question,
                selected.card_id,
                decision_source,
                reason,
            )
            await ensure_personal_review_for_occurrence(
                session,
                question,
                decision_settings,
                selected.card_id,
            )
        elif finalize_proposal:
            _set_occurrence_status(question, QuestionOccurrenceStatus.ROUTED)
            question.automation_decision_source = decision_source
            if not card_is_current:
                prefix = "Candidate card changed before finalization"
            elif current_settings is None or not current_settings.enabled:
                prefix = "Automation disabled before finalization"
            elif current_settings.shadow_mode:
                prefix = "Shadow/proposal only"
            elif not live_enabled:
                prefix = "Live auto-link disabled before finalization"
            else:
                prefix = "Proposal only"
            question.automation_decision_reason = f"{prefix}: {reason}"
            question.processed_at = datetime.now(UTC)
        await session.commit()
        del decision


def _cluster_metadata_compatible(
    question: IntelligenceQuestion,
    representative: IntelligenceQuestion | None,
    similarity: float,
    configured_threshold: float,
) -> tuple[bool, str]:
    if representative is None:
        conservative_threshold = max(configured_threshold, 0.98)
        return (
            similarity >= conservative_threshold,
            f"representative metadata missing; required score={conservative_threshold:.4f}",
        )
    question_topics = {
        normalized for item in question.topic_candidates if (normalized := normalize_question(item))
    }
    representative_topics = {
        normalized
        for item in representative.topic_candidates
        if (normalized := normalize_question(item))
    }
    if (
        question_topics
        and representative_topics
        and question_topics.isdisjoint(representative_topics)
    ):
        return False, "topic candidates are incompatible"
    question_scope = {
        normalized for item in question.answer_scope if (normalized := normalize_question(item))
    }
    representative_scope = {
        normalized
        for item in representative.answer_scope
        if (normalized := normalize_question(item))
    }
    if question_scope and representative_scope:
        if question_scope.isdisjoint(representative_scope):
            return False, "answer scopes are incompatible"
        return True, "answer scopes overlap and topics do not conflict"
    conservative_threshold = max(configured_threshold, 0.98)
    return (
        similarity >= conservative_threshold,
        f"answer scope metadata incomplete; required score={conservative_threshold:.4f}",
    )


async def _cluster_occurrence(
    session_factory: async_sessionmaker[AsyncSession],
    snapshot: OccurrenceSnapshot,
    settings: CardAutomationSettings,
) -> None:
    async with session_factory() as session:
        question = await _locked_current(session, snapshot)
        if question is None:
            return
        analysis_answer_contract = await _analysis_answer_contract_for_occurrence(
            session,
            question.id,
        )
        current_settings = await session.get(CardAutomationSettings, snapshot.direction_id)
        if current_settings is None or not current_settings.enabled:
            _set_occurrence_status(question, QuestionOccurrenceStatus.ROUTED)
            question.automation_decision_source = AutomationDecisionSource.RULE
            question.automation_decision_reason = "Automation disabled before clustering"
            question.processed_at = datetime.now(UTC)
            await session.commit()
            return
        settings = current_settings
        _set_occurrence_status(question, QuestionOccurrenceStatus.SEARCHING_CLUSTER)
        canonical = question.canonical_question_candidate or question.question_text
        normalized = normalize_question(canonical)
        # Paraphrases have different normalized strings, so a per-question key
        # can let both transactions observe an empty candidate set. Serialize
        # cluster assignment by direction and learning-object type, then read
        # candidates after acquiring the lock. Unrelated directions/types stay
        # concurrent and the partial unique index remains the final backstop.
        lock_key = int.from_bytes(
            hashlib.blake2b(
                f"{snapshot.direction_id}:{question.learning_object_type}".encode(),
                digest_size=8,
            ).digest(),
            "big",
            signed=True,
        )
        await session.scalar(select(func.pg_advisory_xact_lock(lock_key)))
        clusters = list(
            await session.scalars(
                select(QuestionCluster).where(
                    QuestionCluster.direction_id == snapshot.direction_id,
                    QuestionCluster.learning_object_type == question.learning_object_type,
                    QuestionCluster.status.in_(OCCURRENCE_ACCEPTING_CLUSTER_STATUSES),
                )
            )
        )
        exact = next(
            (item for item in clusters if item.normalized_canonical_question == normalized), None
        )
        selected = exact
        selected_score = 1.0 if exact else 0.0
        selection_reason = "Exact normalized cluster match" if exact is not None else ""
        ranked = (
            rank_question_candidates(
                canonical,
                question.question_embedding,
                [
                    QuestionCandidate(
                        card_id=cluster.id,
                        asked_count=cluster.occurrences_count,
                        variants=(
                            QuestionVariant(
                                cluster.canonical_question,
                                tuple(cluster.embedding) if cluster.embedding else None,
                                "cluster",
                            ),
                        ),
                    )
                    for cluster in clusters
                ],
                limit=5,
            )
            if clusters
            else []
        )
        if selected is None and ranked:
            top = ranked[0]
            second_score = ranked[1].similarity if len(ranked) > 1 else None
            gap = top.similarity - second_score if second_score is not None else 1.0
            candidate = next(item for item in clusters if item.id == top.card_id)
            representative = (
                await session.get(
                    IntelligenceQuestion,
                    candidate.representative_occurrence_id,
                )
                if candidate.representative_occurrence_id is not None
                else None
            )
            metadata_compatible, metadata_reason = _cluster_metadata_compatible(
                question,
                representative,
                top.similarity,
                settings.cluster_match_threshold,
            )
            threshold_ok = top.similarity >= settings.cluster_match_threshold
            gap_ok = gap >= settings.candidate_score_gap_threshold
            if threshold_ok and gap_ok and metadata_compatible:
                selected = candidate
                selected_score = top.similarity
                selection_reason = (
                    f"Conservative semantic cluster match: {metadata_reason}; "
                    f"score={top.similarity:.4f}; gap={gap:.4f}"
                )
            else:
                selection_reason = (
                    "No safe semantic cluster match: "
                    f"score={top.similarity:.4f}; gap={gap:.4f}; {metadata_reason}"
                )
        elif selected is None:
            selection_reason = "No existing cluster candidates"
        created = False
        if selected is None:
            selected = QuestionCluster(
                direction_id=snapshot.direction_id,
                status=QuestionClusterStatus.SHADOW,
                canonical_question=canonical,
                normalized_canonical_question=normalized,
                learning_object_type=question.learning_object_type,
                topic_name=(question.topic_candidates[0] if question.topic_candidates else None),
                subtopic_name=question.subcategory,
                topic_candidates=question.topic_candidates,
                answer_contract=analysis_answer_contract,
                representative_occurrence_id=question.id,
                embedding=question.question_embedding,
                embedding_model=question.question_embedding_model,
                embedding_dimensions=question.question_embedding_dimensions,
                embedding_source_hash=question.question_embedding_source_hash,
                cluster_confidence=question.routing_confidence or question.confidence,
                first_seen_at=question.created_at,
                last_seen_at=question.created_at,
            )
            session.add(selected)
            await session.flush()
            selected_score = selected.cluster_confidence
            created = True
        else:
            locked_cluster = await session.scalar(
                select(QuestionCluster).where(QuestionCluster.id == selected.id).with_for_update()
            )
            if locked_cluster is None:
                raise RuntimeError("Selected question cluster disappeared")
            selected = locked_cluster
            if selected.topic_name is None and question.topic_candidates:
                selected.topic_name = question.topic_candidates[0]
            if selected.subtopic_name is None and question.subcategory:
                selected.subtopic_name = question.subcategory
            if selected.answer_contract is None and analysis_answer_contract is not None:
                selected.answer_contract = analysis_answer_contract
        if question.cluster_id != selected.id:
            question.cluster_id = selected.id
            selected.membership_revision += 1
        if selected.status is QuestionClusterStatus.DEFERRED:
            selected.status = QuestionClusterStatus.NEEDS_REVIEW
            selected.promoted_at = datetime.now(UTC)
            selected.promotion_reason = "A new occurrence reopened the deferred cluster"
            selected.version += 1
            await record_automation_decision(
                session,
                entity_type="cluster",
                entity_id=selected.id,
                idempotency_key=(
                    f"cluster:{selected.id}:reopen-on-occurrence:{selected.membership_revision}"
                ),
                decision_type=AutomationDecisionType.CLUSTER_REOPENED,
                decision_source=AutomationDecisionSource.RULE,
                reason=selected.promotion_reason,
                confidence=selected_score,
                settings=settings,
                selected_cluster_id=selected.id,
            )
        _set_occurrence_status(question, QuestionOccurrenceStatus.CLUSTERED)
        question.automation_decision_source = AutomationDecisionSource.CLUSTERING
        question.automation_decision_reason = (
            f"Created a conservative shadow cluster. {selection_reason}"
            if created
            else selection_reason
        )
        question.processed_at = datetime.now(UTC)
        await record_automation_decision(
            session,
            entity_type="occurrence",
            entity_id=question.id,
            idempotency_key=(f"occurrence:{question.id}:revision:{snapshot.revision}:cluster"),
            decision_type=(
                AutomationDecisionType.SHADOW_CLUSTER_CREATED
                if created
                else AutomationDecisionType.CLUSTER_MATCH
            ),
            decision_source=AutomationDecisionSource.CLUSTERING,
            reason=question.automation_decision_reason,
            confidence=selected_score,
            settings=settings,
            selected_cluster_id=selected.id,
            candidate_cluster_ids=[item.card_id for item in ranked],
            retrieval_scores={str(item.card_id): item.similarity for item in ranked},
        )
        await recalculate_cluster_stats(session, selected, settings)
        if selected.status is QuestionClusterStatus.NEEDS_REVIEW:
            _set_occurrence_status(question, QuestionOccurrenceStatus.NEEDS_REVIEW)
        await ensure_personal_review_for_occurrence(session, question, settings, None)
        await session.commit()


async def _analysis_answer_contract_for_occurrence(
    session: AsyncSession,
    question_id: UUID,
) -> dict[str, object] | None:
    suggested_answer = await session.scalar(
        select(IntelligenceAnswerReview.suggested_better_answer)
        .join(
            IntelligenceAnswer,
            IntelligenceAnswer.id == IntelligenceAnswerReview.answer_id,
        )
        .where(
            IntelligenceAnswer.question_id == question_id,
            IntelligenceAnswerReview.status != IntelligenceReviewStatus.REJECTED,
            IntelligenceAnswerReview.suggested_better_answer.is_not(None),
        )
        .order_by(
            (IntelligenceAnswerReview.source == IntelligenceReviewSource.MENTOR).desc(),
            IntelligenceAnswerReview.created_at.desc(),
            IntelligenceAnswerReview.id.desc(),
        )
    )
    if suggested_answer is None:
        return None
    sanitized = redact_untrusted_text(suggested_answer).strip()
    if not sanitized:
        return None
    return answer_contract_from_analysis_draft(sanitized[:12_000])


async def analysis_answer_draft_for_cluster(
    session: AsyncSession,
    cluster_id: UUID,
) -> str | None:
    """Return the latest reusable, privacy-filtered answer from interview analysis."""

    candidates = list(
        await session.scalars(
            select(IntelligenceAnswerReview.suggested_better_answer)
            .join(
                IntelligenceAnswer,
                IntelligenceAnswer.id == IntelligenceAnswerReview.answer_id,
            )
            .join(
                IntelligenceQuestion,
                IntelligenceQuestion.id == IntelligenceAnswer.question_id,
            )
            .where(
                IntelligenceQuestion.cluster_id == cluster_id,
                IntelligenceAnswerReview.status != IntelligenceReviewStatus.REJECTED,
                IntelligenceAnswerReview.suggested_better_answer.is_not(None),
            )
            .order_by(
                (IntelligenceAnswerReview.source == IntelligenceReviewSource.MENTOR).desc(),
                IntelligenceAnswerReview.created_at.desc(),
                IntelligenceAnswerReview.id.desc(),
            )
            .limit(20)
        )
    )
    for candidate in candidates:
        if candidate is None:
            continue
        sanitized = redact_untrusted_text(candidate).strip()
        if sanitized:
            return sanitized[:12_000]
    return None


async def recalculate_cluster_stats(
    session: AsyncSession,
    cluster: QuestionCluster,
    settings: CardAutomationSettings | None = None,
) -> None:
    settings = settings or await _settings(session, cluster.direction_id)
    rows = (
        await session.execute(
            select(
                IntelligenceQuestion,
                IntelligenceInterview,
                InterviewProcess,
                IntelligenceAnswer,
            )
            .join(
                IntelligenceInterview,
                IntelligenceInterview.id == IntelligenceQuestion.interview_id,
            )
            .join(InterviewProcessStage, InterviewProcessStage.id == IntelligenceInterview.stage_id)
            .join(InterviewProcess, InterviewProcess.id == InterviewProcessStage.process_id)
            .outerjoin(
                IntelligenceAnswer, IntelligenceAnswer.question_id == IntelligenceQuestion.id
            )
            .where(IntelligenceQuestion.cluster_id == cluster.id)
        )
    ).all()
    interview_ids = {interview.id for _, interview, _, _ in rows}
    company_ids = {process.company_id for _, _, process, _ in rows if process.company_id}
    student_ids = {interview.student_id for _, interview, _, _ in rows}
    assessments = await _latest_assessments(
        session,
        [question.id for question, _, _, _ in rows],
    )
    failed_interviews: set[UUID] = set()
    for question, interview, _, answer in rows:
        assessment = assessments.get(question.id)
        if is_failed_answer(assessment, answer.answer_text if answer else None):
            failed_interviews.add(interview.id)
    cluster.occurrences_count = len(rows)
    cluster.distinct_interviews_count = len(interview_ids)
    cluster.distinct_companies_count = len(company_ids)
    cluster.distinct_students_count = len(student_ids)
    cluster.failed_answers_count = len(failed_interviews)
    if rows:
        created = [question.created_at for question, _, _, _ in rows]
        cluster.first_seen_at = min(created)
        cluster.last_seen_at = max(created)
        cluster.quality_score = round(
            sum((question.routing_confidence or question.confidence) for question, _, _, _ in rows)
            / len(rows),
            6,
        )
        cluster.cluster_confidence = max(cluster.cluster_confidence, cluster.quality_score)
    cluster.priority_score = priority_score(
        occurrences=cluster.occurrences_count,
        distinct_interviews=cluster.distinct_interviews_count,
        distinct_companies=cluster.distinct_companies_count,
        failed_answers=cluster.failed_answers_count,
        last_seen_at=cluster.last_seen_at,
        novelty=1.0 if cluster.linked_card_id is None else 0.0,
        topic_importance=1.0 if cluster.manual_important else 0.0,
        cluster_confidence=cluster.cluster_confidence,
    )
    cluster.stats_revision = cluster.membership_revision
    promotion = promotion_result(
        distinct_interviews=cluster.distinct_interviews_count,
        distinct_companies=cluster.distinct_companies_count,
        failed_answers=cluster.failed_answers_count,
        min_interviews=settings.min_distinct_interviews_for_promotion,
        min_companies=settings.min_distinct_companies_for_promotion,
        min_failures=settings.min_failed_answers_for_promotion,
        manual_important=cluster.manual_important,
    )
    if promotion.promoted and cluster.status in {
        QuestionClusterStatus.SHADOW,
        QuestionClusterStatus.CANDIDATE,
    }:
        cluster.status = QuestionClusterStatus.NEEDS_REVIEW
        cluster.promoted_at = datetime.now(UTC)
        cluster.promotion_reason = promotion.reason
        cluster.version += 1
        await record_automation_decision(
            session,
            entity_type="cluster",
            entity_id=cluster.id,
            idempotency_key=f"cluster:{cluster.id}:promotion:{cluster.membership_revision}",
            decision_type=AutomationDecisionType.CLUSTER_PROMOTED,
            decision_source=AutomationDecisionSource.RULE,
            reason=promotion.reason or "Promotion threshold reached",
            confidence=cluster.cluster_confidence,
            settings=settings,
            selected_cluster_id=cluster.id,
        )


async def link_occurrence_to_card(
    session: AsyncSession,
    question: IntelligenceQuestion,
    card_id: UUID,
    source: AutomationDecisionSource,
    reason: str,
    *,
    manual_override: bool = False,
) -> None:
    card = await session.scalar(
        select(InterviewCard).where(InterviewCard.id == card_id).with_for_update()
    )
    interview = await session.get(IntelligenceInterview, question.interview_id)
    stage = await session.get(InterviewProcessStage, interview.stage_id) if interview else None
    process = await session.get(InterviewProcess, stage.process_id) if stage else None
    if card is None or interview is None or stage is None or process is None:
        raise RuntimeError("Card or interview source disappeared during automatic link")
    existing_source = await session.scalar(
        select(InterviewCardOccurrence).where(
            InterviewCardOccurrence.source_question_id == question.id
        )
    )
    existing_interview = await session.scalar(
        select(InterviewCardOccurrence).where(
            InterviewCardOccurrence.card_id == card.id,
            InterviewCardOccurrence.interview_id == interview.id,
        )
    )
    if existing_source is None and existing_interview is None:
        session.add(
            InterviewCardOccurrence(
                card_id=card.id,
                source_question_id=question.id,
                interview_id=interview.id,
                process_id=process.id,
                company_id=process.company_id,
                company_name=process.company_name,
                asked_at=stage.scheduled_at,
            )
        )
        await session.flush()
    question.published_card_id = card.id
    question.alias_human_confirmed = False
    if manual_override:
        question.automation_status = QuestionOccurrenceStatus.AUTO_LINKED
    else:
        _set_occurrence_status(question, QuestionOccurrenceStatus.AUTO_LINKED)
    question.automation_decision_source = source
    question.automation_decision_reason = reason
    question.processed_at = datetime.now(UTC)
    await refresh_card_occurrence_stats(session, card)


async def refresh_card_occurrence_stats(
    session: AsyncSession,
    card: InterviewCard,
) -> None:
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


async def ensure_personal_review_for_occurrence(
    session: AsyncSession,
    question: IntelligenceQuestion,
    settings: CardAutomationSettings,
    card_id: UUID | None,
) -> None:
    if not settings.personal_review_enabled:
        return
    answer = await session.scalar(
        select(IntelligenceAnswer).where(IntelligenceAnswer.question_id == question.id)
    )
    review = await session.scalar(
        select(IntelligenceAnswerReview)
        .join(IntelligenceAnswer, IntelligenceAnswer.id == IntelligenceAnswerReview.answer_id)
        .where(
            IntelligenceAnswer.question_id == question.id,
            IntelligenceAnswerReview.status != IntelligenceReviewStatus.REJECTED,
        )
        .order_by(
            (IntelligenceAnswerReview.source == IntelligenceReviewSource.MENTOR).desc(),
            IntelligenceAnswerReview.created_at.desc(),
        )
    )
    if not is_failed_answer(
        review.assessment if review else None,
        answer.answer_text if answer else None,
    ):
        return
    interview = await session.get(IntelligenceInterview, question.interview_id)
    if interview is None or question.direction_id is None:
        return
    if card_id is not None:
        card = await session.get(InterviewCard, card_id)
        if card is None:
            return
        selection = await session.get(
            InterviewTopicSelection,
            {"user_id": interview.student_id, "deck_id": card.deck_id, "category": card.category},
        )
        if selection is None:
            session.add(
                InterviewTopicSelection(
                    user_id=interview.student_id,
                    deck_id=card.deck_id,
                    category=card.category,
                )
            )
        progress = await session.get(
            InterviewCardProgress,
            {"user_id": interview.student_id, "card_id": card.id},
        )
        now = datetime.now(UTC)
        scheduled_for_review = False
        if progress is None:
            session.add(
                InterviewCardProgress(
                    user_id=interview.student_id,
                    card_id=card.id,
                    repetitions=0,
                    interval_days=0,
                    due_at=now,
                )
            )
            scheduled_for_review = True
        elif progress.due_at > now:
            progress.due_at = now
            scheduled_for_review = True
        personal = await session.scalar(
            select(PersonalReviewItem).where(
                PersonalReviewItem.student_id == interview.student_id,
                PersonalReviewItem.source_occurrence_id == question.id,
            )
        )
        if personal is not None:
            personal.canonical_card_id = card.id
            personal.replaced_by_card_id = card.id
            personal.status = PersonalReviewStatus.REPLACED_BY_CANONICAL_CARD
            personal.version += 1
        if scheduled_for_review:
            await record_automation_decision(
                session,
                entity_type="occurrence",
                entity_id=question.id,
                idempotency_key=(
                    f"personal-existing-card:{interview.student_id}:{question.id}:{card.id}"
                ),
                decision_type=AutomationDecisionType.PERSONAL_REVIEW_CREATED,
                decision_source=AutomationDecisionSource.RULE,
                reason="Existing canonical card scheduled for personal review",
                confidence=(
                    review.score
                    if review is not None and review.score is not None
                    else question.confidence
                ),
                settings=settings,
                selected_card_id=card.id,
            )
        return
    if question.learning_object_type not in CARD_ELIGIBLE_TYPES:
        return
    existing = await session.scalar(
        select(PersonalReviewItem).where(
            PersonalReviewItem.student_id == interview.student_id,
            PersonalReviewItem.source_occurrence_id == question.id,
        )
    )
    if existing is not None:
        return
    contract = None
    summary = None
    if review is not None:
        summary = review.summary
        contract = {
            "short_answer": review.suggested_better_answer,
            "required_points": review.missing_points,
            "common_mistakes": [
                str(item.get("problem") or item.get("statement") or "")
                for item in [*review.problems, *review.incorrect_statements]
                if isinstance(item, dict)
            ],
            "source": "private_ai_answer_review",
        }
    item = PersonalReviewItem(
        student_id=interview.student_id,
        direction_id=question.direction_id,
        source_occurrence_id=question.id,
        source_analysis_id=interview.id,
        question_text=question.canonical_question_candidate or question.question_text,
        answer_summary=summary,
        answer_contract=contract,
        due_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(days=365),
    )
    session.add(item)
    await session.flush()
    await record_automation_decision(
        session,
        entity_type="personal_review_item",
        entity_id=item.id,
        idempotency_key=f"personal:{interview.student_id}:{question.id}",
        decision_type=AutomationDecisionType.PERSONAL_REVIEW_CREATED,
        decision_source=AutomationDecisionSource.RULE,
        reason="A weak or missing answer requires a private follow-up",
        confidence=review.score if review and review.score is not None else question.confidence,
        settings=settings,
        selected_cluster_id=question.cluster_id,
    )


async def _latest_assessments(
    session: AsyncSession,
    question_ids: list[UUID],
) -> dict[UUID, IntelligenceAssessment]:
    if not question_ids:
        return {}
    rows = await session.execute(
        select(
            IntelligenceAnswer.question_id,
            IntelligenceAnswerReview.assessment,
        )
        .join(
            IntelligenceAnswerReview,
            IntelligenceAnswerReview.answer_id == IntelligenceAnswer.id,
        )
        .where(
            IntelligenceAnswer.question_id.in_(question_ids),
            IntelligenceAnswerReview.status != IntelligenceReviewStatus.REJECTED,
        )
        .distinct(IntelligenceAnswer.question_id)
        .order_by(
            IntelligenceAnswer.question_id,
            (IntelligenceAnswerReview.source == IntelligenceReviewSource.MENTOR).desc(),
            IntelligenceAnswerReview.created_at.desc(),
            IntelligenceAnswerReview.id.desc(),
        )
    )
    return {question_id: assessment for question_id, assessment in rows}


async def _minimal_context(session: AsyncSession, question: IntelligenceQuestion) -> str:
    utterances = list(
        await session.scalars(
            select(IntelligenceUtterance)
            .where(IntelligenceUtterance.interview_id == question.interview_id)
            .order_by(IntelligenceUtterance.sequence_number)
        )
    )
    referenced = set(question.question_utterance_ids) | set(question.answer_utterance_ids)
    positions = [index for index, item in enumerate(utterances) if item.id in referenced]
    if not positions:
        return ""
    start = max(min(positions) - 2, 0)
    end = min(max(positions) + 3, len(utterances))
    lines = [
        f"U{item.sequence_number:03d} [{item.start_ms}-{item.end_ms}]: {item.text.strip()}"
        for item in utterances[start:end]
    ]
    return "\n".join(lines)[:6_000]


async def _answer_scope(
    session_factory: async_sessionmaker[AsyncSession], question_id: UUID
) -> list[str]:
    async with session_factory() as session:
        scope = await session.scalar(
            select(IntelligenceQuestion.answer_scope).where(IntelligenceQuestion.id == question_id)
        )
        return list(scope or [])


async def _settings(session: AsyncSession, direction_id: UUID) -> CardAutomationSettings:
    settings = await session.get(CardAutomationSettings, direction_id)
    if settings is None:
        settings = CardAutomationSettings(direction_id=direction_id)
        session.add(settings)
        await session.flush()
    return settings


def _student_sensitive_values(student: User | None) -> tuple[str, ...]:
    if student is None:
        return ()
    username = (student.telegram_username or "").strip().lstrip("@")
    first_name = student.first_name.strip()
    last_name = (student.last_name or "").strip()
    values = {
        first_name,
        last_name,
        " ".join(item for item in (first_name, last_name) if item),
        (student.email or "").strip(),
        username,
        f"@{username}" if username else "",
        f"t.me/{username}" if username else "",
        f"https://t.me/{username}" if username else "",
        str(student.telegram_id) if student.telegram_id is not None else "",
    }
    return tuple(sorted((item for item in values if item), key=len, reverse=True))


async def _locked_current(
    session: AsyncSession, snapshot: OccurrenceSnapshot
) -> IntelligenceQuestion | None:
    question = await session.scalar(
        select(IntelligenceQuestion)
        .where(IntelligenceQuestion.id == snapshot.question_id)
        .with_for_update()
    )
    if (
        question is None
        or question.automation_revision != snapshot.revision
        or question.moderation_status is not IntelligenceQuestionModerationStatus.PENDING
        or question.alias_human_confirmed
    ):
        return None
    return question


def _set_occurrence_status(
    question: IntelligenceQuestion,
    target: QuestionOccurrenceStatus,
    *,
    manual_reopen: bool = False,
) -> None:
    ensure_occurrence_transition(
        question.automation_status,
        target,
        manual_reopen=manual_reopen,
    )
    question.automation_status = target


async def _mark_failed(
    session_factory: async_sessionmaker[AsyncSession],
    snapshot: OccurrenceSnapshot,
    *,
    reason: str,
    error_code: str,
    retryable: bool,
    decision_source: AutomationDecisionSource,
    schema_version: str | None,
    stage: str,
) -> None:
    async with session_factory() as session:
        question = await _locked_current(session, snapshot)
        if question is None:
            return
        _set_occurrence_status(question, QuestionOccurrenceStatus.FAILED)
        question.automation_error = reason[:500]
        settings = await _settings(session, snapshot.direction_id)
        await record_automation_decision(
            session,
            entity_type="occurrence",
            entity_id=question.id,
            idempotency_key=(
                f"occurrence:{question.id}:revision:{snapshot.revision}:failed:{stage}:"
                f"{_hash(error_code)[:16]}:{'retryable' if retryable else 'terminal'}"
            ),
            decision_type=AutomationDecisionType.OCCURRENCE_FAILED,
            decision_source=decision_source,
            reason=reason,
            confidence=None,
            settings=settings,
            judge_result={
                "stage": stage,
                "error_code": error_code,
                "retryable": retryable,
                "terminal": not retryable,
            },
            schema_version=schema_version,
        )
        await session.commit()


async def record_automation_decision(
    session: AsyncSession,
    *,
    entity_type: str,
    entity_id: UUID,
    idempotency_key: str,
    decision_type: AutomationDecisionType,
    decision_source: AutomationDecisionSource,
    reason: str,
    confidence: float | None,
    settings: CardAutomationSettings,
    selected_card_id: UUID | None = None,
    selected_cluster_id: UUID | None = None,
    candidate_card_ids: list[UUID] | None = None,
    candidate_cluster_ids: list[UUID] | None = None,
    retrieval_scores: dict[str, object] | None = None,
    judge_result: dict[str, object] | None = None,
    usage: Any | None = None,
    ai_tier: Literal["light", "analysis"] | None = None,
    prompt_version: str | None = None,
    schema_version: str | None = None,
    input_hash: str | None = None,
    latency_ms: int | None = None,
) -> AutomationDecision:
    existing = await session.scalar(
        select(AutomationDecision).where(AutomationDecision.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return existing
    decision_id = uuid4()
    decision = AutomationDecision(
        id=decision_id,
        entity_type=entity_type,
        entity_id=entity_id,
        idempotency_key=idempotency_key,
        decision_type=decision_type,
        decision_source=decision_source,
        selected_card_id=selected_card_id,
        selected_cluster_id=selected_cluster_id,
        candidate_card_ids=[str(item) for item in candidate_card_ids or []],
        candidate_cluster_ids=[str(item) for item in candidate_cluster_ids or []],
        retrieval_scores=retrieval_scores or {},
        judge_result=judge_result,
        confidence=confidence,
        reason=reason[:4_000],
        model_provider=("openai" if usage is not None else None),
        model_name=getattr(usage, "model", None),
        prompt_version=prompt_version,
        schema_version=schema_version or AUTOMATION_SCHEMA_VERSION,
        input_hash=input_hash,
        input_tokens=getattr(usage, "input_tokens", None),
        output_tokens=getattr(usage, "output_tokens", None),
        cost=_estimated_ai_cost(usage, ai_tier),
        latency_ms=latency_ms,
        is_audit_sample=audit_sample(decision_id, settings.audit_sample_percent),
    )
    session.add(decision)
    return decision


def _estimated_ai_cost(
    usage: Any | None,
    tier: Literal["light", "analysis"] | None,
) -> Decimal | None:
    if usage is None or tier is None:
        return None
    configured = get_settings()
    if tier == "analysis":
        input_price = configured.openai_analysis_input_price_per_million_usd
        output_price = configured.openai_analysis_output_price_per_million_usd
    else:
        input_price = configured.openai_light_input_price_per_million_usd
        output_price = configured.openai_light_output_price_per_million_usd
    if input_price <= 0 and output_price <= 0:
        return None
    input_tokens = max(int(getattr(usage, "input_tokens", 0) or 0), 0)
    output_tokens = max(int(getattr(usage, "output_tokens", 0) or 0), 0)
    cost = (Decimal(input_tokens) * input_price + Decimal(output_tokens) * output_price) / Decimal(
        1_000_000
    )
    return cost.quantize(Decimal("0.00000001"))


def _elapsed_ms(started_at: float) -> int:
    return max(int((time.perf_counter() - started_at) * 1_000), 0)


def _hash(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)


def _normalized_topic(value: str) -> str:
    return " ".join(value.casefold().split())


def _unique_topic_labels(values: list[str]) -> tuple[str, ...]:
    unique: dict[str, str] = {}
    for value in values:
        label = value.strip()
        normalized = _normalized_topic(label)
        if normalized and normalized not in unique:
            unique[normalized] = label
    return tuple(unique.values())


def _provider_model_name(
    ai: InterviewAIProvider,
    tier: Literal["light", "analysis"],
) -> str:
    attribute = "analysis_model" if tier == "analysis" else "light_review_model"
    return str(getattr(ai, attribute, getattr(ai, "model", type(ai).__qualname__)))
