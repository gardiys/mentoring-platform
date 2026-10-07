import subprocess
from pathlib import Path
from typing import Any

import pytest

from app.interviews import transcription_audio
from app.interviews.media_guardrails import MediaGuardrailError, MediaProbe, MediaStreamProbe


@pytest.mark.parametrize("has_video", [False, True])
async def test_recordings_without_sound_are_rejected(tmp_path: Path, has_video: bool) -> None:
    probe = MediaProbe(
        format_names=("mp4",),
        duration_seconds=42,
        streams=(MediaStreamProbe("video", "h264", 42),) if has_video else (),
    )
    with pytest.raises(MediaGuardrailError) as raised:
        await transcription_audio.prepare_transcription_audio(
            tmp_path / "recording.mp4",
            probe,
            timeout_seconds=10,
            probe_timeout_seconds=2,
            max_duration_seconds=60,
        )
    assert raised.value.code == "media_audio_missing"


async def test_existing_audio_is_not_reencoded(tmp_path: Path) -> None:
    source = tmp_path / "recording.mp3"
    probe = MediaProbe(("mp3",), 42, (MediaStreamProbe("audio", "mp3", 42),))
    result = await transcription_audio.prepare_transcription_audio(
        source,
        probe,
        timeout_seconds=10,
        probe_timeout_seconds=2,
        max_duration_seconds=60,
    )
    assert result == source


@pytest.mark.parametrize("output_duration", [42, 10])
async def test_extraction_validates_audio_duration_and_bounds_resources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    output_duration: float,
) -> None:
    source = tmp_path / "recording.mp4"
    probe = MediaProbe(
        ("mp4",),
        42,
        (MediaStreamProbe("video", "h264", 42), MediaStreamProbe("audio", "aac", 42)),
    )
    calls: list[list[str]] = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        calls.append(command)
        assert kwargs["timeout"] == 10
        assert kwargs["env"] == transcription_audio.MEDIA_TOOL_ENVIRONMENT
        assert kwargs["stderr"] is subprocess.DEVNULL
        return subprocess.CompletedProcess(command, 0)

    async def inspect(path: Path, **kwargs: Any) -> MediaProbe:
        assert path.name == "transcription-audio.mp3"
        assert kwargs["max_file_bytes"] == transcription_audio.transcription_audio_max_bytes(42)
        assert kwargs["declared_content_type"] == "audio/mpeg"
        return MediaProbe(("mp3",), output_duration, (MediaStreamProbe("audio", "mp3", 42),))

    monkeypatch.setattr(transcription_audio.subprocess, "run", run)
    monkeypatch.setattr(transcription_audio, "probe_media_async", inspect)
    if output_duration == 42:
        result = await transcription_audio.prepare_transcription_audio(
            source,
            probe,
            timeout_seconds=10,
            probe_timeout_seconds=2,
            max_duration_seconds=60,
        )
        assert result != source
    else:
        with pytest.raises(MediaGuardrailError) as raised:
            await transcription_audio.prepare_transcription_audio(
                source,
                probe,
                timeout_seconds=10,
                probe_timeout_seconds=2,
                max_duration_seconds=60,
            )
        assert raised.value.code == "media_audio_extraction_failed"
    command = calls[0]
    assert command[command.index("-map") + 1] == "0:a:0"
    assert "-vn" in command
    assert "-fs" in command
    assert command[command.index("-ac") + 1] == "2"


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (subprocess.TimeoutExpired("ffmpeg", 1), "media_audio_extraction_timeout"),
        (FileNotFoundError("ffmpeg"), "media_audio_extraction_unavailable"),
        (None, "media_audio_extraction_failed"),
    ],
)
def test_extraction_errors_are_classified(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception | None,
    code: str,
) -> None:
    def run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        if failure is not None:
            raise failure
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(transcription_audio.subprocess, "run", run)
    with pytest.raises(MediaGuardrailError) as raised:
        transcription_audio._extract_audio(["ffmpeg"], 1)
    assert raised.value.code == code
