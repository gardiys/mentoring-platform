import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select

from app.core.config import get_settings
from app.interviews.models import InterviewCard
from app.interviews.models import InterviewCardFrequency as Frequency
from tests.conftest import TestSession, test_engine
from tests.test_card_automation_pipeline import _create_card


async def test_frequency_migration_is_repeatable_and_preserves_manual_settings(seeded, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "observed_card_frequency",
        Path(__file__).parents[1] / "migrations/versions/20260922_0093_observed_card_frequency.py",
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    settings = get_settings().model_copy(update={"interview_card_frequent_min_occurrences": 3})
    monkeypatch.setattr(migration, "get_settings", lambda: settings)
    base = await _create_card(seeded, "Base question")
    cases = [
        (2, Frequency.OCCASIONAL, Frequency.OCCASIONAL),
        (3, Frequency.OCCASIONAL, Frequency.OCCASIONAL),
        (5, Frequency.OCCASIONAL, Frequency.OCCASIONAL),
        (3, None, Frequency.OCCASIONAL),
        (0, Frequency.FREQUENT, Frequency.FREQUENT),
    ]
    async with TestSession() as session:
        cards = [
            InterviewCard(
                deck_id=base.deck_id,
                slug=f"frequency-migration-{index}",
                category="Python",
                question_markdown=f"Question {index}",
                answer_markdown="Answer",
                asked_count=count,
                frequency_override=override,
                frequency=frequency,
                is_published=True,
            )
            for index, (count, override, frequency) in enumerate(cases)
        ]
        session.add_all(cards)
        await session.commit()
        ids = [card.id for card in cards]

    def run(connection, operation):
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            operation()

    async with test_engine.begin() as connection:
        await connection.run_sync(run, migration.upgrade)
        await connection.run_sync(run, migration.upgrade)

    async with TestSession() as session:
        for index, card_id in enumerate(ids):
            card = await session.get(InterviewCard, card_id)
            assert card.asked_count == cases[index][0]
            assert card.frequency_override == cases[index][1]
            assert card.frequency == (Frequency.OCCASIONAL if index == 0 else Frequency.FREQUENT)

    async with test_engine.begin() as connection:
        await connection.run_sync(run, migration.downgrade)

    async with TestSession() as session:
        rows = {
            card.id: card
            for card in await session.scalars(
                select(InterviewCard).where(InterviewCard.id.in_(ids))
            )
        }
        assert rows[ids[1]].frequency == rows[ids[2]].frequency == Frequency.OCCASIONAL
        assert rows[ids[3]].frequency == rows[ids[4]].frequency == Frequency.FREQUENT
