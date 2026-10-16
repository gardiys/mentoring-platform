from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AdminUser, CurrentUser, StudentUser
from app.core.config import get_settings
from app.core.errors import api_error
from app.core.middleware import read_limited_request_body
from app.db.session import get_db_session
from app.legal import service
from app.legal.catalog import PRODUCTS, canonical_hash
from app.legal.models import (
    ContractAcceptance,
    LegalAuditEvent,
    LegalCheckout,
    LegalEmailDelivery,
    LegalOfferVersion,
    LegalQuestionnaireDraft,
)
from app.legal.schemas import (
    ContractState,
    EmailCode,
    OfferStatus,
    Questionnaire,
)
from app.opportunities.models import OpportunityPaymentAttempt
from app.payments.models import PaymentAttemptStatus, PaymentWebhookEvent
from app.users.models import User, UserRole

Session = Annotated[AsyncSession, Depends(get_db_session)]
router = APIRouter(prefix="/legal", tags=["legal"])
admin_router = APIRouter(prefix="/admin/legal", tags=["admin-legal"])


def encode(row: Any, *, exclude: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        column.name: jsonable_encoder(getattr(row, column.name))
        for column in row.__table__.columns
        if column.name not in exclude
    }


async def owned_contract(
    session: AsyncSession, user: User, contract_id: UUID
) -> ContractAcceptance:
    stmt = select(ContractAcceptance).where(ContractAcceptance.id == contract_id)
    if user.role is not UserRole.ADMIN:
        stmt = stmt.where(ContractAcceptance.user_id == user.id)
    contract = await session.scalar(stmt)
    if contract is None:
        api_error(404, "contract_not_found", "Договор не найден")
    if canonical_hash(contract.snapshot) != contract.acceptance_snapshot_sha256:
        api_error(503, "contract_integrity_error", "Требуется проверка целостности договора")
    return contract


@router.get("/products")
async def products(_user: CurrentUser) -> dict[str, Any]:
    return {"products": [{"code": code, **value} for code, value in PRODUCTS.items()]}


@router.get("/products/{product}/checkout")
async def details(product: str, session: Session, user: StudentUser) -> dict[str, Any]:
    return await service.checkout_details(session, user, product)


@router.get("/products/{product}/questionnaire")
async def draft(product: str, session: Session, user: StudentUser) -> dict[str, Any]:
    row = await session.scalar(
        select(LegalQuestionnaireDraft).where(
            LegalQuestionnaireDraft.user_id == user.id,
            LegalQuestionnaireDraft.product_code == product,
        )
    )
    return {"questionnaire_schema_version": 1, "answers": row.answers if row else None}


@router.put("/products/{product}/questionnaire")
async def save_draft(
    product: str, payload: Questionnaire, session: Session, user: StudentUser
) -> dict[str, Any]:
    if product not in PRODUCTS:
        api_error(404, "legal_product_not_found", "Программа не найдена")
    await session.execute(select(User.id).where(User.id == user.id).with_for_update())
    row = await session.scalar(
        select(LegalQuestionnaireDraft).where(
            LegalQuestionnaireDraft.user_id == user.id,
            LegalQuestionnaireDraft.product_code == product,
        )
    )
    if row is None:
        row = LegalQuestionnaireDraft(
            user_id=user.id, product_code=product, answers=payload.model_dump()
        )
        session.add(row)
    else:
        row.answers = payload.model_dump()
    pending = list(
        await session.scalars(
            select(LegalCheckout)
            .where(
                LegalCheckout.user_id == user.id,
                LegalCheckout.product_code == product,
                LegalCheckout.status == "pending",
            )
            .with_for_update()
        )
    )
    for checkout in pending:
        checkout.status = "cancelled"
        if checkout.payment_id:
            payment = await session.get(OpportunityPaymentAttempt, checkout.payment_id)
            if payment and payment.status is PaymentAttemptStatus.PENDING:
                payment.status = PaymentAttemptStatus.REVOKED
    await session.commit()
    return {"saved": True}


@router.get("/checkouts/{checkout_id}")
async def checkout_status(checkout_id: UUID, session: Session, user: CurrentUser) -> dict[str, Any]:
    row = await session.scalar(
        select(LegalCheckout).where(
            LegalCheckout.id == checkout_id, LegalCheckout.user_id == user.id
        )
    )
    if row is None:
        api_error(404, "checkout_not_found", "Платёжная сессия не найдена")
    payment = await session.get(OpportunityPaymentAttempt, row.payment_id)
    return {**encode(row), "payment_status": payment.status if payment else None}


@router.post("/checkouts/{checkout_id}/cancel")
async def cancel_checkout(checkout_id: UUID, session: Session, user: StudentUser) -> dict[str, Any]:
    row = await session.scalar(
        select(LegalCheckout)
        .where(LegalCheckout.id == checkout_id, LegalCheckout.user_id == user.id)
        .with_for_update()
    )
    if row is None:
        api_error(404, "checkout_not_found", "Платёжная сессия не найдена")
    if row.status != "pending":
        api_error(409, "checkout_not_pending", "Сессия уже завершена")
    row.status = "cancelled"
    payment = await session.get(OpportunityPaymentAttempt, row.payment_id)
    if payment:
        payment.status = PaymentAttemptStatus.REVOKED
    service.audit(session, "checkout.cancelled", row.id, user.id)
    await session.commit()
    return {"cancelled": True}


@router.post("/email/request-code")
async def request_code(session: Session, user: StudentUser) -> dict[str, bool]:
    await service.request_email_code(session, user)
    return {"queued": True}


@router.post("/email/confirm")
async def confirm_code(payload: EmailCode, session: Session, user: StudentUser) -> dict[str, bool]:
    await service.confirm_email_code(session, user, payload.code)
    return {"verified": True}


@router.get("/offers/{offer_id}")
async def offer_details(offer_id: UUID, session: Session, _user: CurrentUser) -> dict[str, Any]:
    offer = await session.get(LegalOfferVersion, offer_id)
    if offer is None:
        api_error(404, "legal_offer_not_found", "Оферта не найдена")
    return encode(offer)


@router.get("/offers/{offer_id}/offer.pdf")
async def offer_pdf(offer_id: UUID, session: Session, user: CurrentUser) -> Response:
    offer = await session.get(LegalOfferVersion, offer_id)
    if offer is None:
        api_error(404, "legal_offer_not_found", "Оферта не найдена")
    if offer.status != "active" and user.role is not UserRole.ADMIN:
        owned = await session.scalar(
            select(ContractAcceptance.id)
            .where(
                ContractAcceptance.offer_version_id == offer_id,
                ContractAcceptance.user_id == user.id,
            )
            .limit(1)
        )
        pending = await session.scalar(
            select(LegalCheckout.id)
            .where(LegalCheckout.offer_version_id == offer_id, LegalCheckout.user_id == user.id)
            .limit(1)
        )
        if owned is None and pending is None:
            api_error(404, "legal_offer_not_found", "Оферта не найдена")
    return Response(
        await service.checked_pdf(offer, session),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="Offer_{offer.product_code}_{offer.version_code}.pdf"'
            ),
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/contracts")
async def contracts(session: Session, user: CurrentUser) -> list[dict[str, Any]]:
    rows = await session.scalars(
        select(ContractAcceptance)
        .where(ContractAcceptance.user_id == user.id)
        .order_by(ContractAcceptance.accepted_at.desc())
    )
    return [encode(row) for row in rows]


@router.get("/contracts/{contract_id}")
async def contract_details(
    contract_id: UUID, session: Session, user: CurrentUser
) -> dict[str, Any]:
    contract = await owned_contract(session, user, contract_id)
    deliveries = list(
        await session.scalars(
            select(LegalEmailDelivery)
            .where(LegalEmailDelivery.contract_id == contract.id)
            .order_by(LegalEmailDelivery.attempt_number)
        )
    )
    result = {**encode(contract), "email_deliveries": [encode(row) for row in deliveries]}
    if user.role is UserRole.ADMIN:
        owner = await session.get(User, contract.user_id)
        result["current_email"] = owner.email if owner else None
        result["webhooks"] = [
            encode(row, exclude=("raw_payload",))
            for row in await session.scalars(
                select(PaymentWebhookEvent).where(
                    PaymentWebhookEvent.opportunity_attempt_id == contract.payment_id
                )
            )
        ]
        result["audit"] = [
            encode(row)
            for row in await session.scalars(
                select(LegalAuditEvent).where(LegalAuditEvent.resource_id == contract.id)
            )
        ]
    return result


@router.get("/contracts/{contract_id}/offer.pdf")
async def contract_pdf(contract_id: UUID, session: Session, user: CurrentUser) -> Response:
    contract = await owned_contract(session, user, contract_id)
    offer = await session.get(LegalOfferVersion, contract.offer_version_id)
    assert offer is not None
    if (
        offer.pdf_sha256 != contract.snapshot["offer_pdf_sha256"]
        or offer.product_code != contract.product_code
    ):
        api_error(503, "contract_offer_integrity_error", "Требуется проверка целостности оферты")
    data = await service.checked_pdf(offer, session)
    service.audit(session, "contract.pdf_downloaded", contract.id, user.id)
    await session.commit()
    return Response(
        data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="Offer_{offer.product_code}_{offer.version_code}.pdf"'
            ),
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/contracts/{contract_id}/resend-email")
async def resend_email(contract_id: UUID, session: Session, user: CurrentUser) -> dict[str, bool]:
    await service.resend(session, await owned_contract(session, user, contract_id), user)
    return {"queued": True}


@admin_router.get("/contracts")
async def admin_contracts(
    session: Session, _admin: AdminUser, q: str = Query(default="", max_length=200)
) -> list[dict[str, Any]]:
    stmt = (
        select(ContractAcceptance)
        .join(User, User.id == ContractAcceptance.user_id)
        .join(
            OpportunityPaymentAttempt, OpportunityPaymentAttempt.id == ContractAcceptance.payment_id
        )
    )
    if q:
        value = f"%{q}%"
        stmt = stmt.where(
            or_(
                User.first_name.ilike(value),
                User.last_name.ilike(value),
                User.email.ilike(value),
                ContractAcceptance.public_number.ilike(value),
                ContractAcceptance.product_code.ilike(value),
                ContractAcceptance.snapshot["customer_email"].astext.ilike(value),
                OpportunityPaymentAttempt.payment_link_id.ilike(value),
                OpportunityPaymentAttempt.provider_operation_id.ilike(value),
            )
        )
    return [
        encode(row)
        for row in await session.scalars(
            stmt.order_by(ContractAcceptance.accepted_at.desc()).limit(200)
        )
    ]


@admin_router.get("/offers")
async def admin_offers(session: Session, _admin: AdminUser) -> list[dict[str, Any]]:
    return [
        encode(row)
        for row in await session.scalars(
            select(LegalOfferVersion).order_by(LegalOfferVersion.publication_date.desc())
        )
    ]


@admin_router.patch("/offers/{offer_id}")
async def offer_status(
    offer_id: UUID, payload: OfferStatus, session: Session, admin: AdminUser
) -> dict[str, Any]:
    # Serialize transitions of all versions of a product, including concurrent activation.
    offer = await session.get(LegalOfferVersion, offer_id)
    if offer is None:
        api_error(404, "legal_offer_not_found", "Оферта не найдена")
    versions = list(
        await session.scalars(
            select(LegalOfferVersion)
            .where(LegalOfferVersion.product_code == offer.product_code)
            .order_by(LegalOfferVersion.id)
            .with_for_update()
        )
    )
    if offer.status == "revoked":
        api_error(
            409, "legal_offer_revoked", "Отозванная редакция не может быть активирована повторно"
        )
    if payload.status == "active":
        await service.checked_pdf(offer, session)
        for row in versions:
            if row.status == "active" and row.id != offer.id:
                row.status = "retired"
                row.retired_at = service.now()
        await session.flush()
        offer.activated_at = service.now()
    elif payload.status == "retired":
        offer.retired_at = service.now()
    else:
        offer.revoked_at = service.now()
    offer.status = payload.status
    service.audit(session, f"offer.{payload.status}", offer.id, admin.id)
    await session.commit()
    await session.refresh(offer)
    return encode(offer)


@admin_router.post("/contracts/{contract_id}/state")
async def contract_state(
    contract_id: UUID, payload: ContractState, session: Session, admin: AdminUser
) -> dict[str, Any]:
    contract = await owned_contract(session, admin, contract_id)
    contract.status = payload.status
    service.audit(
        session,
        f"contract.{payload.status}",
        contract.id,
        admin.id,
        **payload.model_dump(),
        occurred_at=service.now().isoformat(),
    )
    await session.commit()
    await session.refresh(contract)
    return encode(contract)


@admin_router.get("/metrics")
async def metrics(session: Session, _admin: AdminUser) -> dict[str, Any]:
    event_counts = {
        key: value
        for key, value in (
            await session.execute(
                select(LegalAuditEvent.event_type, func.count()).group_by(
                    LegalAuditEvent.event_type
                )
            )
        ).all()
    }
    email_counts = {
        key: value
        for key, value in (
            await session.execute(
                select(LegalEmailDelivery.status, func.count()).group_by(LegalEmailDelivery.status)
            )
        ).all()
    }
    alerts = [
        encode(row)
        for row in await session.scalars(
            select(LegalAuditEvent)
            .where(LegalAuditEvent.event_type.startswith("alert."))
            .order_by(LegalAuditEvent.created_at.desc())
            .limit(100)
        )
    ]
    return {
        "contract_acceptances_created_total": event_counts.get("contract.accepted", 0),
        "contract_confirmation_emails_queued_total": event_counts.get("contract.email_queued", 0),
        "contract_confirmation_emails_sent_total": event_counts.get("contract.email_sent", 0),
        "contract_confirmation_emails_failed_total": event_counts.get("alert.email_failed", 0),
        "contract_confirmation_emails_bounced_total": event_counts.get("contract.email_bounced", 0),
        "contract_confirmation_email_retry_total": event_counts.get("contract.email_retry", 0),
        "legal_offer_hash_mismatch_total": event_counts.get("alert.legal_offer_hash_mismatch", 0),
        "payment_webhook_duplicate_total": event_counts.get("payment.webhook_duplicate", 0),
        "contract_email_outbox_backlog": email_counts.get("pending", 0)
        + email_counts.get("processing", 0),
        "alerts": alerts,
    }


@router.post("/email/delivery-webhook")
async def email_webhook(request: Request, session: Session) -> dict[str, str]:
    import json

    token = get_settings().brevo_delivery_webhook_token
    if token is None or not secrets.compare_digest(
        request.headers.get("authorization", ""), f"Bearer {token.get_secret_value()}"
    ):
        api_error(401, "email_webhook_unauthorized", "Invalid delivery webhook credentials")
    try:
        body = json.loads(await read_limited_request_body(request, max_bytes=32768))
    except (ValueError, UnicodeDecodeError):
        api_error(400, "email_webhook_invalid", "Invalid delivery event")
    if not isinstance(body, dict):
        api_error(400, "email_webhook_invalid", "Invalid delivery event")
    message = body.get("message-id")
    event = body.get("event")
    if event not in {"delivered", "hard_bounce", "soft_bounce", "blocked", "invalid_email"}:
        return {"status": "ignored"}
    row = await session.scalar(
        select(LegalEmailDelivery)
        .where(LegalEmailDelivery.provider_message_id == str(message).strip("<>"))
        .with_for_update()
    )
    if row is None:
        return {"status": "ignored"}
    is_bounce = event != "delivered"
    if row.status == "bounced" or (row.status == "delivered" and not is_bounce):
        return {"status": "duplicate"}
    at = datetime.now(UTC)
    row.status = "bounced" if is_bounce else "delivered"
    if is_bounce:
        row.bounced_at = at
        row.error_code = str(event)
        row.safe_error_message = "Email provider reported non-delivery"
        service.audit(session, "contract.email_bounced", row.contract_id)
    else:
        row.delivered_at = at
    await session.commit()
    return {"status": "ok"}
