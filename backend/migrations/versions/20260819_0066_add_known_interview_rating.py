"""Add the one-month interview-card review rating.

Revision ID: 20260819_0066
Revises: 20260817_0065
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260819_0066"
down_revision: str | None = "20260817_0065"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE interview_review_rating ADD VALUE IF NOT EXISTS 'known'")


def downgrade() -> None:
    # PostgreSQL cannot remove an enum value in place. Convert through text so
    # an already used `known` value can safely fall back to the previous
    # strongest rating during a rollback.
    op.execute(
        "UPDATE interview_card_progress SET last_rating = 'easy' WHERE last_rating = 'known'"
    )
    op.execute(
        "ALTER TABLE interview_card_progress "
        "ALTER COLUMN last_rating TYPE VARCHAR(16) "
        "USING last_rating::text"
    )
    op.execute("DROP TYPE interview_review_rating")
    op.execute("CREATE TYPE interview_review_rating AS ENUM ('again', 'hard', 'good', 'easy')")
    op.execute(
        "ALTER TABLE interview_card_progress "
        "ALTER COLUMN last_rating TYPE interview_review_rating "
        "USING last_rating::interview_review_rating"
    )
