"""Persist one daily selection per student, balancing exposure across students."""

from datetime import UTC, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import ScalarSelect

from app.interviews.models import (
    Company,
    InterviewProcess,
    RecruiterContact,
    RecruiterContactOpen,
    RecruiterContactProcess,
    RecruiterDailyAssignment,
    RecruiterDailyBatch,
    RecruiterFeedback,
    RecruiterFeedbackKind,
)
from app.interviews.schemas import RecruiterDailyRead
from app.mentors.models import MentorStudent, StudentLearningStatus, StudentMentorshipState
from app.tracks.access import accessible_track_ids
from app.users.models import User

DAILY_LIMIT = 10
DAILY_TIMEZONE = ZoneInfo("Europe/Moscow")
# Short allocation transactions serialize exposure decisions, not page rendering.
ALLOCATION_LOCK = 731_984_021


def select_diverse_contacts(
    ranked: list[tuple[UUID, UUID]], deferred_companies: set[UUID]
) -> list[UUID]:
    """Prefer new companies, then fill gaps; never more than two per company."""
    selected: list[UUID] = []
    selected_ids: set[UUID] = set()
    company_counts: dict[UUID, int] = {}
    for pass_number in range(3):
        for recruiter_id, company_id in ranked:
            if recruiter_id in selected_ids:
                continue
            if pass_number == 0 and company_id in deferred_companies:
                continue
            if company_counts.get(company_id, 0) >= (2 if pass_number == 2 else 1):
                continue
            selected.append(recruiter_id)
            selected_ids.add(recruiter_id)
            company_counts[company_id] = company_counts.get(company_id, 0) + 1
            if len(selected) == DAILY_LIMIT:
                return selected
    return selected


def random_draw() -> ColumnElement[float]:
    return func.greatest(func.random(), 0.000000001)


def daily_now() -> datetime:
    return datetime.now(UTC)


async def is_interviewing(session: AsyncSession, user_id: UUID) -> bool:
    current = await session.scalar(
        select(StudentMentorshipState.learning_status).where(
            StudentMentorshipState.student_id == user_id
        )
    )
    if current is None:
        current = await session.scalar(
            select(MentorStudent.learning_status).where(MentorStudent.student_id == user_id)
        )
    return current is StudentLearningStatus.INTERVIEWING


def known_contact(user_id: UUID) -> ColumnElement[bool]:
    return or_(
        exists(
            select(1)
            .where(
                RecruiterDailyAssignment.user_id == user_id,
                RecruiterDailyAssignment.recruiter_id == RecruiterContact.id,
            )
            .correlate(RecruiterContact)
        ),
        exists(
            select(1)
            .where(
                RecruiterContactOpen.user_id == user_id,
                RecruiterContactOpen.recruiter_id == RecruiterContact.id,
            )
            .correlate(RecruiterContact)
        ),
        exists(
            select(1)
            .where(
                RecruiterFeedback.user_id == user_id,
                RecruiterFeedback.recruiter_id == RecruiterContact.id,
            )
            .correlate(RecruiterContact)
        ),
    )


async def daily_selection(
    session: AsyncSession, user: User, *, generate: bool = True
) -> tuple[list[UUID], RecruiterDailyRead]:
    today = daily_now().astimezone(DAILY_TIMEZONE).date()
    eligible = await is_interviewing(session, user.id)
    if (
        generate
        and eligible
        and today.weekday() < 5
        and await session.get(RecruiterDailyBatch, (user.id, today)) is None
    ):
        await session.execute(select(func.pg_advisory_xact_lock(ALLOCATION_LOCK)))
        today = daily_now().astimezone(DAILY_TIMEZONE).date()
        eligible = await is_interviewing(session, user.id)
        if (
            eligible
            and today.weekday() < 5
            and await session.get(RecruiterDailyBatch, (user.id, today)) is None
        ):
            tracks = await accessible_track_ids(session, user)
            # Use the same canonical company as the unfiltered student directory.
            # Multiple interview processes must not increase a contact's sampling weight.
            contact_companies = (
                select(
                    RecruiterContactProcess.recruiter_id,
                    Company.id.label("company_id"),
                )
                .select_from(RecruiterContactProcess)
                .join(InterviewProcess, InterviewProcess.id == RecruiterContactProcess.process_id)
                .join(Company, Company.id == InterviewProcess.company_id)
                .where(InterviewProcess.track_id.in_(tracks))
                .distinct(RecruiterContactProcess.recruiter_id)
                .order_by(RecruiterContactProcess.recruiter_id, Company.name, Company.id)
                .subquery()
            )
            # An opened/issued contact is not assumed to be ignoring the student.
            # A company returns to the first pass only when all their known contacts
            # have an explicit personal "ignores" mark.
            known_rows = await session.execute(
                select(contact_companies.c.company_id, RecruiterFeedback.kind)
                .select_from(RecruiterContact)
                .join(contact_companies, contact_companies.c.recruiter_id == RecruiterContact.id)
                .outerjoin(
                    RecruiterFeedback,
                    (RecruiterFeedback.recruiter_id == RecruiterContact.id)
                    & (RecruiterFeedback.user_id == user.id),
                )
                .where(known_contact(user.id))
            )
            deferred_companies = {
                company_id
                for company_id, kind in known_rows
                if kind != RecruiterFeedbackKind.IGNORES
            }
            broken = exists(
                select(1).where(
                    RecruiterFeedback.recruiter_id == RecruiterContact.id,
                    RecruiterFeedback.kind.in_(
                        [
                            RecruiterFeedbackKind.ACCOUNT_MISSING,
                            RecruiterFeedbackKind.NO_LONGER_WORKS,
                        ]
                    ),
                )
            )
            exposure = (
                select(func.count())
                .select_from(RecruiterDailyAssignment)
                .where(
                    RecruiterDailyAssignment.recruiter_id == RecruiterContact.id,
                    RecruiterDailyAssignment.day == today,
                )
                .correlate(RecruiterContact)
                .scalar_subquery()
            )

            def votes(kinds: list[RecruiterFeedbackKind]) -> ScalarSelect[int]:
                return (
                    select(func.count())
                    .select_from(RecruiterFeedback)
                    .where(
                        RecruiterFeedback.recruiter_id == RecruiterContact.id,
                        RecruiterFeedback.kind.in_(kinds),
                    )
                    .correlate(RecruiterContact)
                    .scalar_subquery()
                )

            helpful = votes([RecruiterFeedbackKind.HELPFUL])
            invited = votes([RecruiterFeedbackKind.INVITED])
            issues = votes([RecruiterFeedbackKind.IGNORES, RecruiterFeedbackKind.OTHER])
            quality = func.greatest(
                0.1, func.least(5.0, (1.0 + helpful + 3 * invited) / (1.0 + issues))
            )
            # Exponential weighted sampling without replacement. Exposure reduces
            # the weight, while positive evidence increases it; new contacts start neutral.
            priority = -func.ln(random_draw()) * (1.0 + exposure) / quality
            ranked_rows = await session.execute(
                select(RecruiterContact.id, contact_companies.c.company_id)
                .join(contact_companies, contact_companies.c.recruiter_id == RecruiterContact.id)
                .where(
                    ~known_contact(user.id),
                    ~broken,
                )
                .order_by(priority, RecruiterContact.id)
            )
            ids = select_diverse_contacts(
                [(recruiter_id, company_id) for recruiter_id, company_id in ranked_rows],
                deferred_companies,
            )
            session.add(RecruiterDailyBatch(user_id=user.id, day=today))
            await session.flush()
            session.add_all(
                [
                    RecruiterDailyAssignment(
                        user_id=user.id, day=today, recruiter_id=rid, position=i
                    )
                    for i, rid in enumerate(ids, 1)
                ]
            )
        # Also persist an empty batch; refresh cannot top up today's quota.
        await session.commit()
    ids = (
        list(
            await session.scalars(
                select(RecruiterDailyAssignment.recruiter_id)
                .where(
                    RecruiterDailyAssignment.user_id == user.id,
                    RecruiterDailyAssignment.day == today,
                )
                .order_by(RecruiterDailyAssignment.position)
            )
        )
        if eligible and today.weekday() < 5
        else []
    )
    contacted = (
        await session.scalar(
            select(func.count())
            .select_from(RecruiterContactOpen)
            .where(
                RecruiterContactOpen.user_id == user.id, RecruiterContactOpen.recruiter_id.in_(ids)
            )
        )
        if ids
        else 0
    )
    next_day = today + timedelta(days=1)
    while next_day.weekday() >= 5:
        next_day += timedelta(days=1)
    return ids, RecruiterDailyRead(
        eligible=eligible,
        is_workday=today.weekday() < 5,
        day=today,
        resets_at=datetime.combine(today + timedelta(days=1), time.min, DAILY_TIMEZONE),
        next_batch_at=datetime.combine(next_day, time.min, DAILY_TIMEZONE),
        assigned_count=len(ids),
        contacted_count=int(contacted or 0),
        daily_limit=DAILY_LIMIT,
    )
