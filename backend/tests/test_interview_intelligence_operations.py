from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.config import get_settings
from app.interviews import (
    intelligence_operations_router,
    intelligence_operations_service,
    intelligence_service,
)
from app.interviews.intelligence_models import (
    IntelligenceAIAdmission,
    IntelligenceAttemptStage,
    IntelligenceAttemptStatus,
    IntelligenceInterview,
    IntelligenceInterviewType,
    IntelligenceProcessingAttempt,
    IntelligenceProcessingStatus,
)
from app.interviews.intelligence_schemas import (
    IntelligenceOperationsQueueRead,
    IntelligenceOperationsWorkerRead,
    IntelligenceOperationsWorkersRead,
)
from app.interviews.models import (
    Company,
    InterviewProcess,
    InterviewProcessStage,
    InterviewStageType,
)
from tests.conftest import SeededData, TestSession, auth


class FakeRedisPipeline:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.commands: list[tuple[str, str]] = []

    async def __aenter__(self) -> "FakeRedisPipeline":
        return self

    async def __aexit__(self, *args: object) -> None:
        del args

    def zcard(self, key: str) -> None:
        self.commands.append(("zcard", key))

    def get(self, key: str) -> None:
        self.commands.append(("get", key))

    def pttl(self, key: str) -> None:
        self.commands.append(("pttl", key))

    async def execute(self) -> list[int | str]:
        if self.error is not None:
            raise self.error
        return [
            7,
            3,
            "Aug-03 12:00:00 j_complete=4 j_failed=0 j_retried=1 j_ongoing=1 queued=7",
            29_400,
            "Aug-03 12:00:01 j_complete=2 j_failed=1 j_retried=0 j_ongoing=2 queued=3",
            14_100,
        ]


class FakeRedis:
    instance: "FakeRedis"
    pipeline_error: Exception | None = None
    close_error: Exception | None = None

    def __init__(self) -> None:
        self.redis_pipeline = FakeRedisPipeline(error=self.pipeline_error)
        self.closed = False
        type(self).instance = self

    @classmethod
    def from_url(cls, *_args: object, **_kwargs: object) -> "FakeRedis":
        return cls()

    def pipeline(self, *, transaction: bool) -> FakeRedisPipeline:
        assert transaction is False
        return self.redis_pipeline

    async def aclose(self) -> None:
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


async def seed_operations_data(
    seeded: SeededData,
    now: datetime,
) -> dict[IntelligenceProcessingStatus, IntelligenceInterview]:
    timezone = ZoneInfo(get_settings().interview_ai_quota_timezone)
    local_start = now.astimezone(timezone).replace(hour=0, minute=0, second=0, microsecond=0)
    today = local_start.astimezone(UTC)
    yesterday = today - timedelta(days=1)

    async with TestSession() as session:
        company = Company(
            name="Operations",
            normalized_name="operations",
            transliterated_name="operations",
        )
        session.add(company)
        await session.flush()
        process = InterviewProcess(
            user_id=seeded.student_id,
            track_id=seeded.python_track_id,
            company_id=company.id,
            company_name=company.name,
        )
        session.add(process)
        await session.flush()

        statuses = (
            IntelligenceProcessingStatus.DRAFT,
            IntelligenceProcessingStatus.UPLOADED,
            IntelligenceProcessingStatus.ANALYZING,
            IntelligenceProcessingStatus.READY,
            IntelligenceProcessingStatus.FAILED,
        )
        updated_at = (
            now - timedelta(hours=5),
            now - timedelta(hours=2),
            now - timedelta(minutes=15),
            now - timedelta(minutes=10),
            now - timedelta(minutes=5),
        )
        requested_at = (None, today, today, today, yesterday)
        interviews: list[IntelligenceInterview] = []
        for index, (processing_status, status_updated_at) in enumerate(
            zip(statuses, updated_at, strict=True)
        ):
            stage = InterviewProcessStage(
                process_id=process.id,
                stage_type=InterviewStageType.TECHNICAL_INTERVIEW,
                scheduled_at=now - timedelta(days=index),
            )
            session.add(stage)
            await session.flush()
            interview = IntelligenceInterview(
                stage_id=stage.id,
                student_id=seeded.student_id,
                interview_type=IntelligenceInterviewType.TECHNICAL,
                processing_status=processing_status,
                created_at=status_updated_at,
                updated_at=status_updated_at,
            )
            session.add(interview)
            interviews.append(interview)
        await session.flush()
        session.add_all(
            [
                IntelligenceAIAdmission(
                    requester_user_id=seeded.student_id,
                    interview_id=interview.id,
                    operation="analysis",
                    requested_at=admission_requested_at,
                )
                for interview, admission_requested_at in zip(
                    interviews,
                    requested_at,
                    strict=True,
                )
                if admission_requested_at is not None
            ]
        )

        failed_interview = interviews[-1]
        session.add_all(
            [
                IntelligenceProcessingAttempt(
                    interview_id=failed_interview.id,
                    stage=IntelligenceAttemptStage.AI_EXTRACT,
                    status=IntelligenceAttemptStatus.FAILED,
                    attempt_number=1,
                    error_code="OPENAI_RATE_LIMIT",
                    started_at=now - timedelta(hours=2),
                    finished_at=now - timedelta(hours=2),
                ),
                IntelligenceProcessingAttempt(
                    interview_id=failed_interview.id,
                    stage=IntelligenceAttemptStage.AI_EXTRACT,
                    status=IntelligenceAttemptStatus.FAILED,
                    attempt_number=2,
                    error_code="OPENAI_RATE_LIMIT",
                    started_at=now - timedelta(hours=1),
                    finished_at=now - timedelta(hours=1),
                ),
                IntelligenceProcessingAttempt(
                    interview_id=failed_interview.id,
                    stage=IntelligenceAttemptStage.AI_REVIEW,
                    status=IntelligenceAttemptStatus.FAILED,
                    attempt_number=1,
                    started_at=now - timedelta(minutes=30),
                    finished_at=now - timedelta(minutes=30),
                ),
                IntelligenceProcessingAttempt(
                    interview_id=failed_interview.id,
                    stage=IntelligenceAttemptStage.TRANSCRIPTION_SUBMIT,
                    status=IntelligenceAttemptStatus.FAILED,
                    attempt_number=1,
                    error_code="OLD_FAILURE",
                    started_at=now - timedelta(hours=26),
                    finished_at=now - timedelta(hours=26),
                ),
            ]
        )
        await session.commit()
        return {interview.processing_status: interview for interview in interviews}


@pytest.mark.asyncio
async def test_admin_ai_operations_returns_pipeline_aggregates(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    await seed_operations_data(seeded, now)

    async def redis_metrics() -> intelligence_operations_service.IntelligenceRedisMetrics:
        return intelligence_operations_service.IntelligenceRedisMetrics(
            queues=IntelligenceOperationsQueueRead(
                available=True,
                transcription_depth=7,
                openai_depth=3,
            ),
            workers=IntelligenceOperationsWorkersRead(
                transcription=IntelligenceOperationsWorkerRead(
                    status="healthy",
                    heartbeat="transcription heartbeat",
                    heartbeat_ttl_seconds=30,
                ),
                openai=IntelligenceOperationsWorkerRead(
                    status="healthy",
                    heartbeat="openai heartbeat",
                    heartbeat_ttl_seconds=15,
                ),
            ),
        )

    monkeypatch.setattr(
        intelligence_operations_service,
        "intelligence_redis_metrics",
        redis_metrics,
    )
    response = await client.get(
        "/api/v1/admin/interviews/ai-operations",
        headers=auth(seeded.admin_id),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 5
    assert body["active"] == 2
    assert body["ready"] == 1
    assert body["failed"] == 1
    assert body["by_status"]["draft"] == 1
    assert body["by_status"]["uploaded"] == 1
    assert body["by_status"]["analyzing"] == 1
    assert body["by_status"]["ready"] == 1
    assert body["by_status"]["failed"] == 1
    assert body["by_status"]["transcribing"] == 0
    assert body["launches_today"] == 3
    assert 7_190 <= body["oldest_active_age_seconds"] <= 7_220
    assert body["failure_codes_24h"] == [
        {"code": "OPENAI_RATE_LIMIT", "count": 2},
        {"code": "UNKNOWN", "count": 1},
    ]
    assert body["queues"] == {
        "available": True,
        "transcription_depth": 7,
        "openai_depth": 3,
    }
    assert body["workers"] == {
        "transcription": {
            "status": "healthy",
            "heartbeat": "transcription heartbeat",
            "heartbeat_ttl_seconds": 30,
        },
        "openai": {
            "status": "healthy",
            "heartbeat": "openai heartbeat",
            "heartbeat_ttl_seconds": 15,
        },
    }


@pytest.mark.asyncio
async def test_admin_requeues_uploaded_processing_without_quota_or_state_changes(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interviews = await seed_operations_data(seeded, datetime.now(UTC))
    uploaded_id = interviews[IntelligenceProcessingStatus.UPLOADED].id
    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, uploaded_id)
        assert interview is not None
        interview.failed_stage = IntelligenceAttemptStage.TRANSCRIPTION_SUBMIT
        interview.processing_error_code = "TRANSCRIPTION_TEMPORARY_ERROR"
        interview.processing_error_message = "Повторная попытка ожидает worker."
        await session.commit()
        admissions_before = int(
            await session.scalar(select(func.count(IntelligenceAIAdmission.id))) or 0
        )

    requested = await client.get(
        "/api/v1/mentor/interviews?status=requested",
        headers=auth(seeded.admin_id),
    )
    assert requested.status_code == 200, requested.text
    assert requested.json()["total"] == 1
    requested_item = requested.json()["items"][0]
    assert requested_item["id"] == str(uploaded_id)
    assert requested_item["failed_stage"] == "transcription_submit"
    assert requested_item["processing_error_code"] == "TRANSCRIPTION_TEMPORARY_ERROR"
    assert requested_item["processing_error_message"] == "Повторная попытка ожидает worker."
    assert requested_item["can_requeue_processing"] is True

    for user_id in (seeded.student_id, seeded.mentor_id):
        forbidden = await client.post(
            f"/api/v1/admin/interviews/ai-operations/{uploaded_id}/requeue",
            headers=auth(user_id),
        )
        assert forbidden.status_code == 403

    async def capacity_must_not_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Operational requeue must not check launch capacity")

    enqueued: list[tuple[str, str]] = []

    async def enqueue(function: str, interview_id: str) -> str:
        enqueued.append((function, interview_id))
        return f"job:{function}:{interview_id}"

    monkeypatch.setattr(
        intelligence_service,
        "_ensure_ai_analysis_capacity",
        capacity_must_not_run,
    )
    monkeypatch.setattr(
        intelligence_operations_router,
        "enqueue_intelligence_job",
        enqueue,
    )
    requeued = await client.post(
        f"/api/v1/admin/interviews/ai-operations/{uploaded_id}/requeue",
        headers=auth(seeded.admin_id),
    )

    assert requeued.status_code == 200, requeued.text
    assert enqueued == [("submit_transcription", str(uploaded_id))]
    body = requeued.json()
    assert body["processing_status"] == "uploaded"
    assert body["failed_stage"] == "transcription_submit"
    assert body["processing_error_code"] == "TRANSCRIPTION_TEMPORARY_ERROR"
    assert body["processing_error_message"] == "Повторная попытка ожидает worker."
    assert body["can_requeue_processing"] is True

    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, uploaded_id)
        admissions_after = int(
            await session.scalar(select(func.count(IntelligenceAIAdmission.id))) or 0
        )
        assert interview is not None
        assert interview.processing_status is IntelligenceProcessingStatus.UPLOADED
        assert interview.failed_stage is IntelligenceAttemptStage.TRANSCRIPTION_SUBMIT
        assert interview.processing_error_code == "TRANSCRIPTION_TEMPORARY_ERROR"
        assert interview.processing_error_message == "Повторная попытка ожидает worker."
        assert admissions_after == admissions_before


@pytest.mark.asyncio
async def test_admin_requeue_enqueue_failure_leaves_database_unchanged(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interviews = await seed_operations_data(seeded, datetime.now(UTC))
    uploaded_id = interviews[IntelligenceProcessingStatus.UPLOADED].id
    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, uploaded_id)
        assert interview is not None
        interview.failed_stage = IntelligenceAttemptStage.TRANSCRIPTION_SUBMIT
        interview.processing_error_code = "TRANSCRIPTION_TEMPORARY_ERROR"
        interview.processing_error_message = "Temporary failure"
        await session.commit()
        admissions_before = int(
            await session.scalar(select(func.count(IntelligenceAIAdmission.id))) or 0
        )

    async def unavailable(_function: str, _interview_id: str) -> str:
        raise ConnectionError("Redis is unavailable")

    monkeypatch.setattr(
        intelligence_operations_router,
        "enqueue_intelligence_job",
        unavailable,
    )
    response = await client.post(
        f"/api/v1/admin/interviews/ai-operations/{uploaded_id}/requeue",
        headers=auth(seeded.admin_id),
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "interview_processing_unavailable"
    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, uploaded_id)
        admissions_after = int(
            await session.scalar(select(func.count(IntelligenceAIAdmission.id))) or 0
        )
        assert interview is not None
        assert interview.processing_status is IntelligenceProcessingStatus.UPLOADED
        assert interview.failed_stage is IntelligenceAttemptStage.TRANSCRIPTION_SUBMIT
        assert interview.processing_error_code == "TRANSCRIPTION_TEMPORARY_ERROR"
        assert interview.processing_error_message == "Temporary failure"
        assert admissions_after == admissions_before


@pytest.mark.parametrize(
    ("processing_status", "expected_code"),
    [
        (
            IntelligenceProcessingStatus.DRAFT,
            "interview_processing_not_started",
        ),
        (
            IntelligenceProcessingStatus.AWAITING_CANDIDATE_SPEAKER,
            "interview_candidate_speaker_required",
        ),
        (
            IntelligenceProcessingStatus.READY,
            "interview_processing_already_completed",
        ),
        (
            IntelligenceProcessingStatus.FAILED,
            "interview_processing_retry_required",
        ),
    ],
)
@pytest.mark.asyncio
async def test_admin_requeue_rejects_nonrecoverable_statuses(
    client: AsyncClient,
    seeded: SeededData,
    processing_status: IntelligenceProcessingStatus,
    expected_code: str,
) -> None:
    interviews = await seed_operations_data(seeded, datetime.now(UTC))
    if processing_status in interviews:
        interview_id = interviews[processing_status].id
    else:
        interview_id = interviews[IntelligenceProcessingStatus.UPLOADED].id
        async with TestSession() as session:
            interview = await session.get(IntelligenceInterview, interview_id)
            assert interview is not None
            interview.processing_status = processing_status
            await session.commit()

    response = await client.post(
        f"/api/v1/admin/interviews/ai-operations/{interview_id}/requeue",
        headers=auth(seeded.admin_id),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == expected_code


@pytest.mark.asyncio
async def test_ai_operations_is_admin_only(
    client: AsyncClient,
    seeded: SeededData,
) -> None:
    for user_id in (seeded.student_id, seeded.mentor_id):
        response = await client.get(
            "/api/v1/admin/interviews/ai-operations",
            headers=auth(user_id),
        )
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_ai_operations_survives_unavailable_redis(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unavailable_redis_metrics() -> (
        intelligence_operations_service.IntelligenceRedisMetrics
    ):
        return intelligence_operations_service.IntelligenceRedisMetrics(
            queues=IntelligenceOperationsQueueRead(available=False),
            workers=IntelligenceOperationsWorkersRead(),
        )

    monkeypatch.setattr(
        intelligence_operations_service,
        "intelligence_redis_metrics",
        unavailable_redis_metrics,
    )
    response = await client.get(
        "/api/v1/admin/interviews/ai-operations",
        headers=auth(seeded.admin_id),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 0
    assert body["active"] == 0
    assert body["oldest_active_at"] is None
    assert body["oldest_active_age_seconds"] is None
    assert body["failure_codes_24h"] == []
    assert body["queues"] == {
        "available": False,
        "transcription_depth": None,
        "openai_depth": None,
    }
    assert body["workers"] == {
        "transcription": {
            "status": "unknown",
            "heartbeat": None,
            "heartbeat_ttl_seconds": None,
        },
        "openai": {
            "status": "unknown",
            "heartbeat": None,
            "heartbeat_ttl_seconds": None,
        },
    }


@pytest.mark.asyncio
async def test_queue_metrics_reads_both_arq_queues_and_closes_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(intelligence_operations_service, "Redis", FakeRedis)

    metrics = await intelligence_operations_service.intelligence_redis_metrics()

    assert metrics.queues == IntelligenceOperationsQueueRead(
        available=True,
        transcription_depth=7,
        openai_depth=3,
    )
    assert metrics.workers.transcription.status == "healthy"
    assert metrics.workers.transcription.heartbeat_ttl_seconds == 30
    assert metrics.workers.openai.status == "healthy"
    assert metrics.workers.openai.heartbeat_ttl_seconds == 15
    assert FakeRedis.instance.redis_pipeline.commands == [
        ("zcard", intelligence_operations_service.TRANSCRIPTION_QUEUE_NAME),
        ("zcard", intelligence_operations_service.OPENAI_QUEUE_NAME),
        ("get", intelligence_operations_service.TRANSCRIPTION_HEALTH_CHECK_KEY),
        ("pttl", intelligence_operations_service.TRANSCRIPTION_HEALTH_CHECK_KEY),
        ("get", intelligence_operations_service.OPENAI_HEALTH_CHECK_KEY),
        ("pttl", intelligence_operations_service.OPENAI_HEALTH_CHECK_KEY),
    ]
    assert FakeRedis.instance.closed is True


@pytest.mark.asyncio
async def test_queue_metrics_suppresses_redis_and_cleanup_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenRedis(FakeRedis):
        pipeline_error = ConnectionError("Redis is unavailable")
        close_error = ConnectionError("Redis close failed")

    monkeypatch.setattr(intelligence_operations_service, "Redis", BrokenRedis)

    metrics = await intelligence_operations_service.intelligence_redis_metrics()

    assert metrics.queues == IntelligenceOperationsQueueRead(available=False)
    assert metrics.workers == IntelligenceOperationsWorkersRead()
    assert BrokenRedis.instance.closed is True


@pytest.mark.asyncio
async def test_queue_metrics_marks_missing_worker_heartbeats_unhealthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MissingHeartbeatPipeline(FakeRedisPipeline):
        async def execute(self) -> list[int | None]:
            return [0, 0, None, -2, None, -2]

    class MissingHeartbeatRedis(FakeRedis):
        def __init__(self) -> None:
            self.redis_pipeline = MissingHeartbeatPipeline()
            self.closed = False
            type(self).instance = self

    monkeypatch.setattr(
        intelligence_operations_service,
        "Redis",
        MissingHeartbeatRedis,
    )

    metrics = await intelligence_operations_service.intelligence_redis_metrics()

    assert metrics.queues.available is True
    assert metrics.workers.transcription.status == "unhealthy"
    assert metrics.workers.openai.status == "unhealthy"
