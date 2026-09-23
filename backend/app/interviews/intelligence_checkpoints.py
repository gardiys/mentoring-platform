from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping
from typing import Protocol, TypeVar
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.interviews.intelligence_ai import (
    ANSWER_RECOVERY_PROMPT,
    ANSWER_RECOVERY_PROMPT_VERSION,
    EXTRACTION_PROMPT,
    EXTRACTION_PROMPT_VERSION,
    LIGHT_REVIEW_PROMPT,
    LIGHT_REVIEW_PROMPT_VERSION,
    SUMMARY_EVIDENCE_MAX_OUTPUT_TOKENS,
    SUMMARY_EVIDENCE_PROMPT,
    SUMMARY_EVIDENCE_PROMPT_VERSION,
    SUMMARY_MIN_OUTPUT_TOKENS,
    SUMMARY_PROMPT,
    SUMMARY_PROMPT_VERSION,
    TECHNICAL_REVIEW_PROMPT,
    TECHNICAL_REVIEW_PROMPT_VERSION,
    AIAnswerRecoveryResult,
    AIExtractionResult,
    AIReviewResult,
    AISummaryEvidenceResult,
    AISummaryResult,
    AIUsageResult,
    AnswerRecoveryOutput,
    ExtractionOutput,
    InterviewAIError,
    InterviewAIProvider,
    InterviewSummaryEvidence,
    InterviewSummaryOutput,
    ReviewOutput,
)
from app.interviews.intelligence_models import (
    IntelligenceAICheckpoint,
    IntelligenceAIUsage,
    IntelligenceQuestionKind,
)
from app.interviews.intelligence_request_policy import (
    INTERVIEW_STAGE_CONTINUE,
    ServiceTier,
    interview_request_scope,
    review_request_policy,
)
from app.interviews.intelligence_transcript_context import transcript_context

_T = TypeVar("_T", bound=BaseModel)
_T_co = TypeVar("_T_co", bound=BaseModel, covariant=True)


class _Result(Protocol[_T_co]):
    @property
    def output(self) -> _T_co: ...

    @property
    def usage(self) -> AIUsageResult: ...


class InterviewAICheckpoints:
    """Save each paid result independently of the interview's final transaction.

    The caller must lock the existing interview FOR NO KEY UPDATE, not FOR UPDATE:
    checkpoint/usage inserts need a compatible FK key-share lock on that parent.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        interview_id: UUID,
        ai: InterviewAIProvider,
        *,
        service_tier: ServiceTier = "default",
    ) -> None:
        self.session_factory = session_factory
        self.interview_id = interview_id
        self.ai = ai
        self.service_tier = service_tier
        self.paid_operations = 0

    async def _run(
        self,
        *,
        operation: str,
        inputs: dict[str, object],
        prompt: str,
        prompt_version: str,
        model: str,
        max_output_tokens: int,
        schema: type[_T],
        call: Callable[[], Awaitable[_Result[_T]]],
        question_id: UUID | None = None,
        reasoning_effort: str | None = None,
    ) -> tuple[_T, AIUsageResult]:
        key = hashlib.sha256(
            json.dumps(
                {
                    # Preserve existing default-reasoning checkpoints.
                    **({"reasoning_effort": reasoning_effort} if reasoning_effort else {}),
                    "inputs": inputs,
                    "prompt": prompt,
                    "prompt_version": prompt_version,
                    "model": model,
                    "max_output_tokens": max_output_tokens,
                    "provider": f"{type(self.ai).__module__}.{type(self.ai).__qualname__}",
                    "schema": schema.model_json_schema(),
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode()
        ).hexdigest()
        async with self.session_factory() as session:
            cached = await session.scalar(
                select(IntelligenceAICheckpoint).where(
                    IntelligenceAICheckpoint.interview_id == self.interview_id,
                    IntelligenceAICheckpoint.operation == operation,
                    IntelligenceAICheckpoint.input_hash == key,
                )
            )
            if cached is not None:
                return schema.model_validate(cached.output), AIUsageResult(None, cached.model, 0, 0)
        # A logical operation may make two provider calls (structured-output recovery).
        # One new operation per Flex pass keeps the job inside its 2 * timeout budget.
        if self.service_tier == "flex" and self.paid_operations:
            raise InterviewAIError(
                INTERVIEW_STAGE_CONTINUE,
                "Continue saved interview analysis in the next job",
                retryable=True,
                retry_after_seconds=1,
            )
        self.paid_operations += 1
        with interview_request_scope(self.service_tier):
            result = await call()
        async with self.session_factory() as session:
            await session.execute(
                insert(IntelligenceAICheckpoint)
                .values(
                    interview_id=self.interview_id,
                    operation=operation,
                    input_hash=key,
                    output=result.output.model_dump(mode="json"),
                    model=result.usage.model,
                )
                .on_conflict_do_nothing(constraint="uq_ai_checkpoint_input")
            )
            session.add(
                IntelligenceAIUsage(
                    interview_id=self.interview_id,
                    question_id=question_id,
                    provider=self.ai.name,
                    model=result.usage.model,
                    operation=operation,
                    input_tokens=result.usage.input_tokens,
                    output_tokens=result.usage.output_tokens,
                    provider_request_id=result.usage.provider_request_id,
                )
            )
            await session.commit()
        return result.output, result.usage

    async def extract(self, transcript: str, *, direction: str | None) -> AIExtractionResult:
        output, usage = await self._run(
            operation="extraction",
            inputs={"transcript": transcript, "direction": direction},
            prompt=EXTRACTION_PROMPT + transcript_context(direction),
            prompt_version=EXTRACTION_PROMPT_VERSION,
            model=getattr(self.ai, "extraction_model", self.ai.name),
            max_output_tokens=getattr(self.ai, "extraction_max_output_tokens", 8_000),
            schema=ExtractionOutput,
            call=lambda: self.ai.extract(transcript, direction=direction),
        )
        return AIExtractionResult(output, usage)

    async def recover_answers(
        self, content: str, *, direction: str | None
    ) -> AIAnswerRecoveryResult:
        output, usage = await self._run(
            operation="answer_recovery",
            inputs={"content": content, "direction": direction},
            prompt=ANSWER_RECOVERY_PROMPT + transcript_context(direction),
            prompt_version=ANSWER_RECOVERY_PROMPT_VERSION,
            model=getattr(self.ai, "extraction_model", self.ai.name),
            max_output_tokens=getattr(self.ai, "extraction_max_output_tokens", 8_000),
            schema=AnswerRecoveryOutput,
            call=lambda: self.ai.recover_answers(content, direction=direction),
        )
        return AIAnswerRecoveryResult(output, usage)

    async def review(
        self,
        *,
        question_id: UUID,
        question: str,
        answer: str,
        category: str,
        question_kind: IntelligenceQuestionKind,
        context: str,
        direction: str | None,
        reference_answer: Mapping[str, str] | None = None,
    ) -> AIReviewResult:
        technical = question_kind is IntelligenceQuestionKind.TECHNICAL
        policy = review_request_policy(self.ai, question_kind, question, answer, context)
        # Question UUIDs change on re-extraction. Cache the actual review input within
        # this interview; keep the UUID only as financial attribution for a new call.
        output, usage = await self._run(
            operation="technical_evaluation" if technical else "light_evaluation",
            inputs={
                "question": question,
                "answer": answer,
                "category": category,
                "question_kind": question_kind.value,
                "context": context,
                "direction": direction,
                **({"reference_answer": dict(reference_answer)} if reference_answer else {}),
            },
            prompt=(TECHNICAL_REVIEW_PROMPT if technical else LIGHT_REVIEW_PROMPT)
            + transcript_context(direction),
            prompt_version=TECHNICAL_REVIEW_PROMPT_VERSION
            if technical
            else LIGHT_REVIEW_PROMPT_VERSION,
            model=policy.model,
            reasoning_effort=policy.reasoning_effort,
            max_output_tokens=getattr(self.ai, "review_max_output_tokens", 4_000),
            schema=ReviewOutput,
            question_id=question_id,
            call=lambda: self.ai.review(
                question=question,
                answer=answer,
                category=category,
                question_kind=question_kind,
                context=context,
                direction=direction,
                **({"reference_answer": reference_answer} if reference_answer else {}),
            ),
        )
        return AIReviewResult(output, usage)

    async def summarize(self, content: str) -> AISummaryResult:
        output, usage = await self._run(
            operation="summary",
            inputs={"content": content},
            prompt=SUMMARY_PROMPT,
            prompt_version=SUMMARY_PROMPT_VERSION,
            model=getattr(self.ai, "light_review_model", self.ai.name),
            max_output_tokens=max(
                getattr(self.ai, "summary_max_output_tokens", 4_000), SUMMARY_MIN_OUTPUT_TOKENS
            ),
            schema=InterviewSummaryOutput,
            call=lambda: self.ai.summarize(content),
        )
        return AISummaryResult(output, usage)

    async def summarize_evidence(self, content: str) -> AISummaryEvidenceResult:
        output, usage = await self._run(
            operation="summary_evidence",
            inputs={"content": content},
            prompt=SUMMARY_EVIDENCE_PROMPT,
            prompt_version=SUMMARY_EVIDENCE_PROMPT_VERSION,
            model=getattr(self.ai, "light_review_model", self.ai.name),
            max_output_tokens=SUMMARY_EVIDENCE_MAX_OUTPUT_TOKENS,
            schema=InterviewSummaryEvidence,
            call=lambda: self.ai.summarize_evidence(content),
        )
        return AISummaryEvidenceResult(output, usage)
