"""Audit revocations of incorrectly confirmed student payments.

Revision ID: 20260811_0044
Revises: 20260811_0043
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260811_0044"
down_revision: str | None = "20260811_0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE payment_attempt_status ADD VALUE IF NOT EXISTS 'revoked'")

    op.add_column(
        "payment_installments",
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "payment_installments",
        sa.Column("revoked_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "payment_installments",
        sa.Column("revocation_reason", sa.String(length=500), nullable=True),
    )
    op.create_foreign_key(
        "fk_payment_installments_revoked_by_user_id_users",
        "payment_installments",
        "users",
        ["revoked_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_payment_installments_revoked_by_user_id_users",
        "payment_installments",
        type_="foreignkey",
    )
    op.drop_column("payment_installments", "revocation_reason")
    op.drop_column("payment_installments", "revoked_by_user_id")
    op.drop_column("payment_installments", "revoked_at")
