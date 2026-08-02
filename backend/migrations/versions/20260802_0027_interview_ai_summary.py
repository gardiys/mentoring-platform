"""Add interview summary and communication assessment payload."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260802_0027"
down_revision: str | None = "20260802_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "intelligence_interviews",
        sa.Column("ai_summary_payload", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "intelligence_interviews",
        sa.Column("ai_summary_model", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "intelligence_interviews",
        sa.Column("ai_summary_prompt_version", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "intelligence_interviews",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "intelligence_interviews",
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_intelligence_interviews_reviewed_by",
        "intelligence_interviews",
        "users",
        ["reviewed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        """
        UPDATE intelligence_interviews AS interview
        SET reviewed_at = now()
        WHERE EXISTS (
            SELECT 1
            FROM intelligence_questions AS question
            JOIN intelligence_answers AS answer ON answer.question_id = question.id
            JOIN intelligence_answer_reviews AS review ON review.answer_id = answer.id
            WHERE question.interview_id = interview.id
              AND review.source = 'ai'
              AND review.status IN ('approved', 'edited', 'rejected')
        )
          AND NOT EXISTS (
            SELECT 1
            FROM intelligence_questions AS question
            JOIN intelligence_answers AS answer ON answer.question_id = question.id
            JOIN intelligence_answer_reviews AS review ON review.answer_id = answer.id
            WHERE question.interview_id = interview.id
              AND review.source = 'ai'
              AND review.status = 'suggested'
        )
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_intelligence_interviews_reviewed_by", "intelligence_interviews", type_="foreignkey"
    )
    op.drop_column("intelligence_interviews", "reviewed_by_user_id")
    op.drop_column("intelligence_interviews", "reviewed_at")
    op.drop_column("intelligence_interviews", "ai_summary_prompt_version")
    op.drop_column("intelligence_interviews", "ai_summary_model")
    op.drop_column("intelligence_interviews", "ai_summary_payload")
