"""Import legacy student offers and payment history.

Revision ID: 20260811_0042
Revises: 20260810_0041
"""

from __future__ import annotations

import csv
import hashlib
import re
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from uuid import UUID, uuid5

import sqlalchemy as sa
from alembic import op

revision: str = "20260811_0042"
down_revision: str | None = "20260810_0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
USER_FILE = DATA_DIR / "legacy_users.csv"
COMPANY_FILE = DATA_DIR / "legacy_companies.csv"
OFFER_FILE = DATA_DIR / "legacy_offers.csv"
PAYMENT_FILE = DATA_DIR / "legacy_student_payments.csv"
DATA_FILES = {
    USER_FILE: (
        "4a9627d3d88cdc261fd59ece53aadfaf74d9f56bca841cc3fd49383671aa8773",
        238,
        {
            "id",
            "telegram_username",
            "role",
            "telegram_id",
            "chat_id",
            "name",
            "surname",
            "daily_notifications",
            "specialization",
            "extra_specialization",
        },
    ),
    COMPANY_FILE: (
        "9d7fe02327bccce9cfad7f9cb8f80769ad44c8facd75c8b562857f319eeba39e",
        694,
        {"id", "created_at", "updated_at", "name", "additional_names"},
    ),
    OFFER_FILE: (
        "1b293cefb9f2caeb3911f6d86420fca9bb57a154cbc031252ebf576ea9704e1d",
        79,
        {
            "id",
            "created_at",
            "updated_at",
            "mentee_id",
            "created_by_user_id",
            "company_id",
            "amount",
            "student_payment_percent",
            "status",
            "note",
            "rejected_reason",
            "employment_date",
            "canceled_at",
            "canceled_by_user_id",
            "cancellation_reason",
        },
    ),
    PAYMENT_FILE: (
        "992239558e7e6359c809e7a6ccd5b4838f3cc66810c820228bed23a066d40a93",
        607,
        {
            "id",
            "created_at",
            "updated_at",
            "offer_id",
            "due_date",
            "amount",
            "status",
            "paid_at",
            "payment_link",
            "confirmation_requested_at",
            "confirmed_at",
            "rejected_reason",
        },
    ),
}

LEGACY_IMPORT_NAMESPACE = UUID("b4e13c60-0a0d-4b35-9237-270166e00440")
PAYMENT_IMPORT_NAMESPACE = UUID("f0965be3-e4bc-4591-885a-318823196780")
ACCEPTED_OFFER_STATUSES = {"approved", "canceled"}
PAYMENT_STATUS_MAP = {
    "paid": "paid",
    "pending": "scheduled",
    "canceled": "cancelled",
    "awaiting_approval": "pending",
}
LEGAL_FORM_PATTERN = re.compile(
    r"(?:^|[\s,.;:()\-])(?:"
    r"ИП|ООО|ОАО|ЗАО|ПАО|АО|НКО|АНО|ФГУП|ГУП|МУП|ГБУ|ЧУ|"
    r"LLC|LTD|INC|JSC|PJSC|CORP(?:ORATION)?|COMPANY|CO"
    r")(?:$|[\s,.;:()\-])",
    flags=re.IGNORECASE,
)
NON_SEARCH_CHARACTER = re.compile(r"[^0-9a-zа-я]+", flags=re.IGNORECASE)
EDGE_QUOTES = " \t\r\n\"'`«»„“”()[]{}.,;:—–-"


def _read_rows(path: Path) -> list[dict[str, str]]:
    expected_hash, expected_count, expected_fields = DATA_FILES[path]
    raw_data = path.read_bytes()
    if hashlib.sha256(raw_data).hexdigest() != expected_hash:
        raise RuntimeError(f"Legacy payment import checksum does not match for {path.name}")
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if set(reader.fieldnames or []) != expected_fields:
            raise RuntimeError(f"Legacy payment import has unexpected columns in {path.name}")
        rows = list(reader)
    if len(rows) != expected_count:
        raise RuntimeError(f"Expected {expected_count} rows in {path.name}, got {len(rows)}")
    return rows


def _legacy_identity(kind: str, legacy_id: str) -> UUID:
    return uuid5(LEGACY_IMPORT_NAMESPACE, f"{kind}:{legacy_id}")


def _payment_identity(kind: str, legacy_id: str) -> UUID:
    return uuid5(PAYMENT_IMPORT_NAMESPACE, f"{kind}:{legacy_id}")


def _parse_datetime(value: str) -> datetime:
    normalized = re.sub(r"\s+([+-]\d{4})$", r"\1", value.strip())
    return datetime.fromisoformat(normalized)


def _clean_company_name(value: str) -> str:
    name = re.sub(r"\s+", " ", value.replace("\x00", " ")).strip(EDGE_QUOTES)
    previous = None
    while name and name != previous:
        previous = name
        name = LEGAL_FORM_PATTERN.sub(" ", f" {name} ")
        name = re.sub(r"\s+", " ", name).strip(EDGE_QUOTES)
    if not name:
        raise RuntimeError("Legacy company has an empty name after normalization")
    return name[:240]


def _search_key(value: str) -> str:
    return NON_SEARCH_CHARACTER.sub("", value.casefold().replace("ё", "е"))


def _resolve_users(connection: sa.Connection, rows: list[dict[str, str]]) -> dict[str, UUID]:
    existing_by_telegram = {
        str(row["telegram_id"]): row["id"]
        for row in connection.execute(
            sa.text("SELECT id, telegram_id FROM users WHERE telegram_id IS NOT NULL")
        ).mappings()
    }
    existing_ids = {
        row["id"] for row in connection.execute(sa.text("SELECT id FROM users")).mappings()
    }
    resolved: dict[str, UUID] = {}
    for row in rows:
        if row["role"].strip() == "Гость":
            continue
        telegram_id = row["telegram_id"].strip()
        user_id = existing_by_telegram.get(telegram_id) if telegram_id else None
        user_id = user_id or _legacy_identity("user", row["id"])
        if user_id not in existing_ids:
            raise RuntimeError(f"Legacy user {row['id']} was not imported before payment history")
        resolved[row["id"]] = user_id
    return resolved


def _resolve_companies(
    connection: sa.Connection, rows: list[dict[str, str]]
) -> dict[str, tuple[UUID, str]]:
    company_by_key: dict[str, tuple[UUID, str]] = {
        row["normalized_name"]: (row["id"], row["name"])
        for row in connection.execute(
            sa.text("SELECT id, name, normalized_name FROM companies")
        ).mappings()
    }
    company_by_key.update(
        {
            row["normalized_name"]: (row["company_id"], row["company_name"])
            for row in connection.execute(
                sa.text(
                    """
                    SELECT alias.company_id, alias.normalized_name,
                           company.name AS company_name
                    FROM company_aliases AS alias
                    JOIN companies AS company ON company.id = alias.company_id
                    """
                )
            ).mappings()
        }
    )
    resolved: dict[str, tuple[UUID, str]] = {}
    for row in rows:
        name = _clean_company_name(row["name"])
        company = company_by_key.get(_search_key(name))
        if company is None:
            raise RuntimeError(f"Legacy company {row['id']} was not imported")
        resolved[row["id"]] = company
    return resolved


def _company_for_offer(
    row: dict[str, str], companies: dict[str, tuple[UUID, str]]
) -> tuple[UUID | None, str]:
    legacy_company_id = row["company_id"].strip()
    if not legacy_company_id:
        return None, "Компания не указана"
    company = companies.get(legacy_company_id)
    if company is None:
        return None, f"Компания #{legacy_company_id} (архив)"
    return company


def _existing_employment_id(
    connection: sa.Connection,
    *,
    student_id: UUID,
    start_date: object,
    salary_kopecks: int,
    repayment_percent: Decimal,
) -> UUID | None:
    return connection.execute(
        sa.text(
            """
            SELECT id
            FROM student_employments
            WHERE student_id = :student_id
              AND start_date = :start_date
              AND net_salary_kopecks = :salary_kopecks
              AND repayment_percent = :repayment_percent
            ORDER BY created_at, id
            LIMIT 1
            """
        ),
        {
            "student_id": student_id,
            "start_date": start_date,
            "salary_kopecks": salary_kopecks,
            "repayment_percent": repayment_percent,
        },
    ).scalar_one_or_none()


def _import_employment(
    connection: sa.Connection,
    row: dict[str, str],
    users: dict[str, UUID],
    companies: dict[str, tuple[UUID, str]],
) -> UUID:
    student_id = users[row["mentee_id"]]
    start_date = _parse_datetime(f"{row['employment_date']}T00:00:00+03:00").date()
    salary_kopecks = int(row["amount"]) * 100
    repayment_percent = Decimal(row["student_payment_percent"])
    existing_id = _existing_employment_id(
        connection,
        student_id=student_id,
        start_date=start_date,
        salary_kopecks=salary_kopecks,
        repayment_percent=repayment_percent,
    )
    if existing_id is not None:
        return existing_id

    requested_status = "terminated" if row["status"] == "canceled" else "active"
    active_employment = (
        connection.execute(
            sa.text(
                """
            SELECT id, start_date
            FROM student_employments
            WHERE student_id = :student_id AND status = 'active'
            LIMIT 1
            """
            ),
            {"student_id": student_id},
        )
        .mappings()
        .first()
    )
    status = (
        "terminated" if requested_status == "active" and active_employment else requested_status
    )
    if row["canceled_at"].strip():
        ended_at = _parse_datetime(row["canceled_at"]).date()
        end_reason = row["cancellation_reason"].strip()[:500] or "Оффер отменён"
    elif status == "terminated":
        ended_at = active_employment["start_date"] if active_employment else start_date
        end_reason = "Импортировано как архив: уже есть активное трудоустройство"
    else:
        ended_at = None
        end_reason = None

    company_id, company_name = _company_for_offer(row, companies)
    employment_id = _payment_identity("employment", row["id"])
    connection.execute(
        sa.text(
            """
            INSERT INTO student_employments
                (id, student_id, company_id, company_name, start_date,
                 net_salary_kopecks, repayment_percent, status, ended_at,
                 end_reason, payment_day_first, payment_day_second,
                 recorded_by_user_id, created_at, updated_at)
            VALUES
                (:id, :student_id, :company_id, :company_name, :start_date,
                 :salary_kopecks, :repayment_percent,
                 CAST(:status AS student_employment_status), :ended_at,
                 :end_reason, 10, 25, :recorded_by_user_id,
                 :created_at, :updated_at)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {
            "id": employment_id,
            "student_id": student_id,
            "company_id": company_id,
            "company_name": company_name,
            "start_date": start_date,
            "salary_kopecks": salary_kopecks,
            "repayment_percent": repayment_percent,
            "status": status,
            "ended_at": ended_at,
            "end_reason": end_reason,
            "recorded_by_user_id": users.get(row["created_by_user_id"]),
            "created_at": _parse_datetime(row["created_at"]),
            "updated_at": _parse_datetime(row["updated_at"]),
        },
    )
    return employment_id


def _import_installment(
    connection: sa.Connection,
    *,
    row: dict[str, str],
    offer: dict[str, str],
    employment_id: UUID,
    sequence_number: int,
    recorded_by_user_id: UUID | None,
) -> UUID:
    salary_rubles = Decimal(offer["amount"])
    amount_rubles = Decimal(row["amount"])
    salary_percent = (amount_rubles * 100 / salary_rubles).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    status = PAYMENT_STATUS_MAP[row["status"]]
    due_date = _parse_datetime(row["due_date"]).date()
    paid_at_value = row["paid_at"].strip() or row["confirmed_at"].strip()
    paid_at = _parse_datetime(paid_at_value) if paid_at_value else None
    existing = (
        connection.execute(
            sa.text(
                """
            SELECT id, status
            FROM payment_installments
            WHERE employment_id = :employment_id
              AND sequence_number = :sequence_number
            """
            ),
            {"employment_id": employment_id, "sequence_number": sequence_number},
        )
        .mappings()
        .first()
    )
    if existing is not None:
        installment_id = existing["id"]
        connection.execute(
            sa.text(
                """
                UPDATE payment_installments
                SET status = CASE
                        WHEN status = 'paid' THEN status
                        ELSE CAST(:status AS payment_installment_status)
                    END,
                    paid_at = COALESCE(paid_at, :paid_at),
                    confirmed_by_user_id = CASE
                        WHEN :status = 'paid'
                        THEN COALESCE(confirmed_by_user_id, :confirmed_by_user_id)
                        ELSE confirmed_by_user_id
                    END,
                    updated_at = GREATEST(updated_at, :updated_at)
                WHERE id = :id
                """
            ),
            {
                "id": installment_id,
                "status": status,
                "paid_at": paid_at,
                "confirmed_by_user_id": recorded_by_user_id,
                "updated_at": _parse_datetime(row["updated_at"]),
            },
        )
        return installment_id

    installment_id = _payment_identity("installment", row["id"])
    connection.execute(
        sa.text(
            """
            INSERT INTO payment_installments
                (id, employment_id, sequence_number, due_date, amount_kopecks,
                 salary_percent, status, paid_at, confirmed_by_user_id,
                 created_at, updated_at)
            VALUES
                (:id, :employment_id, :sequence_number, :due_date,
                 :amount_kopecks, :salary_percent,
                 CAST(:status AS payment_installment_status), :paid_at,
                 :confirmed_by_user_id, :created_at, :updated_at)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {
            "id": installment_id,
            "employment_id": employment_id,
            "sequence_number": sequence_number,
            "due_date": due_date,
            "amount_kopecks": int(amount_rubles * 100),
            "salary_percent": salary_percent,
            "status": status,
            "paid_at": paid_at,
            "confirmed_by_user_id": recorded_by_user_id if status == "paid" else None,
            "created_at": _parse_datetime(row["created_at"]),
            "updated_at": _parse_datetime(row["updated_at"]),
        },
    )
    return installment_id


def upgrade() -> None:
    user_rows = _read_rows(USER_FILE)
    company_rows = _read_rows(COMPANY_FILE)
    offer_rows = _read_rows(OFFER_FILE)
    payment_rows = _read_rows(PAYMENT_FILE)
    connection = op.get_bind()

    if {row["status"] for row in offer_rows} != {"approved", "rejected", "canceled"}:
        raise RuntimeError("Legacy offers contain an unknown status")
    if set(PAYMENT_STATUS_MAP) != {row["status"] for row in payment_rows}:
        raise RuntimeError("Legacy student payments contain an unknown status")

    offers = {row["id"]: row for row in offer_rows}
    if len(offers) != len(offer_rows):
        raise RuntimeError("Legacy offer ids are not unique")
    if any(row["offer_id"] not in offers for row in payment_rows):
        raise RuntimeError("Legacy payment references an unknown offer")

    users = _resolve_users(connection, user_rows)
    companies = _resolve_companies(connection, company_rows)
    accepted_offers = {
        offer_id: row
        for offer_id, row in offers.items()
        if row["status"] in ACCEPTED_OFFER_STATUSES
    }
    if any(row["mentee_id"] not in users for row in accepted_offers.values()):
        raise RuntimeError("Legacy offer references a user that was not imported")

    employment_ids = {
        offer_id: _import_employment(connection, row, users, companies)
        for offer_id, row in accepted_offers.items()
    }
    payments_by_offer: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in payment_rows:
        if row["offer_id"] in accepted_offers:
            payments_by_offer[row["offer_id"]].append(row)

    for offer_id, rows in payments_by_offer.items():
        offer = accepted_offers[offer_id]
        ordered_rows = sorted(
            rows,
            key=lambda row: (
                _parse_datetime(row["due_date"]),
                _parse_datetime(row["created_at"]),
                int(row["id"]),
            ),
        )
        recorded_by_user_id = users.get(offer["created_by_user_id"])
        for sequence_number, row in enumerate(ordered_rows, start=1):
            _import_installment(
                connection,
                row=row,
                offer=offer,
                employment_id=employment_ids[offer_id],
                sequence_number=sequence_number,
                recorded_by_user_id=recorded_by_user_id,
            )


def downgrade() -> None:
    offer_rows = _read_rows(OFFER_FILE)
    payment_rows = _read_rows(PAYMENT_FILE)
    accepted_offer_ids = {
        row["id"] for row in offer_rows if row["status"] in ACCEPTED_OFFER_STATUSES
    }
    imported_payment_rows = [row for row in payment_rows if row["offer_id"] in accepted_offer_ids]
    reward_ids = [
        _payment_identity("mentor-reward", row["id"])
        for row in imported_payment_rows
        if row["status"] == "paid"
    ]
    installment_ids = [_payment_identity("installment", row["id"]) for row in imported_payment_rows]
    employment_ids = [_payment_identity("employment", offer_id) for offer_id in accepted_offer_ids]
    connection = op.get_bind()
    for table, ids in (
        ("mentor_rewards", reward_ids),
        ("payment_installments", installment_ids),
        ("student_employments", employment_ids),
    ):
        connection.execute(
            sa.text(f"DELETE FROM {table} WHERE id IN :ids").bindparams(
                sa.bindparam("ids", expanding=True)
            ),
            {"ids": ids},
        )
