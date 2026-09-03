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
        pdf: bytes,
        subject: str | None = None,
        action_label: str = "Открыть Карьерный пакет на платформе",
    ) -> str | None:
        api_key = (
            self.settings.brevo_api_key.get_secret_value()
            if self.settings.brevo_api_key is not None
            else ""
        )
        if not api_key or not self.settings.brevo_from_email:
            raise CareerPackageEmailError("Email delivery is not configured")
        safe_body = "<br>".join(escape(body).splitlines())
        safe_url = escape(action_url, quote=True)
        payload: dict[str, Any] = {
            "sender": {
                "email": self.settings.brevo_from_email,
                "name": self.settings.brevo_from_name,
            },
            "to": [{"email": recipient_email, "name": recipient_name}],
            "subject": subject
            or f"Карьерный пакет № {package_number}, версия {version_number}",
            "textContent": f"{body}\n\nОткрыть на платформе: {action_url}",
            "htmlContent": (
                f"<p>{safe_body}</p><p><a href=\"{safe_url}\">"
                f"{escape(action_label)}</a></p>"
            ),
            "tags": ["career-package"],
            "attachment": [
                {
                    "name": f"career-package-v{version_number}.pdf",
                    "content": base64.b64encode(pdf).decode("ascii"),
                }
            ],
        }
        if self.settings.brevo_reply_to_email:
            payload["replyTo"] = {
                "email": self.settings.brevo_reply_to_email,
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
