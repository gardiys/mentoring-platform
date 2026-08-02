"""Track interview question occurrences and their companies.

Revision ID: 20260802_0030
Revises: 20260802_0029
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260802_0030"
down_revision: str | None = "20260802_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "interview_cards",
        sa.Column("asked_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_check_constraint(
        "asked_count_non_negative",
        "interview_cards",
        "asked_count >= 0",
    )
    op.create_table(
        "interview_card_occurrences",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("card_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_question_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("interview_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("process_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("company_name", sa.String(length=240), nullable=False),
        sa.Column("asked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["card_id"], ["interview_cards.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_question_id"],
            ["intelligence_questions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["interview_id"], ["intelligence_interviews.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["process_id"], ["interview_processes.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_question_id",
            name="uq_interview_card_occurrence_source_question",
        ),
    )
    op.create_index(
        "ix_interview_card_occurrences_card_asked",
        "interview_card_occurrences",
        ["card_id", "asked_at"],
    )
    op.create_index(
        "ix_interview_card_occurrences_company",
        "interview_card_occurrences",
        ["company_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_interview_card_occurrences_company",
        table_name="interview_card_occurrences",
    )
    op.drop_index(
        "ix_interview_card_occurrences_card_asked",
        table_name="interview_card_occurrences",
    )
    op.drop_table("interview_card_occurrences")
    op.drop_constraint(
        "asked_count_non_negative",
        "interview_cards",
        type_="check",
    )
    op.drop_column("interview_cards", "asked_count")
