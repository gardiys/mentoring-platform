"""Add a one-occurrence override to recurring schedule events.

Revision ID: 20260804_0034
Revises: 20260804_0033
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260804_0034"
down_revision: str | None = "20260804_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "schedule_events",
        sa.Column("rescheduled_from", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "schedule_events",
        sa.Column("rescheduled_to", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "reschedule_pair_consistent",
        "schedule_events",
        "(rescheduled_from IS NULL AND rescheduled_to IS NULL) OR "
        "(rescheduled_from IS NOT NULL AND rescheduled_to IS NOT NULL)",
    )
    op.create_check_constraint(
        "reschedule_kind_consistent",
        "schedule_events",
        "rescheduled_from IS NULL OR kind = 'weekly_call'",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_schedule_events_reschedule_kind_consistent"),
        "schedule_events",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_schedule_events_reschedule_pair_consistent"),
        "schedule_events",
        type_="check",
    )
    op.drop_column("schedule_events", "rescheduled_to")
    op.drop_column("schedule_events", "rescheduled_from")
