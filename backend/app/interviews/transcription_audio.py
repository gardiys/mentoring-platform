"""Prepare a bounded audio-only input without changing the playback recording."""

from __future__ import annotations

import math
import subprocess
from functools import partial
from pathlib import Path

import anyio

from app.interviews.media_guardrails import (
    MEDIA_TOOL_ENVIRONMENT,
    MediaGuardrailError,
    MediaProbe,
    probe_media_async,
)

AUDIO_BITRATE = 128_000
AUDIO_OVERHEAD_BYTES = 1024 * 1024


def transcription_audio_max_bytes(duration_seconds: float) -> int:
    return math.ceil(duration_seconds * AUDIO_BITRATE / 8) + AUDIO_OVERHEAD_BYTES


async def prepare_transcription_audio(
    source: Path,
    probe: MediaProbe,
    *,
    timeout_seconds: float,
    probe_timeout_seconds: float,
    max_duration_seconds: float,
    ffmpeg_binary: str = "ffmpeg",
) -> Path:
    if not probe.audio_codecs:
        raise MediaGuardrailError("media_audio_missing", "Recording has no audio track")
    if not probe.video_codecs:
        return source

    target = source.with_name("transcription-audio.mp3")
    max_bytes = transcription_audio_max_bytes(probe.duration_seconds)
    command = [
        ffmpeg_binary,
        "-nostdin",
        "-v",
        "error",
        "-y",
        "-protocol_whitelist",
        "file",
        "-copyts",
        "-start_at_zero",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        "-vn",
        "-sn",
        "-dn",
        "-map_metadata",
        "-1",
        # Preserve left/right separation for speaker diarization. Pad initial
        # offsets and a shorter audio track to retain the playback time axis.
        "-af",
        "aresample=async=1:first_pts=0,apad",
        "-t",
        str(probe.duration_seconds),
        "-ac",
        "2",
        "-ar",
        "48000",
        "-c:a",
        "libmp3lame",
        "-b:a",
        str(AUDIO_BITRATE),
        "-threads",
        "2",
        "-fs",
        str(max_bytes),
        str(target),
    ]
    await anyio.to_thread.run_sync(partial(_extract_audio, command, timeout_seconds))
    output_probe = await probe_media_async(
        target,
        declared_content_type="audio/mpeg",
        max_duration_seconds=max_duration_seconds + 1,
        max_file_bytes=max_bytes,
        timeout_seconds=probe_timeout_seconds,
    )
    if output_probe.video_codecs or abs(output_probe.duration_seconds - probe.duration_seconds) > 1:
        raise MediaGuardrailError(
            "media_audio_extraction_failed", "Extracted audio does not match the recording"
        )
    return target


def _extract_audio(command: list[str], timeout_seconds: float) -> None:
    try:
        result = subprocess.run(
            command,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout_seconds,
            env=MEDIA_TOOL_ENVIRONMENT,
        )
    except subprocess.TimeoutExpired as error:
        raise MediaGuardrailError(
            "media_audio_extraction_timeout", "Audio extraction timed out"
        ) from error
    except OSError as error:
        raise MediaGuardrailError(
            "media_audio_extraction_unavailable", "Audio extraction is unavailable"
        ) from error
    if result.returncode != 0:
        raise MediaGuardrailError(
            "media_audio_extraction_failed", "Recording audio could not be extracted"
        )
