import httpx
from openai import RateLimitError
from openai.lib._pydantic import to_strict_json_schema

from app.interviews.intelligence_ai import (
    LIGHT_REVIEW_PROMPT,
    TECHNICAL_REVIEW_PROMPT,
    OpenAIInterviewAIProvider,
    ReviewOutput,
    transcript_chunks,
)
from app.interviews.intelligence_jobs import _retry_delay, _will_retry
from app.interviews.intelligence_models import IntelligenceQuestionKind


def _rate_limit_error(*, error_type: str, error_code: str | None) -> RateLimitError:
    response = httpx.Response(
        429,
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
        headers={"x-request-id": "req_test"},
    )
    return RateLimitError(
        "sensitive provider message",
        response=response,
        body={"error": {"type": error_type, "code": error_code}},
    )


def test_openai_quota_error_is_not_retried() -> None:
    translated = OpenAIInterviewAIProvider._translate_error(
        _rate_limit_error(error_type="insufficient_quota", error_code="insufficient_quota")
    )

    assert translated.code == "OPENAI_QUOTA_EXCEEDED"
    assert translated.retryable is False


def test_openai_transient_rate_limit_is_retried() -> None:
    translated = OpenAIInterviewAIProvider._translate_error(
        _rate_limit_error(error_type="tokens", error_code="rate_limit_exceeded")
    )

    assert translated.code == "OPENAI_RATE_LIMIT"
    assert translated.retryable is True


def test_worker_uses_exponential_backoff_and_stops_after_last_try() -> None:
    assert _retry_delay({"job_try": 1}, 60) == 60
    assert _retry_delay({"job_try": 2}, 60) == 120
    assert _retry_delay({"job_try": 3}, 60) == 240
    assert _will_retry({"job_try": 3}, True) is True
    assert _will_retry({"job_try": 4}, True) is False


def test_openai_routes_only_technical_questions_to_expensive_model() -> None:
    provider = object.__new__(OpenAIInterviewAIProvider)
    provider.analysis_model = "expensive-analysis"
    provider.light_review_model = "cheap-review"

    assert provider._review_route(IntelligenceQuestionKind.TECHNICAL) == (
        "expensive-analysis",
        TECHNICAL_REVIEW_PROMPT,
    )
    for kind in (
        IntelligenceQuestionKind.HR,
        IntelligenceQuestionKind.ORGANIZATIONAL,
        IntelligenceQuestionKind.OTHER,
    ):
        assert provider._review_route(kind) == ("cheap-review", LIGHT_REVIEW_PROMPT)


def test_review_output_uses_only_closed_json_objects() -> None:
    schema = to_strict_json_schema(ReviewOutput)

    def assert_closed(value: object) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object":
                assert value.get("additionalProperties") is False
            for nested in value.values():
                assert_closed(nested)
        elif isinstance(value, list):
            for nested in value:
                assert_closed(nested)

    assert_closed(schema)


def test_transcript_chunks_enforce_a_character_budget_and_keep_progressing() -> None:
    blocks = ["a" * 60, "b" * 60, "c" * 60]

    chunks = transcript_chunks(blocks, size=3, overlap=1, max_chars=100)

    assert chunks == ["a" * 60, "b" * 60, "c" * 60]
    assert all(len(chunk) <= 100 for chunk in chunks)
