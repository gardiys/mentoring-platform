import hashlib
import json
import os
import subprocess
from collections import namedtuple
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException
from pytest import MonkeyPatch

from app.core.config import Settings
from app.interviews import media_guardrails
from app.interviews.media_guardrails import (
    MEDIA_CODEC_ALLOWLIST,
    MEDIA_CONTAINER_ALLOWLIST,
    MediaGuardrailError,
    MediaProbe,
    MediaStreamProbe,
    StagingCapacityError,
    StagingGuard,
    cleanup_stale_staging_directories,
    probe_media,
    stage_media_file,
    validate_media_probe,
)
from app.interviews.uploads import (
    SAFE_ATTACHMENT_CONTENT_TYPES,
    SAFE_OFFER_CONTENT_TYPES,
    CompletedMultipartUploadPart,
    InterviewUploadStore,
)


class FakePresignedPostClient:
    def __init__(self) -> None:
        self.request: dict[str, Any] | None = None

    def generate_presigned_post(self, **kwargs: Any) -> dict[str, Any]:
        self.request = kwargs
        return {"url": "https://s3.example.test/upload", "fields": {"key": kwargs["Key"]}}


def test_multipart_part_urls_cannot_outlive_upload_session() -> None:
    with pytest.raises(ValueError, match="S3_MULTIPART_PRESIGN_TTL_SECONDS"):
        Settings(
            s3_multipart_presign_ttl_seconds=7_200,
            s3_multipart_session_ttl_seconds=3_600,
        )


def upload_store() -> tuple[InterviewUploadStore, FakePresignedPostClient]:
    client = FakePresignedPostClient()
    store = object.__new__(InterviewUploadStore)
    store.bucket = "interview-files"
    store.expires_in = 900
    store.public_client = client
    return store, client


class FakeMultipartClient:
    def __init__(self) -> None:
        self.create_request: dict[str, Any] | None = None
        self.complete_requests: list[dict[str, Any]] = []
        self.abort_requests: list[dict[str, Any]] = []
        self.list_requests: list[dict[str, Any]] = []
        self.previous_uploads: list[dict[str, str]] = []
        self.deleted: list[dict[str, Any]] = []
        self.head = {"ContentLength": 130 * 1024 * 1024, "ContentType": "video/mp4"}
        self.completed = False
        self.ambiguous_completion = False
        self.head_missing_attempts = 0
        self.head_calls = 0

    def create_multipart_upload(self, **kwargs: Any) -> dict[str, str]:
        self.create_request = kwargs
        return {"UploadId": "provider-upload-id"}

    def list_multipart_uploads(self, **kwargs: Any) -> dict[str, Any]:
        self.list_requests.append(kwargs)
        return {"Uploads": self.previous_uploads, "IsTruncated": False}

    def complete_multipart_upload(self, **kwargs: Any) -> dict[str, str]:
        self.complete_requests.append(kwargs)
        if self.ambiguous_completion:
            self.completed = True
            raise BotoCoreError()
        if self.completed:
            raise ClientError(
                {"Error": {"Code": "NoSuchUpload"}},
                "CompleteMultipartUpload",
            )
        self.completed = True
        return {"ETag": "completed"}

    def head_object(self, **_kwargs: Any) -> dict[str, Any]:
        self.head_calls += 1
        if self.head_calls <= self.head_missing_attempts:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "HeadObject")
        if not self.completed:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "HeadObject")
        return self.head

    def abort_multipart_upload(self, **kwargs: Any) -> dict[str, object]:
        self.abort_requests.append(kwargs)
        return {}

    def delete_object(self, **kwargs: Any) -> dict[str, object]:
        self.deleted.append(kwargs)
        return {}


class FakeMultipartPublicClient:
    def __init__(self) -> None:
        self.presigned: list[dict[str, Any]] = []

    def generate_presigned_url(
        self,
        operation: str,
        *,
        Params: dict[str, Any],
        ExpiresIn: int,
    ) -> str:
        self.presigned.append({"operation": operation, "params": Params, "expires_in": ExpiresIn})
        return f"https://s3.example.test/part/{Params['PartNumber']}"


def multipart_upload_store() -> tuple[
    InterviewUploadStore,
    FakeMultipartClient,
    FakeMultipartPublicClient,
]:
    client = FakeMultipartClient()
    public_client = FakeMultipartPublicClient()
    store = object.__new__(InterviewUploadStore)
    store.bucket = "interview-files"
    store.multipart_part_size = 64 * 1024 * 1024
    store.multipart_presign_expires_in = 21_600
    store.multipart_session_expires_in = 86_400
    store._multipart_token_secret = "multipart-test-secret"
    store.client = client
    store.public_client = public_client
    return store, client, public_client


def test_presigned_post_cannot_upload_more_than_the_declared_size() -> None:
    store, client = upload_store()

    intent = store.create_upload_intent(
        user_id=uuid4(),
        category="media",
        filename="recording.mp4",
        content_type="video/mp4",
        size=1_234,
        allowed_content_types=("video",),
        max_bytes=10_000,
    )

    assert intent.size == 1_234
    assert client.request is not None
    assert client.request["Conditions"] == [
        {"Content-Type": "video/mp4"},
        ["content-length-range", 1, 1_234],
    ]


async def test_multipart_upload_writes_directly_to_final_key_and_is_idempotent() -> None:
    store, client, public_client = multipart_upload_store()
    user_id = uuid4()
    size = 130 * 1024 * 1024

    intent = await store.create_multipart_upload_intent(
        user_id=user_id,
        category="media",
        resource="interview-stage-media:process:stage",
        filename="recording.mp4",
        content_type="video/mp4",
        size=size,
        allowed_content_types=("video",),
        max_bytes=2 * 1024 * 1024 * 1024,
    )
    parts = tuple(
        CompletedMultipartUploadPart(part_number=number, etag=f'"etag-{number}"')
        for number in range(1, 4)
    )
    completion = dict(
        user_id=user_id,
        category="media",
        resource="interview-stage-media:process:stage",
        storage_key=intent.storage_key,
        upload_id=intent.upload_id,
        upload_token=intent.upload_token,
        filename=intent.filename,
        content_type=intent.content_type,
        expected_size=intent.size,
        parts=parts,
        allowed_content_types=("video",),
        max_bytes=2 * 1024 * 1024 * 1024,
    )

    first = await store.complete_multipart_upload(**completion)
    retried = await store.complete_multipart_upload(**completion)

    assert intent.storage_key.startswith(f"media/{user_id}/")
    assert not intent.storage_key.startswith("pending/")
    assert intent.part_size == 64 * 1024 * 1024
    assert intent.part_count == 3
    assert [part.part_number for part in intent.parts] == [1, 2, 3]
    assert all(call["expires_in"] == 21_600 for call in public_client.presigned)
    assert [call["params"]["ContentLength"] for call in public_client.presigned] == [
        64 * 1024 * 1024,
        64 * 1024 * 1024,
        2 * 1024 * 1024,
    ]
    assert client.create_request == {
        "Bucket": "interview-files",
        "Key": intent.storage_key,
        "ContentType": "video/mp4",
    }
    assert client.list_requests[0]["Prefix"] == intent.storage_key.rsplit("/", 1)[0] + "/"
    assert first == retried
    assert first.storage_key == intent.storage_key
    assert len(client.complete_requests) == 2


async def test_multipart_init_aborts_previous_matching_resource_upload() -> None:
    store, client, _ = multipart_upload_store()
    user_id = uuid4()
    resource = "interview-stage-media:process:stage"
    resource_hash = hashlib.sha256(resource.encode()).hexdigest()[:16]
    stale_key = f"media/{user_id}/{resource_hash}/{uuid4().hex}"
    client.previous_uploads = [{"Key": stale_key, "UploadId": "stale-upload-id"}]

    await store.create_multipart_upload_intent(
        user_id=user_id,
        category="media",
        resource=resource,
        filename="recording.mp4",
        content_type="video/mp4",
        size=1_000,
        allowed_content_types=("video",),
        max_bytes=2 * 1024 * 1024 * 1024,
    )

    assert client.abort_requests == [
        {
            "Bucket": "interview-files",
            "Key": stale_key,
            "UploadId": "stale-upload-id",
        }
    ]


async def test_multipart_token_binds_actor_category_and_resource() -> None:
    store, client, _ = multipart_upload_store()
    owner_id = uuid4()
    intent = await store.create_multipart_upload_intent(
        user_id=owner_id,
        category="media",
        resource="interview-stage-media:process:stage",
        filename="recording.mp4",
        content_type="video/mp4",
        size=130 * 1024 * 1024,
        allowed_content_types=("video",),
        max_bytes=2 * 1024 * 1024 * 1024,
    )

    with pytest.raises(HTTPException) as caught:
        await store.complete_multipart_upload(
            user_id=uuid4(),
            category="media",
            resource="interview-stage-media:other:stage",
            storage_key=intent.storage_key,
            upload_id=intent.upload_id,
            upload_token=intent.upload_token,
            filename=intent.filename,
            content_type=intent.content_type,
            expected_size=intent.size,
            parts=tuple(
                CompletedMultipartUploadPart(
                    part_number=number,
                    etag=f'"etag-{number}"',
                )
                for number in range(1, 4)
            ),
            allowed_content_types=("video",),
            max_bytes=2 * 1024 * 1024 * 1024,
        )

    assert caught.value.status_code == 404
    assert caught.value.detail["code"] == "interview_upload_not_found"
    assert client.complete_requests == []


async def test_multipart_completion_reconciles_ambiguous_provider_timeout() -> None:
    store, client, _ = multipart_upload_store()
    user_id = uuid4()
    client.ambiguous_completion = True
    client.head_missing_attempts = 2
    intent = await store.create_multipart_upload_intent(
        user_id=user_id,
        category="media",
        resource="interview-stage-media:process:stage",
        filename="recording.mp4",
        content_type="video/mp4",
        size=130 * 1024 * 1024,
        allowed_content_types=("video",),
        max_bytes=2 * 1024 * 1024 * 1024,
    )

    completed = await store.complete_multipart_upload(
        user_id=user_id,
        category="media",
        resource="interview-stage-media:process:stage",
        storage_key=intent.storage_key,
        upload_id=intent.upload_id,
        upload_token=intent.upload_token,
        filename=intent.filename,
        content_type=intent.content_type,
        expected_size=intent.size,
        parts=tuple(
            CompletedMultipartUploadPart(part_number=number, etag=f'"etag-{number}"')
            for number in range(1, 4)
        ),
        allowed_content_types=("video",),
        max_bytes=2 * 1024 * 1024 * 1024,
    )

    assert completed.storage_key == intent.storage_key
    assert client.head_calls == 3


async def test_multipart_completion_deletes_metadata_mismatch() -> None:
    store, client, _ = multipart_upload_store()
    user_id = uuid4()
    client.head["ContentLength"] = 1
    intent = await store.create_multipart_upload_intent(
        user_id=user_id,
        category="media",
        resource="interview-stage-media:process:stage",
        filename="recording.mp4",
        content_type="video/mp4",
        size=130 * 1024 * 1024,
        allowed_content_types=("video",),
        max_bytes=2 * 1024 * 1024 * 1024,
    )

    with pytest.raises(HTTPException) as caught:
        await store.complete_multipart_upload(
            user_id=user_id,
            category="media",
            resource="interview-stage-media:process:stage",
            storage_key=intent.storage_key,
            upload_id=intent.upload_id,
            upload_token=intent.upload_token,
            filename=intent.filename,
            content_type=intent.content_type,
            expected_size=intent.size,
            parts=tuple(
                CompletedMultipartUploadPart(
                    part_number=number,
                    etag=f'"etag-{number}"',
                )
                for number in range(1, 4)
            ),
            allowed_content_types=("video",),
            max_bytes=2 * 1024 * 1024 * 1024,
        )

    assert caught.value.status_code == 422
    assert client.deleted == [{"Bucket": "interview-files", "Key": intent.storage_key}]


async def test_multipart_abort_requires_signed_actor_binding() -> None:
    store, client, _ = multipart_upload_store()
    owner_id = uuid4()
    intent = await store.create_multipart_upload_intent(
        user_id=owner_id,
        category="offers",
        resource="interview-offer:process",
        filename="offer.pdf",
        content_type="application/pdf",
        size=1_000,
        allowed_content_types=("application/pdf",),
        max_bytes=20 * 1024 * 1024,
    )

    await store.abort_multipart_upload(
        user_id=owner_id,
        storage_key=intent.storage_key,
        upload_id=intent.upload_id,
        upload_token=intent.upload_token,
    )
    with pytest.raises(HTTPException):
        await store.abort_multipart_upload(
            user_id=UUID(int=0),
            storage_key=intent.storage_key,
            upload_id=intent.upload_id,
            upload_token=intent.upload_token,
        )

    assert client.abort_requests == [
        {
            "Bucket": "interview-files",
            "Key": intent.storage_key,
            "UploadId": intent.upload_id,
        }
    ]


def test_startup_cleanup_only_removes_stale_owned_staging_directories(
    tmp_path: Path,
) -> None:
    stale = tmp_path / "interview-media-stale"
    fresh = tmp_path / "interview-media-fresh"
    unrelated = tmp_path / "keep-me"
    stale.mkdir()
    fresh.mkdir()
    unrelated.mkdir()
    os.utime(stale, (100, 100))
    os.utime(fresh, (9_900, 9_900))

    removed = cleanup_stale_staging_directories(
        tmp_path,
        older_than_seconds=1_000,
        now_timestamp=10_000,
    )

    assert removed == 1
    assert not stale.exists()
    assert fresh.exists()
    assert unrelated.exists()


@pytest.mark.parametrize(
    "content_type",
    [
        "application/javascript",
        "application/x-executable",
        "application/x-msdownload",
        "image/svg+xml",
        "text/html",
    ],
)
def test_attachment_allowlist_rejects_active_and_executable_content(
    content_type: str,
) -> None:
    store, client = upload_store()

    with pytest.raises(HTTPException) as caught:
        store.create_upload_intent(
            user_id=uuid4(),
            category="attachments",
            filename="unsafe-file",
            content_type=content_type,
            size=10,
            allowed_content_types=SAFE_ATTACHMENT_CONTENT_TYPES,
            max_bytes=1_000,
        )

    assert caught.value.status_code == 415
    assert caught.value.detail["code"] == "unsupported_interview_file_type"
    assert client.request is None


def test_attachment_and_offer_allowlists_only_contain_safe_exact_mime_types() -> None:
    assert {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "image/png",
        "text/plain",
    }.issubset(SAFE_ATTACHMENT_CONTENT_TYPES)
    assert "image/svg+xml" not in SAFE_ATTACHMENT_CONTENT_TYPES
    assert "text/html" not in SAFE_ATTACHMENT_CONTENT_TYPES
    assert "application/javascript" not in SAFE_ATTACHMENT_CONTENT_TYPES
    assert "image/png" in SAFE_OFFER_CONTENT_TYPES
    assert "image/svg+xml" not in SAFE_OFFER_CONTENT_TYPES
    assert not InterviewUploadStore._content_type_allowed(
        "application/pdf/unsafe",
        SAFE_ATTACHMENT_CONTENT_TYPES,
    )
    assert MEDIA_CONTAINER_ALLOWLIST.keys() == MEDIA_CODEC_ALLOWLIST.keys()


def test_probe_media_checks_real_container_codec_and_duration(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    recording = tmp_path / "recording.bin"
    recording.write_bytes(b"not-trusted-by-extension")
    payload = {
        "format": {
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            "duration": "125.5",
        },
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "duration": "125.5"},
            {"codec_type": "audio", "codec_name": "aac", "duration": "125.4"},
        ],
    }
    invocation: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        invocation["command"] = command
        invocation["kwargs"] = kwargs
        kwargs["stdout"].write(json.dumps(payload).encode())
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setenv("NEXARA_API_KEY", "must-not-leak")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "must-not-leak")
    monkeypatch.setattr(media_guardrails.subprocess, "run", fake_run)

    probe = probe_media(
        recording,
        declared_content_type="video/mp4; codecs=h264",
        max_duration_seconds=600,
        max_file_bytes=1_000,
        timeout_seconds=7,
        max_probe_bytes=65_536,
    )

    assert probe.format_names == ("mov", "mp4", "m4a", "3gp", "3g2", "mj2")
    assert probe.duration_seconds == 125.5
    assert probe.video_codecs == ("h264",)
    assert probe.audio_codecs == ("aac",)
    assert invocation["kwargs"]["timeout"] == 7
    assert invocation["kwargs"]["env"] == media_guardrails.MEDIA_TOOL_ENVIRONMENT
    assert "NEXARA_API_KEY" not in invocation["kwargs"]["env"]
    assert "S3_SECRET_ACCESS_KEY" not in invocation["kwargs"]["env"]
    assert invocation["kwargs"]["stdin"] is subprocess.DEVNULL
    assert invocation["kwargs"]["stderr"] is subprocess.DEVNULL
    command = invocation["command"]
    assert "-nostdin" not in command
    assert command[command.index("-protocol_whitelist") + 1] == "file"
    assert command[command.index("-probesize") + 1] == "65536"


@pytest.mark.parametrize(
    ("content_type", "max_duration", "expected_code"),
    [
        ("audio/mpeg", 1_000, "media_content_type_mismatch"),
        ("video/mp4", 60, "media_duration_exceeded"),
        ("video/x-flv", 1_000, "unsupported_media_type"),
    ],
)
def test_probe_validation_rejects_mismatch_excess_duration_and_unknown_types(
    content_type: str,
    max_duration: float,
    expected_code: str,
) -> None:
    probe = MediaProbe(
        format_names=("mov", "mp4"),
        duration_seconds=120,
        streams=(MediaStreamProbe(kind="video", codec="h264", duration_seconds=120),),
    )

    with pytest.raises(MediaGuardrailError) as caught:
        validate_media_probe(
            probe,
            declared_content_type=content_type,
            max_duration_seconds=max_duration,
        )

    assert caught.value.code == expected_code


def test_probe_validation_rejects_a_codec_outside_the_container_allowlist() -> None:
    probe = MediaProbe(
        format_names=("matroska", "webm"),
        duration_seconds=120,
        streams=(MediaStreamProbe(kind="video", codec="h264", duration_seconds=120),),
    )

    with pytest.raises(MediaGuardrailError) as caught:
        validate_media_probe(
            probe,
            declared_content_type="video/webm",
            max_duration_seconds=1_000,
        )

    assert caught.value.code == "unsupported_media_codec"


async def test_staging_guard_reserves_disk_headroom_and_releases_bytes(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    disk_usage = namedtuple("disk_usage", ("total", "used", "free"))
    monkeypatch.setattr(
        media_guardrails.shutil,
        "disk_usage",
        lambda _path: disk_usage(total=10_000, used=1_000, free=9_000),
    )
    guard = StagingGuard(
        max_concurrency=2,
        min_free_bytes=1_000,
        max_reserved_bytes=5_000,
    )

    async with guard.reserve(tmp_path, expected_bytes=3_000):
        assert guard.reserved_bytes == 3_000
        with pytest.raises(StagingCapacityError) as caught:
            async with guard.reserve(tmp_path, expected_bytes=2_500):
                pass
        assert caught.value.reason == "staging_byte_budget_exceeded"

    assert guard.reserved_bytes == 0


async def test_staging_guard_rejects_a_download_that_would_consume_disk_headroom(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    disk_usage = namedtuple("disk_usage", ("total", "used", "free"))
    monkeypatch.setattr(
        media_guardrails.shutil,
        "disk_usage",
        lambda _path: disk_usage(total=10_000, used=8_500, free=1_500),
    )
    guard = StagingGuard(max_concurrency=1, min_free_bytes=1_000)

    with pytest.raises(StagingCapacityError) as caught:
        async with guard.reserve(tmp_path, expected_bytes=1_000):
            pass

    assert caught.value.available_bytes == 1_500
    assert caught.value.required_bytes == 2_000


async def test_staged_file_is_cleaned_when_ffprobe_is_unavailable(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    content = b"fake-media"
    disk_usage = namedtuple("disk_usage", ("total", "used", "free"))
    monkeypatch.setattr(
        media_guardrails.shutil,
        "disk_usage",
        lambda _path: disk_usage(total=10_000, used=1_000, free=9_000),
    )

    def missing_ffprobe(*_args: Any, **_kwargs: Any) -> None:
        raise FileNotFoundError

    monkeypatch.setattr(media_guardrails.subprocess, "run", missing_ffprobe)
    guard = StagingGuard(max_concurrency=1, min_free_bytes=1_000)
    staged_directory: Path | None = None

    async def download(destination: Path) -> None:
        destination.write_bytes(content)

    with pytest.raises(MediaGuardrailError) as caught:
        async with stage_media_file(
            guard,
            filename="recording.mp4",
            maximum_bytes=len(content),
            expected_bytes=len(content),
            download=download,
            staging_root=tmp_path,
        ) as staged_path:
            staged_directory = staged_path.parent
            probe_media(
                staged_path,
                declared_content_type="video/mp4",
                max_duration_seconds=600,
            )

    assert caught.value.code == "media_probe_unavailable"
    assert staged_directory is not None
    assert not staged_directory.exists()
    assert guard.reserved_bytes == 0
