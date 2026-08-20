"""Add indexed full-text search for interview cards.

Revision ID: 20260819_0067
Revises: 20260819_0066
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260819_0067"
down_revision: str | None = "20260819_0066"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEARCH_VECTOR_SQL = """
setweight(to_tsvector('russian'::regconfig, coalesce(question_markdown, '')), 'A') ||
setweight(to_tsvector('russian'::regconfig, coalesce(category, '')), 'B') ||
setweight(to_tsvector('russian'::regconfig, coalesce(subcategory, '')), 'B') ||
setweight(to_tsvector('russian'::regconfig, coalesce(answer_markdown, '')), 'C') ||
setweight(to_tsvector('simple'::regconfig, coalesce(question_markdown, '')), 'A') ||
setweight(to_tsvector('simple'::regconfig, coalesce(category, '')), 'B') ||
setweight(to_tsvector('simple'::regconfig, coalesce(subcategory, '')), 'B') ||
setweight(to_tsvector('simple'::regconfig, coalesce(answer_markdown, '')), 'C')
"""


def upgrade() -> None:
    op.add_column(
        "interview_cards",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(SEARCH_VECTOR_SQL, persisted=True),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_interview_cards_search_vector",
        "interview_cards",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_interview_cards_search_vector", table_name="interview_cards")
    op.drop_column("interview_cards", "search_vector")
