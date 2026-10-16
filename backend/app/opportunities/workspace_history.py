from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.opportunities.models import ConsultationRequest, GoTransitionApplication
from app.opportunities.workspace_models import (
    ConsultationRequestHistory,
    GoTransitionApplicationHistory,
)


def record_history(
    session: AsyncSession,
    item: ConsultationRequest | GoTransitionApplication,
    old_status: str | None,
    *,
    actor_id: UUID | None = None,
    comment: str | None = None,
    snapshot: dict[str, object] | None = None,
) -> UUID:
    event_id = uuid4()
    fields = dict(
        id=event_id,
        old_status=old_status,
        new_status=str(item.status),
        actor_user_id=actor_id,
        comment=comment,
        snapshot=jsonable_encoder(snapshot or {}),
        created_at=datetime.now(UTC),
    )
    if isinstance(item, ConsultationRequest):
        session.add(ConsultationRequestHistory(consultation_request_id=item.id, **fields))
    else:
        session.add(GoTransitionApplicationHistory(application_id=item.id, **fields))
    return event_id
