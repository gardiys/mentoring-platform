"""Versioned offers and immutable purchase evidence; email rows are a transactional outbox."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class LegalOfferVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "legal_offer_versions"
    __table_args__ = (
        UniqueConstraint("product_code", "version_code", name="uq_legal_offer_version"),
        Index(
            "uq_legal_offer_active",
            "product_code",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        CheckConstraint(
            "status IN ('draft','active','retired','revoked')", name="legal_offer_status"
        ),
    )
    product_code: Mapped[str] = mapped_column(String(64))
    version_code: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    publication_date: Mapped[date] = mapped_column(Date)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="draft")
    pdf_storage_key: Mapped[str] = mapped_column(String(500))
    markdown_storage_key: Mapped[str | None] = mapped_column(String(500))
    pdf_sha256: Mapped[str] = mapped_column(String(64))
    markdown_sha256: Mapped[str | None] = mapped_column(String(64))
    pdf_size: Mapped[int] = mapped_column(Integer)
    pdf_mime_type: Mapped[str] = mapped_column(String(64), default="application/pdf")
    financial_terms: Mapped[dict[str, Any]] = mapped_column(JSONB)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LegalCheckout(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "legal_checkouts"
    __table_args__ = (
        Index(
            "uq_legal_checkout_pending",
            "application_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        CheckConstraint(
            "status IN ('pending','paid','cancelled','expired')", name="legal_checkout_status"
        ),
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    product_code: Mapped[str] = mapped_column(String(64))
    application_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    offer_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("legal_offer_versions.id", ondelete="RESTRICT")
    )
    payment_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("opportunity_payment_attempts.id", ondelete="RESTRICT"),
        unique=True,
    )
    status: Mapped[str] = mapped_column(String(16), default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)


class ContractAcceptance(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contract_acceptances"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','terminated','refunded','disputed')", name="contract_status"
        ),
    )
    public_number: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    product_code: Mapped[str] = mapped_column(String(64))
    offer_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("legal_offer_versions.id", ondelete="RESTRICT")
    )
    checkout_session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("legal_checkouts.id", ondelete="RESTRICT"), unique=True
    )
    payment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("opportunity_payment_attempts.id", ondelete="RESTRICT"),
        unique=True,
    )
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    provider_paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    webhook_received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    acceptance_snapshot_sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="active")


class LegalEmailDelivery(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "legal_email_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "contract_id", "notification_type", "attempt_number", name="uq_legal_email_attempt"
        ),
        Index("ix_legal_email_due", "status", "next_attempt_at"),
        CheckConstraint(
            "status IN ('pending','processing','sent','delivered','bounced','failed')",
            name="legal_email_status",
        ),
    )
    contract_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("contract_acceptances.id", ondelete="RESTRICT")
    )
    notification_type: Mapped[str] = mapped_column(String(32), default="contract.confirmation")
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    recipient_email: Mapped[str] = mapped_column(String(320))
    subject_snapshot: Mapped[str] = mapped_column(String(500))
    body_snapshot: Mapped[str] = mapped_column(Text)
    attachment_sha256: Mapped[str | None] = mapped_column(String(64))
    provider_message_id: Mapped[str | None] = mapped_column(String(500), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bounced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    safe_error_message: Mapped[str | None] = mapped_column(String(200))


class LegalEmailVerification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "legal_email_verifications"
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    email: Mapped[str] = mapped_column(String(320))
    code_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LegalAuditEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "legal_audit_events"
    actor_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    resource_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    provider_event_id: Mapped[str | None] = mapped_column(String(255), unique=True)


class LegalQuestionnaireDraft(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "legal_questionnaire_drafts"
    __table_args__ = (
        UniqueConstraint("user_id", "product_code", name="uq_legal_questionnaire_draft"),
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    product_code: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    answers: Mapped[dict[str, Any]] = mapped_column(JSONB)


# Application guard complements the migration's database triggers (including bulk SQL).


def _immutable_update(mapper: Any, connection: Any, target: Any) -> None:
    allowed = {"updated_at", "status", "activated_at", "retired_at", "revoked_at"}
    state = inspect(target)
    for attr in state.attrs:
        if attr.key not in allowed and attr.history.has_changes():
            raise ValueError("Legal evidence is immutable; create a new version or audit event")


def _immutable_delete(mapper: Any, connection: Any, target: Any) -> None:
    raise ValueError("Legal evidence cannot be deleted")


for _model in (LegalOfferVersion, ContractAcceptance):
    event.listen(_model, "before_update", _immutable_update)
    event.listen(_model, "before_delete", _immutable_delete)
event.listen(LegalAuditEvent, "before_delete", _immutable_delete)


def _checkout_immutable(mapper: Any, connection: Any, target: LegalCheckout) -> None:
    state = inspect(target)
    for attr in state.attrs:
        if attr.key in {"status", "updated_at"}:
            continue
        if attr.key == "payment_id" and not any(
            value is not None for value in attr.history.deleted
        ):
            continue
        if attr.history.has_changes():
            raise ValueError("Checkout evidence is immutable")


event.listen(LegalCheckout, "before_update", _checkout_immutable)
event.listen(LegalCheckout, "before_delete", _immutable_delete)
event.listen(LegalAuditEvent, "before_update", _immutable_update)
