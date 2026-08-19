from uuid import UUID

import pytest

from app.interviews.question_matching import (
    QuestionCandidate,
    QuestionVariant,
    rank_question_candidates,
)


def candidate(
    suffix: int,
    text: str,
    *,
    asked_count: int = 0,
    embedding: tuple[float, ...] | None = None,
    source: str = "card",
    aliases: tuple[QuestionVariant, ...] = (),
) -> QuestionCandidate:
    return QuestionCandidate(
        card_id=UUID(f"00000000-0000-4000-8000-{suffix:012d}"),
        asked_count=asked_count,
        variants=(QuestionVariant(text=text, embedding=embedding, source=source), *aliases),
    )


def test_exact_match_ignores_heading_case_and_trailing_punctuation() -> None:
    card = candidate(1, "## Что такое GIL в Python?")

    result = rank_question_candidates("что такое gil в python!", None, [card])

    assert len(result) == 1
    assert result[0].card_id == card.card_id
    assert result[0].similarity == 1.0
    assert result[0].match_type == "exact"
    assert result[0].matched_source == "card"


def test_russian_colloquial_kafka_rabbitmq_comparison_is_similar() -> None:
    card = candidate(
        1,
        "Чем ты пользовался: Kafka или RabbitMQ? Знаешь, в чём разница?",
    )

    result = rank_question_candidates(
        "Расскажи, в чем отличия кафки и кролика",
        None,
        [card],
    )

    assert len(result) == 1
    assert result[0].card_id == card.card_id
    assert result[0].similarity >= 0.90
    assert result[0].match_type == "similar"


def test_one_shared_technology_does_not_make_unrelated_question_a_candidate() -> None:
    card = candidate(1, "Как Kafka гарантирует доставку сообщений?")

    result = rank_question_candidates(
        "Расскажи, в чем отличия кафки и кролика",
        None,
        [card],
    )

    assert result == []


def test_short_index_question_retrieves_detailed_canonical_card() -> None:
    card = candidate(
        1,
        (
            "Расскажите, зачем нужны индексы в базах данных, какие виды индексов "
            "существуют и когда их следует использовать."
        ),
    )

    result = rank_question_candidates(
        "Расскажи про то, какие ты индексы знаешь?",
        None,
        [card],
    )

    assert len(result) == 1
    assert result[0].card_id == card.card_id
    assert 0.35 <= result[0].similarity < 0.90
    assert result[0].match_type == "similar"


def test_matching_uses_confirmed_alias_variant_and_reports_its_source() -> None:
    alias = QuestionVariant(
        text="Kafka vs RabbitMQ: в чем разница?",
        embedding=None,
        source="approved_alias",
    )
    card = candidate(1, "Как выбрать брокер сообщений?", aliases=(alias,))

    result = rank_question_candidates(
        "Расскажи про разницу между кафкой и кроликом",
        None,
        [card],
    )

    assert len(result) == 1
    assert result[0].card_id == card.card_id
    assert result[0].matched_source == "approved_alias"


def test_cosine_similarity_is_used_only_for_same_non_empty_dimensions() -> None:
    vector_match = candidate(1, "Несвязанная формулировка", embedding=(1.0, 0.0))
    wrong_dimensions = candidate(2, "Другая тема", embedding=(1.0, 0.0, 0.0))
    empty_vector = candidate(3, "Еще одна тема", embedding=())

    result = rank_question_candidates(
        "Как работает цикл событий?",
        (0.9, 0.1),
        [wrong_dimensions, empty_vector, vector_match],
    )

    assert [item.card_id for item in result] == [vector_match.card_id]
    assert result[0].similarity == pytest.approx(0.9938837347)
    assert result[0].match_type == "similar"


def test_ranking_prefers_similarity_then_asked_count_and_honours_limit() -> None:
    less_frequent = candidate(1, "Что такое Redis?", asked_count=2)
    more_frequent = candidate(2, "Что такое Redis?", asked_count=10)
    lower_similarity = candidate(3, "Как Redis хранит данные?", asked_count=100)

    result = rank_question_candidates(
        "Что такое Redis?",
        None,
        [less_frequent, lower_similarity, more_frequent],
        limit=2,
    )

    assert [item.card_id for item in result] == [more_frequent.card_id, less_frequent.card_id]


def test_non_positive_limit_returns_no_candidates() -> None:
    assert rank_question_candidates("Что такое Python?", None, [], limit=0) == []
