from __future__ import annotations

import fcntl
import hashlib
import logging
import math
import shutil
import stat
import subprocess
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, NoReturn
from urllib.parse import quote, unquote, urlsplit
from uuid import UUID, uuid4

import anyio
import boto3
from boto3.exceptions import S3UploadFailedError
from boto3.s3.transfer import TransferConfig
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.auth.web_session import SignedPayloadError, sign_payload, verify_payload
from app.core.config import Settings
from app.core.errors import api_error

EXTERNAL_STORAGE_KEY_PREFIX = "external:"
LEGACY_INTERVIEW_MEDIA_PREFIX = "https://s3.firstvds.ru:443/interviews/"
LEGACY_S3_ENDPOINT_URL = "https://s3.firstvds.ru"
LEGACY_S3_REGION = "default"
MULTIPART_UPLOAD_TOKEN_KIND = "private_s3_multipart_upload"
MULTIPART_UPLOAD_ABORT_URL = "/api/v1/uploads/multipart/abort"
S3_MULTIPART_MIN_PART_BYTES = 5 * 1024 * 1024
S3_MULTIPART_MAX_PARTS = 10_000
MULTIPART_HEAD_RECONCILIATION_DELAYS = (0.0, 0.25, 1.0, 2.0)
WORKER_UPLOAD_HEAD_RECONCILIATION_DELAYS = (0.0, 0.25, 1.0, 2.0)
WORKER_UPLOAD_TRANSFER_CONFIG = TransferConfig(
    multipart_threshold=64 * 1024 * 1024,
    multipart_chunksize=64 * 1024 * 1024,
    max_concurrency=2,
    use_threads=True,
)
MULTIPART_ACTIVE_UPLOAD_LIST_PAGES = 4
SAFE_RASTER_IMAGE_CONTENT_TYPES = (
    "image/avif",
    "image/bmp",
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
)
SAFE_ATTACHMENT_CONTENT_TYPES = (
    "application/msword",
    "application/pdf",
    "application/rtf",
    "application/vnd.ms-excel",
    "application/vnd.ms-powerpoint",
    "application/vnd.oasis.opendocument.presentation",
    "application/vnd.oasis.opendocument.spreadsheet",
    "application/vnd.oasis.opendocument.text",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/csv",
    "text/markdown",
    "text/plain",
    "text/rtf",
    *SAFE_RASTER_IMAGE_CONTENT_TYPES,
)
SAFE_OFFER_CONTENT_TYPES = ("application/pdf", *SAFE_RASTER_IMAGE_CONTENT_TYPES)
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


@dataclass(frozen=True)
class MultipartUploadPartIntent:
    part_number: int
    upload_url: str
    headers: dict[str, str]


@dataclass(frozen=True)
class MultipartUploadIntent:
    upload_protocol: str
    upload_id: str
    upload_token: str
    abort_url: str
    storage_key: str
    filename: str
    content_type: str
    size: int
    part_size: int
    part_count: int
    parts: tuple[MultipartUploadPartIntent, ...]
    expires_in: int


@dataclass(frozen=True)
class CompletedMultipartUploadPart:
    part_number: int
    etag: str


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


class InterviewStorageWriteError(RuntimeError):
    """A worker could not persist or remove an internally generated object."""


class LegacyTranscodeCapacityError(RuntimeError):
    """Legacy audio cannot safely enter the bounded local transcode staging area."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _BoundedFileWriter:
    def __init__(self, target: BinaryIO, *, maximum_bytes: int) -> None:
        self._target = target
        self._maximum_bytes = maximum_bytes
        self._written_bytes = 0

    def write(self, content: bytes) -> int:
        if self._written_bytes + len(content) > self._maximum_bytes:
            raise LegacyTranscodeCapacityError("legacy_source_too_large")
        written = self._target.write(content)
        self._written_bytes += written
        return written


class _LegacyTranscodeGuard:
    """Bound concurrent conversions across threads and backend worker processes."""

    def __init__(
        self,
        *,
        max_concurrency: int,
        min_free_bytes: int,
        max_reserved_bytes: int,
    ) -> None:
        self._max_concurrency = max_concurrency
        self._semaphore = threading.BoundedSemaphore(max_concurrency)
        self._reservation_lock = threading.Lock()
        self._min_free_bytes = min_free_bytes
        self._max_reserved_bytes = max_reserved_bytes
        self._reserved_bytes = 0

    @contextmanager
    def reserve(self, root: Path, *, expected_bytes: int) -> Iterator[None]:
        if expected_bytes <= 0:
            raise ValueError("expected_bytes must be positive")
        if not self._semaphore.acquire(blocking=False):
            raise LegacyTranscodeCapacityError("legacy_transcode_busy")

        slot: BinaryIO | None = None
        reserved = False
        try:
            try:
                root.mkdir(parents=True, exist_ok=True)
                slot = self._acquire_process_slot(root)
            except OSError as error:
                raise LegacyTranscodeCapacityError(
                    "legacy_transcode_directory_unavailable"
                ) from error
            if slot is None:
                raise LegacyTranscodeCapacityError("legacy_transcode_busy")

            with self._reservation_lock:
                try:
                    free_bytes = shutil.disk_usage(root).free
                except OSError as error:
                    raise LegacyTranscodeCapacityError(
                        "legacy_transcode_directory_unavailable"
                    ) from error
                available_bytes = max(0, free_bytes - self._reserved_bytes)
                if (
                    expected_bytes > self._max_reserved_bytes
                    or available_bytes < expected_bytes + self._min_free_bytes
                ):
                    raise LegacyTranscodeCapacityError("legacy_transcode_disk_capacity")
                self._reserved_bytes += expected_bytes
                reserved = True
            yield
        finally:
            if reserved:
                with self._reservation_lock:
                    self._reserved_bytes -= expected_bytes
            if slot is not None:
                try:
                    fcntl.flock(slot.fileno(), fcntl.LOCK_UN)
                finally:
                    slot.close()
            self._semaphore.release()

    def _acquire_process_slot(self, root: Path) -> BinaryIO | None:
        for slot_number in range(self._max_concurrency):
            slot = (root / f".legacy-transcode-{slot_number}.lock").open("a+b")
            try:
                fcntl.flock(slot.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                slot.close()
                continue
            except OSError:
                slot.close()
                raise
            return slot
        return None


class InterviewUploadStore:
    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.s3_bucket
        self.expires_in = settings.s3_presign_ttl_seconds
        self.multipart_part_size = settings.s3_multipart_part_size_bytes
        self.multipart_presign_expires_in = settings.s3_multipart_presign_ttl_seconds
        self.multipart_session_expires_in = settings.s3_multipart_session_ttl_seconds
        self._multipart_token_secret = (
            settings.web_session_secret.get_secret_value()
            if settings.web_session_secret is not None
            else settings.s3_secret_access_key.get_secret_value()
        )
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
        self._legacy_transcode_root = Path(settings.interview_legacy_transcode_directory)
        self._legacy_transcode_cleanup_age_seconds = (
            settings.interview_legacy_transcode_cleanup_age_seconds
        )
        self._legacy_transcode_timeout_seconds = settings.interview_legacy_transcode_timeout_seconds
        self._legacy_transcode_max_file_bytes = settings.interview_audio_max_bytes
        self._legacy_transcode_guard = _LegacyTranscodeGuard(
            max_concurrency=settings.interview_legacy_transcode_max_concurrency,
            min_free_bytes=settings.interview_legacy_transcode_min_free_bytes,
            max_reserved_bytes=settings.interview_legacy_transcode_max_reserved_bytes,
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
                    ["content-length-range", 1, size],
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

    async def create_multipart_upload_intent(
        self,
        *,
        user_id: UUID,
        category: str,
        resource: str,
        filename: str,
        content_type: str,
        size: int,
        allowed_content_types: tuple[str, ...],
        max_bytes: int,
    ) -> MultipartUploadIntent:
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

        resource_hash = hashlib.sha256(resource.encode("utf-8")).hexdigest()[:16]
        object_uuid = uuid4().hex
        resource_prefix = f"{category}/{user_id}/{resource_hash}/"
        storage_key = f"{resource_prefix}{object_uuid}"
        await self._abort_previous_resource_uploads(prefix=resource_prefix)
        part_size = self._multipart_part_size(size)
        part_count = math.ceil(size / part_size)
        upload_id: str | None = None
        try:
            response = await anyio.to_thread.run_sync(
                lambda: self.client.create_multipart_upload(
                    Bucket=self.bucket,
                    Key=storage_key,
                    ContentType=clean_content_type,
                )
            )
            upload_id = str(response["UploadId"])
            parts = tuple(
                MultipartUploadPartIntent(
                    part_number=part_number,
                    upload_url=str(
                        self.public_client.generate_presigned_url(
                            "upload_part",
                            Params={
                                "Bucket": self.bucket,
                                "Key": storage_key,
                                "UploadId": upload_id,
                                "PartNumber": part_number,
                                "ContentLength": min(
                                    part_size,
                                    size - (part_number - 1) * part_size,
                                ),
                            },
                            ExpiresIn=self.multipart_presign_expires_in,
                        )
                    ),
                    headers={},
                )
                for part_number in range(1, part_count + 1)
            )
        except (BotoCoreError, ClientError, KeyError) as error:
            if upload_id is not None:
                await self._abort_provider_multipart_upload(
                    storage_key=storage_key,
                    upload_id=upload_id,
                )
            self._storage_unavailable(error)

        upload_token = sign_payload(
            {
                "kind": MULTIPART_UPLOAD_TOKEN_KIND,
                "user_id": str(user_id),
                "category": category,
                "resource": resource,
                "storage_key": storage_key,
                "upload_id": upload_id,
                "filename": clean_filename,
                "content_type": clean_content_type,
                "size": size,
                "part_size": part_size,
                "part_count": part_count,
                "exp": self._timestamp() + self.multipart_session_expires_in,
            },
            self._multipart_token_secret,
        )
        return MultipartUploadIntent(
            upload_protocol="multipart-v1",
            upload_id=upload_id,
            upload_token=upload_token,
            abort_url=MULTIPART_UPLOAD_ABORT_URL,
            storage_key=storage_key,
            filename=clean_filename,
            content_type=clean_content_type,
            size=size,
            part_size=part_size,
            part_count=part_count,
            parts=parts,
            expires_in=self.multipart_presign_expires_in,
        )

    async def complete_multipart_upload(
        self,
        *,
        user_id: UUID,
        category: str,
        resource: str,
        storage_key: str,
        upload_id: str,
        upload_token: str,
        filename: str,
        content_type: str,
        expected_size: int,
        parts: tuple[CompletedMultipartUploadPart, ...],
        allowed_content_types: tuple[str, ...],
        max_bytes: int,
    ) -> StoredUpload:
        clean_filename = Path(filename.replace("\x00", "")).name.strip()[:500]
        clean_content_type = content_type.split(";", 1)[0].strip().lower()
        payload = self._verified_multipart_payload(
            upload_token,
            user_id=user_id,
            category=category,
            resource=resource,
            storage_key=storage_key,
            upload_id=upload_id,
        )
        if (
            not clean_filename
            or clean_filename != payload.get("filename")
            or clean_content_type != payload.get("content_type")
            or expected_size != payload.get("size")
            or expected_size <= 0
            or expected_size > max_bytes
            or not self._content_type_allowed(clean_content_type, allowed_content_types)
        ):
            api_error(422, "invalid_interview_upload", "Interview upload metadata is invalid")

        expected_part_count = payload.get("part_count")
        if not isinstance(expected_part_count, int) or expected_part_count <= 0:
            api_error(404, "interview_upload_not_found", "Interview upload was not found")
        if len(parts) != expected_part_count or tuple(part.part_number for part in parts) != tuple(
            range(1, expected_part_count + 1)
        ):
            api_error(
                422,
                "invalid_interview_multipart_parts",
                "Every uploaded file part must be confirmed in order",
            )

        provider_parts = [{"PartNumber": part.part_number, "ETag": part.etag} for part in parts]
        ambiguous_completion_error: BotoCoreError | None = None
        try:
            await anyio.to_thread.run_sync(
                lambda: self.client.complete_multipart_upload(
                    Bucket=self.bucket,
                    Key=storage_key,
                    UploadId=upload_id,
                    MultipartUpload={"Parts": provider_parts},
                )
            )
        except ClientError as error:
            if not self._is_no_such_upload(error):
                self._storage_unavailable(error)
            # A retry after a successful provider completion receives
            # NoSuchUpload. HEAD below turns that case into an idempotent result.
        except BotoCoreError as error:
            # A connection/read timeout can happen after S3 has committed the
            # multipart upload. Reconcile with HEAD before telling the client
            # to retry, otherwise a successful object becomes an orphan.
            ambiguous_completion_error = error

        head = await self._head_completed_multipart_upload(
            storage_key,
            missing_after_ambiguous_error=ambiguous_completion_error,
        )
        actual_size = int(head.get("ContentLength", 0))
        actual_content_type = str(head.get("ContentType", "")).split(";", 1)[0].lower()
        if actual_size != expected_size or actual_content_type != clean_content_type:
            await self.delete(storage_key)
            api_error(422, "invalid_interview_upload", "Uploaded file metadata does not match")
        return StoredUpload(
            storage_key=storage_key,
            filename=clean_filename,
            content_type=clean_content_type,
            size=actual_size,
        )

    async def abort_multipart_upload(
        self,
        *,
        user_id: UUID,
        storage_key: str,
        upload_id: str,
        upload_token: str,
    ) -> None:
        self._verified_multipart_payload(
            upload_token,
            user_id=user_id,
            storage_key=storage_key,
            upload_id=upload_id,
        )
        try:
            await anyio.to_thread.run_sync(
                lambda: self.client.abort_multipart_upload(
                    Bucket=self.bucket,
                    Key=storage_key,
                    UploadId=upload_id,
                )
            )
        except ClientError as error:
            if self._is_no_such_upload(error):
                return
            self._storage_unavailable(error)
        except BotoCoreError as error:
            self._storage_unavailable(error)

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

    def download_url(
        self,
        upload: StoredUpload,
        *,
        inline: bool = False,
        expires_in: int | None = None,
    ) -> str:
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
                    ExpiresIn=expires_in if expires_in is not None else self.expires_in,
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

    async def resolve_upload_size(self, upload: StoredUpload) -> StoredUpload:
        """Return an upload with the authoritative object size from storage.

        Legacy interview imports could not know the remote object size and stored
        zero in the database. Re-read S3 metadata before allocating local staging
        space so workers neither trust stale database metadata nor bypass the
        recording-size limits.
        """
        external_location = self._external_media_location(upload.storage_key)
        client = self.legacy_client if external_location is not None else self.client
        bucket, key = external_location or (self.bucket, upload.storage_key)
        try:
            head = await anyio.to_thread.run_sync(
                lambda: client.head_object(Bucket=bucket, Key=key)
            )
        except (BotoCoreError, ClientError) as error:
            logger.error(
                "Could not read interview object metadata bucket=%s key=%s",
                bucket,
                key,
            )
            raise InterviewStorageReadError("Could not read interview object metadata") from error
        try:
            actual_size = int(head.get("ContentLength", 0))
        except (TypeError, ValueError) as error:
            raise InterviewStorageReadError(
                "Interview object metadata contains an invalid size"
            ) from error
        return replace(upload, size=actual_size)

    async def upload_path(
        self,
        source: Path,
        *,
        storage_key: str,
        content_type: str,
        expected_size: int,
    ) -> None:
        """Upload a worker-produced file and verify its persisted S3 metadata.

        Browser uploads are finalized through the multipart API above.  This
        method is intentionally narrower: it only accepts a regular local file
        and an internal key, and is used by background media processors.
        """
        path = PurePosixPath(storage_key)
        if (
            not storage_key
            or path.is_absolute()
            or ".." in path.parts
            or self._external_media_location(storage_key) is not None
        ):
            raise ValueError("storage_key must be a safe internal object key")
        normalized_content_type = content_type.split(";", 1)[0].strip().lower()
        if not normalized_content_type:
            raise ValueError("content_type is required")
        try:
            source_stat = source.lstat()
        except OSError as error:
            raise InterviewStorageWriteError("Generated media file is unavailable") from error
        if (
            stat.S_ISLNK(source_stat.st_mode)
            or not stat.S_ISREG(source_stat.st_mode)
            or expected_size <= 0
            or source_stat.st_size != expected_size
        ):
            raise InterviewStorageWriteError("Generated media file metadata is invalid")

        try:
            await anyio.to_thread.run_sync(
                lambda: self.client.upload_file(
                    str(source),
                    self.bucket,
                    storage_key,
                    ExtraArgs={"ContentType": normalized_content_type},
                    Config=WORKER_UPLOAD_TRANSFER_CONFIG,
                )
            )
            head: dict[str, Any] | None = None
            for attempt, delay in enumerate(
                WORKER_UPLOAD_HEAD_RECONCILIATION_DELAYS,
                start=1,
            ):
                if delay:
                    await anyio.sleep(delay)
                try:
                    head = dict(
                        await anyio.to_thread.run_sync(
                            lambda: self.client.head_object(
                                Bucket=self.bucket,
                                Key=storage_key,
                            )
                        )
                    )
                    break
                except ClientError as error:
                    missing = error.response.get("Error", {}).get("Code") in {
                        "404",
                        "NoSuchKey",
                        "NotFound",
                    }
                    if missing and attempt < len(WORKER_UPLOAD_HEAD_RECONCILIATION_DELAYS):
                        continue
                    raise
            if head is None:
                raise InterviewStorageWriteError("Generated media object could not be verified")
            actual_size = int(head.get("ContentLength", 0))
            actual_content_type = str(head.get("ContentType", "")).split(";", 1)[0].strip().lower()
            if actual_size != expected_size or actual_content_type != normalized_content_type:
                raise InterviewStorageWriteError(
                    "Generated media object metadata does not match the local file"
                )
        except InterviewStorageWriteError:
            await self.delete_for_processing(storage_key, suppress_errors=True)
            raise
        except (BotoCoreError, ClientError, OSError, S3UploadFailedError) as error:
            logger.error(
                "Could not upload generated media object bucket=%s key=%s error=%s",
                self.bucket,
                storage_key,
                error,
            )
            await self.delete_for_processing(storage_key, suppress_errors=True)
            raise InterviewStorageWriteError("Could not persist generated media object") from error

    async def delete_for_processing(
        self,
        storage_key: str | None,
        *,
        suppress_errors: bool = False,
    ) -> bool:
        """Delete an internal object without translating failures to HTTP errors."""
        if storage_key is None or self._external_media_location(storage_key) is not None:
            return True
        try:
            await anyio.to_thread.run_sync(
                lambda: self.client.delete_object(Bucket=self.bucket, Key=storage_key)
            )
        except (BotoCoreError, ClientError) as error:
            logger.error(
                "Could not delete worker media object bucket=%s key=%s error=%s",
                self.bucket,
                storage_key,
                error,
            )
            if suppress_errors:
                return False
            raise InterviewStorageWriteError("Could not delete generated media object") from error
        return True

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
                return self._transcode_legacy_alac(
                    upload,
                    external_location,
                    source_size=total_size,
                )
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
        *,
        source_size: int,
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

        maximum_file_bytes = self._legacy_transcode_max_file_bytes
        if source_size <= 0 or source_size > maximum_file_bytes:
            api_error(
                503,
                "interview_audio_transcoding_capacity_unavailable",
                "Interview audio is too large to prepare safely",
            )
        expected_disk_bytes = source_size + maximum_file_bytes
        try:
            with self._legacy_transcode_guard.reserve(
                self._legacy_transcode_root,
                expected_bytes=expected_disk_bytes,
            ):
                self._cleanup_stale_legacy_transcodes()
                return self._perform_legacy_alac_transcode(
                    upload=upload,
                    source_bucket=source_bucket,
                    source_key=source_key,
                    converted_key=converted_key,
                    source_size=source_size,
                )
        except LegacyTranscodeCapacityError as error:
            logger.warning(
                "Legacy interview audio transcoding rejected reason=%s",
                error.reason,
            )
            if error.reason == "legacy_transcode_busy":
                api_error(
                    503,
                    "interview_audio_transcoding_busy",
                    "Interview audio preparation is busy; retry later",
                )
            api_error(
                503,
                "interview_audio_transcoding_capacity_unavailable",
                "Interview audio cannot be prepared with the available disk capacity",
            )

    def _perform_legacy_alac_transcode(
        self,
        *,
        upload: StoredUpload,
        source_bucket: str,
        source_key: str,
        converted_key: str,
        source_size: int,
    ) -> StoredUpload:
        try:
            directory = Path(
                tempfile.mkdtemp(prefix="legacy-alac-", dir=self._legacy_transcode_root)
            )
        except OSError as error:
            raise LegacyTranscodeCapacityError("legacy_transcode_directory_unavailable") from error
        source_path = directory / "source.m4a"
        target_path = directory / "recording.mp3"
        try:
            try:
                with source_path.open("wb") as source:
                    self.legacy_client.download_fileobj(
                        Bucket=source_bucket,
                        Key=source_key,
                        Fileobj=_BoundedFileWriter(
                            source,
                            maximum_bytes=self._legacy_transcode_max_file_bytes,
                        ),
                    )
                source_stat = source_path.lstat()
                if not stat.S_ISREG(source_stat.st_mode) or source_stat.st_size != source_size:
                    raise OSError("Legacy source size does not match storage metadata")
            except LegacyTranscodeCapacityError:
                raise
            except (BotoCoreError, ClientError, OSError) as error:
                logger.error("Legacy interview audio download failed: %s", error)
                api_error(
                    503,
                    "interview_audio_transcoding_failed",
                    "Interview audio could not be read for browser preparation",
                )

            try:
                ffmpeg_binary = shutil.which("ffmpeg")
                if ffmpeg_binary is None:
                    raise FileNotFoundError("ffmpeg")
                subprocess.run(
                    [
                        ffmpeg_binary,
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-nostdin",
                        "-y",
                        "-protocol_whitelist",
                        "file",
                        "-i",
                        str(source_path),
                        "-map",
                        "0:a:0",
                        "-vn",
                        "-map_metadata",
                        "-1",
                        "-map_chapters",
                        "-1",
                        "-codec:a",
                        "libmp3lame",
                        "-threads",
                        "1",
                        "-q:a",
                        "3",
                        "-fs",
                        str(self._legacy_transcode_max_file_bytes),
                        str(target_path),
                    ],
                    check=True,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=self._legacy_transcode_timeout_seconds,
                    env={
                        "LANG": "C.UTF-8",
                        "LC_ALL": "C.UTF-8",
                        "PATH": str(Path(ffmpeg_binary).parent),
                    },
                )
            except (FileNotFoundError, OSError, subprocess.SubprocessError) as error:
                logger.error("Legacy interview audio transcoding failed: %s", error)
                api_error(
                    503,
                    "interview_audio_transcoding_failed",
                    "Interview audio could not be prepared for this browser",
                )
            try:
                target_stat = target_path.lstat()
                if (
                    not stat.S_ISREG(target_stat.st_mode)
                    or target_stat.st_size <= 0
                    or target_stat.st_size > self._legacy_transcode_max_file_bytes
                ):
                    raise OSError("Legacy transcode produced an invalid output file")
                size = target_stat.st_size
                with target_path.open("rb") as target:
                    self.client.upload_fileobj(
                        Fileobj=target,
                        Bucket=self.bucket,
                        Key=converted_key,
                        ExtraArgs={"ContentType": "audio/mpeg"},
                    )
            except (BotoCoreError, ClientError, OSError) as error:
                logger.error("Legacy interview audio upload failed: %s", error)
                api_error(
                    503,
                    "interview_audio_transcoding_failed",
                    "Prepared interview audio could not be saved",
                )
            return StoredUpload(
                storage_key=converted_key,
                filename=f"{Path(upload.filename).stem}.mp3",
                content_type="audio/mpeg",
                size=size,
            )
        finally:
            try:
                shutil.rmtree(directory)
            except OSError as error:
                logger.warning(
                    "Could not clean legacy interview transcode directory path=%s error=%s",
                    directory,
                    error,
                )

    def _cleanup_stale_legacy_transcodes(self) -> None:
        cutoff = time.time() - self._legacy_transcode_cleanup_age_seconds
        try:
            entries = tuple(self._legacy_transcode_root.iterdir())
        except OSError as error:
            raise LegacyTranscodeCapacityError("legacy_transcode_directory_unavailable") from error
        for entry in entries:
            if not entry.name.startswith("legacy-alac-"):
                continue
            try:
                entry_stat = entry.stat(follow_symlinks=False)
                if not stat.S_ISDIR(entry_stat.st_mode) or entry_stat.st_mtime > cutoff:
                    continue
                shutil.rmtree(entry)
            except OSError:
                logger.warning("Could not clean stale legacy transcode path=%s", entry)

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

    def _multipart_part_size(self, size: int) -> int:
        minimum_for_part_limit = math.ceil(size / S3_MULTIPART_MAX_PARTS)
        minimum_for_part_limit = (
            math.ceil(minimum_for_part_limit / S3_MULTIPART_MIN_PART_BYTES)
            * S3_MULTIPART_MIN_PART_BYTES
        )
        return max(self.multipart_part_size, minimum_for_part_limit)

    def _verified_multipart_payload(
        self,
        token: str,
        *,
        user_id: UUID,
        storage_key: str,
        upload_id: str,
        category: str | None = None,
        resource: str | None = None,
    ) -> dict[str, Any]:
        try:
            payload = verify_payload(
                token,
                self._multipart_token_secret,
                expected_kind=MULTIPART_UPLOAD_TOKEN_KIND,
            )
        except SignedPayloadError:
            api_error(404, "interview_upload_not_found", "Interview upload was not found")

        token_category = payload.get("category")
        token_resource = payload.get("resource")
        expected_values: tuple[tuple[object, object], ...] = (
            (payload.get("user_id"), str(user_id)),
            (payload.get("storage_key"), storage_key),
            (payload.get("upload_id"), upload_id),
        )
        if category is not None:
            expected_values += ((token_category, category),)
        if resource is not None:
            expected_values += ((token_resource, resource),)
        if (
            not isinstance(token_category, str)
            or not isinstance(token_resource, str)
            or any(actual != expected for actual, expected in expected_values)
        ):
            api_error(404, "interview_upload_not_found", "Interview upload was not found")

        path = PurePosixPath(storage_key)
        resource_hash = hashlib.sha256(token_resource.encode("utf-8")).hexdigest()[:16]
        prefix = f"{token_category}/{user_id}/{resource_hash}/"
        if not storage_key.startswith(prefix) or len(path.parts) != 4:
            api_error(404, "interview_upload_not_found", "Interview upload was not found")
        try:
            UUID(hex=path.parts[-1])
        except ValueError:
            api_error(404, "interview_upload_not_found", "Interview upload was not found")
        return payload

    async def _head_completed_multipart_upload(
        self,
        storage_key: str,
        *,
        missing_after_ambiguous_error: BotoCoreError | None = None,
    ) -> dict[str, Any]:
        delays = (
            MULTIPART_HEAD_RECONCILIATION_DELAYS
            if missing_after_ambiguous_error is not None
            else (0.0,)
        )
        for attempt, delay in enumerate(delays, start=1):
            if delay:
                await anyio.sleep(delay)
            try:
                return dict(
                    await anyio.to_thread.run_sync(
                        lambda: self.client.head_object(
                            Bucket=self.bucket,
                            Key=storage_key,
                        )
                    )
                )
            except ClientError as error:
                if error.response.get("Error", {}).get("Code") in {
                    "404",
                    "NoSuchKey",
                    "NotFound",
                }:
                    if attempt < len(delays):
                        continue
                    if missing_after_ambiguous_error is not None:
                        self._storage_unavailable(missing_after_ambiguous_error)
                    api_error(
                        409,
                        "interview_upload_incomplete",
                        "Upload every file part before confirming it",
                    )
                self._storage_unavailable(error)
            except BotoCoreError as error:
                self._storage_unavailable(error)
        raise AssertionError("Multipart HEAD reconciliation exhausted unexpectedly")

    async def _abort_provider_multipart_upload(
        self,
        *,
        storage_key: str,
        upload_id: str,
    ) -> None:
        try:
            await anyio.to_thread.run_sync(
                lambda: self.client.abort_multipart_upload(
                    Bucket=self.bucket,
                    Key=storage_key,
                    UploadId=upload_id,
                )
            )
        except (BotoCoreError, ClientError) as error:
            logger.warning(
                "Could not abort partially initialized multipart upload key=%s: %s",
                storage_key,
                error,
            )

    async def _abort_previous_resource_uploads(self, *, prefix: str) -> None:
        key_marker: str | None = None
        upload_id_marker: str | None = None
        for _ in range(MULTIPART_ACTIVE_UPLOAD_LIST_PAGES):
            params: dict[str, Any] = {
                "Bucket": self.bucket,
                "Prefix": prefix,
                "MaxUploads": 1_000,
            }
            if key_marker is not None:
                params["KeyMarker"] = key_marker
            if upload_id_marker is not None:
                params["UploadIdMarker"] = upload_id_marker
            try:
                page = await anyio.to_thread.run_sync(
                    partial(self.client.list_multipart_uploads, **params)
                )
            except (BotoCoreError, ClientError) as error:
                # Listing is a cost guard, not a correctness dependency. Keep
                # S3-compatible providers without this optional API usable and
                # rely on AbortIncompleteMultipartUpload lifecycle there.
                logger.warning(
                    "Could not list previous multipart uploads prefix=%s: %s",
                    prefix,
                    error,
                )
                return
            for upload in page.get("Uploads", ()):
                key = upload.get("Key")
                upload_id = upload.get("UploadId")
                if not isinstance(key, str) or not isinstance(upload_id, str):
                    continue
                await self._abort_provider_multipart_upload(
                    storage_key=key,
                    upload_id=upload_id,
                )
            if not page.get("IsTruncated"):
                return
            next_key_marker = page.get("NextKeyMarker")
            next_upload_id_marker = page.get("NextUploadIdMarker")
            if not isinstance(next_key_marker, str):
                return
            key_marker = next_key_marker
            upload_id_marker = (
                next_upload_id_marker if isinstance(next_upload_id_marker, str) else None
            )

    @staticmethod
    def _is_no_such_upload(error: ClientError) -> bool:
        return error.response.get("Error", {}).get("Code") in {
            "404",
            "NoSuchUpload",
            "NotFound",
        }

    @staticmethod
    def _timestamp() -> int:
        return int(datetime.now(UTC).timestamp())

    @staticmethod
    def _content_type_allowed(content_type: str, allowed_content_types: tuple[str, ...]) -> bool:
        return any(
            content_type == allowed
            or ("/" not in allowed and content_type.startswith(f"{allowed}/"))
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
