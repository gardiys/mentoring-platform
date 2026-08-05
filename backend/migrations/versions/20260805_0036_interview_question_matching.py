"""Add interview question matching metadata and automatic frequency controls.

Revision ID: 20260805_0036
Revises: 20260805_0035
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260805_0036"
down_revision: str | None = "20260805_0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    frequency_enum = postgresql.ENUM(
        "frequent",
        "occasional",
        name="interview_card_frequency",
        create_type=False,
    )
    op.add_column(
        "interview_cards",
        sa.Column("frequency_override", frequency_enum, nullable=True),
    )
    op.add_column(
        "interview_cards",
        sa.Column("question_embedding", postgresql.ARRAY(sa.Float()), nullable=True),
    )
    op.add_column(
        "interview_cards",
        sa.Column("question_embedding_model", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "interview_cards",
        sa.Column("question_embedding_dimensions", sa.Integer(), nullable=True),
    )
    op.add_column(
        "interview_cards",
        sa.Column("question_embedding_source_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "intelligence_questions",
        sa.Column("question_embedding", postgresql.ARRAY(sa.Float()), nullable=True),
    )
    op.add_column(
        "intelligence_questions",
        sa.Column("question_embedding_model", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "intelligence_questions",
        sa.Column("question_embedding_dimensions", sa.Integer(), nullable=True),
    )
    op.add_column(
        "intelligence_questions",
        sa.Column("question_embedding_source_hash", sa.String(length=64), nullable=True),
    )

    # Existing frequency labels came from curated imports or explicit admin choices.
    # Preserve them as manual overrides; newly created automatic cards leave this null.
    op.execute(
        sa.text(
            """
            UPDATE interview_cards
            SET frequency_override = frequency
            """
        )
    )

    # Frequency measures how many interviews contained the question. Older extraction
    # runs could produce two equivalent source questions in one interview, so retain
    # only the first occurrence before enforcing that invariant.
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    id,
                    row_number() OVER (
                        PARTITION BY card_id, interview_id
                        ORDER BY created_at, id
                    ) AS occurrence_number
                FROM interview_card_occurrences
                WHERE interview_id IS NOT NULL
            )
            DELETE FROM interview_card_occurrences AS occurrence
            USING ranked
            WHERE occurrence.id = ranked.id
              AND ranked.occurrence_number > 1
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE interview_cards AS card
            SET asked_count = (
                SELECT count(*)
                FROM interview_card_occurrences AS occurrence
                WHERE occurrence.card_id = card.id
            )
            """
        )
    )
    op.create_index(
        "uq_interview_card_occurrences_card_interview",
        "interview_card_occurrences",
        ["card_id", "interview_id"],
        unique=True,
        postgresql_where=sa.text("interview_id IS NOT NULL"),
    )
    op.create_index(
        "ix_intelligence_questions_published_card",
        "intelligence_questions",
        ["published_card_id"],
        postgresql_where=sa.text("published_card_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_intelligence_questions_published_card",
        table_name="intelligence_questions",
    )
    op.drop_index(
        "uq_interview_card_occurrences_card_interview",
        table_name="interview_card_occurrences",
    )
    op.drop_column("intelligence_questions", "question_embedding_source_hash")
    op.drop_column("intelligence_questions", "question_embedding_dimensions")
    op.drop_column("intelligence_questions", "question_embedding_model")
    op.drop_column("intelligence_questions", "question_embedding")
    op.drop_column("interview_cards", "question_embedding_source_hash")
    op.drop_column("interview_cards", "question_embedding_dimensions")
    op.drop_column("interview_cards", "question_embedding_model")
    op.drop_column("interview_cards", "question_embedding")
    op.drop_column("interview_cards", "frequency_override")
