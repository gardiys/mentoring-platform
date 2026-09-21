"""Persist personal weekday recruiter selections and invitation feedback."""

import sqlalchemy as sa
from alembic import op

revision = "20260921_0087"
down_revision = "20260910_0086"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE recruiter_feedback_kind ADD VALUE IF NOT EXISTS 'invited'")
    op.create_table(
        "recruiter_daily_batches",
        sa.Column(
            "user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "recruiter_daily_assignments",
        sa.Column("user_id", sa.UUID(), primary_key=True),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column(
            "recruiter_id",
            sa.UUID(),
            sa.ForeignKey("recruiter_contacts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id", "day"],
            ["recruiter_daily_batches.user_id", "recruiter_daily_batches.day"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("user_id", "recruiter_id", name="uq_recruiter_assignment_user_contact"),
        sa.UniqueConstraint("user_id", "day", "position", name="uq_recruiter_assignment_position"),
        sa.CheckConstraint("position BETWEEN 1 AND 10", name="recruiter_assignment_position_range"),
    )
    op.create_index(
        "ix_recruiter_assignment_day_contact",
        "recruiter_daily_assignments",
        ["day", "recruiter_id"],
    )


def downgrade() -> None:
    op.drop_table("recruiter_daily_assignments")
    op.drop_table("recruiter_daily_batches")
    op.execute("UPDATE recruiter_feedback SET kind='helpful' WHERE kind='invited'")
    op.execute("ALTER TABLE recruiter_feedback ALTER COLUMN kind TYPE text USING kind::text")
    op.execute("DROP TYPE recruiter_feedback_kind")
    op.execute(
        "CREATE TYPE recruiter_feedback_kind AS ENUM "
        "('helpful','ignores','no_longer_works','account_missing','other')"
    )
    op.execute(
        "ALTER TABLE recruiter_feedback ALTER COLUMN kind TYPE recruiter_feedback_kind "
        "USING kind::recruiter_feedback_kind"
    )
