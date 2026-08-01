import csv
import hashlib
from collections import Counter
from pathlib import Path

DATA_SHA256 = "a60f7112503d1c792ff4704ef997ce9cf5f05fd06e95b615be6040241f7bf352"


def test_go_interview_csv_is_complete_and_normalizable() -> None:
    path = (
        Path(__file__).resolve().parent.parent
        / "migrations"
        / "data"
        / "go_interview_questions.csv"
    )
    raw_data = path.read_bytes()
    assert hashlib.sha256(raw_data).hexdigest() == DATA_SHA256

    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        assert set(reader.fieldnames or []) == {"Тема", "Вопрос", "Ответ с пояснением"}
        rows = list(reader)

    assert len(rows) == 233
    assert all(
        row["Тема"].strip() and row["Вопрос"].strip() and row["Ответ с пояснением"].strip()
        for row in rows
    )
    assert len({row["Вопрос"].strip().casefold() for row in rows}) == len(rows)
    assert Counter(row["Тема"].strip() for row in rows) == {
        "Алгоритмы и структуры данных (бэкенд-минимум)": 3,
        "Архитектура и System Design": 19,
        "Интеграции и внешние API (Resilience + Anti-Corruption Layer)": 1,
        "Тестирование (база)": 8,
        "Cache (Redis и кеш-паттерны)": 3,
        "DevOps минимум и Delivery": 25,
        "Git": 8,
        "Go Concurrency (обязательный прод-уровень)": 29,
        "Go Core (язык и стандартная библиотека)": 22,
        "Go Runtime & Performance (чтобы быть “опытным”)": 30,
        "Go Tooling & Codebase Engineering (уровень “инженер”)": 5,
        "HR вопросы": 12,
        "HTTP/API слой (REST + gRPC)": 9,
        "Integrations": 1,
        "Kafka": 8,
        "Messaging / Brokers (Kafka/Rabbit/NATS) + паттерны": 4,
        "Observability & SRE-мышление": 4,
        "PostgreSQL и SQL (прод-уровень)": 23,
        "Professional Skills (ownership) + AI-workflow": 15,
        "Security (backend-практика)": 4,
    }
