"""Retrieve trusted materials by ranking or pinned identifiers with identical access checks."""

import re
from typing import Any
from uuid import UUID

from sqlalchemy import case, exists, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.interviews.card_automation_models import AutomationDecision, QuestionCluster
from app.interviews.card_automation_privacy import redact_untrusted_text
from app.interviews.card_automation_types import AutomationDecisionSource, AutomationDecisionType

_STOP_WORDS = frozenset(
    """
что как для чем это такое такие такой каких какие какая какой когда где почему зачем
при про или без если между после перед есть быть будет были был было может можно нужно
расскажите объясните кратко устроен устроены устроена обычно работает работают
работа работы используется используют
решить проблему проблемы базовом сценарии рассказать расскажи привести пример
использовали использовал используете у вас ваш ваша вашем свои свой например вопрос
ли бы вы мы они он она оно их его ее ты нам вам нас мне тебе собой
""".split()
)
_ALIASES = {
    "decorator": "декоратор",
    "singleton": "синглтон одиночка",
    "join": "соединение",
    "gil": "global interpreter lock",
    "asyncio": "асинхронность",
    "redis": "редис",
    "postgresql": "postgres postgresql",
    "декоратор": "decorator",
}


def _source_query(question: str) -> str:
    terms = list(
        dict.fromkeys(
            token
            for token in re.findall(r"[\w]+", question.casefold())
            if (len(token) >= 3 or token in {"go", "gc", "io", "id", "is"})
            and token not in _STOP_WORDS
        )
    )[:24]
    for term in list(terms):
        terms.extend(_ALIASES.get(term, "").split())
    if re.search(r"\bn\s*\+\s*1\b", question, re.I):
        # PostgreSQL parses the punctuation too: keep it as a phrase, not discarded n/1.
        return '"n+1"'
    return " OR ".join(dict.fromkeys(terms))


def _source_rank(query: str, title: Any, content: Any) -> ColumnElement[float]:
    # Rank the entire authorized corpus BEFORE applying a limit. PostgreSQL provides
    # Russian stemming and a simple dictionary for code identifiers / English terms.
    scores = []
    for config in ("russian", "simple"):
        language: ColumnElement[Any] = literal_column(f"'{config}'::regconfig")
        title_vector = func.setweight(func.to_tsvector(language, title), literal_column("'A'"))
        body_vector = func.setweight(func.to_tsvector(language, content), literal_column("'D'"))
        vector = title_vector.op("||")(body_vector)
        scores.append(func.ts_rank_cd(vector, func.websearch_to_tsquery(language, query)))
    if query == '"n+1"':
        # Prevent generic words from crowding the actual technical concept out of top-k.
        return case(
            (func.concat_ws(" ", title, content).op("~*")(r"\mn\s*\+\s*1\M"), 10.0),
            else_=0.0,
        )
    return scores[0] + scores[1]


def _relevant_excerpt(content: str, question: str, *, limit: int = 8_000) -> str:
    """Keep the matched passage of long sources, rather than always its introduction."""
    if len(content) <= limit:
        return content
    if re.search(r"\bn\s*\+\s*1\b", question, re.I):
        matches = list(re.finditer(r"\bn\s*\+\s*1\b", content, re.I))
    else:
        terms = [
            t
            for t in re.findall(r"\w+", question.casefold())
            if len(t) >= 4 and t not in _STOP_WORDS
        ]
        pattern = "|".join(re.escape(t) for t in dict.fromkeys(terms))
        matches = list(re.finditer(pattern, content, re.I)) if pattern else []
    if not matches:
        return content[:limit]
    # Choose a dense window around actual query terms; preserve surrounding explanation.
    positions = [m.start() for m in matches]
    best, right = positions[0], 0
    best_count = 0
    for left, position in enumerate(positions):
        while right < len(positions) and positions[right] < position + limit - 1_000:
            right += 1
        if right - left > best_count:
            best, best_count = position, right - left
    start = max(0, best - 500)
    return content[start : start + limit]


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

    query = _source_query(cluster.canonical_question)
    if source_ids is None and not query:
        return []
    card_rank = _source_rank(
        query,
        func.concat_ws(" ", InterviewCard.question_markdown, InterviewCard.category),
        func.coalesce(InterviewCard.answer_markdown, ""),
    )
    knowledge_rank = _source_rank(
        query,
        func.concat_ws(" ", KnowledgeEntry.title, KnowledgeEntry.summary),
        func.coalesce(KnowledgeEntry.content_markdown, ""),
    )
    roadmap_rank = _source_rank(
        query,
        func.concat_ws(" ", Topic.title, Topic.description),
        func.coalesce(Topic.content_markdown, ""),
    )
    cards = list(
        await session.execute(
            select(InterviewCard, card_rank)
            .join(InterviewDeck, InterviewDeck.id == InterviewCard.deck_id)
            .where(
                InterviewDeck.track_id == cluster.direction_id,
                *([card_rank > 0] if source_ids is None else []),
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
            .order_by(card_rank.desc(), InterviewCard.id)
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
                knowledge_rank,
            )
            .join(KnowledgeTopic, KnowledgeTopic.id == KnowledgeEntry.topic_id)
            .join(KnowledgeTopicTrack, KnowledgeTopicTrack.topic_id == KnowledgeTopic.id)
            .where(
                KnowledgeTopicTrack.track_id == cluster.direction_id,
                *([knowledge_rank > 0] if source_ids is None else []),
                *(
                    [KnowledgeEntry.id.in_(requested["knowledge_entry"])]
                    if source_ids is not None
                    else []
                ),
                KnowledgeTopic.is_published.is_(True),
                KnowledgeEntry.is_published.is_(True),
            )
            .order_by(knowledge_rank.desc(), KnowledgeEntry.id)
            .limit(100)
        )
    ).all()
    roadmap_rows = (
        await session.execute(
            select(Topic.id, Topic.title, Topic.description, Topic.content_markdown, roadmap_rank)
            .join(RoadmapSection, RoadmapSection.id == Topic.section_id)
            .join(Roadmap, Roadmap.id == RoadmapSection.roadmap_id)
            .join(LearningTrackRoadmap, LearningTrackRoadmap.roadmap_id == Roadmap.id)
            .where(
                LearningTrackRoadmap.track_id == cluster.direction_id,
                *([roadmap_rank > 0] if source_ids is None else []),
                *([Topic.id.in_(requested["roadmap_topic"])] if source_ids is not None else []),
                Roadmap.is_published.is_(True),
                Topic.is_published.is_(True),
            )
            .order_by(roadmap_rank.desc(), Topic.id)
            .limit(100)
        )
    ).all()
    ranked: list[tuple[float, str, str, str]] = []
    for card, score in cards:
        ranked.append(
            (
                float(score),
                f"interview_card:{card.id}",
                card.question_markdown,
                card.answer_markdown,
            )
        )
    for entry_id, title, _summary, content, score in knowledge_rows:
        ranked.append((float(score), f"knowledge_entry:{entry_id}", title, content))
    for topic_id, title, _description, content, score in roadmap_rows:
        ranked.append((float(score), f"roadmap_topic:{topic_id}", title, content))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    snippets = [
        {
            "source_id": source_id,
            "title": redact_untrusted_text(title)[:500],
            "content": redact_untrusted_text(
                _relevant_excerpt(content, cluster.canonical_question)
            ),
        }
        for _score, source_id, title, content in ranked
    ]

    by_id = {item["source_id"]: item for item in snippets}
    if source_ids is not None:
        return [by_id[reference] for reference in dict.fromkeys(source_ids) if reference in by_id]
    return list(by_id.values())[:8]
