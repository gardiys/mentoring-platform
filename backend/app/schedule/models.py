from __future__ import annotations

from datetime import datetime, time
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    Time,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ScheduleEventKind(StrEnum):
    WEEKLY_CALL = "weekly_call"
    MEETING = "meeting"


class MentorProfile(TimestampMixin, Base):
    __tablename__ = "mentor_profiles"

    mentor_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    consultation_url: Mapped[str | None] = mapped_column(String(2_048), nullable=True)
    group_calendar_url: Mapped[str | None] = mapped_column(String(2_048), nullable=True)


class MentorTrackCalendar(TimestampMixin, Base):
    __tablename__ = "mentor_track_calendars"
    __table_args__ = (Index("ix_mentor_track_calendars_track", "track_id", "mentor_id"),)

    mentor_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    track_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("learning_tracks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    calendar_url: Mapped[str] = mapped_column(String(2_048), nullable=False)


class PinnedResourceLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "pinned_resource_links"
    __table_args__ = (
        CheckConstraint("position >= 0", name="position_non_negative"),
        Index("ix_pinned_resource_links_position_title", "position", "title"),
    )

    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(String(2_048), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ScheduleEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "schedule_events"
    __table_args__ = (
        CheckConstraint(
            "weekday IS NULL OR (weekday >= 0 AND weekday <= 6)",
            name="weekday_range",
        ),
        CheckConstraint(
            "(kind = 'weekly_call' AND weekday IS NOT NULL "
            "AND timezone IS NOT NULL AND starts_at IS NULL) "
            "OR (kind = 'meeting' AND starts_at IS NOT NULL "
            "AND weekday IS NULL AND starts_at_time IS NULL AND timezone IS NULL)",
            name="kind_fields_consistent",
        ),
        CheckConstraint(
            "(rescheduled_from IS NULL AND rescheduled_to IS NULL) OR "
            "(rescheduled_from IS NOT NULL AND rescheduled_to IS NOT NULL)",
            name="reschedule_pair_consistent",
        ),
        CheckConstraint(
            "rescheduled_from IS NULL OR kind = 'weekly_call'",
            name="reschedule_kind_consistent",
        ),
        Index("ix_schedule_events_track_kind", "track_id", "kind"),
        Index("ix_schedule_events_mentor_kind", "mentor_id", "kind"),
        Index("ix_schedule_events_starts_at", "starts_at"),
    )

    track_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("learning_tracks.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    mentor_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    kind: Mapped[ScheduleEventKind] = mapped_column(
        Enum(
            ScheduleEventKind,
            name="schedule_event_kind",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    meeting_url: Mapped[str | None] = mapped_column(String(2_048), nullable=True)
    weekday: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    starts_at_time: Mapped[time | None] = mapped_column(Time(), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rescheduled_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rescheduled_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
