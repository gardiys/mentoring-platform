"""Add alumni opportunities, consultations and Python to Go applications.

Revision ID: 20260830_0070
Revises: 20260830_0069
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260830_0070"
down_revision: str | None = "20260830_0069"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    consultation_status = postgresql.ENUM(
        "requested",
        "payment_pending",
        "paid",
        "scheduled",
        "completed",
        "cancelled",
        name="consultation_status",
    )
    transition_status = postgresql.ENUM(
        "submitted",
        "approved",
        "payment_pending",
        "paid",
        "rejected",
        "cancelled",
        name="go_transition_status",
    )
    consultation_status.create(op.get_bind(), checkfirst=True)
    transition_status.create(op.get_bind(), checkfirst=True)
    op.execute("ALTER TYPE mentor_reward_kind ADD VALUE IF NOT EXISTS 'consultation'")

    op.create_table(
        "program_completions",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("track_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["track_id"], ["learning_tracks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "track_id"),
    )
    op.execute(
        """
        INSERT INTO program_completions (user_id, track_id, completed_at)
        SELECT DISTINCT e.user_id, e.track_id,
               COALESCE(s.status_updated_at, ms.status_updated_at, now())
        FROM learning_track_enrollments e
        LEFT JOIN student_mentorship_states s ON s.student_id = e.user_id
        LEFT JOIN mentor_students ms ON ms.student_id = e.user_id
        WHERE s.learning_status = 'finished' OR ms.learning_status = 'finished'
        ON CONFLICT (user_id, track_id) DO NOTHING
        """
    )

    op.create_table(
        "consultation_requests",
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mentor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brief", sa.Text(), nullable=False),
        sa.Column("price_kopecks", sa.BigInteger(), nullable=False),
        sa.Column("mentor_reward_kopecks", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="consultation_status", create_type=False),
            nullable=False,
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column("written_summary", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("mentor_reward_kopecks >= 0", name="mentor_reward_non_negative"),
        sa.CheckConstraint("price_kopecks > 0", name="price_positive"),
        sa.ForeignKeyConstraint(["mentor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_consultation_requests_student_created",
        "consultation_requests",
        ["student_id", "created_at"],
    )
    op.create_index(
        "ix_consultation_requests_status_created",
        "consultation_requests",
        ["status", "created_at"],
    )

    op.create_table(
        "go_transition_applications",
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("motivation", sa.Text(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="go_transition_status", create_type=False),
            nullable=False,
        ),
        sa.Column("upfront_price_kopecks", sa.BigInteger(), nullable=False),
        sa.Column("success_fee_percent", sa.Integer(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "success_fee_percent > 0 AND success_fee_percent <= 1000",
            name="success_fee_percent_range",
        ),
        sa.CheckConstraint("upfront_price_kopecks > 0", name="upfront_price_positive"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_go_transition_applications_student_created",
        "go_transition_applications",
        ["student_id", "created_at"],
    )
    op.create_index(
        "ix_go_transition_applications_status_created",
        "go_transition_applications",
        ["status", "created_at"],
    )
    op.create_index(
        "uq_go_transition_applications_active_student",
        "go_transition_applications",
        ["student_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('submitted', 'approved', 'payment_pending', 'paid')"
        ),
    )

    op.create_table(
        "opportunity_payment_attempts",
        sa.Column("consultation_request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("transition_application_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("payment_link_id", sa.String(length=64), nullable=False),
        sa.Column("provider_operation_id", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(name="payment_attempt_status", create_type=False),
            nullable=False,
        ),
        sa.Column("payment_url", sa.Text(), nullable=True),
        sa.Column("raw_create_response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "(consultation_request_id IS NOT NULL)::int + "
            "(transition_application_id IS NOT NULL)::int = 1",
            name="one_payable_resource",
        ),
        sa.ForeignKeyConstraint(
            ["consultation_request_id"], ["consultation_requests.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["transition_application_id"],
            ["go_transition_applications.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_link_id"),
        sa.UniqueConstraint("provider_operation_id"),
    )
    op.create_index(
        "ix_opportunity_payment_attempts_consultation",
        "opportunity_payment_attempts",
        ["consultation_request_id"],
    )
    op.create_index(
        "ix_opportunity_payment_attempts_transition",
        "opportunity_payment_attempts",
        ["transition_application_id"],
    )

    op.add_column(
        "payment_webhook_events",
        sa.Column("opportunity_attempt_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_webhook_events_opportunity_attempt",
        "payment_webhook_events",
        "opportunity_payment_attempts",
        ["opportunity_attempt_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "mentor_rewards",
        sa.Column("consultation_request_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_mentor_rewards_consultation_request_id",
        "mentor_rewards",
        ["consultation_request_id"],
    )
    op.create_foreign_key(
        "fk_mentor_rewards_consultation",
        "mentor_rewards",
        "consultation_requests",
        ["consultation_request_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_mentor_rewards_consultation",
        "mentor_rewards",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_mentor_rewards_consultation_request_id", "mentor_rewards", type_="unique"
    )
    op.drop_column("mentor_rewards", "consultation_request_id")
    op.drop_constraint(
        "fk_webhook_events_opportunity_attempt",
        "payment_webhook_events",
        type_="foreignkey",
    )
    op.drop_column("payment_webhook_events", "opportunity_attempt_id")
    op.drop_index(
        "ix_opportunity_payment_attempts_transition", table_name="opportunity_payment_attempts"
    )
    op.drop_index(
        "ix_opportunity_payment_attempts_consultation", table_name="opportunity_payment_attempts"
    )
    op.drop_table("opportunity_payment_attempts")
    op.drop_index(
        "uq_go_transition_applications_active_student",
        table_name="go_transition_applications",
    )
    op.drop_index(
        "ix_go_transition_applications_status_created",
        table_name="go_transition_applications",
    )
    op.drop_index(
        "ix_go_transition_applications_student_created",
        table_name="go_transition_applications",
    )
    op.drop_table("go_transition_applications")
    op.drop_index("ix_consultation_requests_status_created", table_name="consultation_requests")
    op.drop_index("ix_consultation_requests_student_created", table_name="consultation_requests")
    op.drop_table("consultation_requests")
    op.drop_table("program_completions")
    postgresql.ENUM(name="go_transition_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="consultation_status").drop(op.get_bind(), checkfirst=True)
    # PostgreSQL enum values cannot be safely removed during downgrade.
