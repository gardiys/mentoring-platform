"""Store student mentorship state independently from mentor assignment.

Revision ID: 20260815_0056
Revises: 20260815_0055
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260815_0056"
down_revision: str | None = "20260815_0055"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "student_mentorship_states",
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column(
            "learning_status",
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
        sa.Column(
            "strength_level",
            postgresql.ENUM(
                "weak",
                "medium",
                "strong",
                name="student_strength_level",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "status_updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["users.id"],
            name=op.f("fk_student_mentorship_states_student_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("student_id", name=op.f("pk_student_mentorship_states")),
    )
    op.execute(
        """
        INSERT INTO student_mentorship_states (
            student_id, learning_status, strength_level,
            status_updated_at, created_at, updated_at
        )
        SELECT users.id,
               COALESCE(mentor_students.learning_status, 'learning'::student_learning_status),
               mentor_students.strength_level,
               COALESCE(
                   mentor_students.status_updated_at,
                   users.learning_start_date::timestamp with time zone,
                   users.created_at,
                   CURRENT_TIMESTAMP
               ),
               CURRENT_TIMESTAMP,
               CURRENT_TIMESTAMP
        FROM users
        LEFT JOIN mentor_students ON mentor_students.student_id = users.id
        WHERE users.role = 'student'
        ON CONFLICT (student_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("student_mentorship_states")
