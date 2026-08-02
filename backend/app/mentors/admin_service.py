from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import String, cast, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import api_error
from app.mentors.admin_schemas import (
    AdminMentorCandidate,
    AdminMentorListItem,
    AdminMentorMutation,
    AdminMentorStudentRead,
    AdminMentorTrackRead,
)
from app.mentors.models import MentorStudent, MentorTrackAssignment
from app.tracks.models import LearningTrack, LearningTrackEnrollment
from app.tracks.service import ensure_track_access
from app.users.models import User, UserRole


async def _mentor_read(
    session: AsyncSession, user: User, student_count: int
) -> AdminMentorListItem:
    tracks = list(
        await session.scalars(
            select(LearningTrack)
            .join(MentorTrackAssignment, MentorTrackAssignment.track_id == LearningTrack.id)
            .where(MentorTrackAssignment.mentor_id == user.id)
            .order_by(LearningTrack.position, LearningTrack.title)
        )
    )
    students = list(
        await session.scalars(
            select(User)
            .join(MentorStudent, MentorStudent.student_id == User.id)
            .where(MentorStudent.mentor_id == user.id)
            .order_by(User.first_name, User.last_name)
        )
    )
    return AdminMentorListItem(
        id=user.id,
        telegram_id=user.telegram_id,
        telegram_username=user.telegram_username,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        is_active=user.is_active,
        student_count=student_count,
        tracks=[
            AdminMentorTrackRead(id=item.id, slug=item.slug, title=item.title) for item in tracks
        ],
        students=[
            AdminMentorStudentRead(
                id=item.id,
                first_name=item.first_name,
                last_name=item.last_name,
                telegram_username=item.telegram_username,
            )
            for item in students
        ],
        created_at=user.created_at,
    )


async def list_admin_mentors(session: AsyncSession) -> list[AdminMentorListItem]:
    rows = (
        await session.execute(
            select(User, func.count(MentorStudent.student_id))
            .outerjoin(MentorStudent, MentorStudent.mentor_id == User.id)
            .where(User.role == UserRole.MENTOR)
            .group_by(User.id)
            .order_by(User.first_name, User.last_name, User.id)
        )
    ).all()
    return [await _mentor_read(session, mentor, student_count) for mentor, student_count in rows]


async def _validate_track_ids(session: AsyncSession, track_ids: list[UUID]) -> None:
    count = int(
        await session.scalar(
            select(func.count(LearningTrack.id)).where(LearningTrack.id.in_(track_ids))
        )
        or 0
    )
    if count != len(set(track_ids)):
        api_error(422, "invalid_mentor_tracks", "Одно или несколько направлений не найдены")


async def _sync_mentor_tracks(
    session: AsyncSession, mentor_id: UUID, track_ids: list[UUID]
) -> None:
    await session.execute(
        delete(MentorTrackAssignment).where(MentorTrackAssignment.mentor_id == mentor_id)
    )
    session.add_all(
        [MentorTrackAssignment(mentor_id=mentor_id, track_id=track_id) for track_id in track_ids]
    )


async def list_mentor_candidates(
    session: AsyncSession, *, query: str | None, limit: int
) -> list[AdminMentorCandidate]:
    statement = select(User).where(User.role == UserRole.STUDENT)
    if query:
        pattern = f"%{query.strip()}%"
        statement = statement.where(
            or_(
                User.first_name.ilike(pattern),
                User.last_name.ilike(pattern),
                User.email.ilike(pattern),
                User.telegram_username.ilike(pattern),
                cast(User.telegram_id, String).ilike(pattern),
            )
        )
    users = list(
        await session.scalars(statement.order_by(User.first_name, User.last_name).limit(limit))
    )
    return [
        AdminMentorCandidate(
            id=user.id,
            telegram_id=user.telegram_id,
            telegram_username=user.telegram_username,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
        )
        for user in users
    ]


async def _validate_mentor_payload(session: AsyncSession, payload: AdminMentorMutation) -> None:
    if await session.scalar(select(User.id).where(User.telegram_id == payload.telegram_id)):
        api_error(409, "telegram_id_already_used", "Telegram ID is already used")
    if payload.email and await session.scalar(select(User.id).where(User.email == payload.email)):
        api_error(409, "email_already_used", "Email is already used")


async def create_admin_mentor(
    session: AsyncSession, payload: AdminMentorMutation
) -> AdminMentorListItem:
    await _validate_mentor_payload(session, payload)
    await _validate_track_ids(session, payload.track_ids)
    mentor = User(
        telegram_id=payload.telegram_id,
        telegram_username=payload.telegram_username,
        first_name=payload.first_name,
        last_name=payload.last_name or None,
        email=payload.email or None,
        role=UserRole.MENTOR,
        onboarding_completed_at=datetime.now(UTC),
        is_active=True,
    )
    session.add(mentor)
    try:
        await session.flush()
        await _sync_mentor_tracks(session, mentor.id, payload.track_ids)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        api_error(409, "mentor_conflict", "Mentor data conflicts with an account")
    await session.refresh(mentor)
    return await _mentor_read(session, mentor, 0)


async def promote_student_to_mentor(session: AsyncSession, student_id: UUID) -> AdminMentorListItem:
    student = await session.scalar(
        select(User).where(User.id == student_id, User.role == UserRole.STUDENT).with_for_update()
    )
    if student is None:
        api_error(404, "student_not_found", "Student was not found")
    await session.execute(delete(MentorStudent).where(MentorStudent.student_id == student.id))
    track_ids = list(
        await session.scalars(
            select(LearningTrackEnrollment.track_id).where(
                LearningTrackEnrollment.user_id == student.id
            )
        )
    )
    if not track_ids:
        api_error(422, "mentor_directions_required", "Assign a direction before promotion")
    student.role = UserRole.MENTOR
    student.is_active = True
    await _sync_mentor_tracks(session, student.id, track_ids)
    await session.commit()
    await session.refresh(student)
    return await _mentor_read(session, student, 0)


async def update_mentor_directions(
    session: AsyncSession, mentor_id: UUID, track_ids: list[UUID]
) -> AdminMentorListItem:
    mentor = await session.scalar(
        select(User).where(User.id == mentor_id, User.role == UserRole.MENTOR).with_for_update()
    )
    if mentor is None:
        api_error(404, "mentor_not_found", "Mentor was not found")
    await _validate_track_ids(session, track_ids)
    required_track_ids = set(
        await session.scalars(
            select(LearningTrackEnrollment.track_id)
            .join(
                MentorStudent,
                MentorStudent.student_id == LearningTrackEnrollment.user_id,
            )
            .where(MentorStudent.mentor_id == mentor.id)
        )
    )
    if not required_track_ids.issubset(set(track_ids)):
        api_error(
            422,
            "mentor_directions_have_students",
            "Сначала переназначьте учеников, которые учатся на удаляемом направлении",
        )
    await _sync_mentor_tracks(session, mentor.id, track_ids)
    await session.commit()
    student_count = int(
        await session.scalar(
            select(func.count(MentorStudent.student_id)).where(MentorStudent.mentor_id == mentor.id)
        )
        or 0
    )
    return await _mentor_read(session, mentor, student_count)


async def reassign_student(session: AsyncSession, student_id: UUID, mentor_id: UUID) -> None:
    student = await session.get(User, student_id)
    mentor = await session.get(User, mentor_id)
    if student is None or student.role is not UserRole.STUDENT:
        api_error(404, "student_not_found", "Student was not found")
    if mentor is None or mentor.role is not UserRole.MENTOR:
        api_error(422, "invalid_student_mentor", "Selected mentor does not exist")
    student_track_ids = set(
        await session.scalars(
            select(LearningTrackEnrollment.track_id).where(
                LearningTrackEnrollment.user_id == student.id
            )
        )
    )
    mentor_track_ids = set(
        await session.scalars(
            select(MentorTrackAssignment.track_id).where(
                MentorTrackAssignment.mentor_id == mentor.id
            )
        )
    )
    if not student_track_ids.issubset(mentor_track_ids):
        api_error(
            422,
            "mentor_directions_mismatch",
            "Ментор должен вести все направления выбранного ученика",
        )
    relation = await session.scalar(
        select(MentorStudent).where(MentorStudent.student_id == student.id)
    )
    if relation is None:
        session.add(MentorStudent(mentor_id=mentor.id, student_id=student.id))
    else:
        relation.mentor_id = mentor.id
    await session.commit()


async def demote_mentor_to_student(session: AsyncSession, mentor_id: UUID) -> None:
    mentor = await session.scalar(
        select(User).where(User.id == mentor_id, User.role == UserRole.MENTOR).with_for_update()
    )
    if mentor is None:
        api_error(404, "mentor_not_found", "Mentor was not found")
    student_count = int(
        await session.scalar(
            select(func.count(MentorStudent.student_id)).where(MentorStudent.mentor_id == mentor.id)
        )
        or 0
    )
    if student_count:
        api_error(
            409,
            "mentor_has_students",
            "Reassign the mentor's students before removing the mentor role",
        )
    mentor.role = UserRole.STUDENT
    mentor.learning_start_date = mentor.learning_start_date or datetime.now(UTC).date()
    track_ids = list(
        await session.scalars(
            select(MentorTrackAssignment.track_id).where(
                MentorTrackAssignment.mentor_id == mentor.id
            )
        )
    )
    for track_id in track_ids:
        await ensure_track_access(session, user_id=mentor.id, track_id=track_id)
    await session.execute(
        delete(MentorTrackAssignment).where(MentorTrackAssignment.mentor_id == mentor.id)
    )
    await session.commit()
