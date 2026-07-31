from httpx import AsyncClient
from pydantic import SecretStr
from pytest import MonkeyPatch
from sqlalchemy import func, select

from app.auth import dependencies as auth_dependencies
from app.integrations import dependencies as integration_dependencies
from app.roadmaps.models import RoadmapEnrollment
from app.tracks.models import LearningTrackEnrollment
from app.users.models import User
from tests.conftest import SeededData, TestSession
from tests.test_auth_and_health import BOT_TOKEN, telegram_auth

INTEGRATION_TOKEN = "integration-test-token-with-enough-entropy"


def integration_auth(token: str = INTEGRATION_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def student_payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "telegram_id": 987654321,
        "first_name": "Оплаченный",
        "last_name": "Ученик",
        "email": "paid@example.com",
        "track_slug": "python",
    }
    payload.update(changes)
    return payload


async def test_bot_integration_requires_configured_valid_token(
    client: AsyncClient, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(integration_dependencies.settings, "bot_integration_token", None)
    unavailable = await client.post(
        "/api/v1/integrations/telegram/students", json=student_payload()
    )

    monkeypatch.setattr(
        integration_dependencies.settings,
        "bot_integration_token",
        SecretStr(INTEGRATION_TOKEN),
    )
    invalid = await client.post(
        "/api/v1/integrations/telegram/students",
        headers=integration_auth("wrong-token"),
        json=student_payload(),
    )

    assert unavailable.status_code == 503
    assert unavailable.json()["detail"]["code"] == "bot_integration_unavailable"
    assert invalid.status_code == 401


async def test_bot_provisions_paid_student_and_grants_selected_track(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        integration_dependencies.settings,
        "bot_integration_token",
        SecretStr(INTEGRATION_TOKEN),
    )
    monkeypatch.setattr(auth_dependencies.settings, "telegram_bot_token", SecretStr(BOT_TOKEN))

    provisioned = await client.post(
        "/api/v1/integrations/telegram/students",
        headers=integration_auth(),
        json=student_payload(),
    )
    me = await client.get("/api/v1/me", headers=telegram_auth())
    roadmaps = await client.get("/api/v1/roadmaps", headers=telegram_auth())

    assert provisioned.status_code == 200
    assert provisioned.json()["created"] is True
    assert provisioned.json()["access_created"] is True
    assert provisioned.json()["track"]["id"] == str(seeded.python_track_id)
    assert provisioned.json()["roadmaps"][0]["id"] == str(seeded.roadmap_id)
    assert me.status_code == 200
    assert me.json()["telegram_id"] == 987654321
    assert me.json()["onboarding_completed_at"] is not None
    assert [item["slug"] for item in roadmaps.json()] == ["python-backend"]


async def test_bot_provisioning_is_idempotent_and_updates_student_data(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        integration_dependencies.settings,
        "bot_integration_token",
        SecretStr(INTEGRATION_TOKEN),
    )
    first = await client.post(
        "/api/v1/integrations/telegram/students",
        headers=integration_auth(),
        json=student_payload(),
    )
    second = await client.post(
        "/api/v1/integrations/telegram/students",
        headers=integration_auth(),
        json=student_payload(first_name="Новое имя"),
    )

    async with TestSession() as session:
        user_count = await session.scalar(
            select(func.count(User.id)).where(User.telegram_id == 987654321)
        )
        enrollment_count = await session.scalar(
            select(func.count(RoadmapEnrollment.user_id)).where(
                RoadmapEnrollment.user_id == first.json()["user"]["id"]
            )
        )
        access_count = await session.scalar(
            select(func.count(LearningTrackEnrollment.user_id)).where(
                LearningTrackEnrollment.user_id == first.json()["user"]["id"]
            )
        )

    assert first.status_code == second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["access_created"] is False
    assert second.json()["user"]["id"] == first.json()["user"]["id"]
    assert second.json()["user"]["first_name"] == "Новое имя"
    assert user_count == enrollment_count == access_count == 1


async def test_bot_rejects_unknown_direction_without_creating_student(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        integration_dependencies.settings,
        "bot_integration_token",
        SecretStr(INTEGRATION_TOKEN),
    )
    response = await client.post(
        "/api/v1/integrations/telegram/students",
        headers=integration_auth(),
        json=student_payload(track_slug="unknown-direction"),
    )

    async with TestSession() as session:
        user = await session.scalar(select(User).where(User.telegram_id == 987654321))

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "track_not_found"
    assert user is None
