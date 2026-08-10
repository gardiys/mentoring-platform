import csv
import hashlib
from decimal import Decimal
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "migrations" / "data"
SOURCES = {
    "mentor_payouts_daniil_diakonov.csv": (
        "5fa1aa6edbe3af908dd243b4cd552e5226c67f866d5c62292eef511f5f3fd0b5",
        26,
        19,
    ),
    "mentor_payouts_ilya_bochkarev.csv": (
        "bad94df25de3671ac36fc484a46b7f4966265cfb7e562b0a137d569adfedc58a",
        65,
        38,
    ),
    "mentor_payouts_konstantin_oleshko.csv": (
        "daca80bd2f9b0014456cd97d9fafb0ffd36e763d0383d38e7e622300df323b4b",
        30,
        23,
    ),
    "mentor_payouts_mikhail_zubko.csv": (
        "8f4309101927b1ee4e03604fdd10aff76598a1f14af0c7882aac7881160e5e36",
        32,
        19,
    ),
    "mentor_payouts_oleg_bogomolov.csv": (
        "023992e8c68a4b3bb280a6f6a8c4bfe12b5502c468473cd45c11edc0329751cc",
        72,
        27,
    ),
    "mentor_payouts_oleg_chernikov.csv": (
        "8916cf214a9e9be5543a5d31d67e925ed7f35a8baa5ff11d4dd5ea71e6beff21",
        40,
        22,
    ),
    "mentor_payouts_roman_mamin.csv": (
        "2ff95f0f429cd0663158a9d1a1bade78ae3fd4e4a7260f15b8ae8c1371197ae8",
        68,
        46,
    ),
}


def _decimal(value: str) -> Decimal:
    return Decimal((value.strip() or "0").replace(" ", "").replace(",", "."))


def test_legacy_mentor_payout_sources_are_complete_and_consistent() -> None:
    total_accrued = Decimal(0)
    total_paid = Decimal(0)
    total_debt = Decimal(0)
    nonempty_count = 0

    for filename, (expected_hash, expected_rows, expected_nonempty) in SOURCES.items():
        path = DATA_DIR / filename
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_hash
        with path.open(encoding="utf-8-sig", newline="") as source:
            rows = list(csv.DictReader(source))
        assert len(rows) == expected_rows
        rows = [row for row in rows if row["Имя"].strip()]
        assert len(rows) == expected_nonempty
        nonempty_count += len(rows)

        for row in rows:
            basis = _decimal(row["Сумма Оффера / отказа"])
            percent = _decimal(row["Процент выплаты"])
            paid = _decimal(row["Суммарно выплачено"])
            debt = _decimal(row["Всего задолженность"])
            payout_parts = sum(
                (_decimal(row[f"Выплата {index}"]) for index in range(1, 9)),
                Decimal(0),
            )
            accrued = basis * percent / 100

            assert payout_parts == paid
            assert paid + debt == accrued
            total_accrued += accrued
            total_paid += paid
            total_debt += debt

    assert nonempty_count == 194
    assert total_accrued == Decimal("11453009.28")
    assert total_paid == Decimal("8491076")
    assert total_debt == Decimal("2961933.28")
