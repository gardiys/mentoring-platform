"""Offline comparison of exported transcripts against a human reference. No API calls."""

from __future__ import annotations

import argparse
import itertools
import json
import re
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


class Segment(BaseModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    speaker: str | None
    text: str

    @model_validator(mode="after")
    def check_range(self) -> Segment:
        if self.end_ms <= self.start_ms:
            raise ValueError("Segments must have positive duration")
        return self


class Sample(BaseModel):
    reference: list[Segment] = Field(min_length=1)
    hypotheses: dict[str, list[Segment]]


def _words(rows: list[Segment]) -> list[str]:
    return re.findall(
        r"\w+", " ".join(row.text for row in sorted(rows, key=lambda r: r.start_ms)).casefold()
    )


def word_error_rate(reference: list[Segment], hypothesis: list[Segment]) -> float:
    ref, hyp = _words(reference), _words(hypothesis)
    if not ref:
        raise ValueError("Reference must contain words")
    previous = list(range(len(hyp) + 1))
    for i, word in enumerate(ref, 1):
        current = [i]
        for j, candidate in enumerate(hyp, 1):
            current.append(
                min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (word != candidate))
            )
        previous = current
    return previous[-1] / len(ref)


def diarization_error_rate(reference: list[Segment], hypothesis: list[Segment]) -> float:
    """Optimal label mapping, no collar, overlap included, unknown = unmatched speech.

    Intended for small interview fixtures (at most six distinct speakers).
    Compare providers with identical segmentation conventions and audio crop.
    """
    ref_labels = sorted({row.speaker for row in reference if row.speaker is not None})
    hyp_labels = sorted({row.speaker for row in hypothesis if row.speaker is not None})
    if not ref_labels or any(row.speaker is None for row in reference):
        raise ValueError("Reference speakers must be fully annotated")
    size = max(len(ref_labels), len(hyp_labels))
    if size > 6:
        raise ValueError("Offline DER supports up to six speakers")
    boundaries = sorted({v for row in reference + hypothesis for v in (row.start_ms, row.end_ms)})
    spans = []
    total = 0
    for start, end in zip(boundaries, boundaries[1:], strict=False):
        ref = {row.speaker for row in reference if row.start_ms < end and row.end_ms > start}
        hyp = {row.speaker for row in hypothesis if row.start_ms < end and row.end_ms > start}
        spans.append((end - start, ref, hyp))
        total += (end - start) * len(ref)
    best = float("inf")
    for permutation in itertools.permutations([*ref_labels, *[None] * (size - len(ref_labels))]):
        mapping = dict(zip(hyp_labels, permutation, strict=False))
        error = 0
        for duration, ref, hyp in spans:
            correct = len(ref & {mapping.get(speaker) for speaker in hyp if speaker is not None})
            error += duration * (max(len(ref), len(hyp)) - correct)
        best = min(best, error)
    return best / total


def metrics(reference: list[Segment], hypothesis: list[Segment]) -> dict[str, float | int]:
    turns = sorted(hypothesis, key=lambda row: row.start_ms)
    flips = sum(a.speaker != b.speaker for a, b in zip(turns, turns[1:], strict=False))
    minutes = max(row.end_ms for row in reference) / 60_000
    return {
        "wer": word_error_rate(reference, hypothesis),
        "der_no_collar": diarization_error_rate(reference, hypothesis),
        "speaker_changes_per_minute": flips / minutes,
        "utterances": len(hypothesis),
        "reference_words": len(_words(reference)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample", type=Path, help="JSON reference and provider hypotheses")
    args = parser.parse_args()
    sample = Sample.model_validate_json(args.sample.read_text())
    print(
        json.dumps(
            {name: metrics(sample.reference, rows) for name, rows in sample.hypotheses.items()},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
