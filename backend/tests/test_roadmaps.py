from datetime import datetime, timedelta

from httpx import AsyncClient

from tests.conftest import SeededData, auth


async def test_lists_only_published_roadmaps(client: AsyncClient, seeded: SeededData) -> None:
    response = await client.get("/api/v1/roadmaps", headers=auth(seeded.student_id))

    assert response.status_code == 200
    assert [item["slug"] for item in response.json()] == ["python-backend"]
    assert response.json()[0]["total_topics"] == 2


async def test_returns_ordered_roadmap_structure(client: AsyncClient, seeded: SeededData) -> None:
    response = await client.get("/api/v1/roadmaps/python-backend", headers=auth(seeded.student_id))

    assert response.status_code == 200
    assert response.json()["sections"][0]["title"] == "Python"
    assert [topic["title"] for topic in response.json()["sections"][0]["topics"]] == [
        "Типы",
        "Функции",
    ]
    assert response.json()["started_at"] is None
    assert response.json()["total_duration_days"] == 2
    assert response.json()["sections"][0]["deadline_at"] is None


async def test_starts_roadmap_once_and_calculates_deadlines(
    client: AsyncClient, seeded: SeededData
) -> None:
    first = await client.post(
        "/api/v1/roadmaps/python-backend/start",
        headers=auth(seeded.student_id),
    )
    second = await client.post(
        "/api/v1/roadmaps/python-backend/start",
        headers=auth(seeded.student_id),
    )

    assert first.status_code == second.status_code == 200
    assert second.json()["started_at"] == first.json()["started_at"]
    started_at = datetime.fromisoformat(first.json()["started_at"])
    deadline_at = datetime.fromisoformat(first.json()["sections"][0]["deadline_at"])
    assert deadline_at - started_at == timedelta(days=2)
    assert first.json()["planned_completion_at"] == first.json()["sections"][0]["deadline_at"]


async def test_missing_topic_returns_predictable_404(
    client: AsyncClient, seeded: SeededData
) -> None:
    response = await client.get(
        "/api/v1/topics/00000000-0000-4000-8000-000000000000",
        headers=auth(seeded.student_id),
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "topic_not_found"
