"""Anchor semantic role recovery to source speech without rewriting the transcript."""

from dataclasses import dataclass
from uuid import UUID

from app.interviews.intelligence_ai import ExtractedQuestion, ExtractedSpeechSpan
from app.interviews.intelligence_models import IntelligenceUtterance


@dataclass
class GroundedQuestion:
    questions: list[IntelligenceUtterance]
    answers: list[IntelligenceUtterance]
    answer_text: str
    uncertain_ids: list[str]
    speaker_conflict: bool
    answer_unreliable: bool
    # Character offsets are evidence, not invented word-level timestamps.
    answer_spans: list[dict[str, str | int]]


def _span_bounds(span: ExtractedSpeechSpan, source: str) -> tuple[int, int] | None:
    if source.count(span.start_text) != 1 or source.count(span.end_text) != 1:
        return None
    start = source.index(span.start_text)
    last_start = source.index(span.end_text)
    end = last_start + len(span.end_text)
    if last_start < start or end < start + len(span.start_text):
        return None
    return start, end


def ground_question(
    item: ExtractedQuestion,
    by_label: dict[str, IntelligenceUtterance],
    candidate_speaker_id: UUID,
) -> GroundedQuestion | None:
    question_ids = set(item.question_utterance_ids)
    answer_ids = set(item.answer_utterance_ids)
    whole_answer_ids = set(item.whole_answer_utterance_ids)
    if not question_ids or not question_ids <= by_label.keys():
        return None
    questions = sorted((by_label[key] for key in question_ids), key=lambda row: row.sequence_number)
    uncertain = set(item.uncertain_utterance_ids) & (question_ids | answer_ids) & by_label.keys()
    conflicts = {
        key for key in question_ids if by_label[key].speaker_id == candidate_speaker_id
    } | {
        key
        for key in answer_ids & by_label.keys()
        if by_label[key].speaker_id != candidate_speaker_id
    }
    uncertain.update(conflicts)
    shared = question_ids & answer_ids
    uncertain.update(shared)
    question_bounds: dict[str, list[tuple[int, int]]] = {}
    answer_bounds: dict[str, list[tuple[int, int]]] = {}
    invalid_answer_ids: set[str] = set()
    unreliable = (
        item.answer_attribution == "uncertain"
        or not answer_ids <= by_label.keys()
        or not whole_answer_ids <= answer_ids
    )
    for extracted_spans, ids, bounds in (
        (item.question_spans, question_ids, question_bounds),
        (item.answer_spans, answer_ids, answer_bounds),
    ):
        for span in extracted_spans:
            row = by_label.get(span.utterance_id)
            located = _span_bounds(span, row.text) if row is not None else None
            if span.utterance_id not in ids or located is None:
                unreliable = True
                invalid_answer_ids.add(span.utterance_id)
                uncertain.add(span.utterance_id)
                continue
            bounds.setdefault(span.utterance_id, []).append(located)

    answers: list[IntelligenceUtterance] = []
    pieces: list[str] = []
    evidence: list[dict[str, str | int]] = []
    for key in sorted(answer_ids & by_label.keys(), key=lambda key: by_label[key].sequence_number):
        row = by_label[key]
        spans = sorted(set(answer_bounds.get(key, [])))
        # Pure speech can be explicitly selected by ID despite a wrong speaker
        # label. Mixed speech always needs precise, non-overlapping boundaries.
        needs_spans = key in shared or (
            row.speaker_id != candidate_speaker_id and key not in whole_answer_ids
        )
        invalid = (
            key in invalid_answer_ids
            or (needs_spans and not spans)
            or row.sequence_number < questions[0].sequence_number
            or (key in shared and key in whole_answer_ids)
        )
        if key in shared and not question_bounds.get(key):
            invalid = True
        if not spans and not invalid:
            spans = [(0, len(row.text))]
        merged_spans: list[tuple[int, int]] = []
        for start, end in spans:
            if any(
                start < question_end and question_start < end
                for question_start, question_end in question_bounds.get(key, [])
            ):
                invalid = True
            if merged_spans and start <= merged_spans[-1][1]:
                merged_spans[-1] = (merged_spans[-1][0], max(end, merged_spans[-1][1]))
            else:
                merged_spans.append((start, end))
        if invalid:
            unreliable = True
            uncertain.add(key)
            continue
        answers.append(row)
        for start, end in merged_spans:
            pieces.append(row.text[start:end])
            evidence.append({"utterance_id": key, "start_char": start, "end_char": end})
    if not pieces:
        unreliable = True
    if unreliable:
        uncertain.update(question_ids)
    return GroundedQuestion(
        questions=questions,
        answers=answers,
        answer_text="\n".join(pieces),
        uncertain_ids=sorted(uncertain & by_label.keys()),
        speaker_conflict=bool(conflicts or shared),
        answer_unreliable=unreliable,
        answer_spans=evidence,
    )
