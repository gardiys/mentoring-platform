import pytest

from app.interviews.transcription_benchmark import Segment, metrics


@pytest.fixture(autouse=True)
def reset_database():
    yield


def segment(speaker, start, end, text="слово"):
    return Segment(speaker=speaker, start_ms=start, end_ms=end, text=text)


def test_identical_speech_with_permuted_speaker_ids_has_zero_errors():
    reference = [segment("A", 0, 1000, "Почему ушёл?"), segment("B", 1000, 2000, "Ради роста.")]
    result = metrics(
        reference, [segment("2", 0, 1000, "почему ушёл"), segment("1", 1000, 2000, "ради роста")]
    )
    assert result["wer"] == result["der_no_collar"] == 0


def test_missing_speech_and_merged_speakers_are_measured():
    reference = [segment("A", 0, 1000), segment("B", 1000, 2000)]
    assert metrics(reference, [segment("1", 0, 1000)])["der_no_collar"] == 0.5
    assert metrics(reference, [segment("1", 0, 2000)])["der_no_collar"] == 0.5
    assert metrics(reference, [segment(None, 0, 2000)])["der_no_collar"] == 1
    assert metrics(reference, [segment("1", 0, 1000)])["wer"] == 0.5
