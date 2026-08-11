"""Allow audited employment salary corrections.

Revision ID: 20260812_0050
Revises: 20260812_0049
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260812_0050"
down_revision: str | None = "20260812_0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "student_employment_salary_revisions",
        sa.Column("employment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("edited_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("previous_net_salary_kopecks", sa.BigInteger(), nullable=False),
        sa.Column("new_net_salary_kopecks", sa.BigInteger(), nullable=False),
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
        sa.CheckConstraint(
            "new_net_salary_kopecks > 0",
            name=op.f("ck_student_employment_salary_revisions_new_salary_positive"),
        ),
        sa.CheckConstraint(
            "previous_net_salary_kopecks > 0",
            name=op.f("ck_student_employment_salary_revisions_previous_salary_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["edited_by_user_id"],
            ["users.id"],
            name=op.f("fk_student_employment_salary_revisions_edited_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["employment_id"],
            ["student_employments.id"],
            name=op.f("fk_student_employment_salary_revisions_employment_id_student_employments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_student_employment_salary_revisions"),
        ),
    )
    op.create_index(
        "ix_student_employment_salary_revisions_employment_created",
        "student_employment_salary_revisions",
        ["employment_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_student_employment_salary_revisions_employment_created",
        table_name="student_employment_salary_revisions",
    )
    op.drop_table("student_employment_salary_revisions")
