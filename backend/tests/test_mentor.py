from httpx import AsyncClient

from tests.conftest import SeededData, auth


async def test_student_cannot_use_mentor_endpoint(
    client: AsyncClient, seeded: SeededData
) -> None:
    response = await client.get(
        "/api/v1/mentor/students", headers=auth(seeded.student_id)
    )
    assert response.status_code == 403


async def test_mentor_sees_assigned_student_and_topic_history(
    client: AsyncClient, seeded: SeededData
) -> None:
    await client.put(
        f"/api/v1/me/topics/{seeded.topic_ids[0]}/progress",
        headers=auth(seeded.student_id),
        json={"status": "completed"},
    )
    listing = await client.get(
        "/api/v1/mentor/students", headers=auth(seeded.mentor_id)
    )
    detail = await client.get(
        f"/api/v1/mentor/students/{seeded.student_id}",
        headers=auth(seeded.mentor_id),
    )

    assert [item["id"] for item in listing.json()] == [str(seeded.student_id)]
    topic = detail.json()["roadmaps"][0]["sections"][0]["topics"][0]
    assert topic["status"] == "completed"
    assert topic["first_completed_at"] is not None


async def test_mentor_cannot_see_unassigned_student(
    client: AsyncClient, seeded: SeededData
) -> None:
    listing = await client.get(
        "/api/v1/mentor/students", headers=auth(seeded.other_mentor_id)
    )
    detail = await client.get(
        f"/api/v1/mentor/students/{seeded.student_id}",
        headers=auth(seeded.other_mentor_id),
    )

    assert listing.json() == []
    assert detail.status_code == 403
    assert detail.json()["detail"]["code"] == "student_not_assigned_to_mentor"
