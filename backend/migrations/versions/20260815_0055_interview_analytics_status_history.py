"""Add interview offer timestamps and student status history.

Revision ID: 20260815_0055
Revises: 20260815_0054
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260815_0055"
down_revision: str | None = "20260815_0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "interview_processes",
        sa.Column("offer_received_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_interview_processes_offer_received",
        "interview_processes",
        ["offer_received_at"],
    )
    op.execute(
        """
        UPDATE interview_processes
        SET offer_received_at = COALESCE(closed_at, updated_at, created_at)
        WHERE status = 'offer' AND offer_received_at IS NULL
        """
    )

    op.create_table(
        "mentor_student_status_history",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "learning",
                "interviewing",
                "probation",
                "finished",
                name="student_learning_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("changed_by_user_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at",
            name=op.f("ck_mentor_student_status_history_valid_period"),
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["users.id"],
            name=op.f("fk_mentor_student_status_history_student_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["changed_by_user_id"],
            ["users.id"],
            name=op.f("fk_mentor_student_status_history_changed_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mentor_student_status_history")),
    )
    op.create_index(
        "ix_mentor_student_status_history_student_started",
        "mentor_student_status_history",
        ["student_id", "started_at"],
    )
    op.create_index(
        "uq_mentor_student_status_history_open",
        "mentor_student_status_history",
        ["student_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
    )
    op.execute(
        """
        INSERT INTO mentor_student_status_history (
            id, student_id, status, started_at, ended_at, changed_by_user_id
        )
        SELECT gen_random_uuid(), student_id, learning_status,
               COALESCE(status_updated_at, assigned_at, CURRENT_TIMESTAMP), NULL, mentor_id
        FROM mentor_students
        """
    )


def downgrade() -> None:
    op.drop_index(
        "uq_mentor_student_status_history_open",
        table_name="mentor_student_status_history",
    )
    op.drop_index(
        "ix_mentor_student_status_history_student_started",
        table_name="mentor_student_status_history",
    )
    op.drop_table("mentor_student_status_history")
    op.drop_index("ix_interview_processes_offer_received", table_name="interview_processes")
    op.drop_column("interview_processes", "offer_received_at")
