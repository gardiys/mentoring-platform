"""Separate source rechecks and retain cache-write usage for accurate AI pricing."""

import sqlalchemy as sa
from alembic import op

revision = "20260922_0089"
down_revision = "20260921_0088"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("question_clusters", sa.Column("source_retry_after", sa.DateTime(timezone=True)))
    op.add_column("ai_request_logs", sa.Column("cache_write_tokens", sa.Integer()))


def downgrade() -> None:
    op.drop_column("ai_request_logs", "cache_write_tokens")
    op.drop_column("question_clusters", "source_retry_after")
