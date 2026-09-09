"""One policy for browser downloads, desktop grants and Copilot API access."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import api_error
from app.mentors.models import MentorStudent, StudentLearningStatus, StudentMentorshipState
from app.users.models import User, UserRole


async def eligibility(session: AsyncSession, user: User) -> dict[str, object]:
    state = await session.get(StudentMentorshipState, user.id)
    status = (
        state.learning_status
        if state
        else await session.scalar(
            select(MentorStudent.learning_status)
            .where(MentorStudent.student_id == user.id)
            .order_by(MentorStudent.assigned_at.desc())
            .limit(1)
        )
    )
    enabled = get_settings().copilot_students_enabled
    student_allowed = (
        user.role is UserRole.STUDENT
        and user.is_active
        and enabled
        and status is StudentLearningStatus.INTERVIEWING
    )
    admin_allowed = user.role is UserRole.ADMIN and user.is_active
    return {
        "allowed": admin_allowed or student_allowed,
        "student_allowed": student_allowed,
        "learning_status": status.value if status else "learning",
        "students_enabled": enabled,
        "reason": ""
        if student_allowed or admin_allowed
        else (
            "Copilot пока закрыт для учеников."
            if not enabled
            else "Copilot доступен ученикам со статусом «Ходит на собеседования»."
        ),
    }


async def ensure_copilot_user(session: AsyncSession, user: User) -> None:
    access = await eligibility(session, user)
    if not access["allowed"]:
        api_error(403, "copilot_access_denied", str(access["reason"]))
