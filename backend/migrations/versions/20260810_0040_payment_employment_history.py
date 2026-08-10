"""Add employment history and one-time mentor rewards.

Revision ID: 20260810_0040
Revises: 20260810_0039
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260810_0040"
down_revision: str | None = "20260810_0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # PostgreSQL cannot use a newly added enum value until the transaction that
    # added it is committed. Alembic may run the entire upgrade chain in one
    # transaction on a fresh database, so commit this DDL explicitly.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE payment_installment_status ADD VALUE IF NOT EXISTS 'cancelled'")

    employment_status = postgresql.ENUM(
        "active",
        "terminated",
        name="student_employment_status",
        create_type=False,
    )
    reward_kind = postgresql.ENUM(
        "employment_payment",
        "entry_payment",
        "program_exclusion",
        name="mentor_reward_kind",
        create_type=False,
    )
    employment_status.create(op.get_bind(), checkfirst=True)
    reward_kind.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "users",
        sa.Column(
            "entry_payment_kopecks",
            sa.BigInteger(),
            server_default="4500000",
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column("entry_payment_paid_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("program_excluded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("program_exclusion_reason", sa.String(length=500), nullable=True),
    )
    op.create_check_constraint(
        "entry_payment_non_negative",
        "users",
        "entry_payment_kopecks >= 0",
    )

    op.add_column(
        "student_employments",
        sa.Column(
            "status",
            employment_status,
            server_default="active",
            nullable=False,
        ),
    )
    op.add_column("student_employments", sa.Column("ended_at", sa.Date(), nullable=True))
    op.add_column(
        "student_employments",
        sa.Column("end_reason", sa.String(length=500), nullable=True),
    )
    op.drop_constraint(
        "uq_student_employments_student",
        "student_employments",
        type_="unique",
    )
    op.create_index(
        "uq_student_employments_active_student",
        "student_employments",
        ["student_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.add_column(
        "payment_installments",
        sa.Column("salary_percent", sa.Numeric(precision=6, scale=2), nullable=True),
    )
    op.execute(
        """
        UPDATE payment_installments AS installment
        SET salary_percent = round(
            installment.amount_kopecks::numeric * 100
            / employment.net_salary_kopecks,
            2
        )
        FROM student_employments AS employment
        WHERE employment.id = installment.employment_id
        """
    )
    op.alter_column("payment_installments", "salary_percent", nullable=False)

    op.add_column(
        "mentor_rewards",
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "mentor_rewards",
        sa.Column(
            "kind",
            reward_kind,
            server_default="employment_payment",
            nullable=False,
        ),
    )
    op.add_column(
        "mentor_rewards",
        sa.Column("basis_kopecks", sa.BigInteger(), nullable=True),
    )
    op.execute(
        """
        UPDATE mentor_rewards AS reward
        SET student_id = employment.student_id,
            basis_kopecks = installment.amount_kopecks,
            amount_kopecks = round(
                installment.amount_kopecks::numeric * reward.reward_percent
                / student.repayment_percent
            )
        FROM payment_installments AS installment
        JOIN student_employments AS employment ON employment.id = installment.employment_id
        JOIN users AS student ON student.id = employment.student_id
        WHERE installment.id = reward.installment_id
        """
    )
    op.alter_column("mentor_rewards", "student_id", nullable=False)
    op.alter_column("mentor_rewards", "installment_id", nullable=True)
    op.alter_column("mentor_rewards", "reward_percent", nullable=True)
    op.create_foreign_key(
        "fk_mentor_rewards_student_id_users",
        "mentor_rewards",
        "users",
        ["student_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "basis_non_negative",
        "mentor_rewards",
        "basis_kopecks IS NULL OR basis_kopecks >= 0",
    )
    op.create_check_constraint(
        "reward_percent_range",
        "mentor_rewards",
        "reward_percent IS NULL OR (reward_percent >= 0 AND reward_percent <= 100)",
    )
    op.create_index(
        "uq_mentor_rewards_one_time_student_kind",
        "mentor_rewards",
        ["student_id", "kind"],
        unique=True,
        postgresql_where=sa.text("kind IN ('entry_payment', 'program_exclusion')"),
    )

    op.execute(
        """
        UPDATE mentor_students AS relation
        SET reward_percent = CASE
            WHEN EXISTS (
                SELECT 1
                FROM learning_track_enrollments AS enrollment
                JOIN learning_tracks AS track ON track.id = enrollment.track_id
                WHERE enrollment.user_id = relation.student_id
                  AND lower(track.slug) = 'go'
            ) AND NOT EXISTS (
                SELECT 1
                FROM learning_track_enrollments AS enrollment
                JOIN learning_tracks AS track ON track.id = enrollment.track_id
                WHERE enrollment.user_id = relation.student_id
                  AND lower(track.slug) = 'python'
            ) THEN 45.00
            ELSE 60.00
        END
        WHERE relation.reward_percent IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index(
        "uq_mentor_rewards_one_time_student_kind",
        table_name="mentor_rewards",
    )
    op.drop_constraint(
        "ck_mentor_rewards_reward_percent_range",
        "mentor_rewards",
        type_="check",
    )
    op.drop_constraint(
        "ck_mentor_rewards_basis_non_negative",
        "mentor_rewards",
        type_="check",
    )
    op.execute("DELETE FROM mentor_rewards WHERE installment_id IS NULL")
    op.drop_constraint(
        "fk_mentor_rewards_student_id_users",
        "mentor_rewards",
        type_="foreignkey",
    )
    op.alter_column("mentor_rewards", "reward_percent", nullable=False)
    op.alter_column("mentor_rewards", "installment_id", nullable=False)
    op.drop_column("mentor_rewards", "basis_kopecks")
    op.drop_column("mentor_rewards", "kind")
    op.drop_column("mentor_rewards", "student_id")

    op.drop_column("payment_installments", "salary_percent")

    op.drop_index(
        "uq_student_employments_active_student",
        table_name="student_employments",
    )
    op.execute(
        """
        DELETE FROM student_employments AS employment
        USING student_employments AS newer
        WHERE employment.student_id = newer.student_id
          AND (
              employment.created_at < newer.created_at
              OR (
                  employment.created_at = newer.created_at
                  AND employment.id < newer.id
              )
          )
        """
    )
    op.create_unique_constraint(
        "uq_student_employments_student",
        "student_employments",
        ["student_id"],
    )
    op.drop_column("student_employments", "end_reason")
    op.drop_column("student_employments", "ended_at")
    op.drop_column("student_employments", "status")

    op.drop_constraint("ck_users_entry_payment_non_negative", "users", type_="check")
    op.drop_column("users", "program_exclusion_reason")
    op.drop_column("users", "program_excluded_at")
    op.drop_column("users", "entry_payment_paid_at")
    op.drop_column("users", "entry_payment_kopecks")

    postgresql.ENUM(name="mentor_reward_kind").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="student_employment_status").drop(op.get_bind(), checkfirst=True)

    op.execute("UPDATE payment_installments SET status = 'scheduled' WHERE status = 'cancelled'")
    op.alter_column("payment_installments", "status", server_default=None)
    op.alter_column(
        "payment_installments",
        "status",
        type_=sa.String(),
        postgresql_using="status::text",
    )
    postgresql.ENUM(name="payment_installment_status").drop(op.get_bind(), checkfirst=True)
    old_status = postgresql.ENUM(
        "scheduled",
        "pending",
        "paid",
        name="payment_installment_status",
        create_type=False,
    )
    old_status.create(op.get_bind(), checkfirst=True)
    op.alter_column(
        "payment_installments",
        "status",
        type_=old_status,
        postgresql_using="status::payment_installment_status",
        server_default="scheduled",
    )
