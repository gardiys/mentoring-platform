"""Bounded reconsideration of old card blockers under the new evidence policy."""

import sqlalchemy as sa
from alembic import op

revision = "20260922_0092"
down_revision = "20260922_0091"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE answer_contract_status ADD VALUE IF NOT EXISTS 'review_pending'")
    # Existing rows are reconsidered once; future rows start on the current policy.
    op.add_column(
        "question_clusters",
        sa.Column(
            "review_policy_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.alter_column("question_clusters", "review_policy_version", server_default="1")


def downgrade() -> None:
    op.execute(
        "UPDATE question_clusters SET answer_status='needs_manual_review' "
        "WHERE answer_status='review_pending'"
    )
    op.drop_column("question_clusters", "review_policy_version")
