from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select

from app.interviews import intelligence_jobs, transcription_cleanup
from app.interviews.intelligence_models import (
    IntelligenceInterview,
    IntelligenceProcessingStatus,
    IntelligenceSpeaker,
    IntelligenceTranscriptionCleanup,
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


async def prepared(client, seeded, monkeypatch):
    created, _, _ = await create_analysis_from_journal(client, seeded, monkeypatch)
    interview_id = UUID(created.json()["id"])
    monkeypatch.setattr(intelligence_jobs, "async_session_factory", TestSession)
    old = FakeTranscriptionProvider()
    old.name = "soniox"
    ctx = {
        "redis": RecordingRedis(),
        "transcription_provider": old,
        "upload_store": StubUploadStore(),
    }
    await intelligence_jobs.submit_transcription(ctx, str(interview_id))
    return interview_id, old, ctx


async def test_unknown_speech_saved_without_speaker_and_quality_requires_confirmation(
    client, seeded, monkeypatch
):
    interview_id, old, ctx = await prepared(client, seeded, monkeypatch)
    original = old.get_result

    async def result(job_id):
        value = await original(job_id)
        value.utterances[0].speaker = None
        value.utterances[0].quality = {"low_confidence_fraction": 0.8}
        value.raw_payload = {"quality": {"requires_review": True, "speaker_count": 2}}
        return value

    monkeypatch.setattr(old, "get_result", result)
    await intelligence_jobs.process_transcription_result(ctx, str(interview_id))
    async with TestSession() as session:
        utterances = list(
            await session.scalars(
                select(IntelligenceUtterance).order_by(IntelligenceUtterance.sequence_number)
            )
        )
        speakers = list(await session.scalars(select(IntelligenceSpeaker)))
        assert utterances[0].speaker_id is None
        assert utterances[0].recognition_quality["low_confidence_fraction"] == 0.8
        assert all(s.provider_speaker_key != "unknown" for s in speakers)
        from app.interviews.intelligence_service import (
            intelligence_detail,
            select_candidate_speaker,
        )
        from app.users.models import User

        interview = await session.get(IntelligenceInterview, interview_id)
        user = await session.get(User, interview.student_id)
        detail = await intelligence_detail(session, user, interview_id)
        assert detail.transcript[0].speaker_id is None
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as error:
            await select_candidate_speaker(session, user, interview_id, speakers[0].id)
        assert error.value.status_code == 409
        await select_candidate_speaker(
            session, user, interview_id, speakers[0].id, accept_transcription_quality=True
        )
        assert interview.processing_status == IntelligenceProcessingStatus.ANALYZING


@pytest.mark.parametrize(
    "status,should_clean",
    [
        (IntelligenceProcessingStatus.FAILED, True),
        (IntelligenceProcessingStatus.AWAITING_CANDIDATE_SPEAKER, True),
        (IntelligenceProcessingStatus.TRANSCRIPTION_SUBMITTED, False),
    ],
)
async def test_sweeper_retries_failure_and_skips_unsaved_transcripts(
    client, seeded, monkeypatch, status, should_clean
):
    interview_id, _, _ = await prepared(client, seeded, monkeypatch)
    monkeypatch.setattr(transcription_cleanup, "async_session_factory", TestSession)
    calls = []

    class Cleaner:
        def __init__(self, settings):
            pass

        async def cleanup(self, job_id):
            calls.append(job_id)
            if len(calls) == 1:
                raise TranscriptionProviderError(
                    "TRANSCRIPTION_PROVIDER_ERROR", "offline", retryable=True
                )
            return True

        async def close(self):
            pass

    monkeypatch.setattr(transcription_cleanup, "SonioxTranscriptionProvider", Cleaner)
    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, interview_id)
        interview.processing_status = status
        await session.commit()
    await transcription_cleanup.sweep_soniox_resources({})
    async with TestSession() as session:
        row = await session.get(IntelligenceTranscriptionCleanup, "fake-interview")
        assert row.completed_at is None
        row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    await transcription_cleanup.sweep_soniox_resources({})
    assert len(calls) == (2 if should_clean else 0)
    async with TestSession() as session:
        row = await session.get(IntelligenceTranscriptionCleanup, "fake-interview")
        assert (row.completed_at is not None) == should_clean
    await transcription_cleanup.sweep_soniox_resources({})
    assert len(calls) == (2 if should_clean else 0)


async def test_migration_preserves_legacy_unknown_speech_and_blocks_silent_selection(
    client, seeded, monkeypatch
):
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    from app.interviews.intelligence_models import IntelligenceSpeakerRole
    from tests.conftest import test_engine

    interview_id, _, _ = await prepared(client, seeded, monkeypatch)
    async with TestSession() as session:
        speaker = IntelligenceSpeaker(
            interview_id=interview_id,
            provider_speaker_key="unknown",
            role=IntelligenceSpeakerRole.CANDIDATE,
        )
        session.add(speaker)
        await session.flush()
        session.add(
            IntelligenceUtterance(
                interview_id=interview_id,
                speaker_id=speaker.id,
                sequence_number=1,
                start_ms=0,
                end_ms=1000,
                text="Сохранить речь",
            )
        )
        interview = await session.get(IntelligenceInterview, interview_id)
        interview.candidate_speaker_id = speaker.id
        await session.commit()
    path = (
        Path(__file__).resolve().parents[1]
        / "migrations/versions/20261001_0096_transcription_quality.py"
    )
    spec = importlib.util.spec_from_file_location("quality_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def round_trip(connection):
        with Operations.context(MigrationContext.configure(connection)):
            module.downgrade()
            module.upgrade()

    async with test_engine.begin() as connection:
        await connection.run_sync(round_trip)
    async with TestSession() as session:
        row = await session.scalar(
            select(IntelligenceUtterance).where(IntelligenceUtterance.interview_id == interview_id)
        )
        assert row.text == "Сохранить речь" and row.speaker_id is None
        interview = await session.get(IntelligenceInterview, interview_id)
        assert interview.candidate_speaker_id is None
        assert interview.transcription_provider_payload["quality"] == {
            "speaker_count": 0,
            "unattributed_utterances": 1,
            "unattributed_fraction": 1.0,
            "requires_review": True,
        }


async def test_explicit_retry_after_cleanup_submits_once_instead_of_polling_deleted_job(
    client, seeded, monkeypatch
):
    from app.interviews import intelligence_service
    from app.interviews.intelligence_models import IntelligenceAttemptStage
    from app.interviews.intelligence_service import prepare_processing_retry
    from app.users.models import User

    monkeypatch.setattr(intelligence_service.settings, "interview_ai_daily_limit", 2)
    interview_id, _, _ = await prepared(client, seeded, monkeypatch)
    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, interview_id)
        interview.processing_status = IntelligenceProcessingStatus.FAILED
        interview.failed_stage = IntelligenceAttemptStage.TRANSCRIPTION_PARSE
        interview.processing_error_code = "TRANSCRIPTION_INVALID_RESPONSE"
        row = await session.get(
            IntelligenceTranscriptionCleanup, interview.transcription_provider_job_id
        )
        row.completed_at = datetime.now(UTC)
        await session.commit()
        user = await session.get(User, interview.student_id)
        _, job = await prepare_processing_retry(session, user, interview_id)
        assert job == "submit_transcription"
        assert interview.transcription_provider_job_id is None


@pytest.mark.parametrize("stage", ["transcription_poll", "transcription_parse"])
@pytest.mark.parametrize(
    "code,diagnostic,resubmit",
    [
        ("TRANSCRIPTION_JOB_BALANCE_ERROR", "Soniox organization balance is exhausted", True),
        ("TRANSCRIPTION_JOB_FAILED", "Soniox transcription job failed permanently", True),
        ("TRANSCRIPTION_PROVIDER_ERROR", "Soniox could not transcribe the recording", True),
        ("TRANSCRIPTION_PROVIDER_ERROR", "Could not connect to Soniox", False),
    ],
)
async def test_retry_terminal_job_without_waiting_for_sweeper(
    client,
    seeded,
    monkeypatch,
    stage,
    code,
    diagnostic,
    resubmit,
):
    from app.interviews import intelligence_service
    from app.interviews.intelligence_models import (
        IntelligenceAttemptStage,
        IntelligenceAttemptStatus,
        IntelligenceProcessingAttempt,
    )
    from app.users.models import User

    monkeypatch.setattr(intelligence_service.settings, "interview_ai_daily_limit", 2)
    interview_id, _, _ = await prepared(client, seeded, monkeypatch)
    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, interview_id)
        interview.processing_status = IntelligenceProcessingStatus.FAILED
        interview.failed_stage = IntelligenceAttemptStage(stage)
        interview.processing_error_code = code
        session.add(
            IntelligenceProcessingAttempt(
                interview_id=interview.id,
                stage=interview.failed_stage,
                provider="soniox",
                status=IntelligenceAttemptStatus.FAILED,
                attempt_number=1,
                error_code=code,
                error_message=diagnostic,
            )
        )
        await session.commit()
        user = await session.get(User, interview.student_id)
        _, job = await intelligence_service.prepare_processing_retry(session, user, interview_id)
        assert (job == "submit_transcription") == resubmit
        assert (interview.transcription_provider_job_id is None) == resubmit
        if not resubmit:
            assert job == (
                "poll_transcription"
                if stage == "transcription_poll"
                else "process_transcription_result"
            )
        cleanup = await session.get(IntelligenceTranscriptionCleanup, "fake-interview")
        assert cleanup.completed_at is None  # do not depend on the cleanup schedule
