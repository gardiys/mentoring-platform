from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import String, cast, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import api_error
from app.mentors.models import MentorStudent
from app.progress.models import TopicProgress
from app.roadmaps.models import RoadmapEnrollment
from app.students.schemas import (
    AdminStudentDetail,
    AdminStudentListItem,
    AdminStudentMentorRead,
    AdminStudentMutation,
    AdminStudentOptions,
    AdminStudentPage,
    AdminStudentTrackOption,
    AdminStudentTrackRead,
)
from app.tracks.models import LearningTrack, LearningTrackEnrollment
from app.tracks.service import ensure_track_access
from app.users.learning import learning_start_datetime
from app.users.models import User, UserRole


async def get_student_model(session: AsyncSession, student_id: UUID, *, lock: bool = False) -> User:
    statement = select(User).where(User.id == student_id, User.role == UserRole.STUDENT)
    if lock:
        statement = statement.with_for_update()
    student = await session.scalar(statement)
    if student is None:
        api_error(404, "student_not_found", "Student was not found")
    return student


async def _student_tracks(
    session: AsyncSession, student_ids: list[UUID]
) -> dict[UUID, list[AdminStudentTrackRead]]:
    if not student_ids:
        return {}
    rows = (
        await session.execute(
            select(
                LearningTrackEnrollment.user_id,
                LearningTrack,
                LearningTrackEnrollment.granted_at,
            )
            .join(LearningTrack, LearningTrack.id == LearningTrackEnrollment.track_id)
            .where(LearningTrackEnrollment.user_id.in_(student_ids))
            .order_by(LearningTrack.position, LearningTrack.title)
        )
    ).all()
    result: dict[UUID, list[AdminStudentTrackRead]] = {}
    for user_id, track, granted_at in rows:
        result.setdefault(user_id, []).append(
            AdminStudentTrackRead(
                id=track.id,
                slug=track.slug,
                title=track.title,
                is_published=track.is_published,
                granted_at=granted_at,
            )
        )
    return result


async def _last_progress(session: AsyncSession, student_ids: list[UUID]) -> dict[UUID, datetime]:
    if not student_ids:
        return {}
    rows = (
        await session.execute(
            select(TopicProgress.user_id, func.max(TopicProgress.updated_at))
            .where(TopicProgress.user_id.in_(student_ids))
            .group_by(TopicProgress.user_id)
        )
    ).all()
    return {user_id: updated_at for user_id, updated_at in rows if updated_at is not None}


async def _student_mentors(
    session: AsyncSession, student_ids: list[UUID]
) -> dict[UUID, AdminStudentMentorRead]:
    if not student_ids:
        return {}
    rows = (
        await session.execute(
            select(MentorStudent.student_id, User)
            .join(User, User.id == MentorStudent.mentor_id)
            .where(MentorStudent.student_id.in_(student_ids))
        )
    ).all()
    return {
        student_id: AdminStudentMentorRead(
            id=mentor.id,
            first_name=mentor.first_name,
            last_name=mentor.last_name,
            telegram_username=mentor.telegram_username,
        )
        for student_id, mentor in rows
    }


async def list_students(
    session: AsyncSession,
    *,
    query: str | None,
    access: str,
    limit: int,
    offset: int,
) -> AdminStudentPage:
    conditions = [User.role == UserRole.STUDENT]
    if query:
        pattern = f"%{query.strip()}%"
        conditions.append(
            or_(
                User.first_name.ilike(pattern),
                User.last_name.ilike(pattern),
                User.email.ilike(pattern),
                cast(User.telegram_id, String).ilike(pattern),
            )
        )
    if access == "active":
        conditions.append(User.is_active.is_(True))
    elif access == "blocked":
        conditions.append(User.is_active.is_(False))

    total = int(await session.scalar(select(func.count(User.id)).where(*conditions)) or 0)
    students = list(
        await session.scalars(
            select(User)
            .where(*conditions)
            .order_by(User.created_at.desc(), User.first_name)
            .limit(limit)
            .offset(offset)
        )
    )
    ids = [student.id for student in students]
    tracks = await _student_tracks(session, ids)
    progress = await _last_progress(session, ids)
    mentors = await _student_mentors(session, ids)
    return AdminStudentPage(
        items=[
            AdminStudentListItem(
                id=student.id,
                telegram_id=student.telegram_id,
                first_name=student.first_name,
                last_name=student.last_name,
                email=student.email,
                is_active=student.is_active,
                created_at=student.created_at,
                learning_start_date=student.learning_start_date,
                mentor=mentors.get(student.id),
                tracks=tracks.get(student.id, []),
                last_progress_at=progress.get(student.id),
            )
            for student in students
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


async def student_detail(session: AsyncSession, student_id: UUID) -> AdminStudentDetail:
    student = await get_student_model(session, student_id)
    tracks = await _student_tracks(session, [student.id])
    progress = await _last_progress(session, [student.id])
    mentors = await _student_mentors(session, [student.id])
    return AdminStudentDetail(
        id=student.id,
        telegram_id=student.telegram_id,
        first_name=student.first_name,
        last_name=student.last_name,
        email=student.email,
        is_active=student.is_active,
        created_at=student.created_at,
        learning_start_date=student.learning_start_date,
        mentor=mentors.get(student.id),
        updated_at=student.updated_at,
        onboarding_completed_at=student.onboarding_completed_at,
        tracks=tracks.get(student.id, []),
        last_progress_at=progress.get(student.id),
    )


async def student_options(session: AsyncSession) -> AdminStudentOptions:
    tracks = list(
        await session.scalars(
            select(LearningTrack).order_by(LearningTrack.position, LearningTrack.title)
        )
    )
    mentors = list(
        await session.scalars(
            select(User)
            .where(User.role == UserRole.MENTOR, User.is_active.is_(True))
            .order_by(User.first_name, User.last_name)
        )
    )
    return AdminStudentOptions(
        tracks=[
            AdminStudentTrackOption(
                id=track.id,
                slug=track.slug,
                title=track.title,
                is_published=track.is_published,
            )
            for track in tracks
        ],
        mentors=[
            AdminStudentMentorRead(
                id=mentor.id,
                first_name=mentor.first_name,
                last_name=mentor.last_name,
                telegram_username=mentor.telegram_username,
            )
            for mentor in mentors
        ],
    )


async def _validate_student_payload(
    session: AsyncSession,
    payload: AdminStudentMutation,
    *,
    student_id: UUID | None,
) -> None:
    telegram_owner = select(User.id).where(User.telegram_id == payload.telegram_id)
    if student_id is not None:
        telegram_owner = telegram_owner.where(User.id != student_id)
    if await session.scalar(telegram_owner) is not None:
        api_error(409, "telegram_id_already_used", "Telegram ID is already used")

    if payload.email:
        email_owner = select(User.id).where(User.email == payload.email)
        if student_id is not None:
            email_owner = email_owner.where(User.id != student_id)
        if await session.scalar(email_owner) is not None:
            api_error(409, "email_already_used", "Email is already used")

    if payload.track_ids:
        count = await session.scalar(
            select(func.count(LearningTrack.id)).where(LearningTrack.id.in_(payload.track_ids))
        )
        if count != len(payload.track_ids):
            api_error(422, "invalid_student_tracks", "One or more tracks do not exist")
    if payload.mentor_id is not None:
        mentor = await session.get(User, payload.mentor_id)
        if mentor is None or mentor.role not in {UserRole.MENTOR, UserRole.ADMIN}:
            api_error(422, "invalid_student_mentor", "Selected mentor does not exist")


async def _sync_student_mentor(
    session: AsyncSession, student_id: UUID, mentor_id: UUID | None
) -> None:
    relation = await session.scalar(
        select(MentorStudent).where(MentorStudent.student_id == student_id)
    )
    if mentor_id is None:
        if relation is not None:
            await session.delete(relation)
        return
    if relation is None:
        session.add(MentorStudent(mentor_id=mentor_id, student_id=student_id))
    else:
        relation.mentor_id = mentor_id


async def _sync_student_tracks(
    session: AsyncSession, student_id: UUID, track_ids: list[UUID]
) -> None:
    current_ids = set(
        await session.scalars(
            select(LearningTrackEnrollment.track_id).where(
                LearningTrackEnrollment.user_id == student_id
            )
        )
    )
    requested_ids = set(track_ids)
    if removed_ids := current_ids - requested_ids:
        await session.execute(
            delete(LearningTrackEnrollment).where(
                LearningTrackEnrollment.user_id == student_id,
                LearningTrackEnrollment.track_id.in_(removed_ids),
            )
        )
    for track_id in track_ids:
        await ensure_track_access(session, user_id=student_id, track_id=track_id)


async def _set_learning_start_date(
    session: AsyncSession, student: User, learning_start_date: date
) -> None:
    student.learning_start_date = learning_start_date
    await session.execute(
        update(RoadmapEnrollment)
        .where(RoadmapEnrollment.user_id == student.id)
        .values(started_at=learning_start_datetime(learning_start_date))
    )


async def create_student(
    session: AsyncSession, payload: AdminStudentMutation
) -> AdminStudentDetail:
    await _validate_student_payload(session, payload, student_id=None)
    now = datetime.now(UTC)
    student = User(
        telegram_id=payload.telegram_id,
        first_name=payload.first_name,
        last_name=payload.last_name or None,
        email=payload.email or None,
        role=UserRole.STUDENT,
        onboarding_completed_at=now,
        learning_start_date=payload.learning_start_date or now.date(),
        is_active=True,
    )
    session.add(student)
    try:
        await session.flush()
        await _sync_student_tracks(session, student.id, payload.track_ids)
        await _sync_student_mentor(session, student.id, payload.mentor_id)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        api_error(409, "student_conflict", "Student data conflicts with an account")
    return await student_detail(session, student.id)


async def update_student(
    session: AsyncSession, student_id: UUID, payload: AdminStudentMutation
) -> AdminStudentDetail:
    student = await get_student_model(session, student_id, lock=True)
    await _validate_student_payload(session, payload, student_id=student_id)
    student.telegram_id = payload.telegram_id
    student.first_name = payload.first_name
    student.last_name = payload.last_name or None
    student.email = payload.email or None
    if payload.learning_start_date is not None:
        await _set_learning_start_date(session, student, payload.learning_start_date)
    try:
        await _sync_student_tracks(session, student.id, payload.track_ids)
        await _sync_student_mentor(session, student.id, payload.mentor_id)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        api_error(409, "student_conflict", "Student data conflicts with an account")
    return await student_detail(session, student.id)


async def set_student_access(
    session: AsyncSession, student_id: UUID, *, is_active: bool
) -> AdminStudentDetail:
    student = await get_student_model(session, student_id, lock=True)
    student.is_active = is_active
    await session.commit()
    return await student_detail(session, student.id)
