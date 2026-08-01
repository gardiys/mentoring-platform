from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import AsyncClient
from pydantic import SecretStr
from pytest import MonkeyPatch, raises

from app.auth import dependencies as auth_dependencies
from app.auth import telegram_oidc, web_router
from app.auth.telegram_oidc import TelegramIdentity
from app.users.models import User
from tests.conftest import SeededData, TestSession

SESSION_SECRET = "test-web-session-secret-at-least-32-characters"
TELEGRAM_ID = 987654321


def configure_web_auth(monkeypatch: MonkeyPatch) -> None:
    for settings in (web_router.settings, auth_dependencies.settings):
        monkeypatch.setattr(settings, "app_env", "development")
        monkeypatch.setattr(settings, "telegram_web_client_id", "123456789")
        monkeypatch.setattr(settings, "telegram_web_client_secret", SecretStr("client-secret"))
        monkeypatch.setattr(
            settings,
            "telegram_web_redirect_uri",
            "http://test/api/v1/auth/web/telegram/callback",
        )
        monkeypatch.setattr(settings, "web_frontend_url", "http://frontend.test")
        monkeypatch.setattr(settings, "web_session_secret", SecretStr(SESSION_SECRET))


async def grant_telegram_id(seeded: SeededData) -> None:
    async with TestSession() as session:
        user = await session.get(User, seeded.student_id)
        assert user is not None
        user.telegram_id = TELEGRAM_ID
        await session.commit()


async def begin_login(client: AsyncClient, next_path: str = "/roadmaps") -> str:
    response = await client.get(
        "/api/v1/auth/web/telegram/start",
        params={"next": next_path},
    )
    assert response.status_code == 302
    location = response.headers["location"]
    query = parse_qs(urlparse(location).query)
    assert urlparse(location)._replace(query="").geturl() == "https://oauth.telegram.org/auth"
    assert query["client_id"] == ["123456789"]
    assert query["scope"] == ["openid profile"]
    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    assert "mentoring_oauth_state" in client.cookies
    return query["state"][0]


async def test_web_login_creates_cookie_session_and_logout_clears_it(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: MonkeyPatch,
) -> None:
    configure_web_auth(monkeypatch)
    await grant_telegram_id(seeded)
    state = await begin_login(client, "/knowledge?section=python")

    async def exchange(**_: str) -> TelegramIdentity:
        return TelegramIdentity(
            telegram_id=TELEGRAM_ID,
            first_name="Новое имя",
            last_name="Из Telegram",
        )

    monkeypatch.setattr(web_router.telegram_oidc, "exchange_code_for_identity", exchange)
    callback = await client.get(
        "/api/v1/auth/web/telegram/callback",
        params={"code": "authorization-code", "state": state},
    )

    assert callback.status_code == 302
    assert callback.headers["location"] == "http://frontend.test/knowledge?section=python"
    assert "mentoring_session" in client.cookies
    assert "mentoring_oauth_state" not in client.cookies

    monkeypatch.setattr(auth_dependencies.settings, "app_env", "production")
    me = await client.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["id"] == str(seeded.student_id)
    assert me.json()["first_name"] == "Новое имя"

    logout = await client.post("/api/v1/auth/web/logout")
    assert logout.status_code == 204
    assert "mentoring_session" not in client.cookies
    assert (await client.get("/api/v1/me")).status_code == 401


async def test_web_login_rejects_unknown_user_and_open_redirect(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    configure_web_auth(monkeypatch)
    state = await begin_login(client, "//evil.example/steal")

    async def exchange(**_: str) -> TelegramIdentity:
        return TelegramIdentity(
            telegram_id=TELEGRAM_ID,
            first_name="Нет доступа",
            last_name=None,
        )

    monkeypatch.setattr(web_router.telegram_oidc, "exchange_code_for_identity", exchange)
    response = await client.get(
        "/api/v1/auth/web/telegram/callback",
        params={"code": "authorization-code", "state": state},
    )

    assert response.status_code == 307
    assert response.headers["location"] == (
        "http://frontend.test/login?error=platform_access_not_granted"
    )
    assert "mentoring_session" not in client.cookies


async def test_web_login_rejects_mismatched_state_without_token_exchange(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    configure_web_auth(monkeypatch)
    await begin_login(client)

    async def exchange(**_: str) -> TelegramIdentity:
        raise AssertionError("Token exchange must not run for an invalid state")

    monkeypatch.setattr(web_router.telegram_oidc, "exchange_code_for_identity", exchange)
    response = await client.get(
        "/api/v1/auth/web/telegram/callback",
        params={"code": "authorization-code", "state": "tampered"},
    )

    assert response.status_code == 307
    assert response.headers["location"] == "http://frontend.test/login?error=invalid_login_state"


async def test_tampered_browser_session_is_rejected(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    configure_web_auth(monkeypatch)
    monkeypatch.setattr(auth_dependencies.settings, "app_env", "production")
    client.cookies.set("mentoring_session", "payload.invalid-signature")

    response = await client.get("/api/v1/me")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "unauthorized"


def test_telegram_id_token_signature_and_claims_are_verified() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    public_jwk.update({"kid": "telegram-test-key", "alg": "RS256", "use": "sig"})
    now = datetime.now(UTC)
    claims = {
        "iss": telegram_oidc.ISSUER,
        "aud": "123456789",
        "sub": "telegram-subject",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "id": TELEGRAM_ID,
        "given_name": "Иван",
        "family_name": "Иванов",
    }
    id_token = jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": "telegram-test-key"},
    )

    decoded = telegram_oidc._decode_id_token(
        id_token,
        {"keys": [public_jwk]},
        "123456789",
    )
    identity = telegram_oidc._identity_from_claims(decoded)

    assert identity.telegram_id == TELEGRAM_ID
    assert identity.first_name == "Иван"
    assert identity.last_name == "Иванов"
    with raises(telegram_oidc.TelegramOidcError):
        telegram_oidc._decode_id_token(
            id_token,
            {"keys": [public_jwk]},
            "wrong-client-id",
        )
