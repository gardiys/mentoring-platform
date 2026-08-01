import subprocess
import sys

from sqlalchemy import select

from app.bootstrap_admin import bootstrap_admin_user
from app.users.models import User, UserRole
from tests.conftest import TestSession


def test_bootstrap_admin_registers_all_sqlalchemy_models_in_clean_process() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from sqlalchemy.orm import configure_mappers; "
                "import app.bootstrap_admin; "
                "configure_mappers()"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


async def test_bootstrap_admin_creates_and_idempotently_updates_user() -> None:
    telegram_id = 987654321
    async with TestSession() as session:
        user_id = await bootstrap_admin_user(
            session, telegram_id, first_name="Антон"
        )
        repeated_id = await bootstrap_admin_user(
            session,
            telegram_id,
            first_name="Anton",
            last_name="Admin",
        )
        user = await session.scalar(select(User).where(User.telegram_id == telegram_id))

    assert user is not None
    assert repeated_id == user_id == user.id
    assert user.role is UserRole.ADMIN
    assert user.first_name == "Anton"
    assert user.last_name == "Admin"
    assert user.onboarding_completed_at is not None
