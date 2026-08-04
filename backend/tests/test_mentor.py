from uuid import uuid4

from httpx import AsyncClient

from app.mentors.models import MentorStudent, StudentLearningStatus
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
    topic = detail.json()["roadmaps"][0]["sections"][0]["topics"][0]
    assert topic["status"] == "completed"
    assert topic["first_completed_at"] is not None


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
                ),
                User(
                    id=probation_id,
                    first_name="Сергей",
                    role=UserRole.STUDENT,
                    is_active=False,
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
