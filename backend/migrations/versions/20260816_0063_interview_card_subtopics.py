"""Add optional subtopics without changing broad card grouping.

Revision ID: 20260816_0063
Revises: 20260816_0062
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260816_0063"
down_revision: str | None = "20260816_0062"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "interview_cards",
        sa.Column("subcategory", sa.String(length=240), nullable=True),
    )
    op.add_column(
        "question_clusters",
        sa.Column("subtopic_name", sa.String(length=240), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("question_clusters", "subtopic_name")
    op.drop_column("interview_cards", "subcategory")
