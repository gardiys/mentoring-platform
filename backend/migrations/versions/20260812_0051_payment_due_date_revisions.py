"""Add audited payment due date changes.

Revision ID: 20260812_0051
Revises: 20260812_0050
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260812_0051"
down_revision: str | None = "20260812_0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payment_installment_due_date_revisions",
        sa.Column("installment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("changed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("previous_due_date", sa.Date(), nullable=False),
        sa.Column("new_due_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["changed_by_user_id"],
            ["users.id"],
            name=op.f("fk_payment_installment_due_date_revisions_changed_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["installment_id"],
            ["payment_installments.id"],
            name=op.f(
                "fk_payment_installment_due_date_revisions_installment_id_payment_installments"
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_payment_installment_due_date_revisions"),
        ),
    )
    op.create_index(
        "ix_payment_installment_due_date_revisions_installment_created",
        "payment_installment_due_date_revisions",
        ["installment_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_payment_installment_due_date_revisions_installment_created",
        table_name="payment_installment_due_date_revisions",
    )
    op.drop_table("payment_installment_due_date_revisions")
