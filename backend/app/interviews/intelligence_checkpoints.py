from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
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
    SUMMARY_PROMPT,
    SUMMARY_PROMPT_VERSION,
    TECHNICAL_REVIEW_PROMPT,
    TECHNICAL_REVIEW_PROMPT_VERSION,
    AIAnswerRecoveryResult,
    AIExtractionResult,
    AIReviewResult,
    AISummaryResult,
    AIUsageResult,
    AnswerRecoveryOutput,
    ExtractionOutput,
    InterviewAIProvider,
    InterviewSummaryOutput,
    ReviewOutput,
)
from app.interviews.intelligence_models import (
    IntelligenceAICheckpoint,
    IntelligenceAIUsage,
    IntelligenceQuestionKind,
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
    ) -> None:
        self.session_factory = session_factory
        self.interview_id = interview_id
        self.ai = ai

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
    ) -> tuple[_T, AIUsageResult]:
        key = hashlib.sha256(
            json.dumps(
                {
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
    ) -> AIReviewResult:
        technical = question_kind is IntelligenceQuestionKind.TECHNICAL
        output, usage = await self._run(
            operation="technical_evaluation" if technical else "light_evaluation",
            inputs={
                "question_id": str(question_id),
                "question": question,
                "answer": answer,
                "category": category,
                "question_kind": question_kind.value,
                "context": context,
                "direction": direction,
            },
            prompt=(TECHNICAL_REVIEW_PROMPT if technical else LIGHT_REVIEW_PROMPT)
            + transcript_context(direction),
            prompt_version=TECHNICAL_REVIEW_PROMPT_VERSION
            if technical
            else LIGHT_REVIEW_PROMPT_VERSION,
            model=getattr(
                self.ai, "analysis_model" if technical else "light_review_model", self.ai.name
            ),
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
            max_output_tokens=getattr(self.ai, "summary_max_output_tokens", 4_000),
            schema=InterviewSummaryOutput,
            call=lambda: self.ai.summarize(content),
        )
        return AISummaryResult(output, usage)
