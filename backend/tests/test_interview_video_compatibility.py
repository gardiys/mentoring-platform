import io
import shutil
import subprocess
from functools import partial
from pathlib import Path

import anyio
import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException

from app.interviews.uploads import InterviewUploadStore, StoredUpload, _LegacyTranscodeGuard
from app.media.normalization import inspect_mp4_layout


@pytest.fixture(autouse=True)
def reset_database():
    """Real media tooling with in-memory storage; no database or remote files."""
    yield


class MemoryS3:
    def __init__(self, source: bytes):
        self.objects = {"media/source": source}
        self.downloads = 0

    def get_object(self, *, Bucket, Key, Range):
        assert Range == "bytes=0-15"
        data = self.objects[Key]
        return {
            "Body": io.BytesIO(data[:16]),
            "ContentRange": f"bytes 0-15/{len(data)}",
            "ETag": "source-v1",
        }

    def head_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {"ContentLength": len(self.objects[Key]), "ContentType": "video/mp4"}

    def download_fileobj(self, *, Bucket, Key, Fileobj):
        self.downloads += 1
        Fileobj.write(self.objects[Key])

    def upload_file(self, path, bucket, key, **kwargs):
        assert kwargs["ExtraArgs"]["ContentType"] == "video/mp4"
        self.objects[key] = Path(path).read_bytes()


def store_for(tmp_path, data):
    store = object.__new__(InterviewUploadStore)
    store.client = MemoryS3(data)
    store.bucket = "test"
    store._video_max_file_bytes = 1_000_000
    store._video_max_duration_seconds = 60
    store._media_probe_timeout_seconds = 10
    store._legacy_transcode_timeout_seconds = 20
    store._legacy_transcode_root = tmp_path / "staging"
    store._legacy_transcode_cleanup_age_seconds = 3600
    store._legacy_transcode_guard = _LegacyTranscodeGuard(
        max_concurrency=1, min_free_bytes=0, max_reserved_bytes=512 * 1024 * 1024
    )
    upload = StoredUpload(
        storage_key="media/source",
        filename="recording.mp4",
        content_type="video/mp4",
        size=len(data),
    )
    return store, upload


async def test_real_mkv_disguised_as_mp4_becomes_seekable_and_reuses_cached_copy(tmp_path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg and ffprobe are required")
    source = tmp_path / "disguised.mp4"
    await anyio.to_thread.run_sync(
        partial(
            subprocess.run,
            [
                "ffmpeg",
                "-v",
                "error",
                "-nostdin",
                "-f",
                "lavfi",
                "-i",
                "testsrc=size=160x90:rate=10",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=44100",
                "-t",
                "1",
                "-c:v",
                "libx264",
                "-threads",
                "1",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-f",
                "matroska",
                str(source),
            ],
            check=True,
            capture_output=True,
            timeout=20,
        )
    )
    original = source.read_bytes()
    store, upload = store_for(tmp_path, original)
    converted = await store.ensure_browser_playable(upload)
    assert converted.storage_key != upload.storage_key
    assert store.client.objects[upload.storage_key] == original
    result = tmp_path / "result.mp4"
    result.write_bytes(store.client.objects[converted.storage_key])
    assert inspect_mp4_layout(result).browser_seekable
    assert await store.ensure_browser_playable(upload) == converted
    assert await store.ensure_browser_playable(converted) == converted
    assert store.client.downloads == 1
    assert not list(store._legacy_transcode_root.glob("legacy-video-*"))

    def video_hash(path):
        return subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(path),
                "-map",
                "0:v:0",
                "-f",
                "hash",
                "-hash",
                "sha256",
                "-",
            ],
            check=True,
            capture_output=True,
            timeout=20,
        ).stdout

    assert await anyio.to_thread.run_sync(video_hash, source) == await anyio.to_thread.run_sync(
        video_hash, result
    )


async def test_regular_mp4_does_not_download_or_convert(tmp_path):
    store, upload = store_for(tmp_path, b"\x00\x00\x00\x18ftypisom" + b"0" * 20)
    assert await store.ensure_browser_playable(upload) == upload
    assert store.client.downloads == 0
    assert len(store.client.objects) == 1


async def test_oversized_disguised_video_is_rejected_before_download(tmp_path):
    store, upload = store_for(tmp_path, b"\x1a\x45\xdf\xa3" + b"0" * 40)
    store._video_max_file_bytes = 16
    with pytest.raises(HTTPException) as error:
        await store.ensure_browser_playable(upload)
    assert error.value.status_code == 413
    assert store.client.downloads == 0


async def test_no_disk_capacity_keeps_original_and_does_not_download(tmp_path):
    store, upload = store_for(tmp_path, b"\x1a\x45\xdf\xa3" + b"0" * 40)
    store._legacy_transcode_guard = _LegacyTranscodeGuard(
        max_concurrency=1, min_free_bytes=0, max_reserved_bytes=16
    )
    with pytest.raises(HTTPException) as error:
        await store.ensure_browser_playable(upload)
    assert error.value.status_code == 503
    assert store.client.downloads == 0
    assert list(store.client.objects) == [upload.storage_key]
