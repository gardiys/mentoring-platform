"""Bounded review-quality experiment on synthetic evidence; no application DB writes.

Dry-run by default. --live sends up to 48 provider requests, including recovery.
The JSON report contains every paid attempt and outputs for a mentor to compare.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from app.core.config import Settings
from app.interviews.ai_accounting import AIRequestRecorder, estimated_cost
from app.interviews.intelligence_ai import (
    TECHNICAL_REVIEW_PROMPT_VERSION,
    InterviewAIError,
    OpenAIInterviewAIProvider,
    ReviewOutput,
)
from app.interviews.intelligence_models import IntelligenceAssessment, IntelligenceQuestionKind
from app.interviews.intelligence_request_policy import review_request_policy


@dataclass(frozen=True)
class ReviewCase:
    name: str
    question: str
    answer: str
    assessments: tuple[str, ...]
    context: str = ""
    direction: str = "python"
    finding_required: bool = False

    def __post_init__(self) -> None:
        for assessment in self.assessments:
            IntelligenceAssessment(assessment)


CASES = (
    ReviewCase(
        "correct_list",
        "Чем отличается list от tuple в Python?",
        "Оба хранят упорядоченную последовательность. Список изменяемый, "
        "кортеж неизменяемый. При этом объект внутри кортежа может быть изменяемым.",
        ("correct",),
    ),
    ReviewCase(
        "reversed_list",
        "Чем отличается list от tuple в Python?",
        "Кортеж изменяемый, а список нельзя менять после создания.",
        ("incorrect",),
        finding_required=True,
    ),
    ReviewCase(
        "negated_identity",
        "Чем отличается == от is в Python?",
        "is не сравнивает значения: он проверяет идентичность объектов. "
        "А == сравнивает значения через методы сравнения.",
        ("correct",),
    ),
    ReviewCase(
        "incomplete_list",
        "Чем отличается list от tuple в Python?",
        "В списке квадратные скобки, а в кортеже круглые. Больше не знаю.",
        ("partial", "mostly_incorrect", "incorrect"),
        finding_required=True,
    ),
    ReviewCase(
        "damaged_answer",
        "Чем отличается list от tuple в Python?",
        "[Неразборчиво, основная часть ответа отсутствует]",
        ("unable_to_assess",),
        "Transcription interpretation hints: answer_unreliable; lost audio.",
    ),
    ReviewCase(
        "interviewer_hint",
        "Чем отличается == от is в Python?",
        "Не знаю, не могу объяснить.",
        ("incorrect", "unable_to_assess"),
        "Interviewer: is проверяет идентичность объектов, == сравнивает значения. "
        "This is an interviewer hint, not candidate knowledge.",
    ),
    ReviewCase(
        "wrong_speaker_label",
        "Чем отличается list от tuple в Python?",
        "Список можно менять, а кортеж после создания нельзя. "
        "Изменяемые объекты внутри кортежа при этом менять можно.",
        ("correct",),
        "Transcription interpretation hints: speaker_attribution_conflict. "
        "The supplied candidate answer is grounded and confidently attributed. "
        "Candidate-labelled utterance: А список можно менять?",
    ),
    ReviewCase(
        "nil_interface",
        "Почему интерфейс с nil-указателем не равен nil в Go?",
        "Он тоже всегда равен nil, ведь значение указателя nil.",
        ("incorrect",),
        direction="go",
        finding_required=True,
    ),
)


def quality_failures(case: ReviewCase, output: ReviewOutput) -> list[str]:
    failures = []
    try:
        output.validate_review()
    except ValueError:
        failures.append("invalid_review")
    if output.assessment.value not in case.assessments:
        failures.append("unexpected_assessment")
    if output.assessment.value == "unable_to_assess" and output.score is not None:
        failures.append("uncertain_answer_has_score")
    if case.finding_required and not (
        output.incorrect_statements or output.missing_points or output.problems
    ):
        failures.append("missing_substantive_finding")
    if output.assessment.value == "correct" and output.suggested_better_answer:
        failures.append("unnecessary_ideal_answer")
    return failures


class EvaluationRecorder(AIRequestRecorder):
    """Reuse production token accounting, persisting only to the local report."""

    def __init__(self, max_requests: int) -> None:
        self.max_requests = max_requests
        self.rows: dict[UUID, dict[str, Any]] = {}
        self.label: dict[str, str] = {}

    async def start(self, operation: str, model: str, tier: str, recovery: bool) -> UUID:
        if len(self.rows) >= self.max_requests:
            raise InterviewAIError(
                "EVALUATION_CALL_LIMIT", "Evaluation limit reached", retryable=False
            )
        call_id = uuid4()
        self.rows[call_id] = dict(
            self.label,
            operation=operation,
            model=model,
            service_tier=tier,
            recovery=recovery,
            status="started",
        )
        return call_id

    async def _update(self, call_id: UUID, values: dict[str, Any]) -> None:
        self.rows[call_id].update(values)

    def report(self) -> list[dict[str, Any]]:
        rows = []
        for row in self.rows.values():
            result = dict(row)
            if row.get("input_tokens") is not None and row.get("output_tokens") is not None:
                writes = row.get("cache_write_tokens")
                # Unknown write tokens produce a range, never a fictitious exact charge.
                for field, count in (
                    ("estimated_cost_lower_usd", writes or 0),
                    (
                        "estimated_cost_upper_usd",
                        writes
                        if writes is not None
                        else row["input_tokens"] - row["cached_input_tokens"],
                    ),
                ):
                    result[field] = estimated_cost(
                        row["model"],
                        row["service_tier"],
                        row["input_tokens"],
                        row["cached_input_tokens"],
                        row["output_tokens"],
                        cache_write_tokens=count,
                    )
            rows.append(result)
        return rows


async def evaluate(args: argparse.Namespace) -> int:
    cases = CASES[: args.limit]
    report: dict[str, Any] = {
        "prompt_version": TECHNICAL_REVIEW_PROMPT_VERSION,
        "baseline_model": args.baseline_model,
        "candidate_model": args.candidate_model,
        "cases": [asdict(case) for case in cases],
        "results": [],
        "note": (
            "Synthetic smoke evaluation only; human review is required before enabling routing."
        ),
    }
    if not args.live:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    settings = Settings().model_copy(
        update={
            "openai_analysis_model": args.baseline_model,
            "openai_extraction_model": args.baseline_model,
            "openai_simple_review_model": args.candidate_model,
            "openai_simple_review_enabled": False,
            "openai_review_reasoning_effort": None,
            "openai_simple_review_reasoning_effort": "low",
            "openai_background_service_tier": "default",
            "openai_max_retries": 0,
            "openai_review_max_output_tokens": 4_000,
        }
    )
    provider = OpenAIInterviewAIProvider(settings)
    if provider.model_cooldown is not None:
        await provider.model_cooldown.close()
    provider.model_cooldown = None
    recorder = EvaluationRecorder(max_requests=2 * 3 * len(cases))
    provider.request_recorder = recorder

    def save() -> None:
        report["requests"] = recorder.report()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n")

    try:
        for case in cases:
            for variant in ("baseline", "main_low", "simple_model_low"):
                provider.review_reasoning_effort = "low" if variant == "main_low" else None
                provider.simple_review_enabled = variant == "simple_model_low"
                policy = review_request_policy(
                    provider,
                    IntelligenceQuestionKind.TECHNICAL,
                    case.question,
                    case.answer,
                    case.context,
                )
                recorder.label = {"case": case.name, "variant": variant}
                result = await provider.review(
                    question=case.question,
                    answer=case.answer,
                    category=case.direction,
                    question_kind=IntelligenceQuestionKind.TECHNICAL,
                    context=case.context,
                    direction=case.direction,
                )
                report["results"].append(
                    {
                        **recorder.label,
                        "policy": asdict(policy),
                        "output": result.output.model_dump(mode="json"),
                        "quality_failures": quality_failures(case, result.output),
                    }
                )
                save()
                print(f"{case.name}: {variant} finished", flush=True)
    except InterviewAIError as error:
        report["stopped_error_code"] = error.code
        # Stop immediately on quota/rate/auth errors, do not loop through remaining cases.
        print(f"Evaluation stopped: {error.code}", flush=True)
        return 2
    finally:
        save()
        await provider.close()
    return int(any(row["quality_failures"] for row in report["results"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Send paid API requests")
    parser.add_argument("--baseline-model", default="gpt-5.6-terra")
    parser.add_argument("--candidate-model", default="gpt-5.6-luna")
    parser.add_argument("--limit", type=int, choices=range(1, len(CASES) + 1), default=len(CASES))
    parser.add_argument("--output", type=Path, default=Path("interview-review-evaluation.json"))
    raise SystemExit(asyncio.run(evaluate(parser.parse_args())))


if __name__ == "__main__":
    main()
