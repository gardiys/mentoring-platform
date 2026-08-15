from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import api_error
from app.interviews.journal_service import list_processes, process_detail
from app.interviews.models import (
    InterviewCardProgress,
    InterviewProcess,
    InterviewProcessStage,
    InterviewProcessStageAttachment,
    InterviewStageComment,
)
from app.interviews.schemas import (
    InterviewAttachmentRead,
    InterviewCatalogAuthorRead,
    InterviewCatalogCommentRead,
)
from app.interviews.uploads import StoredUpload
from app.mentors.models import (
    MentorDocumentKind,
    MentorStudent,
    MentorStudentDocument,
    MentorStudentNote,
    MentorStudentStatusHistory,
    MockInterview,
    MockInterviewStatus,
    StudentLearningStatus,
    StudentMentorshipState,
)
from app.mentors.schemas import (
    MentorCurrentTopic,
    MentorDocumentContentMutation,
    MentorDocumentRead,
    MentorInterviewDetail,
    MentorInterviewStageFeedback,
    MentorNoteRead,
    MentorStudentActivityKind,
    MentorStudentDetail,
    MentorStudentDirectionOption,
    MentorStudentListItem,
    MentorStudentMentorOption,
    MentorStudentPage,
    MentorStudentSort,
    MentorStudentStateMutation,
    MentorStudentStatusPeriod,
    MockInterviewFeedbackMutation,
    MockInterviewMutation,
    MockInterviewRead,
    StudentRoadmapSummary,
)
from app.notifications.models import NotificationKind
from app.notifications.service import actor_name, notify_student
from app.progress.models import ProgressStatus, TopicProgress
from app.roadmaps.models import Roadmap, RoadmapEnrollment, RoadmapSection, Topic
from app.roadmaps.queries import build_roadmap_detail, get_roadmap_model, list_roadmaps
from app.roadmaps.schemas import RoadmapDetail
from app.tracks.access import accessible_track_ids
from app.tracks.models import LearningTrack, LearningTrackEnrollment, LearningTrackRoadmap
from app.users.models import MENTOR_CAPABLE_ROLES, User, UserRole


async def assigned_student(
    session: AsyncSession,
    mentor: User,
    student_id: UUID,
    *,
    allow_any_user_for_admin: bool = False,
    lock: bool = False,
) -> tuple[User, MentorStudent | None]:
    student = await session.get(User, student_id)
    admin_can_read_any_user = mentor.role is UserRole.ADMIN and allow_any_user_for_admin
    if student is None or (student.role is not UserRole.STUDENT and not admin_can_read_any_user):
        api_error(404, "student_not_found", "Student was not found")
    relation_statement = select(MentorStudent).where(MentorStudent.student_id == student_id)
    if lock:
        relation_statement = relation_statement.with_for_update()
    relation = await session.scalar(relation_statement)
    if mentor.role is not UserRole.ADMIN and (relation is None or relation.mentor_id != mentor.id):
        api_error(
            403,
            "student_not_assigned_to_mentor",
            "Student is not assigned to this mentor",
        )
    return student, relation


async def _roadmap_details(
    session: AsyncSession, student_id: UUID, track_ids: set[UUID] | None = None
) -> list[RoadmapDetail]:
    summaries = await list_roadmaps(session, student_id, track_ids=track_ids)
    result: list[RoadmapDetail] = []
    for summary in summaries:
        roadmap = await get_roadmap_model(session, summary.slug)
        if roadmap is not None:
            result.append(await build_roadmap_detail(session, roadmap, student_id))
    return result


def _overdue_sections(roadmap: RoadmapDetail, now: datetime) -> int:
    return sum(
        1
        for section in roadmap.sections
        if section.deadline_at is not None
        and section.deadline_at < now
        and any(topic.status is not ProgressStatus.COMPLETED for topic in section.topics)
    )


async def _current_topics(
    session: AsyncSession,
    student_id: UUID,
    roadmaps: list[RoadmapDetail],
) -> list[MentorCurrentTopic]:
    rows = (
        await session.execute(
            select(TopicProgress, Topic, RoadmapSection, Roadmap)
            .join(Topic, Topic.id == TopicProgress.topic_id)
            .join(RoadmapSection, RoadmapSection.id == Topic.section_id)
            .join(Roadmap, Roadmap.id == RoadmapSection.roadmap_id)
            .where(
                TopicProgress.user_id == student_id,
                TopicProgress.status == ProgressStatus.IN_PROGRESS,
                TopicProgress.started_at.is_not(None),
            )
            .order_by(TopicProgress.started_at)
        )
    ).all()
    deadline_by_topic = {
        topic.id: section.deadline_at
        for roadmap in roadmaps
        for section in roadmap.sections
        for topic in section.topics
    }
    now = datetime.now(UTC)
    result: list[MentorCurrentTopic] = []
    for progress, topic, section, roadmap in rows:
        if progress.started_at is None:
            continue
        deadline = deadline_by_topic.get(topic.id)
        result.append(
            MentorCurrentTopic(
                id=topic.id,
                title=topic.title,
                section_title=section.title,
                roadmap_title=roadmap.title,
                started_at=progress.started_at,
                days_in_topic=max(0, (now - progress.started_at).days),
                deadline_at=deadline,
                is_overdue=deadline is not None and deadline < now,
            )
        )
    return result


def _last_activity_sort_expression() -> Any:
    """Return the latest meaningful student activity as a correlated SQL expression."""
    roadmap_activity = (
        select(func.max(TopicProgress.updated_at))
        .where(TopicProgress.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )
    process_activity = (
        select(func.max(InterviewProcess.updated_at))
        .where(InterviewProcess.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )
    stage_activity = (
        select(func.max(InterviewProcessStage.updated_at))
        .join(InterviewProcess, InterviewProcess.id == InterviewProcessStage.process_id)
        .where(InterviewProcess.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )
    attachment_activity = (
        select(func.max(InterviewProcessStageAttachment.created_at))
        .join(
            InterviewProcessStage,
            InterviewProcessStage.id == InterviewProcessStageAttachment.stage_id,
        )
        .join(InterviewProcess, InterviewProcess.id == InterviewProcessStage.process_id)
        .where(InterviewProcess.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )
    comment_activity = (
        select(func.max(InterviewStageComment.created_at))
        .where(InterviewStageComment.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )
    card_activity = (
        select(func.max(InterviewCardProgress.last_reviewed_at))
        .where(InterviewCardProgress.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )
    return func.greatest(
        roadmap_activity,
        process_activity,
        stage_activity,
        attachment_activity,
        comment_activity,
        card_activity,
    )


async def _student_activity(
    session: AsyncSession, student_ids: list[UUID]
) -> dict[UUID, tuple[datetime | None, MentorStudentActivityKind | None]]:
    if not student_ids:
        return {}
    result: dict[UUID, tuple[datetime | None, MentorStudentActivityKind | None]] = {
        student_id: (None, None) for student_id in student_ids
    }

    def remember(
        student_id: UUID,
        activity_at: datetime | None,
        kind: MentorStudentActivityKind,
    ) -> None:
        current_at, _ = result[student_id]
        if activity_at is not None and (current_at is None or activity_at > current_at):
            result[student_id] = (activity_at, kind)

    roadmap_rows = (
        await session.execute(
            select(TopicProgress.user_id, func.max(TopicProgress.updated_at))
            .where(TopicProgress.user_id.in_(student_ids))
            .group_by(TopicProgress.user_id)
        )
    ).all()
    for student_id, activity_at in roadmap_rows:
        remember(student_id, activity_at, MentorStudentActivityKind.ROADMAP)

    process_rows = (
        await session.execute(
            select(InterviewProcess.user_id, func.max(InterviewProcess.updated_at))
            .where(InterviewProcess.user_id.in_(student_ids))
            .group_by(InterviewProcess.user_id)
        )
    ).all()
    for student_id, activity_at in process_rows:
        remember(student_id, activity_at, MentorStudentActivityKind.INTERVIEW)

    stage_rows = (
        await session.execute(
            select(InterviewProcess.user_id, func.max(InterviewProcessStage.updated_at))
            .join(InterviewProcessStage, InterviewProcessStage.process_id == InterviewProcess.id)
            .where(InterviewProcess.user_id.in_(student_ids))
            .group_by(InterviewProcess.user_id)
        )
    ).all()
    for student_id, activity_at in stage_rows:
        remember(student_id, activity_at, MentorStudentActivityKind.INTERVIEW)

    attachment_rows = (
        await session.execute(
            select(
                InterviewProcess.user_id,
                func.max(InterviewProcessStageAttachment.created_at),
            )
            .join(InterviewProcessStage, InterviewProcessStage.process_id == InterviewProcess.id)
            .join(
                InterviewProcessStageAttachment,
                InterviewProcessStageAttachment.stage_id == InterviewProcessStage.id,
            )
            .where(InterviewProcess.user_id.in_(student_ids))
            .group_by(InterviewProcess.user_id)
        )
    ).all()
    for student_id, activity_at in attachment_rows:
        remember(student_id, activity_at, MentorStudentActivityKind.INTERVIEW)

    comment_rows = (
        await session.execute(
            select(InterviewStageComment.user_id, func.max(InterviewStageComment.created_at))
            .where(InterviewStageComment.user_id.in_(student_ids))
            .group_by(InterviewStageComment.user_id)
        )
    ).all()
    for student_id, activity_at in comment_rows:
        if student_id is not None:
            remember(student_id, activity_at, MentorStudentActivityKind.INTERVIEW)

    card_rows = (
        await session.execute(
            select(
                InterviewCardProgress.user_id,
                func.max(InterviewCardProgress.last_reviewed_at),
            )
            .where(InterviewCardProgress.user_id.in_(student_ids))
            .group_by(InterviewCardProgress.user_id)
        )
    ).all()
    for student_id, activity_at in card_rows:
        remember(student_id, activity_at, MentorStudentActivityKind.INTERVIEW_CARDS)
    return result


async def _student_item(
    session: AsyncSession,
    student: User,
    relation: MentorStudent | None,
    state: StudentMentorshipState | None = None,
    *,
    roadmap_details: list[RoadmapDetail] | None = None,
) -> MentorStudentListItem:
    now = datetime.now(UTC)
    roadmaps = roadmap_details or await _roadmap_details(session, student.id)
    overdue_by_roadmap = {roadmap.id: _overdue_sections(roadmap, now) for roadmap in roadmaps}
    last_activity = await _student_activity(session, [student.id])
    last_progress_at, last_activity_kind = last_activity.get(student.id, (None, None))
    weekly_completed = int(
        await session.scalar(
            select(func.count(TopicProgress.topic_id)).where(
                TopicProgress.user_id == student.id,
                TopicProgress.last_completed_at >= now - timedelta(days=7),
            )
        )
        or 0
    )
    mock_count = int(
        await session.scalar(
            select(func.count(MockInterview.id)).where(
                MockInterview.student_id == student.id,
                MockInterview.status == MockInterviewStatus.COMPLETED,
            )
        )
        or 0
    )
    return MentorStudentListItem(
        id=student.id,
        first_name=student.first_name,
        last_name=student.last_name,
        email=student.email,
        telegram_username=student.telegram_username,
        learning_start_date=student.learning_start_date,
        is_active=student.is_active,
        learning_status=(
            state.learning_status
            if state is not None
            else relation.learning_status
            if relation is not None
            else StudentLearningStatus.LEARNING
        ),
        strength_level=(
            state.strength_level
            if state is not None
            else relation.strength_level
            if relation is not None
            else None
        ),
        roadmaps=[
            StudentRoadmapSummary(
                id=roadmap.id,
                slug=roadmap.slug,
                title=roadmap.title,
                completed_topics=roadmap.completed_topics,
                total_topics=roadmap.total_topics,
                progress_percent=roadmap.progress_percent,
                started_at=roadmap.started_at,
                completed_at=roadmap.completed_at,
                overdue_sections=overdue_by_roadmap[roadmap.id],
            )
            for roadmap in roadmaps
        ],
        current_topics=await _current_topics(session, student.id, roadmaps),
        last_progress_at=last_progress_at,
        last_activity_kind=last_activity_kind,
        completed_topics_this_week=weekly_completed,
        is_overdue=any(overdue_by_roadmap.values()),
        mock_interview_count=mock_count,
    )


async def list_students(
    session: AsyncSession,
    mentor: User,
    *,
    query: str | None = None,
    track_id: UUID | None = None,
    mentor_id: UUID | None = None,
    without_mentor: bool = False,
    is_active: bool | None = None,
    learning_statuses: list[StudentLearningStatus] | None = None,
    sort: MentorStudentSort = MentorStudentSort.NAME_ASC,
    limit: int = 12,
    offset: int = 0,
) -> MentorStudentPage:
    allowed_track_ids = await accessible_track_ids(session, mentor)
    if track_id is not None and track_id not in allowed_track_ids:
        api_error(404, "learning_track_not_found", "Learning track was not found")
    if mentor_id is not None and without_mentor:
        api_error(422, "mentor_filter_conflict", "Choose a mentor or students without a mentor")
    if (mentor_id is not None or without_mentor) and mentor.role is not UserRole.ADMIN:
        api_error(403, "admin_mentor_filter_required", "Only administrators can filter by mentor")

    if mentor.role is UserRole.ADMIN:
        statement = (
            select(User, MentorStudent, StudentMentorshipState)
            .outerjoin(MentorStudent, MentorStudent.student_id == User.id)
            .outerjoin(StudentMentorshipState, StudentMentorshipState.student_id == User.id)
            .where(User.role == UserRole.STUDENT)
        )
    else:
        statement = (
            select(User, MentorStudent, StudentMentorshipState)
            .join(MentorStudent, MentorStudent.student_id == User.id)
            .outerjoin(StudentMentorshipState, StudentMentorshipState.student_id == User.id)
            .where(MentorStudent.mentor_id == mentor.id)
        )

    normalized_query = query.strip() if query else ""
    if normalized_query:
        pattern = f"%{normalized_query}%"
        statement = statement.where(
            or_(
                User.first_name.ilike(pattern),
                User.last_name.ilike(pattern),
                User.email.ilike(pattern),
                User.telegram_username.ilike(pattern),
            )
        )
    if is_active is not None:
        statement = statement.where(User.is_active.is_(is_active))
    if track_id is not None:
        statement = statement.where(
            select(LearningTrackEnrollment.user_id)
            .where(
                LearningTrackEnrollment.user_id == User.id,
                LearningTrackEnrollment.track_id == track_id,
            )
            .exists()
        )
    if mentor_id is not None:
        statement = statement.where(MentorStudent.mentor_id == mentor_id)
    elif without_mentor:
        statement = statement.where(MentorStudent.student_id.is_(None))
    if learning_statuses:
        status_matches = or_(
            StudentMentorshipState.learning_status.in_(learning_statuses),
            and_(
                StudentMentorshipState.student_id.is_(None),
                MentorStudent.learning_status.in_(learning_statuses),
            ),
        )
        if StudentLearningStatus.LEARNING in learning_statuses:
            status_matches = or_(
                status_matches,
                and_(
                    StudentMentorshipState.student_id.is_(None),
                    MentorStudent.student_id.is_(None),
                ),
            )
        statement = statement.where(status_matches)

    total = int(
        await session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
        or 0
    )
    ordering: tuple[Any, ...]
    if sort is MentorStudentSort.LEARNING_START_DESC:
        ordering = (User.learning_start_date.desc().nulls_last(), User.first_name, User.last_name)
    elif sort is MentorStudentSort.LEARNING_START_ASC:
        ordering = (User.learning_start_date.asc().nulls_last(), User.first_name, User.last_name)
    elif sort in {
        MentorStudentSort.LAST_ACTIVITY_DESC,
        MentorStudentSort.LAST_ACTIVITY_ASC,
    }:
        activity_at = _last_activity_sort_expression()
        activity_order = (
            activity_at.desc().nulls_last()
            if sort is MentorStudentSort.LAST_ACTIVITY_DESC
            else activity_at.asc().nulls_first()
        )
        ordering = (activity_order, User.first_name, User.last_name)
    else:
        ordering = (User.first_name, User.last_name)
    rows = (
        await session.execute(statement.order_by(*ordering, User.id).limit(limit).offset(offset))
    ).all()
    directions = list(
        await session.scalars(
            select(LearningTrack)
            .where(
                LearningTrack.id.in_(allowed_track_ids),
                LearningTrack.is_published.is_(True),
            )
            .order_by(LearningTrack.position, LearningTrack.title)
        )
    )
    mentor_options = (
        list(
            await session.scalars(
                select(User)
                .where(User.role.in_(MENTOR_CAPABLE_ROLES))
                .order_by(User.first_name, User.last_name, User.id)
            )
        )
        if mentor.role is UserRole.ADMIN
        else []
    )
    return MentorStudentPage(
        items=await _batch_student_items(
            session,
            [(student, relation, state) for student, relation, state in rows],
            mentor,
        ),
        total=total,
        limit=limit,
        offset=offset,
        directions=[
            MentorStudentDirectionOption(id=item.id, slug=item.slug, title=item.title)
            for item in directions
        ],
        mentors=[
            MentorStudentMentorOption(
                id=item.id,
                role=item.role,
                first_name=item.first_name,
                last_name=item.last_name,
                telegram_username=item.telegram_username,
            )
            for item in mentor_options
        ],
        can_filter_by_mentor=mentor.role is UserRole.ADMIN,
    )


async def _batch_student_items(
    session: AsyncSession,
    user_rows: list[tuple[User, MentorStudent | None, StudentMentorshipState | None]],
    mentor: User,
) -> list[MentorStudentListItem]:
    if not user_rows:
        return []
    student_ids = [student.id for student, _, _ in user_rows]
    now = datetime.now(UTC)
    allowed_track_ids = await accessible_track_ids(session, mentor)
    roadmap_statement = (
        select(
            LearningTrackEnrollment.user_id,
            Roadmap,
            RoadmapEnrollment,
            RoadmapSection,
            Topic,
            TopicProgress,
        )
        .join(LearningTrack, LearningTrack.id == LearningTrackEnrollment.track_id)
        .join(
            LearningTrackRoadmap,
            LearningTrackRoadmap.track_id == LearningTrackEnrollment.track_id,
        )
        .join(Roadmap, Roadmap.id == LearningTrackRoadmap.roadmap_id)
        .outerjoin(
            RoadmapEnrollment,
            and_(
                RoadmapEnrollment.user_id == LearningTrackEnrollment.user_id,
                RoadmapEnrollment.roadmap_id == Roadmap.id,
            ),
        )
        .outerjoin(RoadmapSection, RoadmapSection.roadmap_id == Roadmap.id)
        .outerjoin(
            Topic,
            and_(Topic.section_id == RoadmapSection.id, Topic.is_published.is_(True)),
        )
        .outerjoin(
            TopicProgress,
            and_(
                TopicProgress.user_id == LearningTrackEnrollment.user_id,
                TopicProgress.topic_id == Topic.id,
            ),
        )
        .where(
            LearningTrackEnrollment.user_id.in_(student_ids),
            LearningTrack.is_published.is_(True),
            Roadmap.is_published.is_(True),
            LearningTrackEnrollment.track_id.in_(allowed_track_ids),
        )
        .order_by(
            LearningTrackEnrollment.user_id,
            Roadmap.position,
            RoadmapSection.position,
            Topic.position,
        )
    )
    roadmap_rows = (await session.execute(roadmap_statement)).all()
    roadmap_data: dict[UUID, dict[UUID, dict[str, object]]] = {
        student_id: {} for student_id in student_ids
    }
    for student_id, roadmap, enrollment, section, topic, progress in roadmap_rows:
        item = roadmap_data[student_id].setdefault(
            roadmap.id,
            {"roadmap": roadmap, "enrollment": enrollment, "sections": {}},
        )
        if section is None:
            continue
        sections = cast(dict[UUID, dict[str, object]], item["sections"])
        section_item = sections.setdefault(section.id, {"section": section, "topics": {}})
        if topic is not None:
            topics = cast(dict[UUID, tuple[Topic, TopicProgress | None]], section_item["topics"])
            topics[topic.id] = (topic, progress)

    progress_rows = (
        await session.execute(
            select(
                TopicProgress.user_id,
                func.count(TopicProgress.topic_id).filter(
                    TopicProgress.last_completed_at >= now - timedelta(days=7)
                ),
            )
            .where(TopicProgress.user_id.in_(student_ids))
            .group_by(TopicProgress.user_id)
        )
    ).all()
    weekly_completed_by_student = {
        student_id: int(weekly_completed) for student_id, weekly_completed in progress_rows
    }
    activity = await _student_activity(session, student_ids)
    mock_rows = (
        await session.execute(
            select(MockInterview.student_id, func.count(MockInterview.id))
            .where(
                MockInterview.student_id.in_(student_ids),
                MockInterview.status == MockInterviewStatus.COMPLETED,
            )
            .group_by(MockInterview.student_id)
        )
    ).all()
    mock_counts = {student_id: int(count) for student_id, count in mock_rows}

    result: list[MentorStudentListItem] = []
    for student, relation, state in user_rows:
        summaries: list[StudentRoadmapSummary] = []
        current_topics: list[MentorCurrentTopic] = []
        student_is_overdue = False
        for item in roadmap_data[student.id].values():
            roadmap = cast(Roadmap, item["roadmap"])
            enrollment = cast(RoadmapEnrollment | None, item["enrollment"])
            sections = cast(dict[UUID, dict[str, object]], item["sections"])
            total = 0
            completed = 0
            overdue_sections = 0
            cumulative_days = 0
            for section_item in sections.values():
                section = cast(RoadmapSection, section_item["section"])
                topics = cast(
                    dict[UUID, tuple[Topic, TopicProgress | None]],
                    section_item["topics"],
                )
                cumulative_days += section.duration_days or 0
                deadline = (
                    enrollment.started_at + timedelta(days=cumulative_days)
                    if enrollment is not None
                    and enrollment.started_at is not None
                    and section.duration_days is not None
                    else None
                )
                total += len(topics)
                section_completed = True
                for topic, progress in topics.values():
                    progress_status = progress.status if progress else ProgressStatus.NOT_STARTED
                    if progress_status is ProgressStatus.COMPLETED:
                        completed += 1
                    else:
                        section_completed = False
                    if (
                        progress_status is ProgressStatus.IN_PROGRESS
                        and progress is not None
                        and progress.started_at is not None
                    ):
                        current_topics.append(
                            MentorCurrentTopic(
                                id=topic.id,
                                title=topic.title,
                                section_title=section.title,
                                roadmap_title=roadmap.title,
                                started_at=progress.started_at,
                                days_in_topic=max(0, (now - progress.started_at).days),
                                deadline_at=deadline,
                                is_overdue=deadline is not None and deadline < now,
                            )
                        )
                if deadline is not None and deadline < now and not section_completed:
                    overdue_sections += 1
            student_is_overdue = student_is_overdue or overdue_sections > 0
            summaries.append(
                StudentRoadmapSummary(
                    id=roadmap.id,
                    slug=roadmap.slug,
                    title=roadmap.title,
                    completed_topics=completed,
                    total_topics=total,
                    progress_percent=round(completed / total * 100) if total else 0,
                    started_at=enrollment.started_at if enrollment else None,
                    completed_at=enrollment.completed_at if enrollment else None,
                    overdue_sections=overdue_sections,
                )
            )
        last_progress, last_activity_kind = activity.get(student.id, (None, None))
        result.append(
            MentorStudentListItem(
                id=student.id,
                first_name=student.first_name,
                last_name=student.last_name,
                email=student.email,
                telegram_username=student.telegram_username,
                learning_start_date=student.learning_start_date,
                is_active=student.is_active,
                learning_status=(
                    state.learning_status
                    if state is not None
                    else relation.learning_status
                    if relation is not None
                    else StudentLearningStatus.LEARNING
                ),
                strength_level=(
                    state.strength_level
                    if state is not None
                    else relation.strength_level
                    if relation is not None
                    else None
                ),
                roadmaps=summaries,
                current_topics=current_topics,
                last_progress_at=last_progress,
                last_activity_kind=last_activity_kind,
                completed_topics_this_week=weekly_completed_by_student.get(student.id, 0),
                is_overdue=student_is_overdue,
                mock_interview_count=mock_counts.get(student.id, 0),
            )
        )
    return result


def _file(
    filename: str | None, content_type: str | None, size: int | None
) -> InterviewAttachmentRead | None:
    if filename is None or content_type is None or size is None:
        return None
    return InterviewAttachmentRead(filename=filename, content_type=content_type, size=size)


def _document_read(document: MentorStudentDocument) -> MentorDocumentRead:
    return MentorDocumentRead(
        id=document.id,
        kind=document.kind,
        text_content=document.text_content,
        file=_file(document.filename, document.content_type, document.size),
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def _mock_read(mock: MockInterview, mentor: User) -> MockInterviewRead:
    return MockInterviewRead(
        id=mock.id,
        mentor_name=" ".join(filter(None, (mentor.first_name, mentor.last_name))),
        student_id=mock.student_id,
        scheduled_at=mock.scheduled_at,
        status=mock.status,
        description=mock.description,
        feedback=mock.feedback,
        conducted_at=mock.conducted_at,
        media=_file(mock.media_filename, mock.media_content_type, mock.media_size),
        created_at=mock.created_at,
        updated_at=mock.updated_at,
    )


async def _student_mocks(
    session: AsyncSession, student_id: UUID, viewer: User
) -> list[MockInterviewRead]:
    statement = (
        select(MockInterview, User)
        .join(User, User.id == MockInterview.mentor_id)
        .where(MockInterview.student_id == student_id)
        .order_by(MockInterview.scheduled_at.desc())
    )
    rows = (await session.execute(statement)).all()
    return [_mock_read(mock, mock_mentor) for mock, mock_mentor in rows]


async def _student_documents(
    session: AsyncSession, student_id: UUID, viewer: User
) -> list[MentorDocumentRead]:
    statement = select(MentorStudentDocument).where(MentorStudentDocument.student_id == student_id)
    documents = list(await session.scalars(statement.order_by(MentorStudentDocument.kind)))
    return [_document_read(document) for document in documents]


async def _student_notes(
    session: AsyncSession, student_id: UUID, viewer: User
) -> list[MentorNoteRead]:
    statement = (
        select(MentorStudentNote, User)
        .join(User, User.id == MentorStudentNote.mentor_id)
        .where(MentorStudentNote.student_id == student_id)
        .order_by(MentorStudentNote.created_at.desc())
    )
    if viewer.role is UserRole.MENTOR:
        statement = statement.where(MentorStudentNote.mentor_id == viewer.id)
    rows = (await session.execute(statement)).all()
    return [
        MentorNoteRead(
            id=note.id,
            body=note.body,
            author_name=" ".join(filter(None, (author.first_name, author.last_name))),
            is_own=note.mentor_id == viewer.id,
            created_at=note.created_at,
            updated_at=note.updated_at,
        )
        for note, author in rows
    ]


async def student_detail(
    session: AsyncSession, mentor: User, student_id: UUID
) -> MentorStudentDetail:
    student, relation = await assigned_student(session, mentor, student_id)
    allowed_track_ids = await accessible_track_ids(session, mentor)
    roadmaps = await _roadmap_details(session, student.id, allowed_track_ids)
    state = await session.get(StudentMentorshipState, student.id)
    item = await _student_item(
        session,
        student,
        relation,
        state,
        roadmap_details=roadmaps,
    )
    return MentorStudentDetail(
        **item.model_dump(exclude={"roadmaps"}),
        roadmaps=roadmaps,
        interviews=await list_processes(session, student, None, allowed_track_ids),
        mock_interviews=await _student_mocks(session, student.id, mentor),
        documents=await _student_documents(session, student.id, mentor),
        notes=await _student_notes(session, student.id, mentor),
        status_history=await _student_status_history(session, student.id, relation, state),
    )


async def _student_status_history(
    session: AsyncSession,
    student_id: UUID,
    relation: MentorStudent | None,
    state: StudentMentorshipState | None,
) -> list[MentorStudentStatusPeriod]:
    rows = list(
        await session.scalars(
            select(MentorStudentStatusHistory)
            .where(MentorStudentStatusHistory.student_id == student_id)
            .order_by(MentorStudentStatusHistory.started_at.desc())
        )
    )
    now = datetime.now(UTC)
    if not rows and state is not None:
        learning_status = state.learning_status
        started_at = state.status_updated_at
        return [
            MentorStudentStatusPeriod(
                status=learning_status,
                started_at=started_at,
                ended_at=None,
                days=max(0, (now - started_at).days),
            )
        ]
    if not rows and relation is not None:
        learning_status = relation.learning_status
        started_at = relation.status_updated_at or relation.assigned_at
        return [
            MentorStudentStatusPeriod(
                status=learning_status,
                started_at=started_at,
                ended_at=None,
                days=max(0, (now - started_at).days),
            )
        ]
    return [
        MentorStudentStatusPeriod(
            status=row.status,
            started_at=row.started_at,
            ended_at=row.ended_at,
            days=max(0, ((row.ended_at or now) - row.started_at).days),
        )
        for row in rows
    ]


async def update_student_state(
    session: AsyncSession,
    mentor: User,
    student_id: UUID,
    payload: MentorStudentStateMutation,
) -> MentorStudentDetail:
    student, relation = await assigned_student(session, mentor, student_id, lock=True)
    state = await session.scalar(
        select(StudentMentorshipState)
        .where(StudentMentorshipState.student_id == student_id)
        .with_for_update()
    )
    if state is None:
        state = StudentMentorshipState(
            student_id=student_id,
            learning_status=(
                relation.learning_status if relation else StudentLearningStatus.LEARNING
            ),
            strength_level=relation.strength_level if relation else None,
            status_updated_at=(
                relation.status_updated_at or relation.assigned_at
                if relation is not None
                else student.created_at
            ),
        )
        session.add(state)
        await session.flush()
    status_changed = state.learning_status is not payload.learning_status
    if status_changed:
        now = datetime.now(UTC)
        current_period = await session.scalar(
            select(MentorStudentStatusHistory)
            .where(
                MentorStudentStatusHistory.student_id == student_id,
                MentorStudentStatusHistory.ended_at.is_(None),
            )
            .with_for_update()
        )
        if current_period is not None:
            current_period.ended_at = now
        else:
            session.add(
                MentorStudentStatusHistory(
                    student_id=student_id,
                    status=state.learning_status,
                    started_at=state.status_updated_at,
                    ended_at=now,
                    changed_by_user_id=mentor.id,
                )
            )
        session.add(
            MentorStudentStatusHistory(
                student_id=student_id,
                status=payload.learning_status,
                started_at=now,
                changed_by_user_id=mentor.id,
            )
        )
        state.learning_status = payload.learning_status
        state.status_updated_at = now
    state.strength_level = payload.strength_level
    if relation is not None:
        relation.learning_status = state.learning_status
        relation.strength_level = state.strength_level
        relation.status_updated_at = state.status_updated_at
    if status_changed:
        status_labels = {
            StudentLearningStatus.LEARNING: "учится",
            StudentLearningStatus.INTERVIEWING: "ходит на собеседования",
            StudentLearningStatus.PROBATION: "работает на испытательном сроке",
            StudentLearningStatus.FINISHED: "закончил обучение",
        }
        await notify_student(
            session,
            student_id=student_id,
            actor=mentor,
            event_key=f"student-status:{student_id}:{state.status_updated_at.isoformat()}",
            kind=NotificationKind.STATUS_CHANGED,
            title="Изменён статус обучения",
            body=(
                f"{actor_name(mentor)} перевёл вас в статус "
                f"«{status_labels[payload.learning_status]}»."
            ),
        )
    await session.commit()
    return await student_detail(session, mentor, student_id)


async def create_note(
    session: AsyncSession, mentor: User, student_id: UUID, body: str
) -> MentorNoteRead:
    await assigned_student(session, mentor, student_id, lock=True)
    note = MentorStudentNote(mentor_id=mentor.id, student_id=student_id, body=body)
    session.add(note)
    await session.commit()
    await session.refresh(note)
    return MentorNoteRead(
        id=note.id,
        body=note.body,
        author_name=" ".join(filter(None, (mentor.first_name, mentor.last_name))),
        is_own=True,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


async def delete_note(session: AsyncSession, mentor: User, student_id: UUID, note_id: UUID) -> None:
    await assigned_student(session, mentor, student_id, lock=True)
    statement = select(MentorStudentNote).where(
        MentorStudentNote.id == note_id,
        MentorStudentNote.student_id == student_id,
    )
    if mentor.role is not UserRole.ADMIN:
        statement = statement.where(MentorStudentNote.mentor_id == mentor.id)
    note = await session.scalar(statement)
    if note is None:
        api_error(404, "mentor_note_not_found", "Mentor note was not found")
    await session.delete(note)
    await session.commit()


async def update_note(
    session: AsyncSession,
    mentor: User,
    student_id: UUID,
    note_id: UUID,
    body: str,
) -> MentorNoteRead:
    await assigned_student(session, mentor, student_id, lock=True)
    statement = select(MentorStudentNote).where(
        MentorStudentNote.id == note_id,
        MentorStudentNote.student_id == student_id,
    )
    if mentor.role is not UserRole.ADMIN:
        statement = statement.where(MentorStudentNote.mentor_id == mentor.id)
    note = await session.scalar(statement.with_for_update())
    if note is None:
        api_error(404, "mentor_note_not_found", "Mentor note was not found")
    note.body = body
    await session.commit()
    await session.refresh(note)
    author = await session.get(User, note.mentor_id)
    return MentorNoteRead(
        id=note.id,
        body=note.body,
        author_name=(
            " ".join(filter(None, (author.first_name, author.last_name)))
            if author is not None
            else "Ментор"
        ),
        is_own=note.mentor_id == mentor.id,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


async def get_document(
    session: AsyncSession,
    mentor: User,
    student_id: UUID,
    kind: MentorDocumentKind,
    *,
    lock: bool = False,
) -> MentorStudentDocument | None:
    await assigned_student(session, mentor, student_id, lock=lock)
    statement = select(MentorStudentDocument).where(
        MentorStudentDocument.student_id == student_id,
        MentorStudentDocument.kind == kind,
    )
    if lock:
        statement = statement.with_for_update()
    return cast(MentorStudentDocument | None, await session.scalar(statement))


async def set_document_text(
    session: AsyncSession,
    mentor: User,
    student_id: UUID,
    kind: MentorDocumentKind,
    payload: MentorDocumentContentMutation,
) -> tuple[MentorDocumentRead, str | None]:
    document = await get_document(session, mentor, student_id, kind, lock=True)
    if document is None:
        if not payload.text_content:
            api_error(422, "mentor_document_empty", "Add document text or upload a file")
        document = MentorStudentDocument(
            mentor_id=mentor.id,
            student_id=student_id,
            kind=kind,
            text_content=payload.text_content,
        )
        session.add(document)
        previous_key = None
    else:
        previous_key = document.storage_key if not payload.keep_file else None
        document.mentor_id = mentor.id
        document.text_content = payload.text_content
        if not payload.keep_file:
            document.storage_key = None
            document.filename = None
            document.content_type = None
            document.size = None
        if not document.text_content and not document.storage_key:
            api_error(422, "mentor_document_empty", "Add document text or upload a file")
    await session.flush()
    document_event_at = datetime.now(UTC)
    document_label = "резюме" if kind is MentorDocumentKind.RESUME else "легенду"
    await notify_student(
        session,
        student_id=student_id,
        actor=mentor,
        event_key=f"mentor-document:{document.id}:{document_event_at.isoformat()}",
        kind=NotificationKind.MENTOR_DOCUMENT,
        title="Обновлены материалы от ментора",
        body=f"{actor_name(mentor)} добавил или обновил {document_label}.",
    )
    await session.commit()
    await session.refresh(document)
    return _document_read(document), previous_key


async def set_document_file(
    session: AsyncSession,
    mentor: User,
    student_id: UUID,
    kind: MentorDocumentKind,
    upload: StoredUpload,
) -> tuple[MentorDocumentRead, str | None]:
    document = await get_document(session, mentor, student_id, kind, lock=True)
    if document is None:
        document = MentorStudentDocument(
            mentor_id=mentor.id,
            student_id=student_id,
            kind=kind,
        )
        session.add(document)
    previous_key = document.storage_key
    document.mentor_id = mentor.id
    document.storage_key = upload.storage_key
    document.filename = upload.filename
    document.content_type = upload.content_type
    document.size = upload.size
    try:
        await session.flush()
        await notify_student(
            session,
            student_id=student_id,
            actor=mentor,
            event_key=f"mentor-document-file:{document.id}:{datetime.now(UTC).isoformat()}",
            kind=NotificationKind.MENTOR_DOCUMENT,
            title="Обновлены материалы от ментора",
            body=(
                f"{actor_name(mentor)} загрузил файл: "
                f"{'резюме' if kind is MentorDocumentKind.RESUME else 'легенда'}."
            ),
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await get_document(session, mentor, student_id, kind, lock=True)
        if existing is not None and existing.storage_key == upload.storage_key:
            return _document_read(existing), upload.storage_key
        api_error(
            409,
            "mentor_document_conflict",
            "The mentor document was changed by another request",
        )
    await session.refresh(document)
    return _document_read(document), previous_key


async def create_mock(
    session: AsyncSession,
    mentor: User,
    student_id: UUID,
    payload: MockInterviewMutation,
) -> MockInterviewRead:
    await assigned_student(session, mentor, student_id, lock=True)
    mock = MockInterview(
        mentor_id=mentor.id,
        student_id=student_id,
        scheduled_at=payload.scheduled_at,
        description=payload.description,
    )
    session.add(mock)
    await session.flush()
    await notify_student(
        session,
        student_id=student_id,
        actor=mentor,
        event_key=f"mock-interview-created:{mock.id}",
        kind=NotificationKind.MOCK_INTERVIEW,
        title="Назначено мок-собеседование",
        body=(
            f"{actor_name(mentor)} назначил мок-собеседование на "
            f"{mock.scheduled_at:%d.%m.%Y %H:%M}."
        ),
    )
    await session.commit()
    await session.refresh(mock)
    return _mock_read(mock, mentor)


async def get_mock(
    session: AsyncSession,
    viewer: User,
    mock_id: UUID,
    *,
    student_id: UUID | None = None,
    lock: bool = False,
) -> tuple[MockInterview, User]:
    statement = (
        select(MockInterview, User)
        .join(User, User.id == MockInterview.mentor_id)
        .where(MockInterview.id == mock_id)
    )
    if student_id is not None:
        statement = statement.where(MockInterview.student_id == student_id)
    if viewer.role is UserRole.STUDENT:
        statement = statement.where(MockInterview.student_id == viewer.id)
    elif viewer.role is UserRole.MENTOR:
        statement = statement.where(MockInterview.mentor_id == viewer.id)
    if lock:
        statement = statement.with_for_update()
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        api_error(404, "mock_interview_not_found", "Mock interview was not found")
    return row[0], row[1]


async def complete_mock(
    session: AsyncSession,
    mentor: User,
    student_id: UUID,
    mock_id: UUID,
    payload: MockInterviewFeedbackMutation,
) -> MockInterviewRead:
    await assigned_student(session, mentor, student_id, lock=True)
    mock, mock_mentor = await get_mock(session, mentor, mock_id, student_id=student_id, lock=True)
    mock.feedback = payload.feedback
    mock.conducted_at = payload.conducted_at or datetime.now(UTC)
    mock.status = MockInterviewStatus.COMPLETED
    await notify_student(
        session,
        student_id=student_id,
        actor=mentor,
        event_key=f"mock-interview-feedback:{mock.id}",
        kind=NotificationKind.MOCK_FEEDBACK,
        title="Готов фидбек по мок-собеседованию",
        body=f"{actor_name(mentor)} добавил обратную связь по мок-собеседованию.",
    )
    await session.commit()
    await session.refresh(mock)
    return _mock_read(mock, mock_mentor)


async def set_mock_media(
    session: AsyncSession,
    mentor: User,
    student_id: UUID,
    mock_id: UUID,
    upload: StoredUpload,
) -> tuple[MockInterviewRead, str | None]:
    await assigned_student(session, mentor, student_id, lock=True)
    mock, mock_mentor = await get_mock(session, mentor, mock_id, student_id=student_id, lock=True)
    previous_key = mock.media_storage_key
    mock.media_storage_key = upload.storage_key
    mock.media_filename = upload.filename
    mock.media_content_type = upload.content_type
    mock.media_size = upload.size
    await session.commit()
    await session.refresh(mock)
    return _mock_read(mock, mock_mentor), previous_key


async def student_mock_interviews(session: AsyncSession, student: User) -> list[MockInterviewRead]:
    return await _student_mocks(session, student.id, student)


async def mentor_interview_detail(
    session: AsyncSession,
    mentor: User,
    student_id: UUID,
    process_id: UUID,
) -> MentorInterviewDetail:
    student, _ = await assigned_student(session, mentor, student_id, allow_any_user_for_admin=True)
    process = await process_detail(session, student, process_id)
    if process.track_id not in await accessible_track_ids(session, mentor):
        api_error(404, "interview_process_not_found", "Interview process was not found")
    stage_ids = [stage.id for stage in process.stages]
    comment_rows = (
        (
            await session.execute(
                select(InterviewStageComment, User)
                .outerjoin(User, User.id == InterviewStageComment.user_id)
                .where(InterviewStageComment.stage_id.in_(stage_ids))
                .order_by(InterviewStageComment.created_at)
            )
        ).all()
        if stage_ids
        else []
    )
    comments: dict[UUID, list[InterviewCatalogCommentRead]] = {
        stage_id: [] for stage_id in stage_ids
    }
    for comment, author in comment_rows:
        comments[comment.stage_id].append(
            InterviewCatalogCommentRead(
                id=comment.id,
                author=(
                    InterviewCatalogAuthorRead(
                        id=author.id,
                        name=author.first_name,
                        telegram_username=author.telegram_username,
                    )
                    if author is not None
                    else None
                ),
                body=comment.body,
                is_own=comment.user_id == mentor.id,
                is_mentor_feedback=(
                    author is not None and author.role in {UserRole.MENTOR, UserRole.ADMIN}
                ),
                is_ai_feedback=comment.is_ai_feedback,
                created_at=comment.created_at,
                updated_at=comment.updated_at,
            )
        )
    return MentorInterviewDetail(
        process=process,
        feedback=[
            MentorInterviewStageFeedback(stage_id=stage_id, comments=comments[stage_id])
            for stage_id in stage_ids
        ],
    )


async def add_interview_feedback(
    session: AsyncSession,
    mentor: User,
    student_id: UUID,
    stage_id: UUID,
    body: str,
) -> InterviewCatalogCommentRead:
    await assigned_student(session, mentor, student_id, lock=True)
    stage = await session.scalar(
        select(InterviewProcessStage)
        .join(InterviewProcess, InterviewProcess.id == InterviewProcessStage.process_id)
        .where(
            InterviewProcessStage.id == stage_id,
            InterviewProcess.user_id == student_id,
        )
    )
    if stage is None:
        api_error(404, "interview_stage_not_found", "Interview stage was not found")
    process = await session.get(InterviewProcess, stage.process_id)
    if process is None or process.track_id not in await accessible_track_ids(session, mentor):
        api_error(404, "interview_stage_not_found", "Interview stage was not found")
    comment = InterviewStageComment(stage_id=stage_id, user_id=mentor.id, body=body)
    session.add(comment)
    await session.flush()
    await notify_student(
        session,
        student_id=student_id,
        actor=mentor,
        event_key=f"mentor-interview-feedback:{comment.id}",
        kind=NotificationKind.MENTOR_FEEDBACK,
        title="Новый фидбек по собеседованию",
        body=f"{actor_name(mentor)} оставил обратную связь по этапу собеседования.",
        action_url=f"/interviews/journal/{process.id}",
    )
    await session.commit()
    await session.refresh(comment)
    return InterviewCatalogCommentRead(
        id=comment.id,
        author=InterviewCatalogAuthorRead(
            id=mentor.id,
            name=mentor.first_name,
            telegram_username=mentor.telegram_username,
        ),
        body=comment.body,
        is_own=True,
        is_mentor_feedback=True,
        is_ai_feedback=False,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
    )
