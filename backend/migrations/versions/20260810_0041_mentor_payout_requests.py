"""Add aggregated mentor payouts and payout requests.

Revision ID: 20260810_0041
Revises: 20260810_0040
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260810_0041"
down_revision: str | None = "20260810_0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    payout_status = postgresql.ENUM(
        "requested",
        "paid",
        "cancelled",
        name="mentor_payout_status",
        create_type=False,
    )
    payout_origin = postgresql.ENUM(
        "mentor_request",
        "admin_direct",
        name="mentor_payout_origin",
        create_type=False,
    )
    payout_status.create(op.get_bind(), checkfirst=True)
    payout_origin.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "mentor_rewards",
        sa.Column("paid_kopecks", sa.BigInteger(), server_default="0", nullable=False),
    )
    op.execute(
        "UPDATE mentor_rewards SET paid_kopecks = amount_kopecks WHERE paid_at IS NOT NULL"
    )
    op.create_check_constraint(
        "paid_amount_range",
        "mentor_rewards",
        "paid_kopecks >= 0 AND paid_kopecks <= amount_kopecks",
    )

    op.create_table(
        "mentor_payouts",
        sa.Column("mentor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount_kopecks", sa.BigInteger(), nullable=False),
        sa.Column("origin", payout_origin, nullable=False),
        sa.Column("status", payout_status, nullable=False),
        sa.Column("payment_reference", sa.String(length=500), nullable=True),
        sa.Column("paid_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.String(length=500), nullable=True),
        sa.Column("receipt_storage_key", sa.String(length=500), nullable=True),
        sa.Column("receipt_filename", sa.String(length=500), nullable=True),
        sa.Column("receipt_content_type", sa.String(length=160), nullable=True),
        sa.Column("receipt_size", sa.BigInteger(), nullable=True),
        sa.Column("receipt_uploaded_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("amount_kopecks > 0", name="amount_positive"),
        sa.ForeignKeyConstraint(["mentor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["paid_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["cancelled_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_mentor_payouts_mentor_created",
        "mentor_payouts",
        ["mentor_id", "created_at"],
    )
    op.create_index(
        "ix_mentor_payouts_status_created",
        "mentor_payouts",
        ["status", "created_at"],
    )
    op.create_index(
        "uq_mentor_payouts_open_mentor",
        "mentor_payouts",
        ["mentor_id"],
        unique=True,
        postgresql_where=sa.text("status = 'requested'"),
    )

    op.create_table(
        "mentor_payout_allocations",
        sa.Column("payout_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reward_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount_kopecks", sa.BigInteger(), nullable=False),
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
        sa.CheckConstraint("amount_kopecks > 0", name="amount_positive"),
        sa.ForeignKeyConstraint(
            ["payout_id"], ["mentor_payouts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["reward_id"], ["mentor_rewards.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "payout_id",
            "reward_id",
            name="uq_mentor_payout_allocations_pair",
        ),
    )
    op.create_index(
        "ix_mentor_payout_allocations_reward",
        "mentor_payout_allocations",
        ["reward_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mentor_payout_allocations_reward",
        table_name="mentor_payout_allocations",
    )
    op.drop_table("mentor_payout_allocations")
    op.drop_index("uq_mentor_payouts_open_mentor", table_name="mentor_payouts")
    op.drop_index("ix_mentor_payouts_status_created", table_name="mentor_payouts")
    op.drop_index("ix_mentor_payouts_mentor_created", table_name="mentor_payouts")
    op.drop_table("mentor_payouts")

    op.drop_constraint(
        "ck_mentor_rewards_paid_amount_range",
        "mentor_rewards",
        type_="check",
    )
    op.drop_column("mentor_rewards", "paid_kopecks")
    postgresql.ENUM(name="mentor_payout_origin").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="mentor_payout_status").drop(op.get_bind(), checkfirst=True)
