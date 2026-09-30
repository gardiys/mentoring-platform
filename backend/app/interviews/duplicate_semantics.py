"""Bounded-memory semantic retrieval using already persisted embeddings (no API calls)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import TYPE_CHECKING
from uuid import UUID

import numpy as np

from app.interviews.question_embeddings import EmbeddingRow, embedding_source_hash
from app.interviews.question_matching import EMBEDDING_MATCH_THRESHOLD, RankedQuestionCandidate

if TYPE_CHECKING:
    from app.interviews.card_automation_service import _DuplicateCardContext

NEIGHBOURS = 12
BLOCK_SIZE = 64


def semantic_duplicate_pairs(
    contexts: Sequence[_DuplicateCardContext],
) -> dict[tuple[UUID, UUID], RankedQuestionCandidate]:
    groups: dict[tuple[UUID, str, int], list[tuple[UUID, str, Sequence[float]]]] = defaultdict(list)
    for context in contexts:
        variants: list[tuple[EmbeddingRow, str]] = [(context.card, context.card.question_markdown)]
        variants.extend((alias, alias.question_text) for alias in context.aliases)
        for row, text in variants:
            vector = row.question_embedding
            model, dimensions = row.question_embedding_model, row.question_embedding_dimensions
            if (
                not vector
                or not model
                or not dimensions
                or len(vector) != dimensions
                or row.question_embedding_source_hash != embedding_source_hash(text)
            ):
                continue
            groups[(context.track.id, model, dimensions)].append((context.card.id, text, vector))

    result: dict[tuple[UUID, UUID], RankedQuestionCandidate] = {}
    for rows in groups.values():
        matrix = np.asarray([row[2] for row in rows], dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1)
        valid = np.isfinite(matrix).all(axis=1) & np.isfinite(norms) & (norms > 0)
        matrix[~valid] = 0
        matrix /= np.where(valid, norms, 1)[:, None]
        for start in range(0, len(rows), BLOCK_SIZE):
            # No NxN allocation or BLAS thread fanout in the maintenance worker.
            scores = np.einsum("ij,kj->ik", matrix[start : start + BLOCK_SIZE], matrix)
            for offset, similarities in enumerate(scores):
                source_id = rows[start + offset][0]
                eligible = np.flatnonzero(similarities >= EMBEDDING_MATCH_THRESHOLD)
                # Multiple approved aliases of one card must not consume the shortlist.
                by_card: dict[UUID, tuple[float, str]] = {}
                for index in eligible:
                    target_id, text, _ = rows[index]
                    score = min(1.0, float(similarities[index]))
                    if target_id != source_id and score > by_card.get(target_id, (-1, ""))[0]:
                        by_card[target_id] = (score, text)
                for target_id, (score, text) in sorted(
                    by_card.items(), key=lambda item: (-item[1][0], str(item[0]))
                )[:NEIGHBOURS]:
                    left, right = sorted((source_id, target_id), key=str)
                    pair = (left, right)
                    if pair not in result or score > result[pair].similarity:
                        result[pair] = RankedQuestionCandidate(
                            card_id=target_id,
                            similarity=score,
                            match_type="similar",
                            matched_source="semantic",
                            matched_text=text,
                        )
    return result
