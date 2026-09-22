"""Publish independently validated clusters without impersonating a moderator."""

import hashlib
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.interviews.card_automation_models import (
    AutomationDecision,
    CardAutomationSettings,
    PersonalReviewItem,
    QuestionCluster,
)
from app.interviews.card_automation_pipeline import (
    ensure_personal_review_for_occurrence,
    link_occurrence_to_card,
    record_automation_decision,
)
from app.interviews.card_automation_privacy import redact_untrusted_text, redact_untrusted_value
from app.interviews.card_automation_schemas import AnswerContract, AnswerValidationResult
from app.interviews.card_automation_types import (
    CARD_ELIGIBLE_TYPES,
    CRITICAL_QUALITY_FLAGS,
    AnswerContractStatus,
    AutomationDecisionSource,
    AutomationDecisionType,
    PersonalReviewStatus,
    QuestionClusterStatus,
    QuestionOccurrenceStatus,
)
from app.interviews.card_topic_resolution import resolved_topic
from app.interviews.intelligence_models import (
    IntelligenceQuestion,
    IntelligenceQuestionModerationStatus,
)
from app.interviews.models import InterviewCard, InterviewCardFrequency, InterviewDeck
from app.interviews.question_matching import (
    normalize_question,
)

AUTO_PUBLISH_CONFIDENCE = 0.9


@dataclass(frozen=True)
class PublicationTarget:
    card: InterviewCard | None = None
    deck_id: UUID | None = None
    category: str | None = None
    reason: str | None = None


async def publication_preflight_reason(
    session: AsyncSession, cluster: QuestionCluster, settings: CardAutomationSettings
) -> str | None:
    """Read-only early check; publication repeats these checks under its locks."""
    if cluster.linked_card_id is not None:
        return "Cluster already has a linked card; automatic answer work is unnecessary"
    if (
        cluster.learning_object_type not in CARD_ELIGIBLE_TYPES
        or not normalize_question(cluster.canonical_question)
        or redact_untrusted_text(cluster.canonical_question) != cluster.canonical_question
    ):
        return "Question did not pass automatic publication quality/privacy checks"
    questions = list(
        await session.scalars(
            select(IntelligenceQuestion).where(IntelligenceQuestion.cluster_id == cluster.id)
        )
    )
    reason = await _question_review_blocker(
        session,
        cluster,
        questions,
        independent_question_check=True,
    )
    if reason:
        return reason
    return (await _publication_target(session, cluster, settings)).reason


def _transcript_uncertainty_only(question: IntelligenceQuestion) -> bool:
    # Extraction caps confidence at 0.5 when speech/attribution is uncertain.
    # A standalone learning card is checked independently; this never upgrades
    # the candidate's own answer, speaker labels, or interview feedback.
    return question.confidence == 0.5 and bool(
        (question.transcription_annotations or {}).get("uncertain_utterance_ids")
    )


async def _question_review_blocker(
    session: AsyncSession,
    cluster: QuestionCluster,
    questions: list[IntelligenceQuestion],
    *,
    independent_question_check: bool = False,
) -> str | None:
    human_decision = await session.scalar(
        select(AutomationDecision.id)
        .where(
            AutomationDecision.entity_type == "cluster",
            AutomationDecision.entity_id == cluster.id,
            AutomationDecision.decision_source == AutomationDecisionSource.HUMAN,
        )
        .limit(1)
    )
    if (
        not questions
        or human_decision is not None
        or any(
            q.moderation_status is not IntelligenceQuestionModerationStatus.PENDING
            or q.automation_decision_source is AutomationDecisionSource.HUMAN
            or q.published_card_id is not None
            or q.alias_human_confirmed
            or q.automation_status
            not in {QuestionOccurrenceStatus.CLUSTERED, QuestionOccurrenceStatus.NEEDS_REVIEW}
            or not q.is_standalone
            or not q.is_real_interviewer_question
            or (q.routing_confidence or 0) < AUTO_PUBLISH_CONFIDENCE
            or (q.confidence < 0.85 and not _transcript_uncertainty_only(q))
            or (
                CRITICAL_QUALITY_FLAGS
                - (
                    {"bad_transcription", "missing_context"}
                    if independent_question_check
                    else set()
                )
            ).intersection(q.quality_flags or [])
            for q in questions
        )
    ):
        return "Question needs manual review or has a previous human decision"
    return None


async def _publication_target(
    session: AsyncSession,
    cluster: QuestionCluster,
    settings: CardAutomationSettings,
    *,
    refresh: bool = False,
) -> PublicationTarget:
    from app.interviews.card_cluster_matching import (
        all_distinct,
        current_cluster_matches,
        matching_card,
        publication_cards,
    )

    cards = await publication_cards(session, cluster, refresh=refresh)
    matches = await current_cluster_matches(session, cluster, settings, cards)
    exact = [
        c
        for c in cards
        if normalize_question(c.question_markdown) == normalize_question(cluster.canonical_question)
    ]
    card = exact[0] if len(exact) == 1 else matching_card(matches, settings)
    if len(exact) > 1 or (not exact and card is None and not all_distinct(matches)):
        return PublicationTarget(reason="Possible duplicate found during the publication check")
    if card is None:
        # Resolve the existing broad topic; do not invent a deck or taxonomy from AI text.
        topic = resolved_topic(cluster.topic_name, {c.category for c in cards})
        destinations = {
            (c.deck_id, c.category)
            for c in cards
            if topic is not None
            and c.category == topic
            and (cluster.deck_id is None or c.deck_id == cluster.deck_id)
        }
        if len(destinations) != 1:
            return PublicationTarget(
                reason="No unambiguous published deck and existing topic for this question"
            )
        deck_id, category = next(iter(destinations))
        return PublicationTarget(deck_id=deck_id, category=category)
    return PublicationTarget(card=card)


async def publish_validated_cluster(
    session: AsyncSession, cluster_id: UUID, revision: int, allowed_source_ids: set[str]
) -> UUID | None:
    direction_id = await session.scalar(
        select(QuestionCluster.direction_id).where(QuestionCluster.id == cluster_id)
    )
    if direction_id is None:
        return None
    # Serialize the final duplicate check and insertion across clusters in a direction.
    lock_key = int.from_bytes(
        hashlib.blake2b(f"card-publish:{direction_id}".encode(), digest_size=8).digest(),
        "big",
        signed=True,
    )
    await session.execute(select(func.pg_advisory_xact_lock(lock_key)))
    cluster = await session.scalar(
        select(QuestionCluster)
        .where(QuestionCluster.id == cluster_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    settings = await session.get(CardAutomationSettings, direction_id, populate_existing=True)
    if (
        cluster is None
        or settings is None
        or not settings.enabled
        or settings.shadow_mode
        or not settings.cluster_moderation_enabled
        or not settings.global_auto_publish_enabled
        or cluster.membership_revision != revision
        or cluster.linked_card_id is not None
        or cluster.status is not QuestionClusterStatus.NEEDS_REVIEW
        or cluster.answer_status is not AnswerContractStatus.GENERATED_FROM_SOURCES
    ):
        return None

    async def defer(reason: str) -> None:
        recoverable = reason == "Possible duplicate found during the publication check" or (
            reason == "Answer did not pass automatic publication quality/source checks"
            and redact_untrusted_text(cluster.canonical_question) == cluster.canonical_question
            and cluster.answer_repair_attempts < 2
            and (cluster.answer_validation or {}).get("question_is_self_contained") is not False
        )
        cluster.answer_status = (
            AnswerContractStatus.REVIEW_PENDING
            if recoverable
            else AnswerContractStatus.NEEDS_MANUAL_REVIEW
        )
        cluster.version += 1
        await record_automation_decision(
            session,
            entity_type="cluster",
            entity_id=cluster.id,
            idempotency_key=f"cluster:{cluster.id}:auto-publish-deferred:{cluster.version}",
            decision_type=AutomationDecisionType.ANSWER_VALIDATION_FAILED,
            decision_source=AutomationDecisionSource.RULE,
            reason=reason,
            confidence=None,
            settings=settings,
            selected_cluster_id=cluster.id,
        )

    try:
        contract = AnswerContract.model_validate(cluster.answer_contract)
        validation = AnswerValidationResult.model_validate(cluster.answer_validation)
    except ValueError:
        await defer("Automatic publication requires a valid answer and independent validation")
        return None
    if not publication_quality_passes(cluster, contract, validation, allowed_source_ids):
        await defer("Answer did not pass automatic publication quality/source checks")
        return None
    question_count = await session.scalar(
        select(func.count())
        .select_from(IntelligenceQuestion)
        .where(IntelligenceQuestion.cluster_id == cluster.id)
    )
    questions = list(
        await session.scalars(
            select(IntelligenceQuestion)
            .where(IntelligenceQuestion.cluster_id == cluster.id)
            .order_by(IntelligenceQuestion.id)
            .with_for_update(skip_locked=True)
        )
    )
    if len(questions) != question_count:
        # Routing/manual review may hold a question while waiting for this cluster.
        # Release it and let reconciliation retry, rather than invert those locks.
        return None
    if any(_transcript_uncertainty_only(q) for q in questions) and not (
        validation.question_is_self_contained
    ):
        await defer("Question wording needs independent verification after uncertain transcription")
        return None
    reason = await _question_review_blocker(
        session,
        cluster,
        questions,
        independent_question_check=validation.question_is_self_contained is True,
    )
    if reason:
        await defer(reason)
        return None
    target = await _publication_target(session, cluster, settings, refresh=True)
    if target.reason:
        await defer(target.reason)
        return None
    card = target.card
    created = card is None
    if card is None:
        deck_id, category = target.deck_id, target.category
        assert deck_id is not None and category is not None
        deck = await session.get(
            InterviewDeck, deck_id, with_for_update=True, populate_existing=True
        )
        if deck is None or not deck.is_published or deck.track_id != direction_id:
            await defer("Publication destination is no longer available")
            return None
        answer = contract.short_answer.strip()
        for heading, points in (
            ("Основные моменты", contract.required_points),
            ("Дополнительно", contract.optional_points),
            ("Частые ошибки", contract.common_mistakes),
        ):
            if points:
                answer += f"\n\n### {heading}\n\n" + "\n".join(f"- {p}" for p in points)
        if contract.version_scope:
            answer += "\n\nПрименимость: " + "; ".join(contract.version_scope)
        position = await session.scalar(
            select(func.coalesce(func.max(InterviewCard.position), -1)).where(
                InterviewCard.deck_id == deck_id
            )
        )
        card = InterviewCard(
            deck_id=deck_id,
            slug=f"cluster-{cluster.id}",
            category=category,
            subcategory=cluster.subtopic_name,
            question_markdown=cluster.canonical_question,
            answer_markdown=answer,
            frequency=InterviewCardFrequency.OCCASIONAL,
            frequency_override=None,
            position=int(position if position is not None else -1) + 1,
            is_published=True,
            asked_count=0,
            question_embedding=cluster.embedding,
            question_embedding_model=cluster.embedding_model,
            question_embedding_dimensions=cluster.embedding_dimensions,
            question_embedding_source_hash=cluster.embedding_source_hash,
        )
        session.add(card)
        await session.flush()
    else:
        selected_id = card.id
        await session.get(InterviewDeck, card.deck_id, with_for_update=True, populate_existing=True)
        await session.get(InterviewCard, selected_id, with_for_update=True, populate_existing=True)
        locked_target = await _publication_target(session, cluster, settings, refresh=True)
        if locked_target.card is None or locked_target.card.id != selected_id:
            await defer("Possible duplicate found during the publication check")
            return None
        card = locked_target.card
    reason = (
        "Automatically published after independent answer validation"
        if created
        else "Automatically linked to a verified existing card before publication"
    )
    return await _finish_cluster_card(
        session,
        cluster,
        settings,
        questions,
        card,
        created=created,
        reason=reason,
        confidence=min(contract.confidence, validation.confidence),
        source_references=contract.source_references,
        evidence=validation.model_dump(mode="json"),
    )


async def _finish_cluster_card(
    session: AsyncSession,
    cluster: QuestionCluster,
    settings: CardAutomationSettings,
    questions: list[IntelligenceQuestion],
    card: InterviewCard,
    *,
    created: bool,
    reason: str,
    confidence: float,
    source_references: list[str],
    evidence: dict[str, object],
) -> UUID:
    for q in questions:
        await link_occurrence_to_card(session, q, card.id, AutomationDecisionSource.RULE, reason)
        q.moderation_status = IntelligenceQuestionModerationStatus.APPROVED
        q.automation_revision += 1
        await ensure_personal_review_for_occurrence(session, q, settings, card.id)
    personal_items = list(
        await session.scalars(
            select(PersonalReviewItem)
            .where(PersonalReviewItem.source_occurrence_id.in_([q.id for q in questions]))
            .with_for_update()
        )
    )
    for item in personal_items:
        item.canonical_card_id = item.replaced_by_card_id = card.id
        item.status = PersonalReviewStatus.REPLACED_BY_CANONICAL_CARD
        item.version += 1
    cluster.linked_card_id = card.id
    cluster.deck_id = card.deck_id
    cluster.topic_name = card.category
    cluster.status = QuestionClusterStatus.CARD_CREATED if created else QuestionClusterStatus.LINKED
    cluster.answer_status = AnswerContractStatus.APPROVED
    cluster.version += 1
    await record_automation_decision(
        session,
        entity_type="cluster",
        entity_id=cluster.id,
        idempotency_key=f"cluster:{cluster.id}:auto-publish:{cluster.membership_revision}",
        decision_type=AutomationDecisionType.CARD_CREATED
        if created
        else AutomationDecisionType.CLUSTER_LINKED,
        decision_source=AutomationDecisionSource.RULE,
        reason=reason,
        confidence=confidence,
        settings=settings,
        selected_card_id=card.id,
        selected_cluster_id=cluster.id,
        retrieval_scores={
            "occurrence_ids": [str(q.id) for q in questions],
            "source_references": source_references,
        },
        judge_result=evidence,
    )
    return card.id


async def link_verified_cluster_match(
    session: AsyncSession,
    cluster_id: UUID,
    revision: int,
) -> UUID | None:
    """Attach to an existing answer after a fresh pairwise verdict, without rewriting it."""
    from app.interviews.card_cluster_matching import current_cluster_matches, matching_card

    direction_id = await session.scalar(
        select(QuestionCluster.direction_id).where(
            QuestionCluster.id == cluster_id,
        )
    )
    if direction_id is None:
        return None
    lock_key = int.from_bytes(
        hashlib.blake2b(
            f"card-publish:{direction_id}".encode(),
            digest_size=8,
        ).digest(),
        "big",
        signed=True,
    )
    await session.execute(select(func.pg_advisory_xact_lock(lock_key)))
    cluster = await session.get(
        QuestionCluster, cluster_id, with_for_update=True, populate_existing=True
    )
    settings = await session.get(CardAutomationSettings, direction_id, populate_existing=True)
    if (
        cluster is None
        or settings is None
        or not settings.enabled
        or settings.shadow_mode
        or not settings.global_auto_publish_enabled
        or not settings.cluster_moderation_enabled
        or not settings.auto_link_semantic_enabled
        or cluster.membership_revision != revision
        or cluster.status is not QuestionClusterStatus.NEEDS_REVIEW
        or cluster.answer_status is not AnswerContractStatus.REVIEW_PENDING
        or cluster.linked_card_id is not None
        or cluster.learning_object_type not in CARD_ELIGIBLE_TYPES
        or not normalize_question(cluster.canonical_question)
        or redact_untrusted_text(cluster.canonical_question) != cluster.canonical_question
    ):
        return None
    count = await session.scalar(
        select(func.count())
        .select_from(IntelligenceQuestion)
        .where(
            IntelligenceQuestion.cluster_id == cluster_id,
        )
    )
    questions = list(
        await session.scalars(
            select(IntelligenceQuestion)
            .where(
                IntelligenceQuestion.cluster_id == cluster_id,
            )
            .order_by(IntelligenceQuestion.id)
            .with_for_update(skip_locked=True)
        )
    )
    if len(questions) != count or await _question_review_blocker(session, cluster, questions):
        return None
    candidate = matching_card(await current_cluster_matches(session, cluster, settings), settings)
    if candidate is None:
        return None
    await session.get(
        InterviewDeck, candidate.deck_id, with_for_update=True, populate_existing=True
    )
    await session.get(InterviewCard, candidate.id, with_for_update=True, populate_existing=True)
    # Re-run the lookup under locks: edits/deletions must invalidate the verdict.
    current = matching_card(
        await current_cluster_matches(session, cluster, settings, refresh=True), settings
    )
    if current is None or current.id != candidate.id:
        return None
    return await _finish_cluster_card(
        session,
        cluster,
        settings,
        questions,
        current,
        created=False,
        reason="Automatically linked after a current independent same-card check",
        confidence=0.98,
        source_references=[],
        evidence={"decision": "same_card"},
    )


def publication_quality_passes(
    cluster: QuestionCluster,
    contract: AnswerContract,
    validation: AnswerValidationResult,
    allowed_source_ids: set[str],
) -> bool:
    public_answer = contract.model_dump(mode="json", exclude={"source_references"})
    independently_verified = (
        validation.question_is_self_contained is True
        and validation.answer_is_substantive is True
        and validation.generator_warnings_resolved
        and not validation.unverified_personal_claims
        and validation.confidence >= 0.95
    )
    return not (
        cluster.learning_object_type not in CARD_ELIGIBLE_TYPES
        or not normalize_question(cluster.canonical_question)
        or not validation.supported
        or validation.question_is_self_contained is False
        or validation.answer_is_substantive is False
        or validation.unverified_personal_claims
        or (contract.confidence < AUTO_PUBLISH_CONFIDENCE and not independently_verified)
        or validation.confidence < AUTO_PUBLISH_CONFIDENCE
        or (contract.unsupported_claims and not independently_verified)
        or validation.unsupported_claims
        or validation.contradictions
        or validation.missing_required_points
        or validation.version_sensitive_claims
        or not contract.source_references
        or not set(contract.source_references) <= allowed_source_ids
        or not contract.short_answer.strip()
        or redact_untrusted_text(cluster.canonical_question) != cluster.canonical_question
        or redact_untrusted_value(public_answer) != public_answer
    )
