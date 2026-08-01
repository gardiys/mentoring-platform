from pathlib import Path
from typing import Any

from botocore.exceptions import ClientError
from pytest import MonkeyPatch

from app.interviews.uploads import InterviewUploadStore, StoredUpload


class FakeBody:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.closed = False

    def iter_chunks(self, chunk_size: int) -> list[bytes]:
        del chunk_size
        return [self.content]

    def read(self) -> bytes:
        return self.content

    def close(self) -> None:
        self.closed = True


class FakeS3Client:
    def __init__(self, content: bytes = b"video") -> None:
        self.presigned: list[dict[str, Any]] = []
        self.downloaded: list[dict[str, Any]] = []
        self.body = FakeBody(content)

    def generate_presigned_url(
        self,
        operation: str,
        *,
        Params: dict[str, Any],
        ExpiresIn: int,
    ) -> str:
        self.presigned.append({"operation": operation, "params": Params, "expires_in": ExpiresIn})
        return "https://s3.firstvds.ru:443/interviews/signed?X-Amz-Signature=test"

    def get_object(self, **params: Any) -> dict[str, Any]:
        self.downloaded.append(params)
        return {
            "Body": self.body,
            "ContentLength": len(self.body.content),
            "ContentRange": f"bytes 0-{len(self.body.content) - 1}/{len(self.body.content)}",
            "ETag": '"legacy"',
        }


async def test_private_legacy_media_uses_authenticated_s3_requests() -> None:
    legacy_client = FakeS3Client()
    regular_client = FakeS3Client()
    store = object.__new__(InterviewUploadStore)
    store.bucket = "new-files"
    store.expires_in = 900
    store.client = regular_client
    store.public_client = regular_client
    store.legacy_client = legacy_client
    upload = StoredUpload(
        storage_key=(
            "external:https://s3.firstvds.ru:443/interviews/company/tech/"
            "%D1%81%D0%BE%D0%B1%D0%B5%D1%81.mp4"
        ),
        filename="собес.mp4",
        content_type="video/mp4",
        size=0,
    )

    signed_url = store.download_url(upload, inline=True)
    opened = await store.open_download(upload, range_header="bytes=0-4")

    assert "X-Amz-Signature=test" in signed_url
    assert legacy_client.presigned[0]["params"] == {
        "Bucket": "interviews",
        "Key": "company/tech/собес.mp4",
        "ResponseContentDisposition": "inline; filename*=UTF-8''%D1%81%D0%BE%D0%B1%D0%B5%D1%81.mp4",
        "ResponseContentType": "video/mp4",
    }
    assert legacy_client.downloaded == [
        {
            "Bucket": "interviews",
            "Key": "company/tech/собес.mp4",
            "Range": "bytes=0-4",
        }
    ]
    assert regular_client.presigned == regular_client.downloaded == []
    assert b"".join(opened.chunks()) == b"video"
    assert opened.content_length == 5
    assert opened.content_range == "bytes 0-4/5"
    assert opened.etag == '"legacy"'
    assert legacy_client.body.closed is True
    await store.delete(upload.storage_key)


async def test_mislabeled_legacy_aac_is_served_as_mp4_audio() -> None:
    header = b"\x00\x00\x00\x1cftypisom" + b"\x00" * 64 + b"mp4a"
    legacy_client = FakeS3Client(header)
    store = object.__new__(InterviewUploadStore)
    store.bucket = "new-files"
    store.expires_in = 900
    store.client = FakeS3Client()
    store.public_client = store.client
    store.legacy_client = legacy_client
    upload = StoredUpload(
        storage_key=("external:https://s3.firstvds.ru:443/interviews/company/screening/record.mp3"),
        filename="record.mp3",
        content_type="audio/mpeg",
        size=0,
    )

    playable = await store.ensure_browser_playable(upload)

    assert playable.filename == "record.m4a"
    assert playable.content_type == "audio/mp4"
    assert playable.size == len(header)


async def test_legacy_alac_is_transcoded_for_browser_playback(
    monkeypatch: MonkeyPatch,
) -> None:
    header = b"\x00\x00\x00\x1cftypisom" + b"\x00" * 64 + b"alac"
    store = object.__new__(InterviewUploadStore)
    store.bucket = "new-files"
    store.expires_in = 900
    store.client = FakeS3Client()
    store.public_client = store.client
    store.legacy_client = FakeS3Client(header)
    upload = StoredUpload(
        storage_key=("external:https://s3.firstvds.ru:443/interviews/company/screening/record.mp3"),
        filename="record.mp3",
        content_type="audio/mpeg",
        size=0,
    )
    converted = StoredUpload(
        storage_key="media/converted/audio.mp3",
        filename="record.mp3",
        content_type="audio/mpeg",
        size=123,
    )
    monkeypatch.setattr(store, "_transcode_legacy_alac", lambda *_args: converted)

    assert await store.ensure_browser_playable(upload) == converted


def test_legacy_alac_transcoding_is_cached_in_current_s3(
    monkeypatch: MonkeyPatch,
) -> None:
    class SourceClient:
        def download_fileobj(self, *, Fileobj: Any, **_kwargs: Any) -> None:
            Fileobj.write(b"alac-source")

    class TargetClient:
        uploaded: bytes | None = None

        def head_object(self, **_kwargs: Any) -> dict[str, Any]:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")

        def upload_fileobj(self, *, Fileobj: Any, **_kwargs: Any) -> None:
            self.uploaded = Fileobj.read()

    target_client = TargetClient()
    store = object.__new__(InterviewUploadStore)
    store.bucket = "new-files"
    store.client = target_client
    store.legacy_client = SourceClient()
    upload = StoredUpload(
        storage_key=("external:https://s3.firstvds.ru:443/interviews/company/screening/record.mp3"),
        filename="record.mp3",
        content_type="audio/mpeg",
        size=0,
    )

    def fake_ffmpeg(arguments: list[str], **_kwargs: Any) -> None:
        Path(arguments[-1]).write_bytes(b"browser-mp3")

    monkeypatch.setattr("app.interviews.uploads.subprocess.run", fake_ffmpeg)

    converted = store._transcode_legacy_alac(
        upload,
        ("interviews", "company/screening/record.mp3"),
    )

    assert converted.storage_key.startswith("media/converted/")
    assert converted.filename == "record.mp3"
    assert converted.content_type == "audio/mpeg"
    assert converted.size == len(b"browser-mp3")
    assert target_client.uploaded == b"browser-mp3"
