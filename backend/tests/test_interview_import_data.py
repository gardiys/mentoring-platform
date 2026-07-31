import csv
from collections import Counter
from pathlib import Path


def test_python_interview_csv_is_complete_and_normalizable() -> None:
    path = (
        Path(__file__).resolve().parent.parent
        / "migrations"
        / "data"
        / "python_interview_questions.csv"
    )
    with path.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))

    assert len(rows) == 495
    assert all(row["Вопрос"].strip() and row["Ответ"].strip() for row in rows)
    assert len({row["Тема"].strip() for row in rows}) == 25
    frequencies = Counter(row["Встречается"].strip() for row in rows)
    assert frequencies == {
        "Часто": 132,
        "Редко": 156,
        "Иногда": 110,
        "Средне": 84,
        "": 13,
    }
