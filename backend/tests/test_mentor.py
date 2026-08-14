from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy import select

from app.interviews.intelligence_models import (
    IntelligenceInterview,
    IntelligenceInterviewType,
    IntelligenceProcessingStatus,
)
from app.interviews.models import (
    Company,
    InterviewProcess,
    InterviewProcessStage,
    InterviewProcessStatus,
    InterviewStageType,
)
from app.mentors.models import (
    MentorStudent,
    StudentLearningStatus,
    StudentMentorshipState,
)
from app.tracks.models import LearningTrackEnrollment
from app.users.models import User, UserRole
from tests.conftest import SeededData, TestSession, auth


async def test_student_cannot_use_mentor_endpoint(client: AsyncClient, seeded: SeededData) -> None:
    response = await client.get("/api/v1/mentor/students", headers=auth(seeded.student_id))
    assert response.status_code == 403


async def test_mentor_sees_assigned_student_and_topic_history(
    client: AsyncClient, seeded: SeededData
) -> None:
    await client.put(
        f"/api/v1/me/topics/{seeded.topic_ids[0]}/progress",
        headers=auth(seeded.student_id),
        json={"status": "completed"},
    )
    listing = await client.get("/api/v1/mentor/students", headers=auth(seeded.mentor_id))
    detail = await client.get(
        f"/api/v1/mentor/students/{seeded.student_id}",
        headers=auth(seeded.mentor_id),
    )

    assert [item["id"] for item in listing.json()["items"]] == [str(seeded.student_id)]
    assert listing.json()["items"][0]["last_activity_kind"] == "roadmap"
    topic = detail.json()["roadmaps"][0]["sections"][0]["topics"][0]
    assert topic["status"] == "completed"
    assert topic["first_completed_at"] is not None

    created_interview = await client.post(
        "/api/v1/interviews/journal/tracks",
        headers=auth(seeded.student_id),
        json={
            "company_name": "Активность ученика",
            "track_id": str(seeded.python_track_id),
        },
    )
    assert created_interview.status_code == 201
    listing_after_interview = await client.get(
        "/api/v1/mentor/students",
        headers=auth(seeded.mentor_id),
        params={"sort": "last_activity_desc"},
    )
    assert listing_after_interview.status_code == 200
    student = listing_after_interview.json()["items"][0]
    assert student["last_progress_at"] is not None
    assert student["last_activity_kind"] == "interview"


async def test_student_status_history_tracks_transitions_without_resetting_unchanged_status(
    client: AsyncClient, seeded: SeededData
) -> None:
    initial = await client.get(
        f"/api/v1/mentor/students/{seeded.student_id}",
        headers=auth(seeded.mentor_id),
    )
    changed = await client.patch(
        f"/api/v1/mentor/students/{seeded.student_id}/state",
        headers=auth(seeded.mentor_id),
        json={"learning_status": "interviewing", "strength_level": "medium"},
    )
    unchanged = await client.patch(
        f"/api/v1/mentor/students/{seeded.student_id}/state",
        headers=auth(seeded.mentor_id),
        json={"learning_status": "interviewing", "strength_level": "strong"},
    )

    assert initial.status_code == 200
    assert initial.json()["status_history"][0]["status"] == "learning"
    assert changed.status_code == 200
    history = changed.json()["status_history"]
    assert [period["status"] for period in history] == ["interviewing", "learning"]
    assert history[0]["ended_at"] is None
    assert history[1]["ended_at"] is not None
    assert unchanged.status_code == 200
    assert len(unchanged.json()["status_history"]) == 2
    assert unchanged.json()["status_history"][0]["started_at"] == history[0]["started_at"]


async def test_admin_updates_state_for_student_without_assigning_a_mentor(
    client: AsyncClient, seeded: SeededData
) -> None:
    student_id = uuid4()
    async with TestSession() as session:
        session.add(User(id=student_id, first_name="Без ментора", role=UserRole.STUDENT))
        await session.commit()

    updated = await client.patch(
        f"/api/v1/mentor/students/{student_id}/state",
        headers=auth(seeded.admin_id),
        json={"learning_status": "interviewing", "strength_level": "strong"},
    )
    admin_detail = await client.get(
        f"/api/v1/admin/students/{student_id}",
        headers=auth(seeded.admin_id),
    )
    filtered = await client.get(
        "/api/v1/mentor/students",
        headers=auth(seeded.admin_id),
        params=[
            ("without_mentor", "true"),
            ("learning_status", "interviewing"),
        ],
    )

    assert updated.status_code == 200
    assert updated.json()["learning_status"] == "interviewing"
    assert updated.json()["strength_level"] == "strong"
    assert updated.json()["status_history"][0]["status"] == "interviewing"
    assert admin_detail.status_code == 200
    assert admin_detail.json()["mentor"] is None
    assert admin_detail.json()["learning_status"] == "interviewing"
    assert [item["id"] for item in filtered.json()["items"]] == [str(student_id)]
    async with TestSession() as session:
        assert await session.scalar(
            select(MentorStudent).where(MentorStudent.student_id == student_id)
        ) is None
        state = await session.get(StudentMentorshipState, student_id)
        assert state is not None
        assert state.learning_status is StudentLearningStatus.INTERVIEWING


async def test_interview_analytics_respects_period_and_reports_operational_metrics(
    client: AsyncClient, seeded: SeededData
) -> None:
    now = datetime.now(UTC)
    async with TestSession() as session:
        companies = [
            Company(name="Первая", normalized_name="первая", transliterated_name="pervaya"),
            Company(name="Вторая", normalized_name="вторая", transliterated_name="vtoraya"),
            Company(name="Старая", normalized_name="старая", transliterated_name="staraya"),
        ]
        session.add_all(companies)
        await session.flush()
        active_process = InterviewProcess(
            user_id=seeded.student_id,
            track_id=seeded.python_track_id,
            company_id=companies[0].id,
            company_name=companies[0].name,
            status=InterviewProcessStatus.ACTIVE,
        )
        offer_process = InterviewProcess(
            user_id=seeded.student_id,
            track_id=seeded.python_track_id,
            company_id=companies[1].id,
            company_name=companies[1].name,
            status=InterviewProcessStatus.OFFER,
            offer_received_at=now - timedelta(days=1),
        )
        old_process = InterviewProcess(
            user_id=seeded.student_id,
            track_id=seeded.python_track_id,
            company_id=companies[2].id,
            company_name=companies[2].name,
            status=InterviewProcessStatus.CLOSED,
        )
        session.add_all([active_process, offer_process, old_process])
        await session.flush()
        screening = InterviewProcessStage(
            process_id=active_process.id,
            stage_type=InterviewStageType.SCREENING,
            scheduled_at=now - timedelta(days=4),
        )
        technical = InterviewProcessStage(
            process_id=active_process.id,
            stage_type=InterviewStageType.TECHNICAL_INTERVIEW,
            scheduled_at=now - timedelta(days=2),
            media_storage_key="interviews/recording.mp4",
            media_filename="recording.mp4",
            media_content_type="video/mp4",
            media_size=1024,
            ai_analysis_requested_at=now - timedelta(days=1),
        )
        final = InterviewProcessStage(
            process_id=offer_process.id,
            stage_type=InterviewStageType.FINAL_INTERVIEW,
            scheduled_at=now - timedelta(days=1),
        )
        old_stage = InterviewProcessStage(
            process_id=old_process.id,
            stage_type=InterviewStageType.OTHER,
            scheduled_at=now - timedelta(days=10),
        )
        session.add_all([screening, technical, final, old_stage])
        await session.flush()
        session.add(
            IntelligenceInterview(
                stage_id=technical.id,
                student_id=seeded.student_id,
                interview_type=IntelligenceInterviewType.TECHNICAL,
                processing_status=IntelligenceProcessingStatus.READY,
            )
        )
        await session.commit()

    weekly = await client.get(
        "/api/v1/mentor/students/analytics",
        headers=auth(seeded.mentor_id),
        params={"period": "week"},
    )
    monthly = await client.get(
        "/api/v1/mentor/students/analytics",
        headers=auth(seeded.mentor_id),
        params={"period": "month"},
    )

    assert weekly.status_code == 200
    data = weekly.json()
    assert data["total_interviews"] == 3
    assert data["offers_received"] == 1
    assert data["ai_analyses_started"] == 1
    assert data["ai_analyses_ready"] == 1
    assert data["interviews_with_recording"] == 1
    assert data["unique_companies"] == 2
    assert data["active_processes"] == 1
    assert data["offer_conversion_percent"] == 50.0
    assert data["recording_coverage_percent"] == 33.3
    assert data["ranking"][0]["student_id"] == str(seeded.student_id)
    assert data["ranking"][0]["interview_count"] == 3
    stage_counts = {item["stage_type"]: item["count"] for item in data["stage_counts"]}
    assert stage_counts["screening"] == 1
    assert stage_counts["technical_interview"] == 1
    assert stage_counts["final_interview"] == 1
    assert stage_counts["other"] == 0
    assert monthly.status_code == 200
    assert monthly.json()["total_interviews"] == 4


async def test_admin_compares_mentor_efficiency_by_real_interview_activity(
    client: AsyncClient, seeded: SeededData
) -> None:
    now = datetime.now(UTC)
    inactive_student_id = uuid4()
    unassigned_student_id = uuid4()
    async with TestSession() as session:
        primary_relation = await session.scalar(
            select(MentorStudent).where(MentorStudent.student_id == seeded.student_id)
        )
        assert primary_relation is not None
        primary_relation.learning_status = StudentLearningStatus.INTERVIEWING
        session.add_all(
            [
                User(
                    id=inactive_student_id,
                    first_name="Неактивный",
                    role=UserRole.STUDENT,
                ),
                User(
                    id=unassigned_student_id,
                    first_name="Без ментора",
                    role=UserRole.STUDENT,
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                MentorStudent(
                    mentor_id=seeded.other_mentor_id,
                    student_id=inactive_student_id,
                    learning_status=StudentLearningStatus.INTERVIEWING,
                ),
                StudentMentorshipState(
                    student_id=unassigned_student_id,
                    learning_status=StudentLearningStatus.INTERVIEWING,
                ),
                LearningTrackEnrollment(
                    user_id=inactive_student_id,
                    track_id=seeded.python_track_id,
                ),
                LearningTrackEnrollment(
                    user_id=unassigned_student_id,
                    track_id=seeded.python_track_id,
                ),
            ]
        )
        company = Company(
            name="Активная компания",
            normalized_name="активная компания",
            transliterated_name="aktivnaya kompaniya",
        )
        session.add(company)
        await session.flush()
        process = InterviewProcess(
            user_id=seeded.student_id,
            track_id=seeded.python_track_id,
            company_id=company.id,
            company_name=company.name,
            status=InterviewProcessStatus.OFFER,
            offer_received_at=now - timedelta(days=1),
        )
        session.add(process)
        await session.flush()
        session.add(
            InterviewProcessStage(
                process_id=process.id,
                stage_type=InterviewStageType.TECHNICAL_INTERVIEW,
                scheduled_at=now - timedelta(days=2),
                media_storage_key="interviews/mentor-efficiency.mp4",
                media_filename="mentor-efficiency.mp4",
                media_content_type="video/mp4",
                media_size=1024,
                ai_analysis_requested_at=now - timedelta(days=1),
            )
        )
        await session.commit()

    response = await client.get(
        "/api/v1/mentor/students/mentor-efficiency",
        headers=auth(seeded.admin_id),
        params={"period": "week", "track_id": str(seeded.python_track_id)},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["mentor_count"] == 2
    assert data["assigned_students"] == 2
    assert data["interviewing_students"] == 3
    assert data["active_interviewing_students"] == 1
    assert data["inactive_interviewing_students"] == 2
    assert data["unassigned_students"] == 1
    assert data["unassigned_interviewing_students"] == 1
    by_mentor = {item["mentor_id"]: item for item in data["mentors"]}
    active = by_mentor[str(seeded.mentor_id)]
    assert active["active_interviewing_students"] == 1
    assert active["recording_students"] == 1
    assert active["interview_count"] == 1
    assert active["ai_analysis_count"] == 1
    assert active["offer_count"] == 1
    assert active["participation_percent"] == 100.0
    assert active["recording_participation_percent"] == 100.0
    inactive = by_mentor[str(seeded.other_mentor_id)]
    assert inactive["inactive_interviewing_students"] == 1
    assert inactive["participation_percent"] == 0

    forbidden = await client.get(
        "/api/v1/mentor/students/mentor-efficiency",
        headers=auth(seeded.mentor_id),
    )
    assert forbidden.status_code == 403


async def test_mentor_cannot_see_unassigned_student(
    client: AsyncClient, seeded: SeededData
) -> None:
    listing = await client.get("/api/v1/mentor/students", headers=auth(seeded.other_mentor_id))
    detail = await client.get(
        f"/api/v1/mentor/students/{seeded.student_id}",
        headers=auth(seeded.other_mentor_id),
    )

    assert listing.json()["items"] == []
    assert detail.status_code == 403
    assert detail.json()["detail"]["code"] == "student_not_assigned_to_mentor"


async def test_mentor_student_list_supports_pagination_direction_and_multiple_statuses(
    client: AsyncClient, seeded: SeededData
) -> None:
    interviewing_id = uuid4()
    probation_id = uuid4()
    unassigned_id = uuid4()
    async with TestSession() as session:
        session.add_all(
            [
                User(
                    id=interviewing_id,
                    first_name="Пётр",
                    telegram_username="petya_python",
                    role=UserRole.STUDENT,
                    learning_start_date=date(2026, 1, 10),
                ),
                User(
                    id=probation_id,
                    first_name="Сергей",
                    role=UserRole.STUDENT,
                    is_active=False,
                    learning_start_date=date(2026, 2, 10),
                ),
                User(id=unassigned_id, first_name="Без ментора", role=UserRole.STUDENT),
            ]
        )
        await session.flush()
        session.add_all(
            [
                MentorStudent(
                    mentor_id=seeded.mentor_id,
                    student_id=interviewing_id,
                    learning_status=StudentLearningStatus.INTERVIEWING,
                ),
                MentorStudent(
                    mentor_id=seeded.mentor_id,
                    student_id=probation_id,
                    learning_status=StudentLearningStatus.PROBATION,
                ),
                LearningTrackEnrollment(
                    user_id=interviewing_id,
                    track_id=seeded.python_track_id,
                ),
                LearningTrackEnrollment(
                    user_id=probation_id,
                    track_id=seeded.go_track_id,
                ),
            ]
        )
        await session.commit()

    response = await client.get(
        "/api/v1/mentor/students",
        headers=auth(seeded.mentor_id),
        params=[
            ("track_id", str(seeded.python_track_id)),
            ("learning_status", "learning"),
            ("learning_status", "interviewing"),
            ("limit", "1"),
            ("offset", "1"),
        ],
    )
    searched = await client.get(
        "/api/v1/mentor/students",
        headers=auth(seeded.mentor_id),
        params={"query": "petya_python"},
    )
    active = await client.get(
        "/api/v1/mentor/students",
        headers=auth(seeded.mentor_id),
        params={"is_active": "true"},
    )
    inactive = await client.get(
        "/api/v1/mentor/students",
        headers=auth(seeded.mentor_id),
        params={"is_active": "false"},
    )
    assigned_to_mentor = await client.get(
        "/api/v1/mentor/students",
        headers=auth(seeded.admin_id),
        params={"mentor_id": str(seeded.mentor_id)},
    )
    without_mentor = await client.get(
        "/api/v1/mentor/students?without_mentor=true",
        headers=auth(seeded.admin_id),
    )
    forbidden_filter = await client.get(
        "/api/v1/mentor/students?without_mentor=true",
        headers=auth(seeded.mentor_id),
    )
    sorted_by_start = await client.get(
        "/api/v1/mentor/students",
        headers=auth(seeded.mentor_id),
        params={"sort": "learning_start_asc"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert len(response.json()["items"]) == 1
    assert response.json()["limit"] == 1
    assert response.json()["offset"] == 1
    assert [direction["title"] for direction in response.json()["directions"]] == ["Python"]
    assert [item["id"] for item in searched.json()["items"]] == [str(interviewing_id)]
    assert searched.json()["items"][0]["telegram_username"] == "petya_python"
    assert active.json()["total"] == 2
    assert [item["id"] for item in inactive.json()["items"]] == [str(probation_id)]
    assert inactive.json()["items"][0]["is_active"] is False
    assert assigned_to_mentor.json()["total"] == 3
    assert without_mentor.json()["total"] == 1
    assert without_mentor.json()["items"][0]["id"] == str(unassigned_id)
    assert without_mentor.json()["can_filter_by_mentor"] is True
    mentor_options = {item["id"]: item for item in without_mentor.json()["mentors"]}
    assert set(mentor_options) == {
        str(seeded.mentor_id),
        str(seeded.other_mentor_id),
        str(seeded.admin_id),
    }
    assert mentor_options[str(seeded.admin_id)]["role"] == "admin"
    assert forbidden_filter.status_code == 403
    assert [item["id"] for item in sorted_by_start.json()["items"]] == [
        str(interviewing_id),
        str(probation_id),
        str(seeded.student_id),
    ]
    assert sorted_by_start.json()["items"][0]["learning_start_date"] == "2026-01-10"
