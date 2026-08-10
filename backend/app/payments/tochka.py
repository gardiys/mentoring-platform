from __future__ import annotations

import base64
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

import httpx
import jwt

from app.core.config import Settings

logger = logging.getLogger(__name__)


class TochkaError(RuntimeError):
    pass


@dataclass(frozen=True)
class PaymentLinkResult:
    payment_link_id: str
    provider_operation_id: str | None
    payment_url: str
    raw_response: dict[str, Any]


@dataclass(frozen=True)
class TochkaWebhookEvent:
    event_id: str | None
    payment_link_id: str | None
    status: str
    operation_id: str | None
    raw_payload: dict[str, Any]

    @property
    def deduplication_key(self) -> str:
        if self.event_id:
            return f"tochka:event:{self.event_id}"
        return (
            f"tochka:{self.payment_link_id or 'none'}:{self.status}:{self.operation_id or 'none'}"
        )


class TochkaPaymentService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.client = client

    async def create_payment_link(
        self,
        *,
        installment_id: UUID,
        payment_link_id: str,
        amount_kopecks: int,
        client_name: str,
        client_email: str,
    ) -> PaymentLinkResult:
        if not self.settings.tochka_client_id or self.settings.tochka_jwt_token is None:
            if self.settings.app_env == "development":
                return PaymentLinkResult(
                    payment_link_id=payment_link_id,
                    provider_operation_id=None,
                    payment_url=_add_query_params(
                        f"{self.settings.web_frontend_url.rstrip('/')}/payments",
                        local_payment=payment_link_id,
                    ),
                    raw_response={"mode": "local_stub"},
                )
            raise TochkaError("Tochka Bank payments are not configured")
        if not client_email:
            raise TochkaError("Student email is required to create a fiscal receipt")

        token = self.settings.tochka_jwt_token.get_secret_value()
        customer_code = self.settings.tochka_customer_code or _customer_code_from_jwt(token)
        if not customer_code:
            raise TochkaError("TOCHKA_CUSTOMER_CODE is not configured")

        amount = Decimal(amount_kopecks) / Decimal(100)
        supplier = _supplier(self.settings)
        item: dict[str, Any] = {
            "vatType": self.settings.tochka_receipt_vat_type,
            "name": self.settings.tochka_receipt_item_name,
            "amount": _format_amount(amount),
            "quantity": 1,
            "paymentMethod": self.settings.tochka_receipt_payment_method,
            "paymentObject": self.settings.tochka_receipt_payment_object,
            "measure": self.settings.tochka_receipt_measure,
        }
        if supplier:
            item["Supplier"] = supplier
        success_url = _tochka_redirect_url(
            self.settings.tochka_redirect_url
            or f"{self.settings.web_frontend_url.rstrip('/')}/payments",
            setting_name="TOCHKA_REDIRECT_URL",
            payment_status="success",
            payment_link_id=payment_link_id,
        )
        failure_url = _tochka_redirect_url(
            self.settings.tochka_fail_redirect_url
            or f"{self.settings.web_frontend_url.rstrip('/')}/payments",
            setting_name="TOCHKA_FAIL_REDIRECT_URL",
            payment_status="failed",
            payment_link_id=payment_link_id,
        )
        data: dict[str, Any] = {
            "customerCode": customer_code,
            "amount": _format_amount(amount),
            "purpose": self.settings.tochka_payment_purpose,
            "paymentMode": self.settings.tochka_payment_modes,
            "paymentLinkId": payment_link_id,
            "consumerId": str(installment_id),
            "taxSystemCode": self.settings.tochka_receipt_tax_system_code,
            "Client": {"name": client_name, "email": client_email},
            "Items": [item],
            "redirectUrl": success_url,
            "failRedirectUrl": failure_url,
        }
        if supplier:
            data["Supplier"] = supplier
        payload = {"Data": data}

        async def request(client: httpx.AsyncClient) -> dict[str, Any]:
            response = await client.post(
                "/acquiring/v1.0/payments_with_receipt",
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Client-Id": self.settings.tochka_client_id or "",
                },
            )
            if response.is_error:
                detail = _provider_error_detail(response)
                logger.warning(
                    "Tochka Bank rejected payment link creation status=%s detail=%s",
                    response.status_code,
                    detail or "not provided",
                )
                suffix = f": {detail}" if detail else ""
                raise TochkaError(
                    f"Tochka Bank rejected the payment: HTTP {response.status_code}{suffix}"
                )
            return cast(dict[str, Any], response.json())

        raw = await self._request(request)
        response_data = raw.get("Data") if isinstance(raw.get("Data"), dict) else raw
        assert isinstance(response_data, dict)
        payment_url = _find_first(
            response_data,
            ("paymentLink", "paymentUrl", "payment_url", "link", "url"),
        )
        if not payment_url:
            raise TochkaError("Tochka Bank response does not contain a payment URL")
        return PaymentLinkResult(
            payment_link_id=str(
                _find_first(response_data, ("paymentLinkId", "payment_link_id")) or payment_link_id
            ),
            provider_operation_id=_string_or_none(
                _find_first(response_data, ("operationId", "operation_id"))
            ),
            payment_url=str(payment_url),
            raw_response=raw,
        )

    async def get_payment_operation_info(self, operation_id: str) -> dict[str, Any]:
        if not self.settings.tochka_client_id or self.settings.tochka_jwt_token is None:
            raise TochkaError("Tochka Bank payments are not configured")
        token = self.settings.tochka_jwt_token.get_secret_value()

        async def request(client: httpx.AsyncClient) -> dict[str, Any]:
            response = await client.get(
                f"/acquiring/v1.0/payments/{operation_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Client-Id": self.settings.tochka_client_id or "",
                },
            )
            if response.is_error:
                raise TochkaError(f"Could not verify Tochka payment: HTTP {response.status_code}")
            return cast(dict[str, Any], response.json())

        return await self._request(request)

    async def configure_webhook(self, callback_url: str) -> dict[str, Any]:
        if not self.settings.tochka_client_id or self.settings.tochka_jwt_token is None:
            raise TochkaError("Tochka Bank payments are not configured")
        token = self.settings.tochka_jwt_token.get_secret_value()

        async def request(client: httpx.AsyncClient) -> dict[str, Any]:
            response = await client.put(
                f"/webhook/v1.0/{self.settings.tochka_client_id}",
                json={"webhooksList": ["acquiringInternetPayment"], "url": callback_url},
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Client-Id": self.settings.tochka_client_id or "",
                },
            )
            if response.is_error:
                raise TochkaError(
                    f"Could not configure Tochka webhook: HTTP {response.status_code}"
                )
            return cast(dict[str, Any], response.json())

        return await self._request(request)

    async def _request(
        self,
        callback: Callable[[httpx.AsyncClient], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        if self.client is not None:
            return await callback(self.client)
        proxy = (
            self.settings.tochka_proxy_url.get_secret_value()
            if self.settings.tochka_proxy_url is not None
            else None
        )
        async with httpx.AsyncClient(
            base_url=_normalize_api_base_url(self.settings.tochka_api_base_url),
            timeout=self.settings.tochka_request_timeout_seconds,
            proxy=proxy,
        ) as client:
            return await callback(client)


def parse_webhook_body(
    body: bytes, content_type: str, settings: Settings
) -> tuple[dict[str, Any], bool]:
    text = body.decode("utf-8").strip()
    if "application/json" in content_type:
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("Webhook JSON must be an object")
        return payload, False
    if text.count(".") >= 2:
        public_key = (
            settings.tochka_public_key.get_secret_value().replace("\\n", "\n")
            if settings.tochka_public_key is not None
            else ""
        )
        if public_key:
            payload = jwt.decode(
                text,
                public_key,
                algorithms=["RS256"],
                options={"verify_aud": False},
            )
            if not isinstance(payload, dict):
                raise ValueError("Webhook JWT payload must be an object")
            return payload, True
        if settings.app_env == "production":
            raise ValueError("TOCHKA_PUBLIC_KEY is required for signed production webhooks")
        return _decode_unverified_jwt(text), False
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("Webhook JSON must be an object")
    return payload, False


def parse_webhook_event(payload: dict[str, Any]) -> TochkaWebhookEvent | None:
    event_type = str(payload.get("event") or payload.get("eventType") or payload.get("type") or "")
    if event_type and not any(
        word in event_type.lower() for word in ("acquiring", "payment", "internet")
    ):
        return None
    data = _event_data(payload)
    payment_link_id = _find_first(data, ("paymentLinkId", "payment_link_id", "orderId"))
    operation_id = _find_first(data, ("operationId", "operation_id"))
    if not payment_link_id and not operation_id:
        raise ValueError("Webhook does not contain paymentLinkId or operationId")
    status = _find_first(data, ("status", "operationStatus"))
    if not status:
        raise ValueError("Webhook does not contain a payment status")
    return TochkaWebhookEvent(
        event_id=_string_or_none(
            _find_first(payload, ("eventId", "event_id"))
            or _find_first(data, ("eventId", "event_id"))
        ),
        payment_link_id=_string_or_none(payment_link_id),
        status=str(status).upper(),
        operation_id=_string_or_none(operation_id),
        raw_payload=payload,
    )


def extract_payment_status(payload: dict[str, Any]) -> str | None:
    data = payload.get("Data") if isinstance(payload.get("Data"), dict) else payload
    assert isinstance(data, dict)
    value = _find_first(data, ("status", "operationStatus"))
    return str(value).upper() if value else None


def map_payment_status(status: str) -> str:
    normalized = status.upper()
    if normalized in {"APPROVED", "CAPTURED", "CONFIRMED", "SUCCESS", "SUCCEEDED"}:
        return "approved"
    if normalized in {"FAILED", "DECLINED", "REJECTED", "ERROR", "EXPIRED"}:
        return "failed"
    if normalized in {"CANCELLED", "CANCELED"}:
        return "cancelled"
    return "manual_review"


def _normalize_api_base_url(value: str) -> str:
    normalized = value.rstrip("/")
    return normalized if normalized.endswith("/uapi") else f"{normalized}/uapi"


def _tochka_redirect_url(url: str, *, setting_name: str, **params: str) -> str:
    if urlsplit(url).scheme.lower() != "https":
        raise TochkaError(f"{setting_name} must use HTTPS when creating a Tochka Bank payment link")
    return _add_query_params(url, **params)


def _format_amount(value: Decimal) -> str:
    """Match the receipt amount format used by the working onboarding integration."""
    return str(value.quantize(Decimal("0.01")))


def _provider_error_detail(response: httpx.Response) -> str | None:
    """Extract a bounded provider error without logging the request or credentials."""
    try:
        payload = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = None

    candidates: list[object] = []
    if isinstance(payload, dict):
        for key in (
            "code",
            "id",
            "message",
            "error",
            "error_description",
            "description",
            "detail",
        ):
            value = payload.get(key)
            if value not in (None, "", [], {}):
                candidates.append(value)
        errors = payload.get("Errors")
        if isinstance(errors, list):
            for error in errors:
                if not isinstance(error, dict):
                    continue
                parts = [
                    str(error[key])
                    for key in ("errorCode", "message", "url")
                    if error.get(key) not in (None, "")
                ]
                if parts:
                    candidates.append(" | ".join(parts))
        data = payload.get("Data")
        if isinstance(data, dict):
            for key in ("code", "message", "error", "description", "detail"):
                value = data.get(key)
                if value not in (None, "", [], {}):
                    candidates.append(value)

    if candidates:
        detail = "; ".join(
            value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            for value in candidates
        )
    else:
        detail = response.text
    compact = " ".join(detail.split()).strip()
    return compact[:500] or None


def _supplier(settings: Settings) -> dict[str, str]:
    values = {
        "name": settings.tochka_supplier_name,
        "phone": settings.tochka_supplier_phone,
        "taxCode": settings.tochka_supplier_tax_code,
    }
    return {key: value for key, value in values.items() if value}


def _customer_code_from_jwt(token: str) -> str | None:
    try:
        payload = _decode_unverified_jwt(token)
    except (ValueError, json.JSONDecodeError):
        return None
    return _string_or_none(payload.get("customer_code") or payload.get("customerCode"))


def _decode_unverified_jwt(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) < 2:
        raise ValueError("Invalid JWT")
    decoded = base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4))
    payload = json.loads(decoded)
    if not isinstance(payload, dict):
        raise ValueError("JWT payload must be an object")
    return payload


def _event_data(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("payload", "Data"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return payload


def _find_first(payload: dict[str, Any], keys: tuple[str, ...]) -> object | None:
    for key in keys:
        if payload.get(key) not in (None, ""):
            return cast(object, payload[key])
    for value in payload.values():
        if isinstance(value, dict):
            nested = _find_first(value, keys)
            if nested not in (None, ""):
                return nested
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    nested = _find_first(item, keys)
                    if nested not in (None, ""):
                        return nested
    return None


def _add_query_params(url: str, **params: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(params)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _string_or_none(value: object) -> str | None:
    return str(value) if value is not None else None
