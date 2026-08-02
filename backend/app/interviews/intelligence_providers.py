from __future__ import annotations

import logging
import re
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from nexara import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncNexara,
    AuthenticationError,
    BadGatewayError,
    BadRequestError,
    Diarization,
    InsufficientBalanceError,
    InternalServerError,
    NexaraError,
    NexaraValidationError,
    NotFoundError,
    RateLimitError,
)
from pydantic import BaseModel, Field

from app.core.config import Settings

logger = logging.getLogger(__name__)
_URL_PATTERN = re.compile(r"https?://[^\s\"']+", re.IGNORECASE)


class TranscriptionProviderError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.retryable = retryable


class TranscriptionJobState(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"


class TranscriptionJob(BaseModel):
    provider_job_id: str
    status: TranscriptionJobState
    raw_payload: dict[str, object] = Field(default_factory=dict)


class TranscriptionUtterance(BaseModel):
    speaker: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    text: str = Field(min_length=1)


class TranscriptionResult(BaseModel):
    language: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    utterances: list[TranscriptionUtterance]
    raw_payload: dict[str, object] = Field(default_factory=dict)


class TranscriptionProvider(Protocol):
    name: str
    requires_file_upload: bool

    async def submit(
        self,
        *,
        file_url: str | None,
        file_path: Path | None,
        language: str | None,
        diarization: bool,
        timestamps: bool,
    ) -> TranscriptionJob: ...

    async def get_status(self, provider_job_id: str) -> TranscriptionJob: ...

    async def get_result(self, provider_job_id: str) -> TranscriptionResult: ...

    async def close(self) -> None: ...


class FakeTranscriptionProvider:
    name = "fake"
    requires_file_upload = False

    async def submit(
        self,
        *,
        file_url: str | None,
        file_path: Path | None,
        language: str | None,
        diarization: bool,
        timestamps: bool,
    ) -> TranscriptionJob:
        del file_url, file_path, language, diarization, timestamps
        return TranscriptionJob(
            provider_job_id="fake-interview",
            status=TranscriptionJobState.QUEUED,
        )

    async def get_status(self, provider_job_id: str) -> TranscriptionJob:
        return TranscriptionJob(
            provider_job_id=provider_job_id,
            status=TranscriptionJobState.COMPLETED,
            raw_payload={"status": "completed", "provider": "fake"},
        )

    async def get_result(self, provider_job_id: str) -> TranscriptionResult:
        del provider_job_id
        return TranscriptionResult(
            language="ru",
            duration_ms=42_000,
            utterances=[
                TranscriptionUtterance(
                    speaker="A",
                    start_ms=1_000,
                    end_ms=5_000,
                    text="Расскажите, пожалуйста, как работает GIL в Python?",
                ),
                TranscriptionUtterance(
                    speaker="B",
                    start_ms=5_200,
                    end_ms=18_000,
                    text=(
                        "GIL — это глобальная блокировка интерпретатора, которая позволяет "
                        "только одному потоку исполнять Python-байткод одновременно."
                    ),
                ),
                TranscriptionUtterance(
                    speaker="A",
                    start_ms=18_500,
                    end_ms=22_000,
                    text="А когда потоки всё-таки полезны?",
                ),
                TranscriptionUtterance(
                    speaker="B",
                    start_ms=22_200,
                    end_ms=35_000,
                    text="Они полезны для I/O-bound задач, где поток ждёт сеть или диск.",
                ),
            ],
            raw_payload={"status": "completed", "provider": "fake"},
        )

    async def close(self) -> None:
        return None


class NexaraTranscriptionProvider:
    """Adapter for the official asynchronous Nexara Python SDK.

    Provider-specific payloads are normalized here and never escape into the
    interview domain. The API key, signed media URL and transcript text are
    deliberately omitted from persisted diagnostic payloads.
    """

    name = "nexara"
    requires_file_upload = True

    def __init__(self, settings: Settings) -> None:
        if settings.nexara_api_key is None:
            raise TranscriptionProviderError(
                "TRANSCRIPTION_AUTH_ERROR",
                "Nexara API key is not configured",
                retryable=False,
            )
        self.model = settings.nexara_model
        self.client = AsyncNexara(
            api_key=settings.nexara_api_key.get_secret_value(),
            base_url=settings.nexara_base_url.rstrip("/"),
            timeout=settings.nexara_timeout_seconds,
            max_retries=settings.nexara_max_retries,
        )

    async def submit(
        self,
        *,
        file_url: str | None,
        file_path: Path | None,
        language: str | None,
        diarization: bool,
        timestamps: bool,
    ) -> TranscriptionJob:
        del timestamps
        if not diarization:
            raise TranscriptionProviderError(
                "TRANSCRIPTION_CONFIG_ERROR",
                "Nexara adapter requires speaker diarization",
                retryable=False,
            )
        if file_path is None and file_url is None:
            raise TranscriptionProviderError(
                "TRANSCRIPTION_CONFIG_ERROR",
                "Nexara transcription source is not configured",
                retryable=False,
            )
        try:
            if file_path is not None:
                job = await self.client.transcriptions.create_job(
                    file=file_path,
                    task="diarize",
                    language=language,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                    model=self.model,
                )
            else:
                job = await self.client.transcriptions.create_job(
                    url=file_url,
                    task="diarize",
                    language=language,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                    model=self.model,
                )
        except NexaraError as error:
            raise self._provider_error(error) from error
        return TranscriptionJob(
            provider_job_id=job.job_id,
            status=self._status(job.status, job.error),
            raw_payload=self._safe_job_payload(job.model_dump(mode="json")),
        )

    async def get_status(self, provider_job_id: str) -> TranscriptionJob:
        try:
            job = await self.client.transcriptions.retrieve_job(provider_job_id)
        except NexaraError as error:
            raise self._provider_error(error) from error
        return TranscriptionJob(
            provider_job_id=provider_job_id,
            status=self._status(job.status, job.error),
            raw_payload=self._safe_job_payload(job.model_dump(mode="json")),
        )

    async def get_result(self, provider_job_id: str) -> TranscriptionResult:
        try:
            job = await self.client.transcriptions.retrieve_job(provider_job_id)
        except NexaraError as error:
            raise self._provider_error(error) from error
        if self._status(job.status, job.error) is not TranscriptionJobState.COMPLETED:
            raise TranscriptionProviderError(
                "TRANSCRIPTION_NOT_READY",
                "Nexara transcription is not ready",
                retryable=True,
            )
        try:
            result = Diarization.model_validate(job.result)
        except (TypeError, ValueError) as error:
            raise TranscriptionProviderError(
                "TRANSCRIPTION_INVALID_RESPONSE",
                "Nexara response does not contain a valid diarized transcript",
                retryable=False,
            ) from error
        utterances: list[TranscriptionUtterance] = []
        try:
            for segment in result.segments:
                start_ms = round(segment.start * 1_000)
                end_ms = round(segment.end * 1_000)
                if end_ms < start_ms:
                    raise ValueError
                utterances.append(
                    TranscriptionUtterance(
                        speaker=segment.speaker,
                        start_ms=start_ms,
                        end_ms=end_ms,
                        text=segment.text.strip(),
                    )
                )
        except ValueError as error:
            raise TranscriptionProviderError(
                "TRANSCRIPTION_INVALID_RESPONSE",
                "Nexara returned malformed diarized segments",
                retryable=False,
            ) from error
        if not utterances:
            raise TranscriptionProviderError(
                "TRANSCRIPTION_INVALID_RESPONSE",
                "Nexara returned an empty transcript",
                retryable=False,
            )
        return TranscriptionResult(
            language=result.language,
            duration_ms=round(result.duration * 1_000),
            utterances=utterances,
            raw_payload=self._safe_job_payload(job.model_dump(mode="json")),
        )

    async def close(self) -> None:
        await self.client.aclose()

    @staticmethod
    def _status(status: str, error: str | None) -> TranscriptionJobState:
        if status == "in_progress":
            return TranscriptionJobState.PROCESSING
        if status == "complete":
            return TranscriptionJobState.COMPLETED
        if status == "error":
            raise TranscriptionProviderError(
                "TRANSCRIPTION_PROVIDER_ERROR",
                "Nexara could not transcribe the recording",
                retryable=False,
            )
        raise TranscriptionProviderError(
            "TRANSCRIPTION_INVALID_RESPONSE",
            "Nexara returned an unknown job status",
            retryable=False,
        )

    @staticmethod
    def _safe_job_payload(data: dict[str, object]) -> dict[str, object]:
        return {key: value for key, value in data.items() if key not in {"result", "error"}}

    @staticmethod
    def _provider_error(error: NexaraError) -> TranscriptionProviderError:
        if isinstance(error, APIError):
            safe_detail = _URL_PATTERN.sub("<redacted-url>", error.detail)[:500]
            logger.warning(
                "Nexara API request failed status=%s detail=%s",
                error.status_code,
                safe_detail,
            )
        if isinstance(error, AuthenticationError):
            return TranscriptionProviderError(
                "TRANSCRIPTION_AUTH_ERROR",
                "Nexara credentials were rejected",
                retryable=False,
            )
        if isinstance(error, InsufficientBalanceError):
            return TranscriptionProviderError(
                "TRANSCRIPTION_BALANCE_ERROR",
                "Nexara balance is insufficient",
                retryable=False,
            )
        if isinstance(error, NotFoundError):
            return TranscriptionProviderError(
                "TRANSCRIPTION_RESULT_EXPIRED",
                "Nexara transcription result is unavailable or has expired",
                retryable=False,
            )
        if isinstance(error, BadRequestError | NexaraValidationError):
            return TranscriptionProviderError(
                "TRANSCRIPTION_INVALID_REQUEST",
                "Nexara rejected the transcription request",
                retryable=False,
            )
        if isinstance(
            error,
            APIConnectionError
            | APITimeoutError
            | RateLimitError
            | InternalServerError
            | BadGatewayError,
        ):
            return TranscriptionProviderError(
                "TRANSCRIPTION_PROVIDER_ERROR",
                "Nexara is temporarily unavailable",
                retryable=True,
            )
        if isinstance(error, APIError):
            return TranscriptionProviderError(
                "TRANSCRIPTION_PROVIDER_ERROR",
                "Nexara rejected the transcription request",
                retryable=False,
            )
        return TranscriptionProviderError(
            "TRANSCRIPTION_PROVIDER_ERROR",
            "Could not process the recording with Nexara",
            retryable=True,
        )


def build_transcription_provider(settings: Settings) -> TranscriptionProvider:
    if settings.transcription_provider == "fake":
        if settings.app_env == "production":
            raise RuntimeError("Fake transcription provider is forbidden in production")
        return FakeTranscriptionProvider()
    if settings.transcription_provider == "nexara":
        return NexaraTranscriptionProvider(settings)
    raise RuntimeError(f"Unsupported transcription provider: {settings.transcription_provider}")
