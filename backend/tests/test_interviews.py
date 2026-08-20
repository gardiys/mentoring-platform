from uuid import UUID

from httpx import AsyncClient

from app.interviews.models import InterviewCard, InterviewCardFrequency
from tests.conftest import SeededData, TestSession, auth


def deck_payload(track_id: str) -> dict:
    return {
        "track_id": track_id,
        "slug": "python-core-interview",
        "title": "Python Core",
        "description": "Подготовка к техническому интервью",
        "position": 0,
        "is_published": True,
        "cards": [
            {
                "slug": "python-metaclass",
                "category": "Продвинутый Python",
                "question_markdown": "Что такое metaclass?",
                "answer_markdown": "Класс, который создаёт классы.",
                "frequency": "occasional",
                "position": 0,
                "is_published": True,
            },
            {
                "slug": "python-gil",
                "category": "Основы Python",
                "question_markdown": "Что такое GIL?",
                "answer_markdown": "Блокировка исполнения Python-байткода в CPython.",
                "frequency": "frequent",
                "position": 1,
                "is_published": True,
            },
        ],
    }


async def create_deck(client: AsyncClient, seeded: SeededData) -> dict:
    response = await client.post(
        "/api/v1/admin/interviews/decks",
        headers=auth(seeded.admin_id),
        json=deck_payload(str(seeded.python_track_id)),
    )
    assert response.status_code == 201
    return response.json()


async def test_only_admin_can_manage_interview_decks(
    client: AsyncClient, seeded: SeededData
) -> None:
    response = await client.get("/api/v1/admin/interviews/decks", headers=auth(seeded.student_id))
    assert response.status_code == 403

    deck = await create_deck(client, seeded)
    assert deck["track_slug"] == "python"
    assert len(deck["cards"]) == 2


async def test_student_sees_only_decks_from_enrolled_tracks(
    client: AsyncClient, seeded: SeededData
) -> None:
    await create_deck(client, seeded)
    go_payload = deck_payload(str(seeded.go_track_id))
    go_payload.update(slug="go-core-interview", title="Go Core")
    go_payload["cards"] = []
    response = await client.post(
        "/api/v1/admin/interviews/decks",
        headers=auth(seeded.admin_id),
        json=go_payload,
    )
    assert response.status_code == 201

    response = await client.get("/api/v1/interviews/decks", headers=auth(seeded.student_id))
    assert response.status_code == 200
    assert [deck["slug"] for deck in response.json()] == ["python-core-interview"]

    response = await client.get(
        "/api/v1/interviews/decks/go-core-interview/session",
        headers=auth(seeded.student_id),
    )
    assert response.status_code == 403

    python_mentor = await client.get("/api/v1/interviews/decks", headers=auth(seeded.mentor_id))
    go_mentor = await client.get("/api/v1/interviews/decks", headers=auth(seeded.other_mentor_id))
    assert [deck["slug"] for deck in python_mentor.json()] == ["python-core-interview"]
    assert [deck["slug"] for deck in go_mentor.json()] == ["go-core-interview"]


async def test_session_prioritizes_frequent_cards_and_tracks_learning(
    client: AsyncClient, seeded: SeededData
) -> None:
    deck = await create_deck(client, seeded)

    response = await client.put(
        "/api/v1/interviews/decks/python-core-interview/topics",
        headers=auth(seeded.student_id),
        json={"categories": ["Основы Python", "Продвинутый Python"]},
    )
    assert response.status_code == 200

    response = await client.get(
        "/api/v1/interviews/decks/python-core-interview/session",
        headers=auth(seeded.student_id),
    )
    assert response.status_code == 200
    session = response.json()
    assert [card["slug"] for card in session["cards"]] == [
        "python-gil",
        "python-metaclass",
    ]
    assert session["deck"]["stats"] == {
        "available_cards": 2,
        "selected_categories": 2,
        "total_categories": 2,
        "total_cards": 2,
        "learned_cards": 0,
        "remaining_cards": 2,
        "due_cards": 0,
        "progress_percent": 0,
    }

    response = await client.get(
        "/api/v1/interviews/decks/python-core-interview/session",
        params={"frequent_only": True},
        headers=auth(seeded.student_id),
    )
    assert response.status_code == 200
    frequent_session = response.json()
    assert [card["slug"] for card in frequent_session["cards"]] == ["python-gil"]
    assert frequent_session["deck"]["stats"]["total_cards"] == 1
    assert frequent_session["deck"]["stats"]["remaining_cards"] == 1

    frequent_card = next(card for card in deck["cards"] if card["slug"] == "python-gil")
    response = await client.post(
        f"/api/v1/interviews/cards/{frequent_card['id']}/reviews",
        headers=auth(seeded.student_id),
        json={"rating": "again"},
    )
    assert response.status_code == 200
    assert response.json()["learned"] is False

    response = await client.post(
        f"/api/v1/interviews/cards/{frequent_card['id']}/reviews",
        headers=auth(seeded.student_id),
        json={"rating": "good"},
    )
    assert response.status_code == 200
    assert response.json()["learned"] is True
    assert response.json()["interval_days"] == 2

    response = await client.post(
        f"/api/v1/interviews/cards/{frequent_card['id']}/reviews",
        headers=auth(seeded.student_id),
        json={"rating": "known"},
    )
    assert response.status_code == 200
    assert response.json()["rating"] == "known"
    assert response.json()["interval_days"] == 30

    response = await client.get("/api/v1/interviews/decks", headers=auth(seeded.student_id))
    stats = response.json()[0]["stats"]
    assert stats["learned_cards"] == 1
    assert stats["remaining_cards"] == 1
    assert stats["progress_percent"] == 50


async def test_student_searches_all_selected_cards(client: AsyncClient, seeded: SeededData) -> None:
    await create_deck(client, seeded)
    await client.put(
        "/api/v1/interviews/decks/python-core-interview/topics",
        headers=auth(seeded.student_id),
        json={"categories": ["Основы Python", "Продвинутый Python"]},
    )

    response = await client.get(
        "/api/v1/interviews/decks/python-core-interview/cards/search",
        params={"query": "создаёт классы"},
        headers=auth(seeded.student_id),
    )
    assert response.status_code == 200
    assert [card["slug"] for card in response.json()] == ["python-metaclass"]

    response = await client.get(
        "/api/v1/interviews/decks/python-core-interview/cards/search",
        params={"query": "что такое", "frequent_only": True},
        headers=auth(seeded.student_id),
    )
    assert response.status_code == 200
    assert [card["slug"] for card in response.json()] == ["python-gil"]


async def test_student_selects_topics_before_study(client: AsyncClient, seeded: SeededData) -> None:
    deck = await create_deck(client, seeded)

    response = await client.get(
        "/api/v1/interviews/decks/python-core-interview/session",
        headers=auth(seeded.student_id),
    )
    assert response.status_code == 200
    assert response.json()["cards"] == []
    assert response.json()["deck"]["stats"]["available_cards"] == 2
    assert response.json()["deck"]["stats"]["selected_categories"] == 0

    response = await client.get(
        "/api/v1/interviews/decks/python-core-interview/topics",
        headers=auth(seeded.student_id),
    )
    assert response.status_code == 200
    assert {topic["name"] for topic in response.json()} == {
        "Основы Python",
        "Продвинутый Python",
    }

    response = await client.put(
        "/api/v1/interviews/decks/python-core-interview/topics",
        headers=auth(seeded.student_id),
        json={"categories": ["Основы Python"]},
    )
    assert response.status_code == 200
    assert [topic["name"] for topic in response.json() if topic["is_selected"]] == ["Основы Python"]

    response = await client.get(
        "/api/v1/interviews/decks/python-core-interview/session",
        headers=auth(seeded.student_id),
    )
    assert [card["slug"] for card in response.json()["cards"]] == ["python-gil"]

    other_card = next(card for card in deck["cards"] if card["slug"] == "python-metaclass")
    response = await client.post(
        f"/api/v1/interviews/cards/{other_card['id']}/reviews",
        headers=auth(seeded.student_id),
        json={"rating": "good"},
    )
    assert response.status_code == 403


async def test_admin_updates_deck_and_removes_card(client: AsyncClient, seeded: SeededData) -> None:
    deck = await create_deck(client, seeded)
    payload = deck_payload(str(seeded.python_track_id))
    payload["title"] = "Python Advanced"
    payload["cards"] = [
        {
            **payload["cards"][1],
            "id": deck["cards"][1]["id"],
            "answer_markdown": "Обновлённый ответ про CPython.",
        }
    ]
    response = await client.put(
        f"/api/v1/admin/interviews/decks/{deck['id']}",
        headers=auth(seeded.admin_id),
        json=payload,
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["title"] == "Python Advanced"
    assert len(updated["cards"]) == 1
    assert updated["cards"][0]["answer_markdown"] == "Обновлённый ответ про CPython."


async def test_admin_card_table_is_paginated_and_updates_one_card(
    client: AsyncClient, seeded: SeededData
) -> None:
    deck = await create_deck(client, seeded)
    deck_id = deck["id"]
    card_id = deck["cards"][0]["id"]

    summaries = await client.get(
        "/api/v1/admin/interviews/decks/summaries",
        headers=auth(seeded.admin_id),
    )
    page = await client.get(
        f"/api/v1/admin/interviews/decks/{deck_id}/cards",
        params={"limit": 1, "offset": 0},
        headers=auth(seeded.admin_id),
    )
    assert summaries.status_code == page.status_code == 200
    assert summaries.json()[0]["card_count"] == 2
    assert "cards" not in summaries.json()[0]
    assert page.json()["total"] == 2
    assert len(page.json()["items"]) == 1
    assert "answer_markdown" not in page.json()["items"][0]

    card = deck["cards"][0]
    payload = {
        key: card[key]
        for key in (
            "id",
            "slug",
            "category",
            "companies",
            "question_markdown",
            "answer_markdown",
            "frequency",
            "position",
            "is_published",
        )
    }
    payload["answer_markdown"] = "Точечно обновлённый ответ."
    updated = await client.put(
        f"/api/v1/admin/interviews/decks/{deck_id}/cards/{card_id}",
        headers=auth(seeded.admin_id),
        json=payload,
    )
    detail = await client.get(
        f"/api/v1/admin/interviews/decks/{deck_id}",
        headers=auth(seeded.admin_id),
    )
    assert updated.status_code == 200
    assert updated.json()["answer_markdown"] == "Точечно обновлённый ответ."
    assert len(detail.json()["cards"]) == 2


async def test_admin_card_frequency_supports_automatic_and_manual_modes(
    client: AsyncClient, seeded: SeededData
) -> None:
    deck = await create_deck(client, seeded)
    assert all(card["frequency_mode"] == "manual" for card in deck["cards"])

    payload = {
        "slug": "python-auto-frequency",
        "category": "Основы Python",
        "companies": None,
        "question_markdown": "## Автоматический вопрос",
        "answer_markdown": "Ответ",
        "frequency": "frequent",
        "frequency_mode": "automatic",
        "position": 2,
        "is_published": True,
    }
    created = await client.post(
        f"/api/v1/admin/interviews/decks/{deck['id']}/cards",
        headers=auth(seeded.admin_id),
        json=payload,
    )
    assert created.status_code == 201, created.text
    automatic = created.json()
    assert automatic["frequency"] == "occasional"
    assert automatic["frequency_override"] is None
    assert automatic["frequency_mode"] == "automatic"
    assert automatic["frequency_threshold"] == 3

    payload.update(
        id=automatic["id"],
        frequency="frequent",
        frequency_mode="manual",
    )
    manually_updated = await client.put(
        f"/api/v1/admin/interviews/decks/{deck['id']}/cards/{automatic['id']}",
        headers=auth(seeded.admin_id),
        json=payload,
    )
    assert manually_updated.status_code == 200, manually_updated.text
    manual = manually_updated.json()
    assert manual["frequency"] == "frequent"
    assert manual["frequency_override"] == "frequent"
    assert manual["frequency_mode"] == "manual"

    payload.update(frequency_mode="automatic")
    recalculated = await client.put(
        f"/api/v1/admin/interviews/decks/{deck['id']}/cards/{automatic['id']}",
        headers=auth(seeded.admin_id),
        json=payload,
    )
    assert recalculated.status_code == 200, recalculated.text
    assert recalculated.json()["frequency"] == "occasional"
    assert recalculated.json()["frequency_override"] is None

    async with TestSession() as session:
        card = await session.get(InterviewCard, UUID(automatic["id"]))
        assert card is not None
        card.asked_count = 3
        # Simulate a materialized value that became stale after a threshold change.
        card.frequency = InterviewCardFrequency.OCCASIONAL
        await session.commit()

    dynamically_recalculated = await client.get(
        f"/api/v1/admin/interviews/decks/{deck['id']}/cards/{automatic['id']}",
        headers=auth(seeded.admin_id),
    )
    assert dynamically_recalculated.status_code == 200
    assert dynamically_recalculated.json()["frequency"] == "frequent"

    summaries = await client.get(
        "/api/v1/admin/interviews/decks/summaries",
        headers=auth(seeded.admin_id),
    )
    assert summaries.status_code == 200
    summary = next(item for item in summaries.json() if item["id"] == deck["id"])
    assert summary["frequent_count"] == 2

    topics = await client.get(
        "/api/v1/interviews/decks/python-core-interview/topics",
        headers=auth(seeded.student_id),
    )
    assert topics.status_code == 200
    basics = next(item for item in topics.json() if item["name"] == "Основы Python")
    assert basics["frequent_cards"] == 2
