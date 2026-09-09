"""Versioned, student-authorized material feed; reuses canonical cards and human audit."""

import hashlib
import json
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy import false, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.career_packages.models import CareerPackage, CareerPackageVersion
from app.copilot.dependencies import CopilotMaterialUser
from app.core.config import get_settings
from app.core.errors import api_error
from app.db.session import get_db_session
from app.interviews.card_automation_models import AutomationDecision
from app.interviews.card_automation_types import (
    AutomationDecisionSource,
    AutomationDecisionType,
    AutomationReviewResult,
)
from app.interviews.models import InterviewCard, InterviewDeck
from app.knowledge.models import KnowledgeEntry, KnowledgeTopic, KnowledgeTopicTrack
from app.tracks.access import accessible_track_ids
from app.tracks.models import LearningTrack

router = APIRouter(prefix="/copilot/rag", tags=["copilot-rag"])
Session = Annotated[AsyncSession, Depends(get_db_session)]
Track = Literal["python", "go"]
Kind = Literal["kb", "card", "resume"]


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def material(kind: str, row_id: UUID, content: str, title: str, **meta: Any) -> dict[str, Any]:
    payload = {"key": f"{kind}:{row_id}", "content": content, "title": title, **meta}
    payload["version"] = digest(json.dumps(payload, sort_keys=True, ensure_ascii=False))
    return payload


async def materials(
    session: AsyncSession,
    student: Any,
    track: str,
    resume: bool,
    key: tuple[str, UUID] | None = None,
) -> list[dict[str, Any]]:
    allowed = await accessible_track_ids(session, student)
    track_ids = list(
        await session.scalars(
            select(LearningTrack.id).where(
                LearningTrack.id.in_(allowed),
                LearningTrack.slug == track,
            )
        )
    )
    kb = list(
        (
            await session.execute(
                select(KnowledgeEntry, KnowledgeTopic)
                .join(KnowledgeTopic, KnowledgeTopic.id == KnowledgeEntry.topic_id)
                .join(KnowledgeTopicTrack, KnowledgeTopicTrack.topic_id == KnowledgeTopic.id)
                .where(
                    KnowledgeTopicTrack.track_id.in_(track_ids),
                    KnowledgeEntry.is_published.is_(True),
                    KnowledgeTopic.is_published.is_(True),
                    true()
                    if key is None
                    else (KnowledgeEntry.id == key[1] if key[0] == "kb" else false()),
                )
                .limit(1001)
            )
        ).all()
    )
    cards = list(
        (
            await session.execute(
                select(InterviewCard, InterviewDeck)
                .join(InterviewDeck, InterviewDeck.id == InterviewCard.deck_id)
                .where(
                    InterviewDeck.track_id.in_(track_ids),
                    InterviewDeck.is_published.is_(True),
                    InterviewCard.is_published.is_(True),
                    true()
                    if key is None
                    else (InterviewCard.id == key[1] if key[0] == "card" else false()),
                )
                .limit(1001)
            )
        ).all()
    )
    decisions = list(
        await session.scalars(
            select(AutomationDecision)
            .where(
                AutomationDecision.selected_card_id.in_([card.id for card, _ in cards]),
                AutomationDecision.decision_type == AutomationDecisionType.CARD_CREATED,
                AutomationDecision.decision_source == AutomationDecisionSource.HUMAN,
                AutomationDecision.review_result == AutomationReviewResult.CORRECT,
                AutomationDecision.reviewed_at.is_not(None),
                AutomationDecision.reviewed_by_user_id.is_not(None),
                AutomationDecision.is_overridden.is_(False),
            )
            .order_by(AutomationDecision.created_at.desc())
        )
    )
    result = [
        material(
            "kb",
            entry.id,
            entry.title + "\n\n" + entry.content_markdown,
            entry.title,
            source_type="knowledge_base",
            section=topic.title,
            path=f"/knowledge/entries/{entry.slug}",
            provenance="published_learning_material",
            review_status="published",
            track=track,
        )
        for entry, topic in kb
    ]
    for card, deck in cards:
        decision = next(
            (
                d
                for d in decisions
                if d.selected_card_id == card.id
                and d.retrieval_scores.get("question_sha256") == digest(card.question_markdown)
                and d.retrieval_scores.get("answer_sha256") == digest(card.answer_markdown)
            ),
            None,
        )
        result.append(
            material(
                "card",
                card.id,
                card.question_markdown + "\n\n" + card.answer_markdown,
                card.question_markdown,
                source_type="question_database",
                track=track,
                section=f"{deck.title} / {card.category}",
                path=f"/interviews/{deck.slug}/questions",
                provenance="canonical_card",
                review_status="human_reviewed" if decision else "published",
                reviewed_at=decision.reviewed_at.isoformat()
                if decision and decision.reviewed_at
                else None,
                cluster_id=str(decision.entity_id) if decision else None,
                question=card.question_markdown,
                answer=card.answer_markdown,
            )
        )
    if resume and get_settings().career_package_enabled:
        versions = list(
            await session.scalars(
                select(CareerPackageVersion)
                .join(CareerPackage, CareerPackage.id == CareerPackageVersion.package_id)
                .where(
                    CareerPackage.student_id == student.id,
                    CareerPackage.track_id.in_(track_ids),
                    CareerPackageVersion.provided_at.is_not(None),
                    true() if key is None else CareerPackageVersion.id == key[1],
                )
                .limit(1001)
            )
        )
        for version in versions:
            text = version.snapshot.get("resume", {}).get("text_content")
            if text:
                result.append(
                    material(
                        "resume",
                        version.id,
                        text,
                        "Опубликованное резюме",
                        source_type="resume",
                        track=track,
                        section="",
                        path="",
                        provenance="published_resume",
                        review_status="unconfirmed",
                    )
                )
    if len(result) > 1000 or sum(len(item["content"]) for item in result) > 5_000_000:
        api_error(413, "copilot_context_too_large", "Too many materials for one snapshot")
    return result


@router.get("/manifest")
async def manifest(
    session: Session,
    student: CopilotMaterialUser,
    response: Response,
    track: Track,
    resume: bool = False,
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "private, no-store"
    items = await materials(session, student, track, resume)
    return {
        "policy_version": "rag-3",
        "complete": True,
        "items": [{"key": item["key"], "version": item["version"]} for item in items],
    }


@router.get("/sources/{kind}/{source_id}")
async def read_source(
    kind: Kind,
    source_id: UUID,
    session: Session,
    student: CopilotMaterialUser,
    response: Response,
    track: Track,
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "private, no-store"
    # Same SQL scope and snapshot hashing as the manifest. No unauthorised content is loaded.
    items = await materials(session, student, track, kind == "resume", (kind, source_id))
    found = next((item for item in items if item["key"] == f"{kind}:{source_id}"), None)
    if found is None:
        api_error(404, "source_not_found", "Source not found")
    return found
