import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from uuid import uuid4

from httpx import AsyncClient
from pydantic import SecretStr
from pytest import MonkeyPatch

from app.auth import dependencies as auth_dependencies
from app.users.models import User
from tests.conftest import SeededData, TestSession, auth

BOT_TOKEN = "123456:test-token"


def telegram_auth(
    telegram_id: int = 987654321,
    *,
    first_name: str = "Телеграм",
    last_name: str | None = None,
    username: str | None = None,
    auth_date: datetime | None = None,
) -> dict[str, str]:
    telegram_user: dict[str, int | str] = {
        "id": telegram_id,
        "first_name": first_name,
        "language_code": "ru",
    }
    if last_name is not None:
        telegram_user["last_name"] = last_name
    if username is not None:
        telegram_user["username"] = username
    values = {
        "auth_date": str(int((auth_date or datetime.now(UTC)).timestamp())),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(
            telegram_user,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(values.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return {"Authorization": f"tma {urlencode(values)}"}


async def test_authentication_errors(client: AsyncClient, seeded: SeededData) -> None:
    missing = await client.get("/api/v1/me")
    unknown = await client.get("/api/v1/me", headers=auth(uuid4()))

    assert missing.status_code == 401
    assert missing.json()["detail"]["code"] == "unauthorized"
    assert unknown.status_code == 401
    assert unknown.json()["detail"]["code"] == "user_not_found"


async def test_health_and_ready(client: AsyncClient) -> None:
    health = await client.get("/health")
    ready = await client.get("/ready")

    assert health.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}


async def test_telegram_auth_rejects_user_without_granted_access(
    client: AsyncClient, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(auth_dependencies.settings, "telegram_bot_token", SecretStr(BOT_TOKEN))
    response = await client.get("/api/v1/me", headers=telegram_auth())

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "platform_access_not_granted"


async def test_telegram_auth_rejects_tampered_and_expired_data(
    client: AsyncClient, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(auth_dependencies.settings, "telegram_bot_token", SecretStr(BOT_TOKEN))
    valid_header = telegram_auth()
    tampered_header = {
        "Authorization": valid_header["Authorization"][:-1]
        + ("0" if valid_header["Authorization"][-1] != "0" else "1")
    }
    expired_header = telegram_auth(auth_date=datetime.now(UTC) - timedelta(days=2))

    tampered = await client.get("/api/v1/me", headers=tampered_header)
    expired = await client.get("/api/v1/me", headers=expired_header)

    assert tampered.status_code == 401
    assert expired.status_code == 401


async def test_telegram_auth_preserves_platform_names_and_syncs_username(
    client: AsyncClient, seeded: SeededData, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(auth_dependencies.settings, "telegram_bot_token", SecretStr(BOT_TOKEN))
    async with TestSession() as session:
        user = await session.get(User, seeded.student_id)
        assert user is not None
        user.telegram_id = 987654321
        user.first_name = "Иван"
        user.last_name = "Правильная фамилия"
        user.telegram_username = "old_username"
        await session.commit()

    response = await client.get(
        "/api/v1/me",
        headers=telegram_auth(
            first_name="Имя из Telegram",
            last_name="Фамилия из Telegram",
            username="fresh_username",
        ),
    )

    assert response.status_code == 200
    assert response.json()["first_name"] == "Иван"
    assert response.json()["last_name"] == "Правильная фамилия"
    async with TestSession() as session:
        user = await session.get(User, seeded.student_id)
        assert user is not None
        assert user.first_name == "Иван"
        assert user.last_name == "Правильная фамилия"
        assert user.telegram_username == "fresh_username"


async def test_dev_auth_is_disabled_outside_development(
    client: AsyncClient, seeded: SeededData, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(auth_dependencies.settings, "app_env", "production")

    response = await client.get("/api/v1/me", headers=auth(seeded.student_id))

    assert response.status_code == 401


async def test_dev_auth_requires_explicit_opt_in(
    client: AsyncClient, seeded: SeededData, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(auth_dependencies.settings, "app_env", "development")
    monkeypatch.setattr(auth_dependencies.settings, "dev_auth_enabled", False)

    disabled = await client.get("/api/v1/me", headers=auth(seeded.student_id))
    monkeypatch.setattr(auth_dependencies.settings, "dev_auth_enabled", True)
    enabled = await client.get("/api/v1/me", headers=auth(seeded.student_id))

    assert disabled.status_code == 401
    assert enabled.status_code == 200
