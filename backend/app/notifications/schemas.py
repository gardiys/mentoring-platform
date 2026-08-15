from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.notifications.models import NotificationKind


class NotificationRead(BaseModel):
    id: UUID
    kind: NotificationKind
    title: str
    body: str
    action_url: str
    read_at: datetime | None
    created_at: datetime


class NotificationPage(BaseModel):
    items: list[NotificationRead]
    total: int
    unread_count: int
    limit: int
    offset: int
