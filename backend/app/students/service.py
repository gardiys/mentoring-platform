import logging
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import String, and_, cast, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import api_error
from app.interviews.models import (
    InterviewMediaAnonymizationStatus,
    InterviewProcess,
    InterviewProcessStage,
)
from app.media.interview_anonymization_queue import enqueue_interview_media_anonymization
from app.mentors.models import (
    MentorStudent,
    StudentLearningStatus,
    StudentMentorshipState,
)
from app.notifications.models import NotificationKind, PlatformNotification, TelegramOutbox
from app.payments.service import (
    change_student_repayment_percent,
    sync_one_time_mentor_rewards,
    terminate_active_employment_for_student,
)
from app.progress.models import TopicProgress
from app.roadmaps.models import RoadmapEnrollment
from app.students.schemas import (
    AdminStudentDetail,
    AdminStudentListItem,
    AdminStudentMediaAnonymizationItem,
    AdminStudentMediaAnonymizationStatus,
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
from app.users.models import MENTOR_CAPABLE_ROLES, User, UserRole

logger = logging.getLogger(__name__)


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
            role=mentor.role,
            first_name=mentor.first_name,
            last_name=mentor.last_name,
            telegram_username=mentor.telegram_username,
        )
        for student_id, mentor in rows
    }


async def _student_learning_statuses(
    session: AsyncSession, student_ids: list[UUID]
) -> dict[UUID, StudentLearningStatus]:
    if not student_ids:
        return {}
    state_rows = (
        await session.execute(
            select(
                StudentMentorshipState.student_id,
                StudentMentorshipState.learning_status,
            ).where(StudentMentorshipState.student_id.in_(student_ids))
        )
    ).all()
    result = {student_id: learning_status for student_id, learning_status in state_rows}
    missing_ids = set(student_ids) - set(result)
    if missing_ids:
        legacy_rows = (
            await session.execute(
                select(MentorStudent.student_id, MentorStudent.learning_status).where(
                    MentorStudent.student_id.in_(missing_ids)
                )
            )
        ).all()
        result.update({student_id: learning_status for student_id, learning_status in legacy_rows})
    return result


async def _student_reward_percentages(
    session: AsyncSession, student_ids: list[UUID]
) -> dict[UUID, Decimal | None]:
    if not student_ids:
        return {}
    rows = (
        await session.execute(
            select(MentorStudent.student_id, MentorStudent.reward_percent).where(
                MentorStudent.student_id.in_(student_ids)
            )
        )
    ).all()
    return {student_id: reward_percent for student_id, reward_percent in rows}


async def _available_mentors(session: AsyncSession) -> list[AdminStudentMentorRead]:
    mentors = list(
        await session.scalars(
            select(User)
            .where(User.role.in_(MENTOR_CAPABLE_ROLES))
            .order_by(User.first_name, User.last_name, User.id)
        )
    )
    return [
        AdminStudentMentorRead(
            id=mentor.id,
            role=mentor.role,
            first_name=mentor.first_name,
            last_name=mentor.last_name,
            telegram_username=mentor.telegram_username,
        )
        for mentor in mentors
    ]


async def _available_tracks(session: AsyncSession) -> list[AdminStudentTrackOption]:
    tracks = list(
        await session.scalars(
            select(LearningTrack).order_by(LearningTrack.position, LearningTrack.title)
        )
    )
    return [
        AdminStudentTrackOption(
            id=track.id,
            slug=track.slug,
            title=track.title,
            is_published=track.is_published,
        )
        for track in tracks
    ]


async def list_students(
    session: AsyncSession,
    *,
    query: str | None,
    track_id: UUID | None,
    learning_statuses: list[StudentLearningStatus] | None,
    is_active: bool | None,
    mentor_id: UUID | None,
    without_mentor: bool,
    limit: int,
    offset: int,
) -> AdminStudentPage:
    if mentor_id is not None and without_mentor:
        api_error(422, "mentor_filter_conflict", "Choose a mentor or students without a mentor")
    conditions = [User.role == UserRole.STUDENT]
    if query:
        pattern = f"%{query.strip()}%"
        conditions.append(
            or_(
                User.first_name.ilike(pattern),
                User.last_name.ilike(pattern),
                User.email.ilike(pattern),
                User.telegram_username.ilike(pattern),
                cast(User.telegram_id, String).ilike(pattern),
            )
        )
    if is_active is not None:
        conditions.append(User.is_active.is_(is_active))
    if track_id is not None:
        conditions.append(
            select(LearningTrackEnrollment.user_id)
            .where(
                LearningTrackEnrollment.user_id == User.id,
                LearningTrackEnrollment.track_id == track_id,
            )
            .exists()
        )
    mentor_relation = select(MentorStudent.student_id).where(MentorStudent.student_id == User.id)
    if learning_statuses:
        matching_state = select(StudentMentorshipState.student_id).where(
            StudentMentorshipState.student_id == User.id,
            StudentMentorshipState.learning_status.in_(learning_statuses),
        )
        matching_legacy_status = mentor_relation.where(
            MentorStudent.learning_status.in_(learning_statuses)
        )
        if StudentLearningStatus.LEARNING in learning_statuses:
            conditions.append(
                or_(
                    matching_state.exists(),
                    matching_legacy_status.exists(),
                    and_(
                        ~select(StudentMentorshipState.student_id)
                        .where(StudentMentorshipState.student_id == User.id)
                        .exists(),
                        ~mentor_relation.exists(),
                    ),
                )
            )
        else:
            conditions.append(or_(matching_state.exists(), matching_legacy_status.exists()))
    if mentor_id is not None:
        conditions.append(mentor_relation.where(MentorStudent.mentor_id == mentor_id).exists())
    elif without_mentor:
        conditions.append(~mentor_relation.exists())

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
    learning_statuses_by_student = await _student_learning_statuses(session, ids)
    reward_percentages = await _student_reward_percentages(session, ids)
    return AdminStudentPage(
        items=[
            AdminStudentListItem(
                id=student.id,
                telegram_id=student.telegram_id,
                telegram_username=student.telegram_username,
                first_name=student.first_name,
                last_name=student.last_name,
                email=student.email,
                is_active=student.is_active,
                learning_status=learning_statuses_by_student.get(
                    student.id, StudentLearningStatus.LEARNING
                ),
                created_at=student.created_at,
                learning_start_date=student.learning_start_date,
                mentor=mentors.get(student.id),
                tracks=tracks.get(student.id, []),
                last_progress_at=progress.get(student.id),
                repayment_percent=student.repayment_percent,
                mentor_reward_percent=reward_percentages.get(student.id),
                entry_payment_kopecks=student.entry_payment_kopecks,
                entry_payment_paid_at=student.entry_payment_paid_at,
                program_excluded_at=student.program_excluded_at,
                program_exclusion_reason=student.program_exclusion_reason,
                public_identity_hidden_at=student.public_identity_hidden_at,
                public_identity_hidden_reason=student.public_identity_hidden_reason,
                personal_data_erased_at=student.personal_data_erased_at,
                personal_data_erasure_reason=student.personal_data_erasure_reason,
            )
            for student in students
        ],
        total=total,
        limit=limit,
        offset=offset,
        mentors=await _available_mentors(session),
        tracks=await _available_tracks(session),
    )


async def student_detail(session: AsyncSession, student_id: UUID) -> AdminStudentDetail:
    student = await get_student_model(session, student_id)
    tracks = await _student_tracks(session, [student.id])
    progress = await _last_progress(session, [student.id])
    mentors = await _student_mentors(session, [student.id])
    learning_statuses = await _student_learning_statuses(session, [student.id])
    return AdminStudentDetail(
        id=student.id,
        telegram_id=student.telegram_id,
        telegram_username=student.telegram_username,
        first_name=student.first_name,
        last_name=student.last_name,
        email=student.email,
        is_active=student.is_active,
        learning_status=learning_statuses.get(student.id, StudentLearningStatus.LEARNING),
        created_at=student.created_at,
        learning_start_date=student.learning_start_date,
        mentor=mentors.get(student.id),
        updated_at=student.updated_at,
        onboarding_completed_at=student.onboarding_completed_at,
        tracks=tracks.get(student.id, []),
        last_progress_at=progress.get(student.id),
        repayment_percent=student.repayment_percent,
        mentor_reward_percent=(
            await session.scalar(
                select(MentorStudent.reward_percent).where(MentorStudent.student_id == student.id)
            )
        ),
        entry_payment_kopecks=student.entry_payment_kopecks,
        entry_payment_paid_at=student.entry_payment_paid_at,
        program_excluded_at=student.program_excluded_at,
        program_exclusion_reason=student.program_exclusion_reason,
        public_identity_hidden_at=student.public_identity_hidden_at,
        public_identity_hidden_reason=student.public_identity_hidden_reason,
        personal_data_erased_at=student.personal_data_erased_at,
        personal_data_erasure_reason=student.personal_data_erasure_reason,
    )


async def student_options(session: AsyncSession) -> AdminStudentOptions:
    mentors = await _available_mentors(session)
    return AdminStudentOptions(
        tracks=await _available_tracks(session),
        mentors=mentors,
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
        if mentor is None or mentor.role not in MENTOR_CAPABLE_ROLES:
            api_error(422, "invalid_student_mentor", "Selected mentor does not exist")
    elif payload.mentor_reward_percent is not None:
        api_error(
            422,
            "mentor_reward_without_mentor",
            "A mentor must be selected before setting a mentor reward percentage",
        )


async def _sync_student_mentor(
    session: AsyncSession,
    student_id: UUID,
    mentor_id: UUID | None,
    reward_percent: Decimal | None = None,
) -> None:
    relation = await session.scalar(
        select(MentorStudent).where(MentorStudent.student_id == student_id).with_for_update()
    )
    if mentor_id is None:
        if relation is not None:
            await session.delete(relation)
        return
    if relation is None:
        state = await session.get(StudentMentorshipState, student_id)
        session.add(
            MentorStudent(
                mentor_id=mentor_id,
                student_id=student_id,
                reward_percent=reward_percent,
                learning_status=(
                    state.learning_status if state else StudentLearningStatus.LEARNING
                ),
                strength_level=state.strength_level if state else None,
                status_updated_at=state.status_updated_at if state else datetime.now(UTC),
            )
        )
    else:
        relation.mentor_id = mentor_id
        relation.reward_percent = reward_percent


async def _effective_mentor_reward_percent(
    session: AsyncSession, payload: AdminStudentMutation
) -> Decimal | None:
    if payload.mentor_id is None:
        return None
    if payload.mentor_reward_percent is not None:
        return payload.mentor_reward_percent
    slugs = set(
        await session.scalars(
            select(LearningTrack.slug).where(LearningTrack.id.in_(payload.track_ids))
        )
    )
    go_only = bool(slugs) and all(slug.casefold() == "go" for slug in slugs)
    return Decimal("45") if go_only else Decimal("60")


def _rubles_to_kopecks(value: Decimal) -> int:
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


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
    mentor_reward_percent = await _effective_mentor_reward_percent(session, payload)
    student = User(
        telegram_id=payload.telegram_id,
        telegram_username=payload.telegram_username,
        first_name=payload.first_name,
        last_name=payload.last_name or None,
        email=payload.email or None,
        role=UserRole.STUDENT,
        onboarding_completed_at=now,
        learning_start_date=payload.learning_start_date or now.date(),
        repayment_percent=payload.repayment_percent,
        entry_payment_kopecks=_rubles_to_kopecks(payload.entry_payment_rubles),
        entry_payment_paid_at=now if payload.entry_payment_paid else None,
        program_excluded_at=now if payload.program_excluded else None,
        program_exclusion_reason=(
            payload.program_exclusion_reason or None if payload.program_excluded else None
        ),
        is_active=True,
    )
    session.add(student)
    try:
        await session.flush()
        session.add(
            StudentMentorshipState(
                student_id=student.id,
                learning_status=StudentLearningStatus.LEARNING,
                status_updated_at=now,
            )
        )
        await _sync_student_tracks(session, student.id, payload.track_ids)
        await _sync_student_mentor(
            session,
            student.id,
            payload.mentor_id,
            mentor_reward_percent,
        )
        if payload.program_excluded:
            student.is_active = False
        await sync_one_time_mentor_rewards(session, student.id)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        api_error(409, "student_conflict", "Student data conflicts with an account")
    return await student_detail(session, student.id)


async def update_student(
    session: AsyncSession, student_id: UUID, payload: AdminStudentMutation
) -> AdminStudentDetail:
    student = await get_student_model(session, student_id, lock=True)
    if student.personal_data_erased_at is not None:
        api_error(
            409,
            "student_personal_data_erased",
            "Erased personal data cannot be restored through student editing",
        )
    # Keep the lock order consistent with mentor-side mutations (assignment,
    # then employment/payment rows) so reassignment cannot race an old
    # mentor's write and concurrent requests do not deadlock each other.
    await session.scalar(
        select(MentorStudent).where(MentorStudent.student_id == student.id).with_for_update()
    )
    await _validate_student_payload(session, payload, student_id=student_id)
    revoke_browser_sessions = student.telegram_id != payload.telegram_id or (
        payload.program_excluded and student.is_active
    )
    student.telegram_id = payload.telegram_id
    student.telegram_username = payload.telegram_username
    student.first_name = payload.first_name
    student.last_name = payload.last_name or None
    student.email = payload.email or None
    await change_student_repayment_percent(session, student.id, payload.repayment_percent)
    student.repayment_percent = payload.repayment_percent
    student.entry_payment_kopecks = _rubles_to_kopecks(payload.entry_payment_rubles)
    student.entry_payment_paid_at = (
        student.entry_payment_paid_at or datetime.now(UTC) if payload.entry_payment_paid else None
    )
    student.program_excluded_at = (
        student.program_excluded_at or datetime.now(UTC) if payload.program_excluded else None
    )
    student.program_exclusion_reason = (
        payload.program_exclusion_reason or None if payload.program_excluded else None
    )
    if payload.program_excluded:
        student.is_active = False
        await terminate_active_employment_for_student(
            session,
            student.id,
            ended_at=datetime.now(UTC).date(),
            reason=payload.program_exclusion_reason or "Исключён из программы",
        )
    if revoke_browser_sessions:
        student.session_version += 1
    if payload.learning_start_date is not None:
        await _set_learning_start_date(session, student, payload.learning_start_date)
    try:
        mentor_reward_percent = await _effective_mentor_reward_percent(session, payload)
        await _sync_student_tracks(session, student.id, payload.track_ids)
        await _sync_student_mentor(
            session,
            student.id,
            payload.mentor_id,
            mentor_reward_percent,
        )
        await sync_one_time_mentor_rewards(session, student.id)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        api_error(409, "student_conflict", "Student data conflicts with an account")
    return await student_detail(session, student.id)


async def set_student_access(
    session: AsyncSession, student_id: UUID, *, is_active: bool
) -> AdminStudentDetail:
    student = await get_student_model(session, student_id, lock=True)
    if is_active and student.personal_data_erased_at is not None:
        api_error(
            409,
            "student_personal_data_erased",
            "Access cannot be restored after personal data erasure",
        )
    if student.is_active != is_active:
        student.session_version += 1
    student.is_active = is_active
    await session.commit()
    return await student_detail(session, student.id)


async def _queue_student_media_anonymization(session: AsyncSession, student_id: UUID) -> list[UUID]:
    stages = list(
        await session.scalars(
            select(InterviewProcessStage)
            .join(InterviewProcess, InterviewProcess.id == InterviewProcessStage.process_id)
            .where(
                InterviewProcess.user_id == student_id,
                InterviewProcessStage.media_storage_key.is_not(None),
                InterviewProcessStage.media_filename.is_not(None),
                InterviewProcessStage.media_content_type.is_not(None),
                InterviewProcessStage.media_size.is_not(None),
                or_(
                    InterviewProcessStage.media_anonymization_status.is_(None),
                    InterviewProcessStage.media_anonymization_status
                    != InterviewMediaAnonymizationStatus.READY,
                    InterviewProcessStage.anonymized_media_storage_key.is_(None),
                ),
            )
            .with_for_update()
        )
    )
    for stage in stages:
        stage.media_anonymization_status = InterviewMediaAnonymizationStatus.QUEUED
        stage.media_anonymization_started_at = None
        stage.media_anonymization_completed_at = None
        stage.media_anonymization_error = None
    return [stage.id for stage in stages]


async def _redact_student_public_notifications(session: AsyncSession, student_id: UUID) -> None:
    await session.execute(
        update(PlatformNotification)
        .where(
            PlatformNotification.actor_user_id == student_id,
            PlatformNotification.kind == NotificationKind.INTERVIEW_PUBLISHED,
        )
        .values(body="Собеседование опубликовано скрытым учеником.")
    )
    all_stage_ids = list(
        await session.scalars(
            select(InterviewProcessStage.id)
            .join(InterviewProcess, InterviewProcess.id == InterviewProcessStage.process_id)
            .where(InterviewProcess.user_id == student_id)
        )
    )
    if all_stage_ids:
        event_keys = [
            f"telegram:interview-stage-published:{stage_id}" for stage_id in all_stage_ids
        ]
        await session.execute(
            update(TelegramOutbox)
            .where(TelegramOutbox.event_key.in_(event_keys))
            .values(text="Новое собеседование опубликовано скрытым учеником.")
        )


async def _enqueue_anonymization_jobs(stage_ids: list[UUID], *, force: bool = False) -> None:
    for stage_id in stage_ids:
        try:
            await enqueue_interview_media_anonymization(str(stage_id), force=force)
        except Exception:
            # Privacy state is already committed. The worker reconciler will
            # discover queued rows after Redis becomes available again.
            logger.exception(
                "Could not enqueue interview media anonymization stage_id=%s", stage_id
            )


def _stage_anonymization_ready(stage: InterviewProcessStage) -> bool:
    return (
        stage.media_anonymization_status == InterviewMediaAnonymizationStatus.READY
        and stage.anonymized_media_storage_key is not None
        and stage.anonymized_media_filename is not None
        and stage.anonymized_media_content_type is not None
        and stage.anonymized_media_size is not None
        and stage.anonymized_media_size > 0
    )


async def student_media_anonymization_status(
    session: AsyncSession, student_id: UUID
) -> AdminStudentMediaAnonymizationStatus:
    student = await get_student_model(session, student_id)
    rows = (
        await session.execute(
            select(InterviewProcessStage, InterviewProcess.company_name)
            .join(InterviewProcess, InterviewProcess.id == InterviewProcessStage.process_id)
            .where(
                InterviewProcess.user_id == student.id,
                InterviewProcessStage.media_storage_key.is_not(None),
            )
            .order_by(
                InterviewProcessStage.scheduled_at.desc(),
                InterviewProcessStage.id,
            )
        )
    ).all()
    items: list[AdminStudentMediaAnonymizationItem] = []
    counts = {
        "ready": 0,
        "queued": 0,
        "processing": 0,
        "failed": 0,
        "not_started": 0,
    }
    for stage, company_name in rows:
        ready = _stage_anonymization_ready(stage)
        if ready:
            counts["ready"] += 1
        elif stage.media_anonymization_status == InterviewMediaAnonymizationStatus.QUEUED:
            counts["queued"] += 1
        elif stage.media_anonymization_status == InterviewMediaAnonymizationStatus.PROCESSING:
            counts["processing"] += 1
        elif stage.media_anonymization_status in {
            InterviewMediaAnonymizationStatus.FAILED,
            InterviewMediaAnonymizationStatus.READY,
        }:
            # READY without an object is an inconsistent, retryable state.
            counts["failed"] += 1
        else:
            counts["not_started"] += 1
        items.append(
            AdminStudentMediaAnonymizationItem(
                stage_id=stage.id,
                process_id=stage.process_id,
                company_name=company_name,
                filename=stage.media_filename or "Запись без имени",
                status=stage.media_anonymization_status,
                ready=ready,
                error=stage.media_anonymization_error,
                started_at=stage.media_anonymization_started_at,
                completed_at=stage.media_anonymization_completed_at,
            )
        )
    return AdminStudentMediaAnonymizationStatus(
        identity_hidden=(
            student.public_identity_hidden_at is not None
            or student.personal_data_erased_at is not None
        ),
        total=len(items),
        items=items,
        **counts,
    )


async def retry_student_media_anonymization(
    session: AsyncSession, student_id: UUID
) -> AdminStudentMediaAnonymizationStatus:
    student = await get_student_model(session, student_id, lock=True)
    if student.public_identity_hidden_at is None and student.personal_data_erased_at is None:
        api_error(
            409,
            "student_identity_not_hidden",
            "Hide the student's public identity before anonymizing recordings",
        )
    stale_before = datetime.now(UTC) - timedelta(
        seconds=get_settings().content_media_normalization_stale_seconds
    )
    stages = list(
        await session.scalars(
            select(InterviewProcessStage)
            .join(InterviewProcess, InterviewProcess.id == InterviewProcessStage.process_id)
            .where(
                InterviewProcess.user_id == student.id,
                InterviewProcessStage.media_storage_key.is_not(None),
            )
            .with_for_update()
        )
    )
    retry_ids: list[UUID] = []
    for stage in stages:
        ready = _stage_anonymization_ready(stage)
        active = (
            stage.media_anonymization_status == InterviewMediaAnonymizationStatus.PROCESSING
            and stage.media_anonymization_started_at is not None
            and stage.media_anonymization_started_at >= stale_before
        )
        if ready or active:
            continue
        stage.media_anonymization_status = InterviewMediaAnonymizationStatus.QUEUED
        stage.media_anonymization_started_at = None
        stage.media_anonymization_completed_at = None
        stage.media_anonymization_error = None
        retry_ids.append(stage.id)
    await session.commit()
    await _enqueue_anonymization_jobs(retry_ids, force=True)
    return await student_media_anonymization_status(session, student.id)


async def set_student_public_identity(
    session: AsyncSession,
    admin: User,
    student_id: UUID,
    *,
    hidden: bool,
    reason: str | None,
) -> AdminStudentDetail:
    student = await get_student_model(session, student_id, lock=True)
    if not hidden and student.personal_data_erased_at is not None:
        api_error(
            409,
            "student_personal_data_erased",
            "Public identity cannot be restored after personal data erasure",
        )
    stage_ids: list[UUID] = []
    if hidden:
        student.public_identity_hidden_at = student.public_identity_hidden_at or datetime.now(UTC)
        student.public_identity_hidden_by_user_id = admin.id
        student.public_identity_hidden_reason = reason
        stage_ids = await _queue_student_media_anonymization(session, student.id)
        await _redact_student_public_notifications(session, student.id)
    else:
        student.public_identity_hidden_at = None
        student.public_identity_hidden_by_user_id = None
        student.public_identity_hidden_reason = None
    await session.commit()
    await _enqueue_anonymization_jobs(stage_ids)
    return await student_detail(session, student.id)


async def erase_student_personal_data(
    session: AsyncSession,
    admin: User,
    student_id: UUID,
    *,
    reason: str,
) -> AdminStudentDetail:
    student = await get_student_model(session, student_id, lock=True)
    if student.personal_data_erased_at is not None:
        return await student_detail(session, student.id)
    now = datetime.now(UTC)
    stage_ids = await _queue_student_media_anonymization(session, student.id)
    await _redact_student_public_notifications(session, student.id)
    student.public_identity_hidden_at = student.public_identity_hidden_at or now
    student.public_identity_hidden_by_user_id = admin.id
    student.public_identity_hidden_reason = reason
    student.personal_data_erased_at = now
    student.personal_data_erased_by_user_id = admin.id
    student.personal_data_erasure_reason = reason
    # Direct identifiers are irreversibly removed. Stable internal IDs and
    # collaboration/payment artifacts remain available for accounting and
    # dispute-resolution workflows.
    student.telegram_id = None
    student.telegram_username = None
    student.email = None
    student.first_name = "Удалённый ученик"
    student.last_name = None
    student.is_active = False
    student.session_version += 1
    await session.commit()
    await _enqueue_anonymization_jobs(stage_ids)
    return await student_detail(session, student.id)
