import json
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest

from app.core.config import Settings
from app.payments.tochka import TochkaError, TochkaPaymentService


def _settings() -> Settings:
    return Settings(
        app_env="production",
        web_frontend_url="https://platform.example.com",
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


async def test_payment_link_rejects_http_redirect_before_provider_request() -> None:
    provider_called = False

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal provider_called
        provider_called = True
        return httpx.Response(200, json={})

    settings = _settings().model_copy(
        update={"tochka_redirect_url": "http://platform.example.com/payments"}
    )
    async with httpx.AsyncClient(
        base_url="https://enter.tochka.com/uapi",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(TochkaError, match="TOCHKA_REDIRECT_URL must use HTTPS"):
            await TochkaPaymentService(settings, client).create_payment_link(
                installment_id=uuid4(),
                payment_link_id="payment-link-id",
                amount_kopecks=6_250_000,
                client_name="Иван",
                client_email="ivan@example.com",
            )

    assert provider_called is False
