from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.roadmaps.admin_schemas import SLUG_PATTERN
from app.users.schemas import UserRead


class ProvisionTelegramStudentRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    telegram_id: int = Field(gt=0)
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=320)
    track_slug: str = Field(min_length=1, max_length=160, pattern=SLUG_PATTERN)


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
