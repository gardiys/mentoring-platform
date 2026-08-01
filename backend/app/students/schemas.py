from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AdminStudentMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    telegram_id: int = Field(gt=0)
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=320)
    learning_start_date: date | None = None
    mentor_id: UUID | None = None
    track_ids: list[UUID] = Field(default_factory=list)

    @field_validator("track_ids")
    @classmethod
    def unique_tracks(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("Track IDs must be unique")
        return value


class AdminStudentTrackRead(BaseModel):
    id: UUID
    slug: str
    title: str
    is_published: bool
    granted_at: datetime


class AdminStudentMentorRead(BaseModel):
    id: UUID
    first_name: str
    last_name: str | None
    telegram_username: str | None


class AdminStudentListItem(BaseModel):
    id: UUID
    telegram_id: int | None
    first_name: str
    last_name: str | None
    email: str | None
    is_active: bool
    created_at: datetime
    learning_start_date: date | None
    mentor: AdminStudentMentorRead | None
    tracks: list[AdminStudentTrackRead]
    last_progress_at: datetime | None


class AdminStudentDetail(AdminStudentListItem):
    updated_at: datetime
    onboarding_completed_at: datetime | None


class AdminStudentPage(BaseModel):
    items: list[AdminStudentListItem]
    total: int
    limit: int
    offset: int
    mentors: list[AdminStudentMentorRead] = Field(default_factory=list)


class AdminStudentTrackOption(BaseModel):
    id: UUID
    slug: str
    title: str
    is_published: bool


class AdminStudentOptions(BaseModel):
    tracks: list[AdminStudentTrackOption]
    mentors: list[AdminStudentMentorRead]


class AdminStudentAccessMutation(BaseModel):
    is_active: bool
