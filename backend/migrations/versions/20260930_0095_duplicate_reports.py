"""User reports of duplicate interview cards.

Revision ID: 20260930_0095
Revises: 20260929_0094
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260930_0095"
down_revision = "20260929_0094"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interview_card_duplicate_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "card_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("interview_cards.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "reported_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column(
            "reviewed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "primary_card_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("interview_cards.id", ondelete="SET NULL"),
        ),
        sa.UniqueConstraint("card_id", "reported_by_user_id", name="uq_card_duplicate_report_user"),
        sa.CheckConstraint(
            "status IN ('pending', 'dismissed', 'merged')",
            name="valid_status",
        ),
    )
    op.create_index(
        "ix_card_duplicate_reports_status_created",
        "interview_card_duplicate_reports",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("interview_card_duplicate_reports")
