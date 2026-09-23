"""Reuse a published shared answer without importing another learner's speech."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.interviews.card_automation_privacy import redact_untrusted_text
from app.interviews.models import InterviewCard, InterviewDeck


async def published_review_reference(
    session: AsyncSession, *, question: str, direction_id: UUID | None
) -> dict[str, str] | None:
    if direction_id is None:
        return None
    # Exact text (ignoring outer whitespace/case) only. Similarity is not enough
    # to transfer an answer's assumptions or judge a student's understanding.
    cards = list(
        await session.scalars(
            select(InterviewCard)
            .join(InterviewDeck, InterviewDeck.id == InterviewCard.deck_id)
            .where(
                InterviewDeck.track_id == direction_id,
                InterviewDeck.is_published.is_(True),
                InterviewCard.is_published.is_(True),
                func.lower(func.btrim(InterviewCard.question_markdown)) == question.strip().lower(),
            )
            .limit(2)
        )
    )
    if len(cards) != 1:
        return None
    card = cards[0]
    answer = redact_untrusted_text(card.answer_markdown).strip()
    if not answer or len(answer) > 12_000:
        return None
    return {
        "card_id": str(card.id),
        "question": redact_untrusted_text(card.question_markdown),
        "answer": answer,
    }
