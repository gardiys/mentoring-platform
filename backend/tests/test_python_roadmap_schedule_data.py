import csv
import hashlib
from pathlib import Path

DATA_SHA256 = "41169788845a366a943bc1fe8ad8e7e47730a37f07c8c7cbe0c8a5aa49d52d4e"


def test_python_roadmap_schedule_is_complete() -> None:
    path = (
        Path(__file__).resolve().parent.parent
        / "migrations"
        / "data"
        / "python_roadmap_schedule.csv"
    )
    raw_data = path.read_bytes()
    assert hashlib.sha256(raw_data).hexdigest() == DATA_SHA256

    with path.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))

    assert len(rows) == 18
    assert [int(row["ID"]) for row in rows] == list(range(1, 19))
    assert [int(row["Сортировка"]) for row in rows] == list(range(1, 19))
    assert sum(int(row["Вес"]) for row in rows) == 138
    assert all(int(row["Вес"]) > 0 for row in rows)
    assert rows[0]["Тема"] == "Основы Python"
    assert rows[-1]["Тема"] == "Поиск работы"
