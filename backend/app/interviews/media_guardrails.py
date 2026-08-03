from __future__ import annotations

import asyncio
import json
import math
import shutil
import stat
import subprocess
import tempfile
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, cast

import anyio

DEFAULT_FFPROBE_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_PROBE_BYTES = 8 * 1024 * 1024
DEFAULT_ANALYZE_DURATION_SECONDS = 10.0
MAX_FFPROBE_OUTPUT_BYTES = 1024 * 1024
MAX_MEDIA_STREAMS = 32
MEDIA_TOOL_ENVIRONMENT = {
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    # Production binaries live in /usr/local/bin; the final entry preserves
    # direct local development on Apple Silicon without inheriting app secrets.
    "PATH": "/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin",
}

# ffprobe reports a comma-separated list of compatible demuxer names. Matching
# the declared MIME type to that list catches uploads that merely claim to be
# audio or video in their S3 metadata.
MEDIA_CONTAINER_ALLOWLIST: dict[str, frozenset[str]] = {
    "audio/aac": frozenset({"aac"}),
    "audio/amr": frozenset({"amr"}),
    "audio/flac": frozenset({"flac"}),
    "audio/mp4": frozenset({"mov", "mp4", "m4a", "3gp", "3g2", "mj2"}),
    "audio/mp3": frozenset({"mp3"}),
    "audio/mpeg": frozenset({"mp3"}),
    "audio/ogg": frozenset({"ogg"}),
    "audio/vnd.wave": frozenset({"wav"}),
    "audio/wav": frozenset({"wav"}),
    "audio/webm": frozenset({"matroska", "webm"}),
    "audio/x-flac": frozenset({"flac"}),
    "audio/x-m4a": frozenset({"mov", "mp4", "m4a", "3gp", "3g2", "mj2"}),
    "audio/x-ms-wma": frozenset({"asf"}),
    "audio/x-wav": frozenset({"wav"}),
    "video/3gpp": frozenset({"mov", "mp4", "m4a", "3gp", "3g2", "mj2"}),
    "video/mp4": frozenset({"mov", "mp4", "m4a", "3gp", "3g2", "mj2"}),
    "video/mpeg": frozenset({"mpeg", "mpegvideo"}),
    "video/ogg": frozenset({"ogg"}),
    "video/quicktime": frozenset({"mov", "mp4", "m4a", "3gp", "3g2", "mj2"}),
    "video/webm": frozenset({"matroska", "webm"}),
    "video/x-matroska": frozenset({"matroska", "webm"}),
    "video/x-ms-wmv": frozenset({"asf"}),
    "video/x-msvideo": frozenset({"avi"}),
}
MEDIA_CODEC_ALLOWLIST: dict[str, frozenset[str]] = {
    "audio/aac": frozenset({"aac"}),
    "audio/amr": frozenset({"amr_nb", "amr_wb"}),
    "audio/flac": frozenset({"flac"}),
    "audio/mp4": frozenset({"aac", "alac", "mp3", "opus"}),
    "audio/mp3": frozenset({"mp3"}),
    "audio/mpeg": frozenset({"mp3"}),
    "audio/ogg": frozenset({"flac", "opus", "vorbis"}),
    "audio/vnd.wave": frozenset(
        {
            "mp3",
            "pcm_alaw",
            "pcm_f32le",
            "pcm_f64le",
            "pcm_mulaw",
            "pcm_s16le",
            "pcm_s24le",
            "pcm_s32le",
            "pcm_u8",
        }
    ),
    "audio/wav": frozenset(
        {
            "mp3",
            "pcm_alaw",
            "pcm_f32le",
            "pcm_f64le",
            "pcm_mulaw",
            "pcm_s16le",
            "pcm_s24le",
            "pcm_s32le",
            "pcm_u8",
        }
    ),
    "audio/webm": frozenset({"opus", "vorbis"}),
    "audio/x-flac": frozenset({"flac"}),
    "audio/x-m4a": frozenset({"aac", "alac", "mp3", "opus"}),
    "audio/x-ms-wma": frozenset({"wmav1", "wmav2", "wmalossless", "wmapro"}),
    "audio/x-wav": frozenset(
        {
            "mp3",
            "pcm_alaw",
            "pcm_f32le",
            "pcm_f64le",
            "pcm_mulaw",
            "pcm_s16le",
            "pcm_s24le",
            "pcm_s32le",
            "pcm_u8",
        }
    ),
    "video/3gpp": frozenset({"h263", "h264", "hevc", "mpeg4"}),
    "video/mp4": frozenset({"av1", "h264", "hevc", "mjpeg", "mpeg4", "vp9"}),
    "video/mpeg": frozenset({"mpeg1video", "mpeg2video"}),
    "video/ogg": frozenset({"theora", "vp8"}),
    "video/quicktime": frozenset(
        {"av1", "dnxhd", "h264", "hevc", "mjpeg", "mpeg4", "prores", "vp9"}
    ),
    "video/webm": frozenset({"av1", "vp8", "vp9"}),
    "video/x-matroska": frozenset(
        {"av1", "h264", "hevc", "mpeg2video", "mpeg4", "theora", "vp8", "vp9"}
    ),
    "video/x-ms-wmv": frozenset({"vc1", "wmv1", "wmv2", "wmv3"}),
    "video/x-msvideo": frozenset({"ffv1", "h264", "mjpeg", "mpeg4", "rawvideo"}),
}


class MediaGuardrailError(RuntimeError):
    """A staged recording failed a bounded media validation check."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class StagingCapacityError(RuntimeError):
    """The worker cannot safely reserve local space for another recording."""

    def __init__(
        self,
        *,
        available_bytes: int,
        required_bytes: int,
        reason: str = "insufficient_staging_capacity",
    ) -> None:
        super().__init__("Insufficient local staging capacity")
        self.reason = reason
        self.available_bytes = available_bytes
        self.required_bytes = required_bytes


@dataclass(frozen=True)
class MediaStreamProbe:
    kind: str
    codec: str
    duration_seconds: float | None


@dataclass(frozen=True)
class MediaProbe:
    format_names: tuple[str, ...]
    duration_seconds: float
    streams: tuple[MediaStreamProbe, ...]

    @property
    def audio_codecs(self) -> tuple[str, ...]:
        return tuple(stream.codec for stream in self.streams if stream.kind == "audio")

    @property
    def video_codecs(self) -> tuple[str, ...]:
        return tuple(stream.codec for stream in self.streams if stream.kind == "video")


def cleanup_stale_staging_directories(
    root: Path,
    *,
    older_than_seconds: int,
    now_timestamp: float | None = None,
) -> int:
    """Remove only stale directories created by :func:`stage_media_file`."""
    if older_than_seconds <= 0:
        raise ValueError("older_than_seconds must be positive")
    root.mkdir(parents=True, exist_ok=True)
    cutoff = (now_timestamp if now_timestamp is not None else time.time()) - older_than_seconds
    removed = 0
    for entry in root.iterdir():
        if not entry.name.startswith("interview-media-"):
            continue
        try:
            entry_stat = entry.stat(follow_symlinks=False)
            if not stat.S_ISDIR(entry_stat.st_mode) or entry_stat.st_mtime > cutoff:
                continue
            shutil.rmtree(entry)
        except OSError:
            continue
        removed += 1
    return removed


class StagingGuard:
    """Process-local staging concurrency, byte budget, and disk headroom guard.

    Keep the reservation open for the entire lifetime of the staged file. The
    disk check is intentionally repeated inside the concurrency slot. This does
    not replace a bounded container volume, but it prevents cooperating worker
    jobs in one process from overcommitting that volume.
    """

    def __init__(
        self,
        *,
        max_concurrency: int,
        min_free_bytes: int,
        max_reserved_bytes: int | None = None,
    ) -> None:
        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be positive")
        if min_free_bytes < 0:
            raise ValueError("min_free_bytes cannot be negative")
        if max_reserved_bytes is not None and max_reserved_bytes <= 0:
            raise ValueError("max_reserved_bytes must be positive")
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._reservation_lock = asyncio.Lock()
        self._min_free_bytes = min_free_bytes
        self._max_reserved_bytes = max_reserved_bytes
        self._reserved_bytes = 0

    @property
    def reserved_bytes(self) -> int:
        return self._reserved_bytes

    @asynccontextmanager
    async def reserve(self, directory: Path, *, expected_bytes: int) -> AsyncIterator[None]:
        if expected_bytes <= 0:
            raise ValueError("expected_bytes must be positive")

        async with self._semaphore:
            reserved = False
            async with self._reservation_lock:
                try:
                    usage = await anyio.to_thread.run_sync(shutil.disk_usage, directory)
                except OSError as error:
                    raise StagingCapacityError(
                        available_bytes=0,
                        required_bytes=expected_bytes + self._min_free_bytes,
                        reason="staging_directory_unavailable",
                    ) from error
                available_bytes = max(0, usage.free - self._reserved_bytes)
                required_bytes = expected_bytes + self._min_free_bytes
                if available_bytes < required_bytes:
                    raise StagingCapacityError(
                        available_bytes=available_bytes,
                        required_bytes=required_bytes,
                    )
                if (
                    self._max_reserved_bytes is not None
                    and self._reserved_bytes + expected_bytes > self._max_reserved_bytes
                ):
                    raise StagingCapacityError(
                        available_bytes=max(0, self._max_reserved_bytes - self._reserved_bytes),
                        required_bytes=expected_bytes,
                        reason="staging_byte_budget_exceeded",
                    )
                self._reserved_bytes += expected_bytes
                reserved = True
            try:
                yield
            finally:
                if reserved:
                    async with self._reservation_lock:
                        self._reserved_bytes -= expected_bytes


@asynccontextmanager
async def stage_media_file(
    guard: StagingGuard,
    *,
    filename: str,
    maximum_bytes: int,
    download: Callable[[Path], Awaitable[None]],
    expected_bytes: int | None = None,
    staging_root: Path | None = None,
) -> AsyncIterator[Path]:
    """Download one object into an automatically cleaned, capacity-guarded directory."""

    if expected_bytes is not None and (expected_bytes <= 0 or expected_bytes > maximum_bytes):
        raise ValueError("expected_bytes must be positive and no greater than maximum_bytes")
    root = staging_root or Path(tempfile.gettempdir())
    suffix = Path(filename).suffix.casefold()
    if not suffix[1:].isalnum() or len(suffix) > 20:
        suffix = ".bin"
    async with guard.reserve(root, expected_bytes=maximum_bytes):
        with tempfile.TemporaryDirectory(prefix="interview-media-", dir=root) as directory:
            destination = Path(directory) / f"recording{suffix}"
            await download(destination)
            try:
                actual_stat = destination.lstat()
            except OSError as error:
                raise MediaGuardrailError(
                    "invalid_media_file", "Staged media file is unavailable"
                ) from error
            invalid_size = actual_stat.st_size <= 0 or actual_stat.st_size > maximum_bytes
            if expected_bytes is not None:
                invalid_size = invalid_size or actual_stat.st_size != expected_bytes
            if not stat.S_ISREG(actual_stat.st_mode) or invalid_size:
                raise MediaGuardrailError(
                    "invalid_media_file",
                    "Staged media size does not match storage metadata",
                )
            yield destination


def probe_media(
    path: Path,
    *,
    declared_content_type: str,
    max_duration_seconds: float,
    max_file_bytes: int | None = None,
    ffprobe_binary: str = "ffprobe",
    timeout_seconds: float = DEFAULT_FFPROBE_TIMEOUT_SECONDS,
    max_probe_bytes: int = DEFAULT_MAX_PROBE_BYTES,
    analyze_duration_seconds: float = DEFAULT_ANALYZE_DURATION_SECONDS,
) -> MediaProbe:
    """Inspect and validate a staged recording without trusting its extension or MIME metadata."""

    _validate_probe_limits(
        max_duration_seconds=max_duration_seconds,
        max_file_bytes=max_file_bytes,
        timeout_seconds=timeout_seconds,
        max_probe_bytes=max_probe_bytes,
        analyze_duration_seconds=analyze_duration_seconds,
    )
    try:
        file_stat = path.lstat()
    except OSError as error:
        raise MediaGuardrailError(
            "invalid_media_file", "Staged media file is unavailable"
        ) from error
    if stat.S_ISLNK(file_stat.st_mode) or not stat.S_ISREG(file_stat.st_mode):
        raise MediaGuardrailError("invalid_media_file", "Staged media path is not a regular file")
    if file_stat.st_size <= 0:
        raise MediaGuardrailError("invalid_media_file", "Staged media file is empty")
    if max_file_bytes is not None and file_stat.st_size > max_file_bytes:
        raise MediaGuardrailError("media_file_too_large", "Staged media file is too large")

    command = [
        ffprobe_binary,
        "-v",
        "error",
        "-protocol_whitelist",
        "file",
        "-probesize",
        str(max_probe_bytes),
        "-analyzeduration",
        str(round(analyze_duration_seconds * 1_000_000)),
        "-show_entries",
        "format=format_name,duration:stream=codec_type,codec_name,duration",
        "-of",
        "json",
        "-i",
        str(path),
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout_seconds,
            env=MEDIA_TOOL_ENVIRONMENT,
        )
    except subprocess.TimeoutExpired as error:
        raise MediaGuardrailError("media_probe_timeout", "Media inspection timed out") from error
    except (FileNotFoundError, OSError) as error:
        raise MediaGuardrailError(
            "media_probe_unavailable", "Media inspection is unavailable"
        ) from error

    if result.returncode != 0 or len(result.stdout) > MAX_FFPROBE_OUTPUT_BYTES:
        raise MediaGuardrailError("invalid_media_file", "Media container could not be inspected")
    try:
        payload = json.loads(result.stdout)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as error:
        raise MediaGuardrailError(
            "invalid_media_file", "Media probe returned invalid data"
        ) from error
    probe = _parse_probe(payload)
    validate_media_probe(
        probe,
        declared_content_type=declared_content_type,
        max_duration_seconds=max_duration_seconds,
    )
    return probe


async def probe_media_async(
    path: Path,
    *,
    declared_content_type: str,
    max_duration_seconds: float,
    max_file_bytes: int | None = None,
    ffprobe_binary: str = "ffprobe",
    timeout_seconds: float = DEFAULT_FFPROBE_TIMEOUT_SECONDS,
    max_probe_bytes: int = DEFAULT_MAX_PROBE_BYTES,
    analyze_duration_seconds: float = DEFAULT_ANALYZE_DURATION_SECONDS,
) -> MediaProbe:
    """Run :func:`probe_media` off the worker event loop."""

    operation = partial(
        probe_media,
        path,
        declared_content_type=declared_content_type,
        max_duration_seconds=max_duration_seconds,
        max_file_bytes=max_file_bytes,
        ffprobe_binary=ffprobe_binary,
        timeout_seconds=timeout_seconds,
        max_probe_bytes=max_probe_bytes,
        analyze_duration_seconds=analyze_duration_seconds,
    )
    return cast(MediaProbe, await anyio.to_thread.run_sync(operation))


def validate_media_probe(
    probe: MediaProbe,
    *,
    declared_content_type: str,
    max_duration_seconds: float,
) -> None:
    normalized_type = declared_content_type.split(";", 1)[0].strip().lower()
    allowed_formats = MEDIA_CONTAINER_ALLOWLIST.get(normalized_type)
    if allowed_formats is None:
        raise MediaGuardrailError(
            "unsupported_media_type",
            "The declared recording type is not supported",
        )
    if not allowed_formats.intersection(probe.format_names):
        raise MediaGuardrailError(
            "media_content_type_mismatch",
            "The recording container does not match its declared type",
        )

    expected_stream_kind = "video" if normalized_type.startswith("video/") else "audio"
    matching_streams = tuple(
        stream for stream in probe.streams if stream.kind == expected_stream_kind
    )
    if not matching_streams:
        raise MediaGuardrailError(
            "media_content_type_mismatch",
            "The recording streams do not match its declared type",
        )
    allowed_codecs = MEDIA_CODEC_ALLOWLIST[normalized_type]
    if any(stream.codec not in allowed_codecs for stream in matching_streams):
        raise MediaGuardrailError(
            "unsupported_media_codec",
            "The recording codec is not supported",
        )
    if not math.isfinite(max_duration_seconds) or max_duration_seconds <= 0:
        raise ValueError("max_duration_seconds must be positive and finite")
    if probe.duration_seconds > max_duration_seconds:
        raise MediaGuardrailError(
            "media_duration_exceeded",
            "The recording duration exceeds the configured limit",
        )


def _parse_probe(payload: Any) -> MediaProbe:
    if not isinstance(payload, dict):
        raise MediaGuardrailError("invalid_media_file", "Media probe returned invalid data")
    format_payload = payload.get("format")
    stream_payloads = payload.get("streams")
    if not isinstance(format_payload, dict) or not isinstance(stream_payloads, list):
        raise MediaGuardrailError("invalid_media_file", "Media probe returned incomplete data")
    if len(stream_payloads) > MAX_MEDIA_STREAMS:
        raise MediaGuardrailError("invalid_media_file", "Media file contains too many streams")

    raw_format_names = format_payload.get("format_name")
    if not isinstance(raw_format_names, str):
        raise MediaGuardrailError("invalid_media_file", "Media container is unknown")
    format_names = tuple(
        name.strip().lower() for name in raw_format_names.split(",") if name.strip()
    )
    if not format_names:
        raise MediaGuardrailError("invalid_media_file", "Media container is unknown")

    streams: list[MediaStreamProbe] = []
    stream_durations: list[float] = []
    for item in stream_payloads:
        if not isinstance(item, dict) or item.get("codec_type") not in {"audio", "video"}:
            continue
        codec = item.get("codec_name")
        if not isinstance(codec, str) or not codec.strip() or len(codec) > 100:
            raise MediaGuardrailError("invalid_media_file", "Media stream codec is unknown")
        duration = _positive_finite_float(item.get("duration"))
        if duration is not None:
            stream_durations.append(duration)
        streams.append(
            MediaStreamProbe(
                kind=str(item["codec_type"]),
                codec=codec.strip().lower(),
                duration_seconds=duration,
            )
        )
    if not streams:
        raise MediaGuardrailError("invalid_media_file", "Media file has no audio or video streams")

    duration = _positive_finite_float(format_payload.get("duration"))
    if duration is None and stream_durations:
        duration = max(stream_durations)
    if duration is None:
        raise MediaGuardrailError("invalid_media_file", "Media duration is unavailable")
    return MediaProbe(format_names=format_names, duration_seconds=duration, streams=tuple(streams))


def _positive_finite_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def _validate_probe_limits(
    *,
    max_duration_seconds: float,
    max_file_bytes: int | None,
    timeout_seconds: float,
    max_probe_bytes: int,
    analyze_duration_seconds: float,
) -> None:
    if not math.isfinite(max_duration_seconds) or max_duration_seconds <= 0:
        raise ValueError("max_duration_seconds must be positive and finite")
    if max_file_bytes is not None and max_file_bytes <= 0:
        raise ValueError("max_file_bytes must be positive")
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive and finite")
    if max_probe_bytes <= 0:
        raise ValueError("max_probe_bytes must be positive")
    if not math.isfinite(analyze_duration_seconds) or analyze_duration_seconds <= 0:
        raise ValueError("analyze_duration_seconds must be positive and finite")
