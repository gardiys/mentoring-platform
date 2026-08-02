from __future__ import annotations

import hashlib
import logging
import subprocess
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn
from urllib.parse import quote, unquote, urlsplit
from uuid import UUID, uuid4

import anyio
import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings
from app.core.errors import api_error

EXTERNAL_STORAGE_KEY_PREFIX = "external:"
LEGACY_INTERVIEW_MEDIA_PREFIX = "https://s3.firstvds.ru:443/interviews/"
LEGACY_S3_ENDPOINT_URL = "https://s3.firstvds.ru"
LEGACY_S3_REGION = "default"
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoredUpload:
    storage_key: str
    filename: str
    content_type: str
    size: int


@dataclass(frozen=True)
class UploadIntent:
    upload_url: str
    fields: dict[str, str]
    storage_key: str
    filename: str
    content_type: str
    size: int
    expires_in: int


@dataclass
class OpenedDownload:
    body: Any
    content_length: int
    content_range: str | None
    etag: str | None

    def chunks(self) -> Iterator[bytes]:
        try:
            yield from self.body.iter_chunks(chunk_size=1024 * 1024)
        finally:
            self.body.close()


class InterviewStorageReadError(RuntimeError):
    """A private interview object could not be staged for external processing."""


class InterviewUploadStore:
    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.s3_bucket
        self.expires_in = settings.s3_presign_ttl_seconds
        credentials = {
            "aws_access_key_id": settings.s3_access_key_id,
            "aws_secret_access_key": settings.s3_secret_access_key.get_secret_value(),
            "region_name": settings.s3_region,
        }
        self.client: Any = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            config=self._client_config(settings.s3_endpoint_url),
            **credentials,
        )
        self.public_client: Any = boto3.client(
            "s3",
            endpoint_url=settings.s3_public_endpoint_url,
            config=self._client_config(settings.s3_public_endpoint_url),
            **credentials,
        )
        # Imported recordings use the historical FirstVDS bucket URL. They
        # used to be fetched anonymously, which stops working as soon as that
        # bucket becomes private. Keep them on the original endpoint, but sign
        # every browser GET and use authenticated GetObject for proxy streams.
        self.legacy_client: Any = boto3.client(
            "s3",
            endpoint_url=LEGACY_S3_ENDPOINT_URL,
            config=self._client_config(LEGACY_S3_ENDPOINT_URL),
            **(credentials | {"region_name": LEGACY_S3_REGION}),
        )

    def create_upload_intent(
        self,
        *,
        user_id: UUID,
        category: str,
        filename: str,
        content_type: str,
        size: int,
        allowed_content_types: tuple[str, ...],
        max_bytes: int,
    ) -> UploadIntent:
        clean_filename = Path(filename.replace("\x00", "")).name.strip()[:500]
        clean_content_type = content_type.split(";", 1)[0].strip().lower()
        if not clean_filename:
            api_error(422, "invalid_interview_filename", "A filename is required")
        if not self._content_type_allowed(clean_content_type, allowed_content_types):
            api_error(
                415,
                "unsupported_interview_file_type",
                "The selected file type is not supported",
            )
        if size <= 0:
            api_error(422, "empty_interview_file", "The selected file is empty")
        if size > max_bytes:
            api_error(413, "interview_file_too_large", "The selected file is too large")

        storage_key = f"pending/{category}/{user_id}/{uuid4().hex}"
        try:
            response = self.public_client.generate_presigned_post(
                Bucket=self.bucket,
                Key=storage_key,
                Fields={"Content-Type": clean_content_type},
                Conditions=[
                    {"Content-Type": clean_content_type},
                    ["content-length-range", 1, max_bytes],
                ],
                ExpiresIn=self.expires_in,
            )
        except (BotoCoreError, ClientError) as error:
            self._storage_unavailable(error)
        return UploadIntent(
            upload_url=str(response["url"]),
            fields={str(key): str(value) for key, value in response["fields"].items()},
            storage_key=storage_key,
            filename=clean_filename,
            content_type=clean_content_type,
            size=size,
            expires_in=self.expires_in,
        )

    async def complete_upload(
        self,
        *,
        user_id: UUID,
        category: str,
        storage_key: str,
        filename: str,
        content_type: str,
        expected_size: int,
        allowed_content_types: tuple[str, ...],
        max_bytes: int,
    ) -> StoredUpload:
        prefix = f"pending/{category}/{user_id}/"
        path = PurePosixPath(storage_key)
        if not storage_key.startswith(prefix) or len(path.parts) != 4:
            api_error(404, "interview_upload_not_found", "Interview upload was not found")
        try:
            uuid_value = path.parts[-1]
            UUID(hex=uuid_value)
        except ValueError:
            api_error(404, "interview_upload_not_found", "Interview upload was not found")

        clean_filename = Path(filename.replace("\x00", "")).name.strip()[:500]
        clean_content_type = content_type.split(";", 1)[0].strip().lower()
        if expected_size <= 0:
            api_error(422, "empty_interview_file", "The selected file is empty")
        if expected_size > max_bytes:
            api_error(413, "interview_file_too_large", "The selected file is too large")
        if not clean_filename or not self._content_type_allowed(
            clean_content_type, allowed_content_types
        ):
            api_error(422, "invalid_interview_upload", "Interview upload metadata is invalid")

        try:
            head = await anyio.to_thread.run_sync(
                lambda: self.client.head_object(Bucket=self.bucket, Key=storage_key)
            )
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                api_error(
                    409, "interview_upload_incomplete", "Upload the file before confirming it"
                )
            self._storage_unavailable(error)
        except BotoCoreError as error:
            self._storage_unavailable(error)

        actual_size = int(head.get("ContentLength", 0))
        actual_content_type = str(head.get("ContentType", "")).lower()
        if (
            actual_size != expected_size
            or actual_size <= 0
            or actual_size > max_bytes
            or actual_content_type != clean_content_type
        ):
            await self.delete(storage_key)
            api_error(422, "invalid_interview_upload", "Uploaded file metadata does not match")

        final_key = f"{category}/{user_id}/{uuid_value}"
        try:
            await anyio.to_thread.run_sync(
                lambda: self.client.copy_object(
                    Bucket=self.bucket,
                    Key=final_key,
                    CopySource={"Bucket": self.bucket, "Key": storage_key},
                    ContentType=clean_content_type,
                    MetadataDirective="REPLACE",
                )
            )
            await self.delete(storage_key)
        except (BotoCoreError, ClientError) as error:
            self._storage_unavailable(error)
        return StoredUpload(
            storage_key=final_key,
            filename=clean_filename,
            content_type=clean_content_type,
            size=actual_size,
        )

    def download_url(self, upload: StoredUpload, *, inline: bool = False) -> str:
        external_location = self._external_media_location(upload.storage_key)
        client = self.legacy_client if external_location is not None else self.public_client
        bucket, key = external_location or (self.bucket, upload.storage_key)
        disposition_type = "inline" if inline else "attachment"
        disposition = f"{disposition_type}; filename*=UTF-8''{quote(upload.filename)}"
        try:
            return str(
                client.generate_presigned_url(
                    "get_object",
                    Params={
                        "Bucket": bucket,
                        "Key": key,
                        "ResponseContentDisposition": disposition,
                        "ResponseContentType": upload.content_type,
                    },
                    ExpiresIn=self.expires_in,
                )
            )
        except (BotoCoreError, ClientError) as error:
            self._storage_unavailable(error)

    async def download_to_path(self, upload: StoredUpload, destination: Path) -> None:
        external_location = self._external_media_location(upload.storage_key)
        client = self.legacy_client if external_location is not None else self.client
        bucket, key = external_location or (self.bucket, upload.storage_key)
        try:
            await anyio.to_thread.run_sync(
                lambda: client.download_file(bucket, key, str(destination))
            )
        except (BotoCoreError, ClientError) as error:
            logger.error(
                "Could not stage interview object for processing bucket=%s key=%s",
                bucket,
                key,
            )
            raise InterviewStorageReadError(
                "Could not stage interview object for processing"
            ) from error

    async def open_download(
        self,
        upload: StoredUpload,
        *,
        range_header: str | None,
    ) -> OpenedDownload:
        external_location = self._external_media_location(upload.storage_key)
        client = self.legacy_client if external_location is not None else self.client
        bucket, key = external_location or (self.bucket, upload.storage_key)
        params: dict[str, Any] = {
            "Bucket": bucket,
            "Key": key,
        }
        if range_header is not None:
            params["Range"] = range_header
        try:
            response = await anyio.to_thread.run_sync(lambda: client.get_object(**params))
        except ClientError as error:
            status_code = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            error_code = error.response.get("Error", {}).get("Code")
            if status_code == 416 or error_code == "InvalidRange":
                api_error(416, "invalid_interview_media_range", "Requested range is invalid")
            self._storage_unavailable(error)
        except BotoCoreError as error:
            self._storage_unavailable(error)
        return OpenedDownload(
            body=response["Body"],
            content_length=int(response["ContentLength"]),
            content_range=response.get("ContentRange"),
            etag=response.get("ETag"),
        )

    async def ensure_browser_playable(self, upload: StoredUpload) -> StoredUpload:
        external_location = self._external_media_location(upload.storage_key)
        if external_location is None or not upload.filename.casefold().endswith(".mp3"):
            return upload
        try:
            return await anyio.to_thread.run_sync(
                lambda: self._normalize_legacy_audio(upload, external_location)
            )
        except (BotoCoreError, ClientError) as error:
            self._storage_unavailable(error)

    def _normalize_legacy_audio(
        self,
        upload: StoredUpload,
        external_location: tuple[str, str],
    ) -> StoredUpload:
        bucket, key = external_location
        response = self.legacy_client.get_object(
            Bucket=bucket,
            Key=key,
            Range="bytes=0-65535",
        )
        try:
            header = response["Body"].read()
        finally:
            response["Body"].close()
        total_size = self._object_total_size(response, upload.size)
        if len(header) >= 12 and header[4:8] == b"ftyp":
            if b"alac" in header:
                return self._transcode_legacy_alac(upload, external_location)
            return replace(
                upload,
                filename=f"{Path(upload.filename).stem}.m4a",
                content_type="audio/mp4",
                size=total_size,
            )
        return replace(upload, size=total_size)

    def _transcode_legacy_alac(
        self,
        upload: StoredUpload,
        external_location: tuple[str, str],
    ) -> StoredUpload:
        source_bucket, source_key = external_location
        digest = hashlib.sha256(upload.storage_key.encode("utf-8")).hexdigest()
        converted_key = f"media/converted/{digest}.mp3"
        try:
            existing = self.client.head_object(Bucket=self.bucket, Key=converted_key)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") not in {
                "404",
                "NoSuchKey",
                "NotFound",
            }:
                raise
        else:
            return StoredUpload(
                storage_key=converted_key,
                filename=f"{Path(upload.filename).stem}.mp3",
                content_type="audio/mpeg",
                size=int(existing.get("ContentLength", 0)),
            )

        with tempfile.TemporaryDirectory(prefix="interview-audio-") as directory:
            source_path = Path(directory) / "source.m4a"
            target_path = Path(directory) / "recording.mp3"
            with source_path.open("wb") as source:
                self.legacy_client.download_fileobj(
                    Bucket=source_bucket,
                    Key=source_key,
                    Fileobj=source,
                )
            try:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-y",
                        "-i",
                        str(source_path),
                        "-map",
                        "0:a:0",
                        "-vn",
                        "-codec:a",
                        "libmp3lame",
                        "-q:a",
                        "3",
                        str(target_path),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=600,
                )
            except (FileNotFoundError, subprocess.SubprocessError) as error:
                logger.error("Legacy interview audio transcoding failed: %s", error)
                api_error(
                    503,
                    "interview_audio_transcoding_failed",
                    "Interview audio could not be prepared for this browser",
                )
            size = target_path.stat().st_size
            with target_path.open("rb") as target:
                self.client.upload_fileobj(
                    Fileobj=target,
                    Bucket=self.bucket,
                    Key=converted_key,
                    ExtraArgs={"ContentType": "audio/mpeg"},
                )
        return StoredUpload(
            storage_key=converted_key,
            filename=f"{Path(upload.filename).stem}.mp3",
            content_type="audio/mpeg",
            size=size,
        )

    async def delete(self, storage_key: str | None) -> None:
        if storage_key is None:
            return
        if self._external_media_location(storage_key) is not None:
            return
        try:
            await anyio.to_thread.run_sync(
                lambda: self.client.delete_object(Bucket=self.bucket, Key=storage_key)
            )
        except (BotoCoreError, ClientError) as error:
            self._storage_unavailable(error)

    @staticmethod
    def _content_type_allowed(content_type: str, allowed_content_types: tuple[str, ...]) -> bool:
        return any(
            content_type == allowed or content_type.startswith(f"{allowed}/")
            for allowed in allowed_content_types
        )

    @staticmethod
    def _client_config(endpoint_url: str | None) -> Config:
        s3_options = {"addressing_style": "path"} if endpoint_url else {}
        return Config(signature_version="s3v4", s3=s3_options)

    @staticmethod
    def _object_total_size(response: dict[str, Any], fallback: int) -> int:
        content_range = response.get("ContentRange")
        if isinstance(content_range, str) and "/" in content_range:
            try:
                return int(content_range.rsplit("/", 1)[1])
            except ValueError:
                pass
        return fallback or int(response.get("ContentLength", 0))

    @staticmethod
    def _external_media_location(storage_key: str) -> tuple[str, str] | None:
        if not storage_key.startswith(EXTERNAL_STORAGE_KEY_PREFIX):
            return None
        url = storage_key.removeprefix(EXTERNAL_STORAGE_KEY_PREFIX)
        if not url.startswith(LEGACY_INTERVIEW_MEDIA_PREFIX):
            return None
        parsed = urlsplit(url)
        path_parts = unquote(parsed.path).lstrip("/").split("/", 1)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "s3.firstvds.ru:443"
            or parsed.query
            or parsed.fragment
            or len(path_parts) != 2
            or not all(path_parts)
        ):
            return None
        return path_parts[0], path_parts[1]

    @staticmethod
    def _storage_unavailable(error: Exception) -> NoReturn:
        logger.error("Interview S3 request failed: %s", error)
        api_error(503, "interview_storage_unavailable", "Interview file storage is unavailable")
