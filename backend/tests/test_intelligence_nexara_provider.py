from datetime import UTC, datetime

import pytest
from nexara import AsyncJob, RateLimitError

from app.core.config import Settings
from app.interviews.intelligence_providers import (
    NexaraTranscriptionProvider,
    TranscriptionJobState,
    TranscriptionProviderError,
    build_transcription_provider,
)


class StubTranscriptions:
    def __init__(self, job: AsyncJob) -> None:
        self.job = job
        self.submitted: dict[str, object] | None = None

    async def create_job(self, **kwargs: object) -> AsyncJob:
        self.submitted = kwargs
        return self.job

    async def retrieve_job(self, job_id: str) -> AsyncJob:
        assert job_id == self.job.job_id
        return self.job


class StubClient:
    def __init__(self, job: AsyncJob) -> None:
        self.transcriptions = StubTranscriptions(job)
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


def completed_job() -> AsyncJob:
    return AsyncJob(
        job_id="nexara-job-1",
        status="complete",
        created_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        result={
            "task": "diarize",
            "language": "ru",
            "duration": 12.4,
            "text": "Собеседование",
            "segments": [
                {
                    "start": 0.25,
                    "end": 2.1,
                    "text": "Расскажите про GIL",
                    "speaker": "speaker_0",
                },
                {
                    "start": 2.5,
                    "end": 8.75,
                    "text": "Это глобальная блокировка интерпретатора",
                    "speaker": "speaker_1",
                },
            ],
        },
        error=None,
    )


def provider_with_job(job: AsyncJob) -> tuple[NexaraTranscriptionProvider, StubClient]:
    provider = object.__new__(NexaraTranscriptionProvider)
    provider.model = "whisper-1"
    client = StubClient(job)
    provider.client = client  # type: ignore[assignment]
    return provider, client


@pytest.mark.asyncio
async def test_nexara_submit_uses_async_diarization_without_persisting_media_url() -> None:
    provider, client = provider_with_job(completed_job())

    job = await provider.submit(
        file_url="https://s3.example/private.mp3?secret=signed",
        file_path=None,
        language=None,
        diarization=True,
        timestamps=True,
    )

    assert job.provider_job_id == "nexara-job-1"
    assert job.status is TranscriptionJobState.COMPLETED
    assert client.transcriptions.submitted == {
        "url": "https://s3.example/private.mp3?secret=signed",
        "task": "diarize",
        "language": None,
        "response_format": "verbose_json",
        "timestamp_granularities": ["segment"],
        "model": "whisper-1",
    }
    assert "result" not in job.raw_payload
    assert "error" not in job.raw_payload
    assert "secret" not in str(job.raw_payload)


@pytest.mark.asyncio
async def test_nexara_result_normalizes_segments_and_milliseconds() -> None:
    provider, _ = provider_with_job(completed_job())

    result = await provider.get_result("nexara-job-1")

    assert result.language == "ru"
    assert result.duration_ms == 12_400
    assert [item.speaker for item in result.utterances] == ["speaker_0", "speaker_1"]
    assert result.utterances[0].start_ms == 250
    assert result.utterances[1].end_ms == 8_750
    assert "result" not in result.raw_payload


def test_nexara_rate_limit_is_retryable_and_does_not_leak_provider_detail() -> None:
    error = NexaraTranscriptionProvider._provider_error(
        RateLimitError(429, "internal account detail")
    )

    assert error.code == "TRANSCRIPTION_PROVIDER_ERROR"
    assert error.retryable is True
    assert "account" not in error.safe_message


def test_fake_transcription_provider_is_forbidden_in_production() -> None:
    with pytest.raises(RuntimeError, match="forbidden"):
        build_transcription_provider(Settings(app_env="production", transcription_provider="fake"))


def test_nexara_requires_api_key() -> None:
    with pytest.raises(TranscriptionProviderError) as exc_info:
        build_transcription_provider(Settings(transcription_provider="nexara", nexara_api_key=None))

    assert exc_info.value.code == "TRANSCRIPTION_AUTH_ERROR"
