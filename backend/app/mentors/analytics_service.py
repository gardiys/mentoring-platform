from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.errors import api_error
from app.interviews.intelligence_models import (
    IntelligenceInterview,
    IntelligenceProcessingStatus,
)
from app.interviews.models import (
    InterviewProcess,
    InterviewProcessStage,
    InterviewProcessStatus,
    InterviewStageType,
)
from app.mentors.models import MentorStudent, StudentLearningStatus
from app.mentors.schemas import (
    MentorAnalyticsPeriod,
    MentorInterviewAnalytics,
    MentorInterviewRankingItem,
    MentorInterviewStageCount,
)
from app.tracks.access import accessible_track_ids
from app.tracks.models import LearningTrackEnrollment
from app.users.models import User, UserRole


def _period_start(period: MentorAnalyticsPeriod, now: datetime) -> datetime | None:
    if period is MentorAnalyticsPeriod.WEEK:
        return now - timedelta(days=7)
    if period is MentorAnalyticsPeriod.MONTH:
        return now - timedelta(days=30)
    return None


def _in_period(
    column: Any,
    start: datetime | None,
    end: datetime,
) -> list[ColumnElement[bool]]:
    conditions = [column.is_not(None), column <= end]
    if start is not None:
        conditions.append(column >= start)
    return conditions


async def interview_analytics(
    session: AsyncSession,
    viewer: User,
    *,
    period: MentorAnalyticsPeriod,
    track_id: UUID | None = None,
    mentor_id: UUID | None = None,
    without_mentor: bool = False,
    is_active: bool | None = None,
    learning_statuses: list[StudentLearningStatus] | None = None,
) -> MentorInterviewAnalytics:
    allowed_track_ids = await accessible_track_ids(session, viewer)
    if track_id is not None and track_id not in allowed_track_ids:
        api_error(404, "learning_track_not_found", "Learning track was not found")
    if mentor_id is not None and without_mentor:
        api_error(422, "mentor_filter_conflict", "Choose a mentor or students without a mentor")
    if (mentor_id is not None or without_mentor) and viewer.role is not UserRole.ADMIN:
        api_error(403, "admin_mentor_filter_required", "Only administrators can filter by mentor")

    if viewer.role is UserRole.ADMIN:
        students_statement = (
            select(User, MentorStudent)
            .outerjoin(MentorStudent, MentorStudent.student_id == User.id)
            .where(User.role == UserRole.STUDENT)
        )
    else:
        students_statement = (
            select(User, MentorStudent)
            .join(MentorStudent, MentorStudent.student_id == User.id)
            .where(MentorStudent.mentor_id == viewer.id)
        )
    if is_active is not None:
        students_statement = students_statement.where(User.is_active.is_(is_active))
    if track_id is not None:
        students_statement = students_statement.where(
            select(LearningTrackEnrollment.user_id)
            .where(
                LearningTrackEnrollment.user_id == User.id,
                LearningTrackEnrollment.track_id == track_id,
            )
            .exists()
        )
    if mentor_id is not None:
        students_statement = students_statement.where(MentorStudent.mentor_id == mentor_id)
    elif without_mentor:
        students_statement = students_statement.where(MentorStudent.student_id.is_(None))
    if learning_statuses:
        if viewer.role is UserRole.ADMIN and StudentLearningStatus.LEARNING in learning_statuses:
            students_statement = students_statement.where(
                or_(
                    MentorStudent.learning_status.in_(learning_statuses),
                    MentorStudent.student_id.is_(None),
                )
            )
        else:
            students_statement = students_statement.where(
                MentorStudent.learning_status.in_(learning_statuses)
            )

    student_rows = (await session.execute(students_statement)).all()
    students = {student.id: student for student, _ in student_rows}
    student_ids = list(students)
    current_interviewing = sum(
        1
        for _, relation in student_rows
        if relation is not None and relation.learning_status is StudentLearningStatus.INTERVIEWING
    )
    now = datetime.now(UTC)
    start = _period_start(period, now)
    empty = MentorInterviewAnalytics(
        period=period,
        period_start=start,
        period_end=now,
        selected_student_count=0,
        current_interviewing_students=0,
        students_with_interviews=0,
        students_without_interviews=0,
        total_interviews=0,
        unique_companies=0,
        active_processes=0,
        offers_received=0,
        ai_analyses_started=0,
        ai_analyses_ready=0,
        ai_analyses_failed=0,
        interviews_with_recording=0,
        upcoming_interviews_next_week=0,
        average_interviews_per_participant=0,
        offer_conversion_percent=0,
        ai_success_rate_percent=0,
        recording_coverage_percent=0,
        stage_counts=[
            MentorInterviewStageCount(stage_type=stage_type, count=0)
            for stage_type in InterviewStageType
        ],
        ranking=[],
    )
    if not student_ids:
        return empty

    interview_track_ids = {track_id} if track_id is not None else allowed_track_ids
    stage_conditions = [
        InterviewProcess.user_id.in_(student_ids),
        InterviewProcess.track_id.in_(interview_track_ids),
        *_in_period(InterviewProcessStage.scheduled_at, start, now),
    ]
    stage_count_rows = (
        await session.execute(
            select(
                InterviewProcessStage.stage_type,
                func.count(InterviewProcessStage.id),
            )
            .join(InterviewProcess, InterviewProcess.id == InterviewProcessStage.process_id)
            .where(*stage_conditions)
            .group_by(InterviewProcessStage.stage_type)
        )
    ).all()
    stage_count_map = {stage_type: int(count) for stage_type, count in stage_count_rows}
    total_interviews = sum(stage_count_map.values())

    ranking_rows = (
        await session.execute(
            select(
                InterviewProcess.user_id,
                func.count(InterviewProcessStage.id),
                func.count(func.distinct(InterviewProcess.company_id)),
                func.max(InterviewProcessStage.scheduled_at),
            )
            .join(InterviewProcessStage, InterviewProcessStage.process_id == InterviewProcess.id)
            .where(*stage_conditions)
            .group_by(InterviewProcess.user_id)
        )
    ).all()
    students_with_interviews = len(ranking_rows)

    period_process_ids = select(InterviewProcessStage.process_id).where(
        *_in_period(InterviewProcessStage.scheduled_at, start, now)
    )
    process_count = int(
        await session.scalar(
            select(func.count(func.distinct(InterviewProcess.id))).where(
                InterviewProcess.user_id.in_(student_ids),
                InterviewProcess.track_id.in_(interview_track_ids),
                InterviewProcess.id.in_(period_process_ids),
            )
        )
        or 0
    )
    unique_companies = int(
        await session.scalar(
            select(func.count(func.distinct(InterviewProcess.company_id))).where(
                InterviewProcess.user_id.in_(student_ids),
                InterviewProcess.track_id.in_(interview_track_ids),
                InterviewProcess.id.in_(period_process_ids),
            )
        )
        or 0
    )
    active_processes = int(
        await session.scalar(
            select(func.count(InterviewProcess.id)).where(
                InterviewProcess.user_id.in_(student_ids),
                InterviewProcess.track_id.in_(interview_track_ids),
                InterviewProcess.status == InterviewProcessStatus.ACTIVE,
            )
        )
        or 0
    )
    offer_conditions = [
        InterviewProcess.user_id.in_(student_ids),
        InterviewProcess.track_id.in_(interview_track_ids),
        InterviewProcess.status == InterviewProcessStatus.OFFER,
        *_in_period(InterviewProcess.offer_received_at, start, now),
    ]
    offer_rows = (
        await session.execute(
            select(InterviewProcess.user_id, func.count(InterviewProcess.id))
            .where(*offer_conditions)
            .group_by(InterviewProcess.user_id)
        )
    ).all()
    offers_by_student = {student_id: int(count) for student_id, count in offer_rows}
    offers_received = sum(offers_by_student.values())
    period_process_offers = int(
        await session.scalar(
            select(func.count(InterviewProcess.id)).where(
                *offer_conditions,
                InterviewProcess.id.in_(period_process_ids),
            )
        )
        or 0
    )

    ai_conditions = [
        InterviewProcess.user_id.in_(student_ids),
        InterviewProcess.track_id.in_(interview_track_ids),
        *_in_period(InterviewProcessStage.ai_analysis_requested_at, start, now),
    ]
    ai_rows = (
        await session.execute(
            select(InterviewProcess.user_id, func.count(InterviewProcessStage.id))
            .join(InterviewProcessStage, InterviewProcessStage.process_id == InterviewProcess.id)
            .where(*ai_conditions)
            .group_by(InterviewProcess.user_id)
        )
    ).all()
    ai_by_student = {student_id: int(count) for student_id, count in ai_rows}
    ai_started = sum(ai_by_student.values())
    ai_status_rows = (
        await session.execute(
            select(IntelligenceInterview.processing_status, func.count(IntelligenceInterview.id))
            .join(
                InterviewProcessStage,
                InterviewProcessStage.id == IntelligenceInterview.stage_id,
            )
            .join(InterviewProcess, InterviewProcess.id == InterviewProcessStage.process_id)
            .where(*ai_conditions)
            .group_by(IntelligenceInterview.processing_status)
        )
    ).all()
    ai_status_counts = {status: int(count) for status, count in ai_status_rows}
    ai_ready = ai_status_counts.get(IntelligenceProcessingStatus.READY, 0)
    ai_failed = ai_status_counts.get(IntelligenceProcessingStatus.FAILED, 0)

    recordings = int(
        await session.scalar(
            select(func.count(InterviewProcessStage.id))
            .join(InterviewProcess, InterviewProcess.id == InterviewProcessStage.process_id)
            .where(*stage_conditions, InterviewProcessStage.media_storage_key.is_not(None))
        )
        or 0
    )
    upcoming = int(
        await session.scalar(
            select(func.count(InterviewProcessStage.id))
            .join(InterviewProcess, InterviewProcess.id == InterviewProcessStage.process_id)
            .where(
                InterviewProcess.user_id.in_(student_ids),
                InterviewProcess.track_id.in_(interview_track_ids),
                InterviewProcess.status == InterviewProcessStatus.ACTIVE,
                InterviewProcessStage.scheduled_at > now,
                InterviewProcessStage.scheduled_at <= now + timedelta(days=7),
            )
        )
        or 0
    )

    ranked = sorted(
        ranking_rows,
        key=lambda row: (int(row[1]), row[3] or datetime.min.replace(tzinfo=UTC)),
        reverse=True,
    )
    ranking = [
        MentorInterviewRankingItem(
            position=position,
            student_id=student_id,
            first_name=students[student_id].first_name,
            last_name=students[student_id].last_name,
            telegram_username=students[student_id].telegram_username,
            interview_count=int(interview_count),
            company_count=int(company_count),
            offer_count=offers_by_student.get(student_id, 0),
            ai_analysis_count=ai_by_student.get(student_id, 0),
            last_interview_at=last_interview_at,
        )
        for position, (student_id, interview_count, company_count, last_interview_at) in enumerate(
            ranked, start=1
        )
    ]
    completed_ai = ai_ready + ai_failed
    return MentorInterviewAnalytics(
        period=period,
        period_start=start,
        period_end=now,
        selected_student_count=len(student_ids),
        current_interviewing_students=current_interviewing,
        students_with_interviews=students_with_interviews,
        students_without_interviews=len(student_ids) - students_with_interviews,
        total_interviews=total_interviews,
        unique_companies=unique_companies,
        active_processes=active_processes,
        offers_received=offers_received,
        ai_analyses_started=ai_started,
        ai_analyses_ready=ai_ready,
        ai_analyses_failed=ai_failed,
        interviews_with_recording=recordings,
        upcoming_interviews_next_week=upcoming,
        average_interviews_per_participant=(
            round(total_interviews / students_with_interviews, 1) if students_with_interviews else 0
        ),
        offer_conversion_percent=(
            round(period_process_offers / process_count * 100, 1) if process_count else 0
        ),
        ai_success_rate_percent=(round(ai_ready / completed_ai * 100, 1) if completed_ai else 0),
        recording_coverage_percent=(
            round(recordings / total_interviews * 100, 1) if total_interviews else 0
        ),
        stage_counts=[
            MentorInterviewStageCount(
                stage_type=stage_type,
                count=stage_count_map.get(stage_type, 0),
            )
            for stage_type in InterviewStageType
        ],
        ranking=ranking,
    )
