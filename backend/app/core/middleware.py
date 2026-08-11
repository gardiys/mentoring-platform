import logging
import re
from collections.abc import Iterable
from time import perf_counter
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import Request, Response
from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.auth.web_session import BROWSER_SESSION_COOKIE
from app.core.errors import api_error

logger = logging.getLogger("app.http")

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


def normalize_request_id(value: str | None) -> str:
    if value is not None and REQUEST_ID_PATTERN.fullmatch(value):
        return value
    return str(uuid4())


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": {"code": code, "message": message}},
    )


def _content_length(headers: Headers) -> int | None:
    values = headers.getlist("content-length")
    if not values:
        return None
    if len(values) != 1 or "," in values[0]:
        raise ValueError("Ambiguous Content-Length header")
    try:
        value = int(values[0], 10)
    except ValueError as error:
        raise ValueError("Invalid Content-Length header") from error
    if value < 0:
        raise ValueError("Invalid Content-Length header")
    return value


class RequestBodyLimitMiddleware:
    """Bound HTTP request bodies, including requests without Content-Length."""

    def __init__(self, app: ASGIApp, *, max_body_size: int) -> None:
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        try:
            declared_size = _content_length(Headers(scope=scope))
        except ValueError:
            await _error_response(
                400,
                "invalid_content_length",
                "Content-Length header is invalid",
            )(scope, receive, send)
            return
        if declared_size is not None and declared_size > self.max_body_size:
            await _error_response(
                413,
                "request_too_large",
                "Request body is too large",
            )(scope, receive, send)
            return

        messages: list[Message] = []
        received_size = 0
        more_body = True
        while more_body:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.disconnect":
                break
            if message["type"] != "http.request":
                continue
            received_size += len(message.get("body", b""))
            if received_size > self.max_body_size:
                await _error_response(
                    413,
                    "request_too_large",
                    "Request body is too large",
                )(scope, receive, send)
                return
            more_body = bool(message.get("more_body", False))

        message_index = 0

        async def replay_receive() -> Message:
            nonlocal message_index
            if message_index < len(messages):
                message = messages[message_index]
                message_index += 1
                return message
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay_receive, send)


class CookieCSRFMiddleware:
    """Reject cross-site mutations authenticated by the browser session cookie.

    Requests authenticated with Telegram init data and clients without browser
    Origin/Sec-Fetch headers remain unaffected.
    """

    def __init__(self, app: ASGIApp, *, trusted_origins: Iterable[str]) -> None:
        self.app = app
        self.trusted_origins = frozenset(
            origin
            for value in trusted_origins
            if (origin := self._normalize_origin(value)) is not None
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"].upper() in SAFE_METHODS:
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        if BROWSER_SESSION_COOKIE not in request.cookies:
            await self.app(scope, receive, send)
            return
        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("tma "):
            await self.app(scope, receive, send)
            return

        origin_header = request.headers.get("origin")
        fetch_site = request.headers.get("sec-fetch-site")
        normalized_fetch_site = fetch_site.lower() if fetch_site is not None else None
        if normalized_fetch_site == "cross-site":
            await self._reject(scope, receive, send)
            return

        # Browser sessions are cookie-authenticated, so mutations fail closed
        # when their exact origin cannot be established. Integrations and Mini
        # Apps authenticate independently and never need this compatibility
        # exception.
        if origin_header is None:
            await self._reject(scope, receive, send)
            return

        origin = self._normalize_origin(origin_header)
        if origin not in self.trusted_origins or normalized_fetch_site not in {
            None,
            "same-origin",
            "same-site",
            "none",
        }:
            await self._reject(scope, receive, send)
            return
        await self.app(scope, receive, send)

    @staticmethod
    def _normalize_origin(value: str) -> str | None:
        try:
            parsed = urlsplit(value)
            _ = parsed.port
        except ValueError:
            return None
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            return None
        return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
        await _error_response(
            403,
            "csrf_validation_failed",
            "Cross-site browser request is not allowed",
        )(scope, receive, send)


async def read_limited_request_body(request: Request, *, max_bytes: int) -> bytes:
    """Read one endpoint body without ever buffering more than its own limit."""

    try:
        declared_size = _content_length(request.headers)
    except ValueError:
        api_error(400, "invalid_content_length", "Content-Length header is invalid")
    if declared_size is not None and declared_size > max_bytes:
        api_error(413, "request_too_large", "Request body is too large")

    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > max_bytes:
            api_error(413, "request_too_large", "Request body is too large")
        chunks.append(chunk)
    return b"".join(chunks)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = normalize_request_id(request.headers.get("X-Request-Id"))
        request.state.request_id = request_id
        started = perf_counter()
        response = await call_next(request)
        duration_ms = (perf_counter() - started) * 1000
        response.headers["X-Request-Id"] = request_id
        logger.info(
            "%s %s status=%s duration_ms=%.2f request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id,
        )
        return response
