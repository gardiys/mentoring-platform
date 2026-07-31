from datetime import datetime

from httpx import AsyncClient

from app.progress.models import TopicProgress
from app.roadmaps.models import RoadmapEnrollment
from tests.conftest import SeededData, TestSession, auth


async def complete(client: AsyncClient, data: SeededData, index: int = 0):
    return await client.put(
        f"/api/v1/me/topics/{data.topic_ids[index]}/progress",
        headers=auth(data.student_id),
        json={"status": "completed"},
    )


async def test_completion_is_idempotent_and_preserves_first_date(
    client: AsyncClient, seeded: SeededData
) -> None:
    first = await complete(client, seeded)
    second = await complete(client, seeded)

    assert first.status_code == second.status_code == 200
    assert first.json()["roadmap_progress"]["progress_percent"] == 50
    assert (
        second.json()["topic_progress"]["first_completed_at"]
        == first.json()["topic_progress"]["first_completed_at"]
    )
    assert (
        second.json()["topic_progress"]["last_completed_at"]
        >= first.json()["topic_progress"]["last_completed_at"]
    )
    async with TestSession() as session:
        enrollment = await session.get(RoadmapEnrollment, (seeded.student_id, seeded.roadmap_id))
        assert enrollment is not None and enrollment.started_at is not None


async def test_uncomplete_keeps_history_and_recalculates_enrollment(
    client: AsyncClient, seeded: SeededData
) -> None:
    first = await complete(client, seeded, 0)
    await complete(client, seeded, 1)
    async with TestSession() as session:
        enrollment = await session.get(RoadmapEnrollment, (seeded.student_id, seeded.roadmap_id))
        assert enrollment is not None and enrollment.completed_at is not None

    response = await client.put(
        f"/api/v1/me/topics/{seeded.topic_ids[0]}/progress",
        headers=auth(seeded.student_id),
        json={"status": "not_started"},
    )
    assert response.json()["roadmap_progress"] == {
        "completed_topics": 1,
        "total_topics": 2,
        "progress_percent": 50,
    }
    async with TestSession() as session:
        progress = await session.get(TopicProgress, (seeded.student_id, seeded.topic_ids[0]))
        enrollment = await session.get(RoadmapEnrollment, (seeded.student_id, seeded.roadmap_id))
        assert progress is not None
        assert progress.first_completed_at == datetime.fromisoformat(
            first.json()["topic_progress"]["first_completed_at"]
        )
        assert enrollment is not None and enrollment.completed_at is None


async def test_invalid_status_has_application_error(
    client: AsyncClient, seeded: SeededData
) -> None:
    response = await client.put(
        f"/api/v1/me/topics/{seeded.topic_ids[0]}/progress",
        headers=auth(seeded.student_id),
        json={"status": "wat"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_progress_status"
