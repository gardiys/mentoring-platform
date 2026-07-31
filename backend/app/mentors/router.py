from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import MentorUser
from app.core.errors import api_error
from app.db.session import get_db_session
from app.mentors.models import MentorStudent
from app.mentors.schemas import (
    MentorStudentDetail,
    MentorStudentListItem,
    StudentRoadmapSummary,
)
from app.progress.models import TopicProgress
from app.progress.service import get_progress_counts
from app.roadmaps.models import Roadmap, RoadmapEnrollment
from app.roadmaps.queries import build_roadmap_detail, get_roadmap_model, has_roadmap_access
from app.tracks.models import LearningTrack, LearningTrackEnrollment, LearningTrackRoadmap
from app.users.models import User, UserRole

router = APIRouter(prefix="/mentor", tags=["mentor"])
Session = Annotated[AsyncSession, Depends(get_db_session)]


async def _student_ids(session: AsyncSession, mentor: User) -> list[UUID]:
    if mentor.role is UserRole.ADMIN:
        return list(await session.scalars(select(User.id).where(User.role == UserRole.STUDENT)))
    return list(
        await session.scalars(
            select(MentorStudent.student_id).where(MentorStudent.mentor_id == mentor.id)
        )
    )


async def _student_roadmaps(session: AsyncSession, student_id: UUID) -> list[StudentRoadmapSummary]:
    rows = (
        await session.execute(
            select(RoadmapEnrollment, Roadmap)
            .join(Roadmap, Roadmap.id == RoadmapEnrollment.roadmap_id)
            .join(LearningTrackRoadmap, LearningTrackRoadmap.roadmap_id == Roadmap.id)
            .join(
                LearningTrackEnrollment,
                LearningTrackEnrollment.track_id == LearningTrackRoadmap.track_id,
            )
            .join(LearningTrack, LearningTrack.id == LearningTrackRoadmap.track_id)
            .where(
                RoadmapEnrollment.user_id == student_id,
                LearningTrackEnrollment.user_id == student_id,
                LearningTrack.is_published.is_(True),
                Roadmap.is_published.is_(True),
            )
            .distinct()
            .order_by(Roadmap.position)
        )
    ).all()
    result: list[StudentRoadmapSummary] = []
    for enrollment, roadmap in rows:
        counts = await get_progress_counts(session, student_id, roadmap.id)
        result.append(
            StudentRoadmapSummary(
                id=roadmap.id,
                slug=roadmap.slug,
                title=roadmap.title,
                completed_topics=counts.completed,
                total_topics=counts.total,
                progress_percent=counts.percent,
                started_at=enrollment.started_at,
                completed_at=enrollment.completed_at,
            )
        )
    return result


@router.get("/students", response_model=list[MentorStudentListItem])
async def students(session: Session, mentor: MentorUser) -> list[MentorStudentListItem]:
    ids = await _student_ids(session, mentor)
    if not ids:
        return []
    users = (
        await session.scalars(select(User).where(User.id.in_(ids)).order_by(User.first_name))
    ).all()
    result: list[MentorStudentListItem] = []
    for student in users:
        last_progress_at = await session.scalar(
            select(func.max(TopicProgress.updated_at)).where(TopicProgress.user_id == student.id)
        )
        result.append(
            MentorStudentListItem(
                id=student.id,
                first_name=student.first_name,
                last_name=student.last_name,
                email=student.email,
                roadmaps=await _student_roadmaps(session, student.id),
                last_progress_at=last_progress_at,
            )
        )
    return result


@router.get("/students/{student_id}", response_model=MentorStudentDetail)
async def student_detail(
    student_id: UUID, session: Session, mentor: MentorUser
) -> MentorStudentDetail:
    student = await session.get(User, student_id)
    if student is None or student.role is not UserRole.STUDENT:
        api_error(404, "student_not_found", "Student was not found")
    allowed_ids = await _student_ids(session, mentor)
    if student_id not in allowed_ids:
        api_error(
            403,
            "student_not_assigned_to_mentor",
            "Student is not assigned to this mentor",
        )

    enrollments = (
        await session.scalars(
            select(RoadmapEnrollment)
            .where(RoadmapEnrollment.user_id == student_id)
            .order_by(RoadmapEnrollment.started_at)
        )
    ).all()
    roadmaps = []
    for enrollment in enrollments:
        roadmap = await session.get(Roadmap, enrollment.roadmap_id)
        if roadmap is None or not roadmap.is_published:
            continue
        if not await has_roadmap_access(session, student_id, roadmap.id):
            continue
        loaded = await get_roadmap_model(session, roadmap.slug)
        if loaded is not None:
            roadmaps.append(await build_roadmap_detail(session, loaded, student_id))
    return MentorStudentDetail(
        id=student.id,
        first_name=student.first_name,
        last_name=student.last_name,
        email=student.email,
        roadmaps=roadmaps,
    )
