import argparse
import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, UserRole
from app.db.session import async_session_factory


async def bootstrap_admin_user(
    session: AsyncSession,
    telegram_id: int,
    *,
    first_name: str,
    last_name: str | None = None,
) -> UUID:
    user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None:
        user = User(
            telegram_id=telegram_id,
            first_name=first_name,
            last_name=last_name,
            role=UserRole.ADMIN,
        )
        session.add(user)
    else:
        user.first_name = first_name
        user.last_name = last_name
        user.role = UserRole.ADMIN
    user.onboarding_completed_at = user.onboarding_completed_at or datetime.now(UTC)
    await session.commit()
    await session.refresh(user)
    return user.id


async def bootstrap_admin(
    telegram_id: int,
    *,
    first_name: str,
    last_name: str | None = None,
) -> UUID:
    async with async_session_factory() as session:
        return await bootstrap_admin_user(
            session,
            telegram_id,
            first_name=first_name,
            last_name=last_name,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or promote a Telegram user to platform administrator"
    )
    parser.add_argument("--telegram-id", type=int, required=True)
    parser.add_argument("--first-name", default="Администратор")
    parser.add_argument("--last-name", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.telegram_id <= 0:
        raise SystemExit("--telegram-id must be a positive integer")
    user_id = asyncio.run(
        bootstrap_admin(
            args.telegram_id,
            first_name=args.first_name,
            last_name=args.last_name,
        )
    )
    print(f"Administrator is ready: user_id={user_id}, telegram_id={args.telegram_id}")


if __name__ == "__main__":
    main()
