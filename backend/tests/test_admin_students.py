from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import func, select

from app.roadmaps.models import RoadmapEnrollment
from app.tracks.models import LearningTrackEnrollment
from tests.conftest import SeededData, TestSession, auth


def student_payload(
    data: SeededData,
    *,
    telegram_id: int = 777000111,
    first_name: str = "Мария",
    track_ids: list[str] | None = None,
) -> dict[str, object]:
    return {
        "telegram_id": telegram_id,
        "first_name": first_name,
        "last_name": "Петрова",
        "email": "maria@example.com",
        "track_ids": track_ids if track_ids is not None else [str(data.python_track_id)],
    }


async def test_only_admin_can_manage_students(client: AsyncClient, seeded: SeededData) -> None:
    student = await client.get("/api/v1/admin/students", headers=auth(seeded.student_id))
    mentor = await client.get("/api/v1/admin/students", headers=auth(seeded.mentor_id))
    admin = await client.get("/api/v1/admin/students", headers=auth(seeded.admin_id))

    assert student.status_code == mentor.status_code == 403
    assert admin.status_code == 200
    assert admin.json()["total"] == 1
    assert admin.json()["items"][0]["id"] == str(seeded.student_id)
    assert admin.json()["items"][0]["telegram_id"] is None


async def test_admin_creates_student_with_track_access(
    client: AsyncClient, seeded: SeededData
) -> None:
    response = await client.post(
        "/api/v1/admin/students",
        headers=auth(seeded.admin_id),
        json=student_payload(seeded),
    )

    assert response.status_code == 201
    created = response.json()
    assert created["first_name"] == "Мария"
    assert created["is_active"] is True
    assert created["learning_start_date"] == created["created_at"][:10]
    assert [track["slug"] for track in created["tracks"]] == ["python"]

    async with TestSession() as session:
        enrollment = await session.get(RoadmapEnrollment, (UUID(created["id"]), seeded.roadmap_id))
        assert enrollment is not None
        assert enrollment.started_at.date().isoformat() == created["learning_start_date"]

    me = await client.get("/api/v1/me", headers=auth(created["id"]))
    roadmaps = await client.get("/api/v1/roadmaps", headers=auth(created["id"]))
    assert me.status_code == 200
    assert [roadmap["slug"] for roadmap in roadmaps.json()] == ["python-backend"]


async def test_admin_edits_student_data_and_track_access(
    client: AsyncClient, seeded: SeededData
) -> None:
    response = await client.put(
        f"/api/v1/admin/students/{seeded.student_id}",
        headers=auth(seeded.admin_id),
        json=student_payload(
            seeded,
            telegram_id=777000222,
            first_name="Новое имя",
            track_ids=[str(seeded.go_track_id)],
        )
        | {"learning_start_date": "2026-07-15"},
    )
    roadmaps = await client.get("/api/v1/roadmaps", headers=auth(seeded.student_id))

    assert response.status_code == 200
    assert response.json()["telegram_id"] == 777000222
    assert response.json()["first_name"] == "Новое имя"
    assert response.json()["learning_start_date"] == "2026-07-15"
    assert [track["slug"] for track in response.json()["tracks"]] == ["go"]
    assert roadmaps.status_code == 200
    assert roadmaps.json() == []

    async with TestSession() as session:
        enrollment = await session.get(RoadmapEnrollment, (seeded.student_id, seeded.roadmap_id))
        assert enrollment is not None
        assert enrollment.started_at.date().isoformat() == "2026-07-15"


async def test_admin_suspends_and_restores_student_without_losing_tracks(
    client: AsyncClient, seeded: SeededData
) -> None:
    suspended = await client.patch(
        f"/api/v1/admin/students/{seeded.student_id}/access",
        headers=auth(seeded.admin_id),
        json={"is_active": False},
    )
    denied = await client.get("/api/v1/me", headers=auth(seeded.student_id))

    async with TestSession() as session:
        track_count = await session.scalar(
            select(func.count(LearningTrackEnrollment.user_id)).where(
                LearningTrackEnrollment.user_id == seeded.student_id
            )
        )

    restored = await client.patch(
        f"/api/v1/admin/students/{seeded.student_id}/access",
        headers=auth(seeded.admin_id),
        json={"is_active": True},
    )
    available = await client.get("/api/v1/roadmaps", headers=auth(seeded.student_id))

    assert suspended.status_code == 200
    assert suspended.json()["is_active"] is False
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "student_access_suspended"
    assert track_count == 1
    assert restored.json()["is_active"] is True
    assert [roadmap["slug"] for roadmap in available.json()] == ["python-backend"]


async def test_admin_student_list_supports_search_access_filter_and_options(
    client: AsyncClient, seeded: SeededData
) -> None:
    created = await client.post(
        "/api/v1/admin/students",
        headers=auth(seeded.admin_id),
        json=student_payload(seeded),
    )
    await client.patch(
        f"/api/v1/admin/students/{created.json()['id']}/access",
        headers=auth(seeded.admin_id),
        json={"is_active": False},
    )

    search = await client.get(
        "/api/v1/admin/students?q=777000111",
        headers=auth(seeded.admin_id),
    )
    blocked = await client.get(
        "/api/v1/admin/students?access=blocked",
        headers=auth(seeded.admin_id),
    )
    options = await client.get(
        "/api/v1/admin/students/options",
        headers=auth(seeded.admin_id),
    )

    assert search.json()["total"] == 1
    assert search.json()["items"][0]["first_name"] == "Мария"
    assert blocked.json()["total"] == 1
    assert blocked.json()["items"][0]["is_active"] is False
    assert [track["slug"] for track in options.json()["tracks"]] == ["python", "go"]


async def test_admin_rejects_duplicate_student_identifiers(
    client: AsyncClient, seeded: SeededData
) -> None:
    first = await client.post(
        "/api/v1/admin/students",
        headers=auth(seeded.admin_id),
        json=student_payload(seeded),
    )
    duplicate = await client.post(
        "/api/v1/admin/students",
        headers=auth(seeded.admin_id),
        json=student_payload(seeded, first_name="Дубликат"),
    )

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "telegram_id_already_used"
