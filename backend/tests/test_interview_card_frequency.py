import pytest

from app.interviews.card_frequency import (
    automatic_card_frequency,
    card_frequency_mode,
    effective_card_frequency,
    refresh_card_frequency,
)
from app.interviews.models import (
    InterviewCard,
    InterviewCardFrequency,
    InterviewCardFrequencyMode,
)


def test_automatic_frequency_promotes_at_threshold() -> None:
    assert automatic_card_frequency(2, threshold=3) is InterviewCardFrequency.OCCASIONAL
    assert automatic_card_frequency(3, threshold=3) is InterviewCardFrequency.FREQUENT


@pytest.mark.parametrize("count", [3, 5, 7])
def test_observed_frequency_overrides_manual_rare(count: int) -> None:
    card = InterviewCard(
        asked_count=count,
        frequency=InterviewCardFrequency.OCCASIONAL,
        frequency_override=InterviewCardFrequency.OCCASIONAL,
    )

    assert effective_card_frequency(card, threshold=3) is InterviewCardFrequency.FREQUENT
    assert refresh_card_frequency(card, threshold=3) is InterviewCardFrequency.FREQUENT
    assert card.frequency_override is InterviewCardFrequency.OCCASIONAL
    assert card_frequency_mode(card) is InterviewCardFrequencyMode.MANUAL

    card.frequency_override = None
    assert refresh_card_frequency(card, threshold=3) is InterviewCardFrequency.FREQUENT
    assert card_frequency_mode(card) is InterviewCardFrequencyMode.AUTOMATIC


def test_manual_frequent_is_still_available_below_threshold() -> None:
    card = InterviewCard(asked_count=2, frequency_override=InterviewCardFrequency.FREQUENT)
    assert refresh_card_frequency(card, threshold=3) is InterviewCardFrequency.FREQUENT
    card.frequency_override = InterviewCardFrequency.OCCASIONAL
    assert refresh_card_frequency(card, threshold=3) is InterviewCardFrequency.OCCASIONAL


def test_effective_frequency_uses_current_threshold_without_rewriting_card() -> None:
    card = InterviewCard(
        asked_count=4,
        frequency=InterviewCardFrequency.OCCASIONAL,
        frequency_override=None,
    )

    assert effective_card_frequency(card, threshold=3) is InterviewCardFrequency.FREQUENT
    assert card.frequency is InterviewCardFrequency.OCCASIONAL
