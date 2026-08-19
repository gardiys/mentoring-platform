from typing import Any

import httpx

from app.core.config import Settings
from app.core.errors import api_error
from app.onboarding_applications.schemas import (
    ApplicationAction,
    OnboardingApplicationActionResponse,
    OnboardingApplicationDetail,
    OnboardingApplicationPage,
)


class OnboardingBotClient:
    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self.client = client

    async def applications(
        self,
        *,
        statuses: list[str] | None,
        search: str | None,
        limit: int,
        offset: int,
    ) -> OnboardingApplicationPage:
        params: list[tuple[str, str | int]] = [
            ("limit", limit),
            ("offset", offset),
        ]
        params.extend(("statuses", status) for status in statuses or [])
        if search:
            params.append(("search", search))
        payload = await self._request("GET", "/applications", params=params)
        return OnboardingApplicationPage.model_validate(payload)

    async def application(self, applicant_id: str) -> OnboardingApplicationDetail:
        payload = await self._request("GET", f"/applications/{applicant_id}")
        return OnboardingApplicationDetail.model_validate(payload)

    async def execute_action(
        self,
        applicant_id: str,
        action: ApplicationAction,
        *,
        comment: str | None,
        actor_id: str,
        actor_telegram_id: int | None,
    ) -> OnboardingApplicationActionResponse:
        payload = await self._request(
            "POST",
            f"/applications/{applicant_id}/actions",
            json={
                "action": action,
                "comment": comment,
                "actor_id": actor_id,
                "actor_telegram_id": actor_telegram_id,
            },
        )
        return OnboardingApplicationActionResponse.model_validate(payload)

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        base_url = (self.settings.onboarding_bot_api_base_url or "").rstrip("/")
        configured_token = self.settings.onboarding_bot_integration_token
        if not base_url or configured_token is None:
            api_error(
                503,
                "onboarding_integration_unavailable",
                "Интеграция с ботом заявок не настроена",
            )
        token = configured_token.get_secret_value()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        try:
            if self.client is not None:
                response = await self.client.request(
                    method,
                    f"{base_url}/integrations/mentoring-platform{path}",
                    headers=headers,
                    **kwargs,
                )
            else:
                async with httpx.AsyncClient(
                    timeout=self.settings.onboarding_bot_timeout_seconds
                ) as client:
                    response = await client.request(
                        method,
                        f"{base_url}/integrations/mentoring-platform{path}",
                        headers=headers,
                        **kwargs,
                    )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            upstream_status = exc.response.status_code
            status_code = upstream_status if upstream_status in {404, 409, 422} else 502
            api_error(
                status_code,
                "onboarding_integration_rejected",
                _upstream_message(exc.response),
            )
        except (httpx.HTTPError, ValueError):
            api_error(
                502,
                "onboarding_integration_unavailable",
                "Не удалось связаться с ботом заявок",
            )


def _upstream_message(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        return "Бот заявок отклонил операцию"
    if isinstance(detail, str) and detail:
        return detail
    return "Бот заявок отклонил операцию"
