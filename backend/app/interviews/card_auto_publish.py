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
from app.interviews.intelligence_models import (
    IntelligenceQuestion,
    IntelligenceQuestionModerationStatus,
)
from app.interviews.models import InterviewCard, InterviewCardFrequency, InterviewDeck
from app.interviews.question_matching import (
    QuestionCandidate,
    QuestionVariant,
    normalize_question,
    rank_question_candidates,
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
    reason = await _question_review_blocker(session, cluster, questions)
    if reason:
        return reason
    return (await _publication_target(session, cluster, settings)).reason


async def _question_review_blocker(
    session: AsyncSession, cluster: QuestionCluster, questions: list[IntelligenceQuestion]
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
            or q.confidence < 0.85
            or CRITICAL_QUALITY_FLAGS.intersection(q.quality_flags or [])
            for q in questions
        )
    ):
        return "Question needs manual review or has a previous human decision"
    return None


async def _publication_target(
    session: AsyncSession, cluster: QuestionCluster, settings: CardAutomationSettings
) -> PublicationTarget:
    cards = list(
        await session.scalars(
            select(InterviewCard)
            .join(InterviewDeck)
            .where(
                InterviewDeck.track_id == cluster.direction_id,
                InterviewDeck.is_published.is_(True),
                InterviewCard.is_published.is_(True),
            )
        )
    )
    candidates = [
        QuestionCandidate(
            card_id=c.id,
            asked_count=c.asked_count,
            variants=(
                QuestionVariant(
                    text=c.question_markdown,
                    embedding=tuple(c.question_embedding)
                    if c.question_embedding is not None
                    and c.question_embedding_model == cluster.embedding_model
                    and c.question_embedding_dimensions == cluster.embedding_dimensions
                    else None,
                    source="canonical",
                ),
            ),
        )
        for c in cards
    ]
    matches = rank_question_candidates(
        cluster.canonical_question, cluster.embedding, candidates, limit=2
    )
    exact = [
        c
        for c in cards
        if normalize_question(c.question_markdown) == normalize_question(cluster.canonical_question)
    ]
    if len(exact) > 1 or (
        not exact and matches and matches[0].similarity >= settings.cluster_match_threshold
    ):
        return PublicationTarget(reason="Possible duplicate found during the publication check")
    card = exact[0] if exact else None
    if card is None:
        # Resolve the existing broad topic; do not invent a deck or taxonomy from AI text.
        destinations = {
            (c.deck_id, c.category)
            for c in cards
            if cluster.topic_name
            and c.category.casefold().strip() == cluster.topic_name.casefold().strip()
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
        cluster.answer_status = AnswerContractStatus.NEEDS_MANUAL_REVIEW
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
    public_answer = contract.model_dump(mode="json", exclude={"source_references"})
    if (
        cluster.learning_object_type not in CARD_ELIGIBLE_TYPES
        or not normalize_question(cluster.canonical_question)
        or not validation.supported
        or contract.confidence < AUTO_PUBLISH_CONFIDENCE
        or validation.confidence < AUTO_PUBLISH_CONFIDENCE
        or contract.unsupported_claims
        or validation.unsupported_claims
        or validation.contradictions
        or validation.missing_required_points
        or validation.version_sensitive_claims
        or not contract.source_references
        or not set(contract.source_references) <= allowed_source_ids
        or not contract.short_answer.strip()
        or redact_untrusted_text(cluster.canonical_question) != cluster.canonical_question
        or redact_untrusted_value(public_answer) != public_answer
    ):
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
    reason = await _question_review_blocker(session, cluster, questions)
    if reason:
        await defer(reason)
        return None
    target = await _publication_target(session, cluster, settings)
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
    reason = (
        "Automatically published after independent answer validation"
        if created
        else "Automatically linked to an exact card found before publication"
    )
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
        idempotency_key=f"cluster:{cluster.id}:auto-publish:{revision}",
        decision_type=AutomationDecisionType.CARD_CREATED
        if created
        else AutomationDecisionType.CLUSTER_LINKED,
        decision_source=AutomationDecisionSource.RULE,
        reason=reason,
        confidence=min(contract.confidence, validation.confidence),
        settings=settings,
        selected_card_id=card.id,
        selected_cluster_id=cluster.id,
        retrieval_scores={
            "occurrence_ids": [str(q.id) for q in questions],
            "source_references": contract.source_references,
        },
        judge_result=validation.model_dump(mode="json"),
    )
    return card.id
