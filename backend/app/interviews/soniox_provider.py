"""Soniox asynchronous REST adapter; shares the persistent transcription workflow."""

from __future__ import annotations

from collections import Counter
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import anyio
import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import Settings
from app.interviews.intelligence_providers import (
    TranscriptionJob,
    TranscriptionJobState,
    TranscriptionProviderError,
    TranscriptionResult,
    TranscriptionUtterance,
)
from app.interviews.intelligence_transcript_context import COMMON_TERMS, TRACK_TERMS


class _Token(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str
    start_ms: int = Field(ge=0, strict=True)
    end_ms: int = Field(ge=0, strict=True)
    speaker: str | None = None
    language: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    # Soniox explicitly sends null for ordinary speech tokens.
    is_audio_event: bool | None = None


def _invalid_response() -> TranscriptionProviderError:
    return TranscriptionProviderError(
        "TRANSCRIPTION_INVALID_RESPONSE",
        "Soniox returned an invalid transcript response",
        retryable=False,
    )


def _identifier(value: object) -> str:
    try:
        return str(UUID(str(value)))
    except ValueError:
        raise _invalid_response() from None


def _safe_payload(data: dict[str, Any]) -> dict[str, object]:
    return {
        key: data[key]
        for key in ("status", "model", "created_at", "audio_duration_ms")
        if key in data and isinstance(data[key], str | int | float | bool)
    }


def _utterances(
    tokens: object, *, pause_ms: int = 1500, max_ms: int = 30_000, confidence_threshold: float = 0.6
) -> tuple[list[TranscriptionUtterance], str | None]:
    if not isinstance(tokens, list):
        raise _invalid_response()
    utterances: list[TranscriptionUtterance] = []
    languages: Counter[str] = Counter()
    parts: list[str] = []
    speaker: str | None = None
    start, end = 0, 0
    confidences: list[float] = []

    def flush() -> None:
        text = "".join(parts).strip()
        if text:
            utterances.append(
                TranscriptionUtterance(
                    speaker=speaker,
                    start_ms=start,
                    end_ms=end,
                    text=text,
                    quality={
                        "confidence_mean": sum(confidences) / len(confidences)
                        if confidences
                        else None,
                        "low_confidence_fraction": sum(
                            c < confidence_threshold for c in confidences
                        )
                        / len(confidences)
                        if confidences
                        else None,
                        "confidence_token_count": len(confidences),
                    },
                )
            )
        parts.clear()
        confidences.clear()

    for value in tokens:
        try:
            token = _Token.model_validate(value)
        except ValidationError:
            raise _invalid_response() from None
        if token.end_ms < token.start_ms:
            raise _invalid_response()
        if not token.text or token.is_audio_event:
            continue
        # Subword tokens already contain spacing; inserting spaces corrupts words.
        # Unattributed punctuation belongs to the current turn, unattributed speech
        # remains unknown rather than inheriting a potentially wrong speaker.
        lexical = any(char.isalnum() for char in token.text)
        next_speaker = ((token.speaker or "").strip() or None) if lexical else speaker
        if parts and (
            next_speaker != speaker
            or token.start_ms - end > pause_ms
            or (token.end_ms - start > max_ms and token.text[:1].isspace())
        ):
            flush()
        if not parts:
            speaker, start, end = next_speaker, token.start_ms, token.end_ms
        parts.append(token.text)
        end = max(end, token.end_ms)
        if token.confidence is not None and any(c.isalnum() for c in token.text):
            confidences.append(token.confidence)
        if token.language:
            languages[token.language] += len(token.text)
    flush()
    if not utterances:
        raise _invalid_response()
    return utterances, languages.most_common(1)[0][0] if languages else None


class SonioxTranscriptionProvider:
    name = "soniox"
    requires_file_upload = True

    def __init__(self, settings: Settings) -> None:
        if settings.soniox_api_key is None:
            raise TranscriptionProviderError(
                "TRANSCRIPTION_AUTH_ERROR",
                "Soniox API key is not configured",
                retryable=False,
            )
        self.settings = settings
        self.model = settings.soniox_model
        self.language_hints = settings.soniox_language_hints
        self.client = httpx.AsyncClient(
            base_url=settings.soniox_base_url.rstrip("/") + "/",
            headers={"Authorization": f"Bearer {settings.soniox_api_key.get_secret_value()}"},
            proxy=settings.soniox_proxy_url.get_secret_value()
            if settings.soniox_proxy_url
            else None,
            timeout=httpx.Timeout(settings.soniox_timeout_seconds, connect=30),
            trust_env=False,
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = await self.client.request(method, path, **kwargs)
        except httpx.RequestError:
            raise TranscriptionProviderError(
                "TRANSCRIPTION_PROVIDER_ERROR",
                "Could not connect to Soniox",
                retryable=True,
            ) from None
        status = response.status_code
        if method == "DELETE" and status in {200, 204, 404}:
            return {}
        if not response.is_success:
            code, message, retryable = {
                401: ("TRANSCRIPTION_AUTH_ERROR", "Soniox credentials were rejected", False),
                403: ("TRANSCRIPTION_AUTH_ERROR", "Soniox access was denied", False),
                402: (
                    "TRANSCRIPTION_BALANCE_ERROR",
                    "Soniox balance or budget is exhausted",
                    False,
                ),
                404: ("TRANSCRIPTION_RESULT_EXPIRED", "Soniox result is unavailable", False),
                409: (
                    "TRANSCRIPTION_CONFLICT",
                    "Soniox resource state conflicts with the request",
                    True,
                ),
                429: ("TRANSCRIPTION_PROVIDER_ERROR", "Soniox rate limit exceeded", True),
            }.get(
                status,
                (
                    "TRANSCRIPTION_PROVIDER_ERROR"
                    if status >= 500
                    else "TRANSCRIPTION_INVALID_REQUEST",
                    "Soniox could not process the request",
                    status >= 500 or status == 408,
                ),
            )
            # Never log response bodies: they can echo filenames, URLs or credentials.
            raise TranscriptionProviderError(code, message, retryable=retryable)
        try:
            data = response.json()
        except ValueError:
            raise _invalid_response() from None
        if not isinstance(data, dict):
            raise _invalid_response()
        return data

    def _job(self, data: dict[str, Any], *, allow_error: bool = False) -> TranscriptionJob:
        try:
            state = TranscriptionJobState(data["status"])
        except (KeyError, ValueError):
            raise _invalid_response() from None
        if state is TranscriptionJobState.ERROR and not allow_error:
            # Retrying a terminal job ID cannot repair a failed transcription.
            balance_exhausted = data.get("error_type") == "organization_balance_exhausted"
            raise TranscriptionProviderError(
                "TRANSCRIPTION_JOB_BALANCE_ERROR"
                if balance_exhausted
                else "TRANSCRIPTION_JOB_FAILED",
                "Soniox organization balance is exhausted"
                if balance_exhausted
                else "Soniox transcription job failed permanently",
                retryable=False,
            )
        return TranscriptionJob(
            provider_job_id=_identifier(data.get("id")),
            status=state,
            raw_payload=_safe_payload(data),
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
        del timestamps  # Soniox always includes millisecond token timestamps.
        if not diarization:
            raise TranscriptionProviderError(
                "TRANSCRIPTION_CONFIG_ERROR", "Speaker diarization is required", retryable=False
            )
        body: dict[str, Any] = {
            "model": self.model,
            "context": {
                "terms": list(
                    dict.fromkeys(
                        [*COMMON_TERMS, *(term for terms in TRACK_TERMS.values() for term in terms)]
                    )
                )
            },
            "enable_speaker_diarization": diarization,
            "enable_language_identification": True,
            "language_hints": [language] if language else self.language_hints,
        }
        if file_path is not None:
            uploaded = await self._upload(file_path)
            body["file_id"] = _identifier(uploaded.get("id"))
        elif file_url:
            body["audio_url"] = file_url
        else:
            raise TranscriptionProviderError(
                "TRANSCRIPTION_CONFIG_ERROR",
                "Soniox transcription source is not configured",
                retryable=False,
            )
        try:
            data = await self._request("POST", "transcriptions", json=body)
        except TranscriptionProviderError as error:
            # On a timeout/5xx the job may have been accepted; keep its input alive.
            if (
                not error.retryable
                and error.code != "TRANSCRIPTION_INVALID_RESPONSE"
                and "file_id" in body
            ):
                await self._delete_unsubmitted_file(body["file_id"])
            raise
        return self._job(data, allow_error=True)

    async def _upload(self, path: Path) -> dict[str, Any]:
        # httpx's built-in multipart file objects read synchronously. Stream bounded
        # chunks with anyio instead; disk reads run in its thread pool.
        boundary = uuid4().hex
        suffix = path.suffix if path.suffix.isascii() and path.suffix[1:].isalnum() else ".bin"
        header = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="recording{suffix}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
        trailer = f"\r\n--{boundary}--\r\n".encode()
        try:
            size = (await anyio.Path(path).stat()).st_size
            if size > self.settings.soniox_upload_max_bytes:
                raise TranscriptionProviderError(
                    "MEDIA_FILE_TOO_LARGE", "Soniox upload limit exceeded", retryable=False
                )

            async def content() -> AsyncIterator[bytes]:
                yield header
                async with await anyio.open_file(path, "rb") as source:
                    while chunk := await source.read(256 * 1024):
                        yield chunk
                yield trailer

            return await self._request(
                "POST",
                "files",
                content=content(),
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "Content-Length": str(len(header) + size + len(trailer)),
                },
            )
        except OSError:
            raise TranscriptionProviderError(
                "STORAGE_ERROR", "Could not read the staged recording", retryable=True
            ) from None

    async def _delete_unsubmitted_file(self, file_id: str) -> None:
        try:
            await self._request("DELETE", f"files/{file_id}")
        except TranscriptionProviderError:
            pass  # Preserve the original submission error.

    async def get_status(self, provider_job_id: str) -> TranscriptionJob:
        return self._job(
            await self._request("GET", f"transcriptions/{_identifier(provider_job_id)}")
        )

    async def get_result(self, provider_job_id: str) -> TranscriptionResult:
        path = f"transcriptions/{_identifier(provider_job_id)}"
        data = await self._request("GET", path)
        if self._job(data).status is not TranscriptionJobState.COMPLETED:
            raise TranscriptionProviderError(
                "TRANSCRIPTION_NOT_READY",
                "Soniox transcript is not ready",
                retryable=True,
            )
        transcript = await self._request("GET", path + "/transcript")
        if _identifier(transcript.get("id")) != _identifier(provider_job_id):
            raise _invalid_response()
        if _identifier(data.get("id")) != _identifier(provider_job_id):
            raise _invalid_response()
        utterances, language = _utterances(
            transcript.get("tokens"),
            pause_ms=self.settings.soniox_utterance_pause_ms,
            max_ms=self.settings.soniox_utterance_max_ms,
            confidence_threshold=self.settings.soniox_low_confidence_threshold,
        )
        speech_chars = sum(len(row.text) for row in utterances)
        unknown_chars = sum(len(row.text) for row in utterances if row.speaker is None)
        speaker_count = len({row.speaker for row in utterances if row.speaker is not None})
        quality = {
            "speaker_count": speaker_count,
            "unattributed_fraction": unknown_chars / max(speech_chars, 1),
            "unattributed_utterances": sum(row.speaker is None for row in utterances),
            "requires_review": speaker_count < 2
            or unknown_chars / max(speech_chars, 1)
            > self.settings.soniox_unattributed_fraction_limit,
        }
        duration = data.get("audio_duration_ms")
        duration_source = "provider"
        if not isinstance(duration, int) or isinstance(duration, bool) or duration < 0:
            duration = max(item.end_ms for item in utterances)
            duration_source = "last_token"
        return TranscriptionResult(
            language=language,
            duration_ms=duration,
            utterances=utterances,
            raw_payload={
                **_safe_payload(data),
                "duration_source": duration_source,
                "quality": quality,
            },
        )

    async def cleanup(self, provider_job_id: str) -> bool:
        # Called only after the transcript transaction has committed locally.
        path = f"transcriptions/{_identifier(provider_job_id)}"
        try:
            data = await self._request("GET", path)
        except TranscriptionProviderError as error:
            if error.code == "TRANSCRIPTION_RESULT_EXPIRED":
                return True
            raise
        if _identifier(data.get("id")) != _identifier(provider_job_id):
            raise _invalid_response()
        if data.get("status") not in {"completed", "error"}:
            return False
        file_id = data.get("file_id")
        # Delete the source first so a failed deletion can still be retried via job metadata.
        if file_id:
            await self._request("DELETE", f"files/{_identifier(file_id)}")
        await self._request("DELETE", path)
        return True

    async def check_connection(self) -> None:
        """Authenticated read-only probe; does not create a paid transcription."""
        data = await self._request("GET", "models")
        models = data.get("models")
        if not isinstance(models, list):
            raise _invalid_response()
        model = next(
            (item for item in models if isinstance(item, dict) and item.get("id") == self.model),
            None,
        )
        if model is None or model.get("transcription_mode") != "async":
            raise TranscriptionProviderError(
                "TRANSCRIPTION_CONFIG_ERROR",
                "Configured Soniox async model is not available",
                retryable=False,
            )
        languages = model.get("languages", [])
        supported = {item.get("code") for item in languages if isinstance(item, dict)}
        if not set(self.language_hints) <= supported:
            raise TranscriptionProviderError(
                "TRANSCRIPTION_CONFIG_ERROR",
                "Configured Soniox language hints are not supported",
                retryable=False,
            )
        # /models has no diarization capability flag. Validate actual output instead.

    async def close(self) -> None:
        await self.client.aclose()
