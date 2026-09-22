"""Fresh, content-bound pairwise evidence for the final publication duplicate check."""

import hashlib
import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.interviews.card_automation_models import (
    AutomationDecision,
    CardAutomationSettings,
    QuestionCluster,
)
from app.interviews.card_automation_privacy import redact_untrusted_text
from app.interviews.card_automation_types import AutomationDecisionSource, AutomationDecisionType
from app.interviews.intelligence_ai import PAIRWISE_CARD_MATCH_PROMPT_VERSION
from app.interviews.models import InterviewCard, InterviewDeck
from app.interviews.question_matching import (
    QuestionCandidate,
    QuestionVariant,
    rank_question_candidates,
)


@dataclass
class ClusterMatch:
    card: InterviewCard
    similarity: float
    fingerprint: str
    verdict: str | None = None


def match_fingerprint(cluster: QuestionCluster, card: InterviewCard) -> str:
    return hashlib.sha256(
        json.dumps(
            [
                "cluster-publication-match-v1",
                PAIRWISE_CARD_MATCH_PROMPT_VERSION,
                str(cluster.direction_id),
                str(cluster.id),
                cluster.membership_revision,
                cluster.canonical_question,
                str(card.id),
                str(card.deck_id),
                card.category,
                redact_untrusted_text(card.question_markdown)[:4_000],
                # Hash the entire card: edits beyond the AI excerpt must also invalidate consent.
                card.question_markdown,
                card.answer_markdown,
            ],
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


async def publication_cards(session: AsyncSession, cluster: QuestionCluster) -> list[InterviewCard]:
    return list(
        await session.scalars(
            select(InterviewCard)
            .join(InterviewDeck)
            .where(
                InterviewDeck.track_id == cluster.direction_id,
                InterviewDeck.is_published.is_(True),
                InterviewCard.is_published.is_(True),
            )
        )
    )


async def current_cluster_matches(
    session: AsyncSession,
    cluster: QuestionCluster,
    settings: CardAutomationSettings,
    cards: list[InterviewCard] | None = None,
) -> list[ClusterMatch]:
    cards = await publication_cards(session, cluster) if cards is None else cards
    candidates = [
        QuestionCandidate(
            card_id=c.id,
            asked_count=c.asked_count,
            variants=(
                QuestionVariant(
                    text=c.question_markdown,
                    embedding=tuple(c.question_embedding)
                    if c.question_embedding is not None
                    and c.question_embedding_model == cluster.embedding_model
                    and c.question_embedding_dimensions == cluster.embedding_dimensions
                    else None,
                    source="canonical",
                ),
            ),
        )
        for c in cards
    ]
    ranked = rank_question_candidates(
        cluster.canonical_question, cluster.embedding, candidates, limit=4
    )
    by_id = {c.id: c for c in cards}
    matches = [
        ClusterMatch(by_id[r.card_id], r.similarity, match_fingerprint(cluster, by_id[r.card_id]))
        for r in ranked
        if r.similarity >= settings.cluster_match_threshold
    ]
    for match in matches:
        decision = await session.scalar(
            select(AutomationDecision)
            .where(
                AutomationDecision.entity_type == "cluster",
                AutomationDecision.entity_id == cluster.id,
                AutomationDecision.decision_type == AutomationDecisionType.SEMANTIC_CARD_MATCH,
                AutomationDecision.decision_source == AutomationDecisionSource.SEMANTIC_JUDGE,
                AutomationDecision.input_hash == match.fingerprint,
                AutomationDecision.is_overridden.is_(False),
            )
            .order_by(AutomationDecision.created_at.desc(), AutomationDecision.id.desc())
            .limit(1)
        )
        if decision is not None:
            result = decision.judge_result or {}
            threshold = max(0.98, settings.pairwise_judge_confidence_threshold)
            match.verdict = (
                str(result.get("decision"))
                if (decision.confidence or 0) >= threshold
                else "uncertain"
            )
            if match.verdict == "same_card" and (
                result.get("missing_in_existing_card") or result.get("extra_in_existing_card")
            ):
                match.verdict = "uncertain"
    return matches


def matching_card(
    matches: list[ClusterMatch], settings: CardAutomationSettings
) -> InterviewCard | None:
    if not settings.auto_link_semantic_enabled or len(matches) > 3:
        return None
    same = [m for m in matches if m.verdict == "same_card"]
    distinct = {"related_different_scope", "not_related"}
    if len(same) == 1 and all(m is same[0] or m.verdict in distinct for m in matches):
        return same[0].card
    return None


def all_distinct(matches: list[ClusterMatch]) -> bool:
    return len(matches) <= 3 and all(
        m.verdict in {"related_different_scope", "not_related"} for m in matches
    )
