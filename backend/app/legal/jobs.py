from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import or_, select

from app.career_packages.email import CareerPackageEmailError, CareerPackageEmailService
from app.core.config import get_settings
from app.db.session import async_session_factory
from app.legal.catalog import PRODUCTS, canonical_hash
from app.legal.models import ContractAcceptance, LegalEmailDelivery, LegalOfferVersion
from app.legal.service import audit, now
from app.legal.storage import read_document

logger = logging.getLogger(__name__)
RETRY_SECONDS = (60, 300, 1800, 7200, 43200)


async def deliver_legal_emails(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    # One transaction/row, SKIP LOCKED and timeout below lease prevent two workers
    # sending the same outbox row. A provider idempotency key covers lost responses.
    for _ in range(20):
        async with async_session_factory() as session:
            row = await session.scalar(
                select(LegalEmailDelivery)
                .where(
                    or_(
                        LegalEmailDelivery.status == "pending",
                        LegalEmailDelivery.status == "processing",
                    ),
                    LegalEmailDelivery.next_attempt_at <= now(),
                )
                .order_by(LegalEmailDelivery.next_attempt_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if row is None:
                return
            row.status = "processing"
            try:
                pdf = None
                attachment_name = None
                if row.contract_id:
                    contract = await session.get(ContractAcceptance, row.contract_id)
                    if (
                        contract is None
                        or canonical_hash(contract.snapshot) != contract.acceptance_snapshot_sha256
                    ):
                        raise ValueError("contract_integrity_error")
                    offer = await session.get(LegalOfferVersion, contract.offer_version_id)
                    if (
                        offer is None
                        or offer.product_code != contract.product_code
                        or offer.pdf_sha256 != contract.snapshot["offer_pdf_sha256"]
                        or row.attachment_sha256 != offer.pdf_sha256
                    ):
                        raise ValueError("contract_offer_mismatch")
                    pdf = await read_document(offer.pdf_storage_key, row.attachment_sha256)
                    attachment_name = f"Offer_{contract.product_code}_{offer.version_code}.pdf"
                message_id = await CareerPackageEmailService(
                    settings, ctx["brevo_client"]
                ).send_package(
                    recipient_email=row.recipient_email,
                    recipient_name="",
                    package_number="",
                    version_number=1,
                    body=row.body_snapshot,
                    action_url=f"{settings.web_frontend_url.rstrip('/')}/documents",
                    pdf=pdf,
                    subject=row.subject_snapshot,
                    action_label="Мои документы",
                    attachment_name=attachment_name,
                    tags=["legal-transactional"],
                    idempotency_key=str(row.id),
                    sender_email=settings.legal_email_from,
                    reply_to_email=settings.legal_email_reply_to
                    or settings.brevo_reply_to_email
                    or settings.legal_official_email,
                )
                row.provider_message_id = message_id.strip("<>") if message_id else None
                row.status = "sent"
                row.sent_at = now()
                row.error_code = None
                row.safe_error_message = None
                audit(
                    session,
                    "contract.email_sent" if row.contract_id else "verification.email_sent",
                    row.contract_id,
                )
            except Exception as error:
                row.retry_count += 1
                row.error_code = (
                    "document_integrity_error"
                    if isinstance(error, ValueError)
                    else "provider_or_storage_error"
                )
                row.safe_error_message = (
                    str(error)[:200]
                    if isinstance(error, CareerPackageEmailError)
                    else "Email could not be sent; inspect provider and document integrity"
                )
                if row.retry_count > settings.contract_email_max_retries:
                    row.status = "failed"
                    row.failed_at = now()
                    audit(
                        session,
                        "alert.email_failed"
                        if row.contract_id
                        else "alert.verification_email_failed",
                        row.contract_id,
                        delivery_id=str(row.id),
                    )
                else:
                    row.status = "pending"
                    row.next_attempt_at = now() + timedelta(
                        seconds=RETRY_SECONDS[min(row.retry_count - 1, len(RETRY_SECONDS) - 1)]
                    )
                    audit(
                        session,
                        "contract.email_retry" if row.contract_id else "verification.email_retry",
                        row.contract_id,
                        delivery_id=str(row.id),
                    )
                from app.legal.storage import LegalDocumentError

                if isinstance(error, LegalDocumentError):
                    audit(
                        session,
                        "alert.legal_offer_hash_mismatch"
                        if str(error) == "legal_offer_hash_mismatch"
                        else "alert.legal_document_unavailable",
                        row.contract_id,
                    )
                logger.warning("Legal email delivery failed email_delivery_id=%s", row.id)
            await session.commit()


async def monitor_legal_health(ctx: dict[str, Any]) -> None:
    from app.legal.storage import LegalDocumentError

    async with async_session_factory() as session:
        offers = list(
            await session.scalars(
                select(LegalOfferVersion).where(LegalOfferVersion.status == "active")
            )
        )
        alerts: list[tuple[str, Any]] = []
        for product in PRODUCTS:
            if not any(offer.product_code == product for offer in offers):
                alerts.append(("alert.legal_offer_missing", None))
        for offer in offers:
            try:
                await read_document(offer.pdf_storage_key, offer.pdf_sha256)
            except LegalDocumentError as error:
                alerts.append(("alert." + str(error), offer.id))
        oldest = await session.scalar(
            select(LegalEmailDelivery)
            .where(
                LegalEmailDelivery.status == "pending",
                LegalEmailDelivery.created_at < now() - timedelta(hours=1),
            )
            .limit(1)
        )
        if oldest:
            alerts.append(("alert.email_outbox_backlog", oldest.id))
        for event, resource in alerts:
            from app.legal.models import LegalAuditEvent

            existing = await session.scalar(
                select(LegalAuditEvent.id)
                .where(
                    LegalAuditEvent.event_type == event,
                    LegalAuditEvent.resource_id == resource,
                    LegalAuditEvent.created_at > now() - timedelta(hours=1),
                )
                .limit(1)
            )
            if existing is None:
                audit(session, event, resource)
                logger.error("Legal operational alert event=%s resource_id=%s", event, resource)
        await session.commit()
