from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from app.interviews.card_automation_models import PersonalReviewItem, QuestionCluster
from app.interviews.card_automation_types import (
    LearningObjectType,
    PersonalReviewStatus,
    QuestionClusterStatus,
)
from app.interviews.models import InterviewCard, InterviewCardFrequency, InterviewDeck
from tests.conftest import SeededData, TestSession, auth


def _cluster(direction_id: UUID, question: str) -> QuestionCluster:
    return QuestionCluster(
        id=uuid4(),
        direction_id=direction_id,
        status=QuestionClusterStatus.NEEDS_REVIEW,
        canonical_question=question,
        normalized_canonical_question=question.casefold(),
        learning_object_type=LearningObjectType.OPEN_TECHNICAL_QUESTION,
    )


@pytest.mark.asyncio
async def test_cluster_endpoints_enforce_role_and_direction_scope(
    client: AsyncClient,
    seeded: SeededData,
) -> None:
    python_cluster = _cluster(seeded.python_track_id, "How does the GIL work?")
    go_cluster = _cluster(seeded.go_track_id, "How does a Go scheduler work?")
    async with TestSession() as session:
        session.add_all([python_cluster, go_cluster])
        await session.commit()

    student_response = await client.get(
        "/api/v1/admin/card-automation/clusters",
        headers=auth(seeded.student_id),
    )
    assert student_response.status_code == 403

    mentor_response = await client.get(
        "/api/v1/mentor/card-automation/clusters",
        headers=auth(seeded.mentor_id),
    )
    assert mentor_response.status_code == 200
    mentor_payload = mentor_response.json()
    assert mentor_payload["total"] == 1
    assert [item["id"] for item in mentor_payload["items"]] == [str(python_cluster.id)]

    hidden_detail = await client.get(
        f"/api/v1/mentor/card-automation/clusters/{go_cluster.id}",
        headers=auth(seeded.mentor_id),
    )
    assert hidden_detail.status_code == 404

    admin_response = await client.get(
        "/api/v1/admin/card-automation/clusters",
        headers=auth(seeded.admin_id),
    )
    assert admin_response.status_code == 200
    assert admin_response.json()["total"] == 2


@pytest.mark.asyncio
async def test_cluster_mutation_requires_idempotency_header(
    client: AsyncClient,
    seeded: SeededData,
) -> None:
    cluster = _cluster(seeded.python_track_id, "What is a descriptor?")
    async with TestSession() as session:
        session.add(cluster)
        await session.commit()

    payload = {"expected_version": 1, "reason": "Important core topic"}
    missing_header = await client.post(
        f"/api/v1/admin/card-automation/clusters/{cluster.id}/mark-important",
        headers=auth(seeded.admin_id),
        json=payload,
    )
    assert missing_header.status_code == 422

    accepted = await client.post(
        f"/api/v1/admin/card-automation/clusters/{cluster.id}/mark-important",
        headers={**auth(seeded.admin_id), "Idempotency-Key": f"test:{cluster.id}"},
        json=payload,
    )
    assert accepted.status_code == 200
    assert accepted.json()["cluster"]["manual_important"] is True


@pytest.mark.asyncio
async def test_admin_can_save_cluster_draft_without_publishing_card(
    client: AsyncClient,
    seeded: SeededData,
) -> None:
    cluster = _cluster(seeded.python_track_id, "What does the GIL do?")
    deck = InterviewDeck(
        id=uuid4(),
        track_id=seeded.python_track_id,
        slug=f"api-existing-topics-{uuid4().hex}",
        title="Existing interview topics",
        position=0,
        is_published=True,
    )
    card = InterviewCard(
        id=uuid4(),
        deck_id=deck.id,
        slug=f"api-python-internals-{uuid4().hex}",
        category="Python internals",
        question_markdown="What is the GIL?",
        answer_markdown="A CPython interpreter lock.",
        frequency=InterviewCardFrequency.OCCASIONAL,
        position=0,
        is_published=True,
    )
    cluster.deck_id = deck.id
    async with TestSession() as session:
        session.add_all([deck, card])
        await session.commit()
        session.add(cluster)
        await session.commit()

    payload = {
        "canonical_question": "How does the CPython GIL work?",
        "topic_name": "Python internals",
        "answer_contract": {
            "short_answer": "The GIL serializes Python bytecode execution.",
            "required_points": ["one executing thread per interpreter"],
            "optional_points": [],
            "common_mistakes": [],
            "unsupported_claims": [],
            "follow_up_questions": [],
            "difficulty": "middle",
            "version_scope": ["CPython"],
            "source_references": [],
            "confidence": 0.9,
        },
        "expected_version": 1,
        "reason": "Administrator reviewed the AI proposal",
    }
    missing_header = await client.patch(
        f"/api/v1/admin/card-automation/clusters/{cluster.id}/draft",
        headers=auth(seeded.admin_id),
        json=payload,
    )
    assert missing_header.status_code == 422

    forbidden = await client.patch(
        f"/api/v1/admin/card-automation/clusters/{cluster.id}/draft",
        headers={**auth(seeded.mentor_id), "Idempotency-Key": "mentor-draft-test"},
        json=payload,
    )
    assert forbidden.status_code == 403

    response = await client.patch(
        f"/api/v1/admin/card-automation/clusters/{cluster.id}/draft",
        headers={**auth(seeded.admin_id), "Idempotency-Key": "admin-draft-test"},
        json=payload,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cluster"]["canonical_question"] == "How does the CPython GIL work?"
    assert body["cluster"]["topic_name"] == "Python internals"
    assert body["cluster"]["version"] == 2
    assert body["created_card_id"] is None

    detail = await client.get(
        f"/api/v1/admin/card-automation/clusters/{cluster.id}",
        headers=auth(seeded.admin_id),
    )
    assert detail.status_code == 200
    assert detail.json()["answer_status"] == "needs_manual_review"
    assert detail.json()["answer_contract"]["difficulty"] == "middle"


@pytest.mark.asyncio
async def test_personal_review_endpoint_never_exposes_another_student_item(
    client: AsyncClient,
    seeded: SeededData,
) -> None:
    item = PersonalReviewItem(
        id=uuid4(),
        student_id=seeded.student_id,
        direction_id=seeded.python_track_id,
        question_text="What is the GIL?",
        status=PersonalReviewStatus.ACTIVE,
        version=1,
    )
    async with TestSession() as session:
        session.add(item)
        await session.commit()

    owner_response = await client.get(
        "/api/v1/students/me/personal-review-items?due_only=false",
        headers=auth(seeded.student_id),
    )
    assert owner_response.status_code == 200
    assert [row["id"] for row in owner_response.json()["items"]] == [str(item.id)]

    mentor_response = await client.get(
        "/api/v1/students/me/personal-review-items?due_only=false",
        headers=auth(seeded.mentor_id),
    )
    assert mentor_response.status_code == 403


@pytest.mark.asyncio
async def test_settings_are_admin_only_and_start_safe(
    client: AsyncClient,
    seeded: SeededData,
) -> None:
    forbidden_response = await client.get(
        "/api/v1/admin/card-automation/settings",
        headers=auth(seeded.mentor_id),
    )
    assert forbidden_response.status_code == 403

    response = await client.get(
        "/api/v1/admin/card-automation/settings",
        headers=auth(seeded.admin_id),
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert {item["direction_slug"] for item in items} == {"python", "go"}
    assert all(item["enabled"] is False for item in items)
    assert all(item["shadow_mode"] is True for item in items)
    assert all(item["global_auto_publish_enabled"] is False for item in items)
    assert all(item["legacy_queue_enabled"] is True for item in items)


@pytest.mark.asyncio
async def test_settings_update_requires_idempotency_header(
    client: AsyncClient,
    seeded: SeededData,
) -> None:
    current_response = await client.get(
        "/api/v1/admin/card-automation/settings",
        headers=auth(seeded.admin_id),
    )
    current = next(
        item
        for item in current_response.json()["items"]
        if item["direction_id"] == str(seeded.python_track_id)
    )
    payload = {
        key: value
        for key, value in current.items()
        if key not in {"direction_slug", "direction_title", "version", "updated_at"}
    }
    payload["expected_version"] = current["version"]
    payload["semantic_similarity_threshold"] = 0.91

    missing_header = await client.put(
        "/api/v1/admin/card-automation/settings",
        headers=auth(seeded.admin_id),
        json=payload,
    )
    assert missing_header.status_code == 422

    updated = await client.put(
        "/api/v1/admin/card-automation/settings",
        headers={
            **auth(seeded.admin_id),
            "Idempotency-Key": "settings-api-update-0001",
        },
        json=payload,
    )
    assert updated.status_code == 200
    assert updated.json()["semantic_similarity_threshold"] == 0.91


@pytest.mark.asyncio
async def test_decision_override_rejects_incompatible_target_with_422(
    client: AsyncClient,
    seeded: SeededData,
) -> None:
    response = await client.post(
        f"/api/v1/admin/card-automation/decisions/{uuid4()}/override",
        headers={
            **auth(seeded.admin_id),
            "Idempotency-Key": "test:incompatible-decision-override",
        },
        json={
            "expected_entity_version": 1,
            "replacement_decision_type": "routed_as_noise",
            "selected_card_id": str(uuid4()),
            "reason": "A noise decision cannot point to a card",
        },
    )

    assert response.status_code == 422
