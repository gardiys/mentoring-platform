from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Roadmap(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "roadmaps"
    __table_args__ = (CheckConstraint("position >= 0", name="position_non_negative"),)

    slug: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    sections = relationship(
        "RoadmapSection", back_populates="roadmap", order_by="RoadmapSection.position"
    )
    enrollments = relationship("RoadmapEnrollment", back_populates="roadmap")


class RoadmapSection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "roadmap_sections"
    __table_args__ = (
        CheckConstraint("position >= 0", name="position_non_negative"),
        CheckConstraint(
            "duration_days IS NULL OR duration_days > 0",
            name="duration_days_positive",
        ),
        Index("ix_roadmap_sections_position", "roadmap_id", "position"),
    )

    roadmap_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("roadmaps.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    roadmap = relationship("Roadmap", back_populates="sections")
    topics = relationship("Topic", back_populates="section", order_by="Topic.position")


class Topic(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "topics"
    __table_args__ = (
        CheckConstraint("position >= 0", name="position_non_negative"),
        CheckConstraint(
            "estimated_minutes IS NULL OR estimated_minutes > 0",
            name="estimated_minutes_positive",
        ),
        Index("ix_topics_section_position", "section_id", "position"),
    )

    section_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("roadmap_sections.id", ondelete="CASCADE"),
        nullable=False,
    )
    # A globally unique slug is deliberately stricter than uniqueness within a roadmap.
    slug: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    section = relationship("RoadmapSection", back_populates="topics")
    progress = relationship("TopicProgress", back_populates="topic")
    media = relationship(
        "ProtectedContentMedia",
        back_populates="roadmap_topic",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ProtectedContentMedia.position, ProtectedContentMedia.created_at",
        lazy="selectin",
    )


class RoadmapEnrollment(Base):
    __tablename__ = "roadmap_enrollments"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    roadmap_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("roadmaps.id", ondelete="CASCADE"), primary_key=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="enrollments")
    roadmap = relationship("Roadmap", back_populates="enrollments")
