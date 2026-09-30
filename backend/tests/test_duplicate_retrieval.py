import json
import zlib
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.interviews.card_automation_service import _rank_duplicate_pairs
from app.interviews.card_duplicate_cache import (
    InterviewCardDuplicateSnapshot,
    _decode_snapshot,
    _encode_snapshot,
)
from app.interviews.duplicate_semantics import semantic_duplicate_pairs
from app.interviews.question_embeddings import embedding_source_hash


@pytest.fixture(autouse=True)
def reset_database():
    yield


def context(text, vector, track_id, model="test"):
    return SimpleNamespace(
        card=SimpleNamespace(
            id=uuid4(),
            question_markdown=text,
            answer_markdown="Ответ " * 1000,
            question_embedding=vector,
            question_embedding_model=model,
            question_embedding_dimensions=len(vector),
            question_embedding_source_hash=embedding_source_hash(text),
            asked_count=1,
            category="HR",
            subcategory=None,
            companies=None,
            frequency="occasional",
            updated_at=datetime.now(UTC),
        ),
        track=SimpleNamespace(id=track_id, slug="python", title="Python"),
        deck=SimpleNamespace(id=uuid4(), title="Вопросы"),
        aliases=(),
    )


def test_semantic_paraphrases_reach_moderation_without_common_words():
    track = uuid4()
    # Synthetic vectors isolate retrieval from the paid embedding provider.
    left = context("Почему решил поменять работу?", [1, 0, 0], track)
    right = context("Почему вышел на рынок?", [0.98, 0.1, 0], track)
    unrelated = context("Как устроен сборщик мусора?", [0, 0, 1], track)
    result = _rank_duplicate_pairs([left, right, unrelated], set(), 0.72)
    assert len(result) == 1
    assert {result[0].left.id, result[0].right.id} == {left.card.id, right.card.id}
    assert result[0].matched_source == "semantic"
    assert (
        _rank_duplicate_pairs(
            [left, right], {tuple(sorted((left.card.id, right.card.id), key=str))}, 0.72
        )
        == []
    )


@pytest.mark.parametrize("invalid", ["stale", "model", "track", "zero", "nan"])
def test_incompatible_or_invalid_vectors_are_never_compared(invalid):
    track = uuid4()
    left = context("alpha", [1, 0], track)
    right = context("beta", [1, 0], track)
    if invalid == "stale":
        right.card.question_embedding_source_hash = "old"
    if invalid == "model":
        right.card.question_embedding_model = "other"
    if invalid == "track":
        right.track.id = uuid4()
    if invalid == "zero":
        right.card.question_embedding = [0, 0]
    if invalid == "nan":
        right.card.question_embedding = [float("nan"), 0]
    assert semantic_duplicate_pairs([left, right]) == {}


def test_compact_snapshot_stores_answers_once_and_preserves_shared_card_objects():
    track = uuid4()
    contexts = [context(f"Вопрос {index}", [1, 0], track) for index in range(30)]
    snapshot = InterviewCardDuplicateSnapshot(
        generated_at=datetime.now(UTC), items=_rank_duplicate_pairs(contexts, set(), 0.72)
    )
    payload = _encode_snapshot(snapshot)
    wire = json.loads(zlib.decompress(payload))
    assert len(wire["cards"]) == 30
    assert len(wire["pairs"]) > 30
    assert len(zlib.decompress(payload)) < len(snapshot.model_dump_json().encode()) / 4
    restored = _decode_snapshot(payload)
    assert restored == snapshot
    first = restored.items[0].left
    instances = [
        card for pair in restored.items for card in (pair.left, pair.right) if card.id == first.id
    ]
    assert len(instances) > 1 and all(card is first for card in instances)


async def test_failed_snapshot_shows_error_without_requeue_loop(monkeypatch):
    from unittest.mock import AsyncMock

    from app.interviews import card_automation_service as service

    monkeypatch.setattr(service, "read_duplicate_snapshot", AsyncMock(return_value=None))
    monkeypatch.setattr(
        service, "duplicate_refresh_error", AsyncMock(return_value="Расчёт прерван")
    )
    enqueue = AsyncMock()
    monkeypatch.setattr(service, "request_interview_card_duplicate_refresh", enqueue)
    result = await service.list_cached_interview_card_duplicates(
        AsyncMock(),
        direction_id=None,
        minimum_similarity=0.35,
        limit=20,
        offset=0,
    )
    assert result.cache_status == "failed"
    assert not result.cache_refreshing
    assert result.cache_error == "Расчёт прерван"
    enqueue.assert_not_awaited()


async def test_worker_failure_releases_lock_and_records_retryable_status(monkeypatch):
    from unittest.mock import AsyncMock

    from app.interviews import card_automation_jobs as jobs
    from app.interviews import card_automation_service as service

    monkeypatch.setattr(jobs, "acquire_duplicate_refresh_lock", AsyncMock(return_value=True))
    monkeypatch.setattr(jobs, "mark_duplicate_refresh_running", AsyncMock())
    monkeypatch.setattr(jobs, "async_session_factory", lambda: AsyncMock())
    monkeypatch.setattr(
        service,
        "calculate_interview_card_duplicates",
        AsyncMock(side_effect=RuntimeError("test failure")),
    )
    failed, clear, release = AsyncMock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr(jobs, "set_duplicate_refresh_error", failed)
    monkeypatch.setattr(jobs, "clear_duplicate_refresh_status", clear)
    monkeypatch.setattr(jobs, "release_duplicate_refresh_lock", release)
    with pytest.raises(RuntimeError, match="test failure"):
        await jobs.refresh_interview_card_duplicate_cache({})
    assert failed.await_args.args == (True,)
    clear.assert_awaited_once()
    release.assert_awaited_once()
