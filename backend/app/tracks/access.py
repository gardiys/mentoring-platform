from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.mentors.models import MentorTrackAssignment
from app.tracks.models import LearningTrack, LearningTrackEnrollment
from app.users.models import User, UserRole


async def accessible_track_ids(session: AsyncSession, user: User) -> set[UUID]:
    if user.role is UserRole.ADMIN:
        return set(await session.scalars(select(LearningTrack.id)))
    if user.role is UserRole.MENTOR:
        return set(
            await session.scalars(
                select(MentorTrackAssignment.track_id).where(
                    MentorTrackAssignment.mentor_id == user.id
                )
            )
        )
    return set(
        await session.scalars(
            select(LearningTrackEnrollment.track_id).where(
                LearningTrackEnrollment.user_id == user.id
            )
        )
    )


async def has_track_access(session: AsyncSession, user: User, track_id: UUID) -> bool:
    return track_id in await accessible_track_ids(session, user)
