from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ContentMediaKind(StrEnum):
    AUDIO = "audio"
    VIDEO = "video"


class ContentMediaUploadRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    filename: str = Field(min_length=1, max_length=500)
    content_type: str = Field(min_length=1, max_length=160)
    size: int = Field(gt=0)


class ContentMediaUploadIntent(BaseModel):
    upload_url: str
    fields: dict[str, str]
    storage_key: str
    filename: str
    content_type: str
    size: int
    expires_in: int


class ContentMediaUploadFinalize(ContentMediaUploadRequest):
    storage_key: str = Field(min_length=1, max_length=500)
    title: str | None = Field(default=None, max_length=240)
    position: int = Field(default=0, ge=0, le=2_147_483_647)


class ProtectedContentMediaRead(BaseModel):
    id: UUID
    kind: ContentMediaKind
    filename: str
    content_type: str
    size: int
    title: str | None
    position: int
    created_at: datetime


class ContentMediaPlayback(BaseModel):
    url: str
    expires_in: int
