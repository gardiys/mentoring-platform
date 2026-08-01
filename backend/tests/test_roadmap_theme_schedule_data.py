import csv
import hashlib
from pathlib import Path

DATA_SHA256 = "d6b5fb2dfcc36f9fd640389a3d7f2d7240c0787a9770104501fa3a10dafb4794"


def _combined_identity(row: dict[str, str]) -> tuple[object, ...]:
    return (
        int(row["id"]),
        row["main_theme"].strip(),
        row["theme"].strip(),
        int(row["weight"]),
        int(row["ordering"]),
        row["description"].strip(),
    )


def _python_identity(row: dict[str, str]) -> tuple[object, ...]:
    return (
        int(row["ID"]),
        row["Раздел"].strip(),
        row["Тема"].strip(),
        int(row["Вес"]),
        int(row["Сортировка"]),
        row["Описание"].strip(),
    )


def test_combined_roadmap_schedule_matches_python_and_contains_go_weights() -> None:
    data_dir = Path(__file__).resolve().parent.parent / "migrations" / "data"
    combined_path = data_dir / "roadmap_theme_schedule.csv"
    assert hashlib.sha256(combined_path.read_bytes()).hexdigest() == DATA_SHA256

    with combined_path.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    with (data_dir / "python_roadmap_schedule.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        existing_python_rows = list(csv.DictReader(source))

    python_rows = sorted(
        (row for row in rows if row["specialization"] == "Python"),
        key=lambda row: int(row["ordering"]),
    )
    go_rows = sorted(
        (row for row in rows if row["specialization"] == "Go"),
        key=lambda row: int(row["ordering"]),
    )

    assert [_combined_identity(row) for row in python_rows] == [
        _python_identity(row) for row in existing_python_rows
    ]
    assert len(python_rows) == 18
    assert sum(int(row["weight"]) for row in python_rows) == 138

    assert len(go_rows) == 19
    assert sum(int(row["weight"]) for row in go_rows) == 124
    assert [int(row["ordering"]) for row in go_rows] == [
        *range(1, 13),
        *range(14, 19),
        20,
        21,
    ]
    assert {row["theme"]: int(row["weight"]) for row in go_rows}["Поиск работы"] == 30
