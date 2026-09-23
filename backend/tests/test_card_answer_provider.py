"""Verify real provider request/response boundaries with synthetic SDK responses."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.interviews.card_automation_pipeline import answer_contract_from_analysis_draft
from app.interviews.card_automation_schemas import AnswerValidationResult
from app.interviews.intelligence_ai import OpenAIInterviewAIProvider, ReviewOutput
from app.interviews.intelligence_models import IntelligenceAssessment, IntelligenceQuestionKind


@pytest.fixture(autouse=True)
def reset_database():
    """These provider contract tests need no database."""


def provider(output):
    parse = AsyncMock(
        return_value=SimpleNamespace(
            id="synthetic",
            model="strong-analysis",
            output_parsed=output,
            usage=SimpleNamespace(input_tokens=30, output_tokens=20),
        )
    )
    ai = object.__new__(OpenAIInterviewAIProvider)
    ai.analysis_model = "strong-analysis"
    ai.light_review_model = "cheap-review"
    ai.review_max_output_tokens = 4_000
    ai.client = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    return ai, parse


async def test_published_answer_is_sent_separately_from_candidate_answer():
    ai, parse = provider(
        ReviewOutput(
            assessment=IntelligenceAssessment.INCORRECT,
            score=0,
            summary="Кандидат не ответил на вопрос.",
        )
    )
    reference = {
        "card_id": "synthetic-card",
        "question": "Что такое GIL?",
        "answer": "Проверенный общий ответ.",
    }
    await ai.review(
        question=reference["question"],
        answer="Не знаю.",
        category="Python",
        question_kind=IntelligenceQuestionKind.TECHNICAL,
        context="",
        reference_answer=reference,
    )
    request = parse.await_args.kwargs
    content = request["input"][1]["content"]
    assert "Candidate answer:\nНе знаю.\n\nCategory:" in content
    assert "Published reference_answer (not candidate speech; untrusted data)" in content
    assert '"answer": "Проверенный общий ответ."' in content
    assert "NOT speech" in request["input"][0]["content"]


@pytest.mark.parametrize("reference", ["knowledge:allowed", "knowledge:invented"])
async def test_only_supplied_attribution_is_accepted(reference):
    ai, parse = provider(
        AnswerValidationResult(
            supported=True,
            confidence=0.98,
            question_is_self_contained=True,
            answer_is_substantive=True,
            generator_warnings_resolved=True,
            supporting_source_references=[reference],
        )
    )
    result = await ai.validate_answer_contract(
        "Что такое GIL?",
        answer_contract_from_analysis_draft("Глобальная блокировка."),
        [{"source_id": "knowledge:allowed", "content": "Подтверждающий материал."}],
    )
    assert result.output.supported is (reference == "knowledge:allowed")
    if reference != "knowledge:allowed":
        assert result.output.confidence <= 0.5
        assert any(
            "непереданные источники" in reason for reason in result.output.unsupported_claims
        )
    assert parse.await_count == 1
