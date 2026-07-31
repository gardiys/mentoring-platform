from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

SEARCH_VECTOR_SQL = """
setweight(to_tsvector('russian'::regconfig, coalesce(title, '')), 'A') ||
setweight(to_tsvector('russian'::regconfig, coalesce(summary, '')), 'B') ||
setweight(to_tsvector('russian'::regconfig, coalesce(content_markdown, '')), 'C')
"""


class KnowledgeEntryKind(StrEnum):
    ARTICLE = "article"
    QUESTION = "question"


class KnowledgeTopic(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_topics"
    __table_args__ = (CheckConstraint("position >= 0", name="position_non_negative"),)

    slug: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    entries = relationship(
        "KnowledgeEntry",
        back_populates="topic",
        cascade="all, delete-orphan",
        order_by="KnowledgeEntry.position",
    )


class KnowledgeEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_entries"
    __table_args__ = (
        CheckConstraint("position >= 0", name="position_non_negative"),
        Index("ix_knowledge_entries_topic_position", "topic_id", "position"),
        Index("ix_knowledge_entries_search_vector", "search_vector", postgresql_using="gin"),
    )

    topic_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge_topics.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[KnowledgeEntryKind] = mapped_column(
        Enum(
            KnowledgeEntryKind,
            name="knowledge_entry_kind",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(SEARCH_VECTOR_SQL, persisted=True),
        nullable=False,
    )

    topic = relationship("KnowledgeTopic", back_populates="entries")
