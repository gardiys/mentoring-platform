from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, StudentUser
from app.core.errors import api_error
from app.db.session import get_db_session
from app.users.models import User
from app.users.schemas import UserEmailMutation, UserRead

router = APIRouter(tags=["users"])
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/me", response_model=UserRead)
async def me(current_user: CurrentUser) -> User:
    return current_user


@router.patch("/me/email", response_model=UserRead)
async def update_my_email(
    payload: UserEmailMutation,
    student: StudentUser,
    session: Session,
) -> User:
    owner = await session.scalar(
        select(User.id).where(
            func.lower(User.email) == payload.email,
            User.id != student.id,
        )
    )
    if owner is not None:
        api_error(409, "email_already_used", "Email is already used")
    student.email = payload.email
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        api_error(409, "email_already_used", "Email is already used")
    await session.refresh(student)
    return student


@router.post("/me/onboarding", response_model=UserRead)
async def complete_onboarding(current_user: CurrentUser, session: Session) -> User:
    if current_user.onboarding_completed_at is None:
        current_user.onboarding_completed_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(current_user)
    return current_user
