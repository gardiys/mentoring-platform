from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.legal import jobs, service, storage
from app.legal.catalog import (
    canonical_hash,
    checkboxes,
    financial_terms,
    manifest,
    validate_files,
)
from app.legal.models import (
    ContractAcceptance,
    LegalAuditEvent,
    LegalCheckout,
    LegalEmailDelivery,
    LegalEmailVerification,
    LegalOfferVersion,
)
from app.opportunities.models import (
    GoTransitionApplication,
    PythonRepeatApplication,
)
from app.payments import router as payment_router
from app.users.models import User
from tests.conftest import SeededData, TestSession, auth
from tests.legal_helpers import ANSWERS, approved_application, checkout_path, legal_checkout

PRODUCTS = ("repeat_python_mentorship", "python_to_go_transition")


async def make_purchase(client: AsyncClient, seeded: SeededData, product: str) -> dict:
    application = await approved_application(client, seeded, product)
    response = await legal_checkout(client, seeded.student_id, product, application)
    assert response.status_code == 200, response.text
    return response.json()


async def webhook(
    client: AsyncClient,
    checkout: dict,
    *,
    status: str = "SUCCEEDED",
    event_id: str = "payment-1",
    amount: str = "30000.00",
    currency: str = "RUB",
):
    return await client.post(
        "/api/v1/payments/tochka/webhook",
        json={
            "eventId": event_id,
            "paymentLinkId": checkout["payment_link_id"],
            "operationId": "operation-" + checkout["checkout_session_id"],
            "status": status,
            "amount": amount,
            "currency": currency,
            "paidAt": datetime.now(UTC).isoformat(),
        },
    )


@pytest.mark.parametrize("product", PRODUCTS)
async def test_success_is_atomic_idempotent_and_grants_access(
    client: AsyncClient, seeded: SeededData, product: str
) -> None:
    checkout = await make_purchase(client, seeded, product)
    async with TestSession() as session:
        assert await session.scalar(select(func.count()).select_from(ContractAcceptance)) == 0
    response = await webhook(client, checkout)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"
    assert (await webhook(client, checkout)).json()["status"] == "duplicate"
    assert (await webhook(client, checkout, event_id="other-event")).json()["status"] == "ok"
    async with TestSession() as session:
        contracts = list(await session.scalars(select(ContractAcceptance)))
        deliveries = list(
            await session.scalars(
                select(LegalEmailDelivery).where(LegalEmailDelivery.contract_id.is_not(None))
            )
        )
        assert len(contracts) == len(deliveries) == 1
        contract = contracts[0]
        assert contract.product_code == product
        assert contract.snapshot["financial_terms"] == financial_terms()
        assert contract.snapshot["questionnaire_answers"]["position"] == ANSWERS["position"]
        assert (
            contract.snapshot["checkboxes"]["financial"]["text"]
            == checkboxes(
                contract.snapshot["title"], "03.09.2026" if product == PRODUCTS[1] else "02.09.2026"
            )["financial"]
        )
        assert contract.provider_paid_at is not None
        assert contract.acceptance_snapshot_sha256 == canonical_hash(contract.snapshot)
        model = GoTransitionApplication if product == PRODUCTS[1] else PythonRepeatApplication
        application = await session.get(
            model,
            UUID(
                (
                    await session.get(LegalCheckout, UUID(checkout["checkout_session_id"]))
                ).application_id.hex
            ),
        )
        assert str(application.status) in {"paid", "enrolled"}
        assert deliveries[0].status == "pending"
    owned = await client.get(
        f"/api/v1/legal/contracts/{contract.id}", headers=auth(seeded.student_id)
    )
    assert owned.status_code == 200
    denied = await client.get(
        f"/api/v1/legal/contracts/{contract.id}", headers=auth(seeded.mentor_id)
    )
    assert denied.status_code == 404
    pdf = await client.get(
        f"/api/v1/legal/contracts/{contract.id}/offer.pdf", headers=auth(seeded.admin_id)
    )
    assert hashlib.sha256(pdf.content).hexdigest() == contract.snapshot["offer_pdf_sha256"]


@pytest.mark.parametrize("status", ["PENDING", "AUTHORIZED", "FAILED", "DECLINED"])
async def test_nonfinal_payment_never_creates_contract(
    client: AsyncClient, seeded: SeededData, status: str
) -> None:
    checkout = await make_purchase(client, seeded, PRODUCTS[1])
    response = await webhook(client, checkout, status=status)
    assert response.status_code == 200
    async with TestSession() as session:
        assert await session.scalar(select(func.count()).select_from(ContractAcceptance)) == 0
        assert (
            await session.scalar(
                select(func.count())
                .select_from(LegalEmailDelivery)
                .where(LegalEmailDelivery.contract_id.is_not(None))
            )
            == 0
        )


@pytest.mark.parametrize(
    "amount,currency", [("1.00", "RUB"), ("30000.00", "USD"), ("30000.01", "RUB")]
)
async def test_mismatched_payment_is_alerted(
    client: AsyncClient, seeded: SeededData, amount: str, currency: str
) -> None:
    checkout = await make_purchase(client, seeded, PRODUCTS[1])
    assert (await webhook(client, checkout, amount=amount, currency=currency)).json()[
        "status"
    ] == "unverified"
    async with TestSession() as session:
        assert await session.scalar(select(func.count()).select_from(ContractAcceptance)) == 0
        assert await session.scalar(
            select(LegalAuditEvent.id).where(
                LegalAuditEvent.event_type == "alert.payment_amount_currency_mismatch"
            )
        )


@pytest.mark.parametrize(
    "case", ["checkbox", "questionnaire", "amount", "product", "version", "email", "go_details"]
)
async def test_checkout_rejects_missing_or_tampered_evidence(
    client: AsyncClient, seeded: SeededData, case: str
) -> None:
    application = await approved_application(client, seeded, PRODUCTS[1])
    details = await client.get(
        f"/api/v1/legal/products/{PRODUCTS[1]}/checkout", headers=auth(seeded.student_id)
    )
    payload = {
        "expected_offer_version_id": details.json()["offer_version_id"],
        "questionnaire_schema_version": 1,
        "answers": dict(ANSWERS),
        "confirmations": {"offer": True, "financial": True, "truthful": True},
        "page_identifier": "/test",
    }
    if case == "checkbox":
        payload["confirmations"]["financial"] = False
    if case == "questionnaire":
        del payload["answers"]
    if case == "amount":
        payload["amount"] = 1
    if case == "product":
        payload["product_code"] = PRODUCTS[0]
    if case == "version":
        payload["expected_offer_version_id"] = str(uuid4())
    if case == "go_details":
        payload["answers"]["go_in_current_work"] = True
    if case == "email":
        async with TestSession() as session:
            user = await session.get(User, seeded.student_id)
            user.email = "changed@example.com"
            await session.commit()
    response = await client.post(
        checkout_path(PRODUCTS[1], application),
        headers=auth(seeded.student_id),
        json=payload,
    )
    assert response.status_code in {409, 422}, response.text
    async with TestSession() as session:
        assert await session.scalar(select(func.count()).select_from(LegalCheckout)) == 0


@pytest.mark.parametrize("product", PRODUCTS)
async def test_exact_document_attachment_and_email_snapshot(
    client: AsyncClient, seeded: SeededData, monkeypatch: pytest.MonkeyPatch, product: str
) -> None:
    checkout = await make_purchase(client, seeded, product)
    await webhook(client, checkout)
    async with TestSession() as session:
        user = await session.get(User, seeded.student_id)
        user.email = "new-address@example.com"
        await session.commit()
    sent = []

    def send(request):
        email = json.loads(request.content)
        UUID(email["headers"]["idempotencyKey"])
        sent.append(email)
        return httpx.Response(201, json={"messageId": "brevo-message-1"})

    settings = Settings(
        _env_file=None, brevo_api_key="test-key", brevo_from_email="sender@example.com"
    )
    monkeypatch.setattr(jobs, "get_settings", lambda: settings)
    monkeypatch.setattr(jobs, "async_session_factory", TestSession)
    async with httpx.AsyncClient(
        base_url="https://email.test", transport=httpx.MockTransport(send)
    ) as email_client:
        await jobs.deliver_legal_emails({"brevo_client": email_client})
        await jobs.deliver_legal_emails({"brevo_client": email_client})
    assert len(sent) == 1
    email = sent[0]
    assert email["to"][0]["email"] == "graduate@example.com"
    assert "30 000" in email["textContent"] and "100%" in email["textContent"]
    assert "двумя равными" in email["textContent"]
    assert ANSWERS["previous_contract"] not in email["textContent"]
    assert email["attachment"][0]["name"].startswith("Offer_" + product)
    async with TestSession() as session:
        contract = await session.scalar(select(ContractAcceptance))
        assert (
            hashlib.sha256(base64.b64decode(email["attachment"][0]["content"])).hexdigest()
            == contract.snapshot["offer_pdf_sha256"]
        )
        delivery = await session.scalar(select(LegalEmailDelivery))
        assert delivery.status == "sent" and delivery.delivered_at is None
        assert delivery.provider_message_id == "brevo-message-1"


async def test_retries_exhaustion_resend_and_bounce(
    client: AsyncClient, seeded: SeededData, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = await make_purchase(client, seeded, PRODUCTS[1])
    await webhook(client, checkout)
    settings = Settings(
        _env_file=None,
        brevo_api_key="test-key",
        brevo_from_email="sender@example.com",
        contract_email_max_retries=1,
        brevo_delivery_webhook_token="delivery-secret",
    )
    monkeypatch.setattr(jobs, "get_settings", lambda: settings)
    monkeypatch.setattr(jobs, "async_session_factory", TestSession)
    async with httpx.AsyncClient(
        base_url="https://email.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(503)),
    ) as email_client:
        await jobs.deliver_legal_emails({"brevo_client": email_client})
        async with TestSession() as session:
            delivery = await session.scalar(select(LegalEmailDelivery))
            assert delivery.status == "pending" and delivery.retry_count == 1
            delivery.next_attempt_at = service.now() - timedelta(seconds=1)
            await session.commit()
        await jobs.deliver_legal_emails({"brevo_client": email_client})
    async with TestSession() as session:
        delivery = await session.scalar(select(LegalEmailDelivery))
        contract = await session.scalar(select(ContractAcceptance))
        assert contract.status == "active" and delivery.status == "failed"
        delivery.created_at = service.now() - timedelta(minutes=10)
        await session.commit()
    assert (
        await client.post(
            f"/api/v1/legal/contracts/{contract.id}/resend-email", headers=auth(seeded.admin_id)
        )
    ).status_code == 200
    assert (
        await client.post(
            f"/api/v1/legal/contracts/{contract.id}/resend-email", headers=auth(seeded.student_id)
        )
    ).status_code == 429
    async with TestSession() as session:
        delivery = await session.scalar(
            select(LegalEmailDelivery).where(LegalEmailDelivery.attempt_number == 2)
        )
        delivery.provider_message_id = "message-2"
        delivery.status = "sent"
        await session.commit()
    from app.legal import router

    monkeypatch.setattr(router, "get_settings", lambda: settings)
    assert (
        await client.post(
            "/api/v1/legal/email/delivery-webhook",
            json={"event": "hard_bounce", "message-id": "message-2"},
        )
    ).status_code == 401
    response = await client.post(
        "/api/v1/legal/email/delivery-webhook",
        headers={"Authorization": "Bearer delivery-secret"},
        json={"event": "hard_bounce", "message-id": "message-2"},
    )
    assert response.status_code == 200
    async with TestSession() as session:
        delivery = await session.get(LegalEmailDelivery, delivery.id)
        assert delivery.status == "bounced"


async def test_old_checkout_uses_original_retired_version_and_refund_keeps_evidence(
    client: AsyncClient, seeded: SeededData
) -> None:
    checkout = await make_purchase(client, seeded, PRODUCTS[1])
    async with TestSession() as session:
        old = await session.scalar(
            select(LegalOfferVersion).where(LegalOfferVersion.product_code == PRODUCTS[1])
        )
        old.status = "retired"
        await session.flush()
        new = LegalOfferVersion(
            id=uuid4(),
            product_code=old.product_code,
            version_code="2026-10-16",
            title=old.title,
            publication_date=old.publication_date,
            effective_from=old.effective_from,
            status="active",
            pdf_storage_key=old.pdf_storage_key,
            markdown_storage_key=old.markdown_storage_key,
            pdf_sha256=old.pdf_sha256,
            markdown_sha256=old.markdown_sha256,
            pdf_size=old.pdf_size,
            financial_terms=financial_terms(),
        )
        session.add(new)
        await session.commit()
    await webhook(client, checkout)
    async with TestSession() as session:
        contract = await session.scalar(select(ContractAcceptance))
        assert contract.offer_version_id == old.id
        accepted = contract.accepted_at
    response = await client.post(
        f"/api/v1/admin/legal/contracts/{contract.id}/state",
        headers=auth(seeded.admin_id),
        json={
            "status": "refunded",
            "external_event_id": "refund-1",
            "amount_minor": 3_000_000,
            "reason": "Full refund",
        },
    )
    assert response.status_code == 200, response.text
    pdf = await client.get(
        f"/api/v1/legal/contracts/{contract.id}/offer.pdf", headers=auth(seeded.student_id)
    )
    assert hashlib.sha256(pdf.content).hexdigest() == old.pdf_sha256
    async with TestSession() as session:
        row = await session.get(ContractAcceptance, contract.id)
        assert row.accepted_at == accepted and row.status == "refunded"
        assert await session.scalar(select(func.count()).select_from(LegalEmailDelivery)) == 1


@pytest.mark.parametrize("problem", ["missing", "hash", "revoked"])
async def test_invalid_offer_blocks_checkout(
    client: AsyncClient, seeded: SeededData, monkeypatch: pytest.MonkeyPatch, problem: str
) -> None:
    await approved_application(client, seeded, PRODUCTS[1])
    if problem == "revoked":
        async with TestSession() as session:
            row = await session.scalar(
                select(LegalOfferVersion).where(LegalOfferVersion.product_code == PRODUCTS[1])
            )
            row.status = "revoked"
            await session.commit()
    else:

        async def broken(*args):
            raise storage.LegalDocumentError(
                "document_unavailable" if problem == "missing" else "legal_offer_hash_mismatch"
            )

        monkeypatch.setattr(service, "read_document", broken)
    response = await client.get(
        f"/api/v1/legal/products/{PRODUCTS[1]}/checkout", headers=auth(seeded.student_id)
    )
    assert response.status_code == 503


async def test_offer_and_contract_immutability_and_unique_active(
    client: AsyncClient, seeded: SeededData
) -> None:
    checkout = await make_purchase(client, seeded, PRODUCTS[1])
    await webhook(client, checkout)
    async with TestSession() as session:
        offer = await session.scalar(
            select(LegalOfferVersion).where(LegalOfferVersion.product_code == PRODUCTS[1])
        )
        offer.pdf_sha256 = "1" * 64
        with pytest.raises(ValueError, match="immutable"):
            await session.flush()
        await session.rollback()
        contract = await session.scalar(select(ContractAcceptance))
        contract.snapshot = {"tampered": True}
        with pytest.raises(ValueError, match="immutable"):
            await session.flush()
        await session.rollback()
        old = await session.scalar(
            select(LegalOfferVersion).where(LegalOfferVersion.product_code == PRODUCTS[1])
        )
        values = {
            column.name: getattr(old, column.name)
            for column in old.__table__.columns
            if column.name not in {"id", "created_at", "updated_at"}
        }
        session.add(LegalOfferVersion(id=uuid4(), **{**values, "version_code": "new"}))
        with pytest.raises(IntegrityError):
            await session.flush()


async def test_email_verification_single_use_rate_limit_and_email_change(
    client: AsyncClient, seeded: SeededData, monkeypatch: pytest.MonkeyPatch
) -> None:
    await approved_application(client, seeded, PRODUCTS[1])
    async with TestSession() as session:
        await session.execute(update(LegalEmailVerification).values(verified_at=None))
        await session.commit()
    # Age test helper's existing row to allow requesting a real code.
    async with TestSession() as session:
        await session.execute(
            update(LegalEmailVerification).values(created_at=service.now() - timedelta(minutes=2))
        )
        await session.commit()
    response = await client.post(
        "/api/v1/legal/email/request-code", headers=auth(seeded.student_id)
    )
    assert response.status_code == 200
    assert (
        await client.post("/api/v1/legal/email/request-code", headers=auth(seeded.student_id))
    ).status_code == 429
    async with TestSession() as session:
        delivery = await session.scalar(
            select(LegalEmailDelivery).where(
                LegalEmailDelivery.notification_type == "email.verification"
            )
        )
        code = re.search(r"\d{8}", delivery.body_snapshot).group()
        delivery_id = delivery.id

    def send(request: httpx.Request) -> httpx.Response:
        email = json.loads(request.content)
        recipient = email["to"][0]
        if "name" in recipient and not recipient["name"].strip():
            return httpx.Response(400, json={"code": "missing_parameter"})
        try:
            UUID(email["headers"]["idempotencyKey"])
        except ValueError:
            return httpx.Response(400, json={"code": "out_of_range"})
        assert recipient["email"] == "graduate@example.com"
        assert code in email["textContent"]
        assert "attachment" not in email
        return httpx.Response(201, json={"messageId": "verification-message"})

    settings = Settings(
        _env_file=None, brevo_api_key="test-key", brevo_from_email="sender@example.com"
    )
    monkeypatch.setattr(jobs, "get_settings", lambda: settings)
    monkeypatch.setattr(jobs, "async_session_factory", TestSession)
    async with httpx.AsyncClient(
        base_url="https://email.test", transport=httpx.MockTransport(send)
    ) as email_client:
        await jobs.deliver_legal_emails({"brevo_client": email_client})
    async with TestSession() as session:
        delivery = await session.get(LegalEmailDelivery, delivery_id)
        assert delivery.status == "sent"
        assert delivery.provider_message_id == "verification-message"
        assert delivery.retry_count == 0

    response = await client.post(
        "/api/v1/legal/email/confirm", headers=auth(seeded.student_id), json={"code": code}
    )
    assert response.status_code == 200
    assert (
        await client.post(
            "/api/v1/legal/email/confirm", headers=auth(seeded.student_id), json={"code": code}
        )
    ).status_code == 409


async def test_signed_production_webhook_is_required(
    client: AsyncClient, seeded: SeededData, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = await make_purchase(client, seeded, PRODUCTS[1])
    monkeypatch.setattr(
        payment_router,
        "settings",
        Settings(_env_file=None).model_copy(update={"app_env": "production"}),
    )
    response = await webhook(client, checkout)
    assert response.json()["status"] == "unverified"
    async with TestSession() as session:
        assert await session.scalar(select(func.count()).select_from(ContractAcceptance)) == 0


async def test_bundled_documents_match_manifest_and_markdown(seeded: SeededData) -> None:
    expected_hashes = {
        "repeat_python_mentorship": (
            "2f7a2c4e01609f37a9ebb04b7c93943d4f616cb2f55691ec409d41e9270bbd3f"
        ),
        "python_to_go_transition": (
            "d5482491d8cc7c5497885000b618f94cf1b38922f529fa129bb1fd9e2c42811b"
        ),
    }
    for row in manifest():
        assert row["pdf_sha256"] == expected_hashes[row["product_code"]]
        pdf = await storage.read_document(row["pdf_storage_key"], row["pdf_sha256"])
        md = await storage.read_document(row["markdown_storage_key"], row["markdown_sha256"])
        validate_files(pdf, md.decode())
        assert len(pdf) == row["pdf_size"]
        with pytest.raises(storage.LegalDocumentError):
            await storage.read_document(row["pdf_storage_key"], "0" * 64)


@pytest.mark.schema_change
async def test_migration_creates_schema_and_guards_bulk_sql(
    client: AsyncClient, seeded: SeededData, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text

    from tests.conftest import test_engine

    migration_path = (
        Path(__file__).parents[1] / "migrations/versions/20261016_0100_legal_contracts.py"
    )
    spec = importlib.util.spec_from_file_location("legal_contract_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    names = [
        "legal_questionnaire_drafts",
        "legal_audit_events",
        "legal_email_verifications",
        "legal_email_deliveries",
        "contract_acceptances",
        "legal_checkouts",
        "legal_offer_versions",
    ]
    async with test_engine.begin() as connection:
        for name in names:
            await connection.execute(text(f"DROP TABLE {name} CASCADE"))

        def upgrade(sync_connection):
            monkeypatch.setattr(
                migration, "op", Operations(MigrationContext.configure(sync_connection))
            )
            migration.upgrade()

        await connection.run_sync(upgrade)
    async with TestSession() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(LegalOfferVersion)
                .where(LegalOfferVersion.status == "active")
            )
            == 2
        )
        with pytest.raises(Exception, match="immutable"):
            await session.execute(
                text("UPDATE legal_offer_versions SET pdf_sha256 = repeat('0', 64)")
            )
        await session.rollback()
    checkout = await make_purchase(client, seeded, PRODUCTS[1])
    response = await webhook(client, checkout)
    assert response.json()["status"] == "ok"
    async with TestSession() as session:
        with pytest.raises(Exception, match="immutable"):
            await session.execute(text("UPDATE legal_checkouts SET snapshot = '{}'::jsonb"))
        await session.rollback()
        with pytest.raises(Exception, match="cannot be deleted"):
            await session.execute(text("DELETE FROM contract_acceptances"))
        await session.rollback()


async def test_go_schedule_uses_two_calendar_months_and_excludes_old_python(
    client: AsyncClient, seeded: SeededData
) -> None:
    from datetime import date
    from decimal import Decimal

    from app.payments.models import PaymentInstallment, StudentEmployment, StudentEmploymentStatus
    from app.payments.service import _regenerate_unpaid_installments

    checkout = await make_purchase(client, seeded, PRODUCTS[1])
    await webhook(client, checkout)
    async with TestSession() as session:
        employment = StudentEmployment(
            student_id=seeded.student_id,
            track_id=seeded.go_track_id,
            company_name="Go company",
            start_date=date(2027, 1, 31),
            billing_started_at=date(2027, 1, 31),
            net_salary_kopecks=25_000_001,
            repayment_percent=Decimal(100),
            status=StudentEmploymentStatus.ACTIVE,
            payment_day_first=10,
            payment_day_second=25,
        )
        session.add(employment)
        await session.flush()
        await _regenerate_unpaid_installments(session, employment)
        await session.flush()
        rows = list(
            await session.scalars(
                select(PaymentInstallment)
                .where(PaymentInstallment.employment_id == employment.id)
                .order_by(PaymentInstallment.sequence_number)
            )
        )
        assert [row.due_date for row in rows] == [date(2027, 2, 28), date(2027, 3, 31)]
        assert [row.amount_kopecks for row in rows] == [12_500_000, 12_500_001]


async def test_unknown_checkout_and_chargeback_are_audited(
    client: AsyncClient, seeded: SeededData
) -> None:
    checkout = await make_purchase(client, seeded, PRODUCTS[1])
    await webhook(client, checkout)
    response = await webhook(client, checkout, status="CHARGEBACK", event_id="chargeback-1")
    assert response.json()["status"] == "ok"
    async with TestSession() as session:
        contract = await session.scalar(select(ContractAcceptance))
        assert contract.status == "disputed"
        assert await session.scalar(
            select(LegalAuditEvent.id).where(
                LegalAuditEvent.event_type == "contract.payment_reversal"
            )
        )
    response = await webhook(
        client,
        {"payment_link_id": "legal_missing", "checkout_session_id": str(uuid4())},
        event_id="missing",
    )
    assert response.json()["status"] == "unverified"


async def test_document_tampering_blocks_email_and_admin_methods_are_protected(
    client: AsyncClient, seeded: SeededData, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = await make_purchase(client, seeded, PRODUCTS[1])
    await webhook(client, checkout)
    sent = []

    async def broken(*args):
        raise storage.LegalDocumentError("legal_offer_hash_mismatch")

    monkeypatch.setattr(jobs, "read_document", broken)
    monkeypatch.setattr(jobs, "async_session_factory", TestSession)
    async with httpx.AsyncClient(
        base_url="https://email.test",
        transport=httpx.MockTransport(lambda request: sent.append(request) or httpx.Response(201)),
    ) as email_client:
        await jobs.deliver_legal_emails({"brevo_client": email_client})
    assert not sent
    assert (
        await client.get("/api/v1/admin/legal/contracts", headers=auth(seeded.student_id))
    ).status_code == 403
    async with TestSession() as session:
        contract = await session.scalar(select(ContractAcceptance))
        assert contract.status == "active"
        assert await session.scalar(
            select(LegalAuditEvent.id).where(
                LegalAuditEvent.event_type == "alert.legal_offer_hash_mismatch"
            )
        )


@pytest.mark.parametrize("bank_status", ["APPROVED", "AUTHORIZED"])
async def test_production_uses_authenticated_operation_and_approval_time(
    client: AsyncClient, seeded: SeededData, monkeypatch: pytest.MonkeyPatch, bank_status: str
) -> None:
    from app.payments.tochka import TochkaPaymentService

    checkout = await make_purchase(client, seeded, PRODUCTS[1])
    paid_at = service.now()
    settings = Settings(_env_file=None).model_copy(update={"app_env": "production"})
    monkeypatch.setattr(payment_router, "settings", settings)
    # Signature parsing itself is covered by test_tochka; isolate the authenticated
    # operation lookup here using its documented Operation/Order envelope.
    monkeypatch.setattr(
        payment_router,
        "parse_webhook_body",
        lambda body, content_type, config: (json.loads(body), True),
    )

    async def operation_info(self, operation_id):
        return {
            "Data": {
                "Operation": [
                    {
                        "operationId": operation_id,
                        "consumerId": checkout["checkout_session_id"],
                        "amount": "30000.00",
                        "status": bank_status,
                        "Order": [
                            {
                                "type": "approval",
                                "orderId": "bank-approval-id",
                                "amount": "30000.00",
                                "time": paid_at.isoformat(),
                            }
                        ],
                    }
                ]
            }
        }

    monkeypatch.setattr(TochkaPaymentService, "get_payment_operation_info", operation_info)
    response = await webhook(client, checkout)
    assert response.json()["status"] == "ok"
    async with TestSession() as session:
        contract = await session.scalar(select(ContractAcceptance))
        if bank_status == "APPROVED":
            assert contract.accepted_at == paid_at
            assert contract.provider_paid_at == paid_at
        else:
            assert contract is None


async def test_concurrent_duplicate_webhooks_do_not_fail_or_duplicate(
    client: AsyncClient, seeded: SeededData
) -> None:
    import asyncio

    checkout = await make_purchase(client, seeded, PRODUCTS[1])
    responses = await asyncio.gather(webhook(client, checkout), webhook(client, checkout))
    assert all(response.status_code == 200 for response in responses)
    assert {response.json()["status"] for response in responses} <= {"ok", "duplicate"}
    async with TestSession() as session:
        assert await session.scalar(select(func.count()).select_from(ContractAcceptance)) == 1
        assert await session.scalar(select(func.count()).select_from(LegalEmailDelivery)) == 1
