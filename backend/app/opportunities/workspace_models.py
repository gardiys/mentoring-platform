from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class OpportunityHistory:
    old_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_status: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ConsultationRequestHistory(OpportunityHistory, UUIDPrimaryKeyMixin, Base):
    __tablename__ = "consultation_request_history"
    __table_args__ = (
        Index("ix_consultation_history_request_created", "consultation_request_id", "created_at"),
    )

    consultation_request_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("consultation_requests.id", ondelete="CASCADE"),
        nullable=False,
    )


class GoTransitionApplicationHistory(OpportunityHistory, UUIDPrimaryKeyMixin, Base):
    __tablename__ = "go_transition_application_history"
    __table_args__ = (
        Index("ix_go_transition_history_application_created", "application_id", "created_at"),
    )

    application_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("go_transition_applications.id", ondelete="CASCADE"),
        nullable=False,
    )
