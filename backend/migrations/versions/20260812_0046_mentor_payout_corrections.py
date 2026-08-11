"""Audit mentor payout edits and reversals.

Revision ID: 20260812_0046
Revises: 20260811_0045
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260812_0046"
down_revision: str | None = "20260811_0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "mentor_payouts",
        sa.Column("edited_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "mentor_payouts",
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "mentor_payouts",
        sa.Column("edit_reason", sa.String(length=500), nullable=True),
    )
    op.create_foreign_key(
        "fk_mentor_payouts_edited_by_user_id_users",
        "mentor_payouts",
        "users",
        ["edited_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "mentor_payout_revisions",
        sa.Column("payout_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("edited_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("previous_amount_kopecks", sa.BigInteger(), nullable=False),
        sa.Column("new_amount_kopecks", sa.BigInteger(), nullable=False),
        sa.Column("previous_payment_reference", sa.String(length=500), nullable=True),
        sa.Column("new_payment_reference", sa.String(length=500), nullable=True),
        sa.Column("previous_paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("new_paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.ForeignKeyConstraint(["payout_id"], ["mentor_payouts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["edited_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_mentor_payout_revisions_payout_created",
        "mentor_payout_revisions",
        ["payout_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mentor_payout_revisions_payout_created",
        table_name="mentor_payout_revisions",
    )
    op.drop_table("mentor_payout_revisions")
    op.drop_constraint(
        "fk_mentor_payouts_edited_by_user_id_users",
        "mentor_payouts",
        type_="foreignkey",
    )
    op.drop_column("mentor_payouts", "edit_reason")
    op.drop_column("mentor_payouts", "edited_at")
    op.drop_column("mentor_payouts", "edited_by_user_id")
