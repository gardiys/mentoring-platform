"""Source checks shared by workers and reads; legacy AI percentages are never trusted."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app.interviews.feedback_types import (
    SKILL_LABELS,
    CommunicationDimension,
    CommunicationExercise,
)
from app.interviews.intelligence_models import IntelligenceReviewSource, IntelligenceReviewStatus


def normalized(value: str) -> str:
    return " ".join(value.split()).casefold()


def difficulty_weight(value: object) -> int:
    return {"junior": 2, "middle": 1, "senior": 1}.get(str(value), 1)


def weighted_score(values: list[tuple[float, int]]) -> float | None:
    if len(values) < 3:
        return None
    return sum(score * weight for score, weight in values) / sum(w for _, w in values)


def _communication_summary(items: list[dict[str, Any]]) -> str:
    if not items:
        return "Недостаточно подтверждённых реплик для оценки коммуникации."
    scored = sorted(
        (item for item in items if item["score"] is not None), key=lambda item: item["score"]
    )
    parts = [f"Подтверждённые примеры есть по {len(items)} из {len(SKILL_LABELS)} категорий."]
    for label, selected in (
        ("Сильные стороны", [item for item in reversed(scored) if item["score"] >= 0.8]),
        ("В первую очередь стоит проработать", [item for item in scored if item["score"] < 0.6]),
        ("Можно усилить", [item for item in scored if 0.6 <= item["score"] < 0.8]),
    ):
        if selected:
            parts.append(
                label + ": " + ", ".join(item["name"].lower() for item in selected[:3]) + "."
            )
    if not scored:
        parts.append("Для числовой оценки пока недостаточно данных.")
    return " ".join(parts)


def excerpt(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1].rsplit(" ", 1)[0].rstrip(".,;:") + "…"


def _quantities(text: str) -> set[str]:
    # Conservative guard, not a semantic proof: normalise decimal punctuation and
    # preserve adjacent units, including spelled-out quantities.
    words = {
        "один": "1",
        "одна": "1",
        "одно": "1",
        "два": "2",
        "две": "2",
        "три": "3",
        "четыре": "4",
        "пять": "5",
        "шесть": "6",
        "семь": "7",
        "восемь": "8",
        "девять": "9",
        "десять": "10",
        "одиннадцать": "11",
        "двенадцать": "12",
        "тринадцать": "13",
        "четырнадцать": "14",
        "пятнадцать": "15",
        "шестнадцать": "16",
        "семнадцать": "17",
        "восемнадцать": "18",
        "девятнадцать": "19",
        "сорок": "40",
        "пятьдесят": "50",
        "шестьдесят": "60",
        "семьдесят": "70",
        "восемьдесят": "80",
        "девяносто": "90",
        "двести": "200",
        "триста": "300",
        "четыреста": "400",
        "пятьсот": "500",
        "шестьсот": "600",
        "семьсот": "700",
        "восемьсот": "800",
        "девятьсот": "900",
        "тысячи": "1000",
        "тысяч": "1000",
        "миллиона": "1000000",
        "миллионов": "1000000",
        "ноль": "0",
        "нуль": "0",
        "двадцать": "20",
        "тридцать": "30",
        "сто": "100",
        "тысяча": "1000",
        "миллион": "1000000",
    }
    value = normalized(text)
    for word, number in words.items():
        value = re.sub(r"\b" + word + r"\b", number, value)
    units = (
        r"%|процент\w*|человек\w*|сотрудник\w*|секунд\w*|минут\w*|час\w*|дн[яей]+|"
        r"месяц\w*|год\w*|лет|руб\w*|доллар\w*|раз\w*|задач\w*|проект\w*"
    )
    result = set()
    for match in re.finditer(r"\b(\d+(?:[.,]\d+)?)(?:\s*(" + units + r"))?", value):
        number, unit = match.groups()
        unit = unit or ""
        if unit.startswith("процент"):
            unit = "%"
        result.add(number.replace(",", ".") + ":" + unit)
    return result


def ground_delivery(
    dimensions: list[Any], question: Any, answer: Any, utterances: list[Any]
) -> list[dict[str, Any]]:
    if (question.transcription_annotations or {}).get("answer_unreliable"):
        return []
    source = {str(row.id): row.text for row in utterances}
    allowed = {str(value) for value in question.answer_utterance_ids}
    speech = normalized(answer.answer_text)
    result: list[dict[str, Any]] = []
    for raw in dimensions:
        try:
            item = CommunicationDimension.model_validate(raw)
        except (ValidationError, TypeError):
            continue
        quote = normalized(item.evidence_quote)
        ids = item.evidence_utterance_ids
        if (
            not item.skill
            or len(quote) < 20
            or not ids
            or not set(ids) <= allowed
            or not set(ids) <= source.keys()
            or quote not in speech
            or not any(quote in normalized(source[id_]) for id_ in ids)
        ):
            continue
        item.name = SKILL_LABELS[item.skill]
        item.confidence = min(item.confidence, question.confidence)
        if item.rewrite:
            original = normalized(item.rewrite.original)
            new_numbers = _quantities(item.rewrite.improved)
            known_numbers = _quantities(answer.answer_text)
            if (
                not original
                or original not in speech
                or not any(original in normalized(source[id_]) for id_ in ids)
                or not new_numbers <= known_numbers
            ):
                item.rewrite = None
        if item.score is not None and item.score < 0.6 and item.exercise is None:
            tasks = {
                "structure": (
                    "Перескажи этот пример по схеме ситуация → действие → результат.",
                    "Все три части названы и относятся к одному примеру.",
                ),
                "specificity": (
                    "Замени общие слова конкретными действиями из этого примера.",
                    "Названы проверяемые действия; факты и цифры не выдуманы.",
                ),
                "conciseness": (
                    "Дай прямой ответ, затем отдельно раскрой пояснения по запросу.",
                    "Первое предложение отвечает на вопрос; каждое пояснение связано с ним.",
                ),
                "clarification": (
                    "Повтори этот вопрос и назови условия, которые нужно уточнить до ответа.",
                    "Уточнения влияют на решение; предположения явно обозначены.",
                ),
                "handling_unknown": (
                    "Скажи, что известно, что пока неизвестно и как проверишь ответ.",
                    "Границы знаний обозначены без выдуманных утверждений.",
                ),
                "handling_pushback": (
                    "Повтори диалог: уточни смысл поправки и пересмотри ответ с её учётом.",
                    "Поправка учтена либо приведено проверяемое обоснование несогласия.",
                ),
                "reasoning_aloud": (
                    "Повтори решение, вслух называя предположения, варианты и причины выбора.",
                    "Можно проследить путь от условий задачи до решения.",
                ),
                "ownership": (
                    "Перескажи пример, отделив свой вклад от вклада команды.",
                    "Личные действия названы; заслуги коллег не приписаны себе.",
                ),
            }
            task, criterion = tasks[item.skill]
            item.exercise = CommunicationExercise(
                task=f"На примере «{excerpt(item.evidence_quote, 120)}»: {task}",
                success_criterion=criterion,
            )
        result.append(item.model_dump(mode="json"))
    return result


def ground_dimensions(
    rows: list[Any], utterances: list[Any], *, rejected_skills: set[str] | None = None
) -> tuple[list[dict[str, Any]], int]:
    grouped: dict[str, dict[UUID, dict[str, Any]]] = {}
    filtered_count = 0
    for question, answer, review in rows:
        raw = getattr(review, "delivery_assessment", None) or []
        grounded = ground_delivery(raw, question, answer, utterances)
        filtered_count += len(raw) - len(grounded)
        for item in grounded:
            skill = item["skill"]
            if skill in (rejected_skills or set()):
                continue
            per_question = grouped.setdefault(skill, {})
            old = per_question.get(question.id)
            if old is None or _example_severity(item) < _example_severity(old):
                per_question[question.id] = item
    items = []
    for observations in grouped.values():
        values = list(observations.values())
        selected = min(values, key=_example_severity)
        example = selected.copy()
        scores = [item["score"] for item in values if item["score"] is not None]
        example.update(
            example_score=example["score"],
            score=sum(scores) / len(scores) if scores else None,
            observation_count=len(values),
            scored_observation_count=len(scores),
        )
        items.append(example)
    return items, filtered_count


def _example_severity(item: dict[str, Any]) -> float:
    score = item.get("example_score", item.get("score"))
    return score if score is not None else 1


def ground_communication(
    payload: dict[str, Any],
    rows: list[Any],
    utterances: list[Any],
    *,
    rejected_skills: set[str] | None = None,
) -> dict[str, Any]:
    result = dict(payload)
    items, filtered_count = ground_dimensions(rows, utterances, rejected_skills=rejected_skills)
    dimensions = {item["skill"]: item for item in items}
    # No global percentage: coverage varies and the rubric is not a psychometric scale.
    result.pop("communication_strengths", None)
    result.pop("communication_growth_areas", None)
    result.update(
        communication_dimensions=items,
        communication_labels=SKILL_LABELS,
        communication_score=None,
        communication_grounded=bool(items),
        communication_summary=_communication_summary(items),
    )
    if filtered_count:
        result["caveats"] = list(
            dict.fromkeys(
                [
                    *(result.get("caveats") or []),
                    "Часть выводов о коммуникации исключена: цитаты слишком короткие "
                    "либо источник или авторство не подтверждены.",
                ]
            )
        )[:6]
    if not items and (
        payload.get("communication_dimensions") or payload.get("communication_score") is not None
    ):
        result["caveats"] = list(
            dict.fromkeys(
                [
                    *(result.get("caveats") or []),
                    "Оценка коммуникации скрыта: нет проверенных цитат. Нужен новый AI-разбор.",
                ]
            )
        )[:6]
    # Communication actions are built from grounded exercises, not a free-form summary.
    actions = [
        action
        for action in payload.get("priority_actions", [])
        if not action.get("communication_skill")
    ]
    coaching = [
        {
            "title": item["name"],
            "reason": excerpt(item["summary"], 500),
            "steps": [excerpt(item["exercise"]["task"], 300)],
            "success_criterion": item["exercise"]["success_criterion"],
            "related_topics": [],
            "communication_skill": item["skill"],
        }
        for item in sorted(items, key=_example_severity)
        if _example_severity(item) < 0.6 and item["exercise"]
    ][:3]

    def severity(action: dict[str, Any]) -> float:
        if skill := action.get("communication_skill"):
            return _example_severity(dimensions[skill])
        topics = [
            topic
            for topic in payload.get("technical_topics", [])
            if topic.get("topic") in action.get("related_topics", [])
        ]
        return min(
            (
                topic["score"]
                if topic.get("score") is not None
                else 0.4
                if topic.get("gaps")
                else 1
                for topic in topics
            ),
            default=0.5,
        )

    result["priority_actions"] = sorted(coaching + actions, key=severity)[:6]
    if not items and payload.get("technical_summary"):
        result["overall_summary"] = (
            "Для выводов о коммуникации недостаточно подтверждённых примеров. "
            "Оценки и рекомендации по отдельным ответам приведены ниже."
        )
    return result


def _effective_summary_rows(rows: list[Any]) -> list[Any]:
    grouped: dict[UUID, list[Any]] = {}
    order: list[UUID] = []
    for row in rows:
        question = row[0]
        if question.id not in grouped:
            order.append(question.id)
        grouped.setdefault(question.id, []).append(row)

    result: list[Any] = []
    for question_id in order:
        candidates = grouped[question_id]
        mentor = next(
            (
                row
                for row in candidates
                if row[2].source is IntelligenceReviewSource.MENTOR
                and row[2].status is IntelligenceReviewStatus.APPROVED
            ),
            None,
        )
        ai = next(
            (
                row
                for row in candidates
                if row[2].source is IntelligenceReviewSource.AI
                and row[2].status
                in {
                    IntelligenceReviewStatus.SUGGESTED,
                    IntelligenceReviewStatus.APPROVED,
                }
            ),
            None,
        )
        if selected := mentor or ai:
            result.append(selected)
    return result
