"""Select new themes after routing finishes, independently of arrival order."""

import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from time import perf_counter
from uuid import UUID

from sqlalchemy import and_, exists, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.interviews.card_ai_budget import (
    UNKNOWN_ATTEMPT_LIMIT,
    _day_bounds,
    acquire_card_budget_lock,
    eligible,
    new_card_theme,
    reconcile_card_charges,
    request_deadline,
)
from app.interviews.card_automation_models import (
    AutomationDecision,
    CardAICharge,
    CardAutomationSettings,
    QuestionCluster,
)
from app.interviews.card_automation_pipeline import record_automation_decision
from app.interviews.card_automation_types import (
    AnswerContractStatus,
    AutomationDecisionSource,
    AutomationDecisionType,
    QuestionClusterStatus,
    QuestionOccurrenceStatus,
)
from app.interviews.intelligence_models import IntelligenceInterview, IntelligenceQuestion

logger = logging.getLogger(__name__)


async def defer_card_generation(
    session: AsyncSession,
    cluster: QuestionCluster,
    settings: CardAutomationSettings,
    code: str,
    reason: str,
    *,
    retryable: bool = False,
) -> None:
    if (
        cluster.answer_status == AnswerContractStatus.NOT_SELECTED
        and cluster.generation_deferred_reason == code
        and cluster.generation_selected_revision == cluster.membership_revision
        and not retryable
        and code not in {"CARD_AI_DAILY_BUDGET", "CARD_AI_MAINTENANCE_BUDGET"}
    ):
        # A settings change requests one reassessment, not a permanent retry.
        cluster.generation_retry_after = None
        return
    awaiting = code == "CARD_AI_AWAITING_ADMISSION"
    cluster.answer_status = None if awaiting else AnswerContractStatus.NOT_SELECTED
    cluster.generation_deferred_reason = code
    cluster.ai_error_code = None
    cluster.ai_retry_after = None
    if not awaiting:
        cluster.generation_selected_revision = cluster.membership_revision
    cluster.generation_retry_after = (
        datetime.now(UTC) + timedelta(minutes=5)
        if retryable
        else _day_bounds()[1]
        if code in {"CARD_AI_DAILY_BUDGET", "CARD_AI_MAINTENANCE_BUDGET"}
        else None
    )
    if code == "CARD_AI_RESERVATION_BUSY":
        deadlines = [
            request_deadline(row)
            for row in await session.scalars(
                select(CardAICharge).where(
                    CardAICharge.cluster_id == cluster.id,
                    CardAICharge.status.in_(["reserved", "unknown"]),
                )
            )
            if request_deadline(row) > datetime.now(UTC)
        ]
        if deadlines:
            cluster.generation_retry_after = max(deadlines)
    cluster.version += 1
    decision = await record_automation_decision(
        session,
        entity_type="cluster",
        entity_id=cluster.id,
        idempotency_key=(
            f"cluster:{cluster.id}:budget:{code}:membership:"
            f"{cluster.membership_revision}:settings:{settings.version}"
        ),
        decision_type=AutomationDecisionType.CARD_AI_DEFERRED,
        decision_source=AutomationDecisionSource.RULE,
        reason=reason,
        confidence=None,
        settings=settings,
        selected_cluster_id=cluster.id,
        retrieval_scores={
            "budget_reason": code,
            "retry_after": cluster.generation_retry_after.isoformat()
            if cluster.generation_retry_after
            else None,
        },
    )
    decision.reason = reason
    decision.retrieval_scores = {
        "budget_reason": code,
        "retry_after": cluster.generation_retry_after.isoformat()
        if cluster.generation_retry_after
        else None,
    }


async def select_card_candidates(session: AsyncSession) -> int:
    started = perf_counter()
    await acquire_card_budget_lock(session, "admission")
    await reconcile_card_charges(session)
    now = datetime.now(UTC)
    settings_rows = list(
        await session.scalars(
            select(CardAutomationSettings).where(
                CardAutomationSettings.enabled.is_(True),
                CardAutomationSettings.cluster_moderation_enabled.is_(True),
            )
        )
    )
    selected = evaluated = 0
    for settings in settings_rows:
        # Finish routing and aggregates per interview; a large legacy backlog
        # must not prevent admission of an unrelated completed interview.
        blocked_origins = set(
            await session.scalars(
                select(IntelligenceQuestion.interview_id)
                .where(
                    IntelligenceQuestion.direction_id == settings.direction_id,
                    IntelligenceQuestion.automation_status.in_(
                        [
                            QuestionOccurrenceStatus.CREATED,
                            QuestionOccurrenceStatus.ROUTING,
                            QuestionOccurrenceStatus.ROUTED,
                            QuestionOccurrenceStatus.SEARCHING_CARD,
                            QuestionOccurrenceStatus.SEARCHING_CLUSTER,
                        ]
                    ),
                )
                .distinct()
            )
        )
        blocked_origins.update(
            await session.scalars(
                select(IntelligenceQuestion.interview_id)
                .join(QuestionCluster, QuestionCluster.id == IntelligenceQuestion.cluster_id)
                .where(
                    QuestionCluster.direction_id == settings.direction_id,
                    QuestionCluster.stats_revision < QuestionCluster.membership_revision,
                )
                .distinct()
            )
        )
        # Keep historical deferred topics out of the ORM and per-topic work.
        # Count both billed slots and still-live unpaid selections. The latter
        # are used only to filter history; the ranking below starts with billed
        # slots and can reconsider live selections after a settings change.
        occupied: dict[UUID, set[UUID]] = defaultdict(set)
        for interview_id, cluster_id in await session.execute(
            select(CardAICharge.interview_id, CardAICharge.cluster_id)
            .where(
                CardAICharge.direction_id == settings.direction_id,
                CardAICharge.amount_usd > 0,
                CardAICharge.manual.is_(False),
                CardAICharge.maintenance.is_(False),
            )
            .distinct()
        ):
            occupied[interview_id].add(cluster_id)
        candidate_conditions = (
            QuestionCluster.direction_id == settings.direction_id,
            QuestionCluster.status.in_(
                [
                    QuestionClusterStatus.SHADOW,
                    QuestionClusterStatus.CANDIDATE,
                    QuestionClusterStatus.NEEDS_REVIEW,
                ]
            ),
            QuestionCluster.linked_card_id.is_(None),
            ~exists(
                select(AutomationDecision.id)
                .where(
                    AutomationDecision.entity_type == "cluster",
                    AutomationDecision.entity_id == QuestionCluster.id,
                    AutomationDecision.decision_source == AutomationDecisionSource.HUMAN,
                    AutomationDecision.decision_type
                    != AutomationDecisionType.CARD_AI_COST_WRITTEN_OFF,
                )
                .correlate(QuestionCluster)
            ),
        )
        pending_slots = {origin: set(slots) for origin, slots in occupied.items()}
        for origin, cluster_id in await session.execute(
            select(QuestionCluster.generation_source_interview_id, QuestionCluster.id).where(
                *candidate_conditions,
                QuestionCluster.generation_source_interview_id.is_not(None),
                QuestionCluster.generation_admitted_at.is_not(None),
                QuestionCluster.generation_selected_revision == QuestionCluster.membership_revision,
                QuestionCluster.generation_backlog.is_(False),
                or_(
                    QuestionCluster.answer_status.is_(None),
                    QuestionCluster.answer_status.in_(
                        [
                            AnswerContractStatus.GENERATED_FROM_SOURCES,
                            AnswerContractStatus.REVIEW_PENDING,
                            AnswerContractStatus.REPAIR_PENDING,
                            AnswerContractStatus.WAITING_FOR_AI,
                        ]
                    ),
                ),
                ~exists(
                    select(CardAICharge.request_id).where(
                        CardAICharge.cluster_id == QuestionCluster.id,
                        CardAICharge.amount_usd > 0,
                        CardAICharge.manual.is_(False),
                    )
                ),
            )
        ):
            pending_slots.setdefault(origin, set()).add(cluster_id)
        full_origins = {
            origin
            for origin, slots in pending_slots.items()
            if len(slots) >= settings.card_ai_max_topics_per_interview
        }
        candidates = list(
            await session.scalars(
                select(QuestionCluster)
                .where(
                    *candidate_conditions,
                    or_(
                        QuestionCluster.answer_status.is_(None),
                        and_(
                            QuestionCluster.answer_status == AnswerContractStatus.NOT_SELECTED,
                            or_(
                                QuestionCluster.generation_selected_revision.is_(None),
                                QuestionCluster.generation_selected_revision
                                != QuestionCluster.membership_revision,
                                QuestionCluster.generation_retry_after <= now,
                                and_(
                                    QuestionCluster.generation_deferred_reason
                                    == "CARD_AI_TOPIC_LIMIT",
                                    literal(settings.card_ai_max_topics_per_interview > 0),
                                    or_(
                                        QuestionCluster.generation_source_interview_id.is_(None),
                                        QuestionCluster.generation_source_interview_id.not_in(
                                            full_origins
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                )
                .order_by(QuestionCluster.priority_score.desc(), QuestionCluster.id)
            )
        )
        if not candidates:
            continue
        candidate_ids = {cluster.id for cluster in candidates}
        charges_by_cluster: dict[UUID, list[CardAICharge]] = defaultdict(list)
        for charge in await session.scalars(
            select(CardAICharge).where(
                CardAICharge.cluster_id.in_(candidate_ids),
                CardAICharge.direction_id == settings.direction_id,
                CardAICharge.amount_usd > 0,
            )
        ):
            charges_by_cluster[charge.cluster_id].append(charge)
        origins = dict(
            (
                await session.execute(
                    select(IntelligenceQuestion.cluster_id, IntelligenceQuestion.interview_id)
                    .where(IntelligenceQuestion.cluster_id.in_(candidate_ids))
                    .distinct(IntelligenceQuestion.cluster_id)
                    .order_by(
                        IntelligenceQuestion.cluster_id,
                        IntelligenceQuestion.created_at.desc(),
                        IntelligenceQuestion.id,
                    )
                )
            )
            .tuples()
            .all()
        )
        representatives = dict(
            (
                await session.execute(
                    select(IntelligenceQuestion.id, IntelligenceQuestion.interview_id).where(
                        IntelligenceQuestion.id.in_(
                            {
                                cluster.representative_occurrence_id
                                for cluster in candidates
                                if cluster.id not in origins
                                and cluster.representative_occurrence_id is not None
                            }
                        )
                    )
                )
            )
            .tuples()
            .all()
        )
        origin_ids = (
            set(origins.values())
            | set(representatives.values())
            | {
                charge.interview_id
                for charges in charges_by_cluster.values()
                for charge in charges
                if not charge.manual
            }
        )
        origin_dates = dict(
            (
                await session.execute(
                    select(IntelligenceInterview.id, IntelligenceInterview.created_at).where(
                        IntelligenceInterview.id.in_(origin_ids)
                    )
                )
            )
            .tuples()
            .all()
        )
        for cluster in candidates:
            if (
                cluster.generation_backlog
                and cluster.generation_selected_revision is not None
                and cluster.generation_selected_revision != cluster.membership_revision
            ):
                cluster.generation_backlog = False
            previous = charges_by_cluster.get(cluster.id, [])
            if sum(charge.status == "unknown" for charge in previous) >= UNKNOWN_ATTEMPT_LIMIT:
                evaluated += 1
                await defer_card_generation(
                    session,
                    cluster,
                    settings,
                    "CARD_AI_COST_UNKNOWN",
                    "Стоимость двух попыток неизвестна; требуется списание резерва администратором",
                )
                continue
            if (
                cluster.answer_status == AnswerContractStatus.NOT_SELECTED
                and cluster.generation_selected_revision == cluster.membership_revision
                and not (cluster.generation_retry_after and cluster.generation_retry_after <= now)
                and cluster.generation_deferred_reason != "CARD_AI_TOPIC_LIMIT"
            ):
                continue
            # Membership growth provides a new source interview for an unpaid theme.
            paid = next((c for c in previous if not c.manual), None)
            origin = paid.interview_id if paid else origins.get(cluster.id)
            if origin is None and cluster.representative_occurrence_id is not None:
                origin = representatives.get(cluster.representative_occurrence_id)
            cluster.generation_source_interview_id = origin
            if origin in blocked_origins or cluster.stats_revision < cluster.membership_revision:
                continue
            # Consume a due reassessment only once its source is ready.
            cluster.generation_retry_after = None
            evaluated += 1
            new_theme = new_card_theme(cluster, paid)
            if new_theme and not eligible(cluster, settings):
                await defer_card_generation(
                    session,
                    cluster,
                    settings,
                    "CARD_AI_NOT_SELECTED",
                    "Тема не прошла пороги повторяемости и приоритета",
                )
                continue
            if (
                new_theme
                and cluster.generation_backlog
                and not settings.card_ai_legacy_backlog_enabled
            ):
                if cluster.generation_deferred_reason != "CARD_AI_BACKLOG_DISABLED":
                    await defer_card_generation(
                        session,
                        cluster,
                        settings,
                        "CARD_AI_BACKLOG_DISABLED",
                        "Платная генерация старого бэклога выключена",
                    )
                continue
            if origin is None:
                await defer_card_generation(
                    session,
                    cluster,
                    settings,
                    "CARD_AI_NO_SOURCE_INTERVIEW",
                    "Нет интервью-источника",
                )
                continue
            origin_created = origin_dates.get(origin)
            source_is_backlog = cluster.generation_backlog or now - (
                origin_created or cluster.last_seen_at
            ) > timedelta(days=7)
            slots = occupied.setdefault(origin, set())
            if (
                new_theme
                and not source_is_backlog
                and len(slots) >= settings.card_ai_max_topics_per_interview
            ):
                await defer_card_generation(
                    session,
                    cluster,
                    settings,
                    "CARD_AI_TOPIC_LIMIT",
                    "Выбраны темы интервью с более высоким приоритетом",
                )
                continue
            if new_theme and not source_is_backlog:
                slots.add(cluster.id)
            if cluster.generation_admitted_at is None:
                cluster.generation_admitted_at = now
            if cluster.status in {QuestionClusterStatus.SHADOW, QuestionClusterStatus.CANDIDATE}:
                cluster.promoted_at = now
                cluster.promotion_reason = (
                    "Отобрано по приоритету после завершения маршрутизации интервью"
                )
                cluster.version += 1
                await record_automation_decision(
                    session,
                    entity_type="cluster",
                    entity_id=cluster.id,
                    idempotency_key=f"cluster:{cluster.id}:ranked-promotion:{cluster.membership_revision}",
                    decision_type=AutomationDecisionType.CLUSTER_PROMOTED,
                    decision_source=AutomationDecisionSource.RULE,
                    reason=cluster.promotion_reason,
                    confidence=cluster.cluster_confidence,
                    settings=settings,
                    selected_cluster_id=cluster.id,
                )
            cluster.status = QuestionClusterStatus.NEEDS_REVIEW
            cluster.answer_status = None
            cluster.generation_source_interview_id = origin
            cluster.generation_selected_revision = cluster.membership_revision
            cluster.generation_deferred_reason = None
            cluster.generation_retry_after = None
            selected += 1
    await session.commit()
    logger.info(
        "Card AI admission directions=%d evaluated=%d selected=%d duration_ms=%.1f",
        len(settings_rows),
        evaluated,
        selected,
        (perf_counter() - started) * 1000,
    )
    return selected
