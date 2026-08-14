import csv
import hashlib
import importlib.util
import re
from collections import Counter
from pathlib import Path
from types import ModuleType
from uuid import UUID

import pytest

from app.db.models import User
from app.users.models import UserRole
from tests.conftest import SeededData, TestSession, test_engine

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BACKEND_DIR / "migrations" / "data" / "application_student_profiles.csv"
MIGRATION_FILE = (
    BACKEND_DIR
    / "migrations"
    / "versions"
    / "20260815_0054_refresh_application_student_profiles.py"
)
DATA_CHECKSUM = "b3d7e99c8c8db74490f16dd879a6b4261224d3a391ff1a83e235fdf79451430b"
TELEGRAM_USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")


def _migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("refresh_application_profiles", MIGRATION_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _profiles() -> list[dict[str, str]]:
    with DATA_FILE.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def test_application_profile_source_is_sanitized_and_consistent() -> None:
    assert hashlib.sha256(DATA_FILE.read_bytes()).hexdigest() == DATA_CHECKSUM
    rows = _profiles()

    assert len(rows) == 19
    assert set(rows[0]) == {
        "source_user_id",
        "application_status",
        "first_name",
        "last_name",
        "email",
        "telegram_username",
        "telegram_id",
    }
    assert Counter(row["application_status"] for row in rows) == {
        "ACTIVE_STUDENT": 8,
        "ONBOARDING_COMPLETED": 9,
        "PAYMENT_PENDING": 2,
    }
    assert all(row["first_name"] and row["last_name"] for row in rows)
    assert all("@" in row["email"] for row in rows)
    assert len({UUID(row["source_user_id"]) for row in rows}) == len(rows)
    assert len({row["email"].casefold() for row in rows}) == len(rows)
    usernames = [row["telegram_username"] for row in rows if row["telegram_username"]]
    assert len(usernames) == 18
    assert all(TELEGRAM_USERNAME_PATTERN.fullmatch(username) for username in usernames)
    assert [row["telegram_id"] for row in rows if row["telegram_id"]] == ["1893126228"]
    assert _migration()._read_profiles() == rows


@pytest.mark.asyncio
async def test_application_profile_updates_existing_student_by_contact(
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
async def test_numeric_telegram_value_only_fills_an_empty_telegram_id() -> None:
    migration = _migration()
    profile = next(row for row in _profiles() if row["telegram_id"])
    source_user_id = UUID(profile["source_user_id"])
    async with TestSession() as session:
        session.add(
            User(
                id=source_user_id,
                first_name="Устаревшее имя",
                role=UserRole.STUDENT,
            )
        )
        await session.commit()

    async with test_engine.begin() as connection:
        result = await connection.run_sync(
            lambda sync_connection: migration._apply_profiles(sync_connection, [profile])
        )

    assert result == {"updated": 1, "unmatched": 0, "non_students": 0}
    async with TestSession() as session:
        student = await session.get(User, source_user_id)
        assert student is not None
        assert student.telegram_id == int(profile["telegram_id"])
        assert student.telegram_username is None


@pytest.mark.asyncio
async def test_application_profile_rejects_cross_account_matches(
    seeded: SeededData,
) -> None:
    migration = _migration()
    profile = dict(next(row for row in _profiles() if row["telegram_username"]))
    profile["source_user_id"] = str(seeded.student_id)
    profile["email"] = "mentor-conflict@example.com"
    async with TestSession() as session:
        mentor = await session.get(User, seeded.mentor_id)
        assert mentor is not None
        mentor.email = profile["email"]
        await session.commit()

    async with test_engine.begin() as connection:
        with pytest.raises(RuntimeError, match="match multiple platform accounts"):
            await connection.run_sync(
                lambda sync_connection: migration._apply_profiles(sync_connection, [profile])
            )
