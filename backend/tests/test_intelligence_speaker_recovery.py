from uuid import uuid4

import pytest

from app.interviews.intelligence_ai import ExtractedQuestion, ExtractedSpeechSpan
from app.interviews.intelligence_extraction_grounding import ground_question
from app.interviews.intelligence_models import IntelligenceQuestionKind, IntelligenceUtterance


def span(label: str, text: str) -> ExtractedSpeechSpan:
    return ExtractedSpeechSpan(utterance_id=label, start_text=text, end_text=text)


def question(**overrides: object) -> ExtractedQuestion:
    return ExtractedQuestion.model_validate(
        {
            "question": "Что делает verify=False?",
            "question_utterance_ids": ["U001"],
            "answer_utterance_ids": ["U002"],
            "question_kind": IntelligenceQuestionKind.TECHNICAL,
            "category": "TLS",
            "confidence": 0.95,
        }
        | overrides
    )


def source(text: str, speaker_id, sequence: int) -> IntelligenceUtterance:
    return IntelligenceUtterance(
        id=uuid4(),
        speaker_id=speaker_id,
        sequence_number=sequence,
        start_ms=sequence * 1000,
        end_ms=sequence * 1000 + 900,
        text=text,
    )


def test_globally_swapped_speakers_recover_original_candidate_answer() -> None:
    selected, actual = uuid4(), uuid4()
    answer = "Ну, трафик зашифрован, но сертификат сервера не проверяется."
    utterances = {
        "U001": source("Что делает verify=False?", selected, 1),
        "U002": source(answer, actual, 2),
    }
    result = ground_question(question(answer_spans=[span("U002", answer)]), utterances, selected)
    assert result is not None
    assert result.answer_text == answer
    assert result.speaker_conflict
    assert not result.answer_unreliable
    assert result.uncertain_ids == ["U001", "U002"]
    assert utterances["U002"].text == answer


@pytest.mark.parametrize("selected_label", [True, False])
def test_mixed_speech_excludes_question_and_interviewer_explanation(selected_label: bool) -> None:
    candidate = uuid4()
    prompt = "Что именно делает этот флаг?"
    answer = "Ну, отключает проверку SSL-сертификата."
    hint = "Уточню: сертификата удалённого сервера."
    row = source(f"{prompt} {answer} {hint}", candidate if selected_label else uuid4(), 1)
    result = ground_question(
        question(
            answer_utterance_ids=["U001"],
            question_spans=[span("U001", prompt)],
            answer_spans=[span("U001", answer)],
        ),
        {"U001": row},
        candidate,
    )
    assert result is not None
    assert result.answer_text == answer
    assert not result.answer_unreliable
    assert result.speaker_conflict
    assert result.answer_spans == [
        {
            "utterance_id": "U001",
            "start_char": len(prompt) + 1,
            "end_char": len(prompt) + 1 + len(answer),
        }
    ]


@pytest.mark.parametrize(
    "bad_span",
    [
        span("U001", "Выдуманный ответ"),
        span("U999", "Не знаю."),
        ExtractedSpeechSpan(utterance_id="U001", start_text="проверку", end_text="Ну"),
        span("U001", "Что делает флаг?"),
    ],
)
def test_invalid_or_overlapping_anchors_keep_question_without_scoring_answer(bad_span) -> None:
    candidate = uuid4()
    result = ground_question(
        question(
            answer_utterance_ids=["U001"],
            question_spans=[span("U001", "Что делает флаг?")],
            answer_spans=[bad_span],
        ),
        {"U001": source("Что делает флаг? Ну, отключает проверку.", candidate, 1)},
        candidate,
    )
    assert result is not None
    assert result.questions
    assert result.answer_unreliable
    assert result.answer_text == ""


def test_uncertain_role_is_not_treated_as_a_candidate_error() -> None:
    candidate = uuid4()
    result = ground_question(
        question(answer_attribution="uncertain"),
        {
            "U001": source("Что делает флаг?", uuid4(), 1),
            "U002": source("Отключает проверку.", candidate, 2),
        },
        candidate,
    )
    assert result is not None
    assert result.answer_text == "Отключает проверку."
    assert result.answer_unreliable


def test_resumed_answer_is_ordered_and_does_not_include_interviewer_hint() -> None:
    candidate, interviewer = uuid4(), uuid4()
    rows = {
        "U001": source("Что делает флаг?", interviewer, 1),
        "U002": source("Не отключает шифрование.", candidate, 2),
        "U003": source("А сертификат?", interviewer, 3),
        "U004": source("Не проверяет сертификат.", candidate, 4),
    }
    result = ground_question(
        question(answer_utterance_ids=["U004", "U002", "U002"]), rows, candidate
    )
    assert result is not None
    assert result.answer_text == "Не отключает шифрование.\nНе проверяет сертификат."
    assert not result.answer_unreliable


def test_missing_answer_keeps_question_but_unknown_question_source_is_rejected() -> None:
    candidate = uuid4()
    rows = {"U001": source("Что делает флаг?", candidate, 1)}
    result = ground_question(question(answer_utterance_ids=[]), rows, candidate)
    assert result is not None
    assert result.answer_unreliable
    assert result.answer_text == ""
    assert ground_question(question(question_utterance_ids=["U999"]), rows, candidate) is None


def test_ambiguous_repeated_anchor_does_not_pick_arbitrary_speech() -> None:
    candidate = uuid4()
    result = ground_question(
        question(answer_spans=[span("U002", "Да.")]),
        {
            "U001": source("Что делает флаг?", uuid4(), 1),
            "U002": source("Да. Подсказка интервьюера. Да.", candidate, 2),
        },
        candidate,
    )
    assert result is not None
    assert result.answer_unreliable
    assert not result.answer_text


def test_two_fragments_in_one_utterance_preserve_errors_and_skip_interruption() -> None:
    candidate = uuid4()
    prompt = "Что делает GIL?"
    first = "Ну, GIL не устраняет гонки."
    hint = "Интервьюер: а потоки?"
    last = "Думаю, все потоки работают параллельно."
    result = ground_question(
        question(
            answer_utterance_ids=["U001"],
            question_spans=[span("U001", prompt)],
            answer_spans=[
                span("U001", last),
                ExtractedSpeechSpan(
                    utterance_id="U001", start_text="Ну, GIL", end_text="устраняет гонки."
                ),
            ],
        ),
        {"U001": source(f"{prompt} {first} {hint} {last}", candidate, 1)},
        candidate,
    )
    assert result is not None
    assert result.answer_text == f"{first}\n{last}"
    assert not result.answer_unreliable


def test_unanchored_answer_from_another_speaker_cannot_be_credited() -> None:
    candidate = uuid4()
    result = ground_question(
        question(),
        {
            "U001": source("Что делает флаг?", candidate, 1),
            "U002": source("Объяснение интервьюера.", uuid4(), 2),
        },
        candidate,
    )
    assert result is not None
    assert result.questions
    assert result.answer_text == ""
    assert result.answer_unreliable


def test_explicit_whole_answer_survives_wrong_speaker_label_without_fragile_quotes() -> None:
    candidate = uuid4()
    answer = "А-а, моя задача была сделать общий интерфейс для LMмоделей. Я изменил API."
    result = ground_question(
        question(whole_answer_utterance_ids=["U002"]),
        {
            "U001": source("Какие были интересные задачи и фейлы?", candidate, 1),
            "U002": source(answer, uuid4(), 2),
        },
        candidate,
    )
    assert result is not None
    assert result.answer_text == answer
    assert not result.answer_unreliable
    assert result.speaker_conflict
    assert result.answer_spans == [
        {"utterance_id": "U002", "start_char": 0, "end_char": len(answer)}
    ]


def test_whole_answer_cannot_include_question_or_precede_it() -> None:
    candidate = uuid4()
    rows = {
        "U001": source("Предыдущая тема.", candidate, 1),
        "U002": source("Что делает флаг? Отключает проверку.", candidate, 2),
    }
    for answer_id in rows:
        result = ground_question(
            question(
                question_utterance_ids=["U002"],
                answer_utterance_ids=[answer_id],
                whole_answer_utterance_ids=[answer_id],
            ),
            rows,
            candidate,
        )
        assert result is not None
        assert result.answer_unreliable
        assert result.answer_text == ""
