from types import SimpleNamespace as NS
from uuid import uuid4

import pytest

from app.interviews.feedback_grounding import ground_communication, ground_delivery, weighted_score
from app.interviews.intelligence_ai import InterviewSummaryOutput, TechnicalTopicAssessment
from app.interviews.intelligence_jobs import _ground_technical_assessment, _summary_evidence_blocks
from app.interviews.intelligence_models import IntelligenceAssessment as A
from app.interviews.intelligence_models import IntelligenceDifficulty as D
from app.interviews.intelligence_models import IntelligenceQuestionKind as K
from app.interviews.intelligence_models import IntelligenceReviewSource as S


@pytest.fixture(autouse=True)
def reset_database():
    """These source checks need no database."""
    yield


def evidence(kind=K.HR, unreliable=False):
    id_ = uuid4()
    text = "Мы исправили ошибку. Я проверил логи и нашёл причину."
    question = NS(
        id=uuid4(),
        sequence_number=1,
        question_kind=kind,
        category="Опыт",
        subcategory=None,
        question_text="Расскажи про сложную задачу",
        confidence=0.9,
        transcription_annotations={"answer_unreliable": unreliable},
        answer_utterance_ids=[id_],
        difficulty=D.JUNIOR,
        question_start_ms=0,
    )
    answer = NS(answer_text=text, start_ms=1000, end_ms=8000)
    dimension = dict(
        skill="structure",
        score=0.4,
        summary="Действия названы, результат не уточнён.",
        evidence_quote=text,
        evidence_utterance_ids=[str(id_)],
        confidence=0.95,
        exercise={
            "task": "Перескажи этот случай по схеме ситуация, действие, результат.",
            "success_criterion": "Названы три части без добавления выдуманных фактов.",
        },
    )
    review = NS(
        assessment=A.UNABLE_TO_ASSESS,
        score=None,
        summary="Ответ о личном опыте.",
        source=S.AI,
        strengths=[],
        problems=[],
        missing_points=[],
        incorrect_statements=[],
        suggested_better_answer=None,
        delivery_assessment=[dimension],
    )
    return question, answer, review, [NS(id=id_, text=text)]


def test_hr_correctness_unassessable_does_not_remove_grounded_delivery():
    q, a, r, u = evidence()
    output = ground_communication({}, [(q, a, r)], u)
    assert output["communication_score"] is None
    assert output["communication_grounded"]
    assert output["communication_dimensions"][0]["confidence"] == 0.9
    assert output["priority_actions"][0]["communication_skill"] == "structure"
    summary = _ground_technical_assessment(
        InterviewSummaryOutput(
            overall_summary="Итог",
            technical_summary="Технических вопросов нет",
            communication_summary="Подача",
        ),
        [(q, a, r)],
    )
    assert summary.technical_score is None


@pytest.mark.parametrize(
    "failure", ["foreign_id", "interviewer_quote", "empty_answer", "unreliable", "legacy"]
)
def test_invalid_sources_cannot_produce_communication_score(failure):
    q, a, r, u = evidence()
    if failure == "foreign_id":
        r.delivery_assessment[0]["evidence_utterance_ids"] = [str(uuid4())]
    if failure == "interviewer_quote":
        r.delivery_assessment[0]["evidence_quote"] = "Подскажу тебе правильный ответ"
    if failure == "empty_answer":
        a.answer_text = ""
    if failure == "unreliable":
        q.transcription_annotations["answer_unreliable"] = True
    if failure == "legacy":
        r.delivery_assessment = []
    result = ground_communication(
        {
            "communication_score": 0.9,
            "communication_dimensions": [{"name": "clarity"}],
            "communication_strengths": ["Выдумка"],
        },
        [(q, a, r)],
        u,
    )
    assert result["communication_score"] is None
    assert result["communication_dimensions"] == []
    assert "communication_strengths" not in result
    assert result["caveats"]


def test_rewrite_with_invented_numbers_is_removed():
    q, a, r, u = evidence()
    r.delivery_assessment[0]["rewrite"] = {
        "original": a.answer_text,
        "improved": "Я сократил ошибки на 90%.",
    }
    assert ground_delivery(r.delivery_assessment, q, a, u)[0]["rewrite"] is None


def test_rejected_skill_disappears_from_all_aggregates_and_actions():
    q, a, r, u = evidence()
    result = ground_communication({}, [(q, a, r)], u, rejected_skills={"structure"})
    assert result["communication_score"] is None
    assert result["priority_actions"] == []
    assert (
        result["communication_summary"]
        == "Недостаточно подтверждённых реплик для оценки коммуникации."
    )


def test_communication_overview_distinguishes_strengths_gaps_and_missing_scores():
    q, a, r, u = evidence()
    r.delivery_assessment = [
        {**r.delivery_assessment[0], "skill": skill, "score": score}
        for skill, score in [
            ("structure", 0.4),
            ("specificity", 0.9),
            ("ownership", 0.7),
            ("clarification", None),
        ]
    ]
    output = ground_communication({}, [(q, a, r)], u)
    summary = output["communication_summary"]
    assert "по 4 из 8 категорий" in summary
    assert "Сильные стороны: конкретность." in summary
    assert "В первую очередь стоит проработать: структура ответа." in summary
    assert "Можно усилить: личный вклад." in summary
    assert "уточнение условий" not in summary
    assert len(summary) <= 800
    rejected = ground_communication({}, [(q, a, r)], u, rejected_skills={"structure"})
    assert "структура ответа" not in rejected["communication_summary"]


def test_missing_exercise_is_replaced_with_source_specific_practice():
    q, a, r, u = evidence()
    r.delivery_assessment[0].pop("exercise")
    result = ground_communication({}, [(q, a, r)], u)
    exercise = result["communication_dimensions"][0]["exercise"]
    assert a.answer_text in exercise["task"]
    assert exercise["success_criterion"]
    assert result["priority_actions"][0]["steps"] == [exercise["task"]]


@pytest.mark.parametrize("technical_score,first_skill", [(0.2, None), (0.8, "structure")])
def test_priorities_follow_gap_severity_instead_of_category(technical_score, first_skill):
    q, a, r, u = evidence()
    result = ground_communication(
        {
            "technical_topics": [{"topic": "Python", "score": technical_score}],
            "priority_actions": [{"title": "Повторить Python", "related_topics": ["Python"]}],
        },
        [(q, a, r)],
        u,
    )
    assert result["priority_actions"][0].get("communication_skill") == first_skill


def test_summary_carries_candidate_speech_and_context():
    import json

    q, a, r, u = evidence()
    block = json.loads(_summary_evidence_blocks([(q, a, r)], u, {"interview_type": "hr"})[0])
    assert block["answer_excerpt"] == a.answer_text
    assert block["answer_duration_ms"] == 7000
    assert block["answer_word_count"] == len(a.answer_text.split())
    assert block["delivery_assessment"][0]["evidence_quote"] == a.answer_text
    assert block["interview_context"]["interview_type"] == "hr"


def test_basic_gap_weighs_more_and_small_samples_have_no_percent():
    assert weighted_score([(0, 2), (1, 1), (1, 1)]) == 0.5
    assert weighted_score([(0, 2), (1, 1)]) is None
    rows = []
    for number, difficulty, score in [(1, D.JUNIOR, 0), (2, D.SENIOR, 1), (3, D.SENIOR, 1)]:
        q, a, r, _ = evidence(K.TECHNICAL)
        q.sequence_number = number
        q.difficulty = difficulty
        r.score = score
        r.assessment = A.INCORRECT if score == 0 else A.CORRECT
        if number == 1:
            r.incorrect_statements = [
                {
                    "statement": "Ошибка",
                    "correction": "Исправить базовое понятие",
                    "evidence": "Цитата",
                }
            ]
        rows.append((q, a, r))
    overview = InterviewSummaryOutput(
        overall_summary="Итог",
        technical_summary="Итог",
        communication_summary="Итог",
        technical_topics=[
            TechnicalTopicAssessment(
                topic="Опыт",
                summary="Итог",
                gaps=["Выдуманный пробел"],
                next_step="Повторить",
                evidence_question_numbers=[1, 2, 3, 999],
                questions_count=4,
                confidence=1,
            )
        ],
    )
    result = _ground_technical_assessment(overview, rows)
    assert result.technical_score == 0.5
    assert result.technical_topics[0].gaps == ["Исправить базовое понятие"]
    assert result.technical_topics[0].evidence_question_numbers == [1, 2, 3]


def test_mentor_technical_review_overrides_unreliable_ai_attribution():
    rows = []
    for number in range(1, 4):
        q, a, r, _ = evidence(K.TECHNICAL, unreliable=True)
        q.sequence_number = number
        r.source = S.MENTOR
        r.assessment = A.CORRECT
        r.score = 1.0
        rows.append((q, a, r))
    overview = InterviewSummaryOutput(
        overall_summary="Итог", technical_summary="Итог", communication_summary="Итог"
    )
    assert _ground_technical_assessment(overview, rows).technical_score == 1.0


def test_category_mean_counts_answers_not_duplicate_findings_and_keeps_gap_example():
    rows, utterances = [], []
    for score in [0.4] + [0.9] * 9:
        q, a, r, u = evidence()
        r.delivery_assessment[0]["score"] = score
        r.delivery_assessment *= 2
        rows.append((q, a, r))
        utterances.extend(u)
    result = ground_communication({}, rows, utterances)
    dimension = result["communication_dimensions"][0]
    assert result["communication_score"] is None
    assert dimension["score"] == pytest.approx(0.85)
    assert dimension["example_score"] == 0.4
    assert dimension["observation_count"] == dimension["scored_observation_count"] == 10
    assert result["priority_actions"][0]["communication_skill"] == "structure"


def test_short_acknowledgement_does_not_support_skill_judgment():
    q, a, r, u = evidence()
    a.answer_text = u[0].text = "Да, я исправил ошибку и проверил логи."
    r.delivery_assessment[0]["evidence_quote"] = "Да"
    assert ground_delivery(r.delivery_assessment, q, a, u) == []


@pytest.mark.parametrize(
    "source,improved,allowed",
    [
        ("В команде было 20 человек, я проверял логи.", "Я улучшил скорость на 20%.", False),
        (
            "В команде было 20 человек, я проверял логи.",
            "Я улучшил скорость на двадцать процентов.",
            False,
        ),
        ("Я сократил время на 1,5 часа и проверил логи.", "Время сократилось на 1.5 часа.", True),
        ("Я сократил время на 20 процентов и проверил логи.", "Время сократилось на 20%.", True),
    ],
)
def test_rewrite_preserves_quantities_and_units(source, improved, allowed):
    q, a, r, u = evidence()
    a.answer_text = u[0].text = source
    r.delivery_assessment[0].update(
        evidence_quote=source, rewrite={"original": source, "improved": improved}
    )
    output = ground_delivery(r.delivery_assessment, q, a, u)[0]
    assert (output["rewrite"] is not None) == allowed


def test_fallback_exercise_excerpt_has_word_boundary_and_ellipsis():
    q, a, r, u = evidence()
    source = "Я проверил диагностические сообщения и обнаружил причину сбоя. " * 4
    a.answer_text = u[0].text = source
    r.delivery_assessment[0].update(evidence_quote=source, exercise=None)
    task = ground_delivery(r.delivery_assessment, q, a, u)[0]["exercise"]["task"]
    quote = task.split("«")[1].split("»")[0]
    assert quote.endswith("…")
    assert len(quote) <= 120
    assert source.startswith(quote[:-1])
    assert not source[len(quote) - 1].isalpha()


def test_missing_delivery_does_not_repeat_technical_summary():
    result = ground_communication({"technical_summary": "Технические пробелы."}, [], [])
    assert result["overall_summary"] != result["technical_summary"]
