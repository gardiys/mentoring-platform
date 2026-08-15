from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.errors import api_error
from app.mentors.models import MentorStudent, MentorTrackAssignment
from app.schedule.models import (
    MentorProfile,
    MentorTrackCalendar,
    PinnedResourceLink,
    ScheduleEvent,
    ScheduleEventKind,
)
from app.schedule.schemas import (
    AdminScheduleEventMutation,
    AdminScheduleEventPageRead,
    MentorMeetingMutation,
    MentorProfileMutation,
    MentorProfileRead,
    MentorTrackCalendarRead,
    MentorWeeklyCallMutation,
    MentorWeeklyCallRescheduleMutation,
    MyMentorDashboardRead,
    MyMentorPublicRead,
    PinnedResourceLinkMutation,
    PinnedResourceLinkRead,
    ScheduleEventRead,
    ScheduleEventSource,
    ScheduleTrackRead,
)
from app.tracks.models import LearningTrack, LearningTrackEnrollment
from app.users.models import MENTOR_CAPABLE_ROLES, User, UserRole


def _person_name(user: User | None) -> str:
    if user is None:
        return "Платформа"
    return " ".join(part for part in (user.first_name, user.last_name) if part)


def _regular_next_weekly_occurrence(
    event: ScheduleEvent, *, after: datetime | None = None
) -> datetime | None:
    if (
        event.kind is not ScheduleEventKind.WEEKLY_CALL
        or event.weekday is None
        or event.starts_at_time is None
        or event.timezone is None
    ):
        return None
    timezone = ZoneInfo(event.timezone)
    reference = (after or datetime.now(UTC)).astimezone(timezone)
    days_ahead = (event.weekday - reference.weekday()) % 7
    local_occurrence = datetime.combine(
        reference.date() + timedelta(days=days_ahead),
        event.starts_at_time,
        tzinfo=timezone,
    )
    if local_occurrence <= reference:
        local_occurrence += timedelta(days=7)
    return local_occurrence.astimezone(UTC)


def _override_affects_schedule(event: ScheduleEvent, *, now: datetime) -> bool:
    if event.rescheduled_from is None or event.rescheduled_to is None:
        return False
    return event.rescheduled_from >= now or event.rescheduled_to > now


def _rescheduled_occurrence_is_pending(event: ScheduleEvent, *, now: datetime) -> bool:
    return event.rescheduled_to is not None and event.rescheduled_to > now


def _reschedule_is_cancellable(event: ScheduleEvent, *, now: datetime) -> bool:
    if event.rescheduled_from is None or event.rescheduled_to is None:
        return False
    return now < min(event.rescheduled_from, event.rescheduled_to)


def _weekly_occurrences(
    event: ScheduleEvent, *, now: datetime | None = None
) -> tuple[datetime | None, datetime | None, bool]:
    current = now or datetime.now(UTC)
    regular = _regular_next_weekly_occurrence(event, after=current)
    affects_schedule = _override_affects_schedule(event, now=current)
    if not affects_schedule:
        return regular, regular, False

    if event.rescheduled_to is not None and event.rescheduled_to > current:
        return regular, event.rescheduled_to, True

    # An occurrence moved to an earlier slot must stay suppressed after that slot
    # has passed, even when its original date is still in the future.
    assert event.rescheduled_from is not None
    effective = _regular_next_weekly_occurrence(
        event,
        after=max(current, event.rescheduled_from),
    )
    return regular, effective, False


def next_schedule_occurrence(
    event: ScheduleEvent, *, now: datetime | None = None
) -> datetime | None:
    """Return the next effective occurrence, including a one-off reschedule."""
    current = now or datetime.now(UTC)
    if event.kind is ScheduleEventKind.MEETING:
        if event.starts_at is None or event.starts_at <= current:
            return None
        return event.starts_at
    return _weekly_occurrences(event, now=current)[1]


def _reschedule_base_occurrence(event: ScheduleEvent, *, now: datetime) -> datetime | None:
    _, effective, pending = _weekly_occurrences(event, now=now)
    if pending:
        return event.rescheduled_from
    return effective


def _event_read(
    event: ScheduleEvent, track: LearningTrack, mentor: User | None
) -> ScheduleEventRead:
    regular_occurrence, effective_occurrence, is_rescheduled = _weekly_occurrences(event)
    return ScheduleEventRead(
        id=event.id,
        track=ScheduleTrackRead(id=track.id, slug=track.slug, title=track.title),
        mentor_id=event.mentor_id,
        source=(
            ScheduleEventSource.MENTOR
            if event.mentor_id is not None
            else ScheduleEventSource.PLATFORM
        ),
        source_name=_person_name(mentor),
        kind=event.kind,
        title=event.title,
        description=event.description,
        meeting_url=event.meeting_url,
        weekday=event.weekday,
        starts_at_time=event.starts_at_time,
        timezone=event.timezone,
        starts_at=event.starts_at,
        regular_next_occurrence_at=regular_occurrence,
        next_occurrence_at=effective_occurrence,
        is_rescheduled=is_rescheduled,
        rescheduled_from=event.rescheduled_from,
        rescheduled_to=event.rescheduled_to,
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


async def _mentor_tracks(session: AsyncSession, mentor: User) -> list[LearningTrack]:
    statement = select(LearningTrack).where(LearningTrack.is_published.is_(True))
    if mentor.role is not UserRole.ADMIN:
        statement = statement.join(
            MentorTrackAssignment,
            MentorTrackAssignment.track_id == LearningTrack.id,
        ).where(MentorTrackAssignment.mentor_id == mentor.id)
    return list(
        await session.scalars(statement.order_by(LearningTrack.position, LearningTrack.title))
    )


async def _mentor_weekly_call_rows(
    session: AsyncSession, mentor_id: UUID
) -> list[tuple[ScheduleEvent, LearningTrack, User | None]]:
    rows = (
        await session.execute(
            select(ScheduleEvent, LearningTrack, User)
            .join(LearningTrack, LearningTrack.id == ScheduleEvent.track_id)
            .outerjoin(User, User.id == ScheduleEvent.mentor_id)
            .where(
                ScheduleEvent.mentor_id == mentor_id,
                ScheduleEvent.kind == ScheduleEventKind.WEEKLY_CALL,
            )
            .order_by(
                ScheduleEvent.weekday,
                ScheduleEvent.starts_at_time.asc().nulls_last(),
                LearningTrack.position,
                ScheduleEvent.title,
                ScheduleEvent.id,
            )
        )
    ).all()
    return [(event, track, owner) for event, track, owner in rows]


async def _mentor_activity_rows(
    session: AsyncSession, mentor_id: UUID
) -> list[tuple[ScheduleEvent, LearningTrack, User | None]]:
    rows = (
        await session.execute(
            select(ScheduleEvent, LearningTrack, User)
            .join(LearningTrack, LearningTrack.id == ScheduleEvent.track_id)
            .outerjoin(User, User.id == ScheduleEvent.mentor_id)
            .where(
                ScheduleEvent.mentor_id == mentor_id,
                ScheduleEvent.kind == ScheduleEventKind.MEETING,
                ScheduleEvent.starts_at >= datetime.now(UTC),
            )
            .order_by(
                ScheduleEvent.starts_at,
                LearningTrack.position,
                ScheduleEvent.title,
                ScheduleEvent.id,
            )
        )
    ).all()
    return [(event, track, owner) for event, track, owner in rows]


async def _profile_read(session: AsyncSession, mentor: User) -> MentorProfileRead:
    profile = await session.get(MentorProfile, mentor.id)
    tracks = await _mentor_tracks(session, mentor)
    track_by_id = {track.id: track for track in tracks}
    calendar_by_track = {
        row.track_id: row
        for row in await session.scalars(
            select(MentorTrackCalendar).where(
                MentorTrackCalendar.mentor_id == mentor.id,
                MentorTrackCalendar.track_id.in_(list(track_by_id)),
            )
        )
    }
    legacy_calendar_url = profile.group_calendar_url if profile else None
    calendars = [
        MentorTrackCalendarRead(
            track=ScheduleTrackRead(id=track.id, slug=track.slug, title=track.title),
            calendar_url=(
                calendar_by_track[track.id].calendar_url
                if track.id in calendar_by_track
                else legacy_calendar_url
            ),
        )
        for track in tracks
        if track.id in calendar_by_track or legacy_calendar_url is not None
    ]
    calls = await _mentor_weekly_call_rows(session, mentor.id)
    activities = await _mentor_activity_rows(session, mentor.id)
    return MentorProfileRead(
        mentor_id=mentor.id,
        consultation_url=profile.consultation_url if profile else None,
        group_calendars=calendars,
        tracks=[
            ScheduleTrackRead(id=track.id, slug=track.slug, title=track.title) for track in tracks
        ],
        weekly_calls=[_event_read(event, track, owner) for event, track, owner in calls],
        one_off_activities=[_event_read(event, track, owner) for event, track, owner in activities],
        updated_at=profile.updated_at if profile else None,
    )


async def get_mentor_profile(session: AsyncSession, mentor: User) -> MentorProfileRead:
    return await _profile_read(session, mentor)


async def update_mentor_profile(
    session: AsyncSession, mentor: User, payload: MentorProfileMutation
) -> MentorProfileRead:
    consultation_url = (
        str(payload.consultation_url) if payload.consultation_url is not None else None
    )
    tracks = {track.id: track for track in await _mentor_tracks(session, mentor)}
    for calendar in payload.group_calendars:
        if calendar.track_id not in tracks:
            api_error(
                422,
                "mentor_calendar_track_not_assigned",
                "Mentor is not assigned to the selected calendar track",
            )
    statement = (
        insert(MentorProfile)
        .values(
            mentor_id=mentor.id,
            consultation_url=consultation_url,
            group_calendar_url=None,
        )
        .on_conflict_do_update(
            index_elements=[MentorProfile.mentor_id],
            set_={
                "consultation_url": consultation_url,
                "group_calendar_url": None,
                "updated_at": func.now(),
            },
        )
    )
    await session.execute(statement)
    await session.execute(
        delete(MentorTrackCalendar).where(MentorTrackCalendar.mentor_id == mentor.id)
    )
    if payload.group_calendars:
        await session.execute(
            insert(MentorTrackCalendar),
            [
                {
                    "mentor_id": mentor.id,
                    "track_id": calendar.track_id,
                    "calendar_url": str(calendar.calendar_url),
                }
                for calendar in payload.group_calendars
            ],
        )
    await session.commit()
    return await _profile_read(session, mentor)


async def _mentor_track_model(session: AsyncSession, mentor: User, track_id: UUID) -> LearningTrack:
    track = await session.get(LearningTrack, track_id)
    if track is None or not track.is_published:
        api_error(422, "invalid_schedule_track", "Selected learning track does not exist")
    if mentor.role is not UserRole.ADMIN:
        assignment = await session.get(
            MentorTrackAssignment,
            {"mentor_id": mentor.id, "track_id": track.id},
        )
        if assignment is None:
            api_error(
                422,
                "mentor_schedule_track_not_assigned",
                "Mentor is not assigned to the selected learning track",
            )
    return track


async def create_mentor_weekly_call(
    session: AsyncSession,
    mentor: User,
    payload: MentorWeeklyCallMutation,
) -> ScheduleEventRead:
    track = await _mentor_track_model(session, mentor, payload.track_id)
    event = ScheduleEvent(
        track_id=track.id,
        mentor_id=mentor.id,
        created_by_user_id=mentor.id,
        kind=ScheduleEventKind.WEEKLY_CALL,
        title=payload.title,
        description=payload.description or None,
        meeting_url=str(payload.meeting_url),
        weekday=payload.weekday,
        starts_at_time=payload.starts_at_time,
        timezone=payload.timezone,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return _event_read(event, track, mentor)


async def _owned_weekly_call(
    session: AsyncSession, mentor_id: UUID, event_id: UUID
) -> ScheduleEvent:
    event = await session.scalar(
        select(ScheduleEvent).where(
            ScheduleEvent.id == event_id,
            ScheduleEvent.mentor_id == mentor_id,
            ScheduleEvent.kind == ScheduleEventKind.WEEKLY_CALL,
        )
    )
    if event is None:
        api_error(404, "mentor_weekly_call_not_found", "Weekly call was not found")
    return event


async def update_mentor_weekly_call(
    session: AsyncSession,
    mentor: User,
    event_id: UUID,
    payload: MentorWeeklyCallMutation,
) -> ScheduleEventRead:
    event = await _owned_weekly_call(session, mentor.id, event_id)
    track = await _mentor_track_model(session, mentor, payload.track_id)
    event.track_id = track.id
    event.title = payload.title
    event.description = payload.description or None
    event.meeting_url = str(payload.meeting_url)
    event.weekday = payload.weekday
    event.starts_at_time = payload.starts_at_time
    event.timezone = payload.timezone
    event.rescheduled_from = None
    event.rescheduled_to = None
    await session.commit()
    await session.refresh(event)
    return _event_read(event, track, mentor)


async def delete_mentor_weekly_call(session: AsyncSession, mentor: User, event_id: UUID) -> None:
    event = await _owned_weekly_call(session, mentor.id, event_id)
    await session.delete(event)
    await session.commit()


async def reschedule_mentor_weekly_call(
    session: AsyncSession,
    mentor: User,
    event_id: UUID,
    payload: MentorWeeklyCallRescheduleMutation,
) -> ScheduleEventRead:
    event = await _owned_weekly_call(session, mentor.id, event_id)
    now = datetime.now(UTC)
    target = payload.starts_at.astimezone(UTC)
    if target <= now:
        api_error(422, "weekly_call_reschedule_in_past", "New call time must be in the future")

    original: datetime | None
    original = _reschedule_base_occurrence(event, now=now)
    if original is None:
        api_error(
            422,
            "weekly_call_time_required",
            "Set the weekly call time before rescheduling an occurrence",
        )
    if target >= original + timedelta(days=7):
        api_error(
            422,
            "weekly_call_reschedule_out_of_range",
            "New call time must be before the following regular occurrence",
        )

    track = await _mentor_track_model(session, mentor, event.track_id)
    event.rescheduled_from = original
    event.rescheduled_to = target
    await session.commit()
    await session.refresh(event)
    return _event_read(event, track, mentor)


async def cancel_mentor_weekly_call_reschedule(
    session: AsyncSession, mentor: User, event_id: UUID
) -> None:
    event = await _owned_weekly_call(session, mentor.id, event_id)
    if (
        event.rescheduled_from is not None
        and event.rescheduled_to is not None
        and not _reschedule_is_cancellable(event, now=datetime.now(UTC))
    ):
        api_error(
            409,
            "weekly_call_reschedule_cannot_cancel",
            "The reschedule can no longer be cancelled because one of its time slots has passed",
        )
    event.rescheduled_from = None
    event.rescheduled_to = None
    await session.commit()


async def create_mentor_activity(
    session: AsyncSession,
    mentor: User,
    payload: MentorMeetingMutation,
) -> ScheduleEventRead:
    track = await _mentor_track_model(session, mentor, payload.track_id)
    event = ScheduleEvent(
        track_id=track.id,
        mentor_id=mentor.id,
        created_by_user_id=mentor.id,
        kind=ScheduleEventKind.MEETING,
        title=payload.title,
        description=payload.description or None,
        meeting_url=str(payload.meeting_url) if payload.meeting_url is not None else None,
        starts_at=payload.starts_at,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return _event_read(event, track, mentor)


async def _owned_mentor_activity(
    session: AsyncSession, mentor_id: UUID, event_id: UUID
) -> ScheduleEvent:
    event = await session.scalar(
        select(ScheduleEvent).where(
            ScheduleEvent.id == event_id,
            ScheduleEvent.mentor_id == mentor_id,
            ScheduleEvent.kind == ScheduleEventKind.MEETING,
        )
    )
    if event is None:
        api_error(404, "mentor_activity_not_found", "Mentor activity was not found")
    return event


async def update_mentor_activity(
    session: AsyncSession,
    mentor: User,
    event_id: UUID,
    payload: MentorMeetingMutation,
) -> ScheduleEventRead:
    event = await _owned_mentor_activity(session, mentor.id, event_id)
    track = await _mentor_track_model(session, mentor, payload.track_id)
    event.track_id = track.id
    event.title = payload.title
    event.description = payload.description or None
    event.meeting_url = str(payload.meeting_url) if payload.meeting_url is not None else None
    event.starts_at = payload.starts_at
    await session.commit()
    await session.refresh(event)
    return _event_read(event, track, mentor)


async def delete_mentor_activity(session: AsyncSession, mentor: User, event_id: UUID) -> None:
    event = await _owned_mentor_activity(session, mentor.id, event_id)
    await session.delete(event)
    await session.commit()


async def _track_model(session: AsyncSession, track_id: UUID) -> LearningTrack:
    track = await session.get(LearningTrack, track_id)
    if track is None:
        api_error(422, "invalid_schedule_track", "Selected learning track does not exist")
    return track


async def _admin_event_model(session: AsyncSession, event_id: UUID) -> ScheduleEvent:
    event = await session.scalar(
        select(ScheduleEvent).where(
            ScheduleEvent.id == event_id,
            ScheduleEvent.mentor_id.is_(None),
        )
    )
    if event is None:
        api_error(404, "schedule_event_not_found", "Schedule event was not found")
    return event


async def _admin_event_read(session: AsyncSession, event: ScheduleEvent) -> ScheduleEventRead:
    track = await session.get(LearningTrack, event.track_id)
    if track is None:
        api_error(404, "schedule_event_track_not_found", "Schedule event track was not found")
    return _event_read(event, track, None)


async def list_admin_schedule_events(
    session: AsyncSession,
    *,
    track_id: UUID | None,
    kind: ScheduleEventKind | None,
    limit: int,
    offset: int,
) -> AdminScheduleEventPageRead:
    filters: list[ColumnElement[bool]] = [ScheduleEvent.mentor_id.is_(None)]
    if track_id is not None:
        filters.append(ScheduleEvent.track_id == track_id)
    if kind is not None:
        filters.append(ScheduleEvent.kind == kind)
    total = int(await session.scalar(select(func.count(ScheduleEvent.id)).where(*filters)) or 0)
    rows = (
        await session.execute(
            select(ScheduleEvent, LearningTrack)
            .join(LearningTrack, LearningTrack.id == ScheduleEvent.track_id)
            .where(*filters)
            .order_by(
                ScheduleEvent.starts_at.desc().nulls_last(),
                ScheduleEvent.weekday.asc().nulls_last(),
                ScheduleEvent.starts_at_time.asc().nulls_last(),
                LearningTrack.position,
                ScheduleEvent.created_at.desc(),
                ScheduleEvent.id,
            )
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return AdminScheduleEventPageRead(
        items=[_event_read(event, track, None) for event, track in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


async def get_admin_schedule_event(session: AsyncSession, event_id: UUID) -> ScheduleEventRead:
    return await _admin_event_read(session, await _admin_event_model(session, event_id))


def _apply_admin_payload(event: ScheduleEvent, payload: AdminScheduleEventMutation) -> None:
    event.track_id = payload.track_id
    event.kind = payload.kind
    event.title = payload.title
    event.description = payload.description or None
    event.meeting_url = str(payload.meeting_url) if payload.meeting_url is not None else None
    event.weekday = payload.weekday
    event.starts_at_time = payload.starts_at_time
    event.timezone = payload.timezone
    event.starts_at = payload.starts_at
    event.rescheduled_from = None
    event.rescheduled_to = None


async def create_admin_schedule_event(
    session: AsyncSession,
    admin: User,
    payload: AdminScheduleEventMutation,
) -> ScheduleEventRead:
    track = await _track_model(session, payload.track_id)
    event = ScheduleEvent(created_by_user_id=admin.id, mentor_id=None)
    _apply_admin_payload(event, payload)
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return _event_read(event, track, None)


async def update_admin_schedule_event(
    session: AsyncSession,
    event_id: UUID,
    payload: AdminScheduleEventMutation,
) -> ScheduleEventRead:
    event = await _admin_event_model(session, event_id)
    track = await _track_model(session, payload.track_id)
    _apply_admin_payload(event, payload)
    await session.commit()
    await session.refresh(event)
    return _event_read(event, track, None)


async def delete_admin_schedule_event(session: AsyncSession, event_id: UUID) -> None:
    event = await _admin_event_model(session, event_id)
    await session.delete(event)
    await session.commit()


def _useful_link_read(link: PinnedResourceLink) -> PinnedResourceLinkRead:
    return PinnedResourceLinkRead(
        id=link.id,
        title=link.title,
        description=link.description,
        url=link.url,
        position=link.position,
        created_at=link.created_at,
        updated_at=link.updated_at,
    )


async def list_useful_links(session: AsyncSession) -> list[PinnedResourceLinkRead]:
    links = list(
        await session.scalars(
            select(PinnedResourceLink).order_by(
                PinnedResourceLink.position,
                PinnedResourceLink.title,
                PinnedResourceLink.id,
            )
        )
    )
    return [_useful_link_read(link) for link in links]


async def _useful_link_model(session: AsyncSession, link_id: UUID) -> PinnedResourceLink:
    link = await session.get(PinnedResourceLink, link_id)
    if link is None:
        api_error(404, "useful_link_not_found", "Useful link was not found")
    return link


async def create_useful_link(
    session: AsyncSession,
    admin: User,
    payload: PinnedResourceLinkMutation,
) -> PinnedResourceLinkRead:
    link = PinnedResourceLink(
        created_by_user_id=admin.id,
        title=payload.title,
        description=payload.description or None,
        url=str(payload.url),
        position=payload.position,
    )
    session.add(link)
    await session.commit()
    await session.refresh(link)
    return _useful_link_read(link)


async def update_useful_link(
    session: AsyncSession,
    link_id: UUID,
    payload: PinnedResourceLinkMutation,
) -> PinnedResourceLinkRead:
    link = await _useful_link_model(session, link_id)
    link.title = payload.title
    link.description = payload.description or None
    link.url = str(payload.url)
    link.position = payload.position
    await session.commit()
    await session.refresh(link)
    return _useful_link_read(link)


async def delete_useful_link(session: AsyncSession, link_id: UUID) -> None:
    link = await _useful_link_model(session, link_id)
    await session.delete(link)
    await session.commit()


async def _student_schedule(
    session: AsyncSession, student: User, mentor: User | None
) -> list[ScheduleEventRead]:
    visibility: list[ColumnElement[bool]] = [ScheduleEvent.mentor_id.is_(None)]
    if mentor is not None:
        visibility.append(ScheduleEvent.mentor_id == mentor.id)
    rows = (
        await session.execute(
            select(ScheduleEvent, LearningTrack, User)
            .join(LearningTrack, LearningTrack.id == ScheduleEvent.track_id)
            .join(
                LearningTrackEnrollment,
                LearningTrackEnrollment.track_id == ScheduleEvent.track_id,
            )
            .outerjoin(User, User.id == ScheduleEvent.mentor_id)
            .where(
                LearningTrackEnrollment.user_id == student.id,
                LearningTrack.is_published.is_(True),
                or_(*visibility),
                or_(
                    ScheduleEvent.kind == ScheduleEventKind.WEEKLY_CALL,
                    ScheduleEvent.starts_at >= datetime.now(UTC),
                ),
            )
        )
    ).all()
    result = [_event_read(event, track, owner) for event, track, owner in rows]
    far_future = datetime.max.replace(tzinfo=UTC)
    return sorted(
        result,
        key=lambda event: (
            event.starts_at or event.next_occurrence_at or far_future,
            event.title.casefold(),
            str(event.id),
        ),
    )


async def my_mentor_dashboard(session: AsyncSession, student: User) -> MyMentorDashboardRead:
    mentor = await session.scalar(
        select(User)
        .join(MentorStudent, MentorStudent.mentor_id == User.id)
        .where(MentorStudent.student_id == student.id)
    )
    if mentor is not None and (mentor.role not in MENTOR_CAPABLE_ROLES or not mentor.is_active):
        mentor = None
    public_mentor: MyMentorPublicRead | None = None
    if mentor is not None:
        profile = await session.get(MentorProfile, mentor.id)
        legacy_calendar_url = profile.group_calendar_url if profile else None
        student_tracks = list(
            await session.scalars(
                select(LearningTrack)
                .join(
                    LearningTrackEnrollment,
                    LearningTrackEnrollment.track_id == LearningTrack.id,
                )
                .where(
                    LearningTrackEnrollment.user_id == student.id,
                    LearningTrack.is_published.is_(True),
                )
                .order_by(LearningTrack.position, LearningTrack.title)
            )
        )
        calendar_rows = {
            row.track_id: row
            for row in await session.scalars(
                select(MentorTrackCalendar).where(
                    MentorTrackCalendar.mentor_id == mentor.id,
                    MentorTrackCalendar.track_id.in_([track.id for track in student_tracks]),
                )
            )
        }
        group_calendars = [
            MentorTrackCalendarRead(
                track=ScheduleTrackRead(id=track.id, slug=track.slug, title=track.title),
                calendar_url=(
                    calendar_rows[track.id].calendar_url
                    if track.id in calendar_rows
                    else legacy_calendar_url
                ),
            )
            for track in student_tracks
            if track.id in calendar_rows or legacy_calendar_url is not None
        ]
        public_mentor = MyMentorPublicRead(
            id=mentor.id,
            first_name=mentor.first_name,
            last_name=mentor.last_name,
            telegram_username=mentor.telegram_username,
            consultation_url=profile.consultation_url if profile else None,
            group_calendars=group_calendars,
        )
    return MyMentorDashboardRead(
        mentor=public_mentor,
        schedule=await _student_schedule(session, student, mentor),
        useful_links=await list_useful_links(session),
    )
