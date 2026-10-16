from __future__ import annotations

import base64
from html import escape
from typing import Any

import httpx

from app.core.config import Settings


class CareerPackageEmailError(RuntimeError):
    pass


class CareerPackageEmailService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.settings = settings
        self.client = client

    async def send_package(
        self,
        *,
        recipient_email: str,
        recipient_name: str,
        package_number: str,
        version_number: int,
        body: str,
        action_url: str,
        pdf: bytes | None,
        subject: str | None = None,
        attachment_name: str | None = None,
        tags: list[str] | None = None,
        idempotency_key: str | None = None,
        sender_email: str | None = None,
        reply_to_email: str | None = None,
        action_label: str = "Открыть Карьерный пакет на платформе",
    ) -> str | None:
        api_key = (
            self.settings.brevo_api_key.get_secret_value()
            if self.settings.brevo_api_key is not None
            else ""
        )
        if not api_key or not (sender_email or self.settings.brevo_from_email):
            raise CareerPackageEmailError("Email delivery is not configured")
        recipient = {"email": recipient_email}
        if recipient_name.strip():
            recipient["name"] = recipient_name.strip()
        safe_body = "<br>".join(escape(body).splitlines())
        safe_url = escape(action_url, quote=True)
        payload: dict[str, Any] = {
            "sender": {
                "email": sender_email or self.settings.brevo_from_email,
                "name": self.settings.brevo_from_name,
            },
            "to": [recipient],
            "subject": subject or f"Карьерный пакет № {package_number}, версия {version_number}",
            "textContent": f"{body}\n\nОткрыть на платформе: {action_url}",
            "htmlContent": (
                f'<p>{safe_body}</p><p><a href="{safe_url}">{escape(action_label)}</a></p>'
            ),
            "tags": tags or ["career-package"],
            "attachment": [
                {
                    "name": attachment_name or f"career-package-v{version_number}.pdf",
                    "content": base64.b64encode(pdf or b"").decode("ascii"),
                }
            ],
        }
        if pdf is None:
            payload.pop("attachment")
        if idempotency_key:
            payload["headers"] = {"idempotencyKey": idempotency_key}
        if reply_to_email or self.settings.brevo_reply_to_email:
            payload["replyTo"] = {
                "email": reply_to_email or self.settings.brevo_reply_to_email,
                "name": self.settings.brevo_reply_to_name,
            }
        try:
            response = await self.client.post(
                "/smtp/email",
                headers={
                    "accept": "application/json",
                    "api-key": api_key,
                    "content-type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            provider_code: str | None = None
            try:
                payload = error.response.json()
                if isinstance(payload, dict) and payload.get("code") is not None:
                    provider_code = str(payload["code"])
                    if (
                        idempotency_key
                        and provider_code == "duplicate_parameter"
                        and "idempotency" in str(payload.get("message", "")).lower()
                    ):
                        # Provider confirms the prior request was processed. Its Message-ID
                        # was lost with the response, so delivery remains unknown.
                        return None
            except ValueError:
                pass
            suffix = f" ({provider_code})" if provider_code else ""
            raise CareerPackageEmailError(
                f"Brevo rejected email: HTTP {error.response.status_code}{suffix}"
            ) from error
        except httpx.HTTPError as error:
            raise CareerPackageEmailError("Could not connect to Brevo") from error
        try:
            message_id = response.json().get("messageId")
        except (ValueError, AttributeError):
            return None
        return str(message_id) if message_id else None
