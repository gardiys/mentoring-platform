"""Add per-direction calendars to mentor profiles.

Revision ID: 20260815_0061
Revises: 20260815_0060
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260815_0061"
down_revision: str | None = "20260815_0060"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mentor_track_calendars",
        sa.Column("mentor_id", sa.UUID(), nullable=False),
        sa.Column("track_id", sa.UUID(), nullable=False),
        sa.Column("calendar_url", sa.String(length=2_048), nullable=False),
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
        sa.ForeignKeyConstraint(["mentor_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["track_id"], ["learning_tracks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("mentor_id", "track_id"),
    )
    op.create_index(
        "ix_mentor_track_calendars_track",
        "mentor_track_calendars",
        ["track_id", "mentor_id"],
    )
    op.execute(
        """
        INSERT INTO mentor_track_calendars (mentor_id, track_id, calendar_url)
        SELECT profile.mentor_id, assignment.track_id, profile.group_calendar_url
        FROM mentor_profiles profile
        JOIN mentor_track_assignments assignment
          ON assignment.mentor_id = profile.mentor_id
        WHERE profile.group_calendar_url IS NOT NULL
        ON CONFLICT (mentor_id, track_id) DO NOTHING
        """
    )


def downgrade() -> None:
    # Keep one of the direction calendars available to the legacy application.
    op.execute(
        """
        UPDATE mentor_profiles AS profile
        SET group_calendar_url = calendar.calendar_url
        FROM (
            SELECT DISTINCT ON (mentor_id) mentor_id, calendar_url
            FROM mentor_track_calendars
            ORDER BY mentor_id, created_at, track_id
        ) AS calendar
        WHERE calendar.mentor_id = profile.mentor_id
          AND profile.group_calendar_url IS NULL
        """
    )
    op.drop_index(
        "ix_mentor_track_calendars_track",
        table_name="mentor_track_calendars",
    )
    op.drop_table("mentor_track_calendars")
