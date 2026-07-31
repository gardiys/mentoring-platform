from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.users.models import UserRole


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str
    last_name: str | None
    role: UserRole
    email: str | None
    telegram_id: int | None
    onboarding_completed_at: datetime | None
