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
from tests.conftest import SeededData, auth

BOT_TOKEN = "123456:test-token"


def telegram_auth(
    telegram_id: int = 987654321,
    *,
    first_name: str = "Телеграм",
    auth_date: datetime | None = None,
) -> dict[str, str]:
    values = {
        "auth_date": str(int((auth_date or datetime.now(UTC)).timestamp())),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(
            {"id": telegram_id, "first_name": first_name, "language_code": "ru"},
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


async def test_dev_auth_is_disabled_outside_development(
    client: AsyncClient, seeded: SeededData, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(auth_dependencies.settings, "app_env", "production")

    response = await client.get("/api/v1/me", headers=auth(seeded.student_id))

    assert response.status_code == 401
