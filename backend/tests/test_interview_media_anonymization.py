from pathlib import Path

from app.media.interview_anonymization import _anonymization_command


def test_video_anonymization_blurs_frame_changes_voice_and_strips_metadata() -> None:
    command = _anonymization_command(Path("source.mov"), Path("anonymous.mp4"), is_video=True)

    assert "gblur=sigma=40:steps=3" in command
    assert "aresample=48000,asetrate=39360,aresample=48000,atempo=1.219512" in command
    assert command[command.index("-map_metadata") + 1] == "-1"
    assert "+faststart" in command
    assert "libx264" in command


def test_audio_anonymization_never_copies_video() -> None:
    command = _anonymization_command(Path("source.mp3"), Path("anonymous.m4a"), is_video=False)

    assert "-vn" in command
    assert "gblur=sigma=40:steps=3" not in command
    assert "aac" in command
