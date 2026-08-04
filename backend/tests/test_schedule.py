from datetime import UTC, datetime, time, timedelta
from uuid import UUID, uuid4

from httpx import AsyncClient

from app.mentors.models import MentorTrackAssignment
from app.schedule.models import ScheduleEvent, ScheduleEventKind
from app.schedule.service import (
    _regular_next_weekly_occurrence,
    _reschedule_base_occurrence,
    _weekly_occurrences,
)
from app.tracks.models import LearningTrackEnrollment
from app.users.models import User, UserRole
from tests.conftest import SeededData, TestSession, auth


def weekly_call_payload(
    track_id: UUID,
    *,
    title: str = "Еженедельный созвон",
    weekday: int = 1,
    starts_at_time: str = "18:30:00",
    meeting_url: str = "https://meet.example.com/weekly",
) -> dict[str, object]:
    return {
        "track_id": str(track_id),
        "title": title,
        "description": "Разбираем прогресс и вопросы за неделю",
        "weekday": weekday,
        "starts_at_time": starts_at_time,
        "timezone": "Europe/Moscow",
        "meeting_url": meeting_url,
    }


def admin_weekly_event_payload(
    track_id: UUID,
    *,
    title: str,
    weekday: int = 2,
) -> dict[str, object]:
    return {
        **weekly_call_payload(
            track_id,
            title=title,
            weekday=weekday,
            meeting_url="https://meet.example.com/platform-weekly",
        ),
        "kind": "weekly_call",
    }


def admin_meeting_payload(
    track_id: UUID,
    *,
    title: str,
    starts_at: datetime,
) -> dict[str, object]:
    return {
        "track_id": str(track_id),
        "kind": "meeting",
        "title": title,
        "description": "Общая встреча направления",
        "meeting_url": "https://meet.example.com/platform-meeting",
        "starts_at": starts_at.isoformat(),
    }


def mentor_activity_payload(
    track_id: UUID,
    *,
    title: str,
    starts_at: datetime,
    meeting_url: str | None = None,
) -> dict[str, object]:
    return {
        "track_id": str(track_id),
        "title": title,
        "description": "Дополнительный разбор с группой",
        "meeting_url": meeting_url,
        "starts_at": starts_at.isoformat(),
    }


def useful_link_payload(
    *,
    title: str,
    position: int,
    url: str,
    description: str | None = None,
) -> dict[str, object]:
    return {
        "title": title,
        "description": description,
        "url": url,
        "position": position,
    }


async def test_mentor_profile_get_put_url_validation_and_student_forbidden(
    client: AsyncClient,
    seeded: SeededData,
) -> None:
    initial = await client.get(
        "/api/v1/mentor/profile",
        headers=auth(seeded.mentor_id),
    )
    updated = await client.put(
        "/api/v1/mentor/profile",
        headers=auth(seeded.mentor_id),
        json={
            "consultation_url": "https://cal.example.com/anton/python",
            "group_calendar_url": "https://cal.example.com/anton/group",
        },
    )
    loaded = await client.get(
        "/api/v1/mentor/profile",
        headers=auth(seeded.mentor_id),
    )
    invalid = await client.put(
        "/api/v1/mentor/profile",
        headers=auth(seeded.mentor_id),
        json={
            "consultation_url": "https://cal.example.com/anton/python",
            "group_calendar_url": "javascript:alert(1)",
        },
    )
    student_get = await client.get(
        "/api/v1/mentor/profile",
        headers=auth(seeded.student_id),
    )
    student_put = await client.put(
        "/api/v1/mentor/profile",
        headers=auth(seeded.student_id),
        json={
            "consultation_url": "https://cal.example.com/student",
            "group_calendar_url": "https://cal.example.com/student/group",
        },
    )

    assert initial.status_code == 200, initial.text
    assert initial.json()["mentor_id"] == str(seeded.mentor_id)
    assert initial.json()["consultation_url"] is None
    assert initial.json()["group_calendar_url"] is None
    assert [track["slug"] for track in initial.json()["tracks"]] == ["python"]
    assert initial.json()["weekly_calls"] == []
    assert initial.json()["one_off_activities"] == []

    assert updated.status_code == 200, updated.text
    assert updated.json()["consultation_url"] == "https://cal.example.com/anton/python"
    assert updated.json()["group_calendar_url"] == "https://cal.example.com/anton/group"
    assert loaded.status_code == 200, loaded.text
    assert loaded.json()["consultation_url"] == "https://cal.example.com/anton/python"
    assert loaded.json()["group_calendar_url"] == "https://cal.example.com/anton/group"
    assert invalid.status_code == 422
    assert student_get.status_code == 403
    assert student_put.status_code == 403


async def test_admin_useful_links_crud_order_validation_and_access(
    client: AsyncClient,
    seeded: SeededData,
) -> None:
    docs = await client.post(
        "/api/v1/admin/useful-links",
        headers=auth(seeded.admin_id),
        json=useful_link_payload(
            title="Docs",
            description="Справочник по Python",
            url="https://docs.example.com/python",
            position=20,
        ),
    )
    beta = await client.post(
        "/api/v1/admin/useful-links",
        headers=auth(seeded.admin_id),
        json=useful_link_payload(
            title="Beta",
            url="https://learn.example.com/beta",
            position=10,
        ),
    )
    alpha = await client.post(
        "/api/v1/admin/useful-links",
        headers=auth(seeded.admin_id),
        json=useful_link_payload(
            title="Alpha",
            url="https://learn.example.com/alpha",
            position=10,
        ),
    )

    for response in (docs, beta, alpha):
        assert response.status_code == 201, response.text
        assert set(response.json()) == {
            "id",
            "title",
            "description",
            "url",
            "position",
            "created_at",
            "updated_at",
        }

    listed = await client.get(
        "/api/v1/admin/useful-links",
        headers=auth(seeded.admin_id),
    )
    updated = await client.put(
        f"/api/v1/admin/useful-links/{docs.json()['id']}",
        headers=auth(seeded.admin_id),
        json=useful_link_payload(
            title="Start",
            description="Обновлённое описание",
            url="https://start.example.com/guide",
            position=0,
        ),
    )
    listed_after_update = await client.get(
        "/api/v1/admin/useful-links",
        headers=auth(seeded.admin_id),
    )
    invalid = await client.post(
        "/api/v1/admin/useful-links",
        headers=auth(seeded.admin_id),
        json=useful_link_payload(
            title="Invalid",
            url="javascript:alert(1)",
            position=30,
        ),
    )
    student_list = await client.get(
        "/api/v1/admin/useful-links",
        headers=auth(seeded.student_id),
    )
    mentor_list = await client.get(
        "/api/v1/admin/useful-links",
        headers=auth(seeded.mentor_id),
    )
    mentor_create = await client.post(
        "/api/v1/admin/useful-links",
        headers=auth(seeded.mentor_id),
        json=useful_link_payload(
            title="Forbidden",
            url="https://example.com/forbidden",
            position=0,
        ),
    )

    assert listed.status_code == 200, listed.text
    assert [item["title"] for item in listed.json()] == ["Alpha", "Beta", "Docs"]
    assert updated.status_code == 200, updated.text
    assert updated.json()["title"] == "Start"
    assert updated.json()["description"] == "Обновлённое описание"
    assert updated.json()["url"] == "https://start.example.com/guide"
    assert updated.json()["position"] == 0
    assert listed_after_update.status_code == 200, listed_after_update.text
    assert [item["title"] for item in listed_after_update.json()] == [
        "Start",
        "Alpha",
        "Beta",
    ]
    assert invalid.status_code == 422
    assert student_list.status_code == 403
    assert mentor_list.status_code == 403
    assert mentor_create.status_code == 403

    deleted = await client.delete(
        f"/api/v1/admin/useful-links/{beta.json()['id']}",
        headers=auth(seeded.admin_id),
    )
    listed_after_delete = await client.get(
        "/api/v1/admin/useful-links",
        headers=auth(seeded.admin_id),
    )
    deleted_again = await client.delete(
        f"/api/v1/admin/useful-links/{beta.json()['id']}",
        headers=auth(seeded.admin_id),
    )

    assert deleted.status_code == 204
    assert listed_after_delete.status_code == 200, listed_after_delete.text
    assert [item["title"] for item in listed_after_delete.json()] == ["Start", "Alpha"]
    assert deleted_again.status_code == 404
    assert deleted_again.json()["detail"]["code"] == "useful_link_not_found"


async def test_mentor_weekly_call_crud_respects_tracks_owner_and_admin_capability(
    client: AsyncClient,
    seeded: SeededData,
) -> None:
    created = await client.post(
        "/api/v1/mentor/profile/weekly-calls",
        headers=auth(seeded.mentor_id),
        json=weekly_call_payload(seeded.python_track_id),
    )
    rejected_go = await client.post(
        "/api/v1/mentor/profile/weekly-calls",
        headers=auth(seeded.mentor_id),
        json=weekly_call_payload(seeded.go_track_id, title="Go-созвон"),
    )

    assert created.status_code == 201, created.text
    call_id = created.json()["id"]
    assert created.json()["source"] == "mentor"
    assert created.json()["mentor_id"] == str(seeded.mentor_id)
    assert created.json()["track"]["slug"] == "python"
    assert created.json()["kind"] == "weekly_call"
    assert created.json()["timezone"] == "Europe/Moscow"
    assert created.json()["next_occurrence_at"] is not None

    assert rejected_go.status_code == 422
    assert rejected_go.json()["detail"]["code"] == "mentor_schedule_track_not_assigned"

    other_mentor_update = await client.put(
        f"/api/v1/mentor/profile/weekly-calls/{call_id}",
        headers=auth(seeded.other_mentor_id),
        json=weekly_call_payload(seeded.go_track_id, title="Чужое изменение"),
    )
    updated = await client.put(
        f"/api/v1/mentor/profile/weekly-calls/{call_id}",
        headers=auth(seeded.mentor_id),
        json=weekly_call_payload(
            seeded.python_track_id,
            title="Обновлённый Python-созвон",
            weekday=4,
            starts_at_time="19:15:00",
            meeting_url="https://meet.example.com/weekly-updated",
        ),
    )

    assert other_mentor_update.status_code == 404
    assert other_mentor_update.json()["detail"]["code"] == "mentor_weekly_call_not_found"
    assert updated.status_code == 200, updated.text
    assert updated.json()["title"] == "Обновлённый Python-созвон"
    assert updated.json()["weekday"] == 4
    assert updated.json()["starts_at_time"] == "19:15:00"

    deleted = await client.delete(
        f"/api/v1/mentor/profile/weekly-calls/{call_id}",
        headers=auth(seeded.mentor_id),
    )
    profile_after_delete = await client.get(
        "/api/v1/mentor/profile",
        headers=auth(seeded.mentor_id),
    )
    admin_call = await client.post(
        "/api/v1/mentor/profile/weekly-calls",
        headers=auth(seeded.admin_id),
        json=weekly_call_payload(seeded.go_track_id, title="Go-созвон администратора"),
    )

    assert deleted.status_code == 204
    assert profile_after_delete.status_code == 200, profile_after_delete.text
    assert profile_after_delete.json()["weekly_calls"] == []
    assert admin_call.status_code == 201, admin_call.text
    assert admin_call.json()["mentor_id"] == str(seeded.admin_id)
    assert admin_call.json()["track"]["slug"] == "go"
    assert admin_call.json()["source_name"] == "Администратор"


async def test_mentor_activity_crud_profile_dashboard_tracks_and_owner(
    client: AsyncClient,
    seeded: SeededData,
) -> None:
    now = datetime.now(UTC)
    async with TestSession() as session:
        session.add(
            ScheduleEvent(
                track_id=seeded.python_track_id,
                mentor_id=seeded.mentor_id,
                created_by_user_id=seeded.mentor_id,
                kind=ScheduleEventKind.MEETING,
                title="Прошедшая активность",
                starts_at=now - timedelta(days=1),
            )
        )
        await session.commit()

    created = await client.post(
        "/api/v1/mentor/profile/activities",
        headers=auth(seeded.mentor_id),
        json=mentor_activity_payload(
            seeded.python_track_id,
            title="Дополнительный Python-созвон",
            starts_at=now + timedelta(days=2),
        ),
    )
    rejected_go = await client.post(
        "/api/v1/mentor/profile/activities",
        headers=auth(seeded.mentor_id),
        json=mentor_activity_payload(
            seeded.go_track_id,
            title="Недоступный Go-созвон",
            starts_at=now + timedelta(days=2),
        ),
    )
    naive_time = await client.post(
        "/api/v1/mentor/profile/activities",
        headers=auth(seeded.mentor_id),
        json={
            **mentor_activity_payload(
                seeded.python_track_id,
                title="Без часового пояса",
                starts_at=now + timedelta(days=2),
            ),
            "starts_at": (datetime.now() + timedelta(days=2)).isoformat(),
        },
    )
    past_time = await client.post(
        "/api/v1/mentor/profile/activities",
        headers=auth(seeded.mentor_id),
        json=mentor_activity_payload(
            seeded.python_track_id,
            title="В прошлом",
            starts_at=now - timedelta(minutes=1),
        ),
    )

    assert created.status_code == 201, created.text
    activity_id = created.json()["id"]
    assert created.json()["kind"] == "meeting"
    assert created.json()["mentor_id"] == str(seeded.mentor_id)
    assert created.json()["track"]["slug"] == "python"
    assert created.json()["meeting_url"] is None
    assert created.json()["regular_next_occurrence_at"] is None
    assert created.json()["next_occurrence_at"] is None
    assert created.json()["is_rescheduled"] is False
    assert rejected_go.status_code == 422
    assert rejected_go.json()["detail"]["code"] == "mentor_schedule_track_not_assigned"
    assert naive_time.status_code == 422
    assert past_time.status_code == 422

    other_update = await client.put(
        f"/api/v1/mentor/profile/activities/{activity_id}",
        headers=auth(seeded.other_mentor_id),
        json=mentor_activity_payload(
            seeded.go_track_id,
            title="Чужое изменение",
            starts_at=now + timedelta(days=3),
        ),
    )
    updated = await client.put(
        f"/api/v1/mentor/profile/activities/{activity_id}",
        headers=auth(seeded.mentor_id),
        json=mentor_activity_payload(
            seeded.python_track_id,
            title="Перенесённый дополнительный созвон",
            starts_at=now + timedelta(days=3),
            meeting_url="https://meet.example.com/extra",
        ),
    )
    profile = await client.get(
        "/api/v1/mentor/profile",
        headers=auth(seeded.mentor_id),
    )
    dashboard = await client.get(
        "/api/v1/me/mentor",
        headers=auth(seeded.student_id),
    )
    student_create = await client.post(
        "/api/v1/mentor/profile/activities",
        headers=auth(seeded.student_id),
        json=mentor_activity_payload(
            seeded.python_track_id,
            title="Студенческая активность",
            starts_at=now + timedelta(days=3),
        ),
    )

    assert other_update.status_code == 404
    assert other_update.json()["detail"]["code"] == "mentor_activity_not_found"
    assert updated.status_code == 200, updated.text
    assert updated.json()["title"] == "Перенесённый дополнительный созвон"
    assert updated.json()["meeting_url"] == "https://meet.example.com/extra"
    assert profile.status_code == 200, profile.text
    assert [item["title"] for item in profile.json()["one_off_activities"]] == [
        "Перенесённый дополнительный созвон"
    ]
    assert "Прошедшая активность" not in {
        item["title"] for item in profile.json()["one_off_activities"]
    }
    assert dashboard.status_code == 200, dashboard.text
    assert "Перенесённый дополнительный созвон" in {
        item["title"] for item in dashboard.json()["schedule"]
    }
    assert student_create.status_code == 403

    other_delete = await client.delete(
        f"/api/v1/mentor/profile/activities/{activity_id}",
        headers=auth(seeded.other_mentor_id),
    )
    deleted = await client.delete(
        f"/api/v1/mentor/profile/activities/{activity_id}",
        headers=auth(seeded.mentor_id),
    )
    admin_activity = await client.post(
        "/api/v1/mentor/profile/activities",
        headers=auth(seeded.admin_id),
        json=mentor_activity_payload(
            seeded.go_track_id,
            title="Go-активность администратора",
            starts_at=now + timedelta(days=4),
        ),
    )

    assert other_delete.status_code == 404
    assert deleted.status_code == 204
    assert admin_activity.status_code == 201, admin_activity.text
    assert admin_activity.json()["track"]["slug"] == "go"
    assert admin_activity.json()["mentor_id"] == str(seeded.admin_id)


async def test_weekly_call_reschedule_validates_window_owner_and_can_be_cancelled(
    client: AsyncClient,
    seeded: SeededData,
) -> None:
    created = await client.post(
        "/api/v1/mentor/profile/weekly-calls",
        headers=auth(seeded.mentor_id),
        json=weekly_call_payload(seeded.python_track_id),
    )
    assert created.status_code == 201, created.text
    call_id = created.json()["id"]
    original = datetime.fromisoformat(created.json()["regular_next_occurrence_at"])
    target = original + timedelta(hours=2)

    rescheduled = await client.put(
        f"/api/v1/mentor/profile/weekly-calls/{call_id}/reschedule",
        headers=auth(seeded.mentor_id),
        json={"starts_at": target.isoformat()},
    )
    assert rescheduled.status_code == 200, rescheduled.text
    assert rescheduled.json()["regular_next_occurrence_at"] == original.isoformat().replace(
        "+00:00", "Z"
    )
    assert rescheduled.json()["next_occurrence_at"] == target.isoformat().replace("+00:00", "Z")
    assert rescheduled.json()["is_rescheduled"] is True
    assert rescheduled.json()["rescheduled_from"] == original.isoformat().replace("+00:00", "Z")
    assert rescheduled.json()["rescheduled_to"] == target.isoformat().replace("+00:00", "Z")

    other_mentor = await client.put(
        f"/api/v1/mentor/profile/weekly-calls/{call_id}/reschedule",
        headers=auth(seeded.other_mentor_id),
        json={"starts_at": target.isoformat()},
    )
    out_of_range = await client.put(
        f"/api/v1/mentor/profile/weekly-calls/{call_id}/reschedule",
        headers=auth(seeded.mentor_id),
        json={"starts_at": (original + timedelta(days=7)).isoformat()},
    )
    naive = await client.put(
        f"/api/v1/mentor/profile/weekly-calls/{call_id}/reschedule",
        headers=auth(seeded.mentor_id),
        json={"starts_at": (datetime.now() + timedelta(days=1)).isoformat()},
    )
    assert other_mentor.status_code == 404
    assert other_mentor.json()["detail"]["code"] == "mentor_weekly_call_not_found"
    assert out_of_range.status_code == 422
    assert out_of_range.json()["detail"]["code"] == "weekly_call_reschedule_out_of_range"
    assert naive.status_code == 422

    cancelled = await client.delete(
        f"/api/v1/mentor/profile/weekly-calls/{call_id}/reschedule",
        headers=auth(seeded.mentor_id),
    )
    profile = await client.get(
        "/api/v1/mentor/profile",
        headers=auth(seeded.mentor_id),
    )
    call = profile.json()["weekly_calls"][0]
    assert cancelled.status_code == 204
    assert call["is_rescheduled"] is False
    assert call["rescheduled_from"] is None
    assert call["rescheduled_to"] is None
    assert call["next_occurrence_at"] == call["regular_next_occurrence_at"]

    rescheduled_again = await client.put(
        f"/api/v1/mentor/profile/weekly-calls/{call_id}/reschedule",
        headers=auth(seeded.mentor_id),
        json={"starts_at": target.isoformat()},
    )
    updated_base = await client.put(
        f"/api/v1/mentor/profile/weekly-calls/{call_id}",
        headers=auth(seeded.mentor_id),
        json=weekly_call_payload(seeded.python_track_id, title="Новый базовый график"),
    )
    assert rescheduled_again.status_code == 200, rescheduled_again.text
    assert updated_base.status_code == 200, updated_base.text
    assert updated_base.json()["is_rescheduled"] is False
    assert updated_base.json()["rescheduled_from"] is None
    assert updated_base.json()["rescheduled_to"] is None

    without_time_payload = weekly_call_payload(
        seeded.python_track_id,
        title="Без времени",
    )
    without_time_payload["starts_at_time"] = None
    without_time = await client.post(
        "/api/v1/mentor/profile/weekly-calls",
        headers=auth(seeded.mentor_id),
        json=without_time_payload,
    )
    missing_time_reschedule = await client.put(
        f"/api/v1/mentor/profile/weekly-calls/{without_time.json()['id']}/reschedule",
        headers=auth(seeded.mentor_id),
        json={"starts_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
    )
    assert without_time.status_code == 201, without_time.text
    assert missing_time_reschedule.status_code == 422
    assert missing_time_reschedule.json()["detail"]["code"] == "weekly_call_time_required"

    moved_earlier = await client.post(
        "/api/v1/mentor/profile/weekly-calls",
        headers=auth(seeded.mentor_id),
        json=weekly_call_payload(
            seeded.python_track_id,
            title="Уже состоявшийся перенос",
            weekday=3,
        ),
    )
    assert moved_earlier.status_code == 201, moved_earlier.text
    moved_id = UUID(moved_earlier.json()["id"])
    moved_original = datetime.fromisoformat(moved_earlier.json()["regular_next_occurrence_at"])
    async with TestSession() as session:
        event = await session.get(ScheduleEvent, moved_id)
        assert event is not None
        event.rescheduled_from = moved_original
        event.rescheduled_to = datetime.now(UTC) - timedelta(minutes=1)
        await session.commit()

    late_cancel = await client.delete(
        f"/api/v1/mentor/profile/weekly-calls/{moved_id}/reschedule",
        headers=auth(seeded.mentor_id),
    )
    next_regular = moved_original + timedelta(days=7)
    replacement_target = next_regular + timedelta(hours=1)
    next_reschedule = await client.put(
        f"/api/v1/mentor/profile/weekly-calls/{moved_id}/reschedule",
        headers=auth(seeded.mentor_id),
        json={"starts_at": replacement_target.isoformat()},
    )
    assert late_cancel.status_code == 409
    assert late_cancel.json()["detail"]["code"] == "weekly_call_reschedule_cannot_cancel"
    assert next_reschedule.status_code == 200, next_reschedule.text
    assert datetime.fromisoformat(next_reschedule.json()["rescheduled_from"]) == next_regular
    assert datetime.fromisoformat(next_reschedule.json()["rescheduled_to"]) == replacement_target


def test_weekly_occurrence_override_handles_early_and_late_reschedules() -> None:
    now = datetime(2026, 8, 4, 12, tzinfo=UTC)
    event = ScheduleEvent(
        kind=ScheduleEventKind.WEEKLY_CALL,
        weekday=(now.weekday() + 1) % 7,
        starts_at_time=time(18, 0),
        timezone="UTC",
    )
    original = _regular_next_weekly_occurrence(event, after=now)
    assert original is not None

    event.rescheduled_from = original
    event.rescheduled_to = now - timedelta(hours=1)
    regular, effective, active = _weekly_occurrences(event, now=now)
    assert regular == original
    assert effective == original + timedelta(days=7)
    assert active is False
    assert _reschedule_base_occurrence(event, now=now) == original + timedelta(days=7)

    after_original = original + timedelta(hours=1)
    event.rescheduled_to = original + timedelta(days=1)
    regular, effective, active = _weekly_occurrences(event, now=after_original)
    assert regular == original + timedelta(days=7)
    assert effective == event.rescheduled_to
    assert active is True

    after_override = event.rescheduled_to + timedelta(hours=1)
    regular, effective, active = _weekly_occurrences(event, now=after_override)
    assert effective == regular
    assert active is False


async def test_admin_schedule_crud_filters_pagination_and_access(
    client: AsyncClient,
    seeded: SeededData,
) -> None:
    now = datetime.now(UTC)
    python_weekly = await client.post(
        "/api/v1/admin/schedule/events",
        headers=auth(seeded.admin_id),
        json=admin_weekly_event_payload(
            seeded.python_track_id,
            title="Общий Python-созвон",
        ),
    )
    python_meeting = await client.post(
        "/api/v1/admin/schedule/events",
        headers=auth(seeded.admin_id),
        json=admin_meeting_payload(
            seeded.python_track_id,
            title="Встреча Python",
            starts_at=now + timedelta(days=2),
        ),
    )
    go_weekly = await client.post(
        "/api/v1/admin/schedule/events",
        headers=auth(seeded.admin_id),
        json=admin_weekly_event_payload(
            seeded.go_track_id,
            title="Общий Go-созвон",
            weekday=3,
        ),
    )

    for response in (python_weekly, python_meeting, go_weekly):
        assert response.status_code == 201, response.text
        assert response.json()["source"] == "platform"
        assert response.json()["mentor_id"] is None

    weekly_id = python_weekly.json()["id"]
    meeting_id = python_meeting.json()["id"]
    updated = await client.put(
        f"/api/v1/admin/schedule/events/{weekly_id}",
        headers=auth(seeded.admin_id),
        json=admin_weekly_event_payload(
            seeded.python_track_id,
            title="Обновлённый общий Python-созвон",
            weekday=5,
        ),
    )
    loaded = await client.get(
        f"/api/v1/admin/schedule/events/{weekly_id}",
        headers=auth(seeded.admin_id),
    )
    python_filter = await client.get(
        "/api/v1/admin/schedule/events",
        headers=auth(seeded.admin_id),
        params={"track_id": str(seeded.python_track_id)},
    )
    weekly_filter = await client.get(
        "/api/v1/admin/schedule/events",
        headers=auth(seeded.admin_id),
        params={"kind": "weekly_call"},
    )
    page = await client.get(
        "/api/v1/admin/schedule/events",
        headers=auth(seeded.admin_id),
        params={"limit": 1, "offset": 1},
    )

    assert updated.status_code == 200, updated.text
    assert updated.json()["title"] == "Обновлённый общий Python-созвон"
    assert updated.json()["weekday"] == 5
    assert loaded.status_code == 200, loaded.text
    assert loaded.json()["id"] == weekly_id

    assert python_filter.status_code == 200, python_filter.text
    assert python_filter.json()["total"] == 2
    assert {item["id"] for item in python_filter.json()["items"]} == {
        weekly_id,
        meeting_id,
    }
    assert weekly_filter.status_code == 200, weekly_filter.text
    assert weekly_filter.json()["total"] == 2
    assert {item["kind"] for item in weekly_filter.json()["items"]} == {"weekly_call"}
    assert page.status_code == 200, page.text
    assert page.json()["total"] == 3
    assert page.json()["limit"] == 1
    assert page.json()["offset"] == 1
    assert len(page.json()["items"]) == 1

    mentor_list = await client.get(
        "/api/v1/admin/schedule/events",
        headers=auth(seeded.mentor_id),
    )
    mentor_create = await client.post(
        "/api/v1/admin/schedule/events",
        headers=auth(seeded.mentor_id),
        json=admin_weekly_event_payload(
            seeded.python_track_id,
            title="Недоступное событие",
        ),
    )
    deleted = await client.delete(
        f"/api/v1/admin/schedule/events/{meeting_id}",
        headers=auth(seeded.admin_id),
    )
    deleted_read = await client.get(
        f"/api/v1/admin/schedule/events/{meeting_id}",
        headers=auth(seeded.admin_id),
    )

    assert mentor_list.status_code == 403
    assert mentor_create.status_code == 403
    assert deleted.status_code == 204
    assert deleted_read.status_code == 404


async def test_my_mentor_dashboard_shows_only_relevant_schedule(
    client: AsyncClient,
    seeded: SeededData,
) -> None:
    profile = await client.put(
        "/api/v1/mentor/profile",
        headers=auth(seeded.mentor_id),
        json={
            "consultation_url": "https://cal.example.com/anton/consultation",
            "group_calendar_url": "https://cal.example.com/anton/group",
        },
    )
    own_call = await client.post(
        "/api/v1/mentor/profile/weekly-calls",
        headers=auth(seeded.mentor_id),
        json=weekly_call_payload(
            seeded.python_track_id,
            title="Созвон моего ментора",
        ),
    )

    async with TestSession() as session:
        session.add(
            MentorTrackAssignment(
                mentor_id=seeded.other_mentor_id,
                track_id=seeded.python_track_id,
            )
        )
        await session.commit()

    other_call = await client.post(
        "/api/v1/mentor/profile/weekly-calls",
        headers=auth(seeded.other_mentor_id),
        json=weekly_call_payload(
            seeded.python_track_id,
            title="Созвон другого ментора",
            weekday=3,
        ),
    )
    global_python_call = await client.post(
        "/api/v1/admin/schedule/events",
        headers=auth(seeded.admin_id),
        json=admin_weekly_event_payload(
            seeded.python_track_id,
            title="Общий Python-созвон",
        ),
    )
    future_python_meeting = await client.post(
        "/api/v1/admin/schedule/events",
        headers=auth(seeded.admin_id),
        json=admin_meeting_payload(
            seeded.python_track_id,
            title="Будущая встреча Python",
            starts_at=datetime.now(UTC) + timedelta(days=3),
        ),
    )
    past_python_meeting = await client.post(
        "/api/v1/admin/schedule/events",
        headers=auth(seeded.admin_id),
        json=admin_meeting_payload(
            seeded.python_track_id,
            title="Прошедшая встреча Python",
            starts_at=datetime.now(UTC) - timedelta(days=3),
        ),
    )
    global_go_call = await client.post(
        "/api/v1/admin/schedule/events",
        headers=auth(seeded.admin_id),
        json=admin_weekly_event_payload(
            seeded.go_track_id,
            title="Общий Go-созвон",
        ),
    )

    for response in (
        profile,
        own_call,
        other_call,
        global_python_call,
        future_python_meeting,
        past_python_meeting,
        global_go_call,
    ):
        assert response.status_code in {200, 201}, response.text

    dashboard = await client.get(
        "/api/v1/me/mentor",
        headers=auth(seeded.student_id),
    )

    assert dashboard.status_code == 200, dashboard.text
    mentor = dashboard.json()["mentor"]
    assert mentor is not None
    assert mentor["id"] == str(seeded.mentor_id)
    assert mentor["first_name"] == "Антон"
    assert mentor["consultation_url"] == "https://cal.example.com/anton/consultation"
    assert mentor["group_calendar_url"] == "https://cal.example.com/anton/group"
    assert dashboard.json()["useful_links"] == []

    schedule = {item["title"]: item for item in dashboard.json()["schedule"]}
    assert set(schedule) == {
        "Созвон моего ментора",
        "Общий Python-созвон",
        "Будущая встреча Python",
    }
    assert schedule["Созвон моего ментора"]["source"] == "mentor"
    assert schedule["Созвон моего ментора"]["source_name"] == "Антон"
    assert schedule["Общий Python-созвон"]["source"] == "platform"
    assert schedule["Общий Python-созвон"]["source_name"] == "Платформа"
    assert schedule["Будущая встреча Python"]["kind"] == "meeting"
    assert all(item["track"]["slug"] == "python" for item in schedule.values())


async def test_unassigned_student_still_sees_global_track_schedule(
    client: AsyncClient,
    seeded: SeededData,
) -> None:
    unassigned_id = uuid4()
    async with TestSession() as session:
        session.add(
            User(
                id=unassigned_id,
                first_name="Без ментора",
                role=UserRole.STUDENT,
            )
        )
        await session.flush()
        session.add(
            LearningTrackEnrollment(
                user_id=unassigned_id,
                track_id=seeded.python_track_id,
            )
        )
        await session.commit()

    mentor_call = await client.post(
        "/api/v1/mentor/profile/weekly-calls",
        headers=auth(seeded.mentor_id),
        json=weekly_call_payload(
            seeded.python_track_id,
            title="Закрытый созвон ментора",
        ),
    )
    global_call = await client.post(
        "/api/v1/admin/schedule/events",
        headers=auth(seeded.admin_id),
        json=admin_weekly_event_payload(
            seeded.python_track_id,
            title="Доступный общий созвон",
        ),
    )
    later_link = await client.post(
        "/api/v1/admin/useful-links",
        headers=auth(seeded.admin_id),
        json=useful_link_payload(
            title="Практика",
            description="Задачи для самостоятельной работы",
            url="https://learn.example.com/practice",
            position=20,
        ),
    )
    first_link = await client.post(
        "/api/v1/admin/useful-links",
        headers=auth(seeded.admin_id),
        json=useful_link_payload(
            title="Старт",
            description="Материалы для начала обучения",
            url="https://learn.example.com/start",
            position=10,
        ),
    )

    assert mentor_call.status_code == 201, mentor_call.text
    assert global_call.status_code == 201, global_call.text
    assert later_link.status_code == 201, later_link.text
    assert first_link.status_code == 201, first_link.text

    dashboard = await client.get(
        "/api/v1/me/mentor",
        headers=auth(unassigned_id),
    )

    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["mentor"] is None
    assert [item["title"] for item in dashboard.json()["schedule"]] == ["Доступный общий созвон"]
    assert dashboard.json()["schedule"][0]["source"] == "platform"
    assert [item["title"] for item in dashboard.json()["useful_links"]] == [
        "Старт",
        "Практика",
    ]
    assert dashboard.json()["useful_links"][0]["url"] == "https://learn.example.com/start"
