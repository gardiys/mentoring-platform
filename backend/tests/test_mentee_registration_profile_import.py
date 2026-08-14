import csv
import hashlib
import importlib.util
import re
from pathlib import Path
from types import ModuleType
from uuid import UUID

import pytest

from app.db.models import User
from tests.conftest import SeededData, TestSession, test_engine

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BACKEND_DIR / "migrations" / "data" / "mentee_registration_profiles.csv"
MIGRATION_FILE = (
    BACKEND_DIR / "migrations" / "versions" / "20260815_0053_refresh_student_profiles.py"
)
DATA_CHECKSUM = "181de9c23f170d081468a1a65e0bd35c9e9ea5ba1a39bdc09854f42247f42f2c"
TELEGRAM_USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")


def _migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("refresh_student_profiles", MIGRATION_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _profiles() -> list[dict[str, str]]:
    with DATA_FILE.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def test_registration_profile_source_is_sanitized_and_consistent() -> None:
    assert hashlib.sha256(DATA_FILE.read_bytes()).hexdigest() == DATA_CHECKSUM
    rows = _profiles()

    assert len(rows) == 149
    assert set(rows[0]) == {
        "legacy_user_id",
        "first_name",
        "last_name",
        "email",
        "telegram_username",
    }
    assert all(row["first_name"] and row["last_name"] for row in rows)
    assert all(row["first_name"] == row["first_name"].title() for row in rows)
    assert all(row["last_name"] == row["last_name"].title() for row in rows)
    assert all("@" in row["email"] for row in rows)
    assert len({row["email"].casefold() for row in rows}) == len(rows)
    usernames = [row["telegram_username"] for row in rows if row["telegram_username"]]
    assert len(usernames) == 148
    assert len({username.casefold() for username in usernames}) == len(usernames)
    assert all(TELEGRAM_USERNAME_PATTERN.fullmatch(username) for username in usernames)
    legacy_user_ids = [UUID(row["legacy_user_id"]) for row in rows if row["legacy_user_id"]]
    assert len(legacy_user_ids) == 135
    assert len(set(legacy_user_ids)) == len(legacy_user_ids)
    assert _migration()._read_profiles() == rows


@pytest.mark.asyncio
async def test_registration_profile_updates_an_existing_student(
    seeded: SeededData,
) -> None:
    migration = _migration()
    profile = next(row for row in _profiles() if row["telegram_username"])
    async with TestSession() as session:
        student = await session.get(User, seeded.student_id)
        assert student is not None
        student.first_name = "Устаревшее имя"
        student.last_name = None
        student.email = None
        student.telegram_username = profile["telegram_username"]
        await session.commit()

    async with test_engine.begin() as connection:
        result = await connection.run_sync(
            lambda sync_connection: migration._apply_profiles(sync_connection, [profile])
        )

    assert result == {"updated": 1, "unmatched": 0, "non_students": 0}
    async with TestSession() as session:
        student = await session.get(User, seeded.student_id)
        assert student is not None
        assert student.first_name == profile["first_name"]
        assert student.last_name == profile["last_name"]
        assert student.email == profile["email"]
        assert student.telegram_username == profile["telegram_username"]


@pytest.mark.asyncio
async def test_registration_profile_rejects_cross_account_matches(
    seeded: SeededData,
) -> None:
    migration = _migration()
    profile = next(row for row in _profiles() if row["telegram_username"])
    async with TestSession() as session:
        student = await session.get(User, seeded.student_id)
        mentor = await session.get(User, seeded.mentor_id)
        assert student is not None and mentor is not None
        student.telegram_username = profile["telegram_username"]
        mentor.email = profile["email"]
        await session.commit()

    async with test_engine.begin() as connection:
        with pytest.raises(RuntimeError, match="match multiple platform accounts"):
            await connection.run_sync(
                lambda sync_connection: migration._apply_profiles(sync_connection, [profile])
            )
