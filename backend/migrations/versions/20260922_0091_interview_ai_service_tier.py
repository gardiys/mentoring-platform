"""Allow explicit economy processing of an interview analysis revision."""

import sqlalchemy as sa
from alembic import op

revision = "20260922_0091"
down_revision = "20260922_0090"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "intelligence_interviews",
        sa.Column("ai_service_tier", sa.String(16), nullable=False, server_default="default"),
    )


def downgrade() -> None:
    op.drop_column("intelligence_interviews", "ai_service_tier")
