"""Bounded, auditable reconsideration of fixable card blockers."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from app.interviews.ai_rate_limit import CONTINUE_ERROR, defer_model_cooldown
from app.interviews.card_auto_publish import (
    link_verified_cluster_match,
    publication_preflight_reason,
    publication_quality_passes,
)
from app.interviews.card_automation_models import (
    AutomationDecision,
    CardAutomationSettings,
    QuestionCluster,
)
from app.interviews.card_automation_pipeline import record_automation_decision
from app.interviews.card_automation_privacy import redact_untrusted_text
from app.interviews.card_automation_schemas import AnswerContract, AnswerValidationResult
from app.interviews.card_automation_types import AnswerContractStatus as Status
from app.interviews.card_automation_types import AutomationDecisionSource as Source
from app.interviews.card_automation_types import AutomationDecisionType as Decision
from app.interviews.card_automation_types import QuestionClusterStatus
from app.interviews.card_cluster_matching import current_cluster_matches, match_fingerprint
from app.interviews.intelligence_ai import InterviewAIError, InterviewAIProvider
from app.interviews.intelligence_queue import enqueue_card_automation_job
from app.interviews.models import InterviewCard, InterviewDeck

REVIEW_POLICY_VERSION = 1
DUPLICATE_REASON = "Possible duplicate found during the publication check"


def no_human_decision() -> ColumnElement[bool]:
    return ~exists(
        select(AutomationDecision.id).where(
            AutomationDecision.entity_type == "cluster",
            AutomationDecision.entity_id == QuestionCluster.id,
            AutomationDecision.decision_source == Source.HUMAN,
        )
    )


async def queue_review_backlog(
    factory: async_sessionmaker[AsyncSession], *, limit: int = 50
) -> int:
    async with factory() as session:
        rows = list(
            await session.scalars(
                select(QuestionCluster)
                .join(
                    CardAutomationSettings,
                    CardAutomationSettings.direction_id == QuestionCluster.direction_id,
                )
                .where(
                    QuestionCluster.review_policy_version < REVIEW_POLICY_VERSION,
                    QuestionCluster.status == QuestionClusterStatus.NEEDS_REVIEW,
                    QuestionCluster.linked_card_id.is_(None),
                    QuestionCluster.answer_status.in_(
                        [
                            Status.NEEDS_EXPERT_SOURCE,
                            Status.NEEDS_MANUAL_REVIEW,
                            Status.GENERATED_FROM_SOURCES,
                        ]
                    ),
                    CardAutomationSettings.enabled.is_(True),
                    CardAutomationSettings.shadow_mode.is_(False),
                    CardAutomationSettings.global_auto_publish_enabled.is_(True),
                    CardAutomationSettings.cluster_moderation_enabled.is_(True),
                    no_human_decision(),
                )
                .order_by(QuestionCluster.id)
                .limit(limit)
                .with_for_update(of=QuestionCluster, skip_locked=True)
            )
        )
        for cluster in rows:
            settings = await session.get(CardAutomationSettings, cluster.direction_id)
            assert settings is not None
            previous = cluster.answer_repair_attempts
            cluster.review_policy_version = REVIEW_POLICY_VERSION
            cluster.answer_status = Status.REVIEW_PENDING
            # Exactly one budget reset for a material change of sources/privacy/validation policy.
            cluster.answer_repair_attempts = 0
            cluster.ai_error_code = None
            cluster.source_retry_after = None
            cluster.version += 1
            await record_automation_decision(
                session,
                entity_type="cluster",
                entity_id=cluster.id,
                idempotency_key=f"cluster:{cluster.id}:review-policy:{REVIEW_POLICY_VERSION}",
                decision_type=Decision.ANSWER_VALIDATION_FAILED,
                decision_source=Source.RULE,
                reason="Queued once for improved source retrieval and independent answer review",
                confidence=None,
                settings=settings,
                selected_cluster_id=cluster.id,
                retrieval_scores={
                    "previous_repair_attempts": previous,
                    "review_policy_version": REVIEW_POLICY_VERSION,
                },
            )
        await session.commit()
        return len(rows)


async def _manual(
    session: AsyncSession,
    cluster: QuestionCluster,
    settings: CardAutomationSettings,
    reason: str,
) -> None:
    cluster.answer_status = Status.NEEDS_MANUAL_REVIEW
    cluster.version += 1
    await record_automation_decision(
        session,
        entity_type="cluster",
        entity_id=cluster.id,
        idempotency_key=f"cluster:{cluster.id}:review-blocked:{cluster.version}",
        decision_type=Decision.ANSWER_VALIDATION_FAILED,
        decision_source=Source.RULE,
        reason=reason,
        confidence=None,
        settings=settings,
        selected_cluster_id=cluster.id,
    )


async def review_cluster(
    ctx: dict[str, Any],
    cluster_id: UUID,
    revision: int,
    factory: async_sessionmaker[AsyncSession],
    ai: InterviewAIProvider,
) -> None:
    from app.interviews.card_automation_jobs import (
        MAX_ANSWER_REPAIRS,
        _contract_source_ids,
        _validation_sources,
    )

    # Acquire publication locks in their normal order, never while already holding a cluster lock.
    async with factory() as session:
        state = await session.get(QuestionCluster, cluster_id)
        if state is None or state.answer_status != Status.REVIEW_PENDING:
            return
        linked = await link_verified_cluster_match(session, cluster_id, revision)
        await session.commit()
        if linked is not None:
            return
    candidate = None
    next_job = None
    async with factory() as session:
        cluster = await session.get(QuestionCluster, cluster_id, with_for_update=True)
        settings = (
            await session.get(CardAutomationSettings, cluster.direction_id) if cluster else None
        )
        if (
            cluster is None
            or cluster.membership_revision != revision
            or cluster.answer_status != Status.REVIEW_PENDING
            or cluster.linked_card_id is not None
            or cluster.status != QuestionClusterStatus.NEEDS_REVIEW
        ):
            return
        if settings is None or not settings.enabled or not settings.cluster_moderation_enabled:
            return
        if settings.shadow_mode or not settings.global_auto_publish_enabled:
            await _manual(session, cluster, settings, "Automatic publication is disabled")
            await session.commit()
            return
        reason = await publication_preflight_reason(session, cluster, settings)
        if reason == DUPLICATE_REASON:
            matches = await current_cluster_matches(session, cluster, settings)
            if len(matches) <= 3:
                candidate = next((m for m in matches if m.verdict is None), None)
            if candidate is None:
                await _manual(
                    session,
                    cluster,
                    settings,
                    "Duplicate check is ambiguous or has too many candidates; review required",
                )
                await session.commit()
                return
            question = redact_untrusted_text(cluster.canonical_question)[:4_000]
            version = cluster.version
            candidate_id, fingerprint = candidate.card.id, candidate.fingerprint
            candidate_question = redact_untrusted_text(candidate.card.question_markdown)[:4_000]
            candidate_answer = redact_untrusted_text(candidate.card.answer_markdown)[:8_000]
        elif reason:
            await _manual(session, cluster, settings, reason)
        else:
            sources = await _validation_sources(session, cluster)
            if not sources:
                cluster.answer_status = Status.NEEDS_EXPERT_SOURCE
                cluster.ai_error_code = "no_trusted_sources"
                cluster.source_retry_after = datetime.now(UTC) + timedelta(hours=6)
                cluster.version += 1
            else:
                contract, validation = cluster.answer_contract, cluster.answer_validation
                references = set(_contract_source_ids(contract))
                need_generation = (
                    contract is None
                    or not references
                    or not references <= {s["source_id"] for s in sources}
                )
                modern = validation is not None and "answer_is_substantive" in validation
                quality_passes = False
                if modern and contract:
                    try:
                        quality_passes = publication_quality_passes(
                            cluster,
                            AnswerContract.model_validate(contract),
                            AnswerValidationResult.model_validate(validation),
                            {s["source_id"] for s in sources},
                        ) and _accepted(validation)
                    except ValueError:
                        pass
                if need_generation or (modern and not quality_passes):
                    if modern and (validation or {}).get("question_is_self_contained") is False:
                        await _manual(
                            session,
                            cluster,
                            settings,
                            "Question requires missing code, data or context",
                        )
                    elif cluster.answer_repair_attempts >= MAX_ANSWER_REPAIRS:
                        await _manual(
                            session,
                            cluster,
                            settings,
                            "Independent review still fails after two answer repairs",
                        )
                    else:
                        cluster.answer_status = Status.REPAIR_PENDING if contract else None
                        cluster.version += 1
                        next_job = "generate_cluster_candidate"
                elif modern and quality_passes:
                    cluster.answer_status = Status.GENERATED_FROM_SOURCES
                    cluster.version += 1
                    next_job = "validate_cluster_answer"
                else:
                    # Revalidate preserved old answers under the new completeness/warnings policy.
                    cluster.answer_validation = None
                    cluster.answer_status = None
                    cluster.version += 1
                    next_job = "validate_cluster_answer"
                cluster.ai_error_code = None
        await session.commit()
    if candidate is not None:
        result = await ai.judge_card_match(
            question=question,
            answer_scope=[],
            candidate_question=candidate_question,
            candidate_answer=candidate_answer,
        )
        async with factory() as session:
            cluster = await session.get(QuestionCluster, cluster_id, with_for_update=True)
            card = await session.get(InterviewCard, candidate_id)
            deck = await session.get(InterviewDeck, card.deck_id) if card else None
            if (
                cluster is None
                or cluster.version != version
                or cluster.membership_revision != revision
                or cluster.answer_status != Status.REVIEW_PENDING
                or card is None
                or deck is None
                or not card.is_published
                or not deck.is_published
                or deck.track_id != cluster.direction_id
                or match_fingerprint(cluster, card) != fingerprint
            ):
                return
            settings = await session.get(CardAutomationSettings, cluster.direction_id)
            if settings is None:
                return
            await record_automation_decision(
                session,
                entity_type="cluster",
                entity_id=cluster_id,
                idempotency_key=f"cluster-match:{fingerprint}:{version}",
                decision_type=Decision.SEMANTIC_CARD_MATCH,
                decision_source=Source.SEMANTIC_JUDGE,
                selected_card_id=candidate_id,
                selected_cluster_id=cluster_id,
                reason=result.output.reasoning_summary,
                confidence=result.output.confidence,
                settings=settings,
                judge_result=result.output.model_dump(mode="json"),
                input_hash=fingerprint,
                prompt_version=result.prompt_version,
                usage=result.usage,
                ai_tier="light",
            )
            await session.commit()
        # One paid comparison per pass, even on Flex. Evidence survives worker restarts.
        await defer_model_cooldown(
            ctx,
            InterviewAIError(
                CONTINUE_ERROR,
                "Continue saved cluster review",
                retryable=True,
                retry_after_seconds=1,
            ),
        )
    elif next_job:
        await enqueue_card_automation_job(next_job, str(cluster_id), revision, redis=ctx["redis"])


def _accepted(validation: dict[str, Any] | None) -> bool:
    validation = validation or {}
    return bool(
        validation.get("supported")
        and validation.get("question_is_self_contained") is True
        and validation.get("answer_is_substantive") is True
        and not any(
            validation.get(k)
            for k in (
                "unsupported_claims",
                "contradictions",
                "missing_required_points",
                "version_sensitive_claims",
                "unverified_personal_claims",
            )
        )
    )
