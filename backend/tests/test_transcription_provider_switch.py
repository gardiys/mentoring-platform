from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.interviews import intelligence_jobs
from app.interviews.intelligence_models import (
    IntelligenceInterview,
    IntelligenceProcessingStatus,
    IntelligenceTranscriptionUsage,
    IntelligenceUtterance,
)
from app.interviews.intelligence_providers import (
    FakeTranscriptionProvider,
    TranscriptionProviderError,
)
from tests.conftest import TestSession
from tests.test_interview_intelligence_api import (
    RecordingRedis,
    StubUploadStore,
    create_analysis_from_journal,
)


@pytest.mark.parametrize("old_name,new_name", [("nexara", "soniox"), ("soniox", "nexara")])
async def test_switch_keeps_poll_result_usage_and_cleanup_on_original_provider(
    client,
    seeded,
    monkeypatch,
    old_name,
    new_name,
):
    created, _, _ = await create_analysis_from_journal(client, seeded, monkeypatch)
    interview_id = UUID(created.json()["id"])
    monkeypatch.setattr(intelligence_jobs, "async_session_factory", TestSession)
    old = FakeTranscriptionProvider()
    old.name = old_name
    new = FakeTranscriptionProvider()
    new.name = new_name
    ctx = {
        "redis": RecordingRedis(),
        "transcription_provider": old,
        "upload_store": StubUploadStore(),
    }
    await intelligence_jobs.submit_transcription(ctx, str(interview_id))
    calls = []
    original_poll, original_result = old.get_status, old.get_result

    async def poll(job_id):
        calls.append("poll")
        return await original_poll(job_id)

    async def result(job_id):
        calls.append("result")
        return await original_result(job_id)

    async def cleanup(job_id):
        async with TestSession() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(IntelligenceUtterance)
                .where(IntelligenceUtterance.interview_id == interview_id)
            )
            assert count == 4  # another connection can see the committed transcript
        calls.append("cleanup")
        raise TranscriptionProviderError(
            "TRANSCRIPTION_PROVIDER_ERROR", "cleanup unavailable", retryable=True
        )

    monkeypatch.setattr(old, "get_status", poll)
    monkeypatch.setattr(old, "get_result", result)
    monkeypatch.setattr(old, "cleanup", cleanup, raising=False)
    built = []

    def build(settings, *, provider_name):
        built.append(provider_name)
        assert provider_name == old_name
        return old

    monkeypatch.setattr(intelligence_jobs, "build_transcription_provider", build)
    ctx["transcription_provider"] = new
    await intelligence_jobs.poll_transcription(ctx, str(interview_id))
    await intelligence_jobs.process_transcription_result(ctx, str(interview_id))
    assert calls == ["poll", "result", "cleanup"]
    assert built == [old_name]
    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, interview_id)
        assert interview.transcription_provider == old_name
        assert (
            interview.processing_status == IntelligenceProcessingStatus.AWAITING_CANDIDATE_SPEAKER
        )
        usage = await session.scalar(
            select(IntelligenceTranscriptionUsage).where(
                IntelligenceTranscriptionUsage.interview_id == interview_id
            )
        )
        assert usage.provider == old_name


async def test_missing_old_provider_credentials_fails_explicitly_without_resubmission(
    client,
    seeded,
    monkeypatch,
):
    created, _, _ = await create_analysis_from_journal(client, seeded, monkeypatch)
    interview_id = UUID(created.json()["id"])
    monkeypatch.setattr(intelligence_jobs, "async_session_factory", TestSession)
    old = FakeTranscriptionProvider()
    old.name = "nexara"
    ctx = {
        "redis": RecordingRedis(),
        "transcription_provider": old,
        "upload_store": StubUploadStore(),
    }
    await intelligence_jobs.submit_transcription(ctx, str(interview_id))
    new = FakeTranscriptionProvider()
    new.name = "soniox"
    ctx["transcription_provider"] = new

    def missing(settings, *, provider_name):
        raise TranscriptionProviderError(
            "TRANSCRIPTION_AUTH_ERROR", "Missing credentials", retryable=False
        )

    monkeypatch.setattr(intelligence_jobs, "build_transcription_provider", missing)
    await intelligence_jobs.poll_transcription(ctx, str(interview_id))
    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, interview_id)
        assert interview.processing_status == IntelligenceProcessingStatus.FAILED
        assert interview.processing_error_code == "TRANSCRIPTION_AUTH_ERROR"
        assert interview.transcription_provider_job_id == "fake-interview"
