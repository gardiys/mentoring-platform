from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.interviews.intelligence_ai import (
    AIUsageResult,
    InterviewAIError,
    InterviewAIProvider,
)
from app.interviews.intelligence_models import (
    IntelligenceQuestion,
    IntelligenceQuestionModerationStatus,
)
from app.interviews.models import InterviewCard, InterviewDeck

type EmbeddingRow = InterviewCard | IntelligenceQuestion
DEFAULT_EMBEDDING_BATCH_SIZE = 64
EMBEDDING_MAX_INPUT_CHARS = 4_000


@dataclass(frozen=True)
class EmbeddingRefreshResult:
    refreshed: int
    usages: list[AIUsageResult]


def _row_source_text(row: EmbeddingRow) -> str:
    if isinstance(row, InterviewCard):
        return row.question_markdown
    return row.question_text


def embedding_input_text(value: str) -> str:
    # The embeddings endpoint rejects empty input and has per-input/aggregate
    # token limits. Interview questions are short by design; bounding legacy
    # rows prevents one malformed record from poisoning every backfill retry.
    return (value.strip() or "Вопрос без текста")[:EMBEDDING_MAX_INPUT_CHARS]


def embedding_source_hash(value: str) -> str:
    return hashlib.sha256(embedding_input_text(value).encode("utf-8")).hexdigest()


def _row_text(row: EmbeddingRow) -> str:
    return embedding_input_text(_row_source_text(row))


def _embedding_is_current(row: EmbeddingRow, provider: InterviewAIProvider) -> bool:
    return (
        row.question_embedding is not None
        and row.question_embedding_model == provider.embedding_model
        and row.question_embedding_dimensions == provider.embedding_dimensions
        and row.question_embedding_source_hash == embedding_source_hash(_row_source_text(row))
        and len(row.question_embedding) == provider.embedding_dimensions
        and all(math.isfinite(value) for value in row.question_embedding)
    )


async def refresh_embedding_rows(
    provider: InterviewAIProvider,
    rows: list[EmbeddingRow],
    *,
    batch_size: int = DEFAULT_EMBEDDING_BATCH_SIZE,
    session: AsyncSession | None = None,
) -> EmbeddingRefreshResult:
    if batch_size < 1:
        raise ValueError("Embedding batch size must be positive")
    stale_rows = [row for row in rows if not _embedding_is_current(row, provider)]
    usages: list[AIUsageResult] = []
    refreshed = 0
    for start in range(0, len(stale_rows), batch_size):
        batch = stale_rows[start : start + batch_size]
        source_snapshots = [
            (
                _row_source_text(row),
                _row_text(row),
                embedding_source_hash(_row_source_text(row)),
            )
            for row in batch
        ]
        result = await provider.embed(
            [input_text for _source_text, input_text, _source_hash in source_snapshots]
        )
        if len(result.embeddings) != len(batch):
            raise InterviewAIError(
                "OPENAI_INVALID_RESPONSE",
                "Embedding provider returned an incomplete batch",
                retryable=False,
            )
        for row, embedding, (source_text, _input_text, source_hash) in zip(
            batch,
            result.embeddings,
            source_snapshots,
            strict=True,
        ):
            if len(embedding) != provider.embedding_dimensions or not all(
                math.isfinite(value) for value in embedding
            ):
                raise InterviewAIError(
                    "OPENAI_INVALID_RESPONSE",
                    "Embedding provider returned an unexpected vector size",
                    retryable=False,
                )
            if session is not None:
                model = type(row)
                source_column = (
                    InterviewCard.question_markdown
                    if isinstance(row, InterviewCard)
                    else IntelligenceQuestion.question_text
                )
                statement = (
                    update(model)
                    .where(model.id == row.id, source_column == source_text)
                    .values(
                        question_embedding=embedding,
                        question_embedding_model=provider.embedding_model,
                        question_embedding_dimensions=provider.embedding_dimensions,
                        question_embedding_source_hash=source_hash,
                    )
                    .execution_options(synchronize_session=False)
                )
                update_result = await session.execute(statement)
                if getattr(update_result, "rowcount", 0) != 1:
                    await session.refresh(
                        row,
                        attribute_names=[
                            source_column.key,
                            "question_embedding",
                            "question_embedding_model",
                            "question_embedding_dimensions",
                            "question_embedding_source_hash",
                        ],
                    )
                    continue
                await session.refresh(
                    row,
                    attribute_names=[
                        "question_embedding",
                        "question_embedding_model",
                        "question_embedding_dimensions",
                        "question_embedding_source_hash",
                    ],
                )
            else:
                if embedding_source_hash(_row_source_text(row)) != source_hash:
                    continue
                row.question_embedding = embedding
                row.question_embedding_model = provider.embedding_model
                row.question_embedding_dimensions = provider.embedding_dimensions
                row.question_embedding_source_hash = source_hash
            refreshed += 1
        usages.append(result.usage)
    return EmbeddingRefreshResult(refreshed=refreshed, usages=usages)


async def refresh_track_question_embeddings(
    session: AsyncSession,
    provider: InterviewAIProvider,
    track_id: UUID,
    current_questions: list[IntelligenceQuestion],
) -> EmbeddingRefreshResult:
    cards = list(
        await session.scalars(
            select(InterviewCard)
            .join(InterviewDeck, InterviewDeck.id == InterviewCard.deck_id)
            .where(
                InterviewDeck.track_id == track_id,
                InterviewDeck.is_published.is_(True),
                InterviewCard.is_published.is_(True),
            )
            .order_by(InterviewDeck.position, InterviewCard.position, InterviewCard.id)
        )
    )
    aliases: list[IntelligenceQuestion] = []
    if cards:
        aliases = list(
            await session.scalars(
                select(IntelligenceQuestion).where(
                    IntelligenceQuestion.published_card_id.in_([card.id for card in cards]),
                    IntelligenceQuestion.moderation_status
                    == IntelligenceQuestionModerationStatus.APPROVED,
                )
            )
        )
    unique_rows: dict[tuple[str, UUID], EmbeddingRow] = {}
    for card in cards:
        unique_rows[("card", card.id)] = card
    for alias in [*aliases, *current_questions]:
        unique_rows[("question", alias.id)] = alias
    return await refresh_embedding_rows(
        provider,
        list(unique_rows.values()),
        session=session,
    )


def _stale_embedding_filter(
    model: type[InterviewCard] | type[IntelligenceQuestion],
    provider: InterviewAIProvider,
) -> ColumnElement[bool]:
    return or_(
        model.question_embedding.is_(None),
        model.question_embedding_model.is_(None),
        model.question_embedding_model != provider.embedding_model,
        model.question_embedding_dimensions.is_(None),
        model.question_embedding_dimensions != provider.embedding_dimensions,
        model.question_embedding_source_hash.is_(None),
        func.cardinality(model.question_embedding) != provider.embedding_dimensions,
    )


async def backfill_question_embedding_batch(
    session: AsyncSession,
    provider: InterviewAIProvider,
    *,
    limit: int = 256,
) -> EmbeddingRefreshResult:
    cards = list(
        await session.scalars(
            select(InterviewCard)
            .join(InterviewDeck, InterviewDeck.id == InterviewCard.deck_id)
            .where(_stale_embedding_filter(InterviewCard, provider))
            .where(
                InterviewDeck.is_published.is_(True),
                InterviewCard.is_published.is_(True),
            )
            .order_by(InterviewCard.created_at, InterviewCard.id)
            .limit(limit)
        )
    )
    remaining = max(0, limit - len(cards))
    questions: list[IntelligenceQuestion] = []
    if remaining:
        questions = list(
            await session.scalars(
                select(IntelligenceQuestion)
                .join(
                    InterviewCard,
                    InterviewCard.id == IntelligenceQuestion.published_card_id,
                )
                .join(InterviewDeck, InterviewDeck.id == InterviewCard.deck_id)
                .where(
                    _stale_embedding_filter(IntelligenceQuestion, provider),
                    IntelligenceQuestion.moderation_status
                    == IntelligenceQuestionModerationStatus.APPROVED,
                    InterviewDeck.is_published.is_(True),
                    InterviewCard.is_published.is_(True),
                )
                .order_by(IntelligenceQuestion.created_at, IntelligenceQuestion.id)
                .limit(remaining)
            )
        )
    return await refresh_embedding_rows(
        provider,
        [*cards, *questions],
        session=session,
    )
