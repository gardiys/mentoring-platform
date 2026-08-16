from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import delete, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.interviews.card_automation_models import (
    CardAutomationSettings,
    PersonalReviewItem,
    QuestionCluster,
)
from app.interviews.card_automation_pipeline import (
    recalculate_cluster_stats,
    record_automation_decision,
)
from app.interviews.card_automation_types import (
    AutomationDecisionSource,
    AutomationDecisionType,
    PersonalReviewStatus,
    QuestionClusterStatus,
)
from app.interviews.card_frequency import refresh_card_frequency
from app.interviews.intelligence_models import IntelligenceQuestion
from app.interviews.models import InterviewCard, InterviewCardOccurrence


@dataclass(frozen=True, slots=True)
class AutomationDeletionImpact:
    cluster_ids: tuple[UUID, ...]
    card_ids: tuple[UUID, ...]


def sync_cluster_embedding_from_representative(
    cluster: QuestionCluster,
    representative: IntelligenceQuestion | None,
) -> None:
    """Keep the cluster vector bound to the occurrence named as representative."""

    if representative is None:
        cluster.embedding = None
        cluster.embedding_model = None
        cluster.embedding_dimensions = None
        cluster.embedding_source_hash = None
        return
    cluster.embedding = representative.question_embedding
    cluster.embedding_model = representative.question_embedding_model
    cluster.embedding_dimensions = representative.question_embedding_dimensions
    cluster.embedding_source_hash = representative.question_embedding_source_hash


async def prepare_automation_deletion(
    session: AsyncSession,
    interview_ids: list[UUID],
) -> AutomationDeletionImpact:
    if not interview_ids:
        return AutomationDeletionImpact((), ())
    questions = list(
        await session.scalars(
            select(IntelligenceQuestion)
            .where(IntelligenceQuestion.interview_id.in_(interview_ids))
            .order_by(IntelligenceQuestion.id)
            .with_for_update()
        )
    )
    question_ids = [question.id for question in questions]
    cluster_ids = tuple(
        sorted(
            {question.cluster_id for question in questions if question.cluster_id is not None},
            key=str,
        )
    )
    question_predicate = (
        InterviewCardOccurrence.source_question_id.in_(question_ids) if question_ids else false()
    )
    occurrence_predicate = or_(
        question_predicate,
        InterviewCardOccurrence.interview_id.in_(interview_ids),
    )
    card_ids = tuple(
        sorted(
            set(
                await session.scalars(
                    select(InterviewCardOccurrence.card_id).where(occurrence_predicate)
                )
            ),
            key=str,
        )
    )
    personal_question_predicate = (
        PersonalReviewItem.source_occurrence_id.in_(question_ids) if question_ids else false()
    )
    personal_review_predicate = or_(
        PersonalReviewItem.source_analysis_id.in_(interview_ids),
        personal_question_predicate,
    )
    personal_items = list(
        await session.scalars(
            select(PersonalReviewItem)
            .where(personal_review_predicate)
            .order_by(PersonalReviewItem.id)
            .with_for_update()
        )
    )
    settings_by_direction: dict[UUID, CardAutomationSettings] = {}
    for item in personal_items:
        previous_status = item.status
        previous_occurrence_id = item.source_occurrence_id
        previous_analysis_id = item.source_analysis_id
        item.source_occurrence_id = None
        item.source_analysis_id = None
        item.status = PersonalReviewStatus.ARCHIVED
        item.version += 1

        settings = settings_by_direction.get(item.direction_id)
        if settings is None:
            settings = await session.get(CardAutomationSettings, item.direction_id)
            if settings is None:
                # A track normally receives settings when it is created. Keep
                # deletion cleanup auditable even for legacy/inconsistent rows;
                # the defaults are deliberately safe (disabled + shadow mode).
                settings = CardAutomationSettings(direction_id=item.direction_id)
                session.add(settings)
                await session.flush()
            settings_by_direction[item.direction_id] = settings
        await record_automation_decision(
            session,
            entity_type="personal_review_item",
            entity_id=item.id,
            idempotency_key=f"personal:{item.id}:source-deleted:v{item.version}",
            decision_type=AutomationDecisionType.PERSONAL_REVIEW_ARCHIVED,
            decision_source=AutomationDecisionSource.RULE,
            reason="Source interview was deleted; personal review item was archived",
            confidence=None,
            settings=settings,
            selected_card_id=item.canonical_card_id,
            retrieval_scores={
                "previous_status": previous_status.value,
                "source_occurrence_id": (
                    str(previous_occurrence_id) if previous_occurrence_id is not None else None
                ),
                "source_analysis_id": (
                    str(previous_analysis_id) if previous_analysis_id is not None else None
                ),
            },
        )
    await session.execute(delete(InterviewCardOccurrence).where(occurrence_predicate))
    return AutomationDeletionImpact(cluster_ids, card_ids)


async def finalize_automation_deletion(
    session: AsyncSession,
    impact: AutomationDeletionImpact,
) -> None:
    for card_id in impact.card_ids:
        card = await session.scalar(
            select(InterviewCard).where(InterviewCard.id == card_id).with_for_update()
        )
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
        companies = list(
            await session.scalars(
                select(InterviewCardOccurrence.company_name)
                .where(InterviewCardOccurrence.card_id == card.id)
                .distinct()
                .order_by(InterviewCardOccurrence.company_name)
            )
        )
        card.companies = ", ".join(companies) or None
        refresh_card_frequency(card)
    for cluster_id in impact.cluster_ids:
        cluster = await session.scalar(
            select(QuestionCluster).where(QuestionCluster.id == cluster_id).with_for_update()
        )
        if cluster is None:
            continue
        settings = await session.get(CardAutomationSettings, cluster.direction_id)
        cluster.membership_revision += 1
        # Confidence is aggregate evidence, so it must be allowed to decrease
        # when the highest-confidence source occurrence is removed.
        cluster.quality_score = 0.0
        cluster.cluster_confidence = 0.0
        await recalculate_cluster_stats(session, cluster, settings)
        if cluster.occurrences_count == 0:
            previous_status = cluster.status
            cluster.status = QuestionClusterStatus.IGNORED
            cluster.promotion_reason = "All source occurrences were deleted"
            cluster.representative_occurrence_id = None
            sync_cluster_embedding_from_representative(cluster, None)
            cluster.priority_score = 0.0
            cluster.quality_score = 0.0
            cluster.cluster_confidence = 0.0
            cluster.version += 1
            settings = settings or await session.get(
                CardAutomationSettings, cluster.direction_id
            )
            if settings is not None:
                await record_automation_decision(
                    session,
                    entity_type="cluster",
                    entity_id=cluster.id,
                    idempotency_key=(
                        f"cluster:{cluster.id}:source-deleted:"
                        f"membership:{cluster.membership_revision}"
                    ),
                    decision_type=AutomationDecisionType.CLUSTER_IGNORED,
                    decision_source=AutomationDecisionSource.RULE,
                    reason="All source occurrences were deleted; cluster was archived",
                    confidence=None,
                    settings=settings,
                    selected_cluster_id=cluster.id,
                    retrieval_scores={
                        "previous_status": previous_status.value,
                        "membership_revision": cluster.membership_revision,
                    },
                )
        else:
            representative_is_current = bool(
                cluster.representative_occurrence_id
                and await session.scalar(
                    select(IntelligenceQuestion.id).where(
                        IntelligenceQuestion.id == cluster.representative_occurrence_id,
                        IntelligenceQuestion.cluster_id == cluster.id,
                    )
                )
            )
            if not representative_is_current:
                cluster.representative_occurrence_id = await session.scalar(
                    select(IntelligenceQuestion.id)
                    .where(IntelligenceQuestion.cluster_id == cluster.id)
                    .order_by(IntelligenceQuestion.created_at, IntelligenceQuestion.id)
                    .limit(1)
                )
            representative = (
                await session.get(
                    IntelligenceQuestion, cluster.representative_occurrence_id
                )
                if cluster.representative_occurrence_id is not None
                else None
            )
            sync_cluster_embedding_from_representative(cluster, representative)
