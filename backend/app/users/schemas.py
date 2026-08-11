import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.users.models import UserRole

_EMAIL_PATTERN = re.compile(r"\A[^@\s]+@[^@\s]+\.[^@\s]+\Z")


class UserEmailMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: str = Field(min_length=5, max_length=320)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        normalized = value.lower()
        if _EMAIL_PATTERN.fullmatch(normalized) is None:
            raise ValueError("A valid email is required")
        return normalized


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str
    last_name: str | None
    role: UserRole
    email: str | None
    telegram_id: int | None
    onboarding_completed_at: datetime | None
    is_active: bool
