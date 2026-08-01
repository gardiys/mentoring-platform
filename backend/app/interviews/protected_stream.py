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


def create_interview_stream_ticket(
    *,
    user_id: UUID,
    stage_id: UUID,
    user_agent: str,
    secret: str,
    ttl_seconds: int,
) -> str:
    return sign_payload(
        {
            "kind": "interview_catalog_stream",
            "user_id": str(user_id),
            "stage_id": str(stage_id),
            "user_agent": _user_agent_digest(user_agent),
            "exp": _timestamp() + ttl_seconds,
        },
        secret,
    )


def read_interview_stream_ticket(token: str, *, user_agent: str, secret: str) -> tuple[UUID, UUID]:
    payload = verify_payload(
        token,
        secret,
        expected_kind="interview_catalog_stream",
    )
    expected_user_agent = payload.get("user_agent")
    if not isinstance(expected_user_agent, str) or not hmac.compare_digest(
        expected_user_agent,
        _user_agent_digest(user_agent),
    ):
        raise SignedPayloadError("Stream ticket belongs to another browser")
    try:
        return UUID(str(payload["user_id"])), UUID(str(payload["stage_id"]))
    except (KeyError, TypeError, ValueError) as error:
        raise SignedPayloadError("Invalid interview stream ticket") from error
