from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.mentors.models import StudentLearningStatus
from app.users.models import UserRole
from app.users.telegram import normalize_telegram_username


class AdminStudentMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    telegram_id: int = Field(gt=0)
    telegram_username: str | None = Field(default=None, max_length=32)
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=320)
    learning_start_date: date | None = None
    mentor_id: UUID | None = None
    track_ids: list[UUID] = Field(default_factory=list)

    @field_validator("telegram_username", mode="before")
    @classmethod
    def valid_telegram_username(cls, value: object) -> object:
        return normalize_telegram_username(value) if isinstance(value, str) else value

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
    role: UserRole
    first_name: str
    last_name: str | None
    telegram_username: str | None


class AdminStudentListItem(BaseModel):
    id: UUID
    telegram_id: int | None
    telegram_username: str | None
    first_name: str
    last_name: str | None
    email: str | None
    is_active: bool
    learning_status: StudentLearningStatus
    created_at: datetime
    learning_start_date: date | None
    mentor: AdminStudentMentorRead | None
    tracks: list[AdminStudentTrackRead]
    last_progress_at: datetime | None


class AdminStudentDetail(AdminStudentListItem):
    updated_at: datetime
    onboarding_completed_at: datetime | None


class AdminStudentTrackOption(BaseModel):
    id: UUID
    slug: str
    title: str
    is_published: bool


class AdminStudentPage(BaseModel):
    items: list[AdminStudentListItem]
    total: int
    limit: int
    offset: int
    mentors: list[AdminStudentMentorRead] = Field(default_factory=list)
    tracks: list[AdminStudentTrackOption] = Field(default_factory=list)


class AdminStudentOptions(BaseModel):
    tracks: list[AdminStudentTrackOption]
    mentors: list[AdminStudentMentorRead]


class AdminStudentAccessMutation(BaseModel):
    is_active: bool
