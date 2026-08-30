from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, distinct, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.errors import api_error
from app.interviews.companies import suggest_companies
from app.interviews.models import (
    Company,
    InterviewProcess,
    RecruiterContact,
    RecruiterContactOpen,
    RecruiterContactProcess,
    RecruiterFeedback,
    RecruiterFeedbackKind,
)
from app.interviews.schemas import (
    RecruiterCompanyGroupRead,
    RecruiterContactCompanyRead,
    RecruiterContactOpenRead,
    RecruiterContactPage,
    RecruiterContactRead,
    RecruiterContactTrackRead,
    RecruiterFeedbackMutation,
    RecruiterFeedbackRead,
    RecruiterIssueCommentRead,
    RecruiterSort,
)
from app.tracks.access import accessible_track_ids
from app.tracks.models import LearningTrack
from app.users.models import User, UserRole
from app.users.privacy import HIDDEN_STUDENT_NAME


async def sync_process_recruiters(
    session: AsyncSession, process: InterviewProcess, usernames: list[str]
) -> None:
    normalized = list(dict.fromkeys(username.casefold() for username in usernames))
    if normalized:
        await session.execute(
            insert(RecruiterContact)
            .values(
                [
                    {
                        "telegram_username": username,
                        "normalized_username": username,
                    }
                    for username in normalized
                ]
            )
            .on_conflict_do_nothing(index_elements=[RecruiterContact.normalized_username])
        )
        contacts = list(
            await session.scalars(
                select(RecruiterContact).where(RecruiterContact.normalized_username.in_(normalized))
            )
        )
        recruiter_ids = [contact.id for contact in contacts]
        await session.execute(
            insert(RecruiterContactProcess)
            .values(
                [
                    {"recruiter_id": recruiter_id, "process_id": process.id}
                    for recruiter_id in recruiter_ids
                ]
            )
            .on_conflict_do_nothing()
        )
        await session.execute(
            delete(RecruiterContactProcess).where(
                RecruiterContactProcess.process_id == process.id,
                RecruiterContactProcess.recruiter_id.not_in(recruiter_ids),
            )
        )
    else:
        await session.execute(
            delete(RecruiterContactProcess).where(RecruiterContactProcess.process_id == process.id)
        )


async def _track_ids(session: AsyncSession, user: User, track_id: UUID | None) -> set[UUID]:
    allowed = await accessible_track_ids(session, user)
    if track_id is not None:
        return {track_id} if track_id in allowed else set()
    return allowed


def _accessible_contact_filter(track_ids: set[UUID]) -> ColumnElement[bool]:
    return exists(
        select(1)
        .select_from(RecruiterContactProcess)
        .join(InterviewProcess, InterviewProcess.id == RecruiterContactProcess.process_id)
        .where(
            RecruiterContactProcess.recruiter_id == RecruiterContact.id,
            InterviewProcess.track_id.in_(track_ids),
        )
    )


async def list_recruiters(
    session: AsyncSession,
    user: User,
    *,
    query: str | None,
    track_id: UUID | None,
    contacted: bool | None,
    sort: RecruiterSort,
    limit: int,
    offset: int,
) -> RecruiterContactPage:
    track_ids = await _track_ids(session, user, track_id)
    if not track_ids:
        return RecruiterContactPage(items=[], total=0, limit=limit, offset=offset)

    pair_statement = (
        select(
            Company.id.label("company_id"),
            RecruiterContact.id.label("recruiter_id"),
        )
        .select_from(Company)
        .join(InterviewProcess, InterviewProcess.company_id == Company.id)
        .join(
            RecruiterContactProcess,
            RecruiterContactProcess.process_id == InterviewProcess.id,
        )
        .join(
            RecruiterContact,
            RecruiterContact.id == RecruiterContactProcess.recruiter_id,
        )
        .where(InterviewProcess.track_id.in_(track_ids))
    )
    if query and query.strip():
        matched_company_ids = [
            company.id for company in await suggest_companies(session, query, 100)
        ]
        escaped = (
            query.strip()
            .lstrip("@")
            .casefold()
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        pair_statement = pair_statement.where(
            or_(
                RecruiterContact.normalized_username.ilike(f"%{escaped}%", escape="\\"),
                Company.name.ilike(f"%{escaped}%", escape="\\"),
                Company.id.in_(matched_company_ids),
            )
        )
    own_contact_exists = exists(
        select(1)
        .select_from(RecruiterContactOpen)
        .where(
            RecruiterContactOpen.recruiter_id == RecruiterContact.id,
            RecruiterContactOpen.user_id == user.id,
        )
    )
    if contacted is not None:
        pair_statement = pair_statement.where(
            own_contact_exists if contacted else ~own_contact_exists
        )

    eligible_pairs = pair_statement.distinct().subquery()
    helpful_score = (
        select(func.count(RecruiterFeedback.user_id))
        .where(
            RecruiterFeedback.recruiter_id == RecruiterContact.id,
            RecruiterFeedback.kind == RecruiterFeedbackKind.HELPFUL,
        )
        .correlate(RecruiterContact)
        .scalar_subquery()
    )
    issue_score = (
        select(func.count(RecruiterFeedback.user_id))
        .where(
            RecruiterFeedback.recruiter_id == RecruiterContact.id,
            RecruiterFeedback.kind != RecruiterFeedbackKind.HELPFUL,
        )
        .correlate(RecruiterContact)
        .scalar_subquery()
    )
    total_open_score = (
        select(func.count(RecruiterContactOpen.user_id))
        .where(RecruiterContactOpen.recruiter_id == RecruiterContact.id)
        .correlate(RecruiterContact)
        .scalar_subquery()
    )
    last_contact_score = (
        select(func.max(RecruiterContactOpen.last_opened_at))
        .where(RecruiterContactOpen.recruiter_id == RecruiterContact.id)
        .correlate(RecruiterContact)
        .scalar_subquery()
    )
    recommended_score = helpful_score - issue_score

    company_statement = (
        select(Company)
        .join(eligible_pairs, eligible_pairs.c.company_id == Company.id)
        .join(
            RecruiterContact,
            RecruiterContact.id == eligible_pairs.c.recruiter_id,
        )
        .group_by(Company.id)
    )
    if sort is RecruiterSort.RECOMMENDED:
        company_statement = company_statement.order_by(
            func.max(recommended_score).desc(),
            func.max(helpful_score).desc(),
            Company.name,
        )
    elif sort is RecruiterSort.MOST_HELPFUL:
        company_statement = company_statement.order_by(func.max(helpful_score).desc(), Company.name)
    elif sort is RecruiterSort.MOST_CONTACTED:
        company_statement = company_statement.order_by(
            func.max(total_open_score).desc(), Company.name
        )
    elif sort is RecruiterSort.RECENTLY_CONTACTED:
        company_statement = company_statement.order_by(
            func.max(last_contact_score).desc().nullslast(), Company.name
        )
    else:
        company_statement = company_statement.order_by(Company.name)

    total = int(
        await session.scalar(
            select(func.count()).select_from(company_statement.order_by(None).subquery())
        )
        or 0
    )
    selected_companies = list(await session.scalars(company_statement.limit(limit).offset(offset)))
    if not selected_companies:
        return RecruiterContactPage(items=[], total=total, limit=limit, offset=offset)
    selected_company_ids = [company.id for company in selected_companies]

    contact_statement = (
        select(eligible_pairs.c.company_id, RecruiterContact)
        .join(
            RecruiterContact,
            RecruiterContact.id == eligible_pairs.c.recruiter_id,
        )
        .where(eligible_pairs.c.company_id.in_(selected_company_ids))
    )
    if sort is RecruiterSort.RECOMMENDED:
        contact_statement = contact_statement.order_by(
            eligible_pairs.c.company_id,
            recommended_score.desc(),
            helpful_score.desc(),
            total_open_score.desc(),
            RecruiterContact.normalized_username,
        )
    elif sort is RecruiterSort.MOST_HELPFUL:
        contact_statement = contact_statement.order_by(
            eligible_pairs.c.company_id,
            helpful_score.desc(),
            RecruiterContact.normalized_username,
        )
    elif sort is RecruiterSort.MOST_CONTACTED:
        contact_statement = contact_statement.order_by(
            eligible_pairs.c.company_id,
            total_open_score.desc(),
            RecruiterContact.normalized_username,
        )
    elif sort is RecruiterSort.RECENTLY_CONTACTED:
        contact_statement = contact_statement.order_by(
            eligible_pairs.c.company_id,
            last_contact_score.desc().nullslast(),
            RecruiterContact.normalized_username,
        )
    else:
        contact_statement = contact_statement.order_by(
            eligible_pairs.c.company_id, RecruiterContact.normalized_username
        )
    contact_rows = (await session.execute(contact_statement)).all()
    contacts = {contact.id: contact for _, contact in contact_rows}
    ids = list(contacts)

    association_rows = (
        await session.execute(
            select(RecruiterContactProcess.recruiter_id, Company, LearningTrack)
            .join(InterviewProcess, InterviewProcess.id == RecruiterContactProcess.process_id)
            .join(Company, Company.id == InterviewProcess.company_id)
            .join(LearningTrack, LearningTrack.id == InterviewProcess.track_id)
            .where(
                RecruiterContactProcess.recruiter_id.in_(ids),
                InterviewProcess.track_id.in_(track_ids),
            )
            .distinct()
            .order_by(Company.name, LearningTrack.position, LearningTrack.title)
        )
    ).all()
    companies: dict[UUID, dict[UUID, Company]] = defaultdict(dict)
    tracks: dict[UUID, dict[UUID, LearningTrack]] = defaultdict(dict)
    for recruiter_id, company, track in association_rows:
        companies[recruiter_id][company.id] = company
        tracks[recruiter_id][track.id] = track

    open_rows = (
        await session.execute(
            select(
                RecruiterContactOpen.recruiter_id,
                func.count(RecruiterContactOpen.user_id),
                func.count(distinct(RecruiterContactOpen.user_id)).filter(
                    User.role == UserRole.STUDENT
                ),
                func.max(RecruiterContactOpen.last_opened_at),
            )
            .join(User, User.id == RecruiterContactOpen.user_id)
            .where(RecruiterContactOpen.recruiter_id.in_(ids))
            .group_by(RecruiterContactOpen.recruiter_id)
        )
    ).all()
    open_stats = {row[0]: row[1:] for row in open_rows}
    own_opens = {
        contact_open.recruiter_id: contact_open
        for contact_open in await session.scalars(
            select(RecruiterContactOpen).where(
                RecruiterContactOpen.recruiter_id.in_(ids),
                RecruiterContactOpen.user_id == user.id,
            )
        )
    }

    feedback_rows = (
        await session.execute(
            select(
                RecruiterFeedback.recruiter_id,
                RecruiterFeedback.kind,
                func.count(RecruiterFeedback.user_id),
            )
            .where(RecruiterFeedback.recruiter_id.in_(ids))
            .group_by(RecruiterFeedback.recruiter_id, RecruiterFeedback.kind)
        )
    ).all()
    feedback_counts: dict[UUID, dict[RecruiterFeedbackKind, int]] = defaultdict(dict)
    for recruiter_id, kind, count in feedback_rows:
        feedback_counts[recruiter_id][kind] = count
    comment_rows = (
        await session.execute(
            select(
                RecruiterFeedback.recruiter_id,
                RecruiterFeedback.kind,
                RecruiterFeedback.reason,
                RecruiterFeedback.updated_at,
                User.id,
                User.first_name,
                User.telegram_username,
                User.role,
                User.public_identity_hidden_at,
                User.personal_data_erased_at,
            )
            .join(User, User.id == RecruiterFeedback.user_id)
            .where(
                RecruiterFeedback.recruiter_id.in_(ids),
                RecruiterFeedback.kind != RecruiterFeedbackKind.HELPFUL,
                RecruiterFeedback.reason.is_not(None),
                func.length(func.trim(RecruiterFeedback.reason)) > 0,
            )
            .order_by(
                RecruiterFeedback.recruiter_id,
                RecruiterFeedback.updated_at.desc(),
            )
        )
    ).all()
    issue_comments: dict[UUID, list[RecruiterIssueCommentRead]] = defaultdict(list)
    issue_comment_totals: dict[UUID, int] = defaultdict(int)
    for (
        recruiter_id,
        kind,
        reason,
        updated_at,
        author_id,
        author_first_name,
        author_telegram_username,
        author_role,
        public_identity_hidden_at,
        personal_data_erased_at,
    ) in comment_rows:
        hide_author = (
            (public_identity_hidden_at is not None or personal_data_erased_at is not None)
            and user.role is not UserRole.ADMIN
            and user.id != author_id
        )
        issue_comment_totals[recruiter_id] += 1
        if len(issue_comments[recruiter_id]) < 5:
            issue_comments[recruiter_id].append(
                RecruiterIssueCommentRead(
                    author_id=author_id,
                    author_first_name=(HIDDEN_STUDENT_NAME if hide_author else author_first_name),
                    author_telegram_username=(None if hide_author else author_telegram_username),
                    author_role=author_role,
                    kind=kind,
                    reason=reason,
                    updated_at=updated_at,
                )
            )
    own_feedback = {
        feedback.recruiter_id: feedback
        for feedback in await session.scalars(
            select(RecruiterFeedback).where(
                RecruiterFeedback.recruiter_id.in_(ids),
                RecruiterFeedback.user_id == user.id,
            )
        )
    }

    contact_reads: dict[UUID, RecruiterContactRead] = {}
    for contact in contacts.values():
        total_opens, student_count, last_contacted_at = open_stats.get(contact.id, (0, 0, None))
        counts = feedback_counts[contact.id]
        mine = own_feedback.get(contact.id)
        own_open = own_opens.get(contact.id)
        contact_reads[contact.id] = RecruiterContactRead(
            id=contact.id,
            telegram_username=contact.telegram_username,
            companies=[
                RecruiterContactCompanyRead(id=company.id, name=company.name)
                for company in companies[contact.id].values()
            ],
            tracks=[
                RecruiterContactTrackRead(id=track.id, slug=track.slug, title=track.title)
                for track in tracks[contact.id].values()
            ],
            total_contact_opens=int(total_opens or 0),
            students_contacted_count=int(student_count or 0),
            last_contacted_at=last_contacted_at,
            helpful_count=counts.get(RecruiterFeedbackKind.HELPFUL, 0),
            ignores_count=counts.get(RecruiterFeedbackKind.IGNORES, 0),
            no_longer_works_count=counts.get(RecruiterFeedbackKind.NO_LONGER_WORKS, 0),
            account_missing_count=counts.get(RecruiterFeedbackKind.ACCOUNT_MISSING, 0),
            other_issue_count=counts.get(RecruiterFeedbackKind.OTHER, 0),
            issue_comments=issue_comments[contact.id],
            issue_comments_total=issue_comment_totals[contact.id],
            has_contacted=own_open is not None,
            my_contact_opens=1 if own_open is not None else 0,
            my_last_contacted_at=(own_open.last_opened_at if own_open is not None else None),
            my_feedback=(
                RecruiterFeedbackRead(
                    kind=mine.kind, reason=mine.reason, updated_at=mine.updated_at
                )
                if mine is not None
                else None
            ),
        )
    recruiters_by_company: dict[UUID, list[RecruiterContactRead]] = defaultdict(list)
    for company_id, contact in contact_rows:
        recruiters_by_company[company_id].append(contact_reads[contact.id])
    items = [
        RecruiterCompanyGroupRead(
            company=RecruiterContactCompanyRead(id=company.id, name=company.name),
            recruiters=recruiters_by_company[company.id],
        )
        for company in selected_companies
    ]
    return RecruiterContactPage(items=items, total=total, limit=limit, offset=offset)


async def _get_recruiter(session: AsyncSession, user: User, recruiter_id: UUID) -> RecruiterContact:
    track_ids = await accessible_track_ids(session, user)
    recruiter = await session.scalar(
        select(RecruiterContact).where(
            RecruiterContact.id == recruiter_id,
            _accessible_contact_filter(track_ids),
        )
    )
    if recruiter is None:
        api_error(404, "recruiter_not_found", "Recruiter contact was not found")
    return recruiter


async def open_recruiter_contact(
    session: AsyncSession, user: User, recruiter_id: UUID
) -> RecruiterContactOpenRead:
    recruiter = await _get_recruiter(session, user, recruiter_id)
    now = datetime.now(UTC)
    statement = insert(RecruiterContactOpen).values(
        recruiter_id=recruiter.id,
        user_id=user.id,
        open_count=1,
        first_opened_at=now,
        last_opened_at=now,
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[
                RecruiterContactOpen.recruiter_id,
                RecruiterContactOpen.user_id,
            ],
            set_={
                "last_opened_at": now,
            },
        )
    )
    await session.commit()
    total_contact_opens, students_contacted_count, last_contacted_at = (
        await session.execute(
            select(
                func.count(RecruiterContactOpen.user_id),
                func.count(distinct(RecruiterContactOpen.user_id)).filter(
                    User.role == UserRole.STUDENT
                ),
                func.max(RecruiterContactOpen.last_opened_at),
            )
            .join(User, User.id == RecruiterContactOpen.user_id)
            .where(RecruiterContactOpen.recruiter_id == recruiter.id)
        )
    ).one()
    own_open = await session.get(RecruiterContactOpen, (recruiter.id, user.id))
    return RecruiterContactOpenRead(
        recruiter_id=recruiter.id,
        url=f"https://t.me/{recruiter.telegram_username}",
        total_contact_opens=int(total_contact_opens or 0),
        students_contacted_count=int(students_contacted_count or 0),
        last_contacted_at=last_contacted_at or now,
        my_contact_opens=1 if own_open is not None else 0,
        my_last_contacted_at=own_open.last_opened_at if own_open is not None else now,
    )


async def set_recruiter_feedback(
    session: AsyncSession,
    user: User,
    recruiter_id: UUID,
    payload: RecruiterFeedbackMutation,
) -> RecruiterFeedbackRead:
    if user.role not in {UserRole.STUDENT, UserRole.MENTOR, UserRole.ADMIN}:
        api_error(403, "feedback_forbidden", "User cannot rate recruiter contacts")
    await _get_recruiter(session, user, recruiter_id)
    now = datetime.now(UTC)
    statement = insert(RecruiterFeedback).values(
        recruiter_id=recruiter_id,
        user_id=user.id,
        kind=payload.kind,
        reason=payload.reason,
        created_at=now,
        updated_at=now,
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[RecruiterFeedback.recruiter_id, RecruiterFeedback.user_id],
            set_={"kind": payload.kind, "reason": payload.reason, "updated_at": now},
        )
    )
    await session.commit()
    return RecruiterFeedbackRead(kind=payload.kind, reason=payload.reason, updated_at=now)


async def delete_recruiter_feedback(session: AsyncSession, user: User, recruiter_id: UUID) -> None:
    if user.role not in {UserRole.STUDENT, UserRole.MENTOR, UserRole.ADMIN}:
        api_error(403, "feedback_forbidden", "User cannot rate recruiter contacts")
    await _get_recruiter(session, user, recruiter_id)
    await session.execute(
        delete(RecruiterFeedback).where(
            RecruiterFeedback.recruiter_id == recruiter_id,
            RecruiterFeedback.user_id == user.id,
        )
    )
    await session.commit()
