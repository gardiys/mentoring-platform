from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.interviews import card_frequency
from app.interviews.intelligence_models import (
    IntelligenceDifficulty,
    IntelligenceInterview,
    IntelligenceInterviewType,
    IntelligenceProcessingStatus,
    IntelligenceQuestion,
    IntelligenceQuestionKind,
)
from app.interviews.models import (
    Company,
    InterviewCard,
    InterviewCardFrequency,
    InterviewCardOccurrence,
    InterviewDeck,
    InterviewProcess,
    InterviewProcessStage,
    InterviewStageType,
)
from tests.conftest import SeededData, TestSession, auth


@dataclass(frozen=True)
class ModerationScenario:
    card_id: UUID
    other_card_id: UUID
    interview_ids: tuple[UUID, ...]
    question_ids: tuple[UUID, ...]
    company_name: str


async def seed_moderation_scenario(
    seeded: SeededData,
    question_texts: tuple[str, ...],
    *,
    card_question: str = ("Чем ты пользовался: Kafka или RabbitMQ? Знаешь, в чём разница?"),
) -> ModerationScenario:
    async with TestSession() as session:
        company = Company(
            name="Nexara",
            normalized_name="nexara",
            transliterated_name="nexara",
        )
        deck = InterviewDeck(
            track_id=seeded.python_track_id,
            slug="python-semantic-moderation",
            title="Python backend",
            position=0,
            is_published=True,
        )
        session.add_all([company, deck])
        await session.flush()

        card = InterviewCard(
            deck_id=deck.id,
            slug="kafka-vs-rabbitmq",
            category="Брокеры сообщений",
            question_markdown=card_question,
            answer_markdown="Kafka — распределённый журнал, RabbitMQ — брокер очередей.",
            frequency=InterviewCardFrequency.OCCASIONAL,
            frequency_override=None,
            position=0,
            is_published=True,
            asked_count=0,
        )
        other_card = InterviewCard(
            deck_id=deck.id,
            slug="kafka-delivery",
            category="Брокеры сообщений",
            question_markdown="Какие гарантии доставки поддерживает Kafka?",
            answer_markdown="At most once, at least once и exactly once.",
            frequency=InterviewCardFrequency.OCCASIONAL,
            frequency_override=None,
            position=1,
            is_published=True,
            asked_count=0,
        )
        process = InterviewProcess(
            user_id=seeded.student_id,
            track_id=seeded.python_track_id,
            company_id=company.id,
            company_name=company.name,
        )
        session.add_all([card, other_card, process])
        await session.flush()

        interview_ids: list[UUID] = []
        question_ids: list[UUID] = []
        scheduled_at = datetime(2026, 8, 5, 12, tzinfo=UTC)
        for index, question_text in enumerate(question_texts):
            stage = InterviewProcessStage(
                process_id=process.id,
                stage_type=InterviewStageType.TECHNICAL_INTERVIEW,
                scheduled_at=scheduled_at + timedelta(days=index),
            )
            session.add(stage)
            await session.flush()
            interview = IntelligenceInterview(
                stage_id=stage.id,
                student_id=seeded.student_id,
                interview_type=IntelligenceInterviewType.TECHNICAL,
                processing_status=IntelligenceProcessingStatus.READY,
            )
            session.add(interview)
            await session.flush()
            question = IntelligenceQuestion(
                interview_id=interview.id,
                direction_id=seeded.python_track_id,
                sequence_number=0,
                question_text=question_text,
                question_start_ms=1_000,
                question_end_ms=2_000,
                answer_start_ms=None,
                answer_end_ms=None,
                question_utterance_ids=[],
                answer_utterance_ids=[],
                category="Брокеры сообщений",
                question_kind=IntelligenceQuestionKind.TECHNICAL,
                difficulty=IntelligenceDifficulty.MIDDLE,
                confidence=0.95,
            )
            session.add(question)
            await session.flush()
            interview_ids.append(interview.id)
            question_ids.append(question.id)

        await session.commit()
        return ModerationScenario(
            card_id=card.id,
            other_card_id=other_card.id,
            interview_ids=tuple(interview_ids),
            question_ids=tuple(question_ids),
            company_name=company.name,
        )


@pytest.mark.asyncio
async def test_semantic_candidate_requires_confirmation_and_counts_one_interview_once(
    client: AsyncClient,
    seeded: SeededData,
) -> None:
    # Both extracted questions belong to one interview, as can happen when AI
    # splits one discussion into two equivalent questions.
    scenario = await seed_moderation_scenario(
        seeded,
        ("Расскажи, в чем отличия кафки и кролика",),
    )
    async with TestSession() as session:
        interview = await session.get(IntelligenceInterview, scenario.interview_ids[0])
        assert interview is not None
        second_question = IntelligenceQuestion(
            interview_id=interview.id,
            direction_id=seeded.python_track_id,
            sequence_number=1,
            question_text="Сравни Apache Kafka и RabbitMQ",
            question_start_ms=3_000,
            question_end_ms=4_000,
            answer_start_ms=None,
            answer_end_ms=None,
            question_utterance_ids=[],
            answer_utterance_ids=[],
            category="Брокеры сообщений",
            question_kind=IntelligenceQuestionKind.TECHNICAL,
            difficulty=IntelligenceDifficulty.MIDDLE,
            confidence=0.93,
        )
        session.add(second_question)
        await session.commit()
        second_question_id = second_question.id

    detail = await client.get(
        f"/api/v1/admin/interviews/question-moderation/{scenario.question_ids[0]}",
        headers=auth(seeded.admin_id),
    )
    assert detail.status_code == 200, detail.text
    candidates = detail.json()["card_candidates"]
    assert candidates
    assert candidates[0]["id"] == str(scenario.card_id)
    assert candidates[0]["match_type"] == "similar"
    assert candidates[0]["matched_source"] == "card"
    assert candidates[0]["matched_text"] == (
        "Чем ты пользовался: Kafka или RabbitMQ? Знаешь, в чём разница?"
    )
    assert candidates[0]["similarity"] >= 0.9

    missing_decision = await client.post(
        (
            f"/api/v1/mentor/interviews/{scenario.interview_ids[0]}"
            f"/questions/{scenario.question_ids[0]}/moderation"
        ),
        headers=auth(seeded.admin_id),
        json={"action": "approve"},
    )
    assert missing_decision.status_code == 422, missing_decision.text
    assert missing_decision.json()["detail"]["code"] == "interview_card_destination_required"

    first_approval = await client.post(
        (
            f"/api/v1/mentor/interviews/{scenario.interview_ids[0]}"
            f"/questions/{scenario.question_ids[0]}/moderation"
        ),
        headers=auth(seeded.admin_id),
        json={"action": "approve", "target_card_id": str(scenario.card_id)},
    )
    assert first_approval.status_code == 200, first_approval.text

    second_approval = await client.post(
        (
            f"/api/v1/mentor/interviews/{scenario.interview_ids[0]}"
            f"/questions/{second_question_id}/moderation"
        ),
        headers=auth(seeded.admin_id),
        json={"action": "approve", "target_card_id": str(scenario.card_id)},
    )
    assert second_approval.status_code == 200, second_approval.text

    async with TestSession() as session:
        card = await session.get(InterviewCard, scenario.card_id)
        first_question = await session.get(IntelligenceQuestion, scenario.question_ids[0])
        second_question = await session.get(IntelligenceQuestion, second_question_id)
        occurrences = list(
            await session.scalars(
                select(InterviewCardOccurrence).where(
                    InterviewCardOccurrence.card_id == scenario.card_id
                )
            )
        )
        assert card is not None
        assert first_question is not None
        assert second_question is not None
        assert card.asked_count == 1
        assert card.companies == scenario.company_name
        assert first_question.published_card_id == scenario.card_id
        assert second_question.published_card_id == scenario.card_id
        assert len(occurrences) == 1
        assert occurrences[0].interview_id == scenario.interview_ids[0]
        assert occurrences[0].company_name == scenario.company_name

    relink = await client.post(
        (
            f"/api/v1/mentor/interviews/{scenario.interview_ids[0]}"
            f"/questions/{scenario.question_ids[0]}/moderation"
        ),
        headers=auth(seeded.admin_id),
        json={"action": "approve", "target_card_id": str(scenario.other_card_id)},
    )
    assert relink.status_code == 409, relink.text
    assert relink.json()["detail"]["code"] == "interview_question_already_published"


@pytest.mark.asyncio
async def test_automatic_frequency_uses_distinct_interviews(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(card_frequency, "frequent_occurrence_threshold", lambda: 3)
    scenario = await seed_moderation_scenario(
        seeded,
        (
            "Kafka или RabbitMQ: что выбрать?",
            "В чем разница RabbitMQ и Kafka?",
            "Сравни кафку с кроликом",
        ),
    )

    for index, (interview_id, question_id) in enumerate(
        zip(scenario.interview_ids, scenario.question_ids, strict=True),
        start=1,
    ):
        response = await client.post(
            (f"/api/v1/mentor/interviews/{interview_id}/questions/{question_id}/moderation"),
            headers=auth(seeded.admin_id),
            json={"action": "approve", "target_card_id": str(scenario.card_id)},
        )
        assert response.status_code == 200, response.text
        async with TestSession() as session:
            card = await session.get(InterviewCard, scenario.card_id)
            assert card is not None
            assert card.asked_count == index
            assert card.frequency is (
                InterviewCardFrequency.FREQUENT if index >= 3 else InterviewCardFrequency.OCCASIONAL
            )

    async with TestSession() as session:
        occurrence_count = int(
            await session.scalar(
                select(func.count(InterviewCardOccurrence.id)).where(
                    InterviewCardOccurrence.card_id == scenario.card_id
                )
            )
            or 0
        )
        assert occurrence_count == 3


@pytest.mark.asyncio
async def test_corrected_exact_question_cannot_create_duplicate_card(
    client: AsyncClient,
    seeded: SeededData,
) -> None:
    canonical_question = "Чем ты пользовался: Kafka или RabbitMQ? Знаешь, в чём разница?"
    scenario = await seed_moderation_scenario(
        seeded,
        ("Как выбирать инфраструктурный инструмент?",),
        card_question=canonical_question,
    )

    response = await client.post(
        (
            f"/api/v1/mentor/interviews/{scenario.interview_ids[0]}"
            f"/questions/{scenario.question_ids[0]}/moderation"
        ),
        headers=auth(seeded.admin_id),
        json={
            "action": "approve",
            "question_markdown": canonical_question,
            "answer_markdown": "Проверенный ответ",
            "create_new_card": True,
            "create_category": True,
            "category": "Новая тема",
        },
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "interview_card_exact_match_exists"


@pytest.mark.asyncio
async def test_exact_confirmed_alias_still_requires_explicit_admin_choice(
    client: AsyncClient,
    seeded: SeededData,
) -> None:
    alias_text = "Расскажи, в чем отличия кафки и кролика"
    scenario = await seed_moderation_scenario(seeded, (alias_text, alias_text))

    first_approval = await client.post(
        (
            f"/api/v1/mentor/interviews/{scenario.interview_ids[0]}"
            f"/questions/{scenario.question_ids[0]}/moderation"
        ),
        headers=auth(seeded.admin_id),
        json={"action": "approve", "target_card_id": str(scenario.card_id)},
    )
    assert first_approval.status_code == 200, first_approval.text

    detail = await client.get(
        f"/api/v1/admin/interviews/question-moderation/{scenario.question_ids[1]}",
        headers=auth(seeded.admin_id),
    )
    assert detail.status_code == 200, detail.text
    candidate = detail.json()["card_candidates"][0]
    assert candidate["id"] == str(scenario.card_id)
    assert candidate["match_type"] == "exact"
    assert candidate["matched_source"] == "approved_alias"
    assert candidate["matched_text"] == alias_text

    missing_decision = await client.post(
        (
            f"/api/v1/mentor/interviews/{scenario.interview_ids[1]}"
            f"/questions/{scenario.question_ids[1]}/moderation"
        ),
        headers=auth(seeded.admin_id),
        json={"action": "approve"},
    )
    assert missing_decision.status_code == 422, missing_decision.text
    assert missing_decision.json()["detail"]["code"] == ("interview_card_destination_required")

    explicit_approval = await client.post(
        (
            f"/api/v1/mentor/interviews/{scenario.interview_ids[1]}"
            f"/questions/{scenario.question_ids[1]}/moderation"
        ),
        headers=auth(seeded.admin_id),
        json={"action": "approve", "target_card_id": str(scenario.card_id)},
    )
    assert explicit_approval.status_code == 200, explicit_approval.text

    repeated_old_client_payload = await client.post(
        (
            f"/api/v1/mentor/interviews/{scenario.interview_ids[1]}"
            f"/questions/{scenario.question_ids[1]}/moderation"
        ),
        headers=auth(seeded.admin_id),
        json={"action": "approve"},
    )
    assert repeated_old_client_payload.status_code == 200, repeated_old_client_payload.text

    async with TestSession() as session:
        occurrence_count = int(
            await session.scalar(
                select(func.count(InterviewCardOccurrence.id)).where(
                    InterviewCardOccurrence.card_id == scenario.card_id
                )
            )
            or 0
        )
    assert occurrence_count == 2


@pytest.mark.asyncio
async def test_new_card_reuses_draft_category_and_follows_draft_position(
    client: AsyncClient,
    seeded: SeededData,
) -> None:
    scenario = await seed_moderation_scenario(
        seeded,
        ("Что такое дескриптор файлов?",),
    )
    async with TestSession() as session:
        published_card = await session.get(InterviewCard, scenario.card_id)
        assert published_card is not None
        draft_card = InterviewCard(
            deck_id=published_card.deck_id,
            slug="draft-linux-file-descriptor",
            category="Linux",
            question_markdown="Черновик вопроса",
            answer_markdown="Черновик ответа",
            frequency=InterviewCardFrequency.OCCASIONAL,
            frequency_override=None,
            position=25,
            is_published=False,
            asked_count=0,
        )
        session.add(draft_card)
        await session.commit()
        deck_id = published_card.deck_id

    response = await client.post(
        (
            f"/api/v1/mentor/interviews/{scenario.interview_ids[0]}"
            f"/questions/{scenario.question_ids[0]}/moderation"
        ),
        headers=auth(seeded.admin_id),
        json={
            "action": "approve",
            "question_markdown": "Что такое дескриптор файлов?",
            "answer_markdown": "Числовой идентификатор открытого ресурса.",
            "deck_id": str(deck_id),
            "category": "linux",
            "create_category": False,
            "create_new_card": True,
        },
    )
    assert response.status_code == 200, response.text

    async with TestSession() as session:
        question = await session.get(IntelligenceQuestion, scenario.question_ids[0])
        assert question is not None
        assert question.published_card_id is not None
        card = await session.get(InterviewCard, question.published_card_id)
        assert card is not None
        assert card.category == "Linux"
        assert card.position == 26
