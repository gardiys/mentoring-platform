from uuid import uuid4

from sqlalchemy import select

from app.interviews import card_automation_router
from app.interviews.models import InterviewCard, InterviewCardDuplicateReport, InterviewDeck
from tests.conftest import TestSession, auth


async def create_cards(seeded):
    deck = InterviewDeck(
        id=uuid4(),
        track_id=seeded.python_track_id,
        slug=f"reports-{uuid4()}",
        title="Вопросы",
        is_published=True,
    )
    cards = [
        InterviewCard(
            id=uuid4(),
            deck_id=deck.id,
            slug=f"card-{uuid4()}",
            category="HR",
            question_markdown=text,
            answer_markdown="Ответ",
            frequency="occasional",
            is_published=True,
        )
        for text in ["Почему решил поменять работу?", "Почему вышел на рынок?"]
    ]
    async with TestSession() as session:
        session.add(deck)
        session.add_all(cards)
        await session.commit()
    return cards


async def test_report_retry_permissions_search_and_merge(client, seeded, monkeypatch):
    cards = await create_cards(seeded)
    card, target = cards
    path = f"/api/v1/interviews/cards/{card.id}/duplicate-report"
    first = await client.post(path, headers=auth(seeded.student_id))
    assert first.status_code == 200, first.text
    second = await client.post(path, headers=auth(seeded.student_id))
    assert second.json() == first.json()
    base = "/api/v1/admin/card-automation"
    assert (
        await client.get(base + "/duplicate-reports", headers=auth(seeded.student_id))
    ).status_code == 403
    listing = await client.get(base + "/duplicate-reports", headers=auth(seeded.admin_id))
    assert listing.status_code == 200, listing.text
    item = listing.json()["items"][0]
    assert item["reports_count"] == 1
    targets = await client.get(
        base + f"/duplicate-reports/{card.id}/targets",
        params={"query": "рынок"},
        headers=auth(seeded.admin_id),
    )
    assert targets.status_code == 200, targets.text
    assert [row["id"] for row in targets.json()] == [str(target.id)]

    async def refresh(**kwargs):
        return True

    monkeypatch.setattr(card_automation_router, "request_interview_card_duplicate_refresh", refresh)
    result = await client.post(
        base + "/duplicates/merge",
        headers={**auth(seeded.admin_id), "Idempotency-Key": str(uuid4())},
        json={
            "left_card_id": str(card.id),
            "right_card_id": str(target.id),
            "primary_card_id": str(target.id),
            "expected_left_updated_at": item["card"]["updated_at"],
            "expected_right_updated_at": targets.json()[0]["updated_at"],
            "reason": "Сообщение о дубле проверено",
        },
    )
    assert result.status_code == 200, result.text
    listing = await client.get(base + "/duplicate-reports", headers=auth(seeded.admin_id))
    assert listing.json()["total"] == 0
    async with TestSession() as session:
        report = await session.scalar(select(InterviewCardDuplicateReport))
        assert report.status == "merged" and report.primary_card_id == target.id
        assert not (await session.get(InterviewCard, card.id)).is_published


async def test_reports_cannot_access_hidden_cards_and_admin_can_dismiss(client, seeded):
    card, _ = await create_cards(seeded)
    path = f"/api/v1/interviews/cards/{card.id}/duplicate-report"
    async with TestSession() as session:
        stored = await session.get(InterviewCard, card.id)
        stored.is_published = False
        await session.commit()
    assert (await client.post(path, headers=auth(seeded.student_id))).status_code == 404
    async with TestSession() as session:
        stored = await session.get(InterviewCard, card.id)
        stored.is_published = True
        deck = await session.get(InterviewDeck, stored.deck_id)
        deck.track_id = seeded.go_track_id
        await session.commit()
    assert (await client.post(path, headers=auth(seeded.student_id))).status_code == 403
    async with TestSession() as session:
        deck = await session.get(InterviewDeck, card.deck_id)
        deck.track_id = seeded.python_track_id
        await session.commit()
    assert (await client.post(path, headers=auth(seeded.student_id))).status_code == 200
    result = await client.post(
        f"/api/v1/admin/card-automation/duplicate-reports/{card.id}/dismiss",
        headers=auth(seeded.admin_id),
    )
    assert result.status_code == 204, result.text
    retry = await client.post(path, headers=auth(seeded.student_id))
    assert retry.json()["status"] == "dismissed"
