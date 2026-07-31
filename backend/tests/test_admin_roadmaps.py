from httpx import AsyncClient

from tests.conftest import SeededData, auth


def roadmap_payload(slug: str = "django-backend") -> dict[str, object]:
    return {
        "slug": slug,
        "title": "Django Backend Developer",
        "description": "Новый роадмап",
        "position": 2,
        "is_published": True,
        "sections": [
            {
                "title": "Django",
                "description": None,
                "position": 0,
                "topics": [
                    {
                        "slug": f"{slug}-orm",
                        "title": "Django ORM",
                        "description": None,
                        "content_markdown": "# Django ORM\n\nМатериал.",
                        "position": 0,
                        "estimated_minutes": 20,
                        "is_published": True,
                    }
                ],
            }
        ],
    }


async def test_only_admin_can_open_constructor_api(
    client: AsyncClient, seeded: SeededData
) -> None:
    student_response = await client.get(
        "/api/v1/admin/roadmaps", headers=auth(seeded.student_id)
    )
    mentor_response = await client.get(
        "/api/v1/admin/roadmaps", headers=auth(seeded.mentor_id)
    )
    admin_response = await client.get(
        "/api/v1/admin/roadmaps", headers=auth(seeded.admin_id)
    )

    assert student_response.status_code == 403
    assert mentor_response.status_code == 403
    assert admin_response.status_code == 200
    assert {item["slug"] for item in admin_response.json()} == {"python-backend", "hidden"}


async def test_admin_creates_nested_published_roadmap(
    client: AsyncClient, seeded: SeededData
) -> None:
    response = await client.post(
        "/api/v1/admin/roadmaps",
        headers=auth(seeded.admin_id),
        json=roadmap_payload(),
    )

    assert response.status_code == 201
    assert response.json()["sections"][0]["topics"][0]["title"] == "Django ORM"
    student_roadmaps = await client.get(
        "/api/v1/roadmaps", headers=auth(seeded.student_id)
    )
    assert {item["slug"] for item in student_roadmaps.json()} == {"python-backend"}

    unavailable = await client.get(
        "/api/v1/roadmaps/django-backend", headers=auth(seeded.student_id)
    )
    unavailable_topic = await client.get(
        f"/api/v1/topics/{response.json()['sections'][0]['topics'][0]['id']}",
        headers=auth(seeded.student_id),
    )
    assert unavailable.status_code == 404
    assert unavailable_topic.status_code == 404


async def test_constructor_rejects_duplicate_slugs(
    client: AsyncClient, seeded: SeededData
) -> None:
    first = await client.post(
        "/api/v1/admin/roadmaps",
        headers=auth(seeded.admin_id),
        json=roadmap_payload(),
    )
    duplicate = await client.post(
        "/api/v1/admin/roadmaps",
        headers=auth(seeded.admin_id),
        json=roadmap_payload(),
    )

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "roadmap_slug_conflict"


async def test_admin_edits_roadmap_without_losing_student_progress(
    client: AsyncClient, seeded: SeededData
) -> None:
    await client.put(
        f"/api/v1/me/topics/{seeded.topic_ids[0]}/progress",
        headers=auth(seeded.student_id),
        json={"status": "completed"},
    )
    detail = await client.get(
        f"/api/v1/admin/roadmaps/{seeded.roadmap_id}",
        headers=auth(seeded.admin_id),
    )
    payload = detail.json()
    payload.pop("id")
    payload["title"] = "Python Backend Updated"
    payload["sections"][0]["topics"].append(
        {
            "slug": "asyncio",
            "title": "Asyncio",
            "description": None,
            "content_markdown": "# Asyncio",
            "position": 2,
            "estimated_minutes": 30,
            "is_published": True,
        }
    )

    updated = await client.put(
        f"/api/v1/admin/roadmaps/{seeded.roadmap_id}",
        headers=auth(seeded.admin_id),
        json=payload,
    )
    topic = await client.get(
        f"/api/v1/topics/{seeded.topic_ids[0]}", headers=auth(seeded.student_id)
    )

    assert updated.status_code == 200
    assert updated.json()["title"] == "Python Backend Updated"
    assert len(updated.json()["sections"][0]["topics"]) == 3
    assert topic.json()["status"] == "completed"
    assert topic.json()["first_completed_at"] is not None


async def test_editor_rejects_removal_of_persisted_topic(
    client: AsyncClient, seeded: SeededData
) -> None:
    detail = await client.get(
        f"/api/v1/admin/roadmaps/{seeded.roadmap_id}",
        headers=auth(seeded.admin_id),
    )
    payload = detail.json()
    payload.pop("id")
    payload["sections"][0]["topics"].pop()

    response = await client.put(
        f"/api/v1/admin/roadmaps/{seeded.roadmap_id}",
        headers=auth(seeded.admin_id),
        json=payload,
    )

    assert response.status_code == 409
    assert (
        response.json()["detail"]["code"]
        == "roadmap_structure_removal_not_supported"
    )
