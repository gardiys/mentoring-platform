"""Store Telegram usernames and backfill the legacy user import."""

from __future__ import annotations

import csv
import hashlib
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID, uuid5

import sqlalchemy as sa
from alembic import op

revision: str = "20260801_0018"
down_revision: str | None = "20260801_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "legacy_users.csv"
DATA_CHECKSUM = "4a9627d3d88cdc261fd59ece53aadfaf74d9f56bca841cc3fd49383671aa8773"
DATA_ROW_COUNT = 238
EXPECTED_FIELDS = {
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
}
IMPORT_NAMESPACE = UUID("b4e13c60-0a0d-4b35-9237-270166e00440")


def _read_rows() -> list[dict[str, str]]:
    if hashlib.sha256(DATA_FILE.read_bytes()).hexdigest() != DATA_CHECKSUM:
        raise RuntimeError("Legacy user import checksum does not match")
    with DATA_FILE.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if set(reader.fieldnames or []) != EXPECTED_FIELDS:
            raise RuntimeError("Legacy user import has unexpected columns")
        rows = list(reader)
    if len(rows) != DATA_ROW_COUNT:
        raise RuntimeError(f"Expected {DATA_ROW_COUNT} legacy users, got {len(rows)}")
    return rows


def _legacy_user_id(legacy_id: str) -> UUID:
    return uuid5(IMPORT_NAMESPACE, f"user:{legacy_id}")


def upgrade() -> None:
    op.add_column("users", sa.Column("telegram_username", sa.String(64), nullable=True))
    connection = op.get_bind()
    for row in _read_rows():
        if row["role"].strip() == "Гость":
            continue
        username = row["telegram_username"].strip().lstrip("@")[:64] or None
        if username is None:
            continue
        telegram_id = row["telegram_id"].strip()
        identity_filter = (
            "id = :legacy_user_id OR telegram_id = :telegram_id"
            if telegram_id
            else "id = :legacy_user_id"
        )
        connection.execute(
            sa.text(
                f"""
                UPDATE users
                SET telegram_username = :username
                WHERE {identity_filter}
                """
            ),
            {
                "username": username,
                "legacy_user_id": _legacy_user_id(row["id"]),
                **({"telegram_id": int(telegram_id)} if telegram_id else {}),
            },
        )
    op.create_index("ix_users_telegram_username", "users", ["telegram_username"])


def downgrade() -> None:
    op.drop_index("ix_users_telegram_username", table_name="users")
    op.drop_column("users", "telegram_username")
