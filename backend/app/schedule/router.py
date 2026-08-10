from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AdminUser, MentorUser, StudentUser
from app.db.session import get_db_session
from app.schedule.models import ScheduleEventKind
from app.schedule.schemas import (
    AdminScheduleEventMutation,
    AdminScheduleEventPageRead,
    MentorMeetingMutation,
    MentorProfileMutation,
    MentorProfileRead,
    MentorWeeklyCallMutation,
    MentorWeeklyCallRescheduleMutation,
    MyMentorDashboardRead,
    PinnedResourceLinkMutation,
    PinnedResourceLinkRead,
    ScheduleEventRead,
)
from app.schedule.service import (
    cancel_mentor_weekly_call_reschedule,
    create_admin_schedule_event,
    create_mentor_activity,
    create_mentor_weekly_call,
    create_useful_link,
    delete_admin_schedule_event,
    delete_mentor_activity,
    delete_mentor_weekly_call,
    delete_useful_link,
    get_admin_schedule_event,
    get_mentor_profile,
    list_admin_schedule_events,
    list_useful_links,
    my_mentor_dashboard,
    reschedule_mentor_weekly_call,
    update_admin_schedule_event,
    update_mentor_activity,
    update_mentor_profile,
    update_mentor_weekly_call,
    update_useful_link,
)

Session = Annotated[AsyncSession, Depends(get_db_session)]

mentor_profile_router = APIRouter(prefix="/mentor/profile", tags=["mentor-profile"])
my_mentor_router = APIRouter(prefix="/me/mentor", tags=["my-mentor"])
admin_schedule_router = APIRouter(prefix="/admin/schedule/events", tags=["admin-schedule"])
admin_useful_links_router = APIRouter(prefix="/admin/useful-links", tags=["admin-useful-links"])


@mentor_profile_router.get("", response_model=MentorProfileRead)
async def mentor_profile(session: Session, mentor: MentorUser) -> MentorProfileRead:
    return await get_mentor_profile(session, mentor)


@mentor_profile_router.put("", response_model=MentorProfileRead)
async def mentor_update_profile(
    payload: MentorProfileMutation,
    session: Session,
    mentor: MentorUser,
) -> MentorProfileRead:
    return await update_mentor_profile(session, mentor, payload)


@mentor_profile_router.post(
    "/weekly-calls",
    response_model=ScheduleEventRead,
    status_code=status.HTTP_201_CREATED,
)
async def mentor_create_weekly_call(
    payload: MentorWeeklyCallMutation,
    session: Session,
    mentor: MentorUser,
) -> ScheduleEventRead:
    return await create_mentor_weekly_call(session, mentor, payload)


@mentor_profile_router.put("/weekly-calls/{event_id}", response_model=ScheduleEventRead)
async def mentor_update_weekly_call(
    event_id: UUID,
    payload: MentorWeeklyCallMutation,
    session: Session,
    mentor: MentorUser,
) -> ScheduleEventRead:
    return await update_mentor_weekly_call(session, mentor, event_id, payload)


@mentor_profile_router.put(
    "/weekly-calls/{event_id}/reschedule",
    response_model=ScheduleEventRead,
)
async def mentor_reschedule_weekly_call(
    event_id: UUID,
    payload: MentorWeeklyCallRescheduleMutation,
    session: Session,
    mentor: MentorUser,
) -> ScheduleEventRead:
    return await reschedule_mentor_weekly_call(session, mentor, event_id, payload)


@mentor_profile_router.delete(
    "/weekly-calls/{event_id}/reschedule",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def mentor_cancel_weekly_call_reschedule(
    event_id: UUID, session: Session, mentor: MentorUser
) -> Response:
    await cancel_mentor_weekly_call_reschedule(session, mentor, event_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@mentor_profile_router.delete(
    "/weekly-calls/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def mentor_delete_weekly_call(
    event_id: UUID, session: Session, mentor: MentorUser
) -> Response:
    await delete_mentor_weekly_call(session, mentor, event_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@mentor_profile_router.post(
    "/activities",
    response_model=ScheduleEventRead,
    status_code=status.HTTP_201_CREATED,
)
async def mentor_create_activity(
    payload: MentorMeetingMutation,
    session: Session,
    mentor: MentorUser,
) -> ScheduleEventRead:
    return await create_mentor_activity(session, mentor, payload)


@mentor_profile_router.put("/activities/{event_id}", response_model=ScheduleEventRead)
async def mentor_update_activity(
    event_id: UUID,
    payload: MentorMeetingMutation,
    session: Session,
    mentor: MentorUser,
) -> ScheduleEventRead:
    return await update_mentor_activity(session, mentor, event_id, payload)


@mentor_profile_router.delete(
    "/activities/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def mentor_delete_activity(event_id: UUID, session: Session, mentor: MentorUser) -> Response:
    await delete_mentor_activity(session, mentor, event_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@my_mentor_router.get("", response_model=MyMentorDashboardRead)
async def student_my_mentor(session: Session, student: StudentUser) -> MyMentorDashboardRead:
    return await my_mentor_dashboard(session, student)


@admin_schedule_router.get("", response_model=AdminScheduleEventPageRead)
async def admin_schedule_events(
    session: Session,
    _admin: AdminUser,
    track_id: UUID | None = None,
    kind: ScheduleEventKind | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AdminScheduleEventPageRead:
    return await list_admin_schedule_events(
        session,
        track_id=track_id,
        kind=kind,
        limit=limit,
        offset=offset,
    )


@admin_schedule_router.post(
    "",
    response_model=ScheduleEventRead,
    status_code=status.HTTP_201_CREATED,
)
async def admin_create_schedule_event(
    payload: AdminScheduleEventMutation,
    session: Session,
    admin: AdminUser,
) -> ScheduleEventRead:
    return await create_admin_schedule_event(session, admin, payload)


@admin_schedule_router.get("/{event_id}", response_model=ScheduleEventRead)
async def admin_schedule_event(
    event_id: UUID, session: Session, _admin: AdminUser
) -> ScheduleEventRead:
    return await get_admin_schedule_event(session, event_id)


@admin_schedule_router.put("/{event_id}", response_model=ScheduleEventRead)
async def admin_update_schedule_event(
    event_id: UUID,
    payload: AdminScheduleEventMutation,
    session: Session,
    _admin: AdminUser,
) -> ScheduleEventRead:
    return await update_admin_schedule_event(session, event_id, payload)


@admin_schedule_router.delete(
    "/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def admin_delete_schedule_event(
    event_id: UUID, session: Session, _admin: AdminUser
) -> Response:
    await delete_admin_schedule_event(session, event_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@admin_useful_links_router.get("", response_model=list[PinnedResourceLinkRead])
async def admin_useful_links(session: Session, _admin: AdminUser) -> list[PinnedResourceLinkRead]:
    return await list_useful_links(session)


@admin_useful_links_router.post(
    "",
    response_model=PinnedResourceLinkRead,
    status_code=status.HTTP_201_CREATED,
)
async def admin_create_useful_link(
    payload: PinnedResourceLinkMutation,
    session: Session,
    admin: AdminUser,
) -> PinnedResourceLinkRead:
    return await create_useful_link(session, admin, payload)


@admin_useful_links_router.put("/{link_id}", response_model=PinnedResourceLinkRead)
async def admin_update_useful_link(
    link_id: UUID,
    payload: PinnedResourceLinkMutation,
    session: Session,
    _admin: AdminUser,
) -> PinnedResourceLinkRead:
    return await update_useful_link(session, link_id, payload)


@admin_useful_links_router.delete(
    "/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def admin_delete_useful_link(link_id: UUID, session: Session, _admin: AdminUser) -> Response:
    await delete_useful_link(session, link_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
