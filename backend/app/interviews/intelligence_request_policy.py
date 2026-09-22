"""Request-scoped pricing and conservative, opt-in review experiments."""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Literal

from app.interviews.intelligence_models import IntelligenceQuestionKind

ServiceTier = Literal["default", "flex"]
INTERVIEW_STAGE_CONTINUE = "OPENAI_INTERVIEW_STAGE_CONTINUE"
interview_service_tier: ContextVar[ServiceTier] = ContextVar(
    "interview_service_tier", default="default"
)


@contextmanager
def interview_request_scope(tier: ServiceTier) -> Iterator[None]:
    token = interview_service_tier.set(tier)
    try:
        yield
    finally:
        interview_service_tier.reset(token)


# Deliberately narrow: novel wording and multi-part questions stay on the main model.
SIMPLE_REVIEW_QUESTIONS = frozenset(
    {
        "чем отличается list от tuple в python",
        "чем отличается список от кортежа в python",
        "чем отличается == от is в python",
        "что такое nil в go",
        "чем отличается массив от слайса в go",
    }
)


def simple_review_eligible(question: str, answer: str, context: str) -> bool:
    normalized = re.sub(r"\s+", " ", question.casefold()).strip(" ?.!\n")
    return (
        normalized in SIMPLE_REVIEW_QUESTIONS
        and 10 <= len(answer.strip()) <= 800
        and not any(marker in answer for marker in ("```", "\ndef ", "\nfunc "))
        and not any(
            marker in context.casefold()
            for marker in (
                "transcription interpretation hints",
                "mixed source",
                "uncertain",
                "unreliable",
                "speaker_attribution_conflict",
            )
        )
    )


@dataclass(frozen=True)
class ReviewRequestPolicy:
    model: str
    reasoning_effort: str | None


def review_request_policy(
    provider: object,
    kind: IntelligenceQuestionKind,
    question: str,
    answer: str,
    context: str,
) -> ReviewRequestPolicy:
    technical = kind is IntelligenceQuestionKind.TECHNICAL
    model = getattr(
        provider,
        "analysis_model" if technical else "light_review_model",
        getattr(provider, "name", "unknown"),
    )
    reasoning = getattr(provider, "review_reasoning_effort", None) if technical else None
    simple_model = getattr(provider, "simple_review_model", None)
    if (
        technical
        and getattr(provider, "simple_review_enabled", False)
        and simple_model
        and simple_review_eligible(question, answer, context)
    ):
        model = simple_model
        reasoning = getattr(provider, "simple_review_reasoning_effort", "low")
    return ReviewRequestPolicy(model, reasoning)
