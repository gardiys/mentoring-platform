import json
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.interviews.intelligence_providers import (
    TranscriptionJobState,
    TranscriptionProviderError,
    build_transcription_provider,
)
from app.interviews.soniox_provider import SonioxTranscriptionProvider, _utterances


@pytest.fixture(autouse=True)
def reset_database():
    """Provider contract tests do not use a database or a paid API."""
    yield


async def provider(handler):
    instance = SonioxTranscriptionProvider(
        Settings(_env_file=None, soniox_api_key=SecretStr("test-key"))
    )
    await instance.client.aclose()
    instance.client = httpx.AsyncClient(
        base_url="https://api.soniox.com/v1/",
        headers={"Authorization": "Bearer test-key"},
        transport=httpx.MockTransport(handler),
    )
    return instance


async def test_upload_submit_uses_file_id_diarization_language_hints_and_safe_metadata(tmp_path):
    file_id, job_id = str(uuid4()), str(uuid4())
    calls = []

    def handler(request):
        calls.append(request.url.path)
        assert request.headers["Authorization"] == "Bearer test-key"
        if request.url.path == "/v1/files":
            assert b"sample audio" in request.content
            assert b'filename="recording.mp3"' in request.content
            return httpx.Response(201, json={"id": file_id})
        body = json.loads(request.content)
        assert "GIL" in body.pop("context")["terms"]
        assert body == {
            "file_id": file_id,
            "model": "stt-async-v5",
            "enable_speaker_diarization": True,
            "enable_language_identification": True,
            "language_hints": ["ru", "en"],
        }
        return httpx.Response(
            201,
            json={
                "id": job_id,
                "status": "queued",
                "audio_url": "https://secret/?token=private",
                "filename": "private.mp3",
            },
        )

    instance = await provider(handler)
    source = tmp_path / "private.mp3"
    source.write_bytes(b"sample audio")
    try:
        job = await instance.submit(
            file_path=source, file_url=None, language=None, diarization=True, timestamps=True
        )
        assert job.provider_job_id == job_id
        assert job.raw_payload == {"status": "queued"}
        assert calls == ["/v1/files", "/v1/transcriptions"]
    finally:
        await instance.close()


async def test_poll_and_result_join_subwords_preserve_turns_and_milliseconds():
    job_id = str(uuid4())
    tokens = [
        {"text": "Почему", "speaker": "1", "start_ms": 100, "end_ms": 500, "language": "ru"},
        {"text": " ушёл?", "speaker": "1", "start_ms": 510, "end_ms": 900, "language": "ru"},
        {
            "text": "Работал с Py",
            "speaker": "2",
            "start_ms": 1000,
            "end_ms": 1500,
            "language": "ru",
        },
        {"text": "thon", "speaker": "2", "start_ms": 1500, "end_ms": 1800, "language": "en"},
        {"text": ".", "start_ms": 1800, "end_ms": 1800},
        {
            "text": " Ещё вопрос?",
            "speaker": "1",
            "start_ms": 2100,
            "end_ms": 2500,
            "language": "ru",
        },
    ]

    def handler(request):
        if request.url.path.endswith("/transcript"):
            return httpx.Response(200, json={"id": job_id, "tokens": tokens})
        return httpx.Response(
            200, json={"id": job_id, "status": "completed", "audio_duration_ms": 3000}
        )

    instance = await provider(handler)
    try:
        assert (await instance.get_status(job_id)).status == TranscriptionJobState.COMPLETED
        result = await instance.get_result(job_id)
        assert result.duration_ms == 3000 and result.language == "ru"
        assert [row.text for row in result.utterances] == [
            "Почему ушёл?",
            "Работал с Python.",
            "Ещё вопрос?",
        ]
        assert [row.speaker for row in result.utterances] == ["1", "2", "1"]
        assert result.utterances[1].start_ms == 1000 and result.utterances[1].end_ms == 1800
        assert "tokens" not in result.raw_payload
    finally:
        await instance.close()


@pytest.mark.parametrize(
    "status,retryable,code",
    [
        (401, False, "TRANSCRIPTION_AUTH_ERROR"),
        (403, False, "TRANSCRIPTION_AUTH_ERROR"),
        (402, False, "TRANSCRIPTION_BALANCE_ERROR"),
        (404, False, "TRANSCRIPTION_RESULT_EXPIRED"),
        (409, True, "TRANSCRIPTION_CONFLICT"),
        (429, True, "TRANSCRIPTION_PROVIDER_ERROR"),
        (503, True, "TRANSCRIPTION_PROVIDER_ERROR"),
        (400, False, "TRANSCRIPTION_INVALID_REQUEST"),
    ],
)
async def test_errors_are_classified_without_leaking_details(status, retryable, code):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"message": "secret-key private-transcript"})

    instance = await provider(handler)
    try:
        with pytest.raises(TranscriptionProviderError) as error:
            await instance.get_status(str(uuid4()))
        assert error.value.code == code and error.value.retryable == retryable
        assert "secret" not in str(error.value) and len(calls) == 1
    finally:
        await instance.close()


async def test_proxy_transport_failure_is_retryable():
    def handler(request):
        raise httpx.ProxyError("proxy-password private", request=request)

    instance = await provider(handler)
    try:
        with pytest.raises(TranscriptionProviderError) as error:
            await instance.get_status(str(uuid4()))
        assert error.value.retryable and "password" not in str(error.value)
    finally:
        await instance.close()


@pytest.mark.parametrize(
    "tokens",
    [
        [],
        None,
        [{"text": "x", "start_ms": 20, "end_ms": 10}],
        [{"text": "x", "start_ms": -1, "end_ms": 10}],
        [{"text": "x", "end_ms": 10}],
    ],
)
def test_malformed_or_empty_transcript_is_rejected(tokens):
    with pytest.raises(TranscriptionProviderError):
        _utterances(tokens)


def test_unknown_speech_not_assigned_to_previous_speaker_and_pause_splits_turn():
    rows, _ = _utterances(
        [
            {"text": "Ответ.", "speaker": "2", "start_ms": 0, "end_ms": 1000},
            {"text": "Кто говорит?", "start_ms": 1100, "end_ms": 2000},
            {"text": "Продолжение", "start_ms": 5000, "end_ms": 6000},
        ]
    )
    assert [row.speaker for row in rows] == ["2", None, None]
    assert len(rows) == 3


@pytest.mark.parametrize("proxy", [None, "http://user:pass@proxy.example:3128"])
async def test_factory_and_optional_proxy_are_configured(monkeypatch, proxy):
    captured = {}
    original = httpx.AsyncClient

    def client(**kwargs):
        captured.update(kwargs)
        return original(transport=httpx.MockTransport(lambda _: httpx.Response(200)))

    monkeypatch.setattr(httpx, "AsyncClient", client)
    settings = Settings(
        _env_file=None,
        transcription_provider="soniox",
        soniox_api_key="test-key",
        soniox_proxy_url=proxy,
    )
    instance = build_transcription_provider(settings)
    assert instance.name == "soniox"
    assert captured["proxy"] == proxy and captured["trust_env"] is False
    await instance.close()


def test_empty_secrets_and_invalid_proxy_validation():
    settings = Settings(_env_file=None, soniox_api_key="", soniox_proxy_url="")
    assert settings.soniox_api_key is None and settings.soniox_proxy_url is None
    with pytest.raises(TranscriptionProviderError):
        SonioxTranscriptionProvider(settings)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, soniox_proxy_url="ftp://proxy.example")


async def test_cleanup_deletes_only_the_completed_job_and_its_file():
    job_id, file_id = str(uuid4()), str(uuid4())
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(
                200, json={"id": job_id, "file_id": file_id, "status": "completed"}
            )
        return httpx.Response(204)

    instance = await provider(handler)
    try:
        await instance.cleanup(job_id)
        assert calls == [
            ("GET", f"/v1/transcriptions/{job_id}"),
            ("DELETE", f"/v1/files/{file_id}"),
            ("DELETE", f"/v1/transcriptions/{job_id}"),
        ]
    finally:
        await instance.close()


@pytest.mark.parametrize("present", [True, False])
async def test_connectivity_check_is_read_only_and_checks_selected_model(present):
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "id": "stt-async-v5",
                        "transcription_mode": "async",
                        "languages": [{"code": "ru"}, {"code": "en"}],
                    }
                ]
                if present
                else []
            },
        )

    instance = await provider(handler)
    try:
        if present:
            await instance.check_connection()
        else:
            with pytest.raises(TranscriptionProviderError) as error:
                await instance.check_connection()
            assert error.value.code == "TRANSCRIPTION_CONFIG_ERROR"
        assert calls == [("GET", "/v1/models")]
    finally:
        await instance.close()


@pytest.mark.parametrize("status", ["queued", "processing", "error", "unexpected"])
async def test_incomplete_or_failed_jobs_do_not_fetch_a_transcript(status):
    job_id = str(uuid4())
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"id": job_id, "status": status})

    instance = await provider(handler)
    try:
        with pytest.raises(TranscriptionProviderError) as error:
            await instance.get_result(job_id)
        assert error.value.retryable == (status in {"queued", "processing"})
        assert calls == [f"/v1/transcriptions/{job_id}"]
    finally:
        await instance.close()


async def test_disabled_diarization_never_uploads():
    instance = await provider(lambda _: pytest.fail("No request expected"))
    try:
        with pytest.raises(TranscriptionProviderError) as error:
            await instance.submit(
                file_url="https://example.com/a",
                file_path=None,
                language=None,
                diarization=False,
                timestamps=True,
            )
        assert error.value.code == "TRANSCRIPTION_CONFIG_ERROR"
    finally:
        await instance.close()


@pytest.mark.parametrize("status", ["error", "processing", "queued", "missing"])
async def test_cleanup_terminal_error_missing_and_running_jobs(status):
    job_id, file_id = str(uuid4()), str(uuid4())
    deletes = []

    def handler(request):
        if request.method == "DELETE":
            deletes.append(request.url.path)
            return httpx.Response(404)  # idempotent partial cleanup
        if status == "missing":
            return httpx.Response(404)
        return httpx.Response(200, json={"id": job_id, "file_id": file_id, "status": status})

    instance = await provider(handler)
    try:
        assert await instance.cleanup(job_id) == (status in {"error", "missing"})
        assert len(deletes) == (2 if status == "error" else 0)
    finally:
        await instance.close()


@pytest.mark.parametrize(
    "speakers,review", [([None, None], True), (["1", "1"], True), (["1", "2"], False)]
)
async def test_diarization_gate_confidence_and_duration_provenance(speakers, review):
    job_id = str(uuid4())
    tokens = [
        {
            "text": text,
            "speaker": speaker,
            "start_ms": i * 1000,
            "end_ms": i * 1000 + 900,
            "confidence": confidence,
        }
        for i, (text, speaker, confidence) in enumerate(
            zip(["Почему?", "Ответ"], speakers, [0.9, 0.2], strict=True)
        )
    ]

    def handler(request):
        if request.url.path.endswith("/transcript"):
            return httpx.Response(200, json={"id": job_id, "tokens": tokens})
        return httpx.Response(200, json={"id": job_id, "status": "completed"})

    instance = await provider(handler)
    try:
        result = await instance.get_result(job_id)
        assert result.raw_payload["quality"]["requires_review"] == review
        assert result.raw_payload["duration_source"] == "last_token"
        assert result.duration_ms == 1900
        assert result.utterances[-1].quality["low_confidence_fraction"] > 0
        assert all(row.speaker != "unknown" for row in result.utterances)
    finally:
        await instance.close()


def test_long_monologue_splits_without_punctuation_but_preserves_subwords():
    tokens = [
        {"text": "Py", "speaker": "1", "start_ms": 0, "end_ms": 500},
        {"text": "thon", "speaker": "1", "start_ms": 500, "end_ms": 1200},
        {"text": " слово", "speaker": "1", "start_ms": 1200, "end_ms": 2000},
        {"text": " ещё", "speaker": "1", "start_ms": 2000, "end_ms": 2800},
    ]
    rows, _ = _utterances(tokens, max_ms=1500)
    assert [row.text for row in rows] == ["Python", "слово", "ещё"]


async def test_upload_limit_rejects_before_network(tmp_path):
    source = tmp_path / "big.mp4"
    source.write_bytes(b"12345")
    instance = await provider(lambda _: pytest.fail("No upload expected"))
    instance.settings.soniox_upload_max_bytes = 4
    try:
        with pytest.raises(TranscriptionProviderError) as error:
            await instance.submit(
                file_path=source, file_url=None, language=None, diarization=True, timestamps=True
            )
        assert error.value.code == "MEDIA_FILE_TOO_LARGE"
    finally:
        await instance.close()


@pytest.mark.parametrize("mode,languages", [("real_time", ["ru", "en"]), ("async", ["en"])])
async def test_connection_rejects_wrong_mode_or_language(mode, languages):
    instance = await provider(
        lambda _: httpx.Response(
            200,
            json={
                "models": [
                    {
                        "id": "stt-async-v5",
                        "transcription_mode": mode,
                        "languages": [{"code": code} for code in languages],
                    }
                ]
            },
        )
    )
    try:
        with pytest.raises(TranscriptionProviderError) as error:
            await instance.check_connection()
        assert error.value.code == "TRANSCRIPTION_CONFIG_ERROR"
    finally:
        await instance.close()


def test_punctuation_flicker_is_smoothed_but_short_spoken_interruptions_are_kept():
    rows, _ = _utterances(
        [
            {"text": "Да", "speaker": "1", "start_ms": 0, "end_ms": 400},
            {"text": ",", "speaker": "2", "start_ms": 400, "end_ms": 400},
            {"text": " продолжу", "speaker": "1", "start_ms": 400, "end_ms": 900},
            {"text": "Нет!", "speaker": "2", "start_ms": 900, "end_ms": 1000},
            {"text": " Хорошо", "speaker": "1", "start_ms": 1000, "end_ms": 1600},
        ]
    )
    assert [row.text for row in rows] == ["Да, продолжу", "Нет!", "Хорошо"]
    assert [row.speaker for row in rows] == ["1", "2", "1"]


@pytest.mark.parametrize(
    "error_type,code",
    [
        ("organization_balance_exhausted", "TRANSCRIPTION_JOB_BALANCE_ERROR"),
        ("processing_error", "TRANSCRIPTION_JOB_FAILED"),
    ],
)
async def test_terminal_job_error_is_distinct_from_http_or_transport_error(error_type, code):
    job_id = str(uuid4())
    instance = await provider(
        lambda _: httpx.Response(
            200,
            json={
                "id": job_id,
                "status": "error",
                "error_type": error_type,
                "error_message": "private URL and transcript must not leak",
            },
        )
    )
    try:
        with pytest.raises(TranscriptionProviderError) as error:
            await instance.get_status(job_id)
        assert error.value.code == code
        assert error.value.retryable is False
        assert "private" not in str(error.value)
    finally:
        await instance.close()


async def test_nullable_audio_event_in_completed_transcript_preserves_speech():
    job_id = str(uuid4())
    tokens = [
        {
            "text": "Почему?",
            "start_ms": 0,
            "end_ms": 700,
            "speaker": "1",
            "language": "ru",
            "confidence": 0.9,
            "is_audio_event": None,
            "translation_status": None,
        },
        {
            "text": "Ради роста.",
            "start_ms": 800,
            "end_ms": 1900,
            "speaker": "2",
            "language": "ru",
            "confidence": 1,
            "is_audio_event": None,
            "translation_status": None,
        },
        {
            "text": "[noise]",
            "start_ms": 1900,
            "end_ms": 2000,
            "speaker": "2",
            "is_audio_event": True,
        },
    ]

    def handler(request):
        if request.url.path.endswith("/transcript"):
            return httpx.Response(200, json={"id": job_id, "tokens": tokens})
        return httpx.Response(
            200, json={"id": job_id, "status": "completed", "audio_duration_ms": 2100}
        )

    instance = await provider(handler)
    try:
        result = await instance.get_result(job_id)
        assert [row.text for row in result.utterances] == ["Почему?", "Ради роста."]
        assert [row.speaker for row in result.utterances] == ["1", "2"]
        assert result.raw_payload["quality"]["requires_review"] is False
        assert result.duration_ms == 2100
    finally:
        await instance.close()
