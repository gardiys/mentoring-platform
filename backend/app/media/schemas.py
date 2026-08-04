from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContentMediaKind(StrEnum):
    AUDIO = "audio"
    VIDEO = "video"


class ContentMediaUploadProtocol(StrEnum):
    LEGACY_POST = "legacy-post"
    MULTIPART_V1 = "multipart-v1"


class ContentMediaUploadRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    filename: str = Field(min_length=1, max_length=500)
    content_type: str = Field(min_length=1, max_length=160)
    size: int = Field(gt=0)
    upload_protocol: ContentMediaUploadProtocol = ContentMediaUploadProtocol.LEGACY_POST


class ContentMediaUploadIntent(BaseModel):
    upload_url: str
    fields: dict[str, str]
    storage_key: str
    filename: str
    content_type: str
    size: int
    expires_in: int


class ContentMediaMultipartUploadPartIntent(BaseModel):
    part_number: int = Field(ge=1, le=10_000)
    upload_url: str
    headers: dict[str, str]


class ContentMediaMultipartUploadIntent(BaseModel):
    upload_protocol: Literal["multipart-v1"]
    upload_id: str
    upload_token: str
    abort_url: str
    storage_key: str
    filename: str
    content_type: str
    size: int
    part_size: int
    part_count: int
    parts: list[ContentMediaMultipartUploadPartIntent]
    expires_in: int


class ContentMediaCompletedMultipartPart(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    part_number: int = Field(ge=1, le=10_000)
    etag: str = Field(min_length=1, max_length=200)


class ContentMediaUploadFinalize(ContentMediaUploadRequest):
    storage_key: str = Field(min_length=1, max_length=500)
    upload_id: str | None = Field(default=None, min_length=1, max_length=1_000)
    upload_token: str | None = Field(default=None, min_length=1, max_length=8_192)
    parts: list[ContentMediaCompletedMultipartPart] = Field(
        default_factory=list,
        max_length=10_000,
    )
    title: str | None = Field(default=None, max_length=240)
    position: int = Field(default=0, ge=0, le=2_147_483_647)

    @model_validator(mode="after")
    def validate_upload_protocol_fields(self) -> "ContentMediaUploadFinalize":
        if self.upload_protocol is ContentMediaUploadProtocol.MULTIPART_V1:
            if self.upload_id is None or self.upload_token is None or not self.parts:
                raise ValueError("Multipart completion requires upload_id, upload_token and parts")
        elif self.upload_id is not None or self.upload_token is not None or self.parts:
            raise ValueError("Multipart fields require upload_protocol=multipart-v1")
        return self


type ContentMediaUploadIntentResponse = ContentMediaUploadIntent | ContentMediaMultipartUploadIntent


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
