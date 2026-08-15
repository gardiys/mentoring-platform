import csv
import hashlib
from collections import Counter
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "migrations" / "data"
SOURCES = {
    "legacy_companies.csv": (
        "9d7fe02327bccce9cfad7f9cb8f80769ad44c8facd75c8b562857f319eeba39e",
        694,
    ),
    "shu_companies_20260815.csv": (
        "05c36decd9d5a5039887bd96fa625efe404d4a65130547f90289c42ca0843822",
        7,
    ),
    "shu_interviews_20260815.csv": (
        "1615971c2f94fecb7d1c6e229c9ce822c08cdf4f17da335a3d8e5f1ef094c4bd",
        34,
    ),
}


def _rows(filename: str) -> list[dict[str, str]]:
    path = DATA_DIR / filename
    expected_hash, expected_count = SOURCES[filename]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_hash
    with path.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    assert len(rows) == expected_count
    return rows


def test_shu_increment_contains_only_new_consistent_interviews() -> None:
    legacy_companies = {row["id"] for row in _rows("legacy_companies.csv")}
    incremental_companies = {row["id"] for row in _rows("shu_companies_20260815.csv")}
    interviews = _rows("shu_interviews_20260815.csv")

    assert {row["author_id"] for row in interviews} == {
        "51",
        "99",
        "176",
        "364",
        "369",
        "2587",
        "2773",
        "2777",
        "2782",
        "3185",
    }
    assert all(row["company_id"] in legacy_companies | incremental_companies for row in interviews)
    assert incremental_companies == {"747", "749", "750", "751", "752", "753", "754"}
    assert Counter(row["stage"] for row in interviews) == {
        "screaning": 22,
        "tech": 12,
    }
    assert Counter(row["specialization"] for row in interviews) == {"Python": 34}
    assert sum(bool(row["video_url"].strip()) for row in interviews) == 30
    assert len({(row["author_id"], row["company_id"]) for row in interviews}) == 31
