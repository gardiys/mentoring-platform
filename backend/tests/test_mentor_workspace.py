from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import update

from app.progress.models import TopicProgress
from app.roadmaps.models import RoadmapEnrollment
from tests.conftest import SeededData, TestSession, auth


async def test_mentor_dashboard_shows_current_topic_week_and_overdue_state(
    client: AsyncClient, seeded: SeededData
) -> None:
    await client.post(
        "/api/v1/roadmaps/python-backend/start",
        headers=auth(seeded.student_id),
    )
    await client.put(
        f"/api/v1/me/topics/{seeded.topic_ids[0]}/progress",
        headers=auth(seeded.student_id),
        json={"status": "in_progress"},
    )
    old_date = datetime.now(UTC) - timedelta(days=5)
    async with TestSession() as session:
        await session.execute(
            update(RoadmapEnrollment)
            .where(
                RoadmapEnrollment.user_id == seeded.student_id,
                RoadmapEnrollment.roadmap_id == seeded.roadmap_id,
            )
            .values(started_at=old_date)
        )
        await session.execute(
            update(TopicProgress)
            .where(
                TopicProgress.user_id == seeded.student_id,
                TopicProgress.topic_id == seeded.topic_ids[0],
            )
            .values(started_at=old_date)
        )
        await session.commit()

    listing = await client.get("/api/v1/mentor/students", headers=auth(seeded.mentor_id))
    student = listing.json()[0]

    assert student["is_overdue"] is True
    assert student["roadmaps"][0]["overdue_sections"] == 1
    assert student["current_topics"][0]["title"] == "Типы"
    assert student["current_topics"][0]["days_in_topic"] >= 5
    assert student["completed_topics_this_week"] == 0


async def test_mentor_manages_student_state_notes_documents_and_mocks(
    client: AsyncClient, seeded: SeededData
) -> None:
    state = await client.patch(
        f"/api/v1/mentor/students/{seeded.student_id}/state",
        headers=auth(seeded.mentor_id),
        json={"learning_status": "interviewing", "strength_level": "strong"},
    )
    note = await client.post(
        f"/api/v1/mentor/students/{seeded.student_id}/notes",
        headers=auth(seeded.mentor_id),
        json={"body": "Проверить прогресс по асинхронности"},
    )
    hidden_note = await client.get(
        f"/api/v1/mentor/students/{seeded.student_id}",
        headers=auth(seeded.other_mentor_id),
    )
    document = await client.put(
        f"/api/v1/mentor/students/{seeded.student_id}/documents/resume",
        headers=auth(seeded.mentor_id),
        json={"text_content": "Python-разработчик, 3 года опыта", "keep_file": True},
    )
    student_documents = await client.get(
        "/api/v1/mentor/me/documents", headers=auth(seeded.student_id)
    )
    mock = await client.post(
        f"/api/v1/mentor/students/{seeded.student_id}/mock-interviews",
        headers=auth(seeded.mentor_id),
        json={
            "scheduled_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "description": "Python и проектирование API",
        },
    )
    completed = await client.patch(
        f"/api/v1/mentor/students/{seeded.student_id}/mock-interviews/{mock.json()['id']}/feedback",
        headers=auth(seeded.mentor_id),
        json={"feedback": "Сильная база, повторить транзакции"},
    )
    student_mocks = await client.get(
        "/api/v1/mentor/me/mock-interviews", headers=auth(seeded.student_id)
    )

    assert state.json()["learning_status"] == "interviewing"
    assert state.json()["strength_level"] == "strong"
    assert note.status_code == 201
    assert hidden_note.status_code == 403
    assert document.json()["kind"] == "resume"
    assert student_documents.json()[0]["text_content"].startswith("Python")
    assert completed.json()["status"] == "completed"
    assert student_mocks.json()[0]["feedback"].startswith("Сильная база")


async def test_mentor_reads_student_interview_and_adds_highlighted_feedback(
    client: AsyncClient, seeded: SeededData
) -> None:
    process = await client.post(
        "/api/v1/interviews/journal/tracks",
        headers=auth(seeded.student_id),
        json={"company_name": "Яндекс", "track_id": str(seeded.python_track_id)},
    )
    process_id = process.json()["id"]
    staged = await client.post(
        f"/api/v1/interviews/journal/tracks/{process_id}/stages",
        headers=auth(seeded.student_id),
        json={
            "stage_type": "technical_interview",
            "scheduled_at": datetime.now(UTC).isoformat(),
            "description": "Алгоритмы и Python",
        },
    )
    stage_id = staged.json()["stages"][0]["id"]
    feedback = await client.post(
        f"/api/v1/mentor/students/{seeded.student_id}/interviews/stages/{stage_id}/feedback",
        headers=auth(seeded.mentor_id),
        json={"body": "Разобрать оценку сложности и индексы"},
    )
    detail = await client.get(
        f"/api/v1/mentor/students/{seeded.student_id}/interviews/{process_id}",
        headers=auth(seeded.mentor_id),
    )
    forbidden = await client.get(
        f"/api/v1/mentor/students/{seeded.student_id}/interviews/{process_id}",
        headers=auth(seeded.other_mentor_id),
    )

    assert feedback.status_code == 201
    assert feedback.json()["is_mentor_feedback"] is True
    assert detail.json()["feedback"][0]["comments"][0]["body"].startswith("Разобрать")
    assert forbidden.status_code == 403
