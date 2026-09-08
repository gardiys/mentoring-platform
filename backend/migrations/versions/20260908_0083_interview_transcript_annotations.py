"""Preserve grounded AI terminology hints separately from the original transcript."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260908_0083"
down_revision = "20260907_0082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "intelligence_questions",
        sa.Column("transcription_annotations", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("intelligence_questions", "transcription_annotations")
