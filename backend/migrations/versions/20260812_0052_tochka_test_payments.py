"""Add isolated admin Tochka test payments.

Revision ID: 20260812_0052
Revises: 20260812_0051
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260812_0052"
down_revision: str | None = "20260812_0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    payment_status = postgresql.ENUM(
        "pending",
        "approved",
        "failed",
        "cancelled",
        "manual_review",
        "revoked",
        name="payment_attempt_status",
        create_type=False,
    )
    op.create_table(
        "tochka_test_payments",
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("amount_kopecks", sa.BigInteger(), nullable=False),
        sa.Column("payment_link_id", sa.String(length=64), nullable=False),
        sa.Column("provider_operation_id", sa.String(length=255), nullable=True),
        sa.Column("status", payment_status, nullable=False),
        sa.Column("payment_url", sa.Text(), nullable=True),
        sa.Column("raw_create_response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "amount_kopecks = 1000",
            name=op.f("ck_tochka_test_payments_amount_is_ten_rubles"),
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
            name=op.f("fk_tochka_test_payments_requested_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tochka_test_payments")),
        sa.UniqueConstraint(
            "payment_link_id",
            name="uq_tochka_test_payments_link_id",
        ),
        sa.UniqueConstraint(
            "provider_operation_id",
            name="uq_tochka_test_payments_provider_operation_id",
        ),
    )
    op.create_index(
        "ix_tochka_test_payments_admin_created",
        "tochka_test_payments",
        ["requested_by_user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tochka_test_payments_admin_created",
        table_name="tochka_test_payments",
    )
    op.drop_table("tochka_test_payments")
