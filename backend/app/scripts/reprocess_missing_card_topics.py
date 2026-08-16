from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as _db_models  # noqa: F401
from app.db.session import async_session_factory
from app.interviews.card_automation_models import CardAutomationSettings, QuestionCluster
from app.interviews.card_automation_pipeline import record_automation_decision
from app.interviews.card_automation_types import (
    AutomationDecisionSource,
    AutomationDecisionType,
    QuestionClusterStatus,
)
from app.interviews.intelligence_models import (
    IntelligenceQuestion,
    IntelligenceQuestionModerationStatus,
)
from app.interviews.intelligence_queue import enqueue_card_automation_job
from app.interviews.models import InterviewCard, InterviewDeck
from app.tracks.models import LearningTrack

logger = logging.getLogger(__name__)

# One reprocessed occurrence can use routing and pairwise matching (up to four
# attempts each), followed by answer generation and validation for its new
# cluster (also up to four attempts each). Reserving 16 calls intentionally
# overestimates shared cluster work so an operator-provided budget is never
# presented as more precise than it really is.
AI_REQUEST_RESERVATION_PER_OCCURRENCE = 16
ACTIVE_CLUSTER_STATUSES = frozenset(
    {
        QuestionClusterStatus.SHADOW,
        QuestionClusterStatus.CANDIDATE,
        QuestionClusterStatus.NEEDS_REVIEW,
        QuestionClusterStatus.DEFERRED,
    }
)


@dataclass(frozen=True, slots=True)
class ReprocessMissingTopicsOptions:
    direction: str
    batch_size: int
    execute: bool
    include_missing_subtopics: bool
    max_ai_requests: int | None


@dataclass(frozen=True, slots=True)
class ClusterCandidate:
    cluster_id: UUID
    occurrence_count: int


async def run(options: ReprocessMissingTopicsOptions) -> dict[str, int]:
    max_occurrences = _max_occurrences(options)
    async with async_session_factory() as session:
        track = await session.scalar(
            select(LearningTrack).where(LearningTrack.slug == options.direction)
        )
        if track is None:
            raise RuntimeError(f"Learning direction {options.direction!r} does not exist")
        settings = await session.get(CardAutomationSettings, track.id)
        if options.execute:
            _ensure_live_run_is_safe(settings, options.direction)
        candidates = await _cluster_candidates(session, track.id, options)

    examined_clusters = len(candidates)
    examined_occurrences = sum(item.occurrence_count for item in candidates)
    selected, budget_blocked_clusters = _select_complete_clusters(candidates, max_occurrences)
    selected_cluster_ids = [item.cluster_id for item in selected]
    prepared_occurrences = sum(item.occurrence_count for item in selected)

    if not options.execute:
        result = {
            "examined_clusters": examined_clusters,
            "examined_occurrences": examined_occurrences,
            "prepared_clusters": len(selected),
            "prepared_occurrences": prepared_occurrences,
            "enqueued": 0,
            "budget_blocked_clusters": budget_blocked_clusters,
            "reserved_ai_requests": prepared_occurrences * AI_REQUEST_RESERVATION_PER_OCCURRENCE,
        }
        logger.info("Missing-topic reprocess dry-run complete %s", result)
        return result

    assert settings is not None
    queue_items: list[tuple[UUID, int]] = []
    for offset in range(0, len(selected_cluster_ids), options.batch_size):
        cluster_batch = selected_cluster_ids[offset : offset + options.batch_size]
        async with async_session_factory() as session:
            rows = (
                await session.execute(
                    select(IntelligenceQuestion, QuestionCluster)
                    .join(QuestionCluster, QuestionCluster.id == IntelligenceQuestion.cluster_id)
                    .where(
                        QuestionCluster.id.in_(cluster_batch),
                        IntelligenceQuestion.alias_human_confirmed.is_(False),
                        IntelligenceQuestion.published_card_id.is_(None),
                        IntelligenceQuestion.moderation_status
                        == IntelligenceQuestionModerationStatus.PENDING,
                    )
                    .order_by(QuestionCluster.id, IntelligenceQuestion.id)
                    .with_for_update(of=IntelligenceQuestion, skip_locked=True)
                )
            ).all()
            for question, cluster in rows:
                await record_automation_decision(
                    session,
                    entity_type="occurrence",
                    entity_id=question.id,
                    idempotency_key=(
                        "bulk:occurrence:"
                        f"{question.id}:reprocess-missing-topic:v{question.automation_revision}"
                    ),
                    decision_type=AutomationDecisionType.OCCURRENCE_REPROCESSED,
                    decision_source=AutomationDecisionSource.RULE,
                    reason=(
                        "Bulk reprocessing requested because cluster topic metadata is missing "
                        "or does not match the published card topic catalog"
                    ),
                    confidence=1.0,
                    settings=settings,
                    selected_cluster_id=cluster.id,
                    retrieval_scores={
                        "operation": "reprocess_missing_card_topics",
                        "direction": options.direction,
                        "previous_topic_name": cluster.topic_name,
                        "previous_subtopic_name": cluster.subtopic_name,
                        "requested_revision": question.automation_revision,
                    },
                )
                queue_items.append((question.id, question.automation_revision))
            await session.commit()

    enqueued = 0
    for question_id, revision in queue_items:
        await enqueue_card_automation_job(
            "reprocess_question_occurrence",
            str(question_id),
            revision,
        )
        enqueued += 1

    result = {
        "examined_clusters": examined_clusters,
        "examined_occurrences": examined_occurrences,
        "prepared_clusters": len(selected),
        "prepared_occurrences": prepared_occurrences,
        "enqueued": enqueued,
        "budget_blocked_clusters": budget_blocked_clusters,
        "reserved_ai_requests": prepared_occurrences * AI_REQUEST_RESERVATION_PER_OCCURRENCE,
    }
    logger.info("Missing-topic reprocess enqueue complete %s", result)
    return result


def _max_occurrences(options: ReprocessMissingTopicsOptions) -> int | None:
    if options.execute and options.max_ai_requests is None:
        raise ValueError("--execute requires --max-ai-requests")
    if options.max_ai_requests is None:
        return None
    maximum = options.max_ai_requests // AI_REQUEST_RESERVATION_PER_OCCURRENCE
    if maximum < 1:
        raise ValueError(
            "max_ai_requests is lower than the safe per-occurrence reservation "
            f"({AI_REQUEST_RESERVATION_PER_OCCURRENCE})"
        )
    return maximum


def _ensure_live_run_is_safe(
    settings: CardAutomationSettings | None,
    direction: str,
) -> None:
    if settings is None or not settings.enabled:
        raise RuntimeError(f"Card automation must be enabled for {direction!r}")
    if not settings.shadow_mode:
        raise RuntimeError(
            "Bulk missing-topic reprocessing requires shadow_mode=true so old records cannot "
            "be automatically relinked while the batch is running"
        )


async def _cluster_candidates(
    session: AsyncSession,
    direction_id: UUID,
    options: ReprocessMissingTopicsOptions,
) -> list[ClusterCandidate]:
    published_topic_exists = exists(
        select(InterviewCard.id)
        .join(InterviewDeck, InterviewDeck.id == InterviewCard.deck_id)
        .where(
            InterviewDeck.track_id == QuestionCluster.direction_id,
            InterviewDeck.is_published.is_(True),
            InterviewCard.is_published.is_(True),
            func.lower(func.btrim(InterviewCard.category))
            == func.lower(func.btrim(QuestionCluster.topic_name)),
        )
    )
    missing_broad_topic = or_(
        QuestionCluster.topic_name.is_(None),
        func.btrim(QuestionCluster.topic_name) == "",
        ~published_topic_exists,
    )
    missing_subtopic = or_(
        QuestionCluster.subtopic_name.is_(None),
        func.btrim(QuestionCluster.subtopic_name) == "",
    )
    topic_filter = (
        or_(missing_broad_topic, missing_subtopic)
        if options.include_missing_subtopics
        else missing_broad_topic
    )
    statement = (
        select(QuestionCluster.id, func.count(IntelligenceQuestion.id))
        .join(IntelligenceQuestion, IntelligenceQuestion.cluster_id == QuestionCluster.id)
        .where(
            QuestionCluster.direction_id == direction_id,
            QuestionCluster.status.in_(ACTIVE_CLUSTER_STATUSES),
            topic_filter,
            IntelligenceQuestion.alias_human_confirmed.is_(False),
            IntelligenceQuestion.published_card_id.is_(None),
            IntelligenceQuestion.moderation_status == IntelligenceQuestionModerationStatus.PENDING,
        )
        .group_by(QuestionCluster.id)
        .order_by(QuestionCluster.id)
    )
    rows = (await session.execute(statement)).all()
    return [
        ClusterCandidate(cluster_id=cluster_id, occurrence_count=int(count))
        for cluster_id, count in rows
    ]


def _select_complete_clusters(
    candidates: list[ClusterCandidate],
    max_occurrences: int | None,
) -> tuple[list[ClusterCandidate], int]:
    if max_occurrences is None:
        return candidates, 0
    selected: list[ClusterCandidate] = []
    used = 0
    blocked = 0
    for candidate in candidates:
        if used + candidate.occurrence_count > max_occurrences:
            blocked += 1
            continue
        selected.append(candidate)
        used += candidate.occurrence_count
    return selected, blocked


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reprocess complete, unmoderated clusters whose broad topic is missing or absent "
            "from the published card catalog. The default mode is read-only."
        )
    )
    parser.add_argument("--direction", choices=("python", "go"), required=True)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument(
        "--include-missing-subtopics",
        action="store_true",
        help="Also reprocess clusters with a valid broad topic but an empty detailed subtopic",
    )
    parser.add_argument("--max-ai-requests", type=int)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Persist audit records and enqueue jobs; without this flag only a dry-run is shown",
    )
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    args = _parser().parse_args()
    if not 1 <= args.batch_size <= 1_000:
        raise SystemExit("--batch-size must be between 1 and 1000")
    if args.max_ai_requests is not None and args.max_ai_requests < 1:
        raise SystemExit("--max-ai-requests must be positive")
    try:
        result = asyncio.run(
            run(
                ReprocessMissingTopicsOptions(
                    direction=args.direction,
                    batch_size=args.batch_size,
                    execute=args.execute,
                    include_missing_subtopics=args.include_missing_subtopics,
                    max_ai_requests=args.max_ai_requests,
                )
            )
        )
    except (RuntimeError, ValueError) as error:
        raise SystemExit(str(error)) from error
    logger.info("Missing-topic reprocess complete %s", result)


if __name__ == "__main__":
    main()
