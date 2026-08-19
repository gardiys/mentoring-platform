"""Add audited canonical interview-card duplicate reviews.

Revision ID: 20260817_0065
Revises: 20260816_0064
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260817_0065"
down_revision: str | None = "20260816_0064"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "interview_card_duplicate_reviews",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("left_card_id", sa.UUID(), nullable=False),
        sa.Column("right_card_id", sa.UUID(), nullable=False),
        sa.Column("primary_card_id", sa.UUID(), nullable=True),
        sa.Column("decision", sa.String(length=24), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("left_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("right_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("merge_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reviewed_by_user_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "decision IN ('merged', 'not_duplicate')",
            name=op.f("ck_interview_card_duplicate_reviews_decision_supported"),
        ),
        sa.CheckConstraint(
            "left_card_id <> right_card_id",
            name=op.f("ck_interview_card_duplicate_reviews_different_cards"),
        ),
        sa.CheckConstraint(
            "similarity >= 0 AND similarity <= 1",
            name=op.f("ck_interview_card_duplicate_reviews_similarity_range"),
        ),
        sa.ForeignKeyConstraint(
            ["left_card_id"],
            ["interview_cards.id"],
            name=op.f("fk_interview_card_duplicate_reviews_left_card_id_interview_cards"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["primary_card_id"],
            ["interview_cards.id"],
            name=op.f("fk_interview_card_duplicate_reviews_primary_card_id_interview_cards"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"],
            ["users.id"],
            name=op.f("fk_interview_card_duplicate_reviews_reviewed_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["right_card_id"],
            ["interview_cards.id"],
            name=op.f("fk_interview_card_duplicate_reviews_right_card_id_interview_cards"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interview_card_duplicate_reviews")),
        sa.UniqueConstraint(
            "left_card_id",
            "right_card_id",
            name=op.f("uq_interview_card_duplicate_reviews_reviewed_pair"),
        ),
    )
    op.create_index(
        "ix_interview_card_duplicate_reviews_created",
        "interview_card_duplicate_reviews",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_interview_card_duplicate_reviews_created",
        table_name="interview_card_duplicate_reviews",
    )
    op.drop_table("interview_card_duplicate_reviews")
