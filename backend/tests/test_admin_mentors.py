from httpx import AsyncClient
from sqlalchemy import select

from app.mentors.models import MentorStudent
from app.tracks.models import LearningTrackEnrollment
from app.users.models import User, UserRole
from tests.conftest import SeededData, TestSession, auth


async def test_only_admin_can_manage_mentors(client: AsyncClient, seeded: SeededData) -> None:
    denied = await client.get("/api/v1/admin/mentors", headers=auth(seeded.student_id))
    allowed = await client.get("/api/v1/admin/mentors", headers=auth(seeded.admin_id))

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert {item["id"] for item in allowed.json()} == {
        str(seeded.mentor_id),
        str(seeded.other_mentor_id),
        str(seeded.admin_id),
    }
    primary = next(item for item in allowed.json() if item["id"] == str(seeded.mentor_id))
    assert [track["slug"] for track in primary["tracks"]] == ["python"]
    assert [student["id"] for student in primary["students"]] == [str(seeded.student_id)]
    admin = next(item for item in allowed.json() if item["id"] == str(seeded.admin_id))
    assert admin["role"] == "admin"
    assert [track["slug"] for track in admin["tracks"]] == ["python", "go"]


async def test_admin_can_be_assigned_as_mentor_without_changing_primary_role(
    client: AsyncClient, seeded: SeededData
) -> None:
    options = await client.get("/api/v1/admin/students/options", headers=auth(seeded.admin_id))
    reassigned = await client.patch(
        f"/api/v1/admin/mentors/students/{seeded.student_id}/mentor",
        headers=auth(seeded.admin_id),
        json={"mentor_id": str(seeded.admin_id)},
    )
    filtered = await client.get(
        f"/api/v1/mentor/students?mentor_id={seeded.admin_id}",
        headers=auth(seeded.admin_id),
    )
    remove_attempt = await client.delete(
        f"/api/v1/admin/mentors/{seeded.admin_id}",
        headers=auth(seeded.admin_id),
    )

    assert options.status_code == 200
    admin_option = next(
        item for item in options.json()["mentors"] if item["id"] == str(seeded.admin_id)
    )
    assert admin_option["role"] == "admin"
    assert reassigned.status_code == 204
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()["items"]] == [str(seeded.student_id)]
    assert remove_attempt.status_code == 404

    async with TestSession() as session:
        admin = await session.get(User, seeded.admin_id)
        relation = await session.scalar(
            select(MentorStudent).where(MentorStudent.student_id == seeded.student_id)
        )
        assert admin is not None
        assert admin.role is UserRole.ADMIN
        assert relation is not None
        assert relation.mentor_id == seeded.admin_id


async def test_admin_creates_and_removes_unassigned_mentor(
    client: AsyncClient, seeded: SeededData
) -> None:
    created = await client.post(
        "/api/v1/admin/mentors",
        headers=auth(seeded.admin_id),
        json={
            "telegram_id": 777111222,
            "telegram_username": "new_mentor",
            "first_name": "Мария",
            "last_name": "Иванова",
            "email": "mentor-new@example.com",
            "track_ids": [str(seeded.python_track_id)],
        },
    )
    removed = await client.delete(
        f"/api/v1/admin/mentors/{created.json()['id']}",
        headers=auth(seeded.admin_id),
    )

    assert created.status_code == 201
    assert created.json()["student_count"] == 0
    assert removed.status_code == 204
    async with TestSession() as session:
        user = await session.get(User, created.json()["id"])
        assert user is not None
        assert user.role is UserRole.STUDENT
        assert user.session_version == 2
        track_ids = set(
            await session.scalars(
                select(LearningTrackEnrollment.track_id).where(
                    LearningTrackEnrollment.user_id == user.id
                )
            )
        )
        assert track_ids == {seeded.python_track_id}


async def test_admin_promotes_student_and_keeps_account_data(
    client: AsyncClient, seeded: SeededData
) -> None:
    promoted = await client.post(
        f"/api/v1/admin/mentors/{seeded.student_id}/promote",
        headers=auth(seeded.admin_id),
    )
    candidates = await client.get("/api/v1/admin/mentors/candidates", headers=auth(seeded.admin_id))

    assert promoted.status_code == 200
    assert promoted.json()["id"] == str(seeded.student_id)
    assert all(item["id"] != str(seeded.student_id) for item in candidates.json())
    async with TestSession() as session:
        user = await session.get(User, seeded.student_id)
        relation = await session.scalar(
            select(MentorStudent).where(MentorStudent.student_id == seeded.student_id)
        )
        assert user is not None
        assert user.role is UserRole.MENTOR
        assert user.session_version == 2
        assert relation is None


async def test_admin_must_reassign_students_before_removing_mentor(
    client: AsyncClient, seeded: SeededData
) -> None:
    response = await client.delete(
        f"/api/v1/admin/mentors/{seeded.mentor_id}",
        headers=auth(seeded.admin_id),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "mentor_has_students"


async def test_admin_updates_directions_and_reassigns_students(
    client: AsyncClient, seeded: SeededData
) -> None:
    rejected = await client.patch(
        f"/api/v1/admin/mentors/{seeded.mentor_id}/directions",
        headers=auth(seeded.admin_id),
        json={"track_ids": [str(seeded.go_track_id)]},
    )
    expanded = await client.patch(
        f"/api/v1/admin/mentors/{seeded.other_mentor_id}/directions",
        headers=auth(seeded.admin_id),
        json={
            "track_ids": [
                str(seeded.python_track_id),
                str(seeded.go_track_id),
            ]
        },
    )
    reassigned = await client.patch(
        f"/api/v1/admin/mentors/students/{seeded.student_id}/mentor",
        headers=auth(seeded.admin_id),
        json={"mentor_id": str(seeded.other_mentor_id)},
    )
    listing = await client.get("/api/v1/admin/mentors", headers=auth(seeded.admin_id))

    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "mentor_directions_have_students"
    assert expanded.status_code == 200
    assert reassigned.status_code == 204
    mentors = {item["id"]: item for item in listing.json()}
    assert mentors[str(seeded.mentor_id)]["students"] == []
    assert mentors[str(seeded.other_mentor_id)]["students"][0]["id"] == str(seeded.student_id)


async def test_admin_edits_existing_mentor_and_admin_profile_data(
    client: AsyncClient, seeded: SeededData
) -> None:
    mentor_updated = await client.patch(
        f"/api/v1/admin/mentors/{seeded.mentor_id}/profile",
        headers=auth(seeded.admin_id),
        json={
            "first_name": "Антон",
            "last_name": "Менторов",
            "email": "anton.mentor@example.com",
            "telegram_username": "  @@anton_python  ",
        },
    )
    admin_updated = await client.patch(
        f"/api/v1/admin/mentors/{seeded.admin_id}/profile",
        headers=auth(seeded.admin_id),
        json={
            "first_name": "Главный администратор",
            "last_name": None,
            "email": None,
            "telegram_username": "@platform_admin",
        },
    )
    invalid = await client.patch(
        f"/api/v1/admin/mentors/{seeded.other_mentor_id}/profile",
        headers=auth(seeded.admin_id),
        json={
            "first_name": "Другой",
            "telegram_username": "invalid username",
        },
    )

    assert mentor_updated.status_code == 200, mentor_updated.text
    assert mentor_updated.json()["telegram_username"] == "anton_python"
    assert mentor_updated.json()["last_name"] == "Менторов"
    assert mentor_updated.json()["email"] == "anton.mentor@example.com"
    assert admin_updated.status_code == 200, admin_updated.text
    assert admin_updated.json()["role"] == "admin"
    assert admin_updated.json()["telegram_username"] == "platform_admin"
    assert invalid.status_code == 422

    async with TestSession() as session:
        mentor = await session.get(User, seeded.mentor_id)
        admin = await session.get(User, seeded.admin_id)
        assert mentor is not None and admin is not None
        assert mentor.role is UserRole.MENTOR
        assert admin.role is UserRole.ADMIN
        assert mentor.telegram_id is None
        assert admin.telegram_id is None
