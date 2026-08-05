from __future__ import annotations

import logging
import stat
import subprocess
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import anyio

from app.interviews.media_guardrails import (
    MEDIA_TOOL_ENVIRONMENT,
    MediaGuardrailError,
    MediaProbe,
    probe_media_async,
)

logger = logging.getLogger(__name__)
MP4_HEADER_BYTES = 16
MAX_MP4_TOP_LEVEL_BOXES = 100_000
DEFAULT_MP4_OUTPUT_OVERHEAD_BYTES = 256 * 1024 * 1024
BROWSER_VIDEO_CODECS = frozenset({"h264"})
BROWSER_MP4_AUDIO_CODECS = frozenset({"aac", "mp3"})


class ContentMediaNormalizationError(RuntimeError):
    """A content video could not be normalized into a browser-friendly MP4."""

    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class Mp4Layout:
    has_ftyp: bool
    moov_offset: int | None
    first_mdat_offset: int | None
    has_fragments: bool

    @property
    def browser_seekable(self) -> bool:
        return (
            self.has_ftyp
            and self.moov_offset is not None
            and self.first_mdat_offset is not None
            and self.moov_offset < self.first_mdat_offset
            and not self.has_fragments
        )


@dataclass(frozen=True)
class NormalizedContentMedia:
    path: Path | None
    size: int
    probe: MediaProbe
    reused_source: bool


def inspect_mp4_layout(
    path: Path,
    *,
    stop_at_first_fragment: bool = False,
) -> Mp4Layout:
    """Inspect top-level ISO BMFF boxes without loading media payloads into memory."""
    try:
        file_stat = path.lstat()
    except OSError as error:
        raise ContentMediaNormalizationError(
            "MEDIA_FILE_UNAVAILABLE",
            "The staged video is unavailable",
            retryable=True,
        ) from error
    if stat.S_ISLNK(file_stat.st_mode) or not stat.S_ISREG(file_stat.st_mode):
        raise ContentMediaNormalizationError(
            "INVALID_MEDIA_FILE",
            "The staged video is not a regular file",
            retryable=False,
        )
    file_size = file_stat.st_size
    if file_size < 8:
        raise ContentMediaNormalizationError(
            "INVALID_MP4_LAYOUT",
            "The video is not a valid MP4 file",
            retryable=False,
        )

    has_ftyp = False
    moov_offset: int | None = None
    first_mdat_offset: int | None = None
    has_fragments = False
    offset = 0
    box_count = 0
    try:
        with path.open("rb") as source:
            while offset < file_size:
                box_count += 1
                if box_count > MAX_MP4_TOP_LEVEL_BOXES:
                    raise ContentMediaNormalizationError(
                        "INVALID_MP4_LAYOUT",
                        "The MP4 file contains too many top-level boxes",
                        retryable=False,
                    )
                remaining = file_size - offset
                if remaining < 8:
                    raise ContentMediaNormalizationError(
                        "INVALID_MP4_LAYOUT",
                        "The MP4 file has a truncated top-level box",
                        retryable=False,
                    )
                source.seek(offset)
                header = source.read(MP4_HEADER_BYTES)
                if len(header) < 8:
                    raise ContentMediaNormalizationError(
                        "INVALID_MP4_LAYOUT",
                        "The MP4 file has a truncated top-level box header",
                        retryable=False,
                    )
                box_size = int.from_bytes(header[:4], "big")
                box_type = header[4:8]
                header_size = 8
                if box_size == 1:
                    if len(header) < 16:
                        raise ContentMediaNormalizationError(
                            "INVALID_MP4_LAYOUT",
                            "The MP4 file has a truncated extended box header",
                            retryable=False,
                        )
                    box_size = int.from_bytes(header[8:16], "big")
                    header_size = 16
                elif box_size == 0:
                    box_size = remaining
                if box_size < header_size or box_size > remaining:
                    raise ContentMediaNormalizationError(
                        "INVALID_MP4_LAYOUT",
                        "The MP4 file contains an invalid top-level box size",
                        retryable=False,
                    )

                if box_type == b"ftyp":
                    has_ftyp = True
                elif box_type == b"moov" and moov_offset is None:
                    moov_offset = offset
                elif box_type == b"mdat" and first_mdat_offset is None:
                    first_mdat_offset = offset
                elif box_type == b"moof":
                    has_fragments = True
                    if stop_at_first_fragment:
                        return Mp4Layout(
                            has_ftyp=has_ftyp,
                            moov_offset=moov_offset,
                            first_mdat_offset=first_mdat_offset,
                            has_fragments=True,
                        )
                offset += box_size
    except ContentMediaNormalizationError:
        raise
    except OSError as error:
        raise ContentMediaNormalizationError(
            "MEDIA_FILE_UNAVAILABLE",
            "The staged video could not be read",
            retryable=True,
        ) from error

    return Mp4Layout(
        has_ftyp=has_ftyp,
        moov_offset=moov_offset,
        first_mdat_offset=first_mdat_offset,
        has_fragments=has_fragments,
    )


async def normalize_content_mp4(
    source: Path,
    target: Path,
    *,
    source_size: int,
    declared_content_type: str = "video/mp4",
    max_file_bytes: int,
    max_duration_seconds: float,
    probe_timeout_seconds: float,
    remux_timeout_seconds: float,
    output_overhead_bytes: int = DEFAULT_MP4_OUTPUT_OVERHEAD_BYTES,
    ffmpeg_binary: str = "ffmpeg",
) -> NormalizedContentMedia:
    """Validate and losslessly remux one H.264/AAC MP4 when its layout needs it."""
    if source_size <= 0 or max_file_bytes <= 0 or output_overhead_bytes <= 0:
        raise ValueError("source size and normalization byte limits must be positive")
    try:
        probe = await probe_media_async(
            source,
            declared_content_type=declared_content_type,
            max_duration_seconds=max_duration_seconds,
            max_file_bytes=max_file_bytes,
            timeout_seconds=probe_timeout_seconds,
        )
    except MediaGuardrailError as error:
        raise ContentMediaNormalizationError(
            error.code.upper(),
            str(error),
            retryable=error.code in {"media_probe_timeout", "media_probe_unavailable"},
        ) from error
    _validate_browser_codecs(probe)
    # A single `moof` already proves that a lossless remux is needed. Avoid
    # walking millions of fragments in long recordings; ffprobe above has
    # already validated the complete media container.
    source_layout = inspect_mp4_layout(source, stop_at_first_fragment=True)
    normalized_declared_type = declared_content_type.split(";", 1)[0].strip().lower()
    if normalized_declared_type == "video/mp4" and source_layout.browser_seekable:
        return NormalizedContentMedia(
            path=None,
            size=source_size,
            probe=probe,
            reused_source=True,
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    operation = partial(
        _run_lossless_remux,
        source,
        target,
        ffmpeg_binary=ffmpeg_binary,
        timeout_seconds=remux_timeout_seconds,
    )
    await anyio.to_thread.run_sync(operation)
    try:
        target_stat = target.lstat()
    except OSError as error:
        raise ContentMediaNormalizationError(
            "NORMALIZATION_OUTPUT_MISSING",
            "Video normalization did not produce an output file",
            retryable=False,
        ) from error
    maximum_output_bytes = source_size + output_overhead_bytes
    if (
        stat.S_ISLNK(target_stat.st_mode)
        or not stat.S_ISREG(target_stat.st_mode)
        or target_stat.st_size <= 0
        or target_stat.st_size > maximum_output_bytes
    ):
        raise ContentMediaNormalizationError(
            "INVALID_NORMALIZATION_OUTPUT",
            "Video normalization produced an invalid output file",
            retryable=False,
        )

    output_layout = inspect_mp4_layout(target)
    if not output_layout.browser_seekable:
        raise ContentMediaNormalizationError(
            "UNSEEKABLE_NORMALIZATION_OUTPUT",
            "The prepared MP4 is still not suitable for browser streaming",
            retryable=False,
        )
    try:
        output_probe = await probe_media_async(
            target,
            declared_content_type="video/mp4",
            max_duration_seconds=max_duration_seconds,
            max_file_bytes=maximum_output_bytes,
            timeout_seconds=probe_timeout_seconds,
        )
    except MediaGuardrailError as error:
        raise ContentMediaNormalizationError(
            "INVALID_NORMALIZATION_OUTPUT",
            "The prepared MP4 could not be validated",
            retryable=error.code in {"media_probe_timeout", "media_probe_unavailable"},
        ) from error
    _validate_browser_codecs(output_probe)
    duration_tolerance_seconds = max(1.0, probe.duration_seconds * 0.001)
    if abs(output_probe.duration_seconds - probe.duration_seconds) > duration_tolerance_seconds:
        raise ContentMediaNormalizationError(
            "NORMALIZATION_DURATION_MISMATCH",
            "The prepared MP4 duration does not match the uploaded video",
            retryable=False,
        )
    return NormalizedContentMedia(
        path=target,
        size=target_stat.st_size,
        probe=output_probe,
        reused_source=False,
    )


def _validate_browser_codecs(probe: MediaProbe) -> None:
    if not probe.video_codecs or probe.video_codecs[0] not in BROWSER_VIDEO_CODECS:
        raise ContentMediaNormalizationError(
            "UNSUPPORTED_BROWSER_VIDEO_CODEC",
            "Only H.264 MP4 video can currently be prepared for browser playback",
            retryable=False,
        )
    if probe.audio_codecs and probe.audio_codecs[0] not in BROWSER_MP4_AUDIO_CODECS:
        raise ContentMediaNormalizationError(
            "UNSUPPORTED_BROWSER_AUDIO_CODEC",
            "The MP4 audio codec is not supported by browser playback",
            retryable=False,
        )


def _run_lossless_remux(
    source: Path,
    target: Path,
    *,
    ffmpeg_binary: str,
    timeout_seconds: float,
) -> None:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    command = [
        ffmpeg_binary,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-protocol_whitelist",
        "file",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-sn",
        "-dn",
        "-map_metadata",
        "-1",
        "-map_chapters",
        "-1",
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(target),
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            # A malformed multi-gigabyte file can make ffmpeg emit an
            # unbounded amount of diagnostics. Keep worker memory bounded;
            # the exit code and curated error code are sufficient here.
            stderr=subprocess.DEVNULL,
            timeout=timeout_seconds,
            env=MEDIA_TOOL_ENVIRONMENT,
        )
    except subprocess.TimeoutExpired as error:
        raise ContentMediaNormalizationError(
            "NORMALIZATION_TIMEOUT",
            "Video normalization timed out",
            retryable=True,
        ) from error
    except (FileNotFoundError, OSError) as error:
        raise ContentMediaNormalizationError(
            "NORMALIZATION_TOOL_UNAVAILABLE",
            "Video normalization is unavailable",
            retryable=True,
        ) from error
    if result.returncode != 0:
        logger.warning(
            "ffmpeg content video remux failed exit_code=%s",
            result.returncode,
        )
        raise ContentMediaNormalizationError(
            "NORMALIZATION_FAILED",
            "The uploaded MP4 could not be prepared for browser playback",
            retryable=False,
        )
