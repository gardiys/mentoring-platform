from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from arq import Retry
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.interviews.card_automation_domain import ensure_occurrence_transition
from app.interviews.card_automation_models import (
    AutomationDecision,
    CardAutomationSettings,
    PersonalReviewItem,
    QuestionCluster,
)
from app.interviews.card_automation_pipeline import (
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
from app.interviews.intelligence_ai import (
    ANSWER_CONTRACT_PROMPT_VERSION,
    ANSWER_CONTRACT_SCHEMA_VERSION,
    ANSWER_VALIDATION_PROMPT_VERSION,
    ANSWER_VALIDATION_SCHEMA_VERSION,
    InterviewAIError,
    InterviewAIProvider,
)
from app.interviews.intelligence_models import (
    IntelligenceAnswer,
    IntelligenceAnswerReview,
    IntelligenceQuestion,
    IntelligenceQuestionModerationStatus,
    IntelligenceReviewStatus,
)
from app.interviews.intelligence_queue import enqueue_card_automation_job
from app.interviews.models import InterviewCard, InterviewCardOccurrence

logger = logging.getLogger(__name__)
CARD_AUTOMATION_JOB_MAX_TRIES = 4
ANSWER_JOB_MAX_TRIES = CARD_AUTOMATION_JOB_MAX_TRIES
_ANSWER_DRAFT_CLUSTER_STATUSES = frozenset(
    {
        QuestionClusterStatus.SHADOW,
        QuestionClusterStatus.CANDIDATE,
        QuestionClusterStatus.NEEDS_REVIEW,
    }
)


async def reconcile_card_automation_jobs(ctx: dict[str, Any]) -> None:
    """Recover queued work after Redis or worker restarts."""

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
        dirty_clusters = (
            await session.execute(
                select(QuestionCluster.id, QuestionCluster.membership_revision).where(
                    QuestionCluster.stats_revision < QuestionCluster.membership_revision
                )
            )
        ).all()
        answer_work = (
            await session.execute(
                select(
                    QuestionCluster.id,
                    QuestionCluster.membership_revision,
                    QuestionCluster.answer_contract.is_(None),
                )
                .join(
                    CardAutomationSettings,
                    CardAutomationSettings.direction_id == QuestionCluster.direction_id,
                )
                .where(
                    CardAutomationSettings.enabled.is_(True),
                    CardAutomationSettings.cluster_moderation_enabled.is_(True),
                    QuestionCluster.status == QuestionClusterStatus.NEEDS_REVIEW,
                    or_(
                        QuestionCluster.answer_status.is_(None),
                        and_(
                            QuestionCluster.answer_contract.is_(None),
                            QuestionCluster.answer_status
                            == AnswerContractStatus.NEEDS_EXPERT_SOURCE,
                        ),
                    ),
                    (
                        QuestionCluster.answer_contract.is_(None)
                        | QuestionCluster.answer_validation.is_(None)
                    ),
                )
                .order_by(QuestionCluster.updated_at)
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
    for cluster_id, membership_revision, needs_generation in answer_work:
        await enqueue_card_automation_job(
            ("generate_cluster_candidate" if needs_generation else "validate_cluster_answer"),
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
        if error.retryable and not final_attempt:
            raise Retry(defer=min(60 * (2 ** (attempt - 1)), 900)) from error
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
        current_revision = cluster.membership_revision
        should_generate = (
            settings.enabled
            and settings.cluster_moderation_enabled
            and cluster.status is QuestionClusterStatus.NEEDS_REVIEW
            and cluster.answer_status in {None, AnswerContractStatus.NEEDS_EXPERT_SOURCE}
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
    ctx: dict[str, Any], cluster_id: str, membership_revision: int
) -> None:
    parsed_id = UUID(cluster_id)
    async with async_session_factory() as session:
        cluster = await session.get(QuestionCluster, parsed_id)
        if (
            cluster is None
            or cluster.membership_revision != membership_revision
            or cluster.status not in _ANSWER_DRAFT_CLUSTER_STATUSES
            or cluster.answer_contract is not None
            or cluster.answer_status not in {None, AnswerContractStatus.NEEDS_EXPERT_SOURCE}
        ):
            return
        settings = await session.get(CardAutomationSettings, cluster.direction_id)
        if settings is None or not settings.enabled or not settings.cluster_moderation_enabled:
            return
        version = cluster.version
        question = redact_untrusted_text(cluster.canonical_question)
        sources = await _trusted_sources(session, cluster)
        analysis_draft = await _analysis_answer_draft(session, cluster)
        provider = _ai(ctx)
        generation_input_hash = _answer_input_hash(
            question,
            sources,
            ANSWER_CONTRACT_PROMPT_VERSION,
            ANSWER_CONTRACT_SCHEMA_VERSION,
            _analysis_model_name(provider),
            analysis_draft=analysis_draft,
        )
        cached_generation = await _cached_answer_decision(
            session,
            input_hash=generation_input_hash,
            decision_type=AutomationDecisionType.ANSWER_CONTRACT_GENERATED,
            prompt_version=ANSWER_CONTRACT_PROMPT_VERSION,
            schema_version=ANSWER_CONTRACT_SCHEMA_VERSION,
            model_name=_analysis_model_name(provider),
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
        transferred_contract = AnswerContract(
            short_answer=analysis_draft,
            required_points=[],
            optional_points=[],
            common_mistakes=[],
            unsupported_claims=[
                "Ответ перенесён из AI-разбора собеседования и требует проверки."
            ],
            follow_up_questions=[],
            difficulty="mixed",
            version_scope=[],
            source_references=[],
            confidence=0.5,
        )
        contract_payload = transferred_contract.model_dump(mode="json")
        confidence = transferred_contract.confidence
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
            generated = await provider.generate_answer_contract(
                question=question[:4_000], trusted_sources=sources
            )
        except InterviewAIError as error:
            latency_ms = _elapsed_ms(started_at)
            attempt = max(int(ctx.get("job_try", 1)), 1)
            if error.retryable and attempt < ANSWER_JOB_MAX_TRIES:
                logger.warning(
                    "Answer contract generation retry cluster_id=%s code=%s attempt=%s",
                    cluster_id,
                    error.code,
                    attempt,
                )
                raise Retry(defer=min(60 * (2 ** (attempt - 1)), 900)) from error
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
                cluster.answer_status = AnswerContractStatus.NEEDS_MANUAL_REVIEW
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
        generation_input_hash = _answer_input_hash(
            question,
            sources,
            generated.prompt_version,
            ANSWER_CONTRACT_SCHEMA_VERSION,
            generated.usage.model,
        )
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
        cluster.answer_contract = contract_payload
        cluster.answer_validation = None
        cluster.answer_status = None
        cluster.version += 1
        await record_automation_decision(
            session,
            entity_type="cluster",
            entity_id=cluster.id,
            idempotency_key=f"cluster:{cluster.id}:answer-contract:{membership_revision}",
            decision_type=AutomationDecisionType.ANSWER_CONTRACT_GENERATED,
            decision_source=decision_source,
            reason=reason,
            confidence=confidence,
            settings=settings,
            selected_cluster_id=cluster.id,
            judge_result=contract_payload,
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
    )


async def validate_cluster_answer(
    ctx: dict[str, Any], cluster_id: str, membership_revision: int
) -> None:
    parsed_id = UUID(cluster_id)
    async with async_session_factory() as session:
        cluster = await session.get(QuestionCluster, parsed_id)
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
        question = redact_untrusted_text(cluster.canonical_question)
        contract_payload = dict(cluster.answer_contract)
        safe_contract_payload = cast(
            dict[str, object],
            redact_untrusted_value(contract_payload),
        )
        sources = await _trusted_sources(session, cluster)
        provider = _ai(ctx)
        validation_input_hash = _answer_input_hash(
            question,
            sources,
            ANSWER_VALIDATION_PROMPT_VERSION,
            ANSWER_VALIDATION_SCHEMA_VERSION,
            _analysis_model_name(provider),
            contract=safe_contract_payload,
        )
        cached_validation = await _cached_answer_decision(
            session,
            input_hash=validation_input_hash,
            decision_type=AutomationDecisionType.ANSWER_CONTRACT_VALIDATED,
            prompt_version=ANSWER_VALIDATION_PROMPT_VERSION,
            schema_version=ANSWER_VALIDATION_SCHEMA_VERSION,
            model_name=_analysis_model_name(provider),
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
    if not sources:
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
            cluster.answer_status = AnswerContractStatus.NEEDS_EXPERT_SOURCE
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
                error_code="no_trusted_sources",
                reason="Answer validation needs an approved internal source",
            )
            await session.commit()
        logger.info(
            "Answer contract validation blocked cluster_id=%s code=no_trusted_sources",
            cluster_id,
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
                question=question[:4_000],
                contract=safe_contract_payload,
                trusted_sources=sources,
            )
        except InterviewAIError as error:
            latency_ms = _elapsed_ms(started_at)
            attempt = max(int(ctx.get("job_try", 1)), 1)
            if error.retryable and attempt < ANSWER_JOB_MAX_TRIES:
                logger.warning(
                    "Answer contract validation retry cluster_id=%s code=%s attempt=%s",
                    cluster_id,
                    error.code,
                    attempt,
                )
                raise Retry(defer=min(60 * (2 ** (attempt - 1)), 900)) from error
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
                cluster.answer_status = AnswerContractStatus.NEEDS_MANUAL_REVIEW
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
        validation_input_hash = _answer_input_hash(
            question,
            sources,
            validation.prompt_version,
            ANSWER_VALIDATION_SCHEMA_VERSION,
            validation.usage.model,
            contract=safe_contract_payload,
        )
        decision_source = AutomationDecisionSource.SEMANTIC_JUDGE
        reason = "Independent structured answer validation completed"
    references = contract_payload.get("source_references")
    supported = bool(validation_supported and isinstance(references, list) and references)
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
            else AnswerContractStatus.NEEDS_EXPERT_SOURCE
        )
        cluster.version += 1
        await record_automation_decision(
            session,
            entity_type="cluster",
            entity_id=cluster.id,
            idempotency_key=f"cluster:{cluster.id}:answer-validation:{membership_revision}",
            decision_type=AutomationDecisionType.ANSWER_CONTRACT_VALIDATED,
            decision_source=decision_source,
            reason=reason,
            confidence=confidence,
            settings=settings,
            selected_cluster_id=cluster.id,
            judge_result=validation_payload,
            usage=usage,
            ai_tier="analysis" if usage is not None else None,
            prompt_version=prompt_version,
            schema_version=schema_version,
            input_hash=validation_input_hash,
            latency_ms=latency_ms,
        )
        await session.commit()


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


async def _trusted_sources(session: Any, cluster: QuestionCluster) -> list[dict[str, str]]:
    """Return small, explicitly identified internal source snippets.

    Candidate answers and raw transcripts are intentionally excluded. The
    source set is limited to human-published cards, knowledge entries and
    roadmap materials from the same direction.
    """

    from app.interviews.models import InterviewCard, InterviewDeck
    from app.knowledge.models import KnowledgeEntry, KnowledgeTopic, KnowledgeTopicTrack
    from app.roadmaps.models import Roadmap, RoadmapSection, Topic
    from app.tracks.models import LearningTrackRoadmap

    cards = list(
        await session.scalars(
            select(InterviewCard)
            .join(InterviewDeck, InterviewDeck.id == InterviewCard.deck_id)
            .where(
                InterviewDeck.track_id == cluster.direction_id,
                InterviewDeck.is_published.is_(True),
                InterviewCard.is_published.is_(True),
            )
            .order_by(InterviewCard.asked_count.desc(), InterviewCard.updated_at.desc())
            .limit(100)
        )
    )
    knowledge_rows = (
        await session.execute(
            select(
                KnowledgeEntry.id,
                KnowledgeEntry.title,
                KnowledgeEntry.summary,
                KnowledgeEntry.content_markdown,
            )
            .join(KnowledgeTopic, KnowledgeTopic.id == KnowledgeEntry.topic_id)
            .join(KnowledgeTopicTrack, KnowledgeTopicTrack.topic_id == KnowledgeTopic.id)
            .where(
                KnowledgeTopicTrack.track_id == cluster.direction_id,
                KnowledgeTopic.is_published.is_(True),
                KnowledgeEntry.is_published.is_(True),
            )
            .order_by(KnowledgeEntry.updated_at.desc())
            .limit(100)
        )
    ).all()
    roadmap_rows = (
        await session.execute(
            select(Topic.id, Topic.title, Topic.description, Topic.content_markdown)
            .join(RoadmapSection, RoadmapSection.id == Topic.section_id)
            .join(Roadmap, Roadmap.id == RoadmapSection.roadmap_id)
            .join(LearningTrackRoadmap, LearningTrackRoadmap.roadmap_id == Roadmap.id)
            .where(
                LearningTrackRoadmap.track_id == cluster.direction_id,
                Roadmap.is_published.is_(True),
                Topic.is_published.is_(True),
            )
            .order_by(Topic.updated_at.desc())
            .limit(100)
        )
    ).all()
    question_tokens = {
        token for token in cluster.normalized_canonical_question.split() if len(token) >= 3
    }
    ranked: list[tuple[int, str, str, str]] = []
    for card in cards:
        haystack = f"{card.category} {card.question_markdown}".casefold()
        score = sum(1 for token in question_tokens if token in haystack)
        if score:
            ranked.append(
                (
                    score,
                    f"interview_card:{card.id}",
                    card.question_markdown,
                    card.answer_markdown,
                )
            )
    for entry_id, title, summary, content in knowledge_rows:
        haystack = f"{title} {summary or ''}".casefold()
        score = sum(1 for token in question_tokens if token in haystack)
        if score:
            ranked.append(
                (
                    score,
                    f"knowledge_entry:{entry_id}",
                    title,
                    content,
                )
            )
    for topic_id, title, description, content in roadmap_rows:
        haystack = f"{title} {description or ''}".casefold()
        score = sum(1 for token in question_tokens if token in haystack)
        if score:
            ranked.append(
                (
                    score,
                    f"roadmap_topic:{topic_id}",
                    title,
                    content,
                )
            )
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [
        {
            "source_id": source_id,
            "title": redact_untrusted_text(title)[:500],
            "content": redact_untrusted_text(content)[:8_000],
        }
        for _score, source_id, title, content in ranked[:8]
    ]


async def _analysis_answer_draft(session: Any, cluster: QuestionCluster) -> str | None:
    """Return the latest reusable answer draft produced by interview AI review.

    This text is intentionally not included in ``_trusted_sources``: it is a
    useful moderation draft, but it has not been verified by a human or an
    approved internal source yet.
    """

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
                IntelligenceQuestion.cluster_id == cluster.id,
                IntelligenceAnswerReview.status != IntelligenceReviewStatus.REJECTED,
                IntelligenceAnswerReview.suggested_better_answer.is_not(None),
            )
            .order_by(
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
    model_name: str,
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
                AutomationDecision.model_name == model_name,
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
    contract: dict[str, object] | None = None,
    analysis_draft: str | None = None,
) -> str:
    payload = {
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
