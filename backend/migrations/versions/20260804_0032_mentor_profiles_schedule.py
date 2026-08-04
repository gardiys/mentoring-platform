"""Add mentor profiles and track schedule events.

Revision ID: 20260804_0032
Revises: 20260803_0031
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260804_0032"
down_revision: str | None = "20260803_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    event_kind = postgresql.ENUM(
        "weekly_call",
        "meeting",
        name="schedule_event_kind",
        create_type=False,
    )
    event_kind.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "mentor_profiles",
        sa.Column("mentor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("consultation_url", sa.String(length=2_048), nullable=True),
        sa.Column("group_calendar_url", sa.String(length=2_048), nullable=True),
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
        sa.ForeignKeyConstraint(["mentor_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("mentor_id"),
    )
    op.create_table(
        "pinned_resource_links",
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("url", sa.String(length=2_048), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
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
            "position >= 0",
            name="position_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_pinned_resource_links_position_title",
        "pinned_resource_links",
        ["position", "title"],
    )
    op.create_table(
        "schedule_events",
        sa.Column("track_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mentor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", event_kind, nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("meeting_url", sa.String(length=2_048), nullable=True),
        sa.Column("weekday", sa.SmallInteger(), nullable=True),
        sa.Column("starts_at_time", sa.Time(), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
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
            "weekday IS NULL OR (weekday >= 0 AND weekday <= 6)",
            name="weekday_range",
        ),
        sa.CheckConstraint(
            "(kind = 'weekly_call' AND weekday IS NOT NULL "
            "AND timezone IS NOT NULL AND starts_at IS NULL) "
            "OR (kind = 'meeting' AND starts_at IS NOT NULL "
            "AND weekday IS NULL AND starts_at_time IS NULL AND timezone IS NULL)",
            name="kind_fields_consistent",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["mentor_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["track_id"], ["learning_tracks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_schedule_events_track_kind",
        "schedule_events",
        ["track_id", "kind"],
    )
    op.create_index(
        "ix_schedule_events_mentor_kind",
        "schedule_events",
        ["mentor_id", "kind"],
    )
    op.create_index(
        "ix_schedule_events_starts_at",
        "schedule_events",
        ["starts_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_schedule_events_starts_at", table_name="schedule_events")
    op.drop_index("ix_schedule_events_mentor_kind", table_name="schedule_events")
    op.drop_index("ix_schedule_events_track_kind", table_name="schedule_events")
    op.drop_table("schedule_events")
    op.drop_index(
        "ix_pinned_resource_links_position_title",
        table_name="pinned_resource_links",
    )
    op.drop_table("pinned_resource_links")
    op.drop_table("mentor_profiles")
    postgresql.ENUM(name="schedule_event_kind").drop(op.get_bind(), checkfirst=True)
