"""Resolve known subtopics to existing broad categories; never create a taxonomy."""

import re

_TOPIC_ALIASES = {
    "apache kafka": "Брокеры сообщений",
    "kafka": "Брокеры сообщений",
    "rabbitmq": "Брокеры сообщений",
    "асинхронность": "Конкурентность в Python",
    "асинхронное программирование": "Конкурентность в Python",
    "многопоточность": "Конкурентность в Python",
    "multiprocessing": "Конкурентность в Python",
    "asyncio": "Конкурентность в Python",
    "тестирование по": "Тестирование программ",
    "pytest": "Тестирование программ",
    "unit testing": "Тестирование программ",
    "postgres": "Базы данных",
    "postgresql": "Базы данных",
    "sql": "Базы данных",
    "llm": "ML",
    "rag": "ML",
}


def topic_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def resolved_topic(topic: str | None, categories: set[str]) -> str | None:
    if not topic:
        return None
    exact = {c for c in categories if topic_key(c) == topic_key(topic)}
    if len(exact) == 1:
        return next(iter(exact))
    target = _TOPIC_ALIASES.get(topic_key(topic))
    mapped = {c for c in categories if target and topic_key(c) == topic_key(target)}
    return next(iter(mapped)) if len(mapped) == 1 else None
