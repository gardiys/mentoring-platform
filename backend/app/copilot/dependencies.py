"""Material access keeps documents scoped to the authenticated account."""

from typing import Annotated

from fastapi import Depends

from app.auth.dependencies import CurrentUser
from app.core.errors import forbidden
from app.users.models import User, UserRole


async def material_user(user: CurrentUser) -> User:
    if not user.is_active or user.role not in {UserRole.STUDENT, UserRole.ADMIN}:
        forbidden("An active student or admin account is required")
    return user


CopilotMaterialUser = Annotated[User, Depends(material_user)]
