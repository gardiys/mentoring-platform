"""Configure consultation duration and Go transition description.

Revision ID: 20260831_0073
Revises: 20260831_0072
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260831_0073"
down_revision: str | None = "20260831_0072"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_GO_DESCRIPTION = """## Что входит в программу

- язык Go, его идиомы, типизация и работа с ошибками;
- goroutine, каналы, конкурентность и устройство runtime;
- разработка backend-сервисов, базы данных и production-практики;
- поддержка ментора, практика и подготовка к Go-собеседованиям;
- сопровождение до выхода на Go-оффер по условиям программы.
"""


def upgrade() -> None:
    op.add_column(
        "consultation_type_settings",
        sa.Column(
            "duration_minutes",
            sa.Integer(),
            server_default="60",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "duration_minutes_range",
        "consultation_type_settings",
        "duration_minutes >= 15 AND duration_minutes <= 480",
    )
    op.add_column(
        "consultation_requests",
        sa.Column(
            "duration_minutes",
            sa.Integer(),
            server_default="60",
            nullable=False,
        ),
    )
    op.create_table(
        "go_transition_program_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("description_markdown", sa.Text(), nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.CheckConstraint("id = 1", name="singleton_id"),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    settings = sa.table(
        "go_transition_program_settings",
        sa.column("id", sa.Integer()),
        sa.column("description_markdown", sa.Text()),
    )
    op.bulk_insert(
        settings,
        [{"id": 1, "description_markdown": DEFAULT_GO_DESCRIPTION}],
    )


def downgrade() -> None:
    op.drop_table("go_transition_program_settings")
    op.drop_column("consultation_requests", "duration_minutes")
    op.drop_constraint(
        "duration_minutes_range",
        "consultation_type_settings",
        type_="check",
    )
    op.drop_column("consultation_type_settings", "duration_minutes")
