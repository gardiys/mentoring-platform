"""A bounded second pass for missing or ungrounded answers, using source evidence only."""

import json
from collections import Counter
from uuid import UUID

from app.interviews.intelligence_ai import ExtractedQuestion
from app.interviews.intelligence_checkpoints import InterviewAICheckpoints
from app.interviews.intelligence_extraction_grounding import ground_question
from app.interviews.intelligence_models import IntelligenceUtterance


async def recover_missing_answers(
    checkpoints: InterviewAICheckpoints,
    questions: list[ExtractedQuestion],
    utterances: list[IntelligenceUtterance],
    blocks: list[str],
    candidate_speaker_id: UUID,
    *,
    direction: str | None,
) -> list[ExtractedQuestion]:
    by_label = {f"U{row.sequence_number:03d}": row for row in utterances}
    positions = {label: index for index, label in enumerate(by_label)}
    targets: dict[str, tuple[int, dict[str, IntelligenceUtterance]]] = {}
    batches: list[list[dict[str, object]]] = []
    batch: list[dict[str, object]] = []
    batch_chars = 0
    for index, question in enumerate(questions):
        grounded = ground_question(question, by_label, candidate_speaker_id)
        if grounded is None or not grounded.answer_unreliable:
            continue
        question_positions = [positions[label] for label in question.question_utterance_ids]
        # Keep neighbouring speech, including the immediate reply across an
        # extraction chunk boundary, without trusting the selected speaker.
        selected = set(
            range(
                max(0, min(question_positions) - 3),
                min(len(utterances), max(question_positions) + 13),
            )
        )
        selected.update(
            positions[label] for label in question.answer_utterance_ids if label in positions
        )
        key = f"Q{index + 1:03d}"
        scope = {f"U{utterances[i].sequence_number:03d}": utterances[i] for i in sorted(selected)}
        payload: dict[str, object] = {
            "question_key": key,
            "question": question.question,
            "question_utterance_ids": question.question_utterance_ids,
            "transcript": "\n\n".join(blocks[i] for i in sorted(selected)),
        }
        size = len(json.dumps(payload, ensure_ascii=False))
        if batch and (len(batch) >= 6 or batch_chars + size > 35_000):
            batches.append(batch)
            batch, batch_chars = [], 0
        # A long source utterance is sent intact, never silently clipped.
        batch.append(payload)
        batch_chars += size
        targets[key] = index, scope
    if batch:
        batches.append(batch)

    repaired = list(questions)
    for batch in batches:
        result = await checkpoints.recover_answers(
            json.dumps({"questions": batch}, ensure_ascii=False), direction=direction
        )
        requested = {row["question_key"] for row in batch}
        counts = Counter(answer.question_key for answer in result.output.answers)
        for answer in result.output.answers:
            if answer.question_key not in requested or counts[answer.question_key] != 1:
                continue
            index, scope = targets[answer.question_key]
            original = questions[index]
            candidate = original.model_copy(
                update={
                    "answer_utterance_ids": answer.answer_utterance_ids,
                    "whole_answer_utterance_ids": answer.whole_answer_utterance_ids,
                    "answer_spans": answer.answer_spans,
                    "question_spans": answer.question_spans or original.question_spans,
                    "answer_attribution": answer.answer_attribution,
                    "confidence": min(original.confidence, answer.confidence),
                }
            )
            grounded = ground_question(candidate, scope, candidate_speaker_id)
            if grounded is not None and grounded.answer_text and not grounded.answer_unreliable:
                repaired[index] = candidate
    return repaired
