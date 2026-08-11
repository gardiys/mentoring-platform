from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from fastapi import FastAPI, Request
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from starlette.types import Message, Receive, Scope, Send

from app.auth.dependencies import get_current_user
from app.auth.web_session import BROWSER_SESSION_COOKIE
from app.core.config import Settings
from app.core.middleware import (
    CookieCSRFMiddleware,
    RequestBodyLimitMiddleware,
    RequestContextMiddleware,
)
from app.integrations.dependencies import require_bot_integration_token
from app.main import create_app


def _client(application: FastAPI, base_url: str = "http://test") -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=application), base_url=base_url)


def _body_limit_app(limit: int) -> tuple[FastAPI, list[bytes]]:
    received: list[bytes] = []
    application = FastAPI()
    application.add_middleware(RequestBodyLimitMiddleware, max_body_size=limit)

    @application.post("/echo")
    async def echo(request: Request) -> dict[str, int]:
        body = await request.body()
        received.append(body)
        return {"size": len(body)}

    return application, received


async def test_body_limit_rejects_declared_oversized_request_before_endpoint() -> None:
    application, received = _body_limit_app(1_024)
    async with _client(application) as client:
        response = await client.post("/echo", content=b"x" * 1_025)

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "request_too_large"
    assert received == []


async def test_body_limit_rejects_chunked_request_without_content_length() -> None:
    application, received = _body_limit_app(1_024)

    async def chunks() -> AsyncIterator[bytes]:
        yield b"x" * 700
        yield b"y" * 700

    async with _client(application) as client:
        response = await client.post("/echo", content=chunks())

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "request_too_large"
    assert received == []


async def test_body_limit_replays_an_allowed_chunked_request() -> None:
    application, received = _body_limit_app(1_024)

    async def chunks() -> AsyncIterator[bytes]:
        yield b"hello"
        yield b" world"

    async with _client(application) as client:
        response = await client.post("/echo", content=chunks())

    assert response.status_code == 200
    assert response.json() == {"size": 11}
    assert received == [b"hello world"]


async def test_body_limit_rejects_ambiguous_content_length() -> None:
    downstream_called = False

    async def downstream(scope: Scope, receive: Receive, send: Send) -> None:
        nonlocal downstream_called
        downstream_called = True

    application = RequestBodyLimitMiddleware(downstream, max_body_size=1_024)
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-length", b"4"), (b"content-length", b"5")],
        "client": ("127.0.0.1", 1234),
        "server": ("test", 80),
    }
    request_messages: list[Message] = [
        {"type": "http.request", "body": b"test", "more_body": False}
    ]
    response_messages: list[Message] = []

    async def receive() -> Message:
        return request_messages.pop(0)

    async def send(message: Message) -> None:
        response_messages.append(message)

    await application(scope, receive, send)

    assert downstream_called is False
    assert response_messages[0]["type"] == "http.response.start"
    assert response_messages[0]["status"] == 400


def _csrf_app() -> FastAPI:
    application = FastAPI()
    application.add_middleware(
        CookieCSRFMiddleware,
        trusted_origins={"https://platform.example.com"},
    )

    @application.post("/mutation")
    async def mutation() -> dict[str, bool]:
        return {"updated": True}

    return application


@pytest.mark.parametrize(
    ("headers", "expected_status"),
    [
        (
            {"Origin": "https://platform.example.com", "Sec-Fetch-Site": "same-origin"},
            200,
        ),
        (
            {"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"},
            403,
        ),
        ({"Origin": "null", "Sec-Fetch-Site": "same-site"}, 403),
        ({"Sec-Fetch-Site": "same-site"}, 403),
        ({"Sec-Fetch-Site": "same-origin"}, 403),
        ({}, 403),
    ],
)
async def test_cookie_csrf_validation(headers: dict[str, str], expected_status: int) -> None:
    async with _client(_csrf_app()) as client:
        client.cookies.set(BROWSER_SESSION_COOKIE, "signed-session")
        response = await client.post("/mutation", headers=headers)

    assert response.status_code == expected_status
    if expected_status == 403:
        assert response.json()["detail"]["code"] == "csrf_validation_failed"


async def test_csrf_does_not_reject_tma_or_cookie_free_clients() -> None:
    cross_site = {"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"}
    async with _client(_csrf_app()) as client:
        without_cookie = await client.post("/mutation", headers=cross_site)
        client.cookies.set(BROWSER_SESSION_COOKIE, "signed-session")
        with_tma = await client.post(
            "/mutation",
            headers={**cross_site, "Authorization": "tma signed-init-data"},
        )

    assert without_cookie.status_code == 200
    assert with_tma.status_code == 200


async def test_request_id_is_preserved_only_when_safe_and_bounded() -> None:
    application = FastAPI()
    application.add_middleware(RequestContextMiddleware)

    @application.get("/")
    async def index() -> dict[str, bool]:
        return {"ok": True}

    async with _client(application) as client:
        accepted = await client.get("/", headers={"X-Request-Id": "trace_01:span-02"})
        replaced = await client.get("/", headers={"X-Request-Id": "bad id/with delimiters"})
        too_long = await client.get("/", headers={"X-Request-Id": "a" * 129})

    assert accepted.headers["X-Request-Id"] == "trace_01:span-02"
    for response in (replaced, too_long):
        generated = response.headers["X-Request-Id"]
        assert len(generated) == 36
        UUID(generated)


def test_settings_reject_unsafe_production_configuration() -> None:
    with pytest.raises(ValidationError, match="literal_error"):
        Settings(_env_file=None, app_env="prod")  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="APP_DEBUG must be false"):
        Settings(_env_file=None, app_env="production", app_debug=True)
    with pytest.raises(ValidationError, match="DEV_AUTH_ENABLED must be false"):
        Settings(
            _env_file=None,
            app_env="production",
            app_debug=False,
            dev_auth_enabled=True,
        )
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings(_env_file=None, app_env="production", app_debug=False)
    with pytest.raises(ValidationError, match="placeholder"):
        Settings(
            _env_file=None,
            app_env="production",
            app_debug=False,
            telegram_web_client_secret="REPLACE_WITH_A_RANDOM_SECRET",
            database_url="postgresql+asyncpg://app:password@postgres:5432/mentoring",
        )


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "https://user:password@platform.example.com",
        "https://platform.example.com/api",
        "https://platform.example.com\n",
        "https://platform.example.com\u0000.evil",
    ],
)
def test_settings_reject_non_exact_cors_origins(origin: str) -> None:
    with pytest.raises(ValidationError, match="exact http|whitespace"):
        Settings(_env_file=None, cors_origins=[origin])


@pytest.mark.parametrize(
    "host",
    ["foo*", "*example.com", "bad host", "bad_host", ".example.com", "example..com"],
)
def test_settings_reject_invalid_allowed_hosts(host: str) -> None:
    with pytest.raises(ValidationError, match="DNS host names"):
        Settings(_env_file=None, allowed_hosts=[host])


def test_settings_accepts_strict_subdomain_wildcard() -> None:
    settings = Settings(_env_file=None, allowed_hosts=["*.example.com"])

    assert settings.allowed_hosts == ["*.example.com"]


def test_settings_allows_any_host_only_outside_production() -> None:
    assert Settings(_env_file=None, allowed_hosts=["*"]).allowed_hosts == ["*"]
    with pytest.raises(ValidationError, match=r"must not contain '\*'"):
        Settings(
            _env_file=None,
            app_env="production",
            app_debug=False,
            database_url="postgresql+asyncpg://app:password@postgres:5432/mentoring",
            allowed_hosts=["*"],
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("web_frontend_url", "https://user:password@platform.example.com"),
        ("telegram_web_redirect_uri", "javascript:alert(1)"),
        ("s3_endpoint_url", "https://s3.example.com\n"),
        ("s3_public_endpoint_url", "https://s3.example.com:invalid"),
        ("nexara_base_url", "https://nexara.example.com/v1?token=secret"),
        ("tochka_api_base_url", "https://bank.example.com/uapi#fragment"),
    ],
)
def test_settings_reject_invalid_service_urls(field: str, value: str) -> None:
    with pytest.raises(ValidationError, match="URL|http|credentials|query|whitespace"):
        Settings(_env_file=None, **{field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("web_frontend_url", "http://platform.example.com"),
        (
            "telegram_web_redirect_uri",
            "http://platform.example.com/api/v1/auth/web/telegram/callback",
        ),
        ("nexara_base_url", "http://nexara.internal/v1"),
        ("tochka_api_base_url", "http://tochka.internal/uapi"),
        ("tochka_redirect_url", "http://platform.example.com/payments"),
        ("tochka_fail_redirect_url", "http://platform.example.com/payments"),
    ],
)
def test_production_requires_https_for_web_and_provider_urls(
    field: str,
    value: str,
) -> None:
    overrides = {field: value}
    if field == "telegram_web_redirect_uri":
        overrides.update(
            web_frontend_url="https://platform.example.com",
            cors_origins=["https://platform.example.com"],
        )
    with pytest.raises(ValidationError, match="HTTPS"):
        Settings(
            _env_file=None,
            app_env="production",
            app_debug=False,
            database_url="postgresql+asyncpg://app:password@postgres:5432/mentoring",
            **overrides,
        )


@pytest.mark.parametrize("field", ["s3_endpoint_url", "s3_public_endpoint_url"])
def test_production_requires_https_for_configured_s3_endpoints(field: str) -> None:
    endpoint_overrides = {
        "s3_endpoint_url": None,
        "s3_public_endpoint_url": None,
        field: "http://s3.internal:9000",
    }
    with pytest.raises(ValidationError, match="HTTPS"):
        Settings(
            _env_file=None,
            app_env="production",
            app_debug=False,
            database_url="postgresql+asyncpg://app:password@postgres:5432/mentoring",
            s3_bucket="production-bucket",
            s3_access_key_id="production-key",
            s3_secret_access_key="production-secret",
            **endpoint_overrides,
        )


def test_production_worker_can_load_common_settings_without_web_secrets() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        app_debug=False,
        database_url="postgresql+asyncpg://worker:password@postgres:5432/mentoring",
        redis_url="redis://redis:6379/0",
    )

    assert settings.web_session_secret is None
    assert settings.dev_auth_enabled is False


async def test_production_app_disables_schema_and_rejects_untrusted_host() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        app_debug=False,
        database_url="postgresql+asyncpg://app:password@postgres:5432/mentoring",
        web_frontend_url="https://platform.example.com",
        cors_origins=["https://platform.example.com"],
    )
    application = create_app(settings)

    async with _client(application, "https://platform.example.com") as client:
        assert (await client.get("/health")).status_code == 200
        assert (await client.get("/docs")).status_code == 404
        assert (await client.get("/openapi.json")).status_code == 404
        client.cookies.set(BROWSER_SESSION_COOKIE, "signed-session")
        cross_site = await client.post(
            "/api/v1/auth/web/logout",
            headers={
                "Origin": "https://evil.example",
                "Sec-Fetch-Site": "cross-site",
                "X-Request-Id": "csrf-order-check",
            },
        )
        assert cross_site.status_code == 403
        assert cross_site.headers["X-Request-Id"] == "csrf-order-check"
    async with _client(application, "https://evil.example") as client:
        rejected = await client.get("/health")

    assert rejected.status_code == 400


def test_every_api_route_has_authentication_or_an_explicit_public_contract() -> None:
    """Make accidentally public future endpoints fail the security test suite."""

    public_routes = {
        ("GET", "/health"),
        ("GET", "/ready"),
        ("GET", "/api/v1/auth/web/telegram/start"),
        ("GET", "/api/v1/auth/web/telegram/callback"),
        ("POST", "/api/v1/auth/web/logout"),
        ("POST", "/api/v1/payments/tochka/webhook"),
        ("GET", "/api/v1/interviews/catalog/stages/{stage_id}/media/stream"),
        ("GET", "/api/v1/knowledge/entries/{entry_slug}/media/{media_id}/stream"),
        ("GET", "/api/v1/topics/{topic_id}/media/{media_id}/stream"),
    }
    application = create_app(Settings(_env_file=None))
    observed_public: set[tuple[str, str]] = set()

    def walk(routes: list[object], prefix: str = "") -> None:
        for route in routes:
            if isinstance(route, APIRoute):
                dependency_calls: set[object] = set()
                dependencies = list(route.dependant.dependencies)
                while dependencies:
                    dependency = dependencies.pop()
                    dependency_calls.add(dependency.call)
                    dependencies.extend(dependency.dependencies)

                protected = bool(
                    {get_current_user, require_bot_integration_token} & dependency_calls
                )
                for method in route.methods:
                    contract = (method, f"{prefix}{route.path}")
                    if not protected:
                        observed_public.add(contract)
                continue

            # FastAPI 0.141 keeps included routers lazy. Traverse their public
            # router/context attributes so this guard covers every endpoint.
            original_router = getattr(route, "original_router", None)
            include_context = getattr(route, "include_context", None)
            if original_router is not None and include_context is not None:
                walk(original_router.routes, f"{prefix}{include_context.prefix}")

    walk(application.routes)

    assert observed_public == public_routes
