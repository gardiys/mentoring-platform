"""Add the versioned Python repeat mentorship product.

Revision ID: 20260831_0074
Revises: 20260831_0073
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260831_0074"
down_revision: str | None = "20260831_0073"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[object]]:
    return [
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
    ]


def upgrade() -> None:
    application_status = postgresql.ENUM(
        "draft",
        "submitted",
        "under_review",
        "needs_diagnostic",
        "needs_clarification",
        "approved",
        "rejected",
        "terms_accepted",
        "payment_pending",
        "paid",
        "enrolled",
        "cancelled",
        "expired",
        name="python_repeat_application_status",
        create_type=False,
    )
    employment_status = postgresql.ENUM(
        "employed",
        "unemployed",
        "on_probation",
        "notice_period",
        "career_break",
        "other",
        name="python_repeat_employment_status",
        create_type=False,
    )
    reason = postgresql.ENUM(
        "lost_job",
        "failed_probation",
        "wants_higher_salary",
        "wants_new_company",
        "returning_after_break",
        "technical_refresh",
        "other",
        name="python_repeat_reason",
        create_type=False,
    )
    search_mode = postgresql.ENUM(
        "active_search",
        "search_while_employed",
        "not_ready_to_search",
        name="python_repeat_search_mode",
        create_type=False,
    )
    enrollment_status = postgresql.ENUM(
        "active",
        "completed",
        "cancelled",
        name="python_repeat_enrollment_status",
        create_type=False,
    )
    offer_status = postgresql.ENUM(
        "draft",
        "submitted",
        "under_review",
        "verified",
        "rejected",
        "cancelled",
        name="python_repeat_offer_status",
        create_type=False,
    )
    obligation_status = postgresql.ENUM(
        "active",
        "paid",
        "cancelled",
        name="python_repeat_obligation_status",
        create_type=False,
    )
    installment_status = postgresql.ENUM(
        "scheduled",
        "pending",
        "paid",
        "refunded",
        "cancelled",
        name="python_repeat_installment_status",
        create_type=False,
    )
    for enum in (
        application_status,
        employment_status,
        reason,
        search_mode,
        enrollment_status,
        offer_status,
        obligation_status,
        installment_status,
    ):
        enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "python_repeat_product_offers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("upfront_price_kopecks", sa.BigInteger(), nullable=False),
        sa.Column("success_fee_percent", sa.Integer(), nullable=False),
        sa.Column("success_fee_installments_count", sa.Integer(), nullable=False),
        sa.Column("mentor_fixed_accrual_kopecks", sa.BigInteger(), nullable=False),
        sa.Column("mentor_success_fee_share_percent", sa.Integer(), nullable=False),
        sa.Column("active_support_months", sa.Integer(), nullable=False),
        sa.Column("probation_support_days", sa.Integer(), nullable=False),
        sa.Column("included_mock_interviews", sa.Integer(), nullable=False),
        sa.Column("offer_valid_days", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("upfront_price_kopecks > 0", name="upfront_price_positive"),
        sa.CheckConstraint("success_fee_percent > 0", name="success_fee_percent_positive"),
        sa.CheckConstraint("success_fee_installments_count > 0", name="installments_positive"),
        sa.CheckConstraint("mentor_fixed_accrual_kopecks >= 0", name="fixed_accrual_non_negative"),
        sa.CheckConstraint(
            "mentor_success_fee_share_percent BETWEEN 0 AND 100", name="mentor_share_range"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version", name="uq_python_repeat_offer_version"),
    )
    op.create_index(
        "uq_python_repeat_offer_active",
        "python_repeat_product_offers",
        ["is_active"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )
    offer_table = sa.table(
        "python_repeat_product_offers",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("version", sa.Integer()),
        sa.column("is_active", sa.Boolean()),
        sa.column("upfront_price_kopecks", sa.BigInteger()),
        sa.column("success_fee_percent", sa.Integer()),
        sa.column("success_fee_installments_count", sa.Integer()),
        sa.column("mentor_fixed_accrual_kopecks", sa.BigInteger()),
        sa.column("mentor_success_fee_share_percent", sa.Integer()),
        sa.column("active_support_months", sa.Integer()),
        sa.column("probation_support_days", sa.Integer()),
        sa.column("included_mock_interviews", sa.Integer()),
        sa.column("offer_valid_days", sa.Integer()),
        sa.column("valid_from", sa.DateTime(timezone=True)),
        sa.column("valid_until", sa.DateTime(timezone=True)),
    )
    now = datetime.now(UTC)
    op.bulk_insert(
        offer_table,
        [
            {
                "id": uuid4(),
                "version": 1,
                "is_active": False,
                "upfront_price_kopecks": 2_000_000,
                "success_fee_percent": 50,
                "success_fee_installments_count": 2,
                "mentor_fixed_accrual_kopecks": 1_000_000,
                "mentor_success_fee_share_percent": 30,
                "active_support_months": 4,
                "probation_support_days": 30,
                "included_mock_interviews": 2,
                "offer_valid_days": 14,
                "valid_from": now,
                "valid_until": now,
            },
            {
                "id": uuid4(),
                "version": 2,
                "is_active": True,
                "upfront_price_kopecks": 3_000_000,
                "success_fee_percent": 100,
                "success_fee_installments_count": 4,
                "mentor_fixed_accrual_kopecks": 1_000_000,
                "mentor_success_fee_share_percent": 30,
                "active_support_months": 4,
                "probation_support_days": 30,
                "included_mock_interviews": 2,
                "offer_valid_days": 14,
                "valid_from": now,
                "valid_until": None,
            },
        ],
    )

    op.create_table(
        "python_repeat_applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employment_status", employment_status, nullable=False),
        sa.Column("reason", reason, nullable=False),
        sa.Column("current_position", sa.String(240), nullable=True),
        sa.Column("current_company", sa.String(240), nullable=True),
        sa.Column("current_stack", sa.Text(), nullable=True),
        sa.Column("last_interview_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("target_position", sa.String(240), nullable=False),
        sa.Column("target_salary_kopecks", sa.BigInteger(), nullable=True),
        sa.Column("technical_gaps", sa.Text(), nullable=False),
        sa.Column("hours_per_week", sa.Integer(), nullable=False),
        sa.Column("desired_start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("search_mode", search_mode, nullable=False),
        sa.Column("additional_comment", sa.Text(), nullable=True),
        sa.Column("status", application_status, nullable=False),
        sa.Column("responsible_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("eligibility_override_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("eligibility_override_reason", sa.Text(), nullable=True),
        sa.Column("admin_comment", sa.Text(), nullable=True),
        sa.Column("product_offer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("terms_version", sa.Integer(), nullable=True),
        sa.Column("terms_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("offer_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("acceptance_ip_address", sa.String(64), nullable=True),
        sa.Column("acceptance_user_agent", sa.String(500), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["responsible_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["eligibility_override_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["product_offer_id"], ["python_repeat_product_offers.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["accepted_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_python_repeat_applications_student_created",
        "python_repeat_applications",
        ["student_id", "created_at"],
    )
    op.create_index(
        "ix_python_repeat_applications_status_created",
        "python_repeat_applications",
        ["status", "created_at"],
    )
    op.create_index(
        "uq_python_repeat_application_active_student",
        "python_repeat_applications",
        ["student_id"],
        unique=True,
        postgresql_where=sa.text("status NOT IN ('rejected', 'cancelled', 'expired', 'enrolled')"),
    )

    op.create_table(
        "python_repeat_application_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("old_status", application_status, nullable=True),
        sa.Column("new_status", application_status, nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(100), nullable=True),
        sa.Column("snapshot", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["application_id"], ["python_repeat_applications.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_python_repeat_history_application_created",
        "python_repeat_application_history",
        ["application_id", "created_at"],
    )

    op.create_table(
        "python_repeat_enrollments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("track_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("previous_track_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mentor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("mentor_assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mentor_assigned_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", enrollment_status, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("personal_plan_markdown", sa.Text(), nullable=True),
        sa.Column("terms_snapshot", postgresql.JSONB(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["application_id"], ["python_repeat_applications.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["track_id"], ["learning_tracks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["previous_track_id"], ["learning_tracks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["mentor_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["mentor_assigned_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("application_id", name="uq_python_repeat_enrollment_application"),
    )
    op.create_index(
        "ix_python_repeat_enrollment_student_created",
        "python_repeat_enrollments",
        ["student_id", "created_at"],
    )
    op.create_index(
        "uq_python_repeat_enrollment_active_student",
        "python_repeat_enrollments",
        ["student_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "python_repeat_employment_offers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("enrollment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.String(240), nullable=False),
        sa.Column("company", sa.String(240), nullable=False),
        sa.Column("technology_direction", sa.String(80), nullable=False),
        sa.Column("fixed_monthly_salary_kopecks", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("employment_type", sa.String(100), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expected_start_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", offer_status, nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("verification_comment", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["enrollment_id"], ["python_repeat_enrollments.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["verified_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_python_repeat_offers_enrollment_created",
        "python_repeat_employment_offers",
        ["enrollment_id", "created_at"],
    )

    op.create_table(
        "python_repeat_success_fee_obligations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("enrollment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("verified_offer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("salary_base_kopecks", sa.BigInteger(), nullable=False),
        sa.Column("success_fee_percent", sa.Integer(), nullable=False),
        sa.Column("total_amount_kopecks", sa.BigInteger(), nullable=False),
        sa.Column("installments_count", sa.Integer(), nullable=False),
        sa.Column("status", obligation_status, nullable=False),
        sa.Column("terms_snapshot", postgresql.JSONB(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("total_amount_kopecks > 0", name="total_positive"),
        sa.ForeignKeyConstraint(
            ["enrollment_id"], ["python_repeat_enrollments.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["verified_offer_id"], ["python_repeat_employment_offers.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("verified_offer_id", name="uq_python_repeat_obligation_offer"),
    )
    op.create_table(
        "python_repeat_installments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("obligation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("amount_kopecks", sa.BigInteger(), nullable=False),
        sa.Column("salary_percent", sa.Integer(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", installment_status, nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_received_kopecks", sa.BigInteger(), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("amount_kopecks > 0", name="amount_positive"),
        sa.ForeignKeyConstraint(
            ["obligation_id"], ["python_repeat_success_fee_obligations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "obligation_id", "sequence_number", name="uq_python_repeat_installment_sequence"
        ),
    )
    op.create_index(
        "ix_python_repeat_installments_due_status",
        "python_repeat_installments",
        ["due_at", "status"],
    )

    op.create_table(
        "python_repeat_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_key", sa.String(240), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_key"),
    )

    op.drop_constraint("one_payable_resource", "opportunity_payment_attempts", type_="check")
    op.add_column(
        "opportunity_payment_attempts",
        sa.Column("python_repeat_application_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "opportunity_payment_attempts",
        sa.Column("python_repeat_installment_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_opportunity_attempt_repeat_application",
        "opportunity_payment_attempts",
        "python_repeat_applications",
        ["python_repeat_application_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_opportunity_attempt_repeat_installment",
        "opportunity_payment_attempts",
        "python_repeat_installments",
        ["python_repeat_installment_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "one_payable_resource",
        "opportunity_payment_attempts",
        "(consultation_request_id IS NOT NULL)::int + "
        "(transition_application_id IS NOT NULL)::int + "
        "(python_repeat_application_id IS NOT NULL)::int + "
        "(python_repeat_installment_id IS NOT NULL)::int = 1",
    )
    op.create_index(
        "ix_opportunity_payment_attempts_python_repeat",
        "opportunity_payment_attempts",
        ["python_repeat_application_id"],
    )
    op.create_index(
        "ix_opportunity_payment_attempts_python_installment",
        "opportunity_payment_attempts",
        ["python_repeat_installment_id"],
    )

    op.execute("ALTER TYPE mentor_reward_kind ADD VALUE IF NOT EXISTS 'python_repeat_fixed'")
    op.execute("ALTER TYPE mentor_reward_kind ADD VALUE IF NOT EXISTS 'python_repeat_success_fee'")
    op.add_column(
        "mentor_rewards",
        sa.Column("python_repeat_enrollment_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "mentor_rewards",
        sa.Column("python_repeat_installment_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_mentor_reward_repeat_enrollment",
        "mentor_rewards",
        "python_repeat_enrollments",
        ["python_repeat_enrollment_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_mentor_reward_repeat_installment",
        "mentor_rewards",
        "python_repeat_installments",
        ["python_repeat_installment_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_mentor_reward_repeat_enrollment", "mentor_rewards", ["python_repeat_enrollment_id"]
    )
    op.create_unique_constraint(
        "uq_mentor_reward_repeat_installment", "mentor_rewards", ["python_repeat_installment_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_mentor_reward_repeat_installment", "mentor_rewards", type_="unique")
    op.drop_constraint("uq_mentor_reward_repeat_enrollment", "mentor_rewards", type_="unique")
    op.drop_constraint("fk_mentor_reward_repeat_installment", "mentor_rewards", type_="foreignkey")
    op.drop_constraint("fk_mentor_reward_repeat_enrollment", "mentor_rewards", type_="foreignkey")
    op.drop_column("mentor_rewards", "python_repeat_installment_id")
    op.drop_column("mentor_rewards", "python_repeat_enrollment_id")
    op.drop_index(
        "ix_opportunity_payment_attempts_python_installment",
        table_name="opportunity_payment_attempts",
    )
    op.drop_index(
        "ix_opportunity_payment_attempts_python_repeat", table_name="opportunity_payment_attempts"
    )
    op.drop_constraint("one_payable_resource", "opportunity_payment_attempts", type_="check")
    op.drop_constraint(
        "fk_opportunity_attempt_repeat_installment",
        "opportunity_payment_attempts",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_opportunity_attempt_repeat_application",
        "opportunity_payment_attempts",
        type_="foreignkey",
    )
    op.drop_column("opportunity_payment_attempts", "python_repeat_installment_id")
    op.drop_column("opportunity_payment_attempts", "python_repeat_application_id")
    op.create_check_constraint(
        "one_payable_resource",
        "opportunity_payment_attempts",
        "(consultation_request_id IS NOT NULL)::int + "
        "(transition_application_id IS NOT NULL)::int = 1",
    )
    for table in (
        "python_repeat_events",
        "python_repeat_installments",
        "python_repeat_success_fee_obligations",
        "python_repeat_employment_offers",
        "python_repeat_enrollments",
        "python_repeat_application_history",
        "python_repeat_applications",
        "python_repeat_product_offers",
    ):
        op.drop_table(table)
    for name in (
        "python_repeat_installment_status",
        "python_repeat_obligation_status",
        "python_repeat_offer_status",
        "python_repeat_enrollment_status",
        "python_repeat_search_mode",
        "python_repeat_reason",
        "python_repeat_employment_status",
        "python_repeat_application_status",
    ):
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)
