from httpx import AsyncClient

from tests.conftest import SeededData, auth
from tests.test_admin_roadmaps import roadmap_payload


def track_payload(
    data: SeededData,
    *,
    slug: str = "python",
    title: str = "Python",
    roadmap_ids: list[str] | None = None,
) -> dict[str, object]:
    return {
        "slug": slug,
        "title": title,
        "description": f"Трек {title} Backend",
        "position": 0,
        "is_published": True,
        "roadmap_ids": roadmap_ids or [str(data.roadmap_id)],
    }


async def test_only_admin_can_manage_learning_tracks(
    client: AsyncClient, seeded: SeededData
) -> None:
    student = await client.get("/api/v1/admin/tracks", headers=auth(seeded.student_id))
    mentor = await client.get("/api/v1/admin/tracks", headers=auth(seeded.mentor_id))
    admin = await client.get("/api/v1/admin/tracks", headers=auth(seeded.admin_id))

    assert student.status_code == mentor.status_code == 403
    assert admin.status_code == 200
    assert [track["slug"] for track in admin.json()] == ["python", "go"]


async def test_admin_includes_roadmap_in_track_and_existing_student_gets_access(
    client: AsyncClient, seeded: SeededData
) -> None:
    roadmap = await client.post(
        "/api/v1/admin/roadmaps",
        headers=auth(seeded.admin_id),
        json=roadmap_payload(),
    )
    updated = await client.put(
        f"/api/v1/admin/tracks/{seeded.python_track_id}",
        headers=auth(seeded.admin_id),
        json=track_payload(
            seeded,
            roadmap_ids=[str(seeded.roadmap_id), roadmap.json()["id"]],
        ),
    )
    student_roadmaps = await client.get("/api/v1/roadmaps", headers=auth(seeded.student_id))

    assert updated.status_code == 200
    assert [item["slug"] for item in updated.json()["roadmaps"]] == [
        "python-backend",
        "django-backend",
    ]
    assert {item["slug"] for item in student_roadmaps.json()} == {
        "python-backend",
        "django-backend",
    }


async def test_admin_revokes_and_restores_track_access_without_losing_track(
    client: AsyncClient, seeded: SeededData
) -> None:
    revoked = await client.delete(
        f"/api/v1/admin/tracks/{seeded.python_track_id}/students/{seeded.student_id}",
        headers=auth(seeded.admin_id),
    )
    unavailable = await client.get("/api/v1/roadmaps", headers=auth(seeded.student_id))
    granted = await client.put(
        f"/api/v1/admin/tracks/{seeded.python_track_id}/students/{seeded.student_id}",
        headers=auth(seeded.admin_id),
    )
    available = await client.get("/api/v1/roadmaps", headers=auth(seeded.student_id))

    assert revoked.status_code == 204
    assert unavailable.json() == []
    assert granted.status_code == 200
    assert granted.json()["granted"] is True
    assert [item["slug"] for item in available.json()] == ["python-backend"]


async def test_track_options_contain_roadmaps_and_students(
    client: AsyncClient, seeded: SeededData
) -> None:
    response = await client.get("/api/v1/admin/tracks/options", headers=auth(seeded.admin_id))

    assert response.status_code == 200
    assert {item["slug"] for item in response.json()["roadmaps"]} == {
        "python-backend",
        "hidden",
    }
    assert [item["id"] for item in response.json()["students"]] == [str(seeded.student_id)]
