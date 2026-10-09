"""Retain card AI reservations independently of deletable interview content."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261007_0097"
down_revision = "20261001_0096"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "card_ai_charges",
        sa.Column("request_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cluster_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("interview_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("amount_usd", sa.Numeric(18, 10), nullable=False),
        sa.Column("validation_reserve_usd", sa.Numeric(18, 10), server_default="0", nullable=False),
    )
    for column in ("cluster_id", "interview_id", "created_at"):
        op.create_index(f"ix_card_ai_charges_{column}", "card_ai_charges", [column])


def downgrade():
    op.drop_table("card_ai_charges")
