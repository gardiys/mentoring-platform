"""Build one final report from saved reviews and, only when needed, compact findings."""

import json
from typing import Any

from app.interviews.intelligence_ai import AISummaryResult, InterviewAIError, transcript_chunks
from app.interviews.intelligence_checkpoints import InterviewAICheckpoints

SUMMARY_INPUT_CHARS = 45_000


async def summarize_review_evidence(
    checkpoints: InterviewAICheckpoints, blocks: list[str]
) -> AISummaryResult:
    content = "\n\n".join(blocks)
    if len(content) <= SUMMARY_INPUT_CHARS:
        return await checkpoints.summarize(content)

    findings: list[dict[str, Any]] = []
    fallback_reviews: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []
    for chunk in transcript_chunks(blocks, size=20, overlap=0, max_chars=SUMMARY_INPUT_CHARS):
        rows = [json.loads(line) for line in chunk.splitlines() if line.strip()]
        requested = {row["question_number"] for row in rows}
        for row in rows:
            coverage.append(
                {
                    "question_number": row["question_number"],
                    "question_kind": row["question_kind"],
                    "topic": row["topic"],
                    "assessment": row["preliminary_review"]["assessment"],
                    "score": row["preliminary_review"]["score"],
                    "transcription_quality": row["transcription_quality"],
                }
            )
        try:
            result = await checkpoints.summarize_evidence(chunk)
        except InterviewAIError as error:
            if (
                error.code not in {"OPENAI_INVALID_RESPONSE", "OPENAI_OUTPUT_TRUNCATED"}
                or getattr(checkpoints, "service_tier", "default") == "flex"
            ):
                raise
            # A broken compression must not lose evidence or regenerate full partial reports.
            fallback_reviews.extend(rows)
            continue
        covered: set[int] = set()
        for finding in result.output.findings:
            numbers = set(finding.question_numbers)
            if not numbers.issubset(requested):
                continue
            covered.update(numbers)
            findings.append(finding.model_dump(mode="json"))
        # Preserve omitted questions verbatim as review data, not invented observations.
        fallback_reviews.extend(row for row in rows if row["question_number"] not in covered)

    return await checkpoints.summarize(
        json.dumps(
            {
                "input_kind": "reviewed_interview_evidence",
                "question_coverage": coverage,
                "findings": findings,
                "uncompressed_reviews": fallback_reviews,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
