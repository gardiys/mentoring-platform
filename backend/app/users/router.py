from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.db.session import get_db_session
from app.users.models import User
from app.users.schemas import UserRead

router = APIRouter(tags=["users"])
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/me", response_model=UserRead)
async def me(current_user: CurrentUser) -> User:
    return current_user


@router.post("/me/onboarding", response_model=UserRead)
async def complete_onboarding(current_user: CurrentUser, session: Session) -> User:
    if current_user.onboarding_completed_at is None:
        current_user.onboarding_completed_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(current_user)
    return current_user
