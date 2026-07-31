"""Add interview decks, cards and spaced-repetition progress."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260731_0005"
down_revision: str | None = "20260731_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

card_frequency = postgresql.ENUM(
    "frequent",
    "occasional",
    name="interview_card_frequency",
    create_type=False,
)
review_rating = postgresql.ENUM(
    "again",
    "hard",
    "good",
    "easy",
    name="interview_review_rating",
    create_type=False,
)


def upgrade() -> None:
    card_frequency.create(op.get_bind(), checkfirst=True)
    review_rating.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "interview_decks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("track_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(160), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("position >= 0", name="ck_interview_decks_position_non_negative"),
        sa.ForeignKeyConstraint(
            ["track_id"],
            ["learning_tracks.id"],
            ondelete="CASCADE",
            name="fk_interview_decks_track_id_learning_tracks",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_interview_decks"),
        sa.UniqueConstraint("slug", name="uq_interview_decks_slug"),
    )
    op.create_index(
        "ix_interview_decks_track_position", "interview_decks", ["track_id", "position"]
    )
    op.create_table(
        "interview_cards",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deck_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(180), nullable=False),
        sa.Column("question_markdown", sa.Text(), nullable=False),
        sa.Column("answer_markdown", sa.Text(), nullable=False),
        sa.Column("frequency", card_frequency, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("position >= 0", name="ck_interview_cards_position_non_negative"),
        sa.ForeignKeyConstraint(
            ["deck_id"],
            ["interview_decks.id"],
            ondelete="CASCADE",
            name="fk_interview_cards_deck_id_interview_decks",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_interview_cards"),
        sa.UniqueConstraint("slug", name="uq_interview_cards_slug"),
    )
    op.create_index("ix_interview_cards_deck_position", "interview_cards", ["deck_id", "position"])
    op.create_table(
        "interview_card_progress",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("card_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repetitions", sa.Integer(), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("ease_factor", sa.Float(), nullable=False),
        sa.Column("lapses", sa.Integer(), nullable=False),
        sa.Column(
            "due_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("first_learned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_rating", review_rating, nullable=True),
        sa.CheckConstraint(
            "ease_factor >= 1.3", name="ck_interview_card_progress_ease_factor_minimum"
        ),
        sa.CheckConstraint(
            "interval_days >= 0", name="ck_interview_card_progress_interval_days_non_negative"
        ),
        sa.CheckConstraint("lapses >= 0", name="ck_interview_card_progress_lapses_non_negative"),
        sa.CheckConstraint(
            "repetitions >= 0", name="ck_interview_card_progress_repetitions_non_negative"
        ),
        sa.ForeignKeyConstraint(
            ["card_id"],
            ["interview_cards.id"],
            ondelete="CASCADE",
            name="fk_interview_card_progress_card_id_interview_cards",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_interview_card_progress_user_id_users",
        ),
        sa.PrimaryKeyConstraint("user_id", "card_id", name="pk_interview_card_progress"),
    )
    op.create_index(
        "ix_interview_card_progress_user_due",
        "interview_card_progress",
        ["user_id", "due_at"],
    )


def downgrade() -> None:
    op.drop_table("interview_card_progress")
    op.drop_table("interview_cards")
    op.drop_table("interview_decks")
    review_rating.drop(op.get_bind(), checkfirst=True)
    card_frequency.drop(op.get_bind(), checkfirst=True)
