from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.roadmaps.admin_schemas import SLUG_PATTERN
from app.users.schemas import UserRead


class ProvisionTelegramStudentRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    telegram_id: int = Field(gt=0)
    telegram_username: str | None = Field(default=None, max_length=64)
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=320)
    track_slug: str = Field(min_length=1, max_length=160, pattern=SLUG_PATTERN)
    mentor_telegram_id: int | None = Field(default=None, gt=0)
    repayment_percent: Decimal | None = Field(default=None, gt=0, le=1000, decimal_places=2)
    mentor_reward_percent: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=2)
    entry_payment_rubles: Decimal = Field(
        default=Decimal("45000"), ge=0, max_digits=12, decimal_places=2
    )
    entry_payment_paid: bool = True


class GrantedTrackRead(BaseModel):
    id: UUID
    slug: str
    title: str


class GrantedRoadmapRead(BaseModel):
    id: UUID
    slug: str
    title: str


class ProvisionTelegramStudentResponse(BaseModel):
    created: bool
    access_created: bool
    user: UserRead
    track: GrantedTrackRead
    roadmaps: list[GrantedRoadmapRead]
