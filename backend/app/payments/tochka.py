from __future__ import annotations

import base64
import json
import logging
import re
import ssl
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

_PROVIDER_IDENTIFIER_PATTERN = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:-]*\Z")
_PROVIDER_STATUS_PATTERN = re.compile(r"\A[A-Z][A-Z0-9_-]*\Z")
_MAX_PROVIDER_IDENTIFIER_LENGTH = 255
_MAX_PAYMENT_LINK_IDENTIFIER_LENGTH = 64
_MAX_PAYMENT_URL_LENGTH = 2_048
_MAX_PROVIDER_RESPONSE_NODES = 10_000
_MAX_PROVIDER_RESPONSE_DEPTH = 20
_MAX_PAYMENT_AMOUNT_KOPECKS = 9_223_372_036_854_775_807


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


@dataclass(frozen=True)
class TochkaPaymentOperation:
    payment_link_id: str | None
    operation_id: str | None
    consumer_id: str | None
    amount_kopecks: int | None
    status: str | None


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
        return_path: str | None = None,
    ) -> PaymentLinkResult:
        payment_link_id = _validate_provider_identifier(
            payment_link_id,
            name="paymentLinkId",
            max_length=_MAX_PAYMENT_LINK_IDENTIFIER_LENGTH,
        )
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
        return_url = (
            _frontend_return_url(self.settings.web_frontend_url, return_path)
            if return_path is not None
            else None
        )
        success_url = _tochka_redirect_url(
            return_url
            or self.settings.tochka_redirect_url
            or f"{self.settings.web_frontend_url.rstrip('/')}/payments",
            setting_name="TOCHKA_REDIRECT_URL",
            payment_status="success",
            payment_link_id=payment_link_id,
        )
        failure_url = _tochka_redirect_url(
            return_url
            or self.settings.tochka_fail_redirect_url
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
            return _provider_response_object(response)

        raw = await self._request(request)
        response_data = raw.get("Data") if isinstance(raw.get("Data"), dict) else raw
        assert isinstance(response_data, dict)
        try:
            payment_url = _find_first(
                response_data,
                ("paymentLink", "paymentUrl", "payment_url", "link", "url"),
            )
            if not payment_url:
                raise TochkaError("Tochka Bank response does not contain a payment URL")
            returned_payment_link_id = _validate_provider_identifier(
                str(
                    _find_first(response_data, ("paymentLinkId", "payment_link_id"))
                    or payment_link_id
                ),
                name="paymentLinkId",
                max_length=_MAX_PAYMENT_LINK_IDENTIFIER_LENGTH,
            )
            operation_id = _optional_provider_identifier(
                _find_first(response_data, ("operationId", "operation_id")),
                name="operationId",
            )
        except ValueError as error:
            raise TochkaError("Tochka Bank returned an invalid response") from error
        validated_payment_url = _validate_payment_url(str(payment_url))
        return PaymentLinkResult(
            payment_link_id=returned_payment_link_id,
            provider_operation_id=operation_id,
            payment_url=validated_payment_url,
            raw_response=raw,
        )

    async def get_payment_operation_info(self, operation_id: str) -> dict[str, Any]:
        if not self.settings.tochka_client_id or self.settings.tochka_jwt_token is None:
            raise TochkaError("Tochka Bank payments are not configured")
        operation_id = _validate_provider_identifier(operation_id, name="operationId")
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
            return _provider_response_object(response)

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
                detail = _provider_error_detail(response)
                logger.warning(
                    "Tochka Bank rejected webhook configuration status=%s detail=%s",
                    response.status_code,
                    detail or "not provided",
                )
                suffix = f": {detail}" if detail else ""
                raise TochkaError(
                    f"Could not configure Tochka webhook: HTTP {response.status_code}{suffix}"
                )
            return _provider_response_object(response)

        return await self._request(request)

    async def _request(
        self,
        callback: Callable[[httpx.AsyncClient], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        proxy = (
            self.settings.tochka_proxy_url.get_secret_value()
            if self.settings.tochka_proxy_url is not None
            else None
        )
        try:
            if self.client is not None:
                return await callback(self.client)
            verify: bool | ssl.SSLContext = True
            if self.settings.tochka_ca_bundle_path is not None:
                verify = ssl.create_default_context(
                    cafile=self.settings.tochka_ca_bundle_path
                )
            async with httpx.AsyncClient(
                base_url=_normalize_api_base_url(self.settings.tochka_api_base_url),
                timeout=self.settings.tochka_request_timeout_seconds,
                proxy=proxy,
                verify=verify,
                # Payment traffic must only use the explicitly configured proxy.
                # Inheriting HTTP(S)_PROXY from the host can unexpectedly route
                # bank requests through a TLS-intercepting corporate proxy.
                trust_env=False,
            ) as client:
                return await callback(client)
        except httpx.TimeoutException as error:
            logger.warning(
                "Tochka Bank request timed out proxy_configured=%s",
                proxy is not None,
            )
            raise TochkaError("Tochka Bank did not respond before the timeout") from error
        except httpx.ProxyError as error:
            logger.warning(
                "Tochka Bank proxy connection failed proxy_configured=%s",
                proxy is not None,
            )
            raise TochkaError(
                "Could not connect to Tochka Bank through TOCHKA_PROXY_URL; "
                "check the proxy address, access rules and TLS certificate"
            ) from error
        except httpx.ConnectError as error:
            message = str(error).lower()
            if "certificate_verify_failed" in message or "self-signed certificate" in message:
                logger.warning(
                    "Tochka Bank TLS certificate verification failed proxy_configured=%s",
                    proxy is not None,
                )
                raise TochkaError(
                    "Could not verify the TLS certificate while connecting to Tochka Bank; "
                    "check that TOCHKA_CA_BUNDLE_PATH contains the current Russian Trusted CA "
                    "chain and that TOCHKA_PROXY_URL does not intercept TLS"
                ) from error
            logger.warning(
                "Tochka Bank connection failed proxy_configured=%s",
                proxy is not None,
            )
            raise TochkaError("Could not connect to Tochka Bank") from error
        except httpx.RequestError as error:
            logger.warning(
                "Tochka Bank transport failed error_type=%s proxy_configured=%s",
                type(error).__name__,
                proxy is not None,
            )
            raise TochkaError("Could not complete the request to Tochka Bank") from error
        except OSError as error:
            logger.warning(
                "Tochka Bank CA bundle could not be loaded proxy_configured=%s",
                proxy is not None,
            )
            raise TochkaError(
                "Could not load the trusted CA bundle for Tochka Bank; "
                "check TOCHKA_CA_BUNDLE_PATH in the backend container"
            ) from error


def parse_webhook_body(
    body: bytes, content_type: str, settings: Settings
) -> tuple[dict[str, Any], bool]:
    try:
        text = body.decode("utf-8").strip()
    except UnicodeDecodeError as error:
        raise ValueError("Webhook body must be valid UTF-8") from error
    if not text:
        raise ValueError("Webhook body must not be empty")
    if "application/json" in content_type:
        return _decode_json_object(text, context="Webhook JSON"), False
    if text.count(".") >= 2:
        public_key = (
            settings.tochka_public_key.get_secret_value().replace("\\n", "\n")
            if settings.tochka_public_key is not None
            else ""
        )
        if public_key:
            try:
                payload = jwt.decode(
                    text,
                    _webhook_verification_key(public_key),
                    algorithms=["RS256"],
                    options={"verify_aud": False},
                )
            except (jwt.PyJWTError, TypeError, ValueError, RecursionError) as error:
                raise ValueError("Invalid Tochka webhook signature") from error
            if not isinstance(payload, dict):
                raise ValueError("Webhook JWT payload must be an object")
            return payload, True
        if settings.app_env == "production":
            raise ValueError("TOCHKA_PUBLIC_KEY is required for signed production webhooks")
        return _decode_unverified_jwt(text), False
    return _decode_json_object(text, context="Webhook JSON"), False


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
    normalized_status = _normalize_provider_status(status)
    return TochkaWebhookEvent(
        event_id=_optional_provider_identifier(
            _find_first(payload, ("eventId", "event_id"))
            or _find_first(data, ("eventId", "event_id")),
            name="eventId",
        ),
        payment_link_id=_optional_provider_identifier(
            payment_link_id,
            name="paymentLinkId",
            max_length=_MAX_PAYMENT_LINK_IDENTIFIER_LENGTH,
        ),
        status=normalized_status,
        operation_id=_optional_provider_identifier(operation_id, name="operationId"),
        raw_payload=payload,
    )


def extract_payment_status(payload: dict[str, Any]) -> str | None:
    data = payload.get("Data") if isinstance(payload.get("Data"), dict) else payload
    assert isinstance(data, dict)
    value = _find_first(data, ("status", "operationStatus"))
    return _normalize_provider_status(value) if value else None


def parse_payment_operation(payload: dict[str, Any]) -> TochkaPaymentOperation:
    """Parse identity fields returned by Get Payment Operation Info.

    Unlike a webhook signature, this response is fetched with this merchant's
    credentials and can therefore be used to bind an event to a local payment.
    """
    data = payload.get("Data") if isinstance(payload.get("Data"), dict) else payload
    assert isinstance(data, dict)
    raw_amount = _find_first(data, ("amount", "Amount"))
    if isinstance(raw_amount, dict):
        raw_amount = _find_first(raw_amount, ("value", "amount", "sum"))
    return TochkaPaymentOperation(
        payment_link_id=_optional_provider_identifier(
            _find_first(data, ("paymentLinkId", "payment_link_id", "orderId")),
            name="paymentLinkId",
            max_length=_MAX_PAYMENT_LINK_IDENTIFIER_LENGTH,
        ),
        operation_id=_optional_provider_identifier(
            _find_first(data, ("operationId", "operation_id")),
            name="operationId",
        ),
        consumer_id=_optional_provider_identifier(
            _find_first(data, ("consumerId", "consumer_id")),
            name="consumerId",
        ),
        amount_kopecks=_optional_amount_kopecks(raw_amount),
        status=extract_payment_status(data),
    )


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
    try:
        parsed = urlsplit(url)
        _ = parsed.port
    except ValueError as error:
        raise TochkaError(
            f"{setting_name} must be an absolute HTTPS URL when creating a Tochka Bank payment link"
        ) from error
    if (
        parsed.scheme.lower() != "https"
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise TochkaError(
            f"{setting_name} must be an absolute HTTPS URL when creating a Tochka Bank payment link"
        )
    return _add_query_params(url, **params)


def _frontend_return_url(origin: str, path: str) -> str:
    parsed = urlsplit(path)
    if (
        not path.startswith("/")
        or path.startswith("//")
        or parsed.scheme
        or parsed.netloc
        or parsed.fragment
    ):
        raise TochkaError("The internal Tochka return path is invalid")
    return f"{origin.rstrip('/')}{path}"


def _format_amount(value: Decimal) -> str:
    """Match the receipt amount format used by the working onboarding integration."""
    return str(value.quantize(Decimal("0.01")))


def _provider_error_detail(response: httpx.Response) -> str | None:
    """Extract a bounded provider error without logging the request or credentials."""
    try:
        payload = response.json()
    except (ValueError, UnicodeDecodeError, RecursionError):
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


def _webhook_verification_key(value: str) -> Any:
    """Accept both the official Tochka JWK JSON and a legacy PEM key."""
    compact = value.strip()
    if not compact.startswith("{"):
        return value
    payload = json.loads(compact)
    if not isinstance(payload, dict) or payload.get("kty") != "RSA":
        raise ValueError("TOCHKA_PUBLIC_KEY must contain an RSA JWK or PEM key")
    return jwt.PyJWK.from_dict(payload).key


def _decode_unverified_jwt(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) < 2:
        raise ValueError("Invalid JWT")
    decoded = base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4))
    return _decode_json_object(decoded, context="JWT payload")


def _decode_json_object(value: str | bytes, *, context: str) -> dict[str, Any]:
    try:
        payload = json.loads(value)
    except RecursionError as error:
        raise ValueError(f"{context} is too deeply nested") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{context} must be an object")
    return payload


def _provider_response_object(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except (ValueError, UnicodeDecodeError, RecursionError) as error:
        raise TochkaError("Tochka Bank returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise TochkaError("Tochka Bank returned an invalid response")
    return payload


def _event_data(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("payload", "Data"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return payload


def _find_first(payload: dict[str, Any], keys: tuple[str, ...]) -> object | None:
    pending: list[tuple[dict[str, Any], int]] = [(payload, 0)]
    visited = 0
    while pending:
        current, depth = pending.pop()
        visited += 1
        if visited > _MAX_PROVIDER_RESPONSE_NODES or depth > _MAX_PROVIDER_RESPONSE_DEPTH:
            raise ValueError("Provider payload is too deeply nested or complex")
        for key in keys:
            if current.get(key) not in (None, ""):
                return cast(object, current[key])
        for value in reversed(tuple(current.values())):
            if isinstance(value, dict):
                pending.append((value, depth + 1))
            elif isinstance(value, list):
                pending.extend(
                    (item, depth + 1) for item in reversed(value) if isinstance(item, dict)
                )
    return None


def _add_query_params(url: str, **params: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(params)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _string_or_none(value: object) -> str | None:
    return str(value) if value is not None else None


def _validate_provider_identifier(
    value: str,
    *,
    name: str,
    max_length: int = _MAX_PROVIDER_IDENTIFIER_LENGTH,
) -> str:
    if not 1 <= len(value) <= max_length or _PROVIDER_IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise ValueError(f"Invalid Tochka {name}")
    return value


def _optional_provider_identifier(
    value: object | None,
    *,
    name: str,
    max_length: int = _MAX_PROVIDER_IDENTIFIER_LENGTH,
) -> str | None:
    if value is None:
        return None
    return _validate_provider_identifier(str(value), name=name, max_length=max_length)


def _normalize_provider_status(value: object) -> str:
    normalized = str(value).strip().upper()
    if (
        not normalized
        or len(normalized) > 64
        or _PROVIDER_STATUS_PATTERN.fullmatch(normalized) is None
    ):
        raise ValueError("Invalid Tochka payment status")
    return normalized


def _optional_amount_kopecks(value: object | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("Invalid Tochka payment amount")
    try:
        amount = Decimal(str(value))
    except (ArithmeticError, ValueError) as error:
        raise ValueError("Invalid Tochka payment amount") from error
    if not amount.is_finite() or amount <= 0:
        raise ValueError("Invalid Tochka payment amount")
    kopecks = amount * 100
    if kopecks != kopecks.to_integral_value() or kopecks > _MAX_PAYMENT_AMOUNT_KOPECKS:
        raise ValueError("Invalid Tochka payment amount")
    return int(kopecks)


def _validate_payment_url(value: str) -> str:
    if len(value) > _MAX_PAYMENT_URL_LENGTH or any(
        ord(character) < 32 or ord(character) == 127 for character in value
    ):
        raise TochkaError("Tochka Bank returned an invalid payment URL")
    try:
        parts = urlsplit(value)
        _ = parts.port
    except ValueError as error:
        raise TochkaError("Tochka Bank returned an invalid payment URL") from error
    if (
        parts.scheme.lower() != "https"
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
    ):
        raise TochkaError("Tochka Bank returned an invalid payment URL")
    return value
