from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from app.interviews.media_guardrails import MediaProbe, MediaStreamProbe
from app.interviews.uploads import InterviewUploadStore
from app.knowledge.models import KnowledgeEntry, KnowledgeEntryKind, KnowledgeTopic
from app.media import normalization, normalization_jobs
from app.media.models import ContentMediaProcessingStatus, ProtectedContentMedia
from app.media.normalization import (
    ContentMediaNormalizationError,
    NormalizedContentMedia,
    inspect_mp4_layout,
    normalize_content_mp4,
)
from app.media.normalization_queue import content_media_normalization_job_id
from tests.conftest import TestSession


def _box(kind: bytes, payload: bytes = b"") -> bytes:
    return (8 + len(payload)).to_bytes(4, "big") + kind + payload


def _seekable_mp4() -> bytes:
    return b"".join(
        (
            _box(b"ftyp", b"isom\x00\x00\x02\x00isommp42"),
            _box(b"moov", b"metadata"),
            _box(b"mdat", b"media-payload"),
        )
    )


def _fragmented_mp4() -> bytes:
    return b"".join(
        (
            _box(b"ftyp", b"isom\x00\x00\x02\x00isommp42"),
            _box(b"moov", b"metadata"),
            _box(b"moof", b"fragment-index"),
            _box(b"mdat", b"fragment-payload"),
        )
    )


def _probe(*, video_codec: str = "h264", audio_codec: str = "aac") -> MediaProbe:
    return MediaProbe(
        format_names=("mov", "mp4"),
        duration_seconds=120.0,
        streams=(
            MediaStreamProbe(kind="video", codec=video_codec, duration_seconds=120.0),
            MediaStreamProbe(kind="audio", codec=audio_codec, duration_seconds=120.0),
        ),
    )


def test_inspect_mp4_layout_distinguishes_seekable_and_fragmented_files(
    tmp_path: Path,
) -> None:
    seekable = tmp_path / "seekable.mp4"
    fragmented = tmp_path / "fragmented.mp4"
    seekable.write_bytes(_seekable_mp4())
    fragmented.write_bytes(_fragmented_mp4())

    seekable_layout = inspect_mp4_layout(seekable)
    fragmented_layout = inspect_mp4_layout(fragmented)

    assert seekable_layout.browser_seekable is True
    assert fragmented_layout.browser_seekable is False
    assert fragmented_layout.has_fragments is True


def test_inspect_mp4_layout_can_stop_at_first_fragment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "long-fragmented.mp4"
    source.write_bytes(
        b"".join(
            (
                _box(b"ftyp", b"isom\x00\x00\x02\x00isommp42"),
                _box(b"moov", b"metadata"),
                _box(b"moof", b"first-fragment"),
                *(_box(b"moof", b"fragment") for _ in range(10)),
            )
        )
    )
    monkeypatch.setattr(normalization, "MAX_MP4_TOP_LEVEL_BOXES", 3)

    layout = inspect_mp4_layout(source, stop_at_first_fragment=True)

    assert layout.has_fragments is True
    with pytest.raises(ContentMediaNormalizationError) as raised:
        inspect_mp4_layout(source)
    assert raised.value.code == "INVALID_MP4_LAYOUT"


def test_inspect_mp4_layout_rejects_truncated_box(tmp_path: Path) -> None:
    source = tmp_path / "truncated.mp4"
    source.write_bytes((100).to_bytes(4, "big") + b"ftyp" + b"short")

    with pytest.raises(ContentMediaNormalizationError) as raised:
        inspect_mp4_layout(source)

    assert raised.value.code == "INVALID_MP4_LAYOUT"
    assert raised.value.retryable is False


@pytest.mark.asyncio
async def test_normalization_reuses_already_seekable_mp4(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.mp4"
    target = tmp_path / "target.mp4"
    source.write_bytes(_seekable_mp4())

    async def fake_probe(*_args: object, **_kwargs: object) -> MediaProbe:
        return _probe()

    monkeypatch.setattr(normalization, "probe_media_async", fake_probe)

    result = await normalize_content_mp4(
        source,
        target,
        source_size=source.stat().st_size,
        max_file_bytes=1024 * 1024,
        max_duration_seconds=3600,
        probe_timeout_seconds=10,
        remux_timeout_seconds=60,
    )

    assert result.reused_source is True
    assert result.path is None
    assert not target.exists()


@pytest.mark.asyncio
async def test_normalization_remuxes_fragmented_mp4_and_validates_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.mp4"
    target = tmp_path / "target.mp4"
    source.write_bytes(_fragmented_mp4())

    async def fake_probe(*_args: object, **_kwargs: object) -> MediaProbe:
        return _probe()

    def fake_remux(source_path: Path, target_path: Path, **_kwargs: object) -> None:
        assert source_path == source
        target_path.write_bytes(_seekable_mp4())

    monkeypatch.setattr(normalization, "probe_media_async", fake_probe)
    monkeypatch.setattr(normalization, "_run_lossless_remux", fake_remux)

    result = await normalize_content_mp4(
        source,
        target,
        source_size=source.stat().st_size,
        max_file_bytes=1024 * 1024,
        max_duration_seconds=3600,
        probe_timeout_seconds=10,
        remux_timeout_seconds=60,
    )

    assert result.reused_source is False
    assert result.path == target
    assert result.size == len(_seekable_mp4())
    assert inspect_mp4_layout(target).browser_seekable is True


@pytest.mark.asyncio
async def test_normalization_converts_seekable_quicktime_container_to_mp4(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.mov"
    target = tmp_path / "target.mp4"
    source.write_bytes(_seekable_mp4())

    async def fake_probe(*_args: object, **_kwargs: object) -> MediaProbe:
        return _probe()

    def fake_remux(_source_path: Path, target_path: Path, **_kwargs: object) -> None:
        target_path.write_bytes(_seekable_mp4())

    monkeypatch.setattr(normalization, "probe_media_async", fake_probe)
    monkeypatch.setattr(normalization, "_run_lossless_remux", fake_remux)

    result = await normalize_content_mp4(
        source,
        target,
        source_size=source.stat().st_size,
        declared_content_type="video/quicktime",
        max_file_bytes=1024 * 1024,
        max_duration_seconds=3600,
        probe_timeout_seconds=10,
        remux_timeout_seconds=60,
    )

    assert result.reused_source is False
    assert result.path == target


@pytest.mark.asyncio
async def test_normalization_rejects_codec_that_stream_copy_cannot_fix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(_fragmented_mp4())

    async def fake_probe(*_args: object, **_kwargs: object) -> MediaProbe:
        return _probe(video_codec="hevc")

    monkeypatch.setattr(normalization, "probe_media_async", fake_probe)

    with pytest.raises(ContentMediaNormalizationError) as raised:
        await normalize_content_mp4(
            source,
            tmp_path / "target.mp4",
            source_size=source.stat().st_size,
            max_file_bytes=1024 * 1024,
            max_duration_seconds=3600,
            probe_timeout_seconds=10,
            remux_timeout_seconds=60,
        )

    assert raised.value.code == "UNSUPPORTED_BROWSER_VIDEO_CODEC"
    assert raised.value.retryable is False


@pytest.mark.asyncio
async def test_normalization_rejects_truncated_duration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.mp4"
    target = tmp_path / "target.mp4"
    source.write_bytes(_fragmented_mp4())
    probes = iter(
        (
            _probe(),
            MediaProbe(
                format_names=("mov", "mp4"),
                duration_seconds=60.0,
                streams=_probe().streams,
            ),
        )
    )

    async def fake_probe(*_args: object, **_kwargs: object) -> MediaProbe:
        return next(probes)

    def fake_remux(_source_path: Path, target_path: Path, **_kwargs: object) -> None:
        target_path.write_bytes(_seekable_mp4())

    monkeypatch.setattr(normalization, "probe_media_async", fake_probe)
    monkeypatch.setattr(normalization, "_run_lossless_remux", fake_remux)

    with pytest.raises(ContentMediaNormalizationError) as raised:
        await normalize_content_mp4(
            source,
            target,
            source_size=source.stat().st_size,
            max_file_bytes=1024 * 1024,
            max_duration_seconds=3600,
            probe_timeout_seconds=10,
            remux_timeout_seconds=60,
        )

    assert raised.value.code == "NORMALIZATION_DURATION_MISMATCH"
    assert raised.value.retryable is False


def test_content_media_normalization_job_id_is_stable() -> None:
    media_id = "88c00bc5-048f-4eee-a87b-64d80fae8628"

    assert content_media_normalization_job_id(media_id) == (
        "content-media-normalization:88c00bc5-048f-4eee-a87b-64d80fae8628"
    )


class _WorkerStore:
    def __init__(self, source: bytes) -> None:
        self.source = source
        self.uploads: list[tuple[str, bytes, str]] = []
        self.deletes: list[str] = []

    async def download_to_path(self, _upload: object, destination: Path) -> None:
        destination.write_bytes(self.source)

    async def upload_path(
        self,
        source: Path,
        *,
        storage_key: str,
        content_type: str,
        expected_size: int,
    ) -> None:
        payload = source.read_bytes()
        assert len(payload) == expected_size
        self.uploads.append((storage_key, payload, content_type))

    async def delete_for_processing(
        self,
        storage_key: str | None,
        *,
        suppress_errors: bool = False,
    ) -> bool:
        del suppress_errors
        if storage_key is not None:
            self.deletes.append(storage_key)
        return True


@pytest.mark.asyncio
async def test_worker_atomically_publishes_normalized_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    topic = KnowledgeTopic(
        slug="normalization-test",
        title="Normalization",
        position=0,
        is_published=True,
    )
    entry = KnowledgeEntry(
        topic=topic,
        kind=KnowledgeEntryKind.ARTICLE,
        slug="normalization-entry",
        title="Video",
        content_markdown="Video",
        position=0,
        is_published=True,
    )
    source = _fragmented_mp4()
    media_id = uuid4()
    async with TestSession() as session:
        session.add(entry)
        await session.flush()
        session.add(
            ProtectedContentMedia(
                id=media_id,
                knowledge_entry_id=entry.id,
                storage_key=f"knowledge-media/{media_id}",
                filename="lesson.mp4",
                content_type="video/mp4",
                size=len(source),
                position=0,
                processing_status=ContentMediaProcessingStatus.QUEUED,
                normalization_source_key=f"knowledge-media/{media_id}",
            )
        )
        await session.commit()

    async def fake_normalize(
        _source_path: Path,
        target_path: Path,
        **_kwargs: Any,
    ) -> NormalizedContentMedia:
        output = _seekable_mp4()
        target_path.write_bytes(output)
        return NormalizedContentMedia(
            path=target_path,
            size=len(output),
            probe=_probe(),
            reused_source=False,
        )

    store = _WorkerStore(source)
    monkeypatch.setattr(normalization_jobs, "async_session_factory", TestSession)
    monkeypatch.setattr(normalization_jobs, "normalize_content_mp4", fake_normalize)
    monkeypatch.setattr(normalization_jobs, "_staging_root", lambda: tmp_path)
    context: dict[str, Any] = {
        "upload_store": store,
        "staging_guard": normalization_jobs.StagingGuard(
            max_concurrency=1,
            min_free_bytes=0,
            max_reserved_bytes=2 * 1024 * 1024 * 1024,
        ),
        "job_try": 1,
    }

    await normalization_jobs.normalize_content_media(context, str(media_id))

    async with TestSession() as session:
        media = await session.get(ProtectedContentMedia, media_id)
        assert media is not None
        assert media.processing_status is ContentMediaProcessingStatus.READY
        assert media.storage_key == f"normalized-content-media/{media_id}/r1-g1.mp4"
        assert media.normalization_source_key == f"knowledge-media/{media_id}"
        assert media.normalization_revision == 1
        assert media.normalization_attempts == 1
        assert media.size == len(_seekable_mp4())
    assert store.uploads == [
        (
            f"normalized-content-media/{media_id}/r1-g1.mp4",
            _seekable_mp4(),
            "video/mp4",
        )
    ]
    # The original remains available during the configured playback grace period.
    assert store.deletes == []


class _ManagedUploadClient:
    def __init__(self) -> None:
        self.uploaded: tuple[str, str, str, dict[str, str]] | None = None

    def upload_file(
        self,
        source: str,
        bucket: str,
        key: str,
        *,
        ExtraArgs: dict[str, str],
        Config: object,
    ) -> None:
        assert Config is not None
        self.uploaded = (source, bucket, key, ExtraArgs)

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        assert self.uploaded is not None
        assert (Bucket, Key) == self.uploaded[1:3]
        return {"ContentLength": 5, "ContentType": "video/mp4"}

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        raise AssertionError(f"unexpected delete {Bucket}/{Key}")


@pytest.mark.asyncio
async def test_worker_upload_path_uses_managed_multipart_and_verifies_head(
    tmp_path: Path,
) -> None:
    source = tmp_path / "normalized.mp4"
    source.write_bytes(b"video")
    client = _ManagedUploadClient()
    store = object.__new__(InterviewUploadStore)
    store.bucket = "private-media"
    store.client = client

    await store.upload_path(
        source,
        storage_key="normalized-content-media/example/r1.mp4",
        content_type="video/mp4",
        expected_size=5,
    )

    assert client.uploaded == (
        str(source),
        "private-media",
        "normalized-content-media/example/r1.mp4",
        {"ContentType": "video/mp4"},
    )


@pytest.mark.asyncio
async def test_stale_claim_generation_cannot_mutate_or_delete_winner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    topic = KnowledgeTopic(
        slug="normalization-race-test",
        title="Normalization race",
        position=0,
        is_published=True,
    )
    entry = KnowledgeEntry(
        topic=topic,
        kind=KnowledgeEntryKind.ARTICLE,
        slug="normalization-race-entry",
        title="Race video",
        content_markdown="Video",
        position=0,
        is_published=True,
    )
    media_id = uuid4()
    source_key = f"knowledge-media/{media_id}"
    async with TestSession() as session:
        session.add(entry)
        await session.flush()
        session.add(
            ProtectedContentMedia(
                id=media_id,
                knowledge_entry_id=entry.id,
                storage_key=source_key,
                filename="lesson.mp4",
                content_type="video/mp4",
                size=1_024,
                position=0,
                processing_status=ContentMediaProcessingStatus.QUEUED,
                normalization_source_key=source_key,
            )
        )
        await session.commit()

    monkeypatch.setattr(normalization_jobs, "async_session_factory", TestSession)
    stale_claim = await normalization_jobs._claim_media(media_id)
    assert stale_claim is not None
    assert stale_claim.generation == 1

    # The reconciler considers the first worker stale while that worker can
    # still finish an S3 upload in another process/thread.
    async with TestSession() as session:
        media = await session.get(ProtectedContentMedia, media_id, with_for_update=True)
        assert media is not None
        media.processing_status = ContentMediaProcessingStatus.QUEUED
        await session.commit()

    winning_claim = await normalization_jobs._claim_media(media_id)
    assert winning_claim is not None
    assert winning_claim.generation == 2
    assert winning_claim.target_key != stale_claim.target_key

    stale_failure_recorded = await normalization_jobs._record_failure(
        stale_claim,
        "LATE_FAILURE",
        "The stale worker finished late",
        retryable=False,
    )
    assert stale_failure_recorded is False
    async with TestSession() as session:
        media = await session.get(ProtectedContentMedia, media_id)
        assert media is not None
        assert media.processing_status is ContentMediaProcessingStatus.PROCESSING
        assert media.normalization_attempts == 2

    normalized = NormalizedContentMedia(
        path=tmp_path / "winner.mp4",
        size=900,
        probe=_probe(),
        reused_source=False,
    )
    assert await normalization_jobs._complete_with_swap(winning_claim, normalized) is True
    assert await normalization_jobs._complete_with_swap(stale_claim, normalized) is False

    store = _WorkerStore(b"source")
    await normalization_jobs._delete_target_if_unreferenced(
        {"upload_store": store},
        stale_claim,
    )

    async with TestSession() as session:
        media = await session.get(ProtectedContentMedia, media_id)
        assert media is not None
        assert media.processing_status is ContentMediaProcessingStatus.READY
        assert media.storage_key == winning_claim.target_key
    assert store.deletes == [stale_claim.target_key]


@pytest.mark.asyncio
async def test_reconciler_runs_periodic_staging_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cleanup_calls: list[tuple[Path, int]] = []

    def fake_cleanup(root: Path, *, older_than_seconds: int) -> int:
        cleanup_calls.append((root, older_than_seconds))
        return 1

    monkeypatch.setattr(normalization_jobs, "async_session_factory", TestSession)
    monkeypatch.setattr(normalization_jobs, "_staging_root", lambda: tmp_path)
    monkeypatch.setattr(
        normalization_jobs,
        "cleanup_stale_staging_directories",
        fake_cleanup,
    )

    await normalization_jobs.reconcile_content_media_normalization(
        {"redis": object(), "upload_store": _WorkerStore(b"")}
    )

    assert cleanup_calls == [
        (
            tmp_path,
            max(
                normalization_jobs.settings.content_media_normalization_cleanup_age_seconds,
                normalization_jobs.settings.content_media_normalization_stale_seconds + 60,
            ),
        )
    ]
