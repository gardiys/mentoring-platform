"""Add personal topic selection for interview decks."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260801_0007"
down_revision: str | None = "20260731_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE interview_cards SET category = 'Общее' WHERE category IS NULL")
    op.alter_column("interview_cards", "category", existing_type=sa.String(240), nullable=False)
    op.create_table(
        "interview_topic_selections",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deck_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(240), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["deck_id"],
            ["interview_decks.id"],
            ondelete="CASCADE",
            name="fk_interview_topic_selections_deck_id_interview_decks",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_interview_topic_selections_user_id_users",
        ),
        sa.PrimaryKeyConstraint(
            "user_id", "deck_id", "category", name="pk_interview_topic_selections"
        ),
    )


def downgrade() -> None:
    op.drop_table("interview_topic_selections")
    op.alter_column("interview_cards", "category", existing_type=sa.String(240), nullable=True)
