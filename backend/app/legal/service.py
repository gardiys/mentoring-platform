from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import api_error
from app.legal.catalog import PRODUCTS, canonical_hash, checkboxes, financial_terms
from app.legal.models import (
    ContractAcceptance,
    LegalAuditEvent,
    LegalCheckout,
    LegalEmailDelivery,
    LegalEmailVerification,
    LegalOfferVersion,
)
from app.legal.schemas import CheckoutConfirmation
from app.legal.storage import LegalDocumentError, read_document
from app.opportunities.models import (
    GoTransitionApplication,
    GoTransitionStatus,
    OpportunityPaymentAttempt,
    PythonRepeatApplication,
    PythonRepeatApplicationStatus,
)
from app.opportunities.notifications import mark_payment_for_review
from app.opportunities.schemas import OpportunityPaymentLinkRead
from app.payments.models import PaymentAttemptStatus
from app.payments.tochka import TochkaError, TochkaPaymentService
from app.users.models import User


def now() -> datetime:
    return datetime.now(UTC)


def audit(
    session: AsyncSession,
    event: str,
    resource: UUID | None = None,
    actor: UUID | None = None,
    **payload: Any,
) -> None:
    session.add(
        LegalAuditEvent(event_type=event, resource_id=resource, actor_id=actor, payload=payload)
    )


async def checked_pdf(offer: LegalOfferVersion, session: AsyncSession | None = None) -> bytes:
    try:
        data = await read_document(offer.pdf_storage_key, offer.pdf_sha256)
        if len(data) != offer.pdf_size or not data.startswith(b"%PDF-"):
            raise LegalDocumentError("legal_offer_hash_mismatch")
        return data
    except LegalDocumentError as error:
        if session is not None:
            event = (
                "alert.legal_offer_hash_mismatch"
                if str(error) == "legal_offer_hash_mismatch"
                else "alert.legal_document_unavailable"
            )
            audit(session, event, offer.id)
            await session.commit()
        api_error(
            503,
            "legal_document_unavailable",
            "PDF оферты недоступен или повреждён. Обратитесь к команде.",
        )


async def active_offer(
    session: AsyncSession, product: str, *, lock: bool = False
) -> LegalOfferVersion:
    if product not in PRODUCTS:
        api_error(404, "legal_product_not_found", "Программа не найдена")
    statement = select(LegalOfferVersion).where(
        LegalOfferVersion.product_code == product,
        LegalOfferVersion.status == "active",
        LegalOfferVersion.effective_from <= now(),
    )
    if lock:
        statement = statement.with_for_update()
    offer = await session.scalar(statement)
    if offer is None:
        api_error(
            503, "legal_offer_missing", "Активная оферта не опубликована. Обратитесь к команде."
        )
    return offer


async def verified_email(session: AsyncSession, user: User) -> bool:
    if not user.email:
        return False
    return (
        await session.scalar(
            select(LegalEmailVerification.id)
            .where(
                LegalEmailVerification.user_id == user.id,
                LegalEmailVerification.email == user.email,
                LegalEmailVerification.verified_at.is_not(None),
            )
            .limit(1)
        )
        is not None
    )


async def request_email_code(session: AsyncSession, user: User) -> None:
    import re

    if not user.email or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", user.email):
        api_error(422, "email_required", "Сначала укажите корректный email в профиле")
    # User lock serializes requests across worker processes.
    await session.execute(select(User.id).where(User.id == user.id).with_for_update())
    latest = await session.scalar(
        select(LegalEmailVerification)
        .where(LegalEmailVerification.user_id == user.id)
        .order_by(LegalEmailVerification.created_at.desc())
        .limit(1)
    )
    if latest and latest.created_at > now() - timedelta(seconds=60):
        api_error(429, "email_verification_cooldown", "Повторный код можно запросить через минуту")
    code = f"{secrets.randbelow(100_000_000):08d}"
    verification = LegalEmailVerification(
        id=uuid4(),
        user_id=user.id,
        email=user.email,
        expires_at=now() + timedelta(minutes=15),
        code_hash="",
    )
    verification.code_hash = hashlib.sha256(f"{verification.id}:{code}".encode()).hexdigest()
    session.add(verification)
    session.add(
        LegalEmailDelivery(
            notification_type="email.verification",
            recipient_email=user.email,
            subject_snapshot="Подтверждение email на платформе",
            body_snapshot=(
                f"Код подтверждения: {code}\nДействует 15 минут. "
                "Введите его в авторизованном кабинете платформы. "
                "Если вы не запрашивали код, проигнорируйте письмо."
            ),
            next_attempt_at=now(),
        )
    )
    await session.commit()


async def confirm_email_code(session: AsyncSession, user: User, code: str) -> None:
    row = await session.scalar(
        select(LegalEmailVerification)
        .where(LegalEmailVerification.user_id == user.id)
        .order_by(LegalEmailVerification.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    if (
        row is None
        or row.email != user.email
        or row.expires_at <= now()
        or row.attempts >= 5
        or row.verified_at is not None
    ):
        api_error(409, "email_code_expired", "Запросите новый код подтверждения")
    row.attempts += 1
    valid = secrets.compare_digest(
        row.code_hash, hashlib.sha256(f"{row.id}:{code}".encode()).hexdigest()
    )
    if valid:
        row.verified_at = now()
    await session.commit()
    if not valid:
        api_error(422, "email_code_invalid", "Неверный код подтверждения")


async def checkout_details(session: AsyncSession, user: User, product: str) -> dict[str, Any]:
    offer = await active_offer(session, product)
    await checked_pdf(offer, session)
    return {
        "product_code": product,
        "title": offer.title,
        "offer_version_id": str(offer.id),
        "version_code": offer.version_code,
        "publication_date": offer.publication_date.isoformat(),
        "pdf_url": f"/api/v1/legal/offers/{offer.id}/offer.pdf",
        "pdf_sha256": offer.pdf_sha256,
        "financial_terms": offer.financial_terms,
        "checkboxes": checkboxes(offer.title, offer.publication_date.strftime("%d.%m.%Y")),
        "questionnaire_schema_version": 1,
        "email": user.email,
        "email_verified": await verified_email(session, user),
    }


async def create_checkout(
    session: AsyncSession,
    user: User,
    product: str,
    application_id: UUID,
    payload: CheckoutConfirmation,
    *,
    ip: str | None,
    user_agent: str | None,
) -> LegalCheckout:
    offer = await active_offer(session, product, lock=True)
    if offer.id != payload.expected_offer_version_id:
        api_error(
            409,
            "legal_offer_changed",
            "Оферта изменилась. Обновите страницу и ознакомьтесь с новой редакцией.",
        )
    await checked_pdf(offer, session)
    if offer.financial_terms != financial_terms():
        api_error(409, "legal_terms_invalid", "Условия программы требуют проверки администратора")
    texts = checkboxes(offer.title, offer.publication_date.strftime("%d.%m.%Y"))
    if set(payload.confirmations) != set(texts) or not all(payload.confirmations.values()):
        api_error(422, "legal_confirmations_required", "Подтвердите все три обязательных пункта")
    if not await verified_email(session, user):
        api_error(409, "email_not_verified", "Подтвердите email перед оплатой")
    is_go = product == "python_to_go_transition"
    if is_go and "go_in_current_work" not in payload.answers.model_fields_set:
        api_error(422, "go_work_answer_required", "Укажите, используется ли Go в текущей работе")
    model = GoTransitionApplication if is_go else PythonRepeatApplication
    application: Any = await session.scalar(
        select(model)
        .where(model.id == application_id, model.student_id == user.id)
        .with_for_update()
    )
    if application is None:
        api_error(404, "legal_application_not_found", "Заявка не найдена")
    if str(application.status) not in {"approved", "terms_accepted", "payment_pending"}:
        api_error(409, "legal_application_not_approved", "Заявка должна быть одобрена командой")
    expiry = (
        application.terms_expires_at
        if isinstance(application, GoTransitionApplication)
        else application.offer_expires_at
    )
    if expiry and expiry <= now():
        api_error(409, "legal_application_expired", "Срок одобренных условий истёк")
    # Reuse eligibility and access rules of the existing product.
    from app.opportunities.python_repeat_service import python_repeat_eligibility
    from app.opportunities.service import _student_has_overdue_obligations

    if is_go:
        if (
            not get_settings().python_to_go_enabled
            or not get_settings().opportunities_enabled
            or await _student_has_overdue_obligations(session, user.id)
        ):
            api_error(409, "legal_product_unavailable", "Программа сейчас недоступна")
    else:
        eligibility = await python_repeat_eligibility(
            session, user, ignore_application_id=application_id
        )
        if (
            not eligibility.eligible
            and getattr(application, "eligibility_override_by_user_id", None) is None
        ):
            api_error(409, "legal_product_unavailable", eligibility.message)
    previous = list(
        await session.scalars(
            select(LegalCheckout)
            .where(LegalCheckout.application_id == application_id)
            .with_for_update()
        )
    )
    if any(row.status == "paid" for row in previous):
        api_error(409, "legal_already_paid", "Программа уже оплачена")
    for row in previous:
        if row.status == "pending":
            row.status = "cancelled"
            if row.payment_id:
                attempt = await session.get(OpportunityPaymentAttempt, row.payment_id)
                if attempt and attempt.status is PaymentAttemptStatus.PENDING:
                    attempt.status = PaymentAttemptStatus.REVOKED
    await session.flush()
    at = now()
    snapshot: dict[str, Any] = {
        "product_code": product,
        "title": offer.title,
        "offer_version_id": str(offer.id),
        "offer_version_code": offer.version_code,
        "offer_publication_date": offer.publication_date.isoformat(),
        "offer_pdf_sha256": offer.pdf_sha256,
        "financial_terms": dict(offer.financial_terms),
        "checkbox_form_version": 1,
        "checkboxes": {
            key: {"accepted": True, "text": value, "confirmed_at": at.isoformat()}
            for key, value in texts.items()
        },
        "questionnaire_schema_version": payload.questionnaire_schema_version,
        "questionnaire_answers": payload.answers.model_dump(),
        "customer_email": user.email,
        "customer_name": " ".join(filter(None, (user.first_name, user.last_name))),
        "ip_address": ip,
        "user_agent": (user_agent or "")[:500],
        "page_identifier": payload.page_identifier,
        "frontend_build_version": payload.frontend_build_version,
        "confirmed_at": at.isoformat(),
    }
    checkout = LegalCheckout(
        id=uuid4(),
        user_id=user.id,
        product_code=product,
        application_id=application_id,
        offer_version_id=offer.id,
        snapshot=snapshot,
        expires_at=at + timedelta(hours=24),
    )
    session.add(checkout)
    await session.flush()
    if isinstance(application, GoTransitionApplication):
        application.status = GoTransitionStatus.PAYMENT_PENDING
        application.terms_accepted_at = at
        application.accepted_terms_snapshot = {
            **application.terms_snapshot,
            **offer.financial_terms,
        }
    else:
        application.status = PythonRepeatApplicationStatus.PAYMENT_PENDING
        application.accepted_at = at
        application.accepted_by_user_id = user.id
        application.terms_snapshot = {
            **(application.terms_snapshot or {}),
            **offer.financial_terms,
            "success_fee_min_kopecks": 0,
            "success_fee_installments_count": 2,
            "success_fee_first_due_months_after_employment": 1,
            "success_fee_second_due_months_after_employment": 2,
            "public_offer_revision": offer.version_code,
            "public_offer_published_at": offer.publication_date.isoformat(),
            "public_offer_sha256": offer.pdf_sha256,
            "public_offer_url": f"/api/v1/legal/offers/{offer.id}/offer.pdf",
        }
    payment_link_id = f"legal_{checkout.id.hex}"
    try:
        result = await TochkaPaymentService(get_settings()).create_payment_link(
            installment_id=checkout.id,
            payment_link_id=payment_link_id,
            amount_kopecks=offer.financial_terms["upfront_amount_minor"],
            client_name=snapshot["customer_name"],
            client_email=user.email or "",
            return_path="/documents",
        )
    except TochkaError:
        api_error(502, "legal_payment_unavailable", "Не удалось создать платёж. Попробуйте позже.")
    attempt = OpportunityPaymentAttempt(
        id=uuid4(),
        transition_application_id=application_id if is_go else None,
        python_repeat_application_id=None if is_go else application_id,
        payment_link_id=result.payment_link_id,
        provider_operation_id=result.provider_operation_id,
        payment_url=result.payment_url,
        status=PaymentAttemptStatus.PENDING,
        terms_snapshot=dict(offer.financial_terms),
        raw_create_response=result.raw_response,
    )
    session.add(attempt)
    await session.flush()
    checkout.payment_id = attempt.id
    audit(
        session,
        "checkout.created",
        checkout.id,
        user.id,
        offer_version_id=str(offer.id),
        product_code=product,
    )
    await session.commit()
    return checkout


async def finalize_contract(
    session: AsyncSession,
    attempt: OpportunityPaymentAttempt,
    paid_at: datetime,
    received_at: datetime,
    *,
    provider_paid_at: datetime | None = None,
) -> ContractAcceptance | None:
    checkout = await session.scalar(
        select(LegalCheckout).where(LegalCheckout.payment_id == attempt.id).with_for_update()
    )
    if checkout is None:
        return None
    existing = await session.scalar(
        select(ContractAcceptance).where(ContractAcceptance.checkout_session_id == checkout.id)
    )
    if existing:
        return existing
    offer = await session.get(LegalOfferVersion, checkout.offer_version_id)
    if (
        checkout.status != "pending"
        or checkout.expires_at < paid_at
        or paid_at < datetime.fromisoformat(checkout.snapshot["confirmed_at"])
        or paid_at > received_at + timedelta(minutes=5)
        or offer is None
        or offer.status == "revoked"
    ):
        await mark_payment_for_review(session, attempt)
        audit(session, "alert.payment_checkout_invalid", checkout.id)
        return None
    # Paid contract persists even when access provisioning needs manual review.
    snapshot = {
        **checkout.snapshot,
        "acceptance_method": "PAYMENT",
        "payment_provider": attempt.provider,
        "payment_amount_minor": checkout.snapshot["financial_terms"]["upfront_amount_minor"],
        "currency": checkout.snapshot["financial_terms"]["currency"],
        "payment_id": attempt.payment_link_id,
        "provider_operation_id": attempt.provider_operation_id,
        "accepted_at": paid_at.isoformat(),
        "provider_paid_at": provider_paid_at.isoformat() if provider_paid_at else None,
        "webhook_received_at": received_at.isoformat(),
        "checkout_session_id": str(checkout.id),
    }
    contract_id = uuid4()
    contract = ContractAcceptance(
        id=contract_id,
        public_number=f"MP-{paid_at:%Y%m%d}-{contract_id.hex.upper()}",
        user_id=checkout.user_id,
        product_code=checkout.product_code,
        offer_version_id=checkout.offer_version_id,
        checkout_session_id=checkout.id,
        payment_id=attempt.id,
        accepted_at=paid_at,
        provider_paid_at=provider_paid_at,
        webhook_received_at=received_at,
        snapshot=snapshot,
        acceptance_snapshot_sha256=canonical_hash(snapshot),
    )
    session.add(contract)
    await session.flush()
    checkout.status = "paid"
    subject, body = confirmation_email(contract)
    session.add(
        LegalEmailDelivery(
            contract_id=contract.id,
            notification_type="contract.confirmation",
            attempt_number=1,
            recipient_email=snapshot["customer_email"],
            subject_snapshot=subject,
            body_snapshot=body,
            attachment_sha256=offer.pdf_sha256,
            next_attempt_at=now(),
        )
    )
    audit(session, "contract.accepted", contract.id, product_code=checkout.product_code)
    audit(session, "contract.email_queued", contract.id)
    return contract


def confirmation_email(contract: ContractAcceptance) -> tuple[str, str]:
    s = contract.snapshot
    settings = get_settings()
    reply = settings.legal_email_reply_to or settings.brevo_reply_to_email
    if not reply:
        reply = settings.legal_official_email
    when = contract.accepted_at.astimezone(ZoneInfo("Europe/Moscow")).strftime(
        "%d.%m.%Y %H:%M:%S (МСК)"
    )
    body = f"""Здравствуйте, {s["customer_name"]}!

{when} вами была акцептована Публичная оферта на оказание информационно-консультационных услуг
по программе «{s["title"]}».

Номер договора: {contract.public_number}
Редакция Оферты: {s["offer_version_code"]}
Дата публикации Оферты: {s["offer_publication_date"]}
Способ акцепта: оплата первой части Услуг
Сумма платежа: 30 000 рублей
Идентификатор платежа: {s["payment_id"]}

Условия стоимости:
— стоимость первой части Услуг составляет 30 000 рублей;
— при наступлении предусмотренного Офертой Трудоустройства дополнительно возникает
результативный компонент в размере 100% расчетной суммы ежемесячного вознаграждения;
— результативный компонент оплачивается двумя равными платежами через один и два календарных
месяца с даты трудоустройства;
— минимальный размер результативного компонента отсутствует;
— первоначальные 30 000 рублей не уменьшают размер результативного компонента.

Точная PDF-копия редакции Оферты, связанной с вашим договором, приложена к настоящему письму.
Документ также доступен в вашем личном кабинете:
{settings.web_frontend_url.rstrip("/")}/documents?contract={contract.id}

Настоящее письмо подтверждает заключение Договора путем акцепта Оферты и не требует
дополнительного подписания или ответа. Направление настоящего письма не изменяет момент
заключения Договора.

По вопросам исполнения или прекращения Договора используйте официальный адрес:
{reply}

С уважением,
ИП Щербак Антон Остапович"""
    return f"Договор заключен — {s['title']}", body


async def resend(session: AsyncSession, contract: ContractAcceptance, actor: User) -> None:
    await session.execute(
        select(ContractAcceptance.id).where(ContractAcceptance.id == contract.id).with_for_update()
    )
    rows = list(
        await session.scalars(
            select(LegalEmailDelivery)
            .where(LegalEmailDelivery.contract_id == contract.id)
            .order_by(LegalEmailDelivery.attempt_number)
        )
    )
    if rows and rows[-1].created_at > now() - timedelta(
        seconds=get_settings().contract_email_resend_cooldown_seconds
    ):
        api_error(
            429, "contract_email_cooldown", "Повторная отправка пока недоступна. Попробуйте позже."
        )
    subject, body = confirmation_email(contract)
    session.add(
        LegalEmailDelivery(
            contract_id=contract.id,
            attempt_number=len(rows) + 1,
            recipient_email=contract.snapshot["customer_email"],
            subject_snapshot=subject,
            body_snapshot=body,
            attachment_sha256=contract.snapshot["offer_pdf_sha256"],
            next_attempt_at=now(),
        )
    )
    audit(session, "contract.email_resend", contract.id, actor.id)
    audit(session, "contract.email_queued", contract.id, actor.id)
    await session.commit()


async def go_financial_terms_for_employment(
    session: AsyncSession, employment: Any
) -> dict[str, Any] | None:
    """Use this purchase's schedule only for a new, track-scoped Go employment case.

    Existing Python cases and installments retain their original schedule.
    Qualification of the new job remains with the existing staff review workflow.
    """
    from app.opportunities.models import GoTransitionEnrollment

    if employment.track_id is None or employment.created_at is None:
        return None
    contract = await session.scalar(
        select(ContractAcceptance)
        .join(LegalCheckout, LegalCheckout.id == ContractAcceptance.checkout_session_id)
        .join(
            GoTransitionEnrollment,
            GoTransitionEnrollment.application_id == LegalCheckout.application_id,
        )
        .where(
            ContractAcceptance.user_id == employment.student_id,
            ContractAcceptance.product_code == "python_to_go_transition",
            ContractAcceptance.status == "active",
            GoTransitionEnrollment.track_id == employment.track_id,
            ContractAcceptance.accepted_at <= employment.created_at,
        )
        .order_by(ContractAcceptance.accepted_at.desc())
        .limit(1)
    )
    return dict(contract.snapshot["financial_terms"]) if contract else None


async def checkout_payment_link(
    session: AsyncSession,
    user: User,
    product: str,
    application_id: UUID,
    payload: CheckoutConfirmation,
    ip: str | None,
    user_agent: str | None,
) -> OpportunityPaymentLinkRead:
    row = await create_checkout(
        session, user, product, application_id, payload, ip=ip, user_agent=user_agent
    )
    payment = await session.get(OpportunityPaymentAttempt, row.payment_id)
    assert payment is not None and payment.payment_url is not None
    return OpportunityPaymentLinkRead(
        payment_url=payment.payment_url,
        payment_link_id=payment.payment_link_id,
        checkout_session_id=row.id,
    )
