from __future__ import annotations

from sqlalchemy import and_, or_
from sqlalchemy.sql.elements import ColumnElement

from app.core.config import get_settings
from app.interviews.models import (
    InterviewCard,
    InterviewCardFrequency,
    InterviewCardFrequencyMode,
)


def frequent_occurrence_threshold() -> int:
    return get_settings().interview_card_frequent_min_occurrences


def automatic_card_frequency(
    asked_count: int,
    *,
    threshold: int | None = None,
) -> InterviewCardFrequency:
    minimum = threshold if threshold is not None else frequent_occurrence_threshold()
    if asked_count >= minimum:
        return InterviewCardFrequency.FREQUENT
    return InterviewCardFrequency.OCCASIONAL


def card_frequency_mode(card: InterviewCard) -> InterviewCardFrequencyMode:
    if card.frequency_override is None:
        return InterviewCardFrequencyMode.AUTOMATIC
    return InterviewCardFrequencyMode.MANUAL


def effective_card_frequency(
    card: InterviewCard,
    *,
    threshold: int | None = None,
) -> InterviewCardFrequency:
    return card.frequency_override or automatic_card_frequency(
        card.asked_count or 0,
        threshold=threshold,
    )


def effective_frequent_predicate() -> ColumnElement[bool]:
    return or_(
        InterviewCard.frequency_override == InterviewCardFrequency.FREQUENT,
        and_(
            InterviewCard.frequency_override.is_(None),
            InterviewCard.asked_count >= frequent_occurrence_threshold(),
        ),
    ).is_(True)


def refresh_card_frequency(
    card: InterviewCard,
    *,
    threshold: int | None = None,
) -> InterviewCardFrequency:
    card.frequency = card.frequency_override or automatic_card_frequency(
        card.asked_count or 0,
        threshold=threshold,
    )
    return card.frequency
