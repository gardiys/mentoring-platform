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
            or not quote
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
            new_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", item.rewrite.improved))
            known_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", answer.answer_text))
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
                task=f"На примере «{item.evidence_quote[:120]}»: {task}",
                success_criterion=criterion,
            )
        result.append(item.model_dump(mode="json"))
    return result


def ground_communication(
    payload: dict[str, Any],
    rows: list[Any],
    utterances: list[Any],
    *,
    rejected_skills: set[str] | None = None,
) -> dict[str, Any]:
    result = dict(payload)
    dimensions: dict[str, dict[str, Any]] = {}
    filtered_count = 0
    for question, answer, review in rows:
        raw = getattr(review, "delivery_assessment", None) or []
        grounded = ground_delivery(raw, question, answer, utterances)
        filtered_count += len(raw) - len(grounded)
        for item in grounded:
            skill = item["skill"]
            if skill in (rejected_skills or set()):
                continue
            # Keep one concrete example for each skill, prioritising an observed gap.
            old = dimensions.get(skill)
            if old is None or (
                item["score"] is not None and (old["score"] is None or item["score"] < old["score"])
            ):
                dimensions[skill] = item
    items = list(dimensions.values())
    scores = [item["score"] for item in items if item["score"] is not None]
    result.update(
        communication_dimensions=items,
        communication_score=sum(scores) / len(scores) if scores else None,
        communication_grounded=bool(items),
        communication_summary=_communication_summary(items),
        communication_strengths=[
            item["summary"][:300]
            for item in items
            if item["score"] is not None and item["score"] >= 0.8
        ][:3],
        communication_growth_areas=[
            item["summary"][:300]
            for item in items
            if item["score"] is not None and item["score"] < 0.6
        ][:3],
    )
    if filtered_count:
        result["caveats"] = list(
            dict.fromkeys(
                [
                    *(result.get("caveats") or []),
                    "Часть выводов о коммуникации исключена: цитаты или авторство не подтверждены.",
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
            "reason": item["summary"][:500],
            "steps": [item["exercise"]["task"][:300]],
            "success_criterion": item["exercise"]["success_criterion"],
            "related_topics": [],
            "communication_skill": item["skill"],
        }
        for item in sorted(items, key=lambda x: x["score"] if x["score"] is not None else 1)
        if item["score"] is not None and item["score"] < 0.6 and item["exercise"]
    ][:3]

    def severity(action: dict[str, Any]) -> float:
        if skill := action.get("communication_skill"):
            return float(dimensions[skill]["score"])
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
        result["overall_summary"] = payload["technical_summary"]
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
