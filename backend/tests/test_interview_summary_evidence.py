import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.interviews.intelligence_ai import (
    AISummaryEvidenceResult,
    AIUsageResult,
    InterviewAIError,
    InterviewSummaryEvidence,
    OpenAIInterviewAIProvider,
    SummaryEvidenceFinding,
)
from app.interviews.intelligence_summary_evidence import summarize_review_evidence


def evidence(number: int, *, long: bool = False) -> str:
    return json.dumps(
        {
            "question_number": number,
            "question_kind": "technical",
            "topic": "Python",
            "question": "Вопрос " + ("подробный " * 250 if long else ""),
            "transcription_quality": {"answer_unreliable": number == 1},
            "preliminary_review": {
                "assessment": "unable_to_assess" if number == 1 else "correct",
                "score": None if number == 1 else 1,
                "summary": "Недостаточно данных." if number == 1 else "Ответ корректен.",
            },
        },
        ensure_ascii=False,
    )


async def compress(content: str) -> AISummaryEvidenceResult:
    rows = [json.loads(line) for line in content.splitlines() if line.strip()]
    return AISummaryEvidenceResult(
        InterviewSummaryEvidence(
            findings=[
                SummaryEvidenceFinding(
                    question_numbers=[row["question_number"]], finding="Сохранённая оценка."
                )
                for row in rows
            ]
        ),
        AIUsageResult(None, "fake", 10, 10),
    )


async def test_short_interview_needs_only_one_final_report():
    checkpoints = SimpleNamespace(summarize=AsyncMock(), summarize_evidence=AsyncMock())
    blocks = [evidence(i) for i in range(1, 31)]
    await summarize_review_evidence(checkpoints, blocks)
    checkpoints.summarize.assert_awaited_once_with("\n\n".join(blocks))
    checkpoints.summarize_evidence.assert_not_awaited()


async def test_long_interview_preserves_all_question_coverage_with_one_final_report():
    checkpoints = SimpleNamespace(
        summarize=AsyncMock(), summarize_evidence=AsyncMock(side_effect=compress)
    )
    blocks = [evidence(i, long=True) for i in range(1, 42)]
    await summarize_review_evidence(checkpoints, blocks)
    assert checkpoints.summarize_evidence.await_count > 1
    checkpoints.summarize.assert_awaited_once()
    payload = json.loads(checkpoints.summarize.await_args.args[0])
    assert {q["question_number"] for q in payload["question_coverage"]} == set(range(1, 42))
    assert {n for f in payload["findings"] for n in f["question_numbers"]} == set(range(1, 42))
    assert payload["question_coverage"][0]["assessment"] == "unable_to_assess"
    assert payload["question_coverage"][0]["score"] is None
    assert payload["question_coverage"][0]["transcription_quality"]["answer_unreliable"]
    assert payload["uncompressed_reviews"] == []
    assert len(checkpoints.summarize.await_args.args[0]) < len("\n\n".join(blocks)) / 2


async def test_missing_or_invented_compression_references_keep_original_reviews():
    bad = AISummaryEvidenceResult(
        InterviewSummaryEvidence(
            findings=[SummaryEvidenceFinding(question_numbers=[9999], finding="Чужой вопрос.")]
        ),
        AIUsageResult(None, "fake", 1, 1),
    )
    checkpoints = SimpleNamespace(
        summarize=AsyncMock(), summarize_evidence=AsyncMock(return_value=bad)
    )
    blocks = [evidence(i, long=True) for i in range(1, 22)]
    await summarize_review_evidence(checkpoints, blocks)
    payload = json.loads(checkpoints.summarize.await_args.args[0])
    assert payload["findings"] == []
    assert payload["uncompressed_reviews"] == [json.loads(b) for b in blocks]


async def test_invalid_compression_falls_back_without_generating_partial_reports():
    checkpoints = SimpleNamespace(
        summarize=AsyncMock(),
        summarize_evidence=AsyncMock(
            side_effect=InterviewAIError("OPENAI_OUTPUT_TRUNCATED", "truncated", retryable=True)
        ),
    )
    blocks = [evidence(i, long=True) for i in range(1, 22)]
    await summarize_review_evidence(checkpoints, blocks)
    checkpoints.summarize.assert_awaited_once()
    assert len(json.loads(checkpoints.summarize.await_args.args[0])["uncompressed_reviews"]) == 21


async def test_quota_failure_does_not_trigger_another_final_request():
    checkpoints = SimpleNamespace(
        summarize=AsyncMock(),
        summarize_evidence=AsyncMock(
            side_effect=InterviewAIError("OPENAI_QUOTA_EXCEEDED", "quota", retryable=False)
        ),
    )
    with pytest.raises(InterviewAIError, match="quota"):
        await summarize_review_evidence(checkpoints, [evidence(i, long=True) for i in range(21)])
    checkpoints.summarize.assert_not_awaited()


async def test_compact_evidence_uses_its_own_schema_and_budget():
    output = InterviewSummaryEvidence(
        findings=[SummaryEvidenceFinding(question_numbers=[1], finding="Ответ корректен.")]
    )
    parse = AsyncMock(
        return_value=SimpleNamespace(
            id="compact-response",
            model="cheap-review",
            output_parsed=output,
            usage=SimpleNamespace(input_tokens=100, output_tokens=80),
        )
    )
    provider = object.__new__(OpenAIInterviewAIProvider)
    provider.light_review_model = "cheap-review"
    provider.client = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    result = await provider.summarize_evidence(evidence(1))
    assert result.output is output
    assert parse.await_args.kwargs["text_format"] is InterviewSummaryEvidence
    assert parse.await_args.kwargs["max_output_tokens"] == 3_000
    assert parse.await_args.kwargs["model"] == "cheap-review"
