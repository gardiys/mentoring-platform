from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.interviews.models import (
    Company,
    InterviewProcess,
    InterviewProcessStage,
    InterviewProcessStatus,
    InterviewStageType,
)
from app.mentors.models import MentorStudent, StudentLearningStatus, StudentMentorshipState
from app.tracks.models import LearningTrackEnrollment
from app.users.models import User, UserRole
from tests.conftest import SeededData, TestSession, auth


@pytest.fixture
async def activity(seeded: SeededData):
    now = datetime.now(UTC)
    interviewing, probation, blocked = uuid4(), uuid4(), uuid4()
    async with TestSession() as session:
        relation = await session.scalar(
            select(MentorStudent).where(MentorStudent.student_id == seeded.student_id)
        )
        relation.learning_status = StudentLearningStatus.INTERVIEWING
        # Current state takes precedence over the legacy relation status.
        session.add(
            StudentMentorshipState(
                student_id=seeded.student_id, learning_status=StudentLearningStatus.LEARNING
            )
        )
        for uid, status, active in (
            (interviewing, StudentLearningStatus.INTERVIEWING, True),
            (probation, StudentLearningStatus.PROBATION, True),
            (blocked, StudentLearningStatus.INTERVIEWING, False),
        ):
            session.add(User(id=uid, first_name="Ученик", role=UserRole.STUDENT, is_active=active))
            await session.flush()
            session.add(
                MentorStudent(student_id=uid, mentor_id=seeded.mentor_id, learning_status=status)
            )
            session.add(LearningTrackEnrollment(user_id=uid, track_id=seeded.python_track_id))
        company = Company(name="Учёт", normalized_name="учёт", transliterated_name="uchet")
        session.add(company)
        await session.flush()
        # Only LEARNING and INTERVIEWING count: five stages, three recordings.
        for uid, stage_count, recording in (
            (seeded.student_id, 3, True),
            (interviewing, 2, False),
            (probation, 1, True),
            (blocked, 1, True),
        ):
            process = InterviewProcess(
                user_id=uid,
                track_id=seeded.python_track_id,
                company_id=company.id,
                company_name=company.name,
                status=InterviewProcessStatus.OFFER
                if uid == probation
                else InterviewProcessStatus.CLOSED,
                offer_received_at=now - timedelta(days=1) if uid == probation else None,
            )
            session.add(process)
            await session.flush()
            for i in range(stage_count):
                session.add(
                    InterviewProcessStage(
                        process_id=process.id,
                        stage_type=InterviewStageType.TECHNICAL_INTERVIEW,
                        scheduled_at=now - timedelta(days=i + 1),
                        media_storage_key=f"recordings/{uuid4()}.mp4" if recording else None,
                        ai_analysis_requested_at=now - timedelta(hours=1)
                        if uid == probation
                        else None,
                    )
                )
            if uid == probation:
                session.add(
                    InterviewProcessStage(
                        process_id=process.id,
                        stage_type=InterviewStageType.FINAL_INTERVIEW,
                        scheduled_at=now + timedelta(days=1),
                    )
                )
        # An old interview entered today must follow its interview date;
        # requesting AI today does not move the interview into this week.
        old_process = InterviewProcess(
            user_id=seeded.student_id,
            track_id=seeded.python_track_id,
            company_id=company.id,
            company_name=company.name,
            status=InterviewProcessStatus.ACTIVE,
        )
        session.add(old_process)
        await session.flush()
        for days in (20, 60, -2):
            session.add(
                InterviewProcessStage(
                    process_id=old_process.id,
                    stage_type=InterviewStageType.SCREENING,
                    scheduled_at=now - timedelta(days=days),
                    media_storage_key=f"recordings/{uuid4()}.mp4",
                    ai_analysis_requested_at=now - timedelta(minutes=1) if days == 20 else None,
                )
            )
        # A second track must not leak into the Python filter.
        session.add(LearningTrackEnrollment(user_id=probation, track_id=seeded.go_track_id))
        go_process = InterviewProcess(
            user_id=probation,
            track_id=seeded.go_track_id,
            company_id=company.id,
            company_name=company.name,
        )
        session.add(go_process)
        await session.flush()
        session.add(
            InterviewProcessStage(
                process_id=go_process.id,
                stage_type=InterviewStageType.TECHNICAL_INTERVIEW,
                scheduled_at=now - timedelta(days=1),
                media_storage_key="recordings/go.mp4",
            )
        )
        await session.commit()


async def read_counts(client, seeded, **params):
    response = await client.get(
        "/api/v1/mentor/students/mentor-efficiency",
        headers=auth(seeded.admin_id),
        params={
            "period": "week",
            "track_id": str(seeded.python_track_id),
            "is_active": "true",
            **params,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    return payload, next(
        (row for row in payload["mentors"] if row["mentor_id"] == str(seeded.mentor_id)), None
    )


@pytest.mark.parametrize(
    "excluded_status", [StudentLearningStatus.PROBATION, StudentLearningStatus.FINISHED]
)
async def test_counts_include_learning_but_exclude_working_students(
    client: AsyncClient, seeded: SeededData, activity, excluded_status
):
    data, row = await read_counts(client, seeded)
    assert row["assigned_students"] == data["assigned_students"] == 2
    assert row["students_with_interviews"] == data["students_with_interviews"] == 2
    assert row["interviewing_students"] == row["active_interviewing_students"] == 1
    assert row["interview_count"] == 5
    assert row["recording_count"] == 3
    assert row["recording_students"] == 1
    assert row["recording_participation_percent"] == 50
    assert row["average_interviews_per_active_student"] == 2.5
    assert row["participation_percent"] == 100
    assert row["ai_analysis_count"] == 1
    assert row["offer_count"] == 0
    assert row["upcoming_students"] == 1
    async with TestSession() as session:
        state = await session.get(StudentMentorshipState, seeded.student_id)
        state.learning_status = excluded_status
        await session.commit()
    _, after = await read_counts(client, seeded)
    assert after["assigned_students"] == after["students_with_interviews"] == 1
    assert after["interview_count"] == 2
    assert after["average_interviews_per_active_student"] == 2
    for key in (
        "recording_count",
        "recording_students",
        "recording_participation_percent",
        "ai_analysis_count",
        "offer_count",
        "upcoming_students",
    ):
        assert after[key] == 0


async def test_period_uses_interview_date_not_entry_or_ai_request(
    client: AsyncClient, seeded: SeededData, activity
):
    _, week = await read_counts(client, seeded)
    _, month = await read_counts(client, seeded, period="month")
    _, all_time = await read_counts(client, seeded, period="all")
    assert [row["interview_count"] for row in (week, month, all_time)] == [5, 6, 7]
    assert [row["recording_count"] for row in (week, month, all_time)] == [3, 4, 5]
    assert all(row["ai_analysis_count"] == 1 for row in (week, month, all_time))
    assert all(row["students_with_interviews"] == 2 for row in (week, month, all_time))
    assert all(row["recording_students"] == 1 for row in (week, month, all_time))


async def test_access_and_direction_filters_apply_to_same_cohort(
    client: AsyncClient, seeded: SeededData, activity
):
    _, inactive = await read_counts(client, seeded, is_active="false")
    assert inactive["assigned_students"] == inactive["students_with_interviews"] == 1
    assert inactive["recording_students"] == inactive["recording_count"] == 1
    data, go = await read_counts(client, seeded, track_id=str(seeded.go_track_id))
    assert go is None
    assert (
        data["mentor_count"] == data["assigned_students"] == data["students_with_interviews"] == 0
    )


async def test_unassigned_students_follow_status_filter_and_missing_status_means_learning(
    client: AsyncClient, seeded: SeededData
):
    learning_id, probation_id = uuid4(), uuid4()
    async with TestSession() as session:
        session.add_all(
            [
                User(id=uid, first_name="Без ментора", role=UserRole.STUDENT)
                for uid in (learning_id, probation_id)
            ]
        )
        await session.flush()
        session.add(
            StudentMentorshipState(
                student_id=probation_id, learning_status=StudentLearningStatus.PROBATION
            )
        )
        session.add_all(
            [
                LearningTrackEnrollment(user_id=uid, track_id=seeded.python_track_id)
                for uid in (learning_id, probation_id)
            ]
        )
        await session.commit()
    data, _ = await read_counts(client, seeded)
    assert data["unassigned_students"] == 1
    assert data["unassigned_interviewing_students"] == 0
