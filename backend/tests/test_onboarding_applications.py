import json

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.onboarding_applications.client import OnboardingBotClient

APPLICATION = {
    "applicant_id": "app_123",
    "status": "QUALIFICATION_REVIEW_REQUIRED",
    "name": "Иван",
    "telegram_user_id": 123456,
    "telegram_username": "student",
    "email": None,
    "direction": "Python",
    "city": "Москва",
    "admin_comment": None,
    "booking_start_time": None,
    "payment_status": None,
    "created_at": "2026-08-18T10:00:00Z",
    "updated_at": "2026-08-18T11:00:00Z",
    "available_actions": ["approve_qualification", "reject_qualification"],
}


def settings() -> Settings:
    return Settings(
        onboarding_bot_api_base_url="https://onboarding.example",
        onboarding_bot_integration_token=SecretStr("shared-secret-with-at-least-32-chars"),
    )


@pytest.mark.asyncio
async def test_lists_applications_with_shared_token_and_filters() -> None:
    captured: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured
        captured = request
        return httpx.Response(
            200,
            json={
                "items": [APPLICATION],
                "total": 1,
                "limit": 50,
                "offset": 0,
                "status_counts": {"QUALIFICATION_REVIEW_REQUIRED": 1},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        result = await OnboardingBotClient(settings(), http_client).applications(
            statuses=["QUALIFICATION_REVIEW_REQUIRED"],
            search="Иван",
            limit=50,
            offset=0,
        )

    assert captured is not None
    assert captured.headers["Authorization"] == "Bearer shared-secret-with-at-least-32-chars"
    assert captured.url.params.get_list("statuses") == ["QUALIFICATION_REVIEW_REQUIRED"]
    assert captured.url.params["search"] == "Иван"
    assert result.items[0].applicant_id == "app_123"


@pytest.mark.asyncio
async def test_action_forwards_admin_identity() -> None:
    captured_payload: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured_payload.update(json.loads(request.content))
        detail = {
            **APPLICATION,
            "status": "REJECTED_BEFORE_CALL",
            "available_actions": [],
            "age": "25",
            "initial_knowledge": None,
            "life_difficulties": None,
            "study_time_per_day": None,
            "military_document_status": None,
            "referral_source": None,
            "form_answers": {},
            "bookings": [],
            "payments": [],
            "events": [],
        }
        return httpx.Response(
            200,
            json={"message": "Кандидату отказано", "delivered": True, "application": detail},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        result = await OnboardingBotClient(settings(), http_client).execute_action(
            "app_123",
            "reject_qualification",
            comment=None,
            actor_id="admin-uuid",
            actor_telegram_id=777,
        )

    assert captured_payload == {
        "action": "reject_qualification",
        "comment": None,
        "actor_id": "admin-uuid",
        "actor_telegram_id": 777,
    }
    assert result.application.status == "REJECTED_BEFORE_CALL"
