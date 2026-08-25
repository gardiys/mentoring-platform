import json
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr

from app.core.config import Settings
from app.payments.tochka import (
    TochkaError,
    TochkaPaymentService,
    extract_payment_status,
    parse_payment_operation,
    parse_webhook_body,
    parse_webhook_event,
)


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="production",
        app_debug=False,
        database_url="postgresql+asyncpg://app:password@postgres:5432/mentoring",
        web_frontend_url="https://platform.example.com",
        cors_origins=["https://platform.example.com"],
        tochka_client_id="client-id",
        tochka_jwt_token="token",
        tochka_customer_code="300000092",
        tochka_redirect_url="https://platform.example.com/payments/success",
        tochka_fail_redirect_url="https://platform.example.com/payments/fail",
    )


@pytest.mark.parametrize(
    ("amount_kopecks", "expected_amount"),
    [(6_250_000, 62_500), (6_250_001, 62_500.01)],
)
async def test_payment_receipt_amounts_match_working_onboarding_format(
    amount_kopecks: int,
    expected_amount: int | float,
) -> None:
    captured_payload: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured_payload.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "Data": {
                    "paymentLinkId": "payment-link-id",
                    "paymentLink": "https://payment.example.com/link",
                }
            },
        )

    async with httpx.AsyncClient(
        base_url="https://enter.tochka.com/uapi",
        transport=httpx.MockTransport(handler),
    ) as client:
        await TochkaPaymentService(_settings(), client).create_payment_link(
            installment_id=uuid4(),
            payment_link_id="payment-link-id",
            amount_kopecks=amount_kopecks,
            client_name="Иван",
            client_email="ivan@example.com",
        )

    data = captured_payload["Data"]
    assert isinstance(data, dict)
    assert data["amount"] == f"{expected_amount:.2f}"
    items = data["Items"]
    assert isinstance(items, list)
    assert items[0]["amount"] == f"{expected_amount:.2f}"
    success_url = urlparse(data["redirectUrl"])
    failure_url = urlparse(data["failRedirectUrl"])
    assert success_url.path == "/payments/success"
    assert failure_url.path == "/payments/fail"
    assert parse_qs(success_url.query) == {
        "payment_status": ["success"],
        "payment_link_id": ["payment-link-id"],
    }
    assert parse_qs(failure_url.query) == {
        "payment_status": ["failed"],
        "payment_link_id": ["payment-link-id"],
    }


async def test_payment_link_error_contains_safe_provider_detail() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "code": "400",
                "id": "error-id",
                "message": "Что-то пошло не так",
                "Errors": [
                    {
                        "errorCode": "Validation Error",
                        "message": "amount must be a number",
                        "url": "https://developers.tochka.com/",
                    }
                ],
            },
        )

    async with httpx.AsyncClient(
        base_url="https://enter.tochka.com/uapi",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(
            TochkaError,
            match=(
                "HTTP 400: 400; error-id; Что-то пошло не так; "
                "Validation Error \\| amount must be a number"
            ),
        ):
            await TochkaPaymentService(_settings(), client).create_payment_link(
                installment_id=uuid4(),
                payment_link_id="payment-link-id",
                amount_kopecks=6_250_000,
                client_name="Иван",
                client_email="ivan@example.com",
            )


async def test_payment_transport_tls_failure_is_reported_as_tochka_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            "[SSL: CERTIFICATE_VERIFY_FAILED] self-signed certificate in certificate chain",
            request=request,
        )

    async with httpx.AsyncClient(
        base_url="https://enter.tochka.com/uapi",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(
            TochkaError,
            match="leave TOCHKA_PROXY_URL empty for a direct connection",
        ):
            await TochkaPaymentService(_settings(), client).create_payment_link(
                installment_id=uuid4(),
                payment_link_id="payment-link-id",
                amount_kopecks=6_250_000,
                client_name="Иван",
                client_email="ivan@example.com",
            )


async def test_payment_client_does_not_inherit_process_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_options: dict[str, object] = {}

    class CapturingClient:
        def __init__(self, **options: object) -> None:
            captured_options.update(options)

        async def __aenter__(self) -> "CapturingClient":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def post(self, _path: str, **_options: object) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "Data": {
                        "paymentLinkId": "payment-link-id",
                        "paymentLink": "https://payment.example.com/link",
                    }
                },
            )

    monkeypatch.setattr(httpx, "AsyncClient", CapturingClient)

    result = await TochkaPaymentService(_settings()).create_payment_link(
        installment_id=uuid4(),
        payment_link_id="payment-link-id",
        amount_kopecks=6_250_000,
        client_name="Иван",
        client_email="ivan@example.com",
    )

    assert result.payment_url == "https://payment.example.com/link"
    assert captured_options["proxy"] is None
    assert captured_options["trust_env"] is False


@pytest.mark.parametrize(
    "redirect_url",
    [
        "http://platform.example.com/payments",
        "https:platform.example.com/payments",
        "https:///payments",
        "https://user:password@platform.example.com/payments",
        "https://platform.example.com/payments#fragment",
    ],
)
async def test_payment_link_rejects_non_absolute_https_redirect_before_provider_request(
    redirect_url: str,
) -> None:
    provider_called = False

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal provider_called
        provider_called = True
        return httpx.Response(200, json={})

    settings = _settings().model_copy(update={"tochka_redirect_url": redirect_url})
    async with httpx.AsyncClient(
        base_url="https://enter.tochka.com/uapi",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(TochkaError, match="must be an absolute HTTPS URL"):
            await TochkaPaymentService(settings, client).create_payment_link(
                installment_id=uuid4(),
                payment_link_id="payment-link-id",
                amount_kopecks=6_250_000,
                client_name="Иван",
                client_email="ivan@example.com",
            )

    assert provider_called is False


@pytest.mark.parametrize(
    "payment_url",
    [
        "javascript:alert(1)",
        "http://payment.example.com/link",
        "https://user:password@payment.example.com/link",
        "https://payment.example.com/video\nLocation: https://evil.example.com",
        "https://payment.example.com:invalid/link",
        "//payment.example.com/link",
    ],
)
async def test_payment_link_rejects_unsafe_provider_url(payment_url: str) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "Data": {
                    "paymentLinkId": "payment-link-id",
                    "paymentLink": payment_url,
                }
            },
        )

    async with httpx.AsyncClient(
        base_url="https://enter.tochka.com/uapi",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(TochkaError, match="invalid payment URL"):
            await TochkaPaymentService(_settings(), client).create_payment_link(
                installment_id=uuid4(),
                payment_link_id="payment-link-id",
                amount_kopecks=6_250_000,
                client_name="Иван",
                client_email="ivan@example.com",
            )


async def test_operation_lookup_rejects_path_injection_before_provider_request() -> None:
    provider_called = False

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal provider_called
        provider_called = True
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(
        base_url="https://enter.tochka.com/uapi",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(ValueError, match="Invalid Tochka operationId"):
            await TochkaPaymentService(_settings(), client).get_payment_operation_info(
                "../../webhook/v1.0/client-id?poison=true"
            )

    assert provider_called is False


@pytest.mark.parametrize(
    "provider_response",
    [
        ["not", "an", "object"],
        "not-json",
    ],
)
async def test_payment_link_rejects_malformed_provider_response(
    provider_response: object,
) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        if isinstance(provider_response, str):
            return httpx.Response(200, text=provider_response)
        return httpx.Response(200, json=provider_response)

    async with httpx.AsyncClient(
        base_url="https://enter.tochka.com/uapi",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(TochkaError, match="invalid"):
            await TochkaPaymentService(_settings(), client).create_payment_link(
                installment_id=uuid4(),
                payment_link_id="payment-link-id",
                amount_kopecks=6_250_000,
                client_name="Иван",
                client_email="ivan@example.com",
            )


@pytest.mark.parametrize(
    "payload",
    [
        {
            "event": "acquiringInternetPayment",
            "Data": {
                "paymentLinkId": "payment-link-id",
                "operationId": "../../other-endpoint",
                "status": "APPROVED",
            },
        },
        {
            "event": "acquiringInternetPayment",
            "Data": {
                "paymentLinkId": "x" * 65,
                "operationId": "operation-id",
                "status": "APPROVED",
            },
        },
    ],
)
def test_webhook_rejects_invalid_provider_identifiers(payload: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="Invalid Tochka"):
        parse_webhook_event(payload)


def test_webhook_rejects_invalid_payment_status() -> None:
    with pytest.raises(ValueError, match="Invalid Tochka payment status"):
        parse_webhook_event(
            {
                "event": "acquiringInternetPayment",
                "Data": {
                    "paymentLinkId": "payment-link-id",
                    "status": "APPROVED\u0000POISONED",
                },
            }
        )

    with pytest.raises(ValueError, match="Invalid Tochka payment status"):
        extract_payment_status({"Data": {"status": "APPROVED\u0000POISONED"}})


def test_payment_operation_extracts_binding_fields_and_amount() -> None:
    installment_id = uuid4()

    operation = parse_payment_operation(
        {
            "Data": {
                "Operation": [
                    {
                        "paymentLinkId": "payment-link-id",
                        "operationId": "operation-id",
                        "consumerId": str(installment_id),
                        "amount": "62500.01",
                        "status": "APPROVED",
                    }
                ]
            }
        }
    )

    assert operation.payment_link_id == "payment-link-id"
    assert operation.operation_id == "operation-id"
    assert operation.consumer_id == str(installment_id)
    assert operation.amount_kopecks == 6_250_001
    assert operation.status == "APPROVED"


@pytest.mark.parametrize("amount", [True, "1.001", "NaN", "Infinity", "1e100"])
def test_payment_operation_rejects_invalid_amount(amount: object) -> None:
    with pytest.raises(ValueError, match="Invalid Tochka payment amount"):
        parse_payment_operation({"Data": {"amount": amount}})


def test_webhook_normalizes_excessive_json_nesting_to_value_error() -> None:
    settings = _settings()
    body = ('{"Data":' * 10_000 + "{}" + "}" * 10_000).encode()

    with pytest.raises(ValueError, match="too deeply nested"):
        parse_webhook_body(body, "application/json", settings)


async def test_webhook_configuration_error_contains_safe_provider_detail() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "code": "403",
                "message": "Forbidden by consent",
                "Errors": [
                    {
                        "errorCode": "Missing permission",
                        "message": "ManageWebhookData is required",
                    }
                ],
            },
        )

    async with httpx.AsyncClient(
        base_url="https://enter.tochka.com/uapi",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(
            TochkaError,
            match=(
                "HTTP 403: 403; Forbidden by consent; "
                "Missing permission \\| ManageWebhookData is required"
            ),
        ):
            await TochkaPaymentService(_settings(), client).configure_webhook(
                "https://platform.example.com/api/v1/payments/tochka/webhook"
            )


def test_signed_webhook_accepts_official_jwk_json_public_key() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    token = jwt.encode(
        {"event": "acquiringInternetPayment", "Data": {"status": "APPROVED"}},
        private_key,
        algorithm="RS256",
    )
    settings = _settings().model_copy(
        update={"tochka_public_key": SecretStr(json.dumps(public_jwk))}
    )

    payload, is_signed = parse_webhook_body(token.encode(), "text/plain; charset=utf-8", settings)

    assert is_signed is True
    assert payload["event"] == "acquiringInternetPayment"
