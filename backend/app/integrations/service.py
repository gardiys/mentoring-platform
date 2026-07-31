from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import api_error
from app.integrations.schemas import ProvisionTelegramStudentRequest
from app.roadmaps.models import Roadmap
from app.tracks.models import LearningTrack
from app.tracks.service import (
    ensure_track_access,
    get_published_track_by_slug,
    track_roadmap_models,
)
from app.users.models import User, UserRole


@dataclass(frozen=True)
class ProvisionedStudent:
    user: User
    track: LearningTrack
    roadmaps: list[Roadmap]
    created: bool
    access_created: bool


async def provision_telegram_student(
    session: AsyncSession,
    payload: ProvisionTelegramStudentRequest,
) -> ProvisionedStudent:
    track = await get_published_track_by_slug(session, payload.track_slug)

    email = payload.email or None
    if email is not None:
        email_owner = await session.scalar(select(User).where(User.email == email))
        if email_owner is not None and email_owner.telegram_id != payload.telegram_id:
            api_error(409, "email_already_used", "Email is already used by another user")

    now = datetime.now(UTC)
    candidate_id = uuid4()
    try:
        created_id = await session.scalar(
            insert(User)
            .values(
                id=candidate_id,
                telegram_id=payload.telegram_id,
                first_name=payload.first_name,
                last_name=payload.last_name or None,
                email=email,
                role=UserRole.STUDENT,
                onboarding_completed_at=now,
            )
            .on_conflict_do_nothing(index_elements=[User.telegram_id])
            .returning(User.id)
        )
        created = created_id is not None
        user = await session.scalar(
            select(User).where(User.telegram_id == payload.telegram_id).with_for_update()
        )
        if user is None:
            raise RuntimeError("Telegram user upsert did not return a user")
        if user.role is not UserRole.STUDENT:
            api_error(
                409,
                "telegram_account_role_conflict",
                "Telegram account belongs to a non-student user",
            )

        user.first_name = payload.first_name
        user.last_name = payload.last_name or None
        if email is not None:
            user.email = email
        user.onboarding_completed_at = user.onboarding_completed_at or now

        access_created = await ensure_track_access(
            session,
            user_id=user.id,
            track_id=track.id,
        )
        await session.commit()
        await session.refresh(user)
    except IntegrityError:
        await session.rollback()
        api_error(409, "student_provisioning_conflict", "Student data conflicts with an account")

    return ProvisionedStudent(
        user=user,
        track=track,
        roadmaps=await track_roadmap_models(session, track.id, published_only=True),
        created=created,
        access_created=access_created,
    )
