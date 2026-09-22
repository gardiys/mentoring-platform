from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from arq import Retry
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.interviews.ai_rate_limit import defer_model_cooldown, retry_delay
from app.interviews.card_answer_sources import load_trusted_sources
from app.interviews.card_automation_domain import ensure_occurrence_transition
from app.interviews.card_automation_models import (
    AutomationDecision,
    CardAutomationSettings,
    PersonalReviewItem,
    QuestionCluster,
)
from app.interviews.card_automation_pipeline import (
    analysis_answer_draft_for_cluster,
    answer_contract_from_analysis_draft,
    ensure_personal_review_for_occurrence,
    process_question_occurrence,
    record_automation_decision,
    refresh_card_occurrence_stats,
)
from app.interviews.card_automation_pipeline import (
    recalculate_cluster_stats as recalculate_cluster_stats_model,
)
from app.interviews.card_automation_privacy import (
    redact_untrusted_text,
    redact_untrusted_value,
)
from app.interviews.card_automation_schemas import AnswerContract, AnswerValidationResult
from app.interviews.card_automation_types import (
    AnswerContractStatus,
    AutomationDecisionSource,
    AutomationDecisionType,
    PersonalReviewStatus,
    QuestionClusterStatus,
    QuestionOccurrenceStatus,
)
from app.interviews.card_cluster_workflow import ai_processing_condition, waiting_for_ai_condition
from app.interviews.card_duplicate_cache import (
    acquire_duplicate_refresh_lock,
    clear_duplicate_refresh_status,
    mark_duplicate_refresh_running,
    release_duplicate_refresh_lock,
    write_duplicate_snapshot,
)
from app.interviews.intelligence_ai import (
    ANSWER_CONTRACT_PROMPT_VERSION,
    ANSWER_CONTRACT_SCHEMA_VERSION,
    ANSWER_VALIDATION_PROMPT_VERSION,
    ANSWER_VALIDATION_SCHEMA_VERSION,
    InterviewAIError,
    InterviewAIProvider,
)
from app.interviews.intelligence_models import (
    IntelligenceQuestion,
    IntelligenceQuestionModerationStatus,
)
from app.interviews.intelligence_queue import enqueue_card_automation_job
from app.interviews.models import InterviewCard, InterviewCardOccurrence

logger = logging.getLogger(__name__)
CARD_AUTOMATION_JOB_MAX_TRIES = 4
ANSWER_JOB_MAX_TRIES = CARD_AUTOMATION_JOB_MAX_TRIES
SOURCE_RECHECK_INTERVAL = timedelta(hours=6)
ANSWER_CACHE_VERSION = "answer-input-v3"
MAX_ANSWER_REPAIRS = 2
AI_SERVICE_ERRORS = frozenset(
    {
        "OPENAI_QUOTA_EXCEEDED",
        "OPENAI_AUTH_ERROR",
        "OPENAI_RATE_LIMIT",
        "OPENAI_PROXY_ERROR",
        "OPENAI_PROVIDER_ERROR",
    }
)
MISSING_REFERENCE_FINDING = "Контракт ссылается на непереданные источники."
_ANSWER_DRAFT_CLUSTER_STATUSES = frozenset(
    {
        QuestionClusterStatus.SHADOW,
        QuestionClusterStatus.CANDIDATE,
        QuestionClusterStatus.NEEDS_REVIEW,
    }
)


async def refresh_interview_card_duplicate_cache(ctx: dict[str, Any]) -> None:
    """Rebuild the shared moderation snapshot outside the API processes."""

    owner = f"{ctx.get('job_id', 'cron')}:{uuid4()}"
    if not await acquire_duplicate_refresh_lock(owner):
        return
    try:
        await mark_duplicate_refresh_running()
        # Local import avoids loading the large moderation service in workers
        # that never execute this optional maintenance job.
        from app.interviews.card_automation_service import (
            calculate_interview_card_duplicates,
        )

        async with async_session_factory() as session:
            items = await calculate_interview_card_duplicates(
                session,
                direction_id=None,
                minimum_similarity=0.35,
            )
        snapshot = await write_duplicate_snapshot(items)
        logger.info(
            "Refreshed interview-card duplicate cache candidates=%s generated_at=%s",
            len(items),
            snapshot.generated_at.isoformat(),
        )
    finally:
        await clear_duplicate_refresh_status()
        await release_duplicate_refresh_lock(owner)


async def repair_missing_source_validations(*, limit: int = 50) -> int:
    """Restore only source-mismatch failures, once per failed validation payload."""
    from app.interviews.card_auto_publish import publication_preflight_reason

    repaired = 0
    async with async_session_factory() as session:
        candidates = list(
            await session.scalars(
                select(QuestionCluster)
                .join(
                    CardAutomationSettings,
                    CardAutomationSettings.direction_id == QuestionCluster.direction_id,
                )
                .where(
                    QuestionCluster.status == QuestionClusterStatus.NEEDS_REVIEW,
                    QuestionCluster.linked_card_id.is_(None),
                    QuestionCluster.answer_status == AnswerContractStatus.NEEDS_EXPERT_SOURCE,
                    QuestionCluster.answer_contract.is_not(None),
                    QuestionCluster.answer_validation["unsupported_claims"].contains(
                        [MISSING_REFERENCE_FINDING]
                    ),
                    CardAutomationSettings.enabled.is_(True),
                    CardAutomationSettings.cluster_moderation_enabled.is_(True),
                    CardAutomationSettings.global_auto_publish_enabled.is_(True),
                    CardAutomationSettings.shadow_mode.is_(False),
                    ~exists(
                        select(AutomationDecision.id).where(
                            AutomationDecision.entity_type == "cluster",
                            AutomationDecision.entity_id == QuestionCluster.id,
                            AutomationDecision.decision_source == AutomationDecisionSource.HUMAN,
                        )
                    ),
                    ~exists(
                        select(AutomationDecision.id).where(
                            AutomationDecision.entity_type == "cluster",
                            AutomationDecision.entity_id == QuestionCluster.id,
                            AutomationDecision.retrieval_scores[
                                "source_repair_version"
                            ].as_integer()
                            == 1,
                            AutomationDecision.judge_result == QuestionCluster.answer_validation,
                        )
                    ),
                )
                .order_by(QuestionCluster.updated_at, QuestionCluster.id)
                .limit(limit)
                .with_for_update(of=QuestionCluster, skip_locked=True)
            )
        )
        for cluster in candidates:
            settings = await session.get(CardAutomationSettings, cluster.direction_id)
            assert settings is not None
            references = _contract_source_ids(cluster.answer_contract)
            sources = await _validation_sources(session, cluster)
            available = {source["source_id"] for source in sources}
            reason = await publication_preflight_reason(session, cluster, settings)
            restorable = bool(references) and set(references) <= available and reason is None
            previous_validation = cluster.answer_validation
            fingerprint = hashlib.sha256(
                json.dumps(previous_validation, sort_keys=True).encode()
            ).hexdigest()
            await record_automation_decision(
                session,
                entity_type="cluster",
                entity_id=cluster.id,
                idempotency_key=f"cluster:{cluster.id}:source-repair-v1:{fingerprint[:24]}",
                decision_type=AutomationDecisionType.ANSWER_VALIDATION_FAILED,
                decision_source=AutomationDecisionSource.RULE,
                reason="Sources restored; validation requeued without answer regeneration"
                if restorable
                else "Source recovery requires a manual decision or an available trusted source",
                confidence=None,
                settings=settings,
                selected_cluster_id=cluster.id,
                judge_result=previous_validation,
                retrieval_scores={"source_repair_version": 1, "restored": restorable},
            )
            if restorable:
                cluster.answer_validation = None
                cluster.answer_status = None
                cluster.version += 1
                repaired += 1
        await session.commit()
    return repaired


async def recheck_source_blocked_clusters(*, limit: int = 50) -> int:
    """Check materials in a separate bounded lane, without calling AI."""
    now = datetime.now(UTC)
    recovered = 0
    async with async_session_factory() as session:
        clusters = await session.scalars(
            select(QuestionCluster)
            .join(
                CardAutomationSettings,
                CardAutomationSettings.direction_id == QuestionCluster.direction_id,
            )
            .where(
                CardAutomationSettings.enabled.is_(True),
                CardAutomationSettings.cluster_moderation_enabled.is_(True),
                QuestionCluster.status == QuestionClusterStatus.NEEDS_REVIEW,
                QuestionCluster.linked_card_id.is_(None),
                or_(
                    QuestionCluster.answer_contract.is_(None),
                    QuestionCluster.ai_error_code == "no_trusted_sources",
                ),
                QuestionCluster.answer_status == AnswerContractStatus.NEEDS_EXPERT_SOURCE,
                or_(
                    QuestionCluster.source_retry_after.is_(None),
                    QuestionCluster.source_retry_after <= now,
                ),
                ~exists(
                    select(AutomationDecision.id).where(
                        AutomationDecision.entity_type == "cluster",
                        AutomationDecision.entity_id == QuestionCluster.id,
                        AutomationDecision.decision_source == AutomationDecisionSource.HUMAN,
                    )
                ),
            )
            .order_by(QuestionCluster.source_retry_after.asc().nulls_first(), QuestionCluster.id)
            .limit(limit)
            .with_for_update(of=QuestionCluster, skip_locked=True)
        )
        for cluster in clusters:
            cluster.source_retry_after = now + SOURCE_RECHECK_INTERVAL
            sources = await _trusted_sources(session, cluster)
            if not sources:
                continue
            settings = await session.get(CardAutomationSettings, cluster.direction_id)
            assert settings is not None
            if await _defer_unpublishable_answer(session, cluster, settings, sources):
                continue
            cluster.answer_status = None
            cluster.answer_validation = None
            cluster.source_retry_after = None
            cluster.ai_error_code = None
            cluster.version += 1
            recovered += 1
        await session.commit()
    return recovered


async def resume_service_blocked_clusters(*, limit: int = 50) -> int:
    """Resume a bounded batch at its saved stage, never regenerate validated work."""
    now = datetime.now(UTC)
    recovered = 0
    async with async_session_factory() as session:
        clusters = await session.scalars(
            select(QuestionCluster)
            .join(
                CardAutomationSettings,
                CardAutomationSettings.direction_id == QuestionCluster.direction_id,
            )
            .where(
                QuestionCluster.status == QuestionClusterStatus.NEEDS_REVIEW,
                QuestionCluster.answer_status == AnswerContractStatus.WAITING_FOR_AI,
                QuestionCluster.linked_card_id.is_(None),
                QuestionCluster.ai_retry_after <= now,
                CardAutomationSettings.enabled.is_(True),
                CardAutomationSettings.cluster_moderation_enabled.is_(True),
                ~exists(
                    select(AutomationDecision.id).where(
                        AutomationDecision.entity_type == "cluster",
                        AutomationDecision.entity_id == QuestionCluster.id,
                        AutomationDecision.decision_source == AutomationDecisionSource.HUMAN,
                    )
                ),
            )
            .order_by(QuestionCluster.ai_retry_after, QuestionCluster.id)
            .limit(limit)
            .with_for_update(of=QuestionCluster, skip_locked=True)
        )
        for cluster in clusters:
            failure = await session.scalar(
                select(AutomationDecision)
                .where(
                    AutomationDecision.entity_type == "cluster",
                    AutomationDecision.entity_id == cluster.id,
                    AutomationDecision.judge_result["terminal"].as_boolean().is_(True),
                )
                .order_by(AutomationDecision.created_at.desc())
                .limit(1)
            )
            cluster.answer_status = (
                AnswerContractStatus.REVIEW_PENDING
                if failure is not None and (failure.judge_result or {}).get("stage") == "review"
                else AnswerContractStatus.REPAIR_PENDING
                if cluster.answer_validation is not None
                else None
            )
            cluster.ai_retry_after = None
            cluster.ai_error_code = None
            cluster.version += 1
            recovered += 1
        await session.commit()
    return recovered


async def schedule_answer_repairs(*, limit: int = 20) -> int:
    """Try a small, bounded correction cycle for sourced drafts, including the backlog."""
    from app.interviews.card_auto_publish import publication_preflight_reason

    scheduled = 0
    now = datetime.now(UTC)
    async with async_session_factory() as session:
        clusters = await session.scalars(
            select(QuestionCluster)
            .join(
                CardAutomationSettings,
                CardAutomationSettings.direction_id == QuestionCluster.direction_id,
            )
            .where(
                QuestionCluster.status == QuestionClusterStatus.NEEDS_REVIEW,
                QuestionCluster.linked_card_id.is_(None),
                QuestionCluster.answer_status.in_(
                    [
                        AnswerContractStatus.NEEDS_EXPERT_SOURCE,
                        AnswerContractStatus.NEEDS_MANUAL_REVIEW,
                    ]
                ),
                QuestionCluster.answer_contract.is_not(None),
                QuestionCluster.answer_validation.is_not(None),
                QuestionCluster.answer_repair_attempts < MAX_ANSWER_REPAIRS,
                QuestionCluster.ai_error_code.is_(None),
                or_(
                    QuestionCluster.source_retry_after.is_(None),
                    QuestionCluster.source_retry_after <= now,
                ),
                CardAutomationSettings.enabled.is_(True),
                CardAutomationSettings.cluster_moderation_enabled.is_(True),
                CardAutomationSettings.global_auto_publish_enabled.is_(True),
                CardAutomationSettings.shadow_mode.is_(False),
                ~exists(
                    select(AutomationDecision.id).where(
                        AutomationDecision.entity_type == "cluster",
                        AutomationDecision.entity_id == QuestionCluster.id,
                        AutomationDecision.decision_source == AutomationDecisionSource.HUMAN,
                    )
                ),
            )
            .order_by(QuestionCluster.source_retry_after.asc().nulls_first(), QuestionCluster.id)
            .limit(limit)
            .with_for_update(of=QuestionCluster, skip_locked=True)
        )
        for cluster in clusters:
            cluster.source_retry_after = now + SOURCE_RECHECK_INTERVAL
            # Explicit missing-context verdicts cannot be fixed by inventing more prose.
            if (cluster.answer_validation or {}).get("question_is_self_contained") is False:
                continue
            settings = await session.get(CardAutomationSettings, cluster.direction_id)
            assert settings is not None
            if await publication_preflight_reason(session, cluster, settings):
                continue
            if not await _trusted_sources(session, cluster):
                continue
            previous_validation = cluster.answer_validation or {}
            contract = cluster.answer_contract or {}
            contract_confidence = contract.get("confidence")
            revalidate_only = (
                previous_validation.get("supported") is True
                and "version_warnings" not in previous_validation
                and not any(
                    previous_validation.get(key)
                    for key in ("unsupported_claims", "contradictions", "missing_required_points")
                )
                and not contract.get("unsupported_claims")
                and isinstance(contract_confidence, int | float)
                and contract_confidence >= 0.9
            )
            cluster.answer_status = None if revalidate_only else AnswerContractStatus.REPAIR_PENDING
            if revalidate_only:
                cluster.answer_validation = None
            cluster.version += 1
            await record_automation_decision(
                session,
                entity_type="cluster",
                entity_id=cluster.id,
                idempotency_key=f"cluster:{cluster.id}:answer-repair:{cluster.version}",
                decision_type=AutomationDecisionType.ANSWER_VALIDATION_FAILED,
                decision_source=AutomationDecisionSource.RULE,
                reason=(
                    "Answer queued for current validation policy without regeneration"
                    if revalidate_only
                    else "Sourced answer queued for bounded correction using validation findings"
                ),
                confidence=None,
                settings=settings,
                selected_cluster_id=cluster.id,
                retrieval_scores={"repair_attempt": cluster.answer_repair_attempts + 1},
            )
            scheduled += 1
        await session.commit()
    return scheduled


async def reconcile_card_automation_jobs(ctx: dict[str, Any]) -> None:
    """Recover queued work after Redis or worker restarts."""

    from app.interviews.card_review_recovery import queue_review_backlog

    await queue_review_backlog(async_session_factory)
    await repair_missing_source_validations()
    await recheck_source_blocked_clusters()
    await resume_service_blocked_clusters()
    await schedule_answer_repairs()

    async with async_session_factory() as session:
        occurrences = (
            await session.execute(
                select(IntelligenceQuestion.id, IntelligenceQuestion.automation_revision)
                .join(
                    CardAutomationSettings,
                    CardAutomationSettings.direction_id == IntelligenceQuestion.direction_id,
                )
                .where(
                    CardAutomationSettings.enabled.is_(True),
                    IntelligenceQuestion.automation_status.in_(
                        {
                            QuestionOccurrenceStatus.CREATED,
                            QuestionOccurrenceStatus.ROUTING,
                            QuestionOccurrenceStatus.SEARCHING_CARD,
                            QuestionOccurrenceStatus.SEARCHING_CLUSTER,
                        }
                    ),
                )
                .order_by(IntelligenceQuestion.updated_at)
                .limit(500)
            )
        ).all()
        pending_directions = set(
            await session.scalars(
                select(QuestionCluster.direction_id)
                .where(or_(ai_processing_condition(), waiting_for_ai_condition()))
                .distinct()
            )
        )
        dirty_clusters = (
            await session.execute(
                select(QuestionCluster.id, QuestionCluster.membership_revision)
                .join(
                    CardAutomationSettings,
                    CardAutomationSettings.direction_id == QuestionCluster.direction_id,
                )
                .where(
                    or_(
                        QuestionCluster.stats_revision < QuestionCluster.membership_revision,
                        and_(
                            QuestionCluster.direction_id.not_in(pending_directions),
                            CardAutomationSettings.enabled.is_(True),
                            CardAutomationSettings.global_auto_publish_enabled.is_(True),
                            CardAutomationSettings.shadow_mode.is_(False),
                            QuestionCluster.status.in_(
                                [QuestionClusterStatus.SHADOW, QuestionClusterStatus.CANDIDATE]
                            ),
                        ),
                    )
                )
                .order_by(QuestionCluster.updated_at)
                .limit(200)
            )
        ).all()
        answer_work = (
            await session.execute(
                select(
                    QuestionCluster.id,
                    QuestionCluster.membership_revision,
                    QuestionCluster.answer_status,
                    or_(
                        QuestionCluster.answer_contract.is_(None),
                        QuestionCluster.answer_status == AnswerContractStatus.REPAIR_PENDING,
                    ),
                )
                .join(
                    CardAutomationSettings,
                    CardAutomationSettings.direction_id == QuestionCluster.direction_id,
                )
                .where(ai_processing_condition())
                .order_by(
                    QuestionCluster.answer_contract.is_(None),
                    QuestionCluster.updated_at,
                    QuestionCluster.id,
                )
                .limit(200)
            )
        ).all()
        expired_personal_items = list(
            await session.scalars(
                select(PersonalReviewItem)
                .where(
                    PersonalReviewItem.status == PersonalReviewStatus.ACTIVE,
                    PersonalReviewItem.expires_at.is_not(None),
                    PersonalReviewItem.expires_at <= datetime.now(UTC),
                )
                .order_by(PersonalReviewItem.expires_at, PersonalReviewItem.id)
                .limit(500)
                .with_for_update(skip_locked=True)
            )
        )
        for item in expired_personal_items:
            item.status = PersonalReviewStatus.ARCHIVED
            item.version += 1
            settings = await session.get(CardAutomationSettings, item.direction_id)
            if settings is not None:
                await record_automation_decision(
                    session,
                    entity_type="personal_review_item",
                    entity_id=item.id,
                    idempotency_key=f"personal:{item.id}:expired",
                    decision_type=AutomationDecisionType.PERSONAL_REVIEW_ARCHIVED,
                    decision_source=AutomationDecisionSource.RULE,
                    reason="Personal review item expired and was archived",
                    confidence=None,
                    settings=settings,
                )
            else:
                logger.warning(
                    "Expired personal review item has no automation settings item_id=%s",
                    item.id,
                )
        if expired_personal_items:
            await session.commit()
    for cluster_id, membership_revision, answer_status, needs_generation in answer_work:
        await enqueue_card_automation_job(
            (
                "review_cluster_for_automation"
                if answer_status == AnswerContractStatus.REVIEW_PENDING
                else "generate_cluster_candidate"
                if needs_generation
                else "validate_cluster_answer"
            ),
            str(cluster_id),
            membership_revision,
            redis=ctx["redis"],
        )
    for question_id, revision in occurrences:
        await enqueue_card_automation_job(
            "route_question_occurrence",
            str(question_id),
            revision,
            redis=ctx["redis"],
        )
    for cluster_id, membership_revision in dirty_clusters:
        await enqueue_card_automation_job(
            "recalculate_cluster_stats",
            str(cluster_id),
            membership_revision,
            redis=ctx["redis"],
        )
    if expired_personal_items:
        logger.info(
            "Archived expired personal review items count=%s",
            len(expired_personal_items),
        )


async def route_question_occurrence(ctx: dict[str, Any], question_id: str, revision: int) -> None:
    attempt = max(int(ctx.get("job_try", 1)), 1)
    final_attempt = attempt >= CARD_AUTOMATION_JOB_MAX_TRIES
    try:
        await process_question_occurrence(
            async_session_factory,
            _ai(ctx),
            UUID(question_id),
            revision,
            retryable_failure_is_terminal=final_attempt,
        )
    except InterviewAIError as error:
        await defer_model_cooldown(ctx, error)
        if error.retryable and not final_attempt:
            raise Retry(defer=retry_delay(error, min(60 * (2 ** (attempt - 1)), 900))) from error
        if error.retryable:
            logger.warning(
                "Occurrence routing retry budget exhausted question_id=%s revision=%s "
                "code=%s attempt=%s",
                question_id,
                revision,
                error.code,
                attempt,
            )
        return
    await _enqueue_followups(ctx, UUID(question_id))


async def find_existing_card_match(ctx: dict[str, Any], question_id: str, revision: int) -> None:
    # Public, revision-aware manual retry entry point. The orchestrator resumes
    # from persisted state and all writes remain idempotent.
    await route_question_occurrence(ctx, question_id, revision)


async def assign_question_cluster(ctx: dict[str, Any], question_id: str, revision: int) -> None:
    await route_question_occurrence(ctx, question_id, revision)


async def recalculate_cluster_stats(
    ctx: dict[str, Any], cluster_id: str, membership_revision: int
) -> None:
    parsed_id = UUID(cluster_id)
    async with async_session_factory() as session:
        cluster = await session.scalar(
            select(QuestionCluster).where(QuestionCluster.id == parsed_id).with_for_update()
        )
        if cluster is None:
            return
        settings = await session.get(CardAutomationSettings, cluster.direction_id)
        if settings is None:
            return
        # Recalculate the newest committed membership even when this job was
        # queued for an older revision. This makes stale jobs useful rather
        # than allowing them to overwrite newer aggregate values.
        await recalculate_cluster_stats_model(session, cluster, settings)
        if (
            settings.global_auto_publish_enabled
            and cluster.answer_status is None
            and cluster.answer_contract is not None
            and not cluster.answer_contract.get("source_references")
            and not await session.scalar(
                select(AutomationDecision.id)
                .where(
                    AutomationDecision.entity_type == "cluster",
                    AutomationDecision.entity_id == cluster.id,
                    AutomationDecision.decision_source == AutomationDecisionSource.HUMAN,
                )
                .limit(1)
            )
        ):
            cluster.answer_contract = None
            cluster.answer_validation = None
            cluster.version += 1
        current_revision = cluster.membership_revision
        should_generate = (
            settings.enabled
            and settings.cluster_moderation_enabled
            and cluster.status is QuestionClusterStatus.NEEDS_REVIEW
            and cluster.answer_status is None
            and cluster.answer_contract is None
        )
        should_validate = (
            settings.enabled
            and settings.cluster_moderation_enabled
            and cluster.status is QuestionClusterStatus.NEEDS_REVIEW
            and cluster.answer_status is None
            and cluster.answer_contract is not None
            and cluster.answer_validation is None
        )
        await session.commit()
    if current_revision != membership_revision:
        logger.info(
            "Recalculated newer cluster revision cluster_id=%s requested=%s current=%s",
            cluster_id,
            membership_revision,
            current_revision,
        )
    if should_generate:
        await enqueue_card_automation_job(
            "generate_cluster_candidate",
            cluster_id,
            current_revision,
            redis=ctx["redis"],
        )
    elif should_validate:
        await enqueue_card_automation_job(
            "validate_cluster_answer",
            cluster_id,
            current_revision,
            redis=ctx["redis"],
        )


async def promote_question_cluster(
    ctx: dict[str, Any], cluster_id: str, membership_revision: int
) -> None:
    await recalculate_cluster_stats(ctx, cluster_id, membership_revision)


async def generate_cluster_candidate(
    ctx: dict[str, Any], cluster_id: str, membership_revision: int, *, manual_draft: bool = False
) -> None:
    parsed_id = UUID(cluster_id)
    async with async_session_factory() as session:
        cluster = await session.get(QuestionCluster, parsed_id, with_for_update=True)
        if (
            cluster is None
            or cluster.membership_revision != membership_revision
            or cluster.status not in _ANSWER_DRAFT_CLUSTER_STATUSES
            or (
                cluster.answer_contract is not None
                and cluster.answer_status != AnswerContractStatus.REPAIR_PENDING
            )
            or cluster.answer_status
            not in (
                {
                    None,
                    AnswerContractStatus.NEEDS_EXPERT_SOURCE,
                    AnswerContractStatus.NEEDS_MANUAL_REVIEW,
                    AnswerContractStatus.REPAIR_PENDING,
                }
                if manual_draft
                else {
                    None,
                    AnswerContractStatus.NEEDS_EXPERT_SOURCE,
                    AnswerContractStatus.REPAIR_PENDING,
                }
            )
        ):
            return
        if (
            not manual_draft
            and cluster.answer_status is AnswerContractStatus.NEEDS_EXPERT_SOURCE
            and cluster.source_retry_after is not None
            and cluster.source_retry_after > datetime.now(UTC)
        ):
            return
        settings = await session.get(CardAutomationSettings, cluster.direction_id)
        if settings is None or not settings.enabled or not settings.cluster_moderation_enabled:
            return
        repair_context = None
        if cluster.answer_status == AnswerContractStatus.REPAIR_PENDING:
            if cluster.answer_repair_attempts >= MAX_ANSWER_REPAIRS:
                cluster.answer_status = AnswerContractStatus.NEEDS_MANUAL_REVIEW
                cluster.version += 1
                await session.commit()
                return
            repair_context = cast(
                dict[str, object],
                redact_untrusted_value(
                    {
                        "previous_contract": cluster.answer_contract,
                        "validation": cluster.answer_validation,
                    }
                ),
            )
        version = cluster.version
        question = redact_untrusted_text(cluster.canonical_question)[:4_000]
        sources = await _trusted_sources(session, cluster)
        if repair_context is not None:
            pinned = await load_trusted_sources(
                session, cluster, source_ids=_contract_source_ids(cluster.answer_contract)
            )
            sources = list(
                {source["source_id"]: source for source in [*pinned, *sources]}.values()
            )[:12]
            previous = repair_context.get("previous_contract")
            if isinstance(previous, dict):
                allowed = {source["source_id"] for source in sources}
                previous["source_references"] = [
                    ref for ref in _contract_source_ids(cluster.answer_contract) if ref in allowed
                ]
        if not manual_draft and await _defer_unpublishable_answer(
            session, cluster, settings, sources
        ):
            await session.commit()
            return
        analysis_draft = (
            None
            if settings.global_auto_publish_enabled or repair_context is not None
            else await analysis_answer_draft_for_cluster(session, cluster.id)
        )
        provider = _ai(ctx)
        generation_input_hash = _answer_input_hash(
            question,
            sources,
            ANSWER_CONTRACT_PROMPT_VERSION,
            ANSWER_CONTRACT_SCHEMA_VERSION,
            _analysis_model_name(provider),
            direction_id=cluster.direction_id,
            provider_name=provider.name,
            max_output_tokens=getattr(provider, "review_max_output_tokens", 4_000),
            analysis_draft=analysis_draft,
            contract=repair_context,
        )
        cached_generation = await _cached_answer_decision(
            session,
            input_hash=generation_input_hash,
            decision_type=AutomationDecisionType.ANSWER_CONTRACT_GENERATED,
            prompt_version=ANSWER_CONTRACT_PROMPT_VERSION,
            schema_version=ANSWER_CONTRACT_SCHEMA_VERSION,
        )
        cached_contract: AnswerContract | None = None
        if cached_generation is not None and cached_generation.judge_result is not None:
            try:
                cached_contract = AnswerContract.model_validate(cached_generation.judge_result)
            except (TypeError, ValueError):
                logger.warning(
                    "Ignoring invalid cached answer contract decision_id=%s",
                    cached_generation.id,
                )
    allowed_source_ids = {str(source["source_id"]) for source in sources}
    if cached_contract is not None:
        contract_payload = cached_contract.model_dump(mode="json")
        confidence = cached_contract.confidence
        usage = None
        prompt_version = ANSWER_CONTRACT_PROMPT_VERSION
        schema_version = ANSWER_CONTRACT_SCHEMA_VERSION
        decision_source = AutomationDecisionSource.RULE
        reason = "Answer contract reused from an identical validated AI input"
        latency_ms = None
    elif analysis_draft is not None:
        contract_payload = answer_contract_from_analysis_draft(analysis_draft)
        confidence = 0.5
        usage = None
        prompt_version = ANSWER_CONTRACT_PROMPT_VERSION
        schema_version = ANSWER_CONTRACT_SCHEMA_VERSION
        decision_source = AutomationDecisionSource.RULE
        reason = (
            "Answer draft transferred from the latest non-rejected AI interview review; "
            "source validation is pending"
        )
        latency_ms = None
    else:
        started_at = time.perf_counter()
        try:
            if repair_context is not None:
                generated = await provider.generate_answer_contract(
                    question=question, trusted_sources=sources, repair_context=repair_context
                )
            else:
                generated = await provider.generate_answer_contract(
                    question=question, trusted_sources=sources
                )
        except InterviewAIError as error:
            await defer_model_cooldown(ctx, error)
            latency_ms = _elapsed_ms(started_at)
            attempt = max(int(ctx.get("job_try", 1)), 1)
            if error.retryable and attempt < ANSWER_JOB_MAX_TRIES:
                logger.warning(
                    "Answer contract generation retry cluster_id=%s code=%s attempt=%s",
                    cluster_id,
                    error.code,
                    attempt,
                )
                raise Retry(
                    defer=retry_delay(error, min(60 * (2 ** (attempt - 1)), 900))
                ) from error
            async with async_session_factory() as session:
                cluster = await session.scalar(
                    select(QuestionCluster).where(QuestionCluster.id == parsed_id).with_for_update()
                )
                if (
                    cluster is None
                    or cluster.version != version
                    or cluster.membership_revision != membership_revision
                ):
                    return
                settings = await session.get(CardAutomationSettings, cluster.direction_id)
                if (
                    settings is None
                    or not settings.enabled
                    or not settings.cluster_moderation_enabled
                ):
                    return
                cluster.ai_error_code = error.code
                cluster.answer_status = (
                    AnswerContractStatus.WAITING_FOR_AI
                    if error.code in AI_SERVICE_ERRORS
                    else AnswerContractStatus.NEEDS_MANUAL_REVIEW
                )
                cluster.ai_retry_after = (
                    datetime.now(UTC) + timedelta(hours=1)
                    if error.code in AI_SERVICE_ERRORS
                    else None
                )
                cluster.version += 1
                await _record_answer_terminal_decision(
                    session,
                    cluster=cluster,
                    settings=settings,
                    membership_revision=membership_revision,
                    decision_type=AutomationDecisionType.ANSWER_CONTRACT_FAILED,
                    decision_source=AutomationDecisionSource.SEMANTIC_JUDGE,
                    stage="generation",
                    outcome=("retry_exhausted" if error.retryable else "failed"),
                    error_code=error.code,
                    reason=(
                        f"Answer contract generation retry budget exhausted: {error.safe_message}"
                        if error.retryable
                        else f"Answer contract generation failed: {error.safe_message}"
                    ),
                    retryable=error.retryable,
                    schema_version=ANSWER_CONTRACT_SCHEMA_VERSION,
                    latency_ms=latency_ms,
                )
                await session.commit()
            logger.warning(
                "Answer contract generation terminal cluster_id=%s code=%s retryable=%s attempt=%s",
                cluster_id,
                error.code,
                error.retryable,
                attempt,
            )
            return
        latency_ms = _elapsed_ms(started_at)
        contract_payload = generated.output.model_dump(mode="json")
        confidence = generated.output.confidence
        usage = generated.usage
        prompt_version = generated.prompt_version
        schema_version = generated.schema_version
        # Keep the request identity. The API may report a dated snapshot instead
        # of the configured alias; that actual model belongs in usage, not the key.
        decision_source = AutomationDecisionSource.SEMANTIC_JUDGE
        reason = (
            "Answer contract generated from internal sources; validation is pending"
            if sources
            else (
                "Best-effort AI answer draft generated without internal sources; "
                "expert review is required"
            )
        )
    contract_payload["source_references"] = [
        reference
        for reference in contract_payload.get("source_references", [])
        if str(reference) in allowed_source_ids
    ]
    async with async_session_factory() as session:
        cluster = await session.scalar(
            select(QuestionCluster).where(QuestionCluster.id == parsed_id).with_for_update()
        )
        if (
            cluster is None
            or cluster.version != version
            or cluster.membership_revision != membership_revision
        ):
            return
        settings = await session.get(CardAutomationSettings, cluster.direction_id)
        if settings is None or not settings.enabled or not settings.cluster_moderation_enabled:
            return
        if repair_context is not None:
            cluster.answer_repair_attempts += 1
        cluster.ai_error_code = None
        cluster.ai_retry_after = None
        cluster.source_retry_after = None
        cluster.answer_contract = contract_payload
        cluster.answer_validation = None
        cluster.answer_status = None
        cluster.version += 1
        await record_automation_decision(
            session,
            entity_type="cluster",
            entity_id=cluster.id,
            idempotency_key=f"cluster:{cluster.id}:answer-contract:{membership_revision}:{generation_input_hash[:24]}",
            decision_type=AutomationDecisionType.ANSWER_CONTRACT_GENERATED,
            decision_source=decision_source,
            reason=reason,
            confidence=confidence,
            settings=settings,
            selected_cluster_id=cluster.id,
            judge_result=contract_payload,
            retrieval_scores={
                "request_model": _analysis_model_name(provider),
                "answer_cache_version": ANSWER_CACHE_VERSION,
                "answer_source_ids": [source["source_id"] for source in sources],
            },
            usage=usage,
            ai_tier="analysis" if usage is not None else None,
            prompt_version=prompt_version,
            schema_version=schema_version,
            input_hash=generation_input_hash,
            latency_ms=latency_ms,
        )
        await session.commit()
    await enqueue_card_automation_job(
        "validate_cluster_answer",
        cluster_id,
        membership_revision,
        redis=ctx["redis"],
        manual_draft=manual_draft,
    )


async def validate_cluster_answer(
    ctx: dict[str, Any], cluster_id: str, membership_revision: int, *, manual_draft: bool = False
) -> None:
    parsed_id = UUID(cluster_id)
    if await _publish_ready_cluster(parsed_id, membership_revision):
        return
    async with async_session_factory() as session:
        cluster = await session.get(QuestionCluster, parsed_id, with_for_update=True)
        if (
            cluster is None
            or cluster.membership_revision != membership_revision
            or cluster.status not in _ANSWER_DRAFT_CLUSTER_STATUSES
            or cluster.answer_contract is None
            or cluster.answer_validation is not None
            or cluster.answer_status is not None
        ):
            return
        settings = await session.get(CardAutomationSettings, cluster.direction_id)
        if settings is None or not settings.enabled or not settings.cluster_moderation_enabled:
            return
        version = cluster.version
        question = redact_untrusted_text(cluster.canonical_question)[:4_000]
        contract_payload = dict(cluster.answer_contract)
        safe_contract_payload = cast(
            dict[str, object],
            redact_untrusted_value(contract_payload),
        )
        sources = await _validation_sources(session, cluster)
        if not manual_draft and await _defer_unpublishable_answer(
            session, cluster, settings, sources
        ):
            await session.commit()
            return
        # Internal allowlisted UUIDs are identifiers, not personal numbers. Keep
        # them intact while redacting the untrusted answer's prose.
        allowed_ids = {s["source_id"] for s in sources}
        references = contract_payload.get("source_references")
        if isinstance(references, list):
            safe_contract_payload["source_references"] = [
                ref if isinstance(ref, str) and ref in allowed_ids else redact_untrusted_value(ref)
                for ref in references
            ]
        provider = _ai(ctx)
        validation_input_hash = _answer_input_hash(
            question,
            sources,
            ANSWER_VALIDATION_PROMPT_VERSION,
            ANSWER_VALIDATION_SCHEMA_VERSION,
            _analysis_model_name(provider),
            direction_id=cluster.direction_id,
            provider_name=provider.name,
            max_output_tokens=getattr(provider, "review_max_output_tokens", 4_000),
            contract=safe_contract_payload,
        )
        cached_validation = await _cached_answer_decision(
            session,
            input_hash=validation_input_hash,
            decision_type=AutomationDecisionType.ANSWER_CONTRACT_VALIDATED,
            prompt_version=ANSWER_VALIDATION_PROMPT_VERSION,
            schema_version=ANSWER_VALIDATION_SCHEMA_VERSION,
        )
        cached_validation_output: AnswerValidationResult | None = None
        if cached_validation is not None and cached_validation.judge_result is not None:
            try:
                cached_validation_output = AnswerValidationResult.model_validate(
                    cached_validation.judge_result
                )
            except (TypeError, ValueError):
                logger.warning(
                    "Ignoring invalid cached answer validation decision_id=%s",
                    cached_validation.id,
                )
    missing_references = set(_contract_source_ids(contract_payload)) - allowed_ids
    if not sources or missing_references:
        async with async_session_factory() as session:
            cluster = await session.scalar(
                select(QuestionCluster).where(QuestionCluster.id == parsed_id).with_for_update()
            )
            if (
                cluster is None
                or cluster.version != version
                or cluster.membership_revision != membership_revision
                or cluster.answer_contract != contract_payload
            ):
                return
            settings = await session.get(CardAutomationSettings, cluster.direction_id)
            if settings is None or not settings.enabled or not settings.cluster_moderation_enabled:
                return
            cluster.answer_status = (
                AnswerContractStatus.REVIEW_PENDING
                if sources
                and not manual_draft
                and settings.global_auto_publish_enabled
                and not settings.shadow_mode
                and cluster.answer_repair_attempts < MAX_ANSWER_REPAIRS
                else AnswerContractStatus.NEEDS_EXPERT_SOURCE
                if not sources or manual_draft
                else AnswerContractStatus.NEEDS_MANUAL_REVIEW
            )
            if not sources:
                cluster.ai_error_code = "no_trusted_sources"
                cluster.source_retry_after = datetime.now(UTC) + SOURCE_RECHECK_INTERVAL
            cluster.version += 1
            await _record_answer_terminal_decision(
                session,
                cluster=cluster,
                settings=settings,
                membership_revision=membership_revision,
                decision_type=AutomationDecisionType.ANSWER_CONTRACT_NEEDS_SOURCE,
                decision_source=AutomationDecisionSource.RULE,
                stage="validation",
                outcome="needs_source",
                error_code="missing_trusted_references"
                if missing_references
                else "no_trusted_sources",
                reason=MISSING_REFERENCE_FINDING
                if missing_references
                else "Answer validation needs an approved internal source",
            )
            await session.commit()
        logger.info(
            "Answer contract validation blocked cluster_id=%s code=%s",
            cluster_id,
            "missing_trusted_references" if missing_references else "no_trusted_sources",
        )
        return
    if cached_validation_output is not None:
        validation_payload = cached_validation_output.model_dump(mode="json")
        validation_supported = cached_validation_output.supported
        confidence = cached_validation_output.confidence
        usage = None
        prompt_version = ANSWER_VALIDATION_PROMPT_VERSION
        schema_version = ANSWER_VALIDATION_SCHEMA_VERSION
        decision_source = AutomationDecisionSource.RULE
        reason = "Answer validation reused from an identical validated AI input"
        latency_ms = None
    else:
        started_at = time.perf_counter()
        try:
            validation = await provider.validate_answer_contract(
                question=question,
                contract=safe_contract_payload,
                trusted_sources=sources,
            )
        except InterviewAIError as error:
            await defer_model_cooldown(ctx, error)
            latency_ms = _elapsed_ms(started_at)
            attempt = max(int(ctx.get("job_try", 1)), 1)
            if error.retryable and attempt < ANSWER_JOB_MAX_TRIES:
                logger.warning(
                    "Answer contract validation retry cluster_id=%s code=%s attempt=%s",
                    cluster_id,
                    error.code,
                    attempt,
                )
                raise Retry(
                    defer=retry_delay(error, min(60 * (2 ** (attempt - 1)), 900))
                ) from error
            async with async_session_factory() as session:
                cluster = await session.scalar(
                    select(QuestionCluster).where(QuestionCluster.id == parsed_id).with_for_update()
                )
                if (
                    cluster is None
                    or cluster.version != version
                    or cluster.membership_revision != membership_revision
                    or cluster.answer_contract != contract_payload
                ):
                    return
                settings = await session.get(CardAutomationSettings, cluster.direction_id)
                if (
                    settings is None
                    or not settings.enabled
                    or not settings.cluster_moderation_enabled
                ):
                    return
                cluster.ai_error_code = error.code
                cluster.answer_status = (
                    AnswerContractStatus.WAITING_FOR_AI
                    if error.code in AI_SERVICE_ERRORS
                    else AnswerContractStatus.NEEDS_MANUAL_REVIEW
                )
                cluster.ai_retry_after = (
                    datetime.now(UTC) + timedelta(hours=1)
                    if error.code in AI_SERVICE_ERRORS
                    else None
                )
                cluster.version += 1
                await _record_answer_terminal_decision(
                    session,
                    cluster=cluster,
                    settings=settings,
                    membership_revision=membership_revision,
                    decision_type=AutomationDecisionType.ANSWER_VALIDATION_FAILED,
                    decision_source=AutomationDecisionSource.SEMANTIC_JUDGE,
                    stage="validation",
                    outcome=("retry_exhausted" if error.retryable else "failed"),
                    error_code=error.code,
                    reason=(
                        f"Answer contract validation retry budget exhausted: {error.safe_message}"
                        if error.retryable
                        else f"Answer contract validation failed: {error.safe_message}"
                    ),
                    retryable=error.retryable,
                    schema_version=ANSWER_VALIDATION_SCHEMA_VERSION,
                    latency_ms=latency_ms,
                )
                await session.commit()
            logger.warning(
                "Answer contract validation terminal cluster_id=%s code=%s retryable=%s attempt=%s",
                cluster_id,
                error.code,
                error.retryable,
                attempt,
            )
            return
        latency_ms = _elapsed_ms(started_at)
        validation_payload = validation.output.model_dump(mode="json")
        validation_supported = validation.output.supported
        confidence = validation.output.confidence
        usage = validation.usage
        prompt_version = validation.prompt_version
        schema_version = validation.schema_version
        decision_source = AutomationDecisionSource.SEMANTIC_JUDGE
        reason = "Independent structured answer validation completed"
    references = contract_payload.get("source_references")
    supported = bool(
        validation_supported
        and isinstance(references, list)
        and references
        and validation_payload.get("question_is_self_contained") is True
        and validation_payload.get("answer_is_substantive") is True
        and not validation_payload.get("unverified_personal_claims")
        and not validation_payload.get("unsupported_claims")
        and not validation_payload.get("contradictions")
        and not validation_payload.get("missing_required_points")
        and not validation_payload.get("version_sensitive_claims")
    )
    async with async_session_factory() as session:
        cluster = await session.scalar(
            select(QuestionCluster).where(QuestionCluster.id == parsed_id).with_for_update()
        )
        if (
            cluster is None
            or cluster.version != version
            or cluster.membership_revision != membership_revision
            or cluster.answer_contract != contract_payload
        ):
            return
        settings = await session.get(CardAutomationSettings, cluster.direction_id)
        if settings is None or not settings.enabled or not settings.cluster_moderation_enabled:
            return
        cluster.answer_validation = validation_payload
        cluster.answer_status = (
            AnswerContractStatus.GENERATED_FROM_SOURCES
            if supported
            else AnswerContractStatus.REVIEW_PENDING
            if not manual_draft
            and settings.global_auto_publish_enabled
            and not settings.shadow_mode
            and validation_payload.get("question_is_self_contained") is not False
            and cluster.answer_repair_attempts < MAX_ANSWER_REPAIRS
            else AnswerContractStatus.NEEDS_MANUAL_REVIEW
        )
        cluster.version += 1
        await record_automation_decision(
            session,
            entity_type="cluster",
            entity_id=cluster.id,
            idempotency_key=f"cluster:{cluster.id}:answer-validation:{membership_revision}:{validation_input_hash[:24]}",
            decision_type=AutomationDecisionType.ANSWER_CONTRACT_VALIDATED,
            decision_source=decision_source,
            reason=reason,
            confidence=confidence,
            settings=settings,
            selected_cluster_id=cluster.id,
            judge_result=validation_payload,
            retrieval_scores={
                "publication_sources_hash": _publication_sources_hash(sources),
                "answer_source_ids": [source["source_id"] for source in sources],
                "request_model": _analysis_model_name(provider),
                "answer_cache_version": ANSWER_CACHE_VERSION,
            },
            usage=usage,
            ai_tier="analysis" if usage is not None else None,
            prompt_version=prompt_version,
            schema_version=schema_version,
            input_hash=validation_input_hash,
            latency_ms=latency_ms,
        )
        await session.commit()

    await _publish_ready_cluster(parsed_id, membership_revision)


async def review_cluster_for_automation(
    ctx: dict[str, Any], cluster_id: str, membership_revision: int
) -> None:
    from app.interviews.card_review_recovery import review_cluster

    parsed_id = UUID(cluster_id)
    async with async_session_factory() as session:
        cluster = await session.get(QuestionCluster, parsed_id)
        if cluster is None:
            return
        version = cluster.version
    try:
        await review_cluster(ctx, parsed_id, membership_revision, async_session_factory, _ai(ctx))
    except InterviewAIError as error:
        await defer_model_cooldown(ctx, error)
        attempt = max(int(ctx.get("job_try", 1)), 1)
        if error.retryable and attempt < ANSWER_JOB_MAX_TRIES:
            raise Retry(defer=retry_delay(error, min(60 * 2 ** (attempt - 1), 900))) from error
        async with async_session_factory() as session:
            cluster = await session.get(QuestionCluster, parsed_id, with_for_update=True)
            if (
                cluster is None
                or cluster.version != version
                or cluster.membership_revision != membership_revision
                or cluster.answer_status != AnswerContractStatus.REVIEW_PENDING
            ):
                return
            settings = await session.get(CardAutomationSettings, cluster.direction_id)
            if settings is None:
                return
            service_failure = error.code in AI_SERVICE_ERRORS
            cluster.answer_status = (
                AnswerContractStatus.WAITING_FOR_AI
                if service_failure
                else AnswerContractStatus.NEEDS_MANUAL_REVIEW
            )
            cluster.ai_retry_after = (
                datetime.now(UTC) + timedelta(hours=1) if service_failure else None
            )
            cluster.ai_error_code = error.code
            cluster.version += 1
            await _record_answer_terminal_decision(
                session,
                cluster=cluster,
                settings=settings,
                membership_revision=membership_revision,
                decision_type=AutomationDecisionType.ANSWER_VALIDATION_FAILED,
                decision_source=AutomationDecisionSource.SEMANTIC_JUDGE,
                stage="review",
                outcome=f"failed-{cluster.version}",
                error_code=error.code,
                reason=error.safe_message,
                retryable=error.retryable,
            )
            await session.commit()


async def _defer_unpublishable_answer(
    session: AsyncSession,
    cluster: QuestionCluster,
    settings: CardAutomationSettings,
    sources: list[dict[str, str]],
) -> bool:
    from app.interviews.card_auto_publish import publication_preflight_reason

    if not settings.global_auto_publish_enabled or settings.shadow_mode:
        return False
    reason = await publication_preflight_reason(session, cluster, settings)
    status = AnswerContractStatus.NEEDS_MANUAL_REVIEW
    if reason == "Possible duplicate found during the publication check":
        status = AnswerContractStatus.REVIEW_PENDING
    if reason is None and not sources:
        reason = (
            "No trusted sources: automatic answer generation skipped; expert material is required"
        )
        status = AnswerContractStatus.NEEDS_EXPERT_SOURCE
    if reason is None:
        return False
    if status is AnswerContractStatus.NEEDS_EXPERT_SOURCE:
        cluster.ai_error_code = "no_trusted_sources"
        cluster.source_retry_after = datetime.now(UTC) + SOURCE_RECHECK_INTERVAL
    if cluster.answer_status != status:
        cluster.answer_status = status
        cluster.version += 1
    # A missing-source cluster can be reconsidered after material is added.
    # Reconciliation must not append the same audit event on every pass.
    await _record_answer_terminal_decision(
        session,
        cluster=cluster,
        settings=settings,
        membership_revision=cluster.membership_revision,
        decision_type=AutomationDecisionType.ANSWER_CONTRACT_NEEDS_SOURCE
        if status is AnswerContractStatus.NEEDS_EXPERT_SOURCE
        else AutomationDecisionType.ANSWER_VALIDATION_FAILED,
        decision_source=AutomationDecisionSource.RULE,
        stage="preflight",
        outcome=hashlib.sha256(reason.encode()).hexdigest()[:16],
        error_code="no_trusted_sources"
        if status is AnswerContractStatus.NEEDS_EXPERT_SOURCE
        else "publication_preflight_failed",
        reason=reason,
    )
    return True


async def _publish_ready_cluster(cluster_id: UUID, revision: int) -> bool:
    from app.interviews.card_auto_publish import publish_validated_cluster

    async with async_session_factory() as session:
        cluster = await session.get(QuestionCluster, cluster_id)
        if cluster is None or cluster.answer_validation is None:
            return False
        validation_decision = await _latest_answer_decision(
            session, cluster, AutomationDecisionType.ANSWER_CONTRACT_VALIDATED
        )
        pinned = _decision_source_ids(validation_decision)
        sources = (
            await load_trusted_sources(session, cluster, source_ids=pinned)
            if pinned is not None
            else await _validation_sources(session, cluster)
        )
        settings = await session.get(CardAutomationSettings, cluster.direction_id)
        if (
            settings is not None
            and settings.enabled
            and not settings.shadow_mode
            and settings.global_auto_publish_enabled
            and settings.cluster_moderation_enabled
            and cluster.status is QuestionClusterStatus.NEEDS_REVIEW
            and cluster.answer_status is AnswerContractStatus.GENERATED_FROM_SOURCES
            and cluster.membership_revision == revision
        ):
            if (
                validation_decision is None
                or validation_decision.prompt_version != ANSWER_VALIDATION_PROMPT_VERSION
                or validation_decision.retrieval_scores.get("publication_sources_hash")
                != _publication_sources_hash(sources)
            ):
                version = cluster.version
                current = await session.get(
                    QuestionCluster, cluster_id, with_for_update=True, populate_existing=True
                )
                if current is not None and current.version == version:
                    current.answer_validation = None
                    current.answer_status = None
                    current.version += 1
                    await session.commit()
                return False
        await publish_validated_cluster(
            session, cluster_id, revision, {s["source_id"] for s in sources}
        )
        await session.commit()
        return True


def _publication_sources_hash(sources: list[dict[str, str]]) -> str:
    return hashlib.sha256(
        json.dumps(sources, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


async def create_personal_review_item(ctx: dict[str, Any], question_id: str, revision: int) -> None:
    del ctx
    parsed_id = UUID(question_id)
    async with async_session_factory() as session:
        question = await session.scalar(
            select(IntelligenceQuestion)
            .where(IntelligenceQuestion.id == parsed_id)
            .with_for_update()
        )
        if (
            question is None
            or question.automation_revision != revision
            or question.direction_id is None
        ):
            return
        settings = await session.get(CardAutomationSettings, question.direction_id)
        if settings is None:
            return
        await ensure_personal_review_for_occurrence(
            session,
            question,
            settings,
            question.published_card_id,
        )
        await session.commit()


async def backfill_existing_questions(
    ctx: dict[str, Any],
    direction_id: str,
    batch_size: int = 100,
) -> None:
    """Prepare one bounded legacy batch and enqueue revision-aware occurrence jobs."""

    parsed_direction_id = UUID(direction_id)
    bounded_batch_size = min(max(int(batch_size), 1), 500)
    async with async_session_factory() as session:
        settings = await session.get(CardAutomationSettings, parsed_direction_id)
        if settings is None or not settings.enabled:
            return
        questions = list(
            await session.scalars(
                select(IntelligenceQuestion)
                .where(
                    IntelligenceQuestion.direction_id == parsed_direction_id,
                    IntelligenceQuestion.moderation_status
                    == IntelligenceQuestionModerationStatus.PENDING,
                    IntelligenceQuestion.alias_human_confirmed.is_(False),
                    IntelligenceQuestion.published_card_id.is_(None),
                    IntelligenceQuestion.automation_status == QuestionOccurrenceStatus.CREATED,
                )
                .order_by(IntelligenceQuestion.created_at, IntelligenceQuestion.id)
                .limit(bounded_batch_size)
                .with_for_update(skip_locked=True)
            )
        )
        queue_items = [(question.id, question.automation_revision) for question in questions]
        for question in questions:
            ensure_occurrence_transition(
                question.automation_status,
                QuestionOccurrenceStatus.ROUTING,
            )
            question.automation_status = QuestionOccurrenceStatus.ROUTING
            question.automation_error = None
        if questions:
            await session.commit()
    for question_id, revision in queue_items:
        await enqueue_card_automation_job(
            "route_question_occurrence",
            str(question_id),
            revision,
            redis=ctx["redis"],
        )
    logger.info(
        "Prepared bounded card automation backfill direction_id=%s count=%s",
        direction_id,
        len(queue_items),
    )


async def reprocess_question_occurrence(
    ctx: dict[str, Any], question_id: str, revision: int
) -> None:
    parsed_id = UUID(question_id)
    async with async_session_factory() as session:
        question = await session.scalar(
            select(IntelligenceQuestion)
            .where(IntelligenceQuestion.id == parsed_id)
            .with_for_update()
        )
        if question is None or question.automation_revision != revision:
            return
        if (
            question.alias_human_confirmed
            or question.moderation_status is not IntelligenceQuestionModerationStatus.PENDING
        ):
            return
        old_card_id = question.published_card_id
        old_cluster_id = question.cluster_id
        source_occurrence = await session.scalar(
            select(InterviewCardOccurrence)
            .where(InterviewCardOccurrence.source_question_id == question.id)
            .with_for_update()
        )
        if source_occurrence is not None:
            await session.delete(source_occurrence)
            await session.flush()
        if old_card_id is not None:
            card = await session.scalar(
                select(InterviewCard).where(InterviewCard.id == old_card_id).with_for_update()
            )
            if card is not None:
                await refresh_card_occurrence_stats(session, card)
        personal_items = list(
            await session.scalars(
                select(PersonalReviewItem)
                .where(PersonalReviewItem.source_occurrence_id == question.id)
                .with_for_update()
            )
        )
        for item in personal_items:
            if item.status is PersonalReviewStatus.REPLACED_BY_CANONICAL_CARD:
                item.status = PersonalReviewStatus.ACTIVE
                item.canonical_card_id = None
                item.replaced_by_card_id = None
                item.due_at = datetime.now(UTC)
                item.version += 1
        question.cluster_id = None
        if old_cluster_id is not None:
            old_cluster = await session.scalar(
                select(QuestionCluster)
                .where(QuestionCluster.id == old_cluster_id)
                .with_for_update()
            )
            if old_cluster is not None:
                old_cluster.membership_revision += 1
                old_cluster.quality_score = 0.0
                old_cluster.cluster_confidence = 0.0
                await session.flush()
                settings = await session.get(
                    CardAutomationSettings,
                    old_cluster.direction_id,
                )
                await recalculate_cluster_stats_model(session, old_cluster, settings)
                if old_cluster.occurrences_count == 0:
                    old_cluster.status = QuestionClusterStatus.IGNORED
                    old_cluster.promotion_reason = "Occurrence was manually reprocessed"
                    old_cluster.representative_occurrence_id = None
                    old_cluster.priority_score = 0.0
                    old_cluster.quality_score = 0.0
                    old_cluster.cluster_confidence = 0.0
                    old_cluster.version += 1
        question.automation_revision += 1
        new_revision = question.automation_revision
        ensure_occurrence_transition(
            question.automation_status,
            QuestionOccurrenceStatus.CREATED,
            manual_reopen=True,
        )
        question.automation_status = QuestionOccurrenceStatus.CREATED
        question.automation_error = None
        question.published_card_id = None
        question.automation_decision_source = None
        question.automation_decision_reason = None
        question.processed_at = None
        await session.commit()
    await enqueue_card_automation_job(
        "route_question_occurrence",
        question_id,
        new_revision,
        redis=ctx["redis"],
    )


async def _enqueue_followups(ctx: dict[str, Any], question_id: UUID) -> None:
    async with async_session_factory() as session:
        question = await session.get(IntelligenceQuestion, question_id)
        if question is None or question.cluster_id is None:
            return
        cluster = await session.get(QuestionCluster, question.cluster_id)
        if cluster is None:
            return
        cluster_id = str(cluster.id)
        membership_revision = cluster.membership_revision
    await enqueue_card_automation_job(
        "recalculate_cluster_stats",
        cluster_id,
        membership_revision,
        redis=ctx["redis"],
    )


async def _record_answer_terminal_decision(
    session: AsyncSession,
    *,
    cluster: QuestionCluster,
    settings: CardAutomationSettings,
    membership_revision: int,
    decision_type: AutomationDecisionType,
    decision_source: AutomationDecisionSource,
    stage: str,
    outcome: str,
    error_code: str,
    reason: str,
    retryable: bool = False,
    schema_version: str | None = None,
    latency_ms: int | None = None,
) -> None:
    await record_automation_decision(
        session,
        entity_type="cluster",
        entity_id=cluster.id,
        idempotency_key=(f"cluster:{cluster.id}:answer-{stage}:{membership_revision}:{outcome}"),
        decision_type=decision_type,
        decision_source=decision_source,
        reason=reason,
        confidence=None,
        settings=settings,
        selected_cluster_id=cluster.id,
        judge_result={
            "stage": stage,
            "outcome": outcome,
            "error_code": error_code,
            "retryable": retryable,
            "terminal": True,
        },
        schema_version=schema_version,
        latency_ms=latency_ms,
    )


def _contract_source_ids(contract: dict[str, object] | None) -> list[str]:
    references = (contract or {}).get("source_references", [])
    return (
        list(dict.fromkeys(ref for ref in references if isinstance(ref, str)))
        if isinstance(references, list)
        else []
    )


def _decision_source_ids(decision: AutomationDecision | None) -> list[str] | None:
    values = decision.retrieval_scores.get("answer_source_ids") if decision else None
    if isinstance(values, list) and all(isinstance(value, str) for value in values):
        return list(dict.fromkeys(values))
    return None


async def _latest_answer_decision(
    session: AsyncSession, cluster: QuestionCluster, decision_type: AutomationDecisionType
) -> AutomationDecision | None:
    output = (
        cluster.answer_contract
        if decision_type is AutomationDecisionType.ANSWER_CONTRACT_GENERATED
        else cluster.answer_validation
    )
    result = await session.scalar(
        select(AutomationDecision)
        .where(
            AutomationDecision.entity_type == "cluster",
            AutomationDecision.entity_id == cluster.id,
            AutomationDecision.decision_type == decision_type,
            AutomationDecision.judge_result == output,
            AutomationDecision.is_overridden.is_(False),
        )
        .order_by(AutomationDecision.created_at.desc(), AutomationDecision.id.desc())
        .limit(1)
    )
    return result


async def _validation_sources(
    session: AsyncSession, cluster: QuestionCluster
) -> list[dict[str, str]]:
    """Keep the generation evidence set; legacy contracts pin every cited source.

    IDs bypass ranking, never access/publication/trust checks. Current content
    is loaded so an edit invalidates validation instead of publishing old facts.
    """
    references = _contract_source_ids(cluster.answer_contract)
    generation = await _latest_answer_decision(
        session, cluster, AutomationDecisionType.ANSWER_CONTRACT_GENERATED
    )
    pinned = _decision_source_ids(generation)
    if pinned is not None:
        return await load_trusted_sources(
            session, cluster, source_ids=list(dict.fromkeys([*pinned, *references]))
        )
    if len(references) > 20:
        return []
    ranked = await _trusted_sources(session, cluster)
    # Legacy answers can cite a valid material outside the first 100 candidates
    # or top eight snippets. Resolve these references by ID before filling gaps.
    pinned_sources = await load_trusted_sources(session, cluster, source_ids=references)
    result = {source["source_id"]: source for source in pinned_sources}
    for source in ranked:
        if len(result) >= max(8, len(references)):
            break
        result.setdefault(source["source_id"], source)
    return list(result.values())


async def _trusted_sources(session: AsyncSession, cluster: QuestionCluster) -> list[dict[str, str]]:
    return await load_trusted_sources(session, cluster)


def _ai(ctx: dict[str, Any]) -> InterviewAIProvider:
    return cast(InterviewAIProvider, ctx["ai_provider"])


def _analysis_model_name(ai: InterviewAIProvider) -> str:
    return str(getattr(ai, "analysis_model", getattr(ai, "model", type(ai).__qualname__)))


async def _cached_answer_decision(
    session: AsyncSession,
    *,
    input_hash: str,
    decision_type: AutomationDecisionType,
    prompt_version: str,
    schema_version: str,
) -> AutomationDecision | None:
    return cast(
        AutomationDecision | None,
        await session.scalar(
            select(AutomationDecision)
            .where(
                AutomationDecision.input_hash == input_hash,
                AutomationDecision.decision_type == decision_type,
                AutomationDecision.prompt_version == prompt_version,
                AutomationDecision.schema_version == schema_version,
                # Only original provider results are cache entries. RULE copies
                # must not resurrect a result after its original is overridden.
                AutomationDecision.model_name.is_not(None),
                AutomationDecision.judge_result.is_not(None),
                AutomationDecision.is_overridden.is_(False),
            )
            .order_by(AutomationDecision.created_at.desc(), AutomationDecision.id.desc())
        ),
    )


def _answer_input_hash(
    question: str,
    sources: list[dict[str, str]],
    prompt_version: str,
    schema_version: str,
    model_name: str,
    *,
    direction_id: UUID,
    provider_name: str,
    max_output_tokens: int,
    contract: dict[str, object] | None = None,
    analysis_draft: str | None = None,
) -> str:
    payload = {
        # Older keys mixed requested and returned model names. Do not silently
        # reuse them or share cached source material across directions.
        "cache_version": ANSWER_CACHE_VERSION,
        "direction_id": str(direction_id),
        "provider": provider_name,
        "max_output_tokens": max_output_tokens,
        "question": question,
        "sources": sources,
        "contract": contract,
        "analysis_draft": analysis_draft,
        "prompt_version": prompt_version,
        "schema_version": schema_version,
        "model_name": model_name,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _elapsed_ms(started_at: float) -> int:
    return max(int((time.perf_counter() - started_at) * 1_000), 0)
