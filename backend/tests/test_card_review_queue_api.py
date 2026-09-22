from unittest.mock import AsyncMock

from app.interviews import card_automation_service as service
from app.interviews.card_automation_models import QuestionCluster
from app.interviews.card_automation_types import QuestionClusterStatus
from tests.conftest import TestSession, auth
from tests.test_card_automation_api import _cluster


async def test_review_queue_is_lightweight_complete_and_preserves_order(
    client, seeded, monkeypatch
):
    summaries = AsyncMock(side_effect=AssertionError("Queue must not load card details"))
    monkeypatch.setattr(service, "_cluster_summaries", summaries)
    rows = [_cluster(seeded.python_track_id, f"Question {i}") for i in range(125)]
    for i, row in enumerate(rows):
        row.priority_score = i
        row.topic_name = "Python"
    other = _cluster(seeded.python_track_id, "Other topic")
    other.topic_name = "Concurrency"
    async with TestSession() as session:
        session.add_all([*rows, other])
        await session.commit()
    response = await client.get(
        "/api/v1/admin/card-automation/clusters/review-queue",
        params={"needs_action_only": "true", "topic_name": "Python", "limit": 20, "offset": 100},
        headers=auth(seeded.admin_id),
    )
    assert response.status_code == 200, response.text
    assert response.json() == [str(row.id) for row in reversed(rows)]
    summaries.assert_not_called()


async def test_review_queue_enforces_scope_and_filters(client, seeded):
    python = _cluster(seeded.python_track_id, "Python question")
    go = _cluster(seeded.go_track_id, "Go question")
    closed = _cluster(seeded.python_track_id, "Closed question")
    closed.status = QuestionClusterStatus.IGNORED
    async with TestSession() as session:
        session.add_all([python, go, closed])
        await session.commit()
    path = "/api/v1/mentor/card-automation/clusters/review-queue"
    response = await client.get(
        path, params={"needs_action_only": "true"}, headers=auth(seeded.mentor_id)
    )
    assert response.status_code == 200, response.text
    assert response.json() == [str(python.id)]
    forbidden_direction = await client.get(
        path, params={"direction_id": str(seeded.go_track_id)}, headers=auth(seeded.mentor_id)
    )
    assert forbidden_direction.status_code == 404
    forbidden_role = await client.get(path, headers=auth(seeded.student_id))
    assert forbidden_role.status_code == 403
    filtered = await client.get(
        path, params={"statuses": "ignored"}, headers=auth(seeded.mentor_id)
    )
    assert filtered.json() == [str(closed.id)]


async def test_review_queue_can_refresh_after_a_decision_and_validates_ranges(client, seeded):
    row = _cluster(seeded.python_track_id, "Pending")
    async with TestSession() as session:
        session.add(row)
        await session.commit()
    path = "/api/v1/admin/card-automation/clusters/review-queue"
    response = await client.get(
        path, params={"needs_action_only": "true"}, headers=auth(seeded.admin_id)
    )
    assert response.json() == [str(row.id)]
    async with TestSession() as session:
        (await session.get(QuestionCluster, row.id)).status = QuestionClusterStatus.IGNORED
        await session.commit()
    response = await client.get(
        path, params={"needs_action_only": "true"}, headers=auth(seeded.admin_id)
    )
    assert response.json() == []
    invalid = await client.get(
        path, params={"min_confidence": 0.9, "max_confidence": 0.1}, headers=auth(seeded.admin_id)
    )
    assert invalid.status_code == 422
