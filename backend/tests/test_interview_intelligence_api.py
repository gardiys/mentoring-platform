import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from arq import Retry
from httpx import AsyncClient
from sqlalchemy import event, func, select

from app.interviews import (
    intelligence_jobs,
    intelligence_router,
    intelligence_service,
    journal_router,
)
from app.interviews.intelligence_ai import FakeInterviewAIProvider, InterviewAIError
from app.interviews.intelligence_models import (
    IntelligenceAIAdmission,
    IntelligenceAIUsage,
    IntelligenceAnswer,
    IntelligenceAnswerReview,
    IntelligenceAssessment,
    IntelligenceAttemptStage,
    IntelligenceAttemptStatus,
    IntelligenceDifficulty,
    IntelligenceInterview,
    IntelligenceProcessingAttempt,
    IntelligenceProcessingStatus,
    IntelligenceQuestion,
    IntelligenceQuestionKind,
    IntelligenceReviewSource,
    IntelligenceReviewStatus,
    IntelligenceSpeaker,
    IntelligenceSpeakerRole,
    IntelligenceUtterance,
)
from app.interviews.intelligence_providers import (
    FakeTranscriptionProvider,
    TranscriptionJob,
    TranscriptionJobState,
)
from app.interviews.intelligence_service import select_candidate_speaker
from app.interviews.media_guardrails import MediaProbe, MediaStreamProbe, StagingGuard
from app.interviews.models import (
    InterviewCard,
    InterviewCardFrequency,
    InterviewCardOccurrence,
    InterviewCardProgress,
    InterviewDeck,
    InterviewProcessStage,
    InterviewTopicSelection,
)
from app.interviews.uploads import InterviewStorageReadError, StoredUpload
from app.mentors.models import MentorTrackAssignment
from app.tracks.models import LearningTrack, LearningTrackEnrollment
from app.users.models import User, UserRole
from tests.conftest import SeededData, TestSession, auth, test_engine


class RecordingRedis:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple[object, ...]]] = []

    async def enqueue_job(self, name: str, *args: object, **kwargs: object) -> None:
        del kwargs
        self.jobs.append((name, args))


class StubUploadStore:
    def download_url(self, upload: object, *, inline: bool = False) -> str:
        del upload, inline
        return "https://storage.example/recording.mp3?signed=redacted"

    async def ensure_browser_playable(self, upload: StoredUpload) -> StoredUpload:
        return upload


class StagedUploadStore(StubUploadStore):
    def __init__(self, actual_size: int = 1_024) -> None:
        self.actual_size = actual_size
        self.download_called = False

    async def resolve_upload_size(self, upload: StoredUpload) -> StoredUpload:
        return StoredUpload(
            storage_key=upload.storage_key,
            filename=upload.filename,
            content_type=upload.content_type,
            size=self.actual_size,
        )

    async def download_to_path(self, upload: object, destination: Path) -> None:
        del upload
        self.download_called = True
        destination.write_bytes(b"x" * self.actual_size)


class UnavailableMetadataUploadStore(StagedUploadStore):
    async def resolve_upload_size(self, upload: StoredUpload) -> StoredUpload:
        del upload
        raise InterviewStorageReadError("S3 HEAD failed")


class FileUploadTranscriptionProvider(FakeTranscriptionProvider):
    requires_file_upload = True

    def __init__(self) -> None:
        self.submitted_path: Path | None = None

    async def submit(self, **kwargs: Any) -> TranscriptionJob:
        file_path = kwargs.get("file_path")
        assert isinstance(file_path, Path)
        assert file_path.exists()
        self.submitted_path = file_path
        return TranscriptionJob(
            provider_job_id="guarded-media",
            status=TranscriptionJobState.QUEUED,
        )


async def create_analysis_from_journal(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
    *,
    company_name: str = "Nexara",
    owner_id: UUID | None = None,
    track_id: UUID | None = None,
    media_size: int | None = 1_024,
    media_storage_key: str = "interview-media/student/recording",
) -> tuple[Any, UUID, UUID]:
    async def fake_enqueue(_: UUID) -> None:
        return None

    monkeypatch.setattr(journal_router, "_enqueue_ai_analysis", fake_enqueue)
    selected_owner_id = owner_id or seeded.student_id
    selected_track_id = track_id or seeded.python_track_id
    process_response = await client.post(
        "/api/v1/interviews/journal/tracks",
        headers=auth(selected_owner_id),
        json={"company_name": company_name, "track_id": str(selected_track_id)},
    )
    assert process_response.status_code == 201, process_response.text
    process_id = UUID(process_response.json()["id"])
    stage_response = await client.post(
        f"/api/v1/interviews/journal/tracks/{process_id}/stages",
        headers=auth(selected_owner_id),
        json={
            "stage_type": "technical_interview",
            "scheduled_at": "2026-08-02T10:00:00Z",
        },
    )
    assert stage_response.status_code == 200, stage_response.text
    stage_id = UUID(stage_response.json()["stages"][0]["id"])
    async with TestSession() as session:
        stage = await session.get(InterviewProcessStage, stage_id)
        assert stage is not None
        stage.media_storage_key = media_storage_key
        stage.media_filename = "recording.mp3"
        stage.media_content_type = "audio/mpeg"
        stage.media_size = media_size
        await session.commit()
    created = await client.post(
        f"/api/v1/interviews/journal/tracks/{process_id}/stages/{stage_id}/ai-analysis",
        headers=auth(selected_owner_id),
    )
    return created, process_id, stage_id


async def mark_analysis_finished(interview_id: UUID) -> None:
    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, interview_id)
        assert interview is not None
        interview.processing_status = IntelligenceProcessingStatus.READY
        await session.commit()


@pytest.mark.asyncio
async def test_student_creates_and_roles_only_see_authorized_interview(
    client: AsyncClient, seeded: SeededData, monkeypatch: pytest.MonkeyPatch
) -> None:
    response, process_id, stage_id = await create_analysis_from_journal(
        client, seeded, monkeypatch, company_name="ООО Nexara"
    )
    assert response.status_code == 201, response.text
    interview_id = response.json()["id"]
    assert response.json()["company_name"] == "Nexara"
    assert response.json()["processing_status"] == "uploaded"

    own = await client.get(f"/api/v1/interviews/{interview_id}", headers=auth(seeded.student_id))
    assert own.status_code == 200

    assigned_mentor = await client.get(
        f"/api/v1/mentor/interviews/{interview_id}", headers=auth(seeded.mentor_id)
    )
    assert assigned_mentor.status_code == 200

    unrelated_mentor = await client.get(
        f"/api/v1/mentor/interviews/{interview_id}",
        headers=auth(seeded.other_mentor_id),
    )
    assert unrelated_mentor.status_code == 404

    admin = await client.get(f"/api/v1/interviews/{interview_id}", headers=auth(seeded.admin_id))
    assert admin.status_code == 200
    duplicate = await client.post(
        f"/api/v1/interviews/journal/tracks/{process_id}/stages/{stage_id}/ai-analysis",
        headers=auth(seeded.student_id),
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "interview_ai_analysis_already_requested"


@pytest.mark.asyncio
async def test_mentor_cannot_access_assigned_student_analysis_outside_mentor_direction(
    client: AsyncClient, seeded: SeededData, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with TestSession() as session:
        session.add(
            LearningTrackEnrollment(
                user_id=seeded.student_id,
                track_id=seeded.go_track_id,
            )
        )
        await session.commit()

    created, _, _ = await create_analysis_from_journal(
        client,
        seeded,
        monkeypatch,
        track_id=seeded.go_track_id,
    )
    assert created.status_code == 201, created.text
    interview_id = created.json()["id"]

    forbidden_detail = await client.get(
        f"/api/v1/mentor/interviews/{interview_id}",
        headers=auth(seeded.mentor_id),
    )
    mentor_queue = await client.get(
        "/api/v1/mentor/interviews?status=all",
        headers=auth(seeded.mentor_id),
    )
    go_mentor_detail = await client.get(
        f"/api/v1/mentor/interviews/{interview_id}",
        headers=auth(seeded.other_mentor_id),
    )

    assert forbidden_detail.status_code == 404
    assert mentor_queue.status_code == 200
    assert interview_id not in {item["id"] for item in mentor_queue.json()["items"]}
    # Direction access alone is insufficient: the Go mentor is not assigned to
    # this student.
    assert go_mentor_detail.status_code == 404

    # An obsolete assignment to an unpublished direction must not reopen the
    # analysis to the mentor.
    async with TestSession() as session:
        session.add(
            MentorTrackAssignment(
                mentor_id=seeded.mentor_id,
                track_id=seeded.go_track_id,
            )
        )
        go_track = await session.get(LearningTrack, seeded.go_track_id)
        assert go_track is not None
        go_track.is_published = False
        await session.commit()
    unpublished = await client.get(
        f"/api/v1/mentor/interviews/{interview_id}",
        headers=auth(seeded.mentor_id),
    )
    assert unpublished.status_code == 404


@pytest.mark.asyncio
async def test_processing_poll_is_authorized_lightweight_and_returns_progress(
    client: AsyncClient, seeded: SeededData, monkeypatch: pytest.MonkeyPatch
) -> None:
    created, _, _ = await create_analysis_from_journal(client, seeded, monkeypatch)
    interview_id = UUID(created.json()["id"])
    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, interview_id)
        assert interview is not None
        speaker = IntelligenceSpeaker(
            interview_id=interview.id,
            provider_speaker_key="candidate",
            role=IntelligenceSpeakerRole.CANDIDATE,
        )
        session.add(speaker)
        await session.flush()
        utterance = IntelligenceUtterance(
            interview_id=interview.id,
            speaker_id=speaker.id,
            sequence_number=0,
            start_ms=0,
            end_ms=1_000,
            text="A transcript body that the poll endpoint must not load",
        )
        session.add(utterance)
        await session.flush()
        question = IntelligenceQuestion(
            interview_id=interview.id,
            sequence_number=0,
            question_text="A question body that the poll endpoint must not load",
            question_start_ms=0,
            question_end_ms=500,
            answer_start_ms=500,
            answer_end_ms=1_000,
            question_utterance_ids=[utterance.id],
            answer_utterance_ids=[utterance.id],
            category="Python",
            question_kind=IntelligenceQuestionKind.TECHNICAL,
            difficulty=IntelligenceDifficulty.MIDDLE,
            confidence=0.95,
        )
        session.add(question)
        await session.flush()
        answer = IntelligenceAnswer(
            question_id=question.id,
            student_id=seeded.student_id,
            answer_text="An answer body that the poll endpoint must not load",
        )
        session.add(answer)
        await session.flush()
        session.add_all(
            [
                IntelligenceAnswerReview(
                    answer_id=answer.id,
                    source=IntelligenceReviewSource.AI,
                    status=IntelligenceReviewStatus.SUGGESTED,
                    assessment=IntelligenceAssessment.CORRECT,
                    summary="A review body that the poll endpoint must not load",
                ),
                IntelligenceProcessingAttempt(
                    interview_id=interview.id,
                    stage=IntelligenceAttemptStage.AI_EXTRACT,
                    status=IntelligenceAttemptStatus.COMPLETED,
                    attempt_number=1,
                    provider="fake",
                ),
            ]
        )
        interview.candidate_speaker_id = speaker.id
        interview.processing_status = IntelligenceProcessingStatus.ANALYZING
        await session.commit()

    statements: list[str] = []

    def record_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        statements.append(statement.lower())

    event.listen(test_engine.sync_engine, "before_cursor_execute", record_statement)
    try:
        response = await client.get(
            f"/api/v1/interviews/{interview_id}/processing",
            headers=auth(seeded.student_id),
        )
    finally:
        event.remove(test_engine.sync_engine, "before_cursor_execute", record_statement)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "status": "analyzing",
        "failed_stage": None,
        "error_code": None,
        "error_message": None,
        "transcribed": True,
        "candidate_selected": True,
        "questions_found": 1,
        "reviews_completed": 1,
        "attempts": [
            {
                "id": response.json()["attempts"][0]["id"],
                "stage": "ai_extract",
                "status": "completed",
                "attempt_number": 1,
                "provider": "fake",
                "error_code": None,
                "error_message": None,
                "started_at": response.json()["attempts"][0]["started_at"],
                "finished_at": None,
            }
        ],
    }
    # Authentication plus two service queries: access, then counters/attempts.
    assert len(statements) <= 3
    assert not any("intelligence_utterances.text" in statement for statement in statements)
    assert not any("intelligence_questions.question_text" in statement for statement in statements)
    assert not any("intelligence_answers.answer_text" in statement for statement in statements)

    unrelated = await client.get(
        f"/api/v1/interviews/{interview_id}/processing",
        headers=auth(seeded.other_mentor_id),
    )
    admin = await client.get(
        f"/api/v1/interviews/{interview_id}/processing",
        headers=auth(seeded.admin_id),
    )
    assert unrelated.status_code == 404
    assert admin.status_code == 200


@pytest.mark.asyncio
async def test_student_and_mentor_are_limited_to_one_ai_analysis_launch_per_day(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for owner_id, prefix in (
        (seeded.student_id, "Student quota"),
        (seeded.mentor_id, "Mentor quota"),
    ):
        created_ids: list[UUID] = []
        for sequence in range(1):
            created, _, _ = await create_analysis_from_journal(
                client,
                seeded,
                monkeypatch,
                company_name=f"{prefix} {sequence}",
                owner_id=owner_id,
            )
            assert created.status_code == 201, created.text
            interview_id = UUID(created.json()["id"])
            created_ids.append(interview_id)
            await mark_analysis_finished(interview_id)

        limited, _, limited_stage_id = await create_analysis_from_journal(
            client,
            seeded,
            monkeypatch,
            company_name=f"{prefix} limited",
            owner_id=owner_id,
        )

        assert limited.status_code == 429
        assert limited.json()["detail"]["code"] == "interview_ai_daily_limit_reached"
        async with TestSession() as session:
            stage = await session.get(InterviewProcessStage, limited_stage_id)
            assert stage is not None
            assert stage.ai_analysis_requested_at is None
            persisted = int(
                await session.scalar(
                    select(func.count(IntelligenceInterview.id)).where(
                        IntelligenceInterview.student_id == owner_id
                    )
                )
                or 0
            )
            assert persisted == len(created_ids)


@pytest.mark.asyncio
async def test_manual_retry_consumes_the_requesters_daily_ai_quota(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(intelligence_service.settings, "interview_ai_daily_limit", 2)
    created, _, _ = await create_analysis_from_journal(
        client, seeded, monkeypatch, company_name="Retry quota"
    )
    interview_id = UUID(created.json()["id"])

    async def fake_enqueue(_function: str, _interview_id: UUID) -> None:
        return None

    monkeypatch.setattr(intelligence_router, "_enqueue", fake_enqueue)
    for attempt in range(2):
        async with TestSession() as session:
            interview = await session.get(IntelligenceInterview, interview_id)
            assert interview is not None
            interview.processing_status = IntelligenceProcessingStatus.FAILED
            interview.failed_stage = IntelligenceAttemptStage.AI_EXTRACT
            interview.processing_error_code = "OPENAI_RATE_LIMIT"
            await session.commit()

        response = await client.post(
            f"/api/v1/interviews/{interview_id}/retry",
            headers=auth(seeded.student_id),
        )
        if attempt == 0:
            assert response.status_code == 200, response.text
        else:
            assert response.status_code == 429
            assert response.json()["detail"]["code"] == "interview_ai_daily_limit_reached"

    async with TestSession() as session:
        admissions = int(
            await session.scalar(
                select(func.count(IntelligenceAIAdmission.id)).where(
                    IntelligenceAIAdmission.requester_user_id == seeded.student_id
                )
            )
            or 0
        )
    assert admissions == 2


@pytest.mark.asyncio
async def test_mentor_overview_generation_is_quotad_and_cannot_replace_a_summary(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(intelligence_service.settings, "interview_ai_daily_limit", 1)
    created, _, _ = await create_analysis_from_journal(
        client, seeded, monkeypatch, company_name="Overview quota"
    )
    interview_id = UUID(created.json()["id"])
    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, interview_id)
        assert interview is not None
        speaker = IntelligenceSpeaker(
            interview_id=interview.id,
            provider_speaker_key="candidate",
            role=IntelligenceSpeakerRole.CANDIDATE,
        )
        session.add(speaker)
        await session.flush()
        session.add(
            IntelligenceUtterance(
                interview_id=interview.id,
                speaker_id=speaker.id,
                sequence_number=1,
                start_ms=0,
                end_ms=1_000,
                text="Candidate answer",
            )
        )
        interview.candidate_speaker_id = speaker.id
        interview.processing_status = IntelligenceProcessingStatus.READY
        await session.commit()

    async def fake_enqueue(_function: str, _interview_id: UUID) -> None:
        return None

    monkeypatch.setattr(intelligence_router, "_enqueue", fake_enqueue)
    first = await client.post(
        f"/api/v1/mentor/interviews/{interview_id}/generate-overview",
        headers=auth(seeded.mentor_id),
    )
    assert first.status_code == 200, first.text

    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, interview_id)
        assert interview is not None
        interview.processing_status = IntelligenceProcessingStatus.READY
        await session.commit()
    limited = await client.post(
        f"/api/v1/mentor/interviews/{interview_id}/generate-overview",
        headers=auth(seeded.mentor_id),
    )
    assert limited.status_code == 429
    assert limited.json()["detail"]["code"] == "interview_ai_daily_limit_reached"

    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, interview_id)
        assert interview is not None
        interview.ai_summary_payload = {"overall_summary": "Already generated"}
        await session.commit()
    duplicate = await client.post(
        f"/api/v1/mentor/interviews/{interview_id}/generate-overview",
        headers=auth(seeded.mentor_id),
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "intelligence_summary_already_exists"


@pytest.mark.asyncio
async def test_admin_ai_analysis_launches_do_not_have_a_personal_quota(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for sequence in range(5):
        created, _, _ = await create_analysis_from_journal(
            client,
            seeded,
            monkeypatch,
            company_name=f"Admin unlimited {sequence}",
            owner_id=seeded.admin_id,
        )
        assert created.status_code == 201, created.text


@pytest.mark.asyncio
async def test_user_can_only_have_one_active_ai_analysis(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, _, _ = await create_analysis_from_journal(
        client, seeded, monkeypatch, company_name="Active analysis"
    )
    second, _, _ = await create_analysis_from_journal(
        client, seeded, monkeypatch, company_name="Second active analysis"
    )

    assert first.status_code == 201
    assert second.status_code == 429
    assert second.json()["detail"]["code"] == "interview_ai_active_limit_reached"


@pytest.mark.asyncio
async def test_waiting_for_speaker_blocks_only_its_owner_not_global_worker_capacity(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(intelligence_service.settings, "interview_ai_global_active_limit", 1)
    first, _, _ = await create_analysis_from_journal(
        client, seeded, monkeypatch, company_name="Waiting for speaker"
    )
    interview_id = UUID(first.json()["id"])
    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, interview_id)
        assert interview is not None
        interview.processing_status = IntelligenceProcessingStatus.AWAITING_CANDIDATE_SPEAKER
        await session.commit()

    same_owner, _, _ = await create_analysis_from_journal(
        client, seeded, monkeypatch, company_name="Same owner still blocked"
    )
    other_owner, _, _ = await create_analysis_from_journal(
        client,
        seeded,
        monkeypatch,
        company_name="Worker capacity remains free",
        owner_id=seeded.mentor_id,
    )

    assert same_owner.status_code == 429
    assert same_owner.json()["detail"]["code"] == "interview_ai_active_limit_reached"
    assert other_owner.status_code == 201, other_owner.text


@pytest.mark.asyncio
async def test_daily_ai_quota_is_atomic_for_simultaneous_requests(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_enqueue(_: UUID) -> None:
        return None

    monkeypatch.setattr(journal_router, "_enqueue_ai_analysis", fake_enqueue)
    monkeypatch.setattr(
        intelligence_service.settings,
        "interview_ai_max_active_per_user",
        10,
    )
    prepared: list[tuple[UUID, UUID]] = []
    for sequence in range(4):
        process_response = await client.post(
            "/api/v1/interviews/journal/tracks",
            headers=auth(seeded.student_id),
            json={
                "company_name": f"Concurrent quota {sequence}",
                "track_id": str(seeded.python_track_id),
            },
        )
        process_id = UUID(process_response.json()["id"])
        stage_response = await client.post(
            f"/api/v1/interviews/journal/tracks/{process_id}/stages",
            headers=auth(seeded.student_id),
            json={
                "stage_type": "technical_interview",
                "scheduled_at": "2026-08-02T10:00:00Z",
            },
        )
        stage_id = UUID(stage_response.json()["stages"][0]["id"])
        async with TestSession() as session:
            stage = await session.get(InterviewProcessStage, stage_id)
            assert stage is not None
            stage.media_storage_key = f"interview-media/student/{sequence}"
            stage.media_filename = f"recording-{sequence}.mp3"
            stage.media_content_type = "audio/mpeg"
            stage.media_size = 1_024
            await session.commit()
        prepared.append((process_id, stage_id))

    responses = await asyncio.gather(
        *(
            client.post(
                f"/api/v1/interviews/journal/tracks/{process_id}/stages/{stage_id}/ai-analysis",
                headers=auth(seeded.student_id),
            )
            for process_id, stage_id in prepared
        )
    )

    assert sorted(response.status_code for response in responses) == [201, 429, 429, 429]
    rejected = next(response for response in responses if response.status_code == 429)
    assert rejected.json()["detail"]["code"] == "interview_ai_daily_limit_reached"


@pytest.mark.asyncio
async def test_previous_quota_day_does_not_count_towards_today(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for sequence in range(3):
        created, _, stage_id = await create_analysis_from_journal(
            client,
            seeded,
            monkeypatch,
            company_name=f"Previous day {sequence}",
        )
        assert created.status_code == 201
        await mark_analysis_finished(UUID(created.json()["id"]))
        async with TestSession() as session:
            stage = await session.get(InterviewProcessStage, stage_id)
            assert stage is not None
            stage.ai_analysis_requested_at = datetime.now(UTC) - timedelta(days=1)
            admission = await session.scalar(
                select(IntelligenceAIAdmission).where(
                    IntelligenceAIAdmission.interview_id == UUID(created.json()["id"])
                )
            )
            assert admission is not None
            admission.requested_at = datetime.now(UTC) - timedelta(days=1)
            await session.commit()

    today, _, _ = await create_analysis_from_journal(
        client,
        seeded,
        monkeypatch,
        company_name="Today is available",
    )
    assert today.status_code == 201, today.text


@pytest.mark.asyncio
async def test_ai_kill_switch_blocks_all_roles(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(intelligence_service.settings, "interview_ai_enabled", False)

    blocked, _, _ = await create_analysis_from_journal(
        client,
        seeded,
        monkeypatch,
        company_name="Disabled AI",
        owner_id=seeded.admin_id,
    )

    assert blocked.status_code == 503
    assert blocked.json()["detail"]["code"] == "interview_ai_analysis_disabled"


@pytest.mark.asyncio
async def test_student_cannot_open_another_students_interview(
    client: AsyncClient, seeded: SeededData, monkeypatch: pytest.MonkeyPatch
) -> None:
    created, _, _ = await create_analysis_from_journal(
        client, seeded, monkeypatch, company_name="Yandex"
    )
    interview_id = created.json()["id"]

    other_student_id = uuid4()
    async with TestSession() as session:
        session.add(User(id=other_student_id, first_name="Другой", role=UserRole.STUDENT))
        await session.flush()
        session.add(
            LearningTrackEnrollment(
                user_id=other_student_id,
                track_id=seeded.python_track_id,
            )
        )
        await session.commit()

    response = await client.get(
        f"/api/v1/interviews/{interview_id}", headers=auth(other_student_id)
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_standalone_intelligence_upload_endpoint_is_disabled(
    client: AsyncClient, seeded: SeededData
) -> None:
    response = await client.post(
        "/api/v1/interviews",
        headers=auth(seeded.mentor_id),
        json={
            "company_name": "Ozon",
            "track_id": str(seeded.python_track_id),
            "interview_type": "technical",
            "interviewed_at": "2026-08-02T10:00:00Z",
        },
    )

    assert response.status_code == 405


@pytest.mark.asyncio
async def test_fake_processing_pipeline_reaches_ready(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created, _, _ = await create_analysis_from_journal(client, seeded, monkeypatch)
    interview_id = UUID(created.json()["id"])

    monkeypatch.setattr(intelligence_jobs, "async_session_factory", TestSession)
    queue = RecordingRedis()
    fake_ai = FakeInterviewAIProvider()
    context: dict[str, Any] = {
        "redis": queue,
        "transcription_provider": FakeTranscriptionProvider(),
        "ai_provider": fake_ai,
        "upload_store": StubUploadStore(),
    }

    await intelligence_jobs.submit_transcription(context, str(interview_id))
    await intelligence_jobs.poll_transcription(context, str(interview_id))
    await intelligence_jobs.process_transcription_result(context, str(interview_id))

    async with TestSession() as session:
        candidate = await session.scalar(
            select(IntelligenceSpeaker).where(
                IntelligenceSpeaker.interview_id == interview_id,
                IntelligenceSpeaker.provider_speaker_key == "B",
            )
        )
        student = await session.get(User, seeded.student_id)
        assert candidate is not None and student is not None
        await select_candidate_speaker(session, student, interview_id, candidate.id)

    duplicate_candidate = await client.put(
        f"/api/v1/interviews/{interview_id}/candidate-speaker",
        headers=auth(seeded.student_id),
        json={"speaker_id": str(candidate.id)},
    )
    assert duplicate_candidate.status_code == 409
    assert (
        duplicate_candidate.json()["detail"]["code"] == "candidate_speaker_selection_not_available"
    )

    await intelligence_jobs.extract_interview_structure(context, str(interview_id))
    assert (
        "refresh_interview_question_embeddings",
        (str(interview_id),),
    ) in queue.jobs
    assert ("generate_answer_reviews", (str(interview_id),)) in queue.jobs
    await intelligence_jobs.refresh_interview_question_embeddings(context, str(interview_id))
    # Duplicate delivery is a no-op: current vectors are reused and usage is
    # not counted twice.
    await intelligence_jobs.refresh_interview_question_embeddings(context, str(interview_id))
    await intelligence_jobs.generate_answer_reviews(context, str(interview_id))

    response = await client.get(
        f"/api/v1/interviews/{interview_id}", headers=auth(seeded.student_id)
    )
    assert response.status_code == 200
    detail = response.json()
    assert detail["processing_status"] == "ready"
    assert len(detail["transcript"]) == 4
    assert len(detail["questions"]) == 2
    assert [question["question_kind"] for question in detail["questions"]] == [
        "technical",
        "hr",
    ]
    assert detail["questions"][0]["answer"]["reviews"][0]["source"] == "ai"
    assert detail["overview"]["overall_summary"]
    assert detail["overview"]["communication_score"] == 0.78
    assert detail["overview"]["communication_dimensions"][0]["name"] == "clarity"
    assert [call["question_kind"] for call in fake_ai.review_calls] == [
        IntelligenceQuestionKind.TECHNICAL,
        IntelligenceQuestionKind.HR,
    ]
    assert "U003" in str(fake_ai.review_calls[0]["context"])
    assert fake_ai.review_calls[1]["context"] == ""
    async with TestSession() as session:
        operations = list(
            await session.scalars(
                select(IntelligenceAIUsage.operation)
                .where(IntelligenceAIUsage.interview_id == interview_id)
                .order_by(IntelligenceAIUsage.operation)
            )
        )
        extracted_questions = list(
            await session.scalars(
                select(IntelligenceQuestion)
                .where(IntelligenceQuestion.interview_id == interview_id)
                .order_by(IntelligenceQuestion.sequence_number)
            )
        )
    assert "embedding" in operations
    assert operations.count("embedding") == 1
    assert "technical_evaluation" in operations
    assert "light_evaluation" in operations
    assert all(question.question_embedding for question in extracted_questions)
    assert all(
        question.question_embedding_model == fake_ai.embedding_model
        for question in extracted_questions
    )
    journal = await client.get(
        f"/api/v1/interviews/journal/tracks/{detail['process_id']}",
        headers=auth(seeded.student_id),
    )
    ai_comments = [
        comment
        for stage in journal.json()["stages"]
        for comment in stage["comments"]
        if comment["is_ai_feedback"]
    ]
    assert len(ai_comments) == 1
    assert ai_comments[0]["author"] is None

    async with TestSession() as session:
        empty_deck = InterviewDeck(
            track_id=seeded.python_track_id,
            slug="python-ai-moderation-empty",
            title="Общие вопросы",
            position=0,
            is_published=True,
        )
        deck = InterviewDeck(
            track_id=seeded.python_track_id,
            slug="python-ai-moderation",
            title="Python",
            position=1,
            is_published=True,
        )
        session.add_all([empty_deck, deck])
        existing_card = InterviewCard(
            deck=deck,
            slug="existing-gil-question",
            category="python",
            companies="Ozon",
            question_markdown="## Как работает GIL в Python?",
            answer_markdown="Проверенный существующий ответ",
            frequency="frequent",
            position=0,
            is_published=True,
            asked_count=4,
        )
        session.add(existing_card)
        missed_question_id = UUID(detail["questions"][-1]["id"])
        missed_answer = await session.scalar(
            select(IntelligenceAnswer).where(IntelligenceAnswer.question_id == missed_question_id)
        )
        assert missed_answer is not None
        missed_answer.answer_text = ""
        await session.commit()
        empty_deck_id = empty_deck.id
        deck_id = deck.id
        existing_card_id = existing_card.id

    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, interview_id)
        assert interview is not None
        interview.ai_summary_payload = None
        interview.ai_summary_model = None
        interview.ai_summary_prompt_version = None
        await session.commit()

    enqueued: list[tuple[str, UUID]] = []

    async def fake_enqueue(function: str, queued_interview_id: UUID) -> None:
        enqueued.append((function, queued_interview_id))

    monkeypatch.setattr(intelligence_router, "_enqueue", fake_enqueue)
    requested_summary = await client.post(
        f"/api/v1/mentor/interviews/{interview_id}/generate-overview",
        headers=auth(seeded.admin_id),
    )
    assert requested_summary.status_code == 200, requested_summary.text
    assert requested_summary.json()["processing_status"] == "analyzing"
    assert enqueued == [("generate_answer_reviews", interview_id)]

    await intelligence_jobs.generate_answer_reviews(context, str(interview_id))
    refreshed = await client.get(
        f"/api/v1/interviews/{interview_id}", headers=auth(seeded.student_id)
    )
    detail = refreshed.json()
    assert detail["processing_status"] == "ready"
    assert detail["overview"]["overall_summary"]

    first_question_id = detail["questions"][0]["id"]
    forbidden_moderation = await client.post(
        f"/api/v1/mentor/interviews/{interview_id}/questions/{first_question_id}/moderation",
        headers=auth(seeded.student_id),
        json={"action": "recommend"},
    )
    assert forbidden_moderation.status_code == 403
    recommended = await client.post(
        f"/api/v1/mentor/interviews/{interview_id}/questions/{first_question_id}/moderation",
        headers=auth(seeded.mentor_id),
        json={"action": "recommend"},
    )
    assert recommended.status_code == 200, recommended.text
    assert recommended.json()["questions"][0]["moderation_status"] == "mentor_approved"

    queue = await client.get(
        "/api/v1/admin/interviews/question-moderation?status=needs_review",
        headers=auth(seeded.admin_id),
    )
    assert queue.status_code == 200, queue.text
    assert {item["question_id"] for item in queue.json()["items"]} == {
        question["id"] for question in detail["questions"]
    }
    queue_detail = await client.get(
        f"/api/v1/admin/interviews/question-moderation/{first_question_id}",
        headers=auth(seeded.admin_id),
    )
    assert queue_detail.status_code == 200, queue_detail.text
    moderation_detail = queue_detail.json()
    assert moderation_detail["matched_card_id"] == str(existing_card_id)
    assert moderation_detail["matched_card_deck_id"] == str(deck_id)
    assert moderation_detail["matched_card_category"] == "python"
    assert moderation_detail["matched_card_asked_count"] == 4
    assert moderation_detail["deck_options"] == [
        {
            "id": str(empty_deck_id),
            "title": "Общие вопросы",
            "categories": [],
        },
        {"id": str(deck_id), "title": "Python", "categories": ["python"]},
    ]

    ai_reviews = [
        question["answer"]["reviews"][0]
        for question in detail["questions"]
        if question["answer"]["reviews"]
    ]
    edited = await client.patch(
        f"/api/v1/mentor/interviews/{interview_id}/reviews/{ai_reviews[0]['id']}",
        headers=auth(seeded.admin_id),
        json={
            "assessment": "correct",
            "score": 0.9,
            "summary": "Уточнённая оценка администратора",
            "strengths": [],
            "problems": [],
            "missing_points": [],
            "incorrect_statements": [],
            "suggested_better_answer": None,
        },
    )
    assert edited.status_code == 200, edited.text
    for review in ai_reviews[1:]:
        approved = await client.post(
            f"/api/v1/mentor/interviews/{interview_id}/reviews/{review['id']}/approve",
            headers=auth(seeded.admin_id),
        )
        assert approved.status_code == 200, approved.text

    completed = await client.post(
        f"/api/v1/mentor/interviews/{interview_id}/complete-review",
        headers=auth(seeded.admin_id),
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["reviewed_at"] is not None

    new_question = detail["questions"][1]
    category_not_selected = await client.post(
        f"/api/v1/mentor/interviews/{interview_id}/questions/{new_question['id']}/moderation",
        headers=auth(seeded.admin_id),
        json={
            "action": "approve",
            "question_markdown": new_question["question_text"],
            "answer_markdown": "Проверенный ответ администратора",
            "deck_id": str(deck_id),
            "category": "Новая тема",
            "frequency": "occasional",
        },
    )
    assert category_not_selected.status_code == 422
    assert category_not_selected.json()["detail"]["code"] == "interview_card_category_not_found"
    category_collision = await client.post(
        f"/api/v1/mentor/interviews/{interview_id}/questions/{new_question['id']}/moderation",
        headers=auth(seeded.admin_id),
        json={
            "action": "approve",
            "question_markdown": new_question["question_text"],
            "answer_markdown": "Проверенный ответ администратора",
            "deck_id": str(deck_id),
            "category": "  PYTHON  ",
            "create_category": True,
            "frequency": "occasional",
        },
    )
    assert category_collision.status_code == 422
    assert category_collision.json()["detail"]["code"] == "interview_card_category_already_exists"

    for question in detail["questions"]:
        review = question["answer"]["reviews"][-1] if question["answer"] else None
        moderated = await client.post(
            f"/api/v1/mentor/interviews/{interview_id}/questions/{question['id']}/moderation",
            headers=auth(seeded.admin_id),
            json={
                "action": "approve",
                "question_markdown": question["question_text"],
                "answer_markdown": (
                    review["suggested_better_answer"]
                    if review and review["suggested_better_answer"]
                    else question["answer"]["answer_text"] or "Проверенный ответ администратора"
                ),
                "deck_id": str(deck_id),
                "category": (
                    question["category"]
                    if question["id"] == first_question_id
                    else "  Career   Growth  "
                ),
                "create_category": question["id"] != first_question_id,
                "frequency": "occasional",
            },
        )
        assert moderated.status_code == 200, moderated.text

    repeated = await client.post(
        f"/api/v1/mentor/interviews/{interview_id}/questions/{first_question_id}/moderation",
        headers=auth(seeded.admin_id),
        json={
            "action": "approve",
            "question_markdown": "Как работает GIL в Python?",
            "answer_markdown": "Проверенный существующий ответ",
            "category": "python",
            "frequency": "frequent",
        },
    )
    assert repeated.status_code == 200, repeated.text

    async with TestSession() as session:
        existing_card = await session.scalar(
            select(InterviewCard).where(InterviewCard.slug == "existing-gil-question")
        )
        assert existing_card is not None
        assert existing_card.asked_count == 5
        assert existing_card.companies is not None
        assert "Ozon" in existing_card.companies
        assert detail["company_name"] in existing_card.companies
        occurrences = list(
            await session.scalars(
                select(InterviewCardOccurrence).where(
                    InterviewCardOccurrence.card_id == existing_card.id
                )
            )
        )
        assert len(occurrences) == 1
        assert occurrences[0].company_name == detail["company_name"]
        missed_question = await session.get(IntelligenceQuestion, missed_question_id)
        assert missed_question is not None and missed_question.published_card_id is not None
        assert missed_question.category == "Career Growth"
        missed_card = await session.get(InterviewCard, missed_question.published_card_id)
        assert missed_card is not None
        assert missed_card.frequency_override is InterviewCardFrequency.OCCASIONAL
        progress = await session.get(
            InterviewCardProgress,
            {
                "user_id": seeded.student_id,
                "card_id": missed_question.published_card_id,
            },
        )
        selection = await session.get(
            InterviewTopicSelection,
            {
                "user_id": seeded.student_id,
                "deck_id": deck_id,
                "category": missed_question.category,
            },
        )
        assert progress is not None and progress.repetitions == 0
        assert selection is not None

    reviewed = await client.get(
        "/api/v1/mentor/interviews?status=reviewed", headers=auth(seeded.admin_id)
    )
    needs_review = await client.get(
        "/api/v1/mentor/interviews?status=needs_review", headers=auth(seeded.admin_id)
    )
    assert [item["id"] for item in reviewed.json()["items"]] == [str(interview_id)]
    assert str(interview_id) not in [item["id"] for item in needs_review.json()["items"]]


@pytest.mark.asyncio
async def test_question_embedding_job_retries_without_failing_interview(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created, _, _ = await create_analysis_from_journal(
        client,
        seeded,
        monkeypatch,
        company_name="Embedding retry",
    )
    interview_id = UUID(created.json()["id"])
    async with TestSession() as session:
        session.add(
            IntelligenceQuestion(
                interview_id=interview_id,
                sequence_number=1,
                question_text="Чем Kafka отличается от RabbitMQ?",
                question_start_ms=1_000,
                question_end_ms=2_000,
                answer_start_ms=None,
                answer_end_ms=None,
                question_utterance_ids=[],
                answer_utterance_ids=[],
                category="message brokers",
                question_kind=IntelligenceQuestionKind.TECHNICAL,
                difficulty=IntelligenceDifficulty.MIDDLE,
                confidence=0.95,
            )
        )
        await session.commit()

    monkeypatch.setattr(intelligence_jobs, "async_session_factory", TestSession)
    provider = FakeInterviewAIProvider()

    async def unavailable(_texts: list[str]) -> object:
        raise InterviewAIError(
            "OPENAI_RATE_LIMIT",
            "Embedding provider is temporarily unavailable",
            retryable=True,
        )

    monkeypatch.setattr(provider, "embed", unavailable)
    context: dict[str, Any] = {
        "ai_provider": provider,
        "job_try": 2,
        "job_id": f"embedding:{interview_id}",
    }

    with pytest.raises(Retry) as raised:
        await intelligence_jobs.refresh_interview_question_embeddings(context, str(interview_id))

    assert 60_000 <= raised.value.defer_score <= 120_000
    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, interview_id)
        question = await session.scalar(
            select(IntelligenceQuestion).where(IntelligenceQuestion.interview_id == interview_id)
        )
        usage_count = int(
            await session.scalar(
                select(func.count(IntelligenceAIUsage.id)).where(
                    IntelligenceAIUsage.interview_id == interview_id,
                    IntelligenceAIUsage.operation == "embedding",
                )
            )
            or 0
        )
    assert interview is not None
    assert interview.processing_status is IntelligenceProcessingStatus.UPLOADED
    assert interview.processing_error_code is None
    assert question is not None and question.question_embedding is None
    assert usage_count == 0

    context["job_try"] = intelligence_jobs.MAX_JOB_TRIES
    await intelligence_jobs.refresh_interview_question_embeddings(context, str(interview_id))


@pytest.mark.asyncio
async def test_file_upload_is_probed_and_staging_is_cleaned_before_transcription(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    created, _, _ = await create_analysis_from_journal(
        client, seeded, monkeypatch, company_name="Guarded media"
    )
    interview_id = UUID(created.json()["id"])
    provider = FileUploadTranscriptionProvider()

    async def fake_probe(*_args: object, **_kwargs: object) -> MediaProbe:
        return MediaProbe(
            format_names=("mp3",),
            duration_seconds=42,
            streams=(MediaStreamProbe(kind="audio", codec="mp3", duration_seconds=42),),
        )

    monkeypatch.setattr(intelligence_jobs, "async_session_factory", TestSession)
    monkeypatch.setattr(intelligence_jobs, "probe_media_async", fake_probe)
    monkeypatch.setattr(
        intelligence_jobs.settings,
        "interview_staging_directory",
        str(tmp_path),
    )
    context: dict[str, Any] = {
        "redis": RecordingRedis(),
        "transcription_provider": provider,
        "upload_store": StagedUploadStore(),
        "media_staging_guard": StagingGuard(max_concurrency=1, min_free_bytes=0),
    }

    await intelligence_jobs.submit_transcription(context, str(interview_id))

    assert provider.submitted_path is not None
    assert not provider.submitted_path.exists()
    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, interview_id)
        assert interview is not None
        assert interview.duration_ms == 42_000
    assert interview.processing_status is IntelligenceProcessingStatus.TRANSCRIPTION_SUBMITTED


@pytest.mark.parametrize("stored_size", [None, 0, 1, 4_096])
@pytest.mark.asyncio
async def test_file_transcription_repairs_missing_or_stale_legacy_media_size(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    stored_size: int | None,
) -> None:
    created, _, stage_id = await create_analysis_from_journal(
        client,
        seeded,
        monkeypatch,
        company_name=f"Legacy media size {stored_size}",
        media_size=stored_size,
        media_storage_key=("external:https://s3.firstvds.ru:443/interviews/legacy/recording.mp3"),
    )
    assert created.status_code == 201, created.text
    interview_id = UUID(created.json()["id"])
    provider = FileUploadTranscriptionProvider()

    async def fake_probe(*_args: object, **_kwargs: object) -> MediaProbe:
        return MediaProbe(
            format_names=("mp3",),
            duration_seconds=10,
            streams=(MediaStreamProbe(kind="audio", codec="mp3", duration_seconds=10),),
        )

    monkeypatch.setattr(intelligence_jobs, "async_session_factory", TestSession)
    monkeypatch.setattr(intelligence_jobs, "probe_media_async", fake_probe)
    monkeypatch.setattr(intelligence_jobs.settings, "interview_staging_directory", str(tmp_path))
    context: dict[str, Any] = {
        "redis": RecordingRedis(),
        "transcription_provider": provider,
        "upload_store": StagedUploadStore(actual_size=1_024),
        "media_staging_guard": StagingGuard(max_concurrency=1, min_free_bytes=0),
    }

    await intelligence_jobs.submit_transcription(context, str(interview_id))

    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, interview_id)
        stage = await session.get(InterviewProcessStage, stage_id)
    assert interview is not None
    assert stage is not None
    assert interview.processing_status is IntelligenceProcessingStatus.TRANSCRIPTION_SUBMITTED
    assert stage.media_size == 1_024


class LegacyM4aUploadStore(StagedUploadStore):
    """A legacy ".mp3" recording that is actually an ALAC-free m4a container."""

    async def ensure_browser_playable(self, upload: StoredUpload) -> StoredUpload:
        return StoredUpload(
            storage_key=upload.storage_key,
            filename="recording.m4a",
            content_type="audio/mp4",
            size=upload.size,
        )


@pytest.mark.asyncio
async def test_file_transcription_corrects_mislabeled_legacy_audio_before_probing(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    created, _, stage_id = await create_analysis_from_journal(
        client,
        seeded,
        monkeypatch,
        company_name="Legacy mislabeled audio",
        media_storage_key="external:https://s3.firstvds.ru:443/interviews/legacy/recording.mp3",
    )
    assert created.status_code == 201, created.text
    interview_id = UUID(created.json()["id"])
    provider = FileUploadTranscriptionProvider()
    declared_content_types: list[str] = []

    async def fake_probe(*_args: object, **kwargs: object) -> MediaProbe:
        declared_content_types.append(str(kwargs["declared_content_type"]))
        return MediaProbe(
            format_names=("mov", "mp4", "m4a"),
            duration_seconds=10,
            streams=(MediaStreamProbe(kind="audio", codec="aac", duration_seconds=10),),
        )

    monkeypatch.setattr(intelligence_jobs, "async_session_factory", TestSession)
    monkeypatch.setattr(intelligence_jobs, "probe_media_async", fake_probe)
    monkeypatch.setattr(intelligence_jobs.settings, "interview_staging_directory", str(tmp_path))
    context: dict[str, Any] = {
        "redis": RecordingRedis(),
        "transcription_provider": provider,
        "upload_store": LegacyM4aUploadStore(actual_size=1_024),
        "media_staging_guard": StagingGuard(max_concurrency=1, min_free_bytes=0),
    }

    await intelligence_jobs.submit_transcription(context, str(interview_id))

    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, interview_id)
        stage = await session.get(InterviewProcessStage, stage_id)
    assert interview is not None
    assert stage is not None
    assert interview.processing_status is IntelligenceProcessingStatus.TRANSCRIPTION_SUBMITTED
    assert interview.processing_error_code is None
    assert declared_content_types == ["audio/mp4"]
    assert stage.media_content_type == "audio/mp4"
    assert stage.media_filename == "recording.m4a"


@pytest.mark.asyncio
async def test_file_transcription_rejects_actual_object_over_limit_before_download(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    created, _, stage_id = await create_analysis_from_journal(
        client, seeded, monkeypatch, company_name="Oversized stored media", media_size=0
    )
    interview_id = UUID(created.json()["id"])
    provider = FileUploadTranscriptionProvider()
    upload_store = StagedUploadStore(
        actual_size=intelligence_jobs.settings.interview_audio_max_bytes + 1
    )
    monkeypatch.setattr(intelligence_jobs, "async_session_factory", TestSession)
    monkeypatch.setattr(intelligence_jobs.settings, "interview_staging_directory", str(tmp_path))
    context: dict[str, Any] = {
        "redis": RecordingRedis(),
        "transcription_provider": provider,
        "upload_store": upload_store,
        "media_staging_guard": StagingGuard(max_concurrency=1, min_free_bytes=0),
    }

    await intelligence_jobs.submit_transcription(context, str(interview_id))

    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, interview_id)
        stage = await session.get(InterviewProcessStage, stage_id)
    assert interview is not None
    assert stage is not None
    assert interview.processing_status is IntelligenceProcessingStatus.FAILED
    assert interview.processing_error_code == "MEDIA_FILE_TOO_LARGE"
    assert stage.media_size == intelligence_jobs.settings.interview_audio_max_bytes + 1
    assert upload_store.download_called is False
    assert provider.submitted_path is None


@pytest.mark.asyncio
async def test_file_transcription_records_storage_metadata_failure_without_value_error(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    created, _, _ = await create_analysis_from_journal(
        client, seeded, monkeypatch, company_name="Unavailable metadata", media_size=None
    )
    interview_id = UUID(created.json()["id"])
    provider = FileUploadTranscriptionProvider()
    upload_store = UnavailableMetadataUploadStore()
    monkeypatch.setattr(intelligence_jobs, "async_session_factory", TestSession)
    monkeypatch.setattr(intelligence_jobs.settings, "interview_staging_directory", str(tmp_path))
    context: dict[str, Any] = {
        "redis": RecordingRedis(),
        "transcription_provider": provider,
        "upload_store": upload_store,
        "media_staging_guard": StagingGuard(max_concurrency=1, min_free_bytes=0),
        "job_try": intelligence_jobs.MAX_JOB_TRIES,
    }

    await intelligence_jobs.submit_transcription(context, str(interview_id))

    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, interview_id)
    assert interview is not None
    assert interview.processing_status is IntelligenceProcessingStatus.FAILED
    assert interview.processing_error_code == "STORAGE_ERROR"
    assert upload_store.download_called is False
    assert provider.submitted_path is None


@pytest.mark.parametrize(
    ("failed_stage", "expected_job", "expected_status"),
    [
        (
            IntelligenceAttemptStage.TRANSCRIPTION_POLL,
            "poll_transcription",
            IntelligenceProcessingStatus.TRANSCRIPTION_SUBMITTED,
        ),
        (
            IntelligenceAttemptStage.TRANSCRIPTION_PARSE,
            "process_transcription_result",
            IntelligenceProcessingStatus.TRANSCRIPT_READY,
        ),
    ],
)
@pytest.mark.asyncio
async def test_transcription_retry_reuses_the_existing_paid_provider_job(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
    failed_stage: IntelligenceAttemptStage,
    expected_job: str,
    expected_status: IntelligenceProcessingStatus,
) -> None:
    created, _, _ = await create_analysis_from_journal(
        client, seeded, monkeypatch, company_name=f"Retry {failed_stage.value}"
    )
    interview_id = UUID(created.json()["id"])
    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, interview_id)
        assert interview is not None
        interview.processing_status = IntelligenceProcessingStatus.FAILED
        interview.failed_stage = failed_stage
        interview.transcription_provider_job_id = "already-paid-provider-job"
        interview.transcription_provider_payload = {"status": "processing"}
        await session.commit()

    enqueued: list[tuple[str, UUID]] = []

    async def fake_enqueue(function: str, queued_interview_id: UUID) -> None:
        enqueued.append((function, queued_interview_id))

    monkeypatch.setattr(intelligence_router, "_enqueue", fake_enqueue)
    retried = await client.post(
        f"/api/v1/interviews/{interview_id}/retry",
        headers=auth(seeded.admin_id),
    )

    assert retried.status_code == 200, retried.text
    assert retried.json()["processing_status"] == expected_status.value
    assert enqueued == [(expected_job, interview_id)]
    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, interview_id)
        assert interview is not None
        assert interview.transcription_provider_job_id == "already-paid-provider-job"
        assert interview.transcription_provider_payload == {"status": "processing"}


@pytest.mark.parametrize(
    "failed_stage",
    [
        IntelligenceAttemptStage.TRANSCRIPTION_POLL,
        IntelligenceAttemptStage.TRANSCRIPTION_PARSE,
    ],
)
@pytest.mark.parametrize(
    "error_code",
    ["TRANSCRIPTION_RESULT_EXPIRED", "TRANSCRIPTION_TIMEOUT"],
)
@pytest.mark.asyncio
async def test_transcription_retry_resubmits_when_provider_job_cannot_be_resumed(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
    failed_stage: IntelligenceAttemptStage,
    error_code: str,
) -> None:
    created, _, _ = await create_analysis_from_journal(
        client, seeded, monkeypatch, company_name=f"Expired {failed_stage.value}"
    )
    interview_id = UUID(created.json()["id"])
    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, interview_id)
        assert interview is not None
        interview.processing_status = IntelligenceProcessingStatus.FAILED
        interview.failed_stage = failed_stage
        interview.processing_error_code = error_code
        interview.transcription_provider_job_id = "expired-provider-job"
        interview.transcription_provider_payload = {"status": "complete"}
        await session.commit()

    enqueued: list[tuple[str, UUID]] = []

    async def fake_enqueue(function: str, queued_interview_id: UUID) -> None:
        enqueued.append((function, queued_interview_id))

    monkeypatch.setattr(intelligence_router, "_enqueue", fake_enqueue)
    retried = await client.post(
        f"/api/v1/interviews/{interview_id}/retry",
        headers=auth(seeded.admin_id),
    )

    assert retried.status_code == 200, retried.text
    assert retried.json()["processing_status"] == "uploaded"
    assert enqueued == [("submit_transcription", interview_id)]
    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, interview_id)
        assert interview is not None
        assert interview.transcription_provider_job_id is None
        assert interview.transcription_provider_payload is None


@pytest.mark.asyncio
async def test_student_cannot_delete_own_intelligence_interview(
    client: AsyncClient, seeded: SeededData, monkeypatch: pytest.MonkeyPatch
) -> None:
    created, _, _ = await create_analysis_from_journal(
        client, seeded, monkeypatch, company_name="Protected student analysis"
    )
    interview_id = UUID(created.json()["id"])

    deleted = await client.delete(
        f"/api/v1/interviews/{interview_id}", headers=auth(seeded.student_id)
    )

    assert deleted.status_code == 403
    assert deleted.json()["detail"]["code"] == "student_intelligence_delete_forbidden"
    existing = await client.get(
        f"/api/v1/interviews/{interview_id}", headers=auth(seeded.student_id)
    )
    assert existing.status_code == 200


@pytest.mark.asyncio
async def test_admin_can_delete_stuck_intelligence_interview(
    client: AsyncClient, seeded: SeededData, monkeypatch: pytest.MonkeyPatch
) -> None:
    created, process_id, stage_id = await create_analysis_from_journal(
        client, seeded, monkeypatch, company_name="Stuck AI"
    )
    interview_id = UUID(created.json()["id"])
    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, interview_id)
        assert interview is not None
        interview.processing_status = IntelligenceProcessingStatus.ANALYZING
        await session.commit()

    deleted = await client.delete(
        f"/api/v1/interviews/{interview_id}", headers=auth(seeded.admin_id)
    )

    assert deleted.status_code == 204, deleted.text
    missing = await client.get(f"/api/v1/interviews/{interview_id}", headers=auth(seeded.admin_id))
    assert missing.status_code == 404
    async with TestSession() as session:
        admission = await session.scalar(
            select(IntelligenceAIAdmission).where(
                IntelligenceAIAdmission.requester_user_id == seeded.student_id
            )
        )
        assert admission is not None
        assert admission.interview_id is None
    journal = await client.get(
        f"/api/v1/interviews/journal/tracks/{process_id}",
        headers=auth(seeded.student_id),
    )
    assert journal.status_code == 200
    assert journal.json()["stages"][0]["id"] == str(stage_id)
    assert journal.json()["stages"][0]["media"]["filename"] == "recording.mp3"
    assert journal.json()["stages"][0]["ai_analysis_requested_at"] is not None
    duplicate = await client.post(
        f"/api/v1/interviews/journal/tracks/{process_id}/stages/{stage_id}/ai-analysis",
        headers=auth(seeded.student_id),
    )
    assert duplicate.status_code == 409
