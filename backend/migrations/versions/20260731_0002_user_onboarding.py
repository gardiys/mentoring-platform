"""Add user onboarding state."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260731_0002"
down_revision: str | None = "20260731_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(sa.text("UPDATE users SET onboarding_completed_at = CURRENT_TIMESTAMP"))


def downgrade() -> None:
    op.drop_column("users", "onboarding_completed_at")
