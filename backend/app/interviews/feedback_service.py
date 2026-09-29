"""Read-only coaching trends and explicit student/mentor progress mutations."""

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import api_error
from app.db.models import MentorStudent, User
from app.interviews.feedback_grounding import _effective_summary_rows, ground_communication
from app.interviews.feedback_types import CommunicationSkill
from app.interviews.intelligence_models import (
    IntelligenceAnswer,
    IntelligenceAnswerReview,
    IntelligenceInterview,
    IntelligenceQuestion,
    IntelligenceUtterance,
)
from app.interviews.intelligence_service import _mentor_interview_access, get_intelligence_interview
from app.interviews.models import InterviewProcessStage
from app.users.models import UserRole


def revision_state(interview: IntelligenceInterview) -> dict[str, Any]:
    value = (interview.coaching_state or {}).get(str(interview.analysis_revision), {})
    return value if isinstance(value, dict) else {}


def rejected_skills(interview: IntelligenceInterview) -> set[str]:
    return {
        key
        for key, value in revision_state(interview).items()
        if isinstance(value, dict) and value.get("decision") == "rejected"
    }


async def communication_history(
    session: AsyncSession, user: User, student_id: UUID
) -> dict[str, Any]:
    if user.role is UserRole.STUDENT and user.id != student_id:
        api_error(404, "student_not_found", "Student was not found")
    if user.role is UserRole.MENTOR and not await session.scalar(
        select(MentorStudent.student_id).where(
            MentorStudent.student_id == student_id, MentorStudent.mentor_id == user.id
        )
    ):
        api_error(404, "student_not_found", "Student was not found")
    statement = (
        select(IntelligenceInterview, InterviewProcessStage.scheduled_at)
        .join(InterviewProcessStage, IntelligenceInterview.stage_id == InterviewProcessStage.id)
        .where(
            IntelligenceInterview.student_id == student_id,
            IntelligenceInterview.ai_summary_payload.is_not(None),
        )
        .order_by(InterviewProcessStage.scheduled_at, IntelligenceInterview.id)
    )
    if user.role is UserRole.MENTOR:
        statement = statement.where(_mentor_interview_access(user))
    interviews = (await session.execute(statement)).all()
    ids = [interview.id for interview, _ in interviews]
    if not ids:
        return {"student_id": str(student_id), "observations": []}
    rows = (
        await session.execute(
            select(IntelligenceQuestion, IntelligenceAnswer, IntelligenceAnswerReview)
            .join(IntelligenceAnswer, IntelligenceAnswer.question_id == IntelligenceQuestion.id)
            .join(
                IntelligenceAnswerReview,
                IntelligenceAnswerReview.answer_id == IntelligenceAnswer.id,
            )
            .where(IntelligenceQuestion.interview_id.in_(ids))
            .order_by(
                IntelligenceQuestion.sequence_number, IntelligenceAnswerReview.created_at.desc()
            )
        )
    ).all()
    utterances = list(
        await session.scalars(
            select(IntelligenceUtterance).where(IntelligenceUtterance.interview_id.in_(ids))
        )
    )
    rows_by_interview: dict[UUID, list[Any]] = defaultdict(list)
    utterances_by_interview: dict[UUID, list[Any]] = defaultdict(list)
    for row in rows:
        rows_by_interview[row[0].interview_id].append(row)
    for utterance in utterances:
        utterances_by_interview[utterance.interview_id].append(utterance)
    observations = []
    for interview, date in interviews:
        grounded = ground_communication(
            interview.ai_summary_payload or {},
            _effective_summary_rows(rows_by_interview[interview.id]),
            utterances_by_interview[interview.id],
            rejected_skills=rejected_skills(interview),
        )
        for dimension in grounded["communication_dimensions"]:
            state = revision_state(interview).get(dimension["skill"], {})
            observations.append(
                {
                    **dimension,
                    "interview_id": str(interview.id),
                    "analysis_revision": interview.analysis_revision,
                    "date": date.isoformat(),
                    "interview_type": interview.interview_type.value,
                    "completed_at": state.get("completed_at"),
                    "decision": state.get("decision"),
                }
            )
    return {"student_id": str(student_id), "observations": observations}


async def update_coaching(
    session: AsyncSession,
    user: User,
    interview_id: UUID,
    skill: CommunicationSkill,
    *,
    revision: int,
    action: str,
) -> dict[str, Any]:
    interview = await get_intelligence_interview(session, user, interview_id, lock=True)
    if revision != interview.analysis_revision:
        api_error(409, "stale_analysis", "Разбор обновился. Обнови страницу.")
    decision = action in {"approve", "reject"}
    if decision and user.role not in {UserRole.MENTOR, UserRole.ADMIN}:
        api_error(403, "review_forbidden", "Только ментор или администратор может проверить вывод.")
    if not decision and interview.student_id != user.id:
        api_error(403, "practice_owner_only", "Тренировку отмечает сам ученик.")
    # Reject/restore is possible only for a source-grounded observation in this revision.
    from app.interviews.intelligence_service import intelligence_detail

    detail = await intelligence_detail(session, user, interview_id)
    dimensions = detail.overview.communication_dimensions if detail.overview else []
    previous = revision_state(interview).get(skill.value, {})
    dimension = next((d for d in dimensions if d.skill == skill), None)
    if dimension is None and not (decision and previous.get("decision") == "rejected"):
        api_error(404, "communication_not_found", "Подтверждённое наблюдение не найдено.")
    if not decision and (dimension is None or dimension.exercise is None):
        api_error(404, "exercise_not_found", "Упражнение не найдено.")
    state = dict(interview.coaching_state or {})
    current = dict(revision_state(interview))
    item = dict(current.get(skill.value, {}))
    if decision:
        item.update(
            decision="approved" if action == "approve" else "rejected",
            reviewer_id=str(user.id),
            reviewed_at=datetime.now(UTC).isoformat(),
        )
    else:
        item["completed_at"] = datetime.now(UTC).isoformat() if action == "complete" else None
    current[skill.value] = item
    state[str(revision)] = current
    interview.coaching_state = state
    await session.commit()
    return item
