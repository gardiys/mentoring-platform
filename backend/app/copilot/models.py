from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CopilotSession(Base):
    """Durable usage and upload linkage, independent of transcript retention."""

    __tablename__ = "copilot_sessions"
    tenant_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    student_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    process_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("interview_processes.id", ondelete="SET NULL")
    )
    stage_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("interview_process_stages.id", ondelete="SET NULL")
    )
    mode: Mapped[str] = mapped_column(String(10))
    track: Mapped[str] = mapped_column(String(20))
    state: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active_ms: Mapped[int] = mapped_column(BigInteger, default=0)
    revision: Mapped[int] = mapped_column(Integer, default=0)
