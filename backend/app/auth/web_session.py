from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

BROWSER_SESSION_COOKIE = "mentoring_session"
OAUTH_STATE_COOKIE = "mentoring_oauth_state"


class SignedPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class BrowserSession:
    user_id: UUID
    version: int


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _timestamp() -> int:
    return int(datetime.now(UTC).timestamp())


def sign_payload(payload: dict[str, Any], secret: str) -> str:
    encoded = _base64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signature = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256)
    return f"{encoded}.{_base64url_encode(signature.digest())}"


def verify_payload(token: str, secret: str, *, expected_kind: str) -> dict[str, Any]:
    try:
        encoded, signature = token.split(".", maxsplit=1)
        expected_signature = hmac.new(
            secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(_base64url_decode(signature), expected_signature):
            raise SignedPayloadError("Invalid signature")
        payload = json.loads(_base64url_decode(encoded))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SignedPayloadError("Invalid signed payload") from exc

    if not isinstance(payload, dict) or payload.get("kind") != expected_kind:
        raise SignedPayloadError("Invalid payload kind")
    expires_at = payload.get("exp")
    if not isinstance(expires_at, int) or expires_at < _timestamp():
        raise SignedPayloadError("Signed payload has expired")
    return payload


def create_browser_session(
    user_id: UUID,
    session_version: int,
    secret: str,
    ttl_seconds: int,
) -> str:
    if session_version < 1:
        raise ValueError("session_version must be positive")
    return sign_payload(
        {
            "kind": "browser_session",
            "user_id": str(user_id),
            "version": session_version,
            "exp": _timestamp() + ttl_seconds,
        },
        secret,
    )


def read_browser_session(token: str, secret: str) -> BrowserSession:
    payload = verify_payload(token, secret, expected_kind="browser_session")
    try:
        user_id = UUID(str(payload["user_id"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise SignedPayloadError("Invalid user id") from exc
    # Cookies issued before session revocation support implicitly belong to
    # version 1, so deploying this migration does not log everybody out.
    version = payload.get("version", 1)
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise SignedPayloadError("Invalid session version")
    return BrowserSession(user_id=user_id, version=version)


def create_oauth_state(secret: str, ttl_seconds: int, next_path: str) -> tuple[str, str, str]:
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    token = sign_payload(
        {
            "kind": "telegram_oauth_state",
            "state": state,
            "verifier": verifier,
            "next": safe_next_path(next_path),
            "exp": _timestamp() + ttl_seconds,
        },
        secret,
    )
    return state, verifier, token


def read_oauth_state(token: str, secret: str, returned_state: str) -> tuple[str, str]:
    payload = verify_payload(token, secret, expected_kind="telegram_oauth_state")
    state = payload.get("state")
    verifier = payload.get("verifier")
    next_path = payload.get("next")
    if not isinstance(state, str) or not hmac.compare_digest(state, returned_state):
        raise SignedPayloadError("OAuth state does not match")
    if not isinstance(verifier, str) or not isinstance(next_path, str):
        raise SignedPayloadError("Invalid OAuth state payload")
    return verifier, safe_next_path(next_path)


def code_challenge(verifier: str) -> str:
    return _base64url_encode(hashlib.sha256(verifier.encode("ascii")).digest())


def safe_next_path(value: str | None) -> str:
    if (
        not value
        or not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        return "/roadmaps"
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "/roadmaps"
    if parsed.scheme or parsed.netloc:
        return "/roadmaps"
    return value
