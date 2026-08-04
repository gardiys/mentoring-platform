from __future__ import annotations

from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ProtectedContentMedia(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "protected_content_media"
    __table_args__ = (
        CheckConstraint(
            "(knowledge_entry_id IS NOT NULL) <> (roadmap_topic_id IS NOT NULL)",
            name="exactly_one_parent",
        ),
        CheckConstraint("size > 0", name="size_positive"),
        CheckConstraint("position >= 0", name="position_non_negative"),
        Index(
            "ix_protected_content_media_knowledge_position",
            "knowledge_entry_id",
            "position",
        ),
        Index(
            "ix_protected_content_media_roadmap_position",
            "roadmap_topic_id",
            "position",
        ),
    )

    knowledge_entry_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge_entries.id", ondelete="CASCADE"),
        nullable=True,
    )
    roadmap_topic_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("topics.id", ondelete="CASCADE"),
        nullable=True,
    )
    uploaded_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    storage_key: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(160), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str | None] = mapped_column(String(240), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    knowledge_entry = relationship("KnowledgeEntry", back_populates="media")
    roadmap_topic = relationship("Topic", back_populates="media")
    uploaded_by = relationship("User")
