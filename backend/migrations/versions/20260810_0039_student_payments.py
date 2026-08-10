"""Add student payment schedules and mentor rewards.

Revision ID: 20260810_0039
Revises: 20260807_0038
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260810_0039"
down_revision: str | None = "20260807_0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    installment_status = postgresql.ENUM(
        "scheduled",
        "pending",
        "paid",
        name="payment_installment_status",
        create_type=False,
    )
    attempt_status = postgresql.ENUM(
        "pending",
        "approved",
        "failed",
        "cancelled",
        "manual_review",
        name="payment_attempt_status",
        create_type=False,
    )
    installment_status.create(op.get_bind(), checkfirst=True)
    attempt_status.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "users",
        sa.Column(
            "repayment_percent",
            sa.Numeric(precision=6, scale=2),
            server_default="200.00",
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE users AS u
        SET repayment_percent = 150.00
        WHERE u.role = 'student'
          AND EXISTS (
              SELECT 1
              FROM learning_track_enrollments AS e
              JOIN learning_tracks AS t ON t.id = e.track_id
              WHERE e.user_id = u.id AND lower(t.slug) = 'go'
          )
          AND NOT EXISTS (
              SELECT 1
              FROM learning_track_enrollments AS e
              JOIN learning_tracks AS t ON t.id = e.track_id
              WHERE e.user_id = u.id AND lower(t.slug) = 'python'
          )
        """
    )
    op.create_check_constraint(
        "repayment_percent_range",
        "users",
        "repayment_percent > 0 AND repayment_percent <= 1000",
    )
    op.add_column(
        "mentor_students",
        sa.Column("reward_percent", sa.Numeric(precision=6, scale=2), nullable=True),
    )
    op.create_check_constraint(
        "mentor_reward_percent_range",
        "mentor_students",
        "reward_percent IS NULL OR (reward_percent >= 0 AND reward_percent <= 100)",
    )

    op.create_table(
        "student_employments",
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("company_name", sa.String(length=240), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("net_salary_kopecks", sa.BigInteger(), nullable=False),
        sa.Column("repayment_percent", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("payment_day_first", sa.SmallInteger(), server_default="10", nullable=False),
        sa.Column("payment_day_second", sa.SmallInteger(), server_default="25", nullable=False),
        sa.Column("recorded_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.CheckConstraint("net_salary_kopecks > 0", name="net_salary_positive"),
        sa.CheckConstraint(
            "repayment_percent > 0 AND repayment_percent <= 1000",
            name="repayment_percent_range",
        ),
        sa.CheckConstraint(
            "payment_day_first >= 1 AND payment_day_first <= 28",
            name="payment_day_first_range",
        ),
        sa.CheckConstraint(
            "payment_day_second >= 1 AND payment_day_second <= 28",
            name="payment_day_second_range",
        ),
        sa.CheckConstraint(
            "payment_day_first < payment_day_second", name="payment_days_ordered"
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", name="uq_student_employments_student"),
    )
    op.create_index(
        "ix_student_employments_start_date", "student_employments", ["start_date"]
    )
    op.create_table(
        "payment_installments",
        sa.Column("employment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("amount_kopecks", sa.BigInteger(), nullable=False),
        sa.Column(
            "status", installment_status, server_default="scheduled", nullable=False
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.CheckConstraint("amount_kopecks > 0", name="amount_positive"),
        sa.CheckConstraint("sequence_number > 0", name="sequence_positive"),
        sa.ForeignKeyConstraint(
            ["confirmed_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["employment_id"], ["student_employments.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "employment_id", "sequence_number", name="uq_payment_installments_sequence"
        ),
    )
    op.create_index(
        "ix_payment_installments_due_status",
        "payment_installments",
        ["due_date", "status"],
    )
    op.create_table(
        "payment_attempts",
        sa.Column("installment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), server_default="tochka", nullable=False),
        sa.Column("payment_link_id", sa.String(length=64), nullable=False),
        sa.Column("provider_operation_id", sa.String(length=255), nullable=True),
        sa.Column("status", attempt_status, server_default="pending", nullable=False),
        sa.Column("payment_url", sa.Text(), nullable=True),
        sa.Column("raw_create_response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
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
            ["installment_id"], ["payment_installments.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_link_id", name="uq_payment_attempts_link_id"),
        sa.UniqueConstraint(
            "provider_operation_id", name="uq_payment_attempts_provider_operation_id"
        ),
    )
    op.create_index(
        "ix_payment_attempts_installment_created",
        "payment_attempts",
        ["installment_id", "created_at"],
    )
    op.create_index(
        "ix_payment_attempts_operation", "payment_attempts", ["provider_operation_id"]
    )
    op.create_table(
        "payment_webhook_events",
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=True),
        sa.Column("deduplication_key", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["attempt_id"], ["payment_attempts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "deduplication_key", name="uq_payment_webhook_events_dedupe"
        ),
    )
    op.create_index(
        "ix_payment_webhook_events_attempt", "payment_webhook_events", ["attempt_id"]
    )
    op.create_table(
        "mentor_rewards",
        sa.Column("installment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mentor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reward_percent", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("amount_kopecks", sa.BigInteger(), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("amount_kopecks >= 0", name="amount_non_negative"),
        sa.ForeignKeyConstraint(
            ["installment_id"], ["payment_installments.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["mentor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("installment_id", name="uq_mentor_rewards_installment"),
    )
    op.create_index(
        "ix_mentor_rewards_mentor_created", "mentor_rewards", ["mentor_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_mentor_rewards_mentor_created", table_name="mentor_rewards")
    op.drop_table("mentor_rewards")
    op.drop_index("ix_payment_webhook_events_attempt", table_name="payment_webhook_events")
    op.drop_table("payment_webhook_events")
    op.drop_index("ix_payment_attempts_operation", table_name="payment_attempts")
    op.drop_index("ix_payment_attempts_installment_created", table_name="payment_attempts")
    op.drop_table("payment_attempts")
    op.drop_index("ix_payment_installments_due_status", table_name="payment_installments")
    op.drop_table("payment_installments")
    op.drop_index("ix_student_employments_start_date", table_name="student_employments")
    op.drop_table("student_employments")
    op.drop_constraint(
        "ck_mentor_students_mentor_reward_percent_range",
        "mentor_students",
        type_="check",
    )
    op.drop_column("mentor_students", "reward_percent")
    op.drop_constraint(
        "ck_users_repayment_percent_range", "users", type_="check"
    )
    op.drop_column("users", "repayment_percent")
    postgresql.ENUM(name="payment_attempt_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="payment_installment_status").drop(op.get_bind(), checkfirst=True)
