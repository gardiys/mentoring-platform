"""Grounded communication feedback and revision-scoped practice progress.

Revision ID: 20260929_0094
Revises: 20260922_0093
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260929_0094"
down_revision = "20260922_0093"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table, name, default in [
        ("intelligence_answer_reviews", "delivery_assessment", "[]"),
        ("intelligence_interviews", "candidate_questions", "[]"),
        ("intelligence_interviews", "coaching_state", "{}"),
    ]:
        op.add_column(
            table,
            sa.Column(
                name,
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'" + default + "'::jsonb"),
            ),
        )


def downgrade() -> None:
    op.drop_column("intelligence_interviews", "coaching_state")
    op.drop_column("intelligence_interviews", "candidate_questions")
    op.drop_column("intelligence_answer_reviews", "delivery_assessment")
