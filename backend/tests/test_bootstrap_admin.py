from sqlalchemy import select

from app.bootstrap_admin import bootstrap_admin_user
from app.users.models import User, UserRole
from tests.conftest import TestSession


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
