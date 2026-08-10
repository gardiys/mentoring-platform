from uuid import UUID

from app.media.protected_stream import create_bound_stream_ticket, read_bound_stream_ticket


def create_interview_stream_ticket(
    *,
    user_id: UUID,
    stage_id: UUID,
    user_agent: str,
    secret: str,
    ttl_seconds: int,
) -> str:
    return create_bound_stream_ticket(
        kind="interview_catalog_stream",
        resource_claim="stage_id",
        user_id=user_id,
        resource_id=stage_id,
        user_agent=user_agent,
        secret=secret,
        ttl_seconds=ttl_seconds,
    )


def read_interview_stream_ticket(token: str, *, user_agent: str, secret: str) -> tuple[UUID, UUID]:
    return read_bound_stream_ticket(
        token,
        expected_kind="interview_catalog_stream",
        resource_claim="stage_id",
        user_agent=user_agent,
        secret=secret,
    )
