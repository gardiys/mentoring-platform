from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.roadmaps.admin_schemas import SLUG_PATTERN


class AdminTrackMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    slug: str = Field(min_length=1, max_length=160, pattern=SLUG_PATTERN)
    title: str = Field(min_length=1, max_length=240)
    description: str | None = None
    position: int = Field(default=0, ge=0)
    is_published: bool = False
    roadmap_ids: list[UUID] = Field(default_factory=list)

    @field_validator("roadmap_ids")
    @classmethod
    def unique_roadmaps(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("Roadmap IDs must be unique")
        return value


class AdminTrackRoadmapRead(BaseModel):
    id: UUID
    slug: str
    title: str
    is_published: bool
    position: int


class AdminTrackRead(BaseModel):
    id: UUID
    slug: str
    title: str
    description: str | None
    position: int
    is_published: bool
    roadmaps: list[AdminTrackRoadmapRead]
    student_ids: list[UUID]


class AdminTrackStudentOption(BaseModel):
    id: UUID
    first_name: str
    last_name: str | None
    email: str | None
    telegram_id: int | None


class AdminTrackOptions(BaseModel):
    roadmaps: list[AdminTrackRoadmapRead]
    students: list[AdminTrackStudentOption]


class TrackAccessRead(BaseModel):
    track_id: UUID
    student_id: UUID
    granted: bool
