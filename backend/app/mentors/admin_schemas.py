from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AdminMentorMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    telegram_id: int = Field(gt=0)
    telegram_username: str | None = Field(default=None, max_length=64)
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=320)
    track_ids: list[UUID] = Field(min_length=1)

    @field_validator("telegram_username")
    @classmethod
    def normalize_telegram_username(cls, value: str | None) -> str | None:
        return value.lstrip("@").strip() or None if value else None


class AdminMentorListItem(BaseModel):
    id: UUID
    telegram_id: int | None
    telegram_username: str | None
    first_name: str
    last_name: str | None
    email: str | None
    is_active: bool
    student_count: int
    tracks: list["AdminMentorTrackRead"]
    students: list["AdminMentorStudentRead"]
    created_at: datetime


class AdminMentorCandidate(BaseModel):
    id: UUID
    telegram_id: int | None
    telegram_username: str | None
    first_name: str
    last_name: str | None
    email: str | None


class AdminMentorTrackRead(BaseModel):
    id: UUID
    slug: str
    title: str


class AdminMentorStudentRead(BaseModel):
    id: UUID
    first_name: str
    last_name: str | None
    telegram_username: str | None


class AdminMentorDirectionsMutation(BaseModel):
    track_ids: list[UUID] = Field(min_length=1)


class AdminStudentMentorMutation(BaseModel):
    mentor_id: UUID
