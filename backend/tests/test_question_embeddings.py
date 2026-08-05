from __future__ import annotations

import asyncio
import hashlib

from app.interviews.intelligence_ai import AIEmbeddingResult, FakeInterviewAIProvider
from app.interviews.intelligence_models import IntelligenceQuestion
from app.interviews.models import InterviewCard, InterviewCardFrequency, InterviewDeck
from app.interviews.question_embeddings import (
    EMBEDDING_MAX_INPUT_CHARS,
    embedding_input_text,
    embedding_source_hash,
    refresh_embedding_rows,
)
from tests.conftest import SeededData, TestSession


class BlockingEmbeddingProvider(FakeInterviewAIProvider):
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def embed(self, texts: list[str]) -> AIEmbeddingResult:
        self.started.set()
        await self.release.wait()
        return await super().embed(texts)


def test_embedding_source_hash_tracks_exact_provider_input() -> None:
    source = f"  {'x' * (EMBEDDING_MAX_INPUT_CHARS + 50)}  "
    provider_input = embedding_input_text(source)

    assert provider_input == "x" * EMBEDDING_MAX_INPUT_CHARS
    assert (
        embedding_source_hash(source) == hashlib.sha256(provider_input.encode("utf-8")).hexdigest()
    )
    assert embedding_source_hash("   ") == hashlib.sha256("Вопрос без текста".encode()).hexdigest()


async def test_refresh_embedding_rows_caches_stale_vectors_and_skips_current_ones() -> None:
    provider = FakeInterviewAIProvider()
    current_vector = [0.0] * provider.embedding_dimensions
    current_vector[0] = 1.0
    current_card = InterviewCard(
        question_markdown="Текущий вопрос",
        answer_markdown="Ответ",
        category="python",
        frequency=InterviewCardFrequency.OCCASIONAL,
        question_embedding=current_vector,
        question_embedding_model=provider.embedding_model,
        question_embedding_dimensions=provider.embedding_dimensions,
        question_embedding_source_hash=embedding_source_hash("Текущий вопрос"),
    )
    stale_card = InterviewCard(
        question_markdown="Как работает GIL?",
        answer_markdown="Ответ",
        category="python",
        frequency=InterviewCardFrequency.OCCASIONAL,
        question_embedding=[1.0],
        question_embedding_model="old-model",
        question_embedding_dimensions=1,
        question_embedding_source_hash=embedding_source_hash("Как работает GIL?"),
    )
    malformed_card = InterviewCard(
        question_markdown="Повреждённый вектор",
        answer_markdown="Ответ",
        category="python",
        frequency=InterviewCardFrequency.OCCASIONAL,
        question_embedding=[1.0],
        question_embedding_model=provider.embedding_model,
        question_embedding_dimensions=provider.embedding_dimensions,
        question_embedding_source_hash=embedding_source_hash("Повреждённый вектор"),
    )
    stale_hash_card = InterviewCard(
        question_markdown="Что такое context manager?",
        answer_markdown="Ответ",
        category="python",
        frequency=InterviewCardFrequency.OCCASIONAL,
        question_embedding=current_vector.copy(),
        question_embedding_model=provider.embedding_model,
        question_embedding_dimensions=provider.embedding_dimensions,
        question_embedding_source_hash=embedding_source_hash("Старая формулировка"),
    )
    new_question = IntelligenceQuestion(question_text="Что такое event loop?")

    result = await refresh_embedding_rows(
        provider,
        [current_card, stale_card, malformed_card, stale_hash_card, new_question],
        batch_size=1,
    )

    assert result.refreshed == 4
    assert len(result.usages) == 4
    assert current_card.question_embedding is current_vector
    assert current_card.question_embedding_source_hash == embedding_source_hash(
        current_card.question_markdown
    )
    assert stale_card.question_embedding_model == provider.embedding_model
    assert stale_card.question_embedding_dimensions == provider.embedding_dimensions
    assert stale_card.question_embedding_source_hash == embedding_source_hash(
        stale_card.question_markdown
    )
    assert len(stale_card.question_embedding or []) == provider.embedding_dimensions
    assert len(malformed_card.question_embedding or []) == provider.embedding_dimensions
    assert malformed_card.question_embedding_source_hash == embedding_source_hash(
        malformed_card.question_markdown
    )
    assert stale_hash_card.question_embedding_source_hash == embedding_source_hash(
        stale_hash_card.question_markdown
    )
    assert new_question.question_embedding_model == provider.embedding_model
    assert new_question.question_embedding_dimensions == provider.embedding_dimensions
    assert new_question.question_embedding_source_hash == embedding_source_hash(
        new_question.question_text
    )
    assert len(new_question.question_embedding or []) == provider.embedding_dimensions


async def test_refresh_embedding_rows_does_not_call_provider_when_everything_is_current() -> None:
    provider = FakeInterviewAIProvider()
    vector = [0.0] * provider.embedding_dimensions
    vector[0] = 1.0
    card = InterviewCard(
        question_markdown="Текущий вопрос",
        answer_markdown="Ответ",
        category="go",
        frequency=InterviewCardFrequency.FREQUENT,
        question_embedding=vector,
        question_embedding_model=provider.embedding_model,
        question_embedding_dimensions=provider.embedding_dimensions,
        question_embedding_source_hash=embedding_source_hash("Текущий вопрос"),
    )

    result = await refresh_embedding_rows(provider, [card])

    assert result.refreshed == 0
    assert result.usages == []
    assert card.question_embedding is vector


async def test_refresh_embedding_rows_replaces_vector_with_invalid_source_hash() -> None:
    provider = FakeInterviewAIProvider()
    old_vector = [0.0] * provider.embedding_dimensions
    old_vector[0] = 1.0
    card = InterviewCard(
        question_markdown="Чем Kafka отличается от RabbitMQ?",
        answer_markdown="Ответ",
        category="architecture",
        frequency=InterviewCardFrequency.FREQUENT,
        question_embedding=old_vector,
        question_embedding_model=provider.embedding_model,
        question_embedding_dimensions=provider.embedding_dimensions,
        question_embedding_source_hash="0" * 64,
    )

    result = await refresh_embedding_rows(provider, [card])

    assert result.refreshed == 1
    assert len(result.usages) == 1
    assert card.question_embedding is not old_vector
    assert card.question_embedding_source_hash == embedding_source_hash(card.question_markdown)


async def test_refresh_embedding_rows_does_not_store_vector_for_concurrently_edited_text(
    seeded: SeededData,
) -> None:
    async with TestSession() as session:
        deck = InterviewDeck(
            track_id=seeded.python_track_id,
            slug="embedding-race",
            title="Embedding race",
            position=0,
            is_published=True,
        )
        session.add(deck)
        await session.flush()
        card = InterviewCard(
            deck_id=deck.id,
            slug="embedding-race-card",
            question_markdown="Старая формулировка",
            answer_markdown="Ответ",
            category="python",
            frequency=InterviewCardFrequency.OCCASIONAL,
            position=0,
            is_published=True,
        )
        session.add(card)
        await session.commit()
        card_id = card.id

    provider = BlockingEmbeddingProvider()
    async with TestSession() as worker_session:
        worker_card = await worker_session.get(InterviewCard, card_id)
        assert worker_card is not None
        refresh_task = asyncio.create_task(
            refresh_embedding_rows(provider, [worker_card], session=worker_session)
        )
        await provider.started.wait()

        async with TestSession() as admin_session:
            edited_card = await admin_session.get(InterviewCard, card_id)
            assert edited_card is not None
            edited_card.question_markdown = "Новая формулировка"
            edited_card.question_embedding = None
            edited_card.question_embedding_model = None
            edited_card.question_embedding_dimensions = None
            edited_card.question_embedding_source_hash = None
            await admin_session.commit()

        provider.release.set()
        result = await refresh_task
        await worker_session.commit()

    assert result.refreshed == 0
    assert len(result.usages) == 1
    async with TestSession() as session:
        saved_card = await session.get(InterviewCard, card_id)
        assert saved_card is not None
        assert saved_card.question_markdown == "Новая формулировка"
        assert saved_card.question_embedding is None
        assert saved_card.question_embedding_source_hash is None
