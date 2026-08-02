"""Integrate AI analysis with interview journal and question cards."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260802_0028"
down_revision: str | None = "20260802_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    moderation_status = postgresql.ENUM(
        "pending",
        "mentor_approved",
        "approved",
        "rejected",
        name="intelligence_question_moderation_status",
    )
    moderation_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "interview_process_stages",
        sa.Column("ai_analysis_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        UPDATE interview_process_stages AS stage
        SET ai_analysis_requested_at = interview.created_at
        FROM intelligence_interviews AS interview
        WHERE interview.stage_id = stage.id
        """
    )

    op.add_column(
        "intelligence_questions",
        sa.Column(
            "moderation_status",
            moderation_status,
            server_default="pending",
            nullable=False,
        ),
    )
    op.add_column(
        "intelligence_questions",
        sa.Column("mentor_reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "intelligence_questions",
        sa.Column("mentor_reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "intelligence_questions",
        sa.Column("admin_reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "intelligence_questions",
        sa.Column("admin_reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "intelligence_questions",
        sa.Column("published_card_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_intelligence_questions_mentor_reviewer",
        "intelligence_questions",
        "users",
        ["mentor_reviewed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_intelligence_questions_admin_reviewer",
        "intelligence_questions",
        "users",
        ["admin_reviewed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_intelligence_questions_published_card",
        "intelligence_questions",
        "interview_cards",
        ["published_card_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.alter_column("interview_stage_comments", "user_id", nullable=True)
    op.drop_constraint(
        "fk_interview_stage_comments_user_id_users",
        "interview_stage_comments",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_interview_stage_comments_user_id_users",
        "interview_stage_comments",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "interview_stage_comments",
        sa.Column("is_ai_feedback", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "interview_stage_comments",
        sa.Column("intelligence_interview_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_interview_stage_comments_intelligence_interview",
        "interview_stage_comments",
        "intelligence_interviews",
        ["intelligence_interview_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_interview_stage_comments_intelligence_interview",
        "interview_stage_comments",
        ["intelligence_interview_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_interview_stage_comments_intelligence_interview",
        "interview_stage_comments",
        type_="unique",
    )
    op.drop_constraint(
        "fk_interview_stage_comments_intelligence_interview",
        "interview_stage_comments",
        type_="foreignkey",
    )
    op.drop_column("interview_stage_comments", "intelligence_interview_id")
    op.drop_column("interview_stage_comments", "is_ai_feedback")
    op.drop_constraint(
        "fk_interview_stage_comments_user_id_users",
        "interview_stage_comments",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_interview_stage_comments_user_id_users",
        "interview_stage_comments",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.execute("DELETE FROM interview_stage_comments WHERE user_id IS NULL")
    op.alter_column("interview_stage_comments", "user_id", nullable=False)

    op.drop_constraint(
        "fk_intelligence_questions_published_card", "intelligence_questions", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_intelligence_questions_admin_reviewer", "intelligence_questions", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_intelligence_questions_mentor_reviewer", "intelligence_questions", type_="foreignkey"
    )
    op.drop_column("intelligence_questions", "published_card_id")
    op.drop_column("intelligence_questions", "admin_reviewed_at")
    op.drop_column("intelligence_questions", "admin_reviewed_by_user_id")
    op.drop_column("intelligence_questions", "mentor_reviewed_at")
    op.drop_column("intelligence_questions", "mentor_reviewed_by_user_id")
    op.drop_column("intelligence_questions", "moderation_status")
    postgresql.ENUM(name="intelligence_question_moderation_status").drop(
        op.get_bind(), checkfirst=True
    )
    op.drop_column("interview_process_stages", "ai_analysis_requested_at")
