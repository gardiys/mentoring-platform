import csv
import hashlib
from collections import Counter
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "migrations" / "data"
SOURCES = {
    "legacy_users.csv": (
        "4a9627d3d88cdc261fd59ece53aadfaf74d9f56bca841cc3fd49383671aa8773",
        238,
    ),
    "legacy_companies.csv": (
        "9d7fe02327bccce9cfad7f9cb8f80769ad44c8facd75c8b562857f319eeba39e",
        694,
    ),
    "legacy_interviews.csv": (
        "3464795d0b293dc00e0b7dcdc40923c02aa4cf15d8b1de15d2be8c5493ad152f",
        2499,
    ),
    "mentorship_associations.csv": (
        "8d6dc6ced374fa9418bdf6b05ce6e8ac1d0150952818182201e80cd99bd1ddd1",
        170,
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


def test_legacy_interview_sources_are_complete_and_consistent() -> None:
    users = _rows("legacy_users.csv")
    companies = _rows("legacy_companies.csv")
    interviews = _rows("legacy_interviews.csv")
    users_by_id = {row["id"]: row for row in users}
    company_ids = {row["id"] for row in companies}

    assert Counter(row["role"] for row in users) == {
        "Менти": 121,
        "Выпускник": 88,
        "Гость": 19,
        "Ментор": 9,
        "CEO": 1,
    }
    imported_users = [row for row in users if row["role"] != "Гость"]
    assert len(imported_users) == 219
    assert all(row["name"].strip() and row["surname"].strip() for row in imported_users)
    assert all(row["telegram_username"].strip() for row in imported_users)
    assert len({row["telegram_id"] for row in imported_users if row["telegram_id"].strip()}) == 209

    assert all(row["author_id"] in users_by_id for row in interviews)
    assert all(row["company_id"] in company_ids for row in interviews)
    assert {row["stage"] for row in interviews} == {
        "screaning",
        "tech",
        "system",
        "final",
        "audio",
    }
    imported_interviews = [
        row for row in interviews if users_by_id[row["author_id"]]["role"] != "Гость"
    ]
    assert len(imported_interviews) == 2463
    assert len({(row["author_id"], row["company_id"]) for row in imported_interviews}) == 1706
    imported_media = [
        row["video_url"].strip() for row in imported_interviews if row["video_url"].strip()
    ]
    assert len(imported_media) == 2152
    assert all(url.startswith("https://s3.firstvds.ru:443/interviews/") for url in imported_media)


def test_mentorship_associations_have_one_mentor_per_student() -> None:
    users = {row["id"]: row for row in _rows("legacy_users.csv")}
    associations = _rows("mentorship_associations.csv")

    assert len({row["mentee_id"] for row in associations}) == 170
    assert len({row["mentor_id"] for row in associations}) == 8
    assert all(row["mentee_id"] in users for row in associations)
    assert all(users[row["mentor_id"]]["role"] == "Ментор" for row in associations)
    assert sum(users[row["mentee_id"]]["role"] == "Гость" for row in associations) == 8
