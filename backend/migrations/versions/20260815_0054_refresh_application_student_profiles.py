"""Refresh student contacts from completed onboarding applications.

Revision ID: 20260815_0054
Revises: 20260815_0053
"""

from __future__ import annotations

import csv
import hashlib
import logging
import re
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "20260815_0054"
down_revision: str | None = "20260815_0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "application_student_profiles.csv"
DATA_CHECKSUM = "b3d7e99c8c8db74490f16dd879a6b4261224d3a391ff1a83e235fdf79451430b"
DATA_ROW_COUNT = 19
EXPECTED_FIELDS = {
    "source_user_id",
    "application_status",
    "first_name",
    "last_name",
    "email",
    "telegram_username",
    "telegram_id",
}
ALLOWED_APPLICATION_STATUSES = {
    "ACTIVE_STUDENT",
    "ONBOARDING_COMPLETED",
    "PAYMENT_PENDING",
}
TELEGRAM_USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

logger = logging.getLogger("alembic.runtime.migration")


def _normalized_email(value: str | None) -> str:
    return (value or "").strip().casefold()


def _normalized_username(value: str | None) -> str:
    username = (value or "").strip()
    username = re.sub(
        r"^https?://(?:www\.)?(?:t\.me|telegram\.me)/",
        "",
        username,
        flags=re.IGNORECASE,
    )
    return username.split("?", 1)[0].split("/", 1)[0].strip().lstrip("@").casefold()


def _read_profiles() -> list[dict[str, str]]:
    raw_data = DATA_FILE.read_bytes()
    if hashlib.sha256(raw_data).hexdigest() != DATA_CHECKSUM:
        raise RuntimeError("Application student profile checksum does not match")
    with DATA_FILE.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if set(reader.fieldnames or []) != EXPECTED_FIELDS:
            raise RuntimeError("Application student profile columns do not match")
        rows = list(reader)
    if len(rows) != DATA_ROW_COUNT:
        raise RuntimeError(f"Expected {DATA_ROW_COUNT} application profiles, got {len(rows)}")

    source_user_ids: set[UUID] = set()
    emails: set[str] = set()
    usernames: set[str] = set()
    telegram_ids: set[int] = set()
    for row_number, row in enumerate(rows, start=2):
        try:
            source_user_id = UUID(row["source_user_id"].strip())
        except ValueError as error:
            raise RuntimeError(f"Invalid source user id in application row {row_number}") from error
        first_name = row["first_name"].strip()
        last_name = row["last_name"].strip()
        email = _normalized_email(row["email"])
        username = row["telegram_username"].strip()
        telegram_id_value = row["telegram_id"].strip()
        if row["application_status"] not in ALLOWED_APPLICATION_STATUSES:
            raise RuntimeError(f"Invalid status in application row {row_number}")
        if not first_name or len(first_name) > 120:
            raise RuntimeError(f"Invalid first name in application row {row_number}")
        if not last_name or len(last_name) > 120:
            raise RuntimeError(f"Invalid last name in application row {row_number}")
        if len(email) > 320 or not EMAIL_PATTERN.fullmatch(email):
            raise RuntimeError(f"Invalid email in application row {row_number}")
        if username and not TELEGRAM_USERNAME_PATTERN.fullmatch(username):
            raise RuntimeError(f"Invalid Telegram username in application row {row_number}")
        telegram_id = None
        if telegram_id_value:
            try:
                telegram_id = int(telegram_id_value)
            except ValueError as error:
                raise RuntimeError(
                    f"Invalid Telegram id in application row {row_number}"
                ) from error
            if telegram_id <= 0 or telegram_id > 9_223_372_036_854_775_807:
                raise RuntimeError(f"Invalid Telegram id in application row {row_number}")
        normalized_username = _normalized_username(username)
        if source_user_id in source_user_ids:
            raise RuntimeError(f"Duplicate source user id in application row {row_number}")
        if email in emails:
            raise RuntimeError(f"Duplicate email in application row {row_number}")
        if normalized_username and normalized_username in usernames:
            raise RuntimeError(f"Duplicate Telegram username in application row {row_number}")
        if telegram_id is not None and telegram_id in telegram_ids:
            raise RuntimeError(f"Duplicate Telegram id in application row {row_number}")
        source_user_ids.add(source_user_id)
        emails.add(email)
        if normalized_username:
            usernames.add(normalized_username)
        if telegram_id is not None:
            telegram_ids.add(telegram_id)
    return rows


def _apply_profiles(connection: sa.Connection, profiles: list[dict[str, str]]) -> dict[str, int]:
    users = list(
        connection.execute(
            sa.text(
                """
                SELECT id, role, email, telegram_username, telegram_id
                FROM users
                """
            )
        ).mappings()
    )
    users_by_id = {user["id"]: user for user in users}
    user_ids_by_email: defaultdict[str, set[Any]] = defaultdict(set)
    user_ids_by_username: defaultdict[str, set[Any]] = defaultdict(set)
    user_ids_by_telegram_id: defaultdict[int, set[Any]] = defaultdict(set)
    for user in users:
        email = _normalized_email(user["email"])
        username = _normalized_username(user["telegram_username"])
        if email:
            user_ids_by_email[email].add(user["id"])
        if username:
            user_ids_by_username[username].add(user["id"])
        if user["telegram_id"] is not None:
            user_ids_by_telegram_id[int(user["telegram_id"])].add(user["id"])

    updates: list[tuple[Any, dict[str, str]]] = []
    profile_by_user_id: dict[Any, int] = {}
    unmatched = 0
    non_students = 0
    ambiguous_rows: list[int] = []
    for row_number, profile in enumerate(profiles, start=2):
        source_user_id = UUID(profile["source_user_id"].strip())
        email = _normalized_email(profile["email"])
        username = _normalized_username(profile["telegram_username"])
        telegram_id_value = profile["telegram_id"].strip()
        telegram_id = int(telegram_id_value) if telegram_id_value else None
        candidate_ids = set(user_ids_by_email[email])
        if source_user_id in users_by_id:
            candidate_ids.add(source_user_id)
        if username:
            candidate_ids.update(user_ids_by_username[username])
        if telegram_id is not None:
            candidate_ids.update(user_ids_by_telegram_id[telegram_id])
        if not candidate_ids:
            unmatched += 1
            continue
        if len(candidate_ids) != 1:
            ambiguous_rows.append(row_number)
            continue

        user_id = candidate_ids.pop()
        previous_row = profile_by_user_id.get(user_id)
        if previous_row is not None:
            ambiguous_rows.extend((previous_row, row_number))
            continue
        profile_by_user_id[user_id] = row_number
        if users_by_id[user_id]["role"] != "student":
            non_students += 1
            continue
        updates.append((user_id, profile))

    if ambiguous_rows:
        rows = ", ".join(str(row) for row in sorted(set(ambiguous_rows)))
        raise RuntimeError(
            "Application profiles match multiple platform accounts; "
            f"resolve source rows before migration: {rows}"
        )

    for user_id, profile in updates:
        username = profile["telegram_username"].strip() or None
        telegram_id_value = profile["telegram_id"].strip()
        telegram_id = int(telegram_id_value) if telegram_id_value else None
        connection.execute(
            sa.text(
                """
                UPDATE users
                SET first_name = :first_name,
                    last_name = :last_name,
                    email = :email,
                    telegram_username = COALESCE(
                        CAST(:telegram_username AS VARCHAR(64)), telegram_username
                    ),
                    telegram_id = COALESCE(telegram_id, CAST(:telegram_id AS BIGINT)),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :user_id AND role = 'student'
                """
            ),
            {
                "user_id": user_id,
                "first_name": profile["first_name"].strip(),
                "last_name": profile["last_name"].strip(),
                "email": _normalized_email(profile["email"]),
                "telegram_username": username,
                "telegram_id": telegram_id,
            },
        )

    return {
        "updated": len(updates),
        "unmatched": unmatched,
        "non_students": non_students,
    }


def upgrade() -> None:
    result = _apply_profiles(op.get_bind(), _read_profiles())
    logger.info(
        "Application student profiles processed: updated=%d unmatched=%d non_students=%d",
        result["updated"],
        result["unmatched"],
        result["non_students"],
    )


def downgrade() -> None:
    # Previous personal data cannot be reconstructed from an authoritative source.
    pass
