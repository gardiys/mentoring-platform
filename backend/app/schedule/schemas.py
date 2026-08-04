from datetime import UTC, datetime, time
from enum import StrEnum
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.schedule.models import ScheduleEventKind


def _future_aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("starts_at must include a timezone")
    try:
        normalized = value.astimezone(UTC)
    except (OverflowError, ValueError) as error:
        raise ValueError("starts_at is outside the supported datetime range") from error
    if normalized <= datetime.now(UTC):
        raise ValueError("starts_at must be in the future")
    return normalized


class ScheduleEventSource(StrEnum):
    MENTOR = "mentor"
    PLATFORM = "platform"


class MentorProfileMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    consultation_url: AnyHttpUrl | None = Field(default=None, max_length=2_048)
    group_calendar_url: AnyHttpUrl | None = Field(default=None, max_length=2_048)


class MentorWeeklyCallMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    track_id: UUID
    title: str = Field(default="Групповой созвон", min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=5_000)
    weekday: int = Field(ge=0, le=6)
    starts_at_time: time | None = None
    timezone: str = Field(default="Europe/Moscow", min_length=1, max_length=64)
    meeting_url: AnyHttpUrl = Field(max_length=2_048)

    @field_validator("starts_at_time")
    @classmethod
    def local_time_must_not_have_timezone(cls, value: time | None) -> time | None:
        if value is not None and value.tzinfo is not None:
            raise ValueError("starts_at_time must be a local time without timezone")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("Unknown IANA timezone") from error
        return value


class MentorMeetingMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    track_id: UUID
    title: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=5_000)
    meeting_url: AnyHttpUrl | None = Field(default=None, max_length=2_048)
    starts_at: datetime

    @field_validator("starts_at")
    @classmethod
    def future_aware_starts_at(cls, value: datetime) -> datetime:
        return _future_aware_datetime(value)


class MentorWeeklyCallRescheduleMutation(BaseModel):
    starts_at: datetime

    @field_validator("starts_at")
    @classmethod
    def future_aware_starts_at(cls, value: datetime) -> datetime:
        return _future_aware_datetime(value)


class ScheduleTrackRead(BaseModel):
    id: UUID
    slug: str
    title: str


class ScheduleEventRead(BaseModel):
    id: UUID
    track: ScheduleTrackRead
    mentor_id: UUID | None
    source: ScheduleEventSource
    source_name: str
    kind: ScheduleEventKind
    title: str
    description: str | None
    meeting_url: str | None
    weekday: int | None
    starts_at_time: time | None
    timezone: str | None
    starts_at: datetime | None
    regular_next_occurrence_at: datetime | None
    next_occurrence_at: datetime | None
    is_rescheduled: bool
    rescheduled_from: datetime | None
    rescheduled_to: datetime | None
    created_at: datetime
    updated_at: datetime


class MentorProfileRead(BaseModel):
    mentor_id: UUID
    consultation_url: str | None
    group_calendar_url: str | None
    tracks: list[ScheduleTrackRead]
    weekly_calls: list[ScheduleEventRead]
    one_off_activities: list[ScheduleEventRead]
    updated_at: datetime | None


class AdminScheduleEventMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    track_id: UUID
    kind: ScheduleEventKind
    title: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=5_000)
    meeting_url: AnyHttpUrl | None = Field(default=None, max_length=2_048)
    weekday: int | None = Field(default=None, ge=0, le=6)
    starts_at_time: time | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    starts_at: datetime | None = None

    @field_validator("starts_at_time")
    @classmethod
    def local_time_must_not_have_timezone(cls, value: time | None) -> time | None:
        if value is not None and value.tzinfo is not None:
            raise ValueError("starts_at_time must be a local time without timezone")
        return value

    @model_validator(mode="after")
    def validate_schedule(self) -> "AdminScheduleEventMutation":
        if self.kind is ScheduleEventKind.WEEKLY_CALL:
            if self.weekday is None or self.starts_at is not None:
                raise ValueError("Weekly calls require weekday and must not contain starts_at")
            self.timezone = self.timezone or "Europe/Moscow"
            try:
                ZoneInfo(self.timezone)
            except ZoneInfoNotFoundError as error:
                raise ValueError("Unknown IANA timezone") from error
        elif (
            self.weekday is not None
            or self.starts_at_time is not None
            or self.timezone is not None
            or self.starts_at is None
        ):
            raise ValueError(
                "Meetings require starts_at and must not contain weekly schedule fields"
            )
        if self.starts_at is not None and self.starts_at.tzinfo is None:
            raise ValueError("starts_at must include a timezone")
        return self


class MyMentorPublicRead(BaseModel):
    id: UUID
    first_name: str
    last_name: str | None
    telegram_username: str | None
    consultation_url: str | None
    group_calendar_url: str | None


class PinnedResourceLinkMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=5_000)
    url: AnyHttpUrl = Field(max_length=2_048)
    position: int = Field(default=0, ge=0, le=2_147_483_647)


class PinnedResourceLinkRead(BaseModel):
    id: UUID
    title: str
    description: str | None
    url: str
    position: int
    created_at: datetime
    updated_at: datetime


class MyMentorDashboardRead(BaseModel):
    mentor: MyMentorPublicRead | None
    schedule: list[ScheduleEventRead]
    useful_links: list[PinnedResourceLinkRead]


class AdminScheduleEventPageRead(BaseModel):
    items: list[ScheduleEventRead]
    total: int
    limit: int
    offset: int
