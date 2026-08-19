from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

import pytest
from arq.connections import ArqRedis

from app.interviews import intelligence_jobs, intelligence_queue
from app.interviews.intelligence_jobs import (
    POLL_MAX_TRIES,
    AIWorkerSettings,
    TranscriptionWorkerSettings,
    WorkerSettings,
    _bounded_poll_delay,
    _deadline_reached,
    _retry_delay,
)
from app.interviews.intelligence_models import IntelligenceProcessingStatus
from app.interviews.intelligence_recovery import intelligence_recovery_job_name
from tests.conftest import TestSession


@dataclass
class StubJob:
    job_id: str


class RecordingRedis:
    def __init__(self, *, duplicate: bool = False) -> None:
        self.duplicate = duplicate
        self.calls: list[tuple[str, tuple[object, ...], dict[str, Any]]] = []

    async def enqueue_job(
        self,
        function: str,
        *args: object,
        **kwargs: Any,
    ) -> StubJob | None:
        self.calls.append((function, args, kwargs))
        if self.duplicate:
            return None
        return StubJob(job_id=cast(str, kwargs["_job_id"]))


@pytest.mark.asyncio
async def test_enqueue_uses_stable_id_expiry_and_treats_duplicate_as_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interview_id = str(uuid4())
    redis = RecordingRedis(duplicate=True)
    monkeypatch.setattr(intelligence_queue, "_job_expires_seconds", lambda: 123_456)

    job_id = await intelligence_queue.enqueue_intelligence_job(
        "poll_transcription",
        interview_id,
        defer_seconds=30,
        redis=cast(ArqRedis, redis),
    )

    expected_id = f"intelligence:{interview_id}:poll_transcription"
    assert job_id == expected_id
    assert redis.calls == [
        (
            "poll_transcription",
            (interview_id,),
            {
                "_expires": 123_456,
                "_job_id": expected_id,
                "_queue_name": intelligence_queue.TRANSCRIPTION_QUEUE_NAME,
                "_defer_by": 30,
            },
        )
    ]


def test_jobs_are_routed_to_independent_provider_queues() -> None:
    assert (
        intelligence_queue.intelligence_queue_name("submit_transcription")
        == intelligence_queue.TRANSCRIPTION_QUEUE_NAME
    )
    assert (
        intelligence_queue.intelligence_queue_name("generate_answer_reviews")
        == intelligence_queue.OPENAI_QUEUE_NAME
    )
    assert (
        intelligence_queue.intelligence_queue_name("refresh_interview_question_embeddings")
        == intelligence_queue.OPENAI_QUEUE_NAME
    )
    assert (
        intelligence_queue.intelligence_queue_name(
            "refresh_interview_card_duplicate_cache"
        )
        == intelligence_queue.OPENAI_QUEUE_NAME
    )
    with pytest.raises(ValueError, match="Unknown interview intelligence job"):
        intelligence_queue.intelligence_queue_name("unexpected_job")


@pytest.mark.asyncio
async def test_reconciler_handles_an_empty_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = RecordingRedis()
    monkeypatch.setattr(intelligence_jobs, "async_session_factory", TestSession)

    await intelligence_jobs.reconcile_intelligence_jobs({"redis": redis})

    assert redis.calls == []


def test_retry_backoff_has_stable_per_job_jitter() -> None:
    first = _retry_delay({"job_try": 2, "job_id": "interview-a"}, 60)
    repeated = _retry_delay({"job_try": 2, "job_id": "interview-a"}, 60)
    second = _retry_delay({"job_try": 2, "job_id": "interview-b"}, 60)

    assert 60 <= first <= 120
    assert first == repeated
    assert first != second


def test_poll_delay_is_bounded_by_overall_deadline() -> None:
    now = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)

    assert _deadline_reached(now, now=now) is True
    assert _deadline_reached(now + timedelta(seconds=1), now=now) is False
    assert _bounded_poll_delay(now + timedelta(seconds=25), 60, now=now) == 25


def test_worker_keeps_deterministic_ids_reusable_and_runs_reconciliation() -> None:
    poll_function = next(
        function
        for function in WorkerSettings.functions
        if getattr(function, "name", None) == "poll_transcription"
    )

    assert poll_function.max_tries == POLL_MAX_TRIES
    assert WorkerSettings.keep_result == 0
    assert len(WorkerSettings.cron_jobs) == 1
    assert WorkerSettings.cron_jobs[0].run_at_startup is True

    assert TranscriptionWorkerSettings.queue_name == intelligence_queue.TRANSCRIPTION_QUEUE_NAME
    assert (
        TranscriptionWorkerSettings.max_jobs
        == intelligence_jobs.settings.transcription_max_concurrency
    )
    assert (
        TranscriptionWorkerSettings.job_timeout
        == intelligence_jobs.settings.transcription_job_timeout_seconds
    )
    assert len(TranscriptionWorkerSettings.cron_jobs) == 1
    assert (
        TranscriptionWorkerSettings.health_check_interval
        == intelligence_jobs.WORKER_HEALTH_CHECK_INTERVAL_SECONDS
    )
    assert AIWorkerSettings.queue_name == intelligence_queue.OPENAI_QUEUE_NAME
    assert AIWorkerSettings.max_jobs == intelligence_jobs.settings.openai_max_concurrency
    assert AIWorkerSettings.job_timeout == intelligence_jobs.settings.openai_job_timeout_seconds
    assert len(AIWorkerSettings.cron_jobs) == 2
    assert all(job.run_at_startup is True for job in AIWorkerSettings.cron_jobs)
    assert intelligence_jobs.refresh_interview_question_embeddings in AIWorkerSettings.functions
    assert (
        intelligence_jobs.refresh_interview_card_duplicate_cache
        in AIWorkerSettings.functions
    )
    assert (
        AIWorkerSettings.health_check_interval
        == intelligence_jobs.WORKER_HEALTH_CHECK_INTERVAL_SECONDS
    )


@pytest.mark.parametrize(
    ("status", "provider_job_id", "speaker", "extracted", "expected"),
    [
        (IntelligenceProcessingStatus.UPLOADED, None, False, False, "submit_transcription"),
        (
            IntelligenceProcessingStatus.TRANSCRIPTION_SUBMITTED,
            "provider-job",
            False,
            False,
            "poll_transcription",
        ),
        (
            IntelligenceProcessingStatus.TRANSCRIPTION_SUBMITTED,
            None,
            False,
            False,
            "submit_transcription",
        ),
        (
            IntelligenceProcessingStatus.TRANSCRIBING,
            "provider-job",
            False,
            False,
            "poll_transcription",
        ),
        (
            IntelligenceProcessingStatus.TRANSCRIBING,
            None,
            False,
            False,
            "submit_transcription",
        ),
        (
            IntelligenceProcessingStatus.TRANSCRIPT_READY,
            "provider-job",
            False,
            False,
            "process_transcription_result",
        ),
        (
            IntelligenceProcessingStatus.ANALYZING,
            None,
            True,
            False,
            "extract_interview_structure",
        ),
        (
            IntelligenceProcessingStatus.ANALYZING,
            None,
            True,
            True,
            "generate_answer_reviews",
        ),
        (IntelligenceProcessingStatus.ANALYZING, None, False, False, None),
        (IntelligenceProcessingStatus.AWAITING_CANDIDATE_SPEAKER, None, True, True, None),
        (IntelligenceProcessingStatus.READY, None, True, True, None),
        (IntelligenceProcessingStatus.FAILED, None, True, True, None),
    ],
)
def test_recovery_maps_only_actionable_states(
    status: IntelligenceProcessingStatus,
    provider_job_id: str | None,
    speaker: bool,
    extracted: bool,
    expected: str | None,
) -> None:
    assert (
        intelligence_recovery_job_name(
            status,
            transcription_provider_job_id=provider_job_id,
            candidate_speaker_selected=speaker,
            extraction_completed=extracted,
        )
        == expected
    )
