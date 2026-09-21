"""Retrieve trusted materials by ranking or pinned identifiers with identical access checks."""

from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.interviews.card_automation_models import AutomationDecision, QuestionCluster
from app.interviews.card_automation_privacy import redact_untrusted_text
from app.interviews.card_automation_types import AutomationDecisionSource, AutomationDecisionType


async def load_trusted_sources(
    session: AsyncSession, cluster: QuestionCluster, *, source_ids: list[str] | None = None
) -> list[dict[str, str]]:
    """Return small, explicitly identified internal source snippets.

    Candidate answers and raw transcripts are intentionally excluded. The
    source set is limited to human-published cards, knowledge entries and
    roadmap materials from the same direction.
    """

    requested: dict[str, list[UUID]] = {
        "interview_card": [],
        "knowledge_entry": [],
        "roadmap_topic": [],
    }
    if source_ids is not None:
        if len(source_ids) > 20:
            return []
        for reference in source_ids:
            kind, separator, value = reference.partition(":")
            if separator and kind in requested:
                try:
                    requested[kind].append(UUID(value))
                except ValueError:
                    pass

    from app.interviews.models import InterviewCard, InterviewDeck
    from app.knowledge.models import KnowledgeEntry, KnowledgeTopic, KnowledgeTopicTrack
    from app.roadmaps.models import Roadmap, RoadmapSection, Topic
    from app.tracks.models import LearningTrackRoadmap

    cards = list(
        await session.scalars(
            select(InterviewCard)
            .join(InterviewDeck, InterviewDeck.id == InterviewCard.deck_id)
            .where(
                InterviewDeck.track_id == cluster.direction_id,
                *(
                    [InterviewCard.id.in_(requested["interview_card"])]
                    if source_ids is not None
                    else []
                ),
                InterviewDeck.is_published.is_(True),
                InterviewCard.is_published.is_(True),
                ~exists(
                    select(AutomationDecision.id).where(
                        AutomationDecision.selected_card_id == InterviewCard.id,
                        AutomationDecision.decision_type == AutomationDecisionType.CARD_CREATED,
                        AutomationDecision.decision_source != AutomationDecisionSource.HUMAN,
                    )
                ),
            )
            .order_by(
                InterviewCard.asked_count.desc(), InterviewCard.updated_at.desc(), InterviewCard.id
            )
            .limit(100)
        )
    )
    knowledge_rows = (
        await session.execute(
            select(
                KnowledgeEntry.id,
                KnowledgeEntry.title,
                KnowledgeEntry.summary,
                KnowledgeEntry.content_markdown,
            )
            .join(KnowledgeTopic, KnowledgeTopic.id == KnowledgeEntry.topic_id)
            .join(KnowledgeTopicTrack, KnowledgeTopicTrack.topic_id == KnowledgeTopic.id)
            .where(
                KnowledgeTopicTrack.track_id == cluster.direction_id,
                *(
                    [KnowledgeEntry.id.in_(requested["knowledge_entry"])]
                    if source_ids is not None
                    else []
                ),
                KnowledgeTopic.is_published.is_(True),
                KnowledgeEntry.is_published.is_(True),
            )
            .order_by(KnowledgeEntry.updated_at.desc(), KnowledgeEntry.id)
            .limit(100)
        )
    ).all()
    roadmap_rows = (
        await session.execute(
            select(Topic.id, Topic.title, Topic.description, Topic.content_markdown)
            .join(RoadmapSection, RoadmapSection.id == Topic.section_id)
            .join(Roadmap, Roadmap.id == RoadmapSection.roadmap_id)
            .join(LearningTrackRoadmap, LearningTrackRoadmap.roadmap_id == Roadmap.id)
            .where(
                LearningTrackRoadmap.track_id == cluster.direction_id,
                *([Topic.id.in_(requested["roadmap_topic"])] if source_ids is not None else []),
                Roadmap.is_published.is_(True),
                Topic.is_published.is_(True),
            )
            .order_by(Topic.updated_at.desc(), Topic.id)
            .limit(100)
        )
    ).all()
    question_tokens = {
        token for token in cluster.normalized_canonical_question.split() if len(token) >= 3
    }
    ranked: list[tuple[int, str, str, str]] = []
    for card in cards:
        haystack = f"{card.category} {card.question_markdown}".casefold()
        score = sum(1 for token in question_tokens if token in haystack)
        if score or source_ids is not None:
            ranked.append(
                (
                    score,
                    f"interview_card:{card.id}",
                    card.question_markdown,
                    card.answer_markdown,
                )
            )
    for entry_id, title, summary, content in knowledge_rows:
        haystack = f"{title} {summary or ''}".casefold()
        score = sum(1 for token in question_tokens if token in haystack)
        if score or source_ids is not None:
            ranked.append(
                (
                    score,
                    f"knowledge_entry:{entry_id}",
                    title,
                    content,
                )
            )
    for topic_id, title, description, content in roadmap_rows:
        haystack = f"{title} {description or ''}".casefold()
        score = sum(1 for token in question_tokens if token in haystack)
        if score or source_ids is not None:
            ranked.append(
                (
                    score,
                    f"roadmap_topic:{topic_id}",
                    title,
                    content,
                )
            )
    ranked.sort(key=lambda item: (-item[0], item[1]))
    snippets = [
        {
            "source_id": source_id,
            "title": redact_untrusted_text(title)[:500],
            "content": redact_untrusted_text(content)[:8_000],
        }
        for _score, source_id, title, content in ranked
    ]

    by_id = {item["source_id"]: item for item in snippets}
    if source_ids is not None:
        return [by_id[reference] for reference in dict.fromkeys(source_ids) if reference in by_id]
    return list(by_id.values())[:8]
