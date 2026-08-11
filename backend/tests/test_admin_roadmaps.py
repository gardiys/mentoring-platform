from uuid import uuid4

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


async def test_only_admin_can_open_constructor_api(client: AsyncClient, seeded: SeededData) -> None:
    student_response = await client.get("/api/v1/admin/roadmaps", headers=auth(seeded.student_id))
    mentor_response = await client.get("/api/v1/admin/roadmaps", headers=auth(seeded.mentor_id))
    admin_response = await client.get("/api/v1/admin/roadmaps", headers=auth(seeded.admin_id))

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
    student_roadmaps = await client.get("/api/v1/roadmaps", headers=auth(seeded.student_id))
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


async def test_constructor_rejects_duplicate_slugs(client: AsyncClient, seeded: SeededData) -> None:
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
    assert response.json()["detail"]["code"] == "roadmap_structure_removal_not_supported"


async def test_only_admin_can_delete_roadmap(client: AsyncClient, seeded: SeededData) -> None:
    student_response = await client.delete(
        f"/api/v1/admin/roadmaps/{seeded.roadmap_id}", headers=auth(seeded.student_id)
    )
    mentor_response = await client.delete(
        f"/api/v1/admin/roadmaps/{seeded.roadmap_id}", headers=auth(seeded.mentor_id)
    )

    assert student_response.status_code == 403
    assert mentor_response.status_code == 403

    still_there = await client.get(
        f"/api/v1/admin/roadmaps/{seeded.roadmap_id}", headers=auth(seeded.admin_id)
    )
    assert still_there.status_code == 200


async def test_admin_deletes_roadmap_and_cascades_student_progress(
    client: AsyncClient, seeded: SeededData
) -> None:
    await client.put(
        f"/api/v1/me/topics/{seeded.topic_ids[0]}/progress",
        headers=auth(seeded.student_id),
        json={"status": "completed"},
    )

    response = await client.delete(
        f"/api/v1/admin/roadmaps/{seeded.roadmap_id}", headers=auth(seeded.admin_id)
    )
    assert response.status_code == 204

    missing = await client.get(
        f"/api/v1/admin/roadmaps/{seeded.roadmap_id}", headers=auth(seeded.admin_id)
    )
    assert missing.status_code == 404

    topic_gone = await client.get(
        f"/api/v1/topics/{seeded.topic_ids[0]}", headers=auth(seeded.student_id)
    )
    assert topic_gone.status_code == 404

    student_roadmaps = await client.get("/api/v1/roadmaps", headers=auth(seeded.student_id))
    assert "python-backend" not in {item["slug"] for item in student_roadmaps.json()}


async def test_deleting_missing_roadmap_returns_404(
    client: AsyncClient,
    seeded: SeededData,
) -> None:
    response = await client.delete(
        f"/api/v1/admin/roadmaps/{uuid4()}", headers=auth(seeded.admin_id)
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "roadmap_not_found"


async def test_admin_outline_omits_markdown_and_updates_one_topic(
    client: AsyncClient, seeded: SeededData
) -> None:
    summaries = await client.get("/api/v1/admin/roadmaps/summaries", headers=auth(seeded.admin_id))
    outline = await client.get(
        f"/api/v1/admin/roadmaps/{seeded.roadmap_id}/outline",
        headers=auth(seeded.admin_id),
    )
    assert summaries.status_code == outline.status_code == 200
    python_summary = next(item for item in summaries.json() if item["id"] == str(seeded.roadmap_id))
    assert python_summary["section_count"] == 1
    assert python_summary["topic_count"] == 2
    assert "sections" not in python_summary
    topic_summary = outline.json()["sections"][0]["topics"][0]
    assert "content_markdown" not in topic_summary

    topic_id = topic_summary["id"]
    section_id = outline.json()["sections"][0]["id"]
    detail = await client.get(
        f"/api/v1/admin/roadmaps/{seeded.roadmap_id}/sections/{section_id}/topics/{topic_id}",
        headers=auth(seeded.admin_id),
    )
    payload = detail.json()
    payload.pop("id")
    payload["title"] = "Точечно обновлённая тема"
    updated = await client.put(
        f"/api/v1/admin/roadmaps/{seeded.roadmap_id}/sections/{section_id}/topics/{topic_id}",
        headers=auth(seeded.admin_id),
        json=payload,
    )
    full = await client.get(
        f"/api/v1/admin/roadmaps/{seeded.roadmap_id}",
        headers=auth(seeded.admin_id),
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Точечно обновлённая тема"
    assert len(full.json()["sections"][0]["topics"]) == 2
