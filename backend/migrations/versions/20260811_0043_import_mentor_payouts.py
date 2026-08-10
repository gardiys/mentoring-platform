"""Import aggregated historical mentor rewards and payouts.

Revision ID: 20260811_0043
Revises: 20260811_0042
"""

from __future__ import annotations

import csv
import hashlib
import re
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import NamedTuple
from uuid import UUID, uuid5

import sqlalchemy as sa
from alembic import op

revision: str = "20260811_0043"
down_revision: str | None = "20260811_0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
USER_FILE = DATA_DIR / "legacy_users.csv"
PAYMENT_FILE = DATA_DIR / "legacy_student_payments.csv"
PAYOUT_FILES = {
    DATA_DIR / "mentor_payouts_roman_mamin.csv": (
        "2ff95f0f429cd0663158a9d1a1bade78ae3fd4e4a7260f15b8ae8c1371197ae8",
        68,
        "24",
    ),
    DATA_DIR / "mentor_payouts_daniil_diakonov.csv": (
        "5fa1aa6edbe3af908dd243b4cd552e5226c67f866d5c62292eef511f5f3fd0b5",
        26,
        "101",
    ),
    DATA_DIR / "mentor_payouts_konstantin_oleshko.csv": (
        "daca80bd2f9b0014456cd97d9fafb0ffd36e763d0383d38e7e622300df323b4b",
        30,
        "20",
    ),
    DATA_DIR / "mentor_payouts_oleg_chernikov.csv": (
        "8916cf214a9e9be5543a5d31d67e925ed7f35a8baa5ff11d4dd5ea71e6beff21",
        40,
        "18",
    ),
    DATA_DIR / "mentor_payouts_mikhail_zubko.csv": (
        "8f4309101927b1ee4e03604fdd10aff76598a1f14af0c7882aac7881160e5e36",
        32,
        "5",
    ),
    DATA_DIR / "mentor_payouts_oleg_bogomolov.csv": (
        "023992e8c68a4b3bb280a6f6a8c4bfe12b5502c468473cd45c11edc0329751cc",
        72,
        "13",
    ),
    DATA_DIR / "mentor_payouts_ilya_bochkarev.csv": (
        "bad94df25de3671ac36fc484a46b7f4966265cfb7e562b0a137d569adfedc58a",
        65,
        "23",
    ),
}
PAYOUT_FIELDS = {
    "Имя",
    "Фамилия",
    "Телеграм",
    "Сумма Оффера / отказа",
    "Процент выплаты",
    "Выплата 1",
    "Выплата 2",
    "Выплата 3",
    "Выплата 4",
    "Выплата 5",
    "Выплата 6",
    "Выплата 7",
    "Выплата 8",
    "Суммарно выплачено",
    "Всего задолженность",
}
USER_HASH = "4a9627d3d88cdc261fd59ece53aadfaf74d9f56bca841cc3fd49383671aa8773"
PAYMENT_HASH = "992239558e7e6359c809e7a6ccd5b4838f3cc66810c820228bed23a066d40a93"
LEGACY_IMPORT_NAMESPACE = UUID("b4e13c60-0a0d-4b35-9237-270166e00440")
PAYMENT_IMPORT_NAMESPACE = UUID("f0965be3-e4bc-4591-885a-318823196780")
MENTOR_PAYOUT_IMPORT_NAMESPACE = UUID("337a3916-49fb-48c1-9563-c86120636998")
SNAPSHOT_AT = datetime.fromisoformat("2026-08-11T00:00:00+03:00")
ADMIN_LEGACY_USER_ID = "55"

TELEGRAM_USER_OVERRIDES = {
    "ploxospal1": "2776",
    "nikitamakkar": "134",
    "hellowein": "363",
    "ilnuropt": "287",
}
NAME_USER_OVERRIDES = {
    ("николас", "митрохин", "10000"): "98",
    ("сережа", "", "230000"): "42",
    ("булат", "кайратов", "230000"): "136",
    ("константин", "", "220000"): "88",
}
EXPLICITLY_SKIPPED_ROWS = {
    ("mentor_payouts_oleg_chernikov.csv", "никита", "", "", "10000"),
    ("mentor_payouts_roman_mamin.csv", "владислав", "смирнов", "", "10000"),
}


class ImportedReward(NamedTuple):
    id: UUID
    mentor_id: UUID
    student_id: UUID
    kind: str
    basis_kopecks: int
    reward_percent: Decimal
    amount_kopecks: int
    source_paid_kopecks: int
    source_key: str


def _identity(kind: str, value: str) -> UUID:
    return uuid5(MENTOR_PAYOUT_IMPORT_NAMESPACE, f"{kind}:{value}")


def _legacy_identity(kind: str, value: str) -> UUID:
    return uuid5(LEGACY_IMPORT_NAMESPACE, f"{kind}:{value}")


def _old_payment_identity(kind: str, value: str) -> UUID:
    return uuid5(PAYMENT_IMPORT_NAMESPACE, f"{kind}:{value}")


def _normalize(value: str) -> str:
    return re.sub(r"[^0-9a-zа-я]", "", value.casefold().replace("ё", "е"))


def _decimal(value: str) -> Decimal:
    normalized = (value.strip() or "0").replace(" ", "").replace(",", ".")
    return Decimal(normalized)


def _kopecks(value: Decimal) -> int:
    kopecks = value * 100
    if kopecks != kopecks.to_integral_value():
        raise RuntimeError(f"Mentor payout amount has more than two decimal places: {value}")
    return int(kopecks)


def _read_users() -> list[dict[str, str]]:
    if hashlib.sha256(USER_FILE.read_bytes()).hexdigest() != USER_HASH:
        raise RuntimeError("Legacy user checksum does not match for mentor payout import")
    with USER_FILE.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    if len(rows) != 238:
        raise RuntimeError(f"Expected 238 legacy users, got {len(rows)}")
    return rows


def _read_payout_rows(path: Path) -> list[dict[str, str]]:
    expected_hash, expected_count, _mentor_id = PAYOUT_FILES[path]
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
        raise RuntimeError(f"Mentor payout checksum does not match for {path.name}")
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if set(reader.fieldnames or []) != PAYOUT_FIELDS:
            raise RuntimeError(f"Mentor payout file has unexpected columns: {path.name}")
        rows = list(reader)
    if len(rows) != expected_count:
        raise RuntimeError(f"Expected {expected_count} rows in {path.name}, got {len(rows)}")
    return rows


def _resolve_platform_users(
    connection: sa.Connection, source_users: list[dict[str, str]]
) -> dict[str, UUID]:
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
    for row in source_users:
        if row["role"].strip() == "Гость":
            continue
        telegram_id = row["telegram_id"].strip()
        user_id = existing_by_telegram.get(telegram_id) if telegram_id else None
        user_id = user_id or _legacy_identity("user", row["id"])
        if user_id not in existing_ids:
            raise RuntimeError(f"Legacy user {row['id']} is missing from the platform")
        resolved[row["id"]] = user_id
    return resolved


def _source_user_for_row(
    *,
    path: Path,
    row: dict[str, str],
    users_by_id: dict[str, dict[str, str]],
    users_by_telegram: dict[str, dict[str, str]],
    users_by_name: dict[tuple[str, str], list[dict[str, str]]],
    users_by_first_name: dict[str, list[dict[str, str]]],
) -> dict[str, str] | None:
    first_name = _normalize(row["Имя"])
    last_name = _normalize(row["Фамилия"])
    telegram = _normalize(row["Телеграм"].lstrip("@"))
    basis = row["Сумма Оффера / отказа"].replace(" ", "")
    row_key = (path.name, first_name, last_name, telegram, basis)
    if row_key in EXPLICITLY_SKIPPED_ROWS:
        return None

    source_user_id = TELEGRAM_USER_OVERRIDES.get(telegram) if telegram else None
    source_user_id = source_user_id or NAME_USER_OVERRIDES.get((first_name, last_name, basis))
    if source_user_id:
        return users_by_id[source_user_id]
    if telegram and telegram in users_by_telegram:
        return users_by_telegram[telegram]
    name_matches = users_by_name.get((first_name, last_name), [])
    if len(name_matches) == 1:
        return name_matches[0]
    if not last_name:
        first_name_matches = users_by_first_name.get(first_name, [])
        if len(first_name_matches) == 1:
            return first_name_matches[0]
    raise RuntimeError(
        f"Could not match mentor payout row {path.name}: "
        f"{row['Имя']} {row['Фамилия']} {row['Телеграм']}"
    )


def _rewards_from_file(
    *,
    path: Path,
    rows: list[dict[str, str]],
    mentor_id: UUID,
    platform_users: dict[str, UUID],
    source_users: list[dict[str, str]],
) -> list[ImportedReward]:
    users_by_id = {row["id"]: row for row in source_users}
    users_by_telegram = {
        _normalize(row["telegram_username"].lstrip("@")): row
        for row in source_users
        if _normalize(row["telegram_username"].lstrip("@"))
    }
    users_by_name: dict[tuple[str, str], list[dict[str, str]]] = {}
    users_by_first_name: dict[str, list[dict[str, str]]] = {}
    for user in source_users:
        users_by_name.setdefault(
            (_normalize(user["name"]), _normalize(user["surname"])), []
        ).append(user)
        users_by_first_name.setdefault(_normalize(user["name"]), []).append(user)

    rewards: list[ImportedReward] = []
    for row_number, row in enumerate(rows, start=2):
        if not row["Имя"].strip():
            continue
        source_user = _source_user_for_row(
            path=path,
            row=row,
            users_by_id=users_by_id,
            users_by_telegram=users_by_telegram,
            users_by_name=users_by_name,
            users_by_first_name=users_by_first_name,
        )
        if source_user is None or source_user["role"].strip() == "Гость":
            continue
        student_id = platform_users.get(source_user["id"])
        if student_id is None:
            raise RuntimeError(f"Matched student {source_user['id']} is missing from the platform")

        basis_rubles = _decimal(row["Сумма Оффера / отказа"])
        reward_percent = _decimal(row["Процент выплаты"])
        paid_rubles = _decimal(row["Суммарно выплачено"])
        debt_rubles = _decimal(row["Всего задолженность"])
        payout_parts = sum((_decimal(row[f"Выплата {index}"]) for index in range(1, 9)), Decimal(0))
        entitlement_rubles = basis_rubles * reward_percent / 100
        if payout_parts != paid_rubles:
            raise RuntimeError(f"Payout parts do not match total in {path.name}:{row_number}")
        if paid_rubles + debt_rubles != entitlement_rubles:
            raise RuntimeError(f"Paid and debt do not match reward in {path.name}:{row_number}")

        source_key = f"{path.name}:{row_number}"
        rewards.append(
            ImportedReward(
                id=_identity("reward", source_key),
                mentor_id=mentor_id,
                student_id=student_id,
                kind="legacy_fixed" if basis_rubles <= 10_000 else "employment_payment",
                basis_kopecks=_kopecks(basis_rubles),
                reward_percent=reward_percent,
                amount_kopecks=_kopecks(entitlement_rubles),
                source_paid_kopecks=_kopecks(paid_rubles),
                source_key=source_key,
            )
        )
    return rewards


def _insert_reward(connection: sa.Connection, reward: ImportedReward) -> None:
    connection.execute(
        sa.text(
            """
            INSERT INTO mentor_rewards
                (id, installment_id, student_id, mentor_id, kind,
                 reward_percent, basis_kopecks, amount_kopecks,
                 paid_kopecks, paid_at, created_at, updated_at)
            VALUES
                (:id, NULL, :student_id, :mentor_id,
                 CAST(:kind AS mentor_reward_kind), :reward_percent,
                 :basis_kopecks, :amount_kopecks, 0, NULL,
                 :created_at, :updated_at)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {
            "id": reward.id,
            "student_id": reward.student_id,
            "mentor_id": reward.mentor_id,
            "kind": reward.kind,
            "reward_percent": reward.reward_percent,
            "basis_kopecks": reward.basis_kopecks,
            "amount_kopecks": reward.amount_kopecks,
            "created_at": SNAPSHOT_AT,
            "updated_at": SNAPSHOT_AT,
        },
    )


def _allocation_amounts(rewards: list[ImportedReward]) -> dict[UUID, int]:
    allocations = {
        reward.id: min(reward.source_paid_kopecks, reward.amount_kopecks) for reward in rewards
    }
    surplus = sum(max(reward.source_paid_kopecks - reward.amount_kopecks, 0) for reward in rewards)
    for reward in rewards:
        if surplus == 0:
            break
        available = reward.amount_kopecks - allocations[reward.id]
        allocated = min(available, surplus)
        allocations[reward.id] += allocated
        surplus -= allocated
    if surplus:
        raise RuntimeError("Historical mentor overpayment exceeds the mentor's accrued rewards")
    return {reward_id: amount for reward_id, amount in allocations.items() if amount > 0}


def _insert_aggregate_payout(
    connection: sa.Connection,
    *,
    mentor_legacy_id: str,
    mentor_id: UUID,
    admin_id: UUID,
    rewards: list[ImportedReward],
) -> None:
    allocations = _allocation_amounts(rewards)
    total_paid_kopecks = sum(reward.source_paid_kopecks for reward in rewards)
    if sum(allocations.values()) != total_paid_kopecks:
        raise RuntimeError("Historical mentor payout allocations do not match the paid total")
    if total_paid_kopecks <= 0:
        return
    payout_id = _identity("payout", mentor_legacy_id)
    connection.execute(
        sa.text(
            """
            INSERT INTO mentor_payouts
                (id, mentor_id, requested_by_user_id, amount_kopecks,
                 origin, status, payment_reference, paid_by_user_id,
                 paid_at, created_at, updated_at)
            VALUES
                (:id, :mentor_id, :admin_id, :amount_kopecks,
                 CAST('admin_direct' AS mentor_payout_origin),
                 CAST('paid' AS mentor_payout_status),
                 :payment_reference, :admin_id, :paid_at,
                 :created_at, :updated_at)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {
            "id": payout_id,
            "mentor_id": mentor_id,
            "admin_id": admin_id,
            "amount_kopecks": total_paid_kopecks,
            "payment_reference": "Импорт агрегированной истории выплат на 11.08.2026",
            "paid_at": SNAPSHOT_AT,
            "created_at": SNAPSHOT_AT,
            "updated_at": SNAPSHOT_AT,
        },
    )
    for reward_id, amount_kopecks in allocations.items():
        allocation_id = _identity("allocation", f"{payout_id}:{reward_id}")
        connection.execute(
            sa.text(
                """
                INSERT INTO mentor_payout_allocations
                    (id, payout_id, reward_id, amount_kopecks,
                     created_at, updated_at)
                VALUES
                    (:id, :payout_id, :reward_id, :amount_kopecks,
                     :created_at, :updated_at)
                ON CONFLICT (payout_id, reward_id) DO NOTHING
                """
            ),
            {
                "id": allocation_id,
                "payout_id": payout_id,
                "reward_id": reward_id,
                "amount_kopecks": amount_kopecks,
                "created_at": SNAPSHOT_AT,
                "updated_at": SNAPSHOT_AT,
            },
        )
        connection.execute(
            sa.text(
                """
                UPDATE mentor_rewards
                SET paid_kopecks = :paid_kopecks,
                    paid_at = CASE
                        WHEN :paid_kopecks = amount_kopecks
                            THEN CAST(:paid_at AS timestamptz)
                        ELSE NULL
                    END,
                    updated_at = :updated_at
                WHERE id = :id
                """
            ),
            {
                "id": reward_id,
                "paid_kopecks": amount_kopecks,
                "paid_at": SNAPSHOT_AT,
                "updated_at": SNAPSHOT_AT,
            },
        )


def _remove_inferred_rewards_from_previous_revision(connection: sa.Connection) -> None:
    if hashlib.sha256(PAYMENT_FILE.read_bytes()).hexdigest() != PAYMENT_HASH:
        raise RuntimeError("Legacy payment checksum does not match during mentor payout import")
    with PAYMENT_FILE.open(encoding="utf-8-sig", newline="") as source:
        payment_rows = list(csv.DictReader(source))
    inferred_ids = [
        _old_payment_identity("mentor-reward", row["id"])
        for row in payment_rows
        if row["status"] == "paid"
    ]
    allocated_count = connection.execute(
        sa.text(
            """
            SELECT count(*)
            FROM mentor_payout_allocations
            WHERE reward_id IN :ids
            """
        ).bindparams(sa.bindparam("ids", expanding=True)),
        {"ids": inferred_ids},
    ).scalar_one()
    if allocated_count:
        raise RuntimeError(
            "The inferred mentor rewards from revision 0042 already have payouts; "
            "manual reconciliation is required before importing historical payouts"
        )
    connection.execute(
        sa.text("DELETE FROM mentor_rewards WHERE id IN :ids").bindparams(
            sa.bindparam("ids", expanding=True)
        ),
        {"ids": inferred_ids},
    )


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE mentor_reward_kind ADD VALUE IF NOT EXISTS 'legacy_fixed'")

    connection = op.get_bind()
    source_users = _read_users()
    platform_users = _resolve_platform_users(connection, source_users)
    admin_id = platform_users[ADMIN_LEGACY_USER_ID]
    _remove_inferred_rewards_from_previous_revision(connection)

    imported_rewards: list[ImportedReward] = []
    for path, (_hash, _count, mentor_legacy_id) in PAYOUT_FILES.items():
        mentor_id = platform_users[mentor_legacy_id]
        rewards = _rewards_from_file(
            path=path,
            rows=_read_payout_rows(path),
            mentor_id=mentor_id,
            platform_users=platform_users,
            source_users=source_users,
        )
        imported_rewards.extend(rewards)
        for reward in rewards:
            _insert_reward(connection, reward)
        _insert_aggregate_payout(
            connection,
            mentor_legacy_id=mentor_legacy_id,
            mentor_id=mentor_id,
            admin_id=admin_id,
            rewards=rewards,
        )

    if len(imported_rewards) != 186:
        raise RuntimeError(f"Expected 186 mentor rewards, got {len(imported_rewards)}")
    total_amount = sum(reward.amount_kopecks for reward in imported_rewards)
    total_paid = sum(reward.source_paid_kopecks for reward in imported_rewards)
    if total_amount != 1_137_300_928 or total_paid != 841_107_600:
        raise RuntimeError("Imported mentor payout totals do not match the reconciled source data")


def downgrade() -> None:
    payout_ids = [
        _identity("payout", mentor_legacy_id)
        for _path, (_hash, _count, mentor_legacy_id) in PAYOUT_FILES.items()
    ]
    reward_ids = [
        _identity("reward", f"{path.name}:{row_number}")
        for path in PAYOUT_FILES
        for row_number, row in enumerate(_read_payout_rows(path), start=2)
        if row["Имя"].strip()
    ]
    connection = op.get_bind()
    connection.execute(
        sa.text("DELETE FROM mentor_payouts WHERE id IN :ids").bindparams(
            sa.bindparam("ids", expanding=True)
        ),
        {"ids": payout_ids},
    )
    connection.execute(
        sa.text("DELETE FROM mentor_rewards WHERE id IN :ids").bindparams(
            sa.bindparam("ids", expanding=True)
        ),
        {"ids": reward_ids},
    )
