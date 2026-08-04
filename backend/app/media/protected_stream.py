from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from uuid import UUID

from app.auth.web_session import SignedPayloadError, sign_payload, verify_payload


def _timestamp() -> int:
    return int(datetime.now(UTC).timestamp())


def _user_agent_digest(user_agent: str) -> str:
    return hashlib.sha256(user_agent.encode("utf-8")).hexdigest()


def create_bound_stream_ticket(
    *,
    kind: str,
    resource_claim: str,
    user_id: UUID,
    resource_id: UUID,
    user_agent: str,
    secret: str,
    ttl_seconds: int,
) -> str:
    """Create a short-lived ticket bound to one browser and one media resource."""

    return sign_payload(
        {
            "kind": kind,
            "user_id": str(user_id),
            resource_claim: str(resource_id),
            "user_agent": _user_agent_digest(user_agent),
            "exp": _timestamp() + ttl_seconds,
        },
        secret,
    )


def read_bound_stream_ticket(
    token: str,
    *,
    expected_kind: str,
    resource_claim: str,
    user_agent: str,
    secret: str,
) -> tuple[UUID, UUID]:
    """Validate browser binding and return the ticket user/resource pair."""

    payload = verify_payload(token, secret, expected_kind=expected_kind)
    expected_user_agent = payload.get("user_agent")
    if not isinstance(expected_user_agent, str) or not hmac.compare_digest(
        expected_user_agent,
        _user_agent_digest(user_agent),
    ):
        raise SignedPayloadError("Stream ticket belongs to another browser")
    try:
        return UUID(str(payload["user_id"])), UUID(str(payload[resource_claim]))
    except (KeyError, TypeError, ValueError) as error:
        raise SignedPayloadError("Invalid protected stream ticket") from error
