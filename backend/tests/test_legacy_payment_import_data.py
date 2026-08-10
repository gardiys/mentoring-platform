import csv
import hashlib
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "migrations" / "data"
SOURCES = {
    "legacy_offers.csv": (
        "1b293cefb9f2caeb3911f6d86420fca9bb57a154cbc031252ebf576ea9704e1d",
        79,
    ),
    "legacy_student_payments.csv": (
        "992239558e7e6359c809e7a6ccd5b4838f3cc66810c820228bed23a066d40a93",
        607,
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


def test_legacy_offers_and_payments_are_complete_and_consistent() -> None:
    offers = _rows("legacy_offers.csv")
    payments = _rows("legacy_student_payments.csv")
    offers_by_id = {row["id"]: row for row in offers}

    assert len(offers_by_id) == len(offers)
    assert len({row["id"] for row in payments}) == len(payments)
    assert Counter(row["status"] for row in offers) == {
        "approved": 72,
        "rejected": 6,
        "canceled": 1,
    }
    assert Counter(row["status"] for row in payments) == {
        "paid": 421,
        "pending": 108,
        "canceled": 75,
        "awaiting_approval": 3,
    }
    assert all(row["offer_id"] in offers_by_id for row in payments)
    assert all(
        offers_by_id[row["offer_id"]]["status"] in {"approved", "canceled"} for row in payments
    )
    assert sum(int(row["amount"]) for row in payments if row["status"] == "paid") == 29_133_170
    assert all(row["paid_at"].strip() for row in payments if row["status"] == "paid")


def test_every_accepted_offer_has_a_payment_schedule() -> None:
    offers = _rows("legacy_offers.csv")
    payments = _rows("legacy_student_payments.csv")
    payment_rows_by_offer: dict[str, list[dict[str, str]]] = defaultdict(list)
    for payment in payments:
        payment_rows_by_offer[payment["offer_id"]].append(payment)

    accepted = [row for row in offers if row["status"] in {"approved", "canceled"}]
    assert len(accepted) == 73
    assert len({row["mentee_id"] for row in accepted}) == 73
    assert all(payment_rows_by_offer[row["id"]] for row in accepted)
    assert {row["student_payment_percent"] for row in accepted} == {"100", "200"}

    for offer in accepted:
        paid_rubles = sum(
            int(payment["amount"])
            for payment in payment_rows_by_offer[offer["id"]]
            if payment["status"] == "paid"
        )
        contractual_rubles = (
            Decimal(offer["amount"]) * Decimal(offer["student_payment_percent"]) / 100
        )
        assert Decimal(paid_rubles) <= contractual_rubles
