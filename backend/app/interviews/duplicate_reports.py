"""User signals and moderator lookup, independent of the automatic snapshot."""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import api_error
from app.interviews.card_automation_schemas import InterviewCardDuplicateCardRead
from app.interviews.card_automation_service import (
    _duplicate_card_read,
    _load_duplicate_card_contexts,
)
from app.interviews.models import InterviewCard, InterviewCardDuplicateReport, InterviewDeck
from app.interviews.service import _public_deck_model
from app.users.models import User


class DuplicateReportRead(BaseModel):
    id: UUID
    status: str


class DuplicateReportItem(BaseModel):
    card: InterviewCardDuplicateCardRead
    reports_count: int
    first_reported_at: datetime


class DuplicateReportPage(BaseModel):
    items: list[DuplicateReportItem]
    total: int


async def report_duplicate(session: AsyncSession, user: User, card_id: UUID) -> DuplicateReportRead:
    row = (
        await session.execute(
            select(InterviewCard, InterviewDeck)
            .join(InterviewDeck)
            .where(InterviewCard.id == card_id, InterviewCard.is_published.is_(True))
            .with_for_update(of=InterviewCard)
        )
    ).one_or_none()
    if row is None:
        api_error(404, "interview_card_not_found", "Карточка не найдена")
    card, deck = row
    await _public_deck_model(session, deck.slug, user)
    # The same user cannot flood the queue or reopen an admin decision on retries.
    await session.execute(
        insert(InterviewCardDuplicateReport)
        .values(
            card_id=card.id,
            reported_by_user_id=user.id,
        )
        .on_conflict_do_nothing(constraint="uq_card_duplicate_report_user")
    )
    report = await session.scalar(
        select(InterviewCardDuplicateReport).where(
            InterviewCardDuplicateReport.card_id == card.id,
            InterviewCardDuplicateReport.reported_by_user_id == user.id,
        )
    )
    assert report is not None
    await session.commit()
    return DuplicateReportRead(id=report.id, status=report.status)


async def list_reports(session: AsyncSession, limit: int, offset: int) -> DuplicateReportPage:
    grouped = (
        select(
            InterviewCardDuplicateReport.card_id,
            func.count().label("count"),
            func.min(InterviewCardDuplicateReport.created_at).label("first"),
        )
        .join(InterviewCard, InterviewCard.id == InterviewCardDuplicateReport.card_id)
        .where(
            InterviewCardDuplicateReport.status == "pending", InterviewCard.is_published.is_(True)
        )
        .group_by(InterviewCardDuplicateReport.card_id)
        .subquery()
    )
    total = await session.scalar(select(func.count()).select_from(grouped)) or 0
    rows = (
        await session.execute(
            select(grouped).order_by(grouped.c.first, grouped.c.card_id).limit(limit).offset(offset)
        )
    ).all()
    contexts = (
        {
            item.card.id: item
            for item in await _load_duplicate_card_contexts(
                session, card_ids=[row.card_id for row in rows]
            )
        }
        if rows
        else {}
    )
    return DuplicateReportPage(
        total=total,
        items=[
            DuplicateReportItem(
                card=_duplicate_card_read(contexts[row.card_id]),
                reports_count=row._mapping["count"],
                first_reported_at=row.first,
            )
            for row in rows
        ],
    )


async def dismiss_reports(session: AsyncSession, admin: User, card_id: UUID) -> None:
    await session.execute(
        update(InterviewCardDuplicateReport)
        .where(
            InterviewCardDuplicateReport.card_id == card_id,
            InterviewCardDuplicateReport.status == "pending",
        )
        .values(status="dismissed", reviewed_by_user_id=admin.id, reviewed_at=datetime.now(UTC))
    )
    await session.commit()


async def search_merge_targets(
    session: AsyncSession,
    card_id: UUID,
    query: str,
) -> list[InterviewCardDuplicateCardRead]:
    source = await session.get(InterviewCard, card_id)
    if source is None or not source.is_published:
        api_error(404, "interview_card_not_found", "Карточка не найдена")
    deck = await session.get_one(InterviewDeck, source.deck_id)
    # Accept question wording or a known card UUID. Escape LIKE wildcards.
    try:
        target_id = UUID(query.strip())
    except ValueError:
        target_id = None
    condition = (
        InterviewCard.id == target_id
        if target_id
        else InterviewCard.question_markdown.icontains(query.strip(), autoescape=True)
    )
    ids = list(
        await session.scalars(
            select(InterviewCard.id)
            .join(InterviewDeck)
            .where(
                InterviewDeck.track_id == deck.track_id,
                InterviewCard.id != card_id,
                InterviewCard.is_published.is_(True),
                condition,
            )
            .order_by(InterviewCard.asked_count.desc(), InterviewCard.id)
            .limit(30)
        )
    )
    return (
        [
            _duplicate_card_read(item)
            for item in await _load_duplicate_card_contexts(session, card_ids=ids)
        ]
        if ids
        else []
    )
