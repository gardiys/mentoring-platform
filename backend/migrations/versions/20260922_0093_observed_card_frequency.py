"""Apply the observed-frequency rule to persisted card labels."""

import sqlalchemy as sa
from alembic import op

from app.core.config import get_settings

revision = "20260922_0093"
down_revision = "20260922_0092"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Match the running application's configured threshold. Keep manual settings;
    # the observed-frequency rule takes precedence over a manual "rare" label.
    op.get_bind().execute(
        sa.text("""
            UPDATE interview_cards
            SET frequency='frequent', updated_at=now()
            WHERE asked_count >= :threshold AND frequency <> 'frequent'
        """),
        {"threshold": get_settings().interview_card_frequent_min_occurrences},
    )


def downgrade() -> None:
    # Restore the previous precedence of manual rare labels without removing
    # occurrences, modifying counters, or undoing an explicit manual frequent label.
    op.get_bind().execute(
        sa.text("""
            UPDATE interview_cards
            SET frequency=frequency_override, updated_at=now()
            WHERE asked_count >= :threshold
              AND frequency_override='occasional' AND frequency='frequent'
        """),
        {"threshold": get_settings().interview_card_frequent_min_occurrences},
    )
