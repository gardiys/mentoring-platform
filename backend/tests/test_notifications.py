from datetime import UTC, date, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from httpx import AsyncClient
from pydantic import SecretStr
from pytest import MonkeyPatch
from sqlalchemy import func, select

from app.core.config import get_settings
from app.interviews.models import (
    Company,
    InterviewProcess,
    InterviewProcessStage,
    InterviewStageType,
)
from app.mentors.models import StudentLearningStatus, StudentMentorshipState
from app.notifications import jobs as notification_jobs
from app.notifications import service as notification_service
from app.notifications.jobs import (
    _reminder_kind,
    schedule_daily_reminders,
    schedule_group_call_reminders,
)
from app.notifications.models import (
    NotificationKind,
    PlatformNotification,
    TelegramOutbox,
)
from app.schedule.models import ScheduleEvent, ScheduleEventKind
from app.tracks.models import LearningTrackEnrollment
from app.users.models import User, UserRole
from tests.conftest import SeededData, TestSession, auth


async def test_notification_inbox_is_private_and_can_be_marked_read(
    client: AsyncClient, seeded: SeededData
) -> None:
    own_id = uuid4()
    other_id = uuid4()
    async with TestSession() as session:
        session.add_all(
            [
                PlatformNotification(
                    id=own_id,
                    user_id=seeded.student_id,
                    kind=NotificationKind.STATUS_CHANGED,
                    title="Статус изменён",
                    body="Теперь вы ходите на собеседования.",
                    action_url="/my-mentor",
                    event_key=f"own:{own_id}",
                ),
                PlatformNotification(
                    id=other_id,
                    user_id=seeded.mentor_id,
                    kind=NotificationKind.MOCK_INTERVIEW,
                    title="Чужое уведомление",
                    body="Не должно быть видно.",
                    action_url="/mentor/students",
                    event_key=f"other:{other_id}",
                ),
            ]
        )
        await session.commit()

    response = await client.get(
        "/api/v1/notifications", headers=auth(seeded.student_id)
    )
    assert response.status_code == 200
    assert response.json()["unread_count"] == 1
    assert [item["id"] for item in response.json()["items"]] == [str(own_id)]

    forbidden = await client.put(
        f"/api/v1/notifications/{other_id}/read",
        headers=auth(seeded.student_id),
    )
    assert forbidden.status_code == 404

    marked = await client.put(
        f"/api/v1/notifications/{own_id}/read",
        headers=auth(seeded.student_id),
    )
    assert marked.status_code == 204
    response = await client.get(
        "/api/v1/notifications", headers=auth(seeded.student_id)
    )
    assert response.json()["unread_count"] == 0


async def test_mentor_status_change_notifies_student_once(
    client: AsyncClient, seeded: SeededData
) -> None:
    response = await client.patch(
        f"/api/v1/mentor/students/{seeded.student_id}/state",
        headers=auth(seeded.mentor_id),
        json={"learning_status": "interviewing", "strength_level": "medium"},
    )
    assert response.status_code == 200

    same_status = await client.patch(
        f"/api/v1/mentor/students/{seeded.student_id}/state",
        headers=auth(seeded.mentor_id),
        json={"learning_status": "interviewing", "strength_level": "strong"},
    )
    assert same_status.status_code == 200

    async with TestSession() as session:
        rows = list(
            await session.scalars(
                select(PlatformNotification).where(
                    PlatformNotification.user_id == seeded.student_id,
                    PlatformNotification.kind == NotificationKind.STATUS_CHANGED,
                )
            )
        )
    assert len(rows) == 1
    assert "ходит на собеседования" in rows[0].body


async def test_new_interview_targets_track_and_queues_one_telegram_message(
    seeded: SeededData, monkeypatch: MonkeyPatch
) -> None:
    second_student_id = uuid4()
    company_id = uuid4()
    process_id = uuid4()
    stage_id = uuid4()
    local_settings = get_settings().model_copy(
        update={
            "telegram_interview_chat_id": "-1009999999999",
            "telegram_group_topic_id": 999,
            "telegram_interview_python_chat_id": "-1001234567890",
            "telegram_interview_python_topic_id": 321,
            "web_frontend_url": "https://platform.example.test",
        }
    )
    monkeypatch.setattr(notification_service, "settings", local_settings)

    async with TestSession() as session:
        actor = await session.get(User, seeded.student_id)
        assert actor is not None
        actor.telegram_username = "student"
        second_student = User(
            id=second_student_id,
            first_name="Пётр",
            role=UserRole.STUDENT,
        )
        session.add(second_student)
        await session.flush()
        session.add(
            LearningTrackEnrollment(
                user_id=second_student_id,
                track_id=seeded.python_track_id,
            )
        )
        session.add(
            Company(
                id=company_id,
                name="Example",
                normalized_name="example",
                transliterated_name="example",
            )
        )
        process = InterviewProcess(
            id=process_id,
            user_id=seeded.student_id,
            track_id=seeded.python_track_id,
            company_id=company_id,
            company_name="Example",
        )
        stage = InterviewProcessStage(
            id=stage_id,
            process_id=process_id,
            stage_type=InterviewStageType.TECHNICAL_INTERVIEW,
            scheduled_at=datetime.now(UTC),
            description="Python и PostgreSQL",
            media_storage_key="interviews/test.mp4",
            media_filename="test.mp4",
            media_content_type="video/mp4",
            media_size=100,
        )
        session.add_all([process, stage])
        await session.flush()

        await notification_service.notify_interview_published(
            session, actor=actor, process=process, stage=stage
        )
        await notification_service.notify_interview_published(
            session, actor=actor, process=process, stage=stage
        )
        await session.commit()

        recipient_ids = set(
            await session.scalars(
                select(PlatformNotification.user_id).where(
                    PlatformNotification.kind == NotificationKind.INTERVIEW_PUBLISHED
                )
            )
        )
        telegram_count = await session.scalar(
            select(func.count()).select_from(TelegramOutbox)
        )
        telegram_row = await session.scalar(select(TelegramOutbox))

    assert second_student_id in recipient_ids
    assert seeded.mentor_id in recipient_ids
    assert seeded.admin_id in recipient_ids
    assert seeded.other_mentor_id not in recipient_ids
    assert seeded.student_id not in recipient_ids
    assert telegram_count == 1
    assert telegram_row is not None
    assert telegram_row.chat_id == "-1001234567890"
    assert telegram_row.message_thread_id == 321
    assert "Автор: Иван (@student)" in telegram_row.text
    assert "Описание собеседования:\nPython и PostgreSQL" in telegram_row.text
    assert "https://platform.example.test" not in telegram_row.text
    assert telegram_row.action_label == "Смотреть собеседование ↗"
    assert telegram_row.action_url == (
        f"https://platform.example.test/interviews/catalog/{company_id}?stage={stage_id}"
    )


def test_payment_reminder_schedule_avoids_daily_overdue_spam() -> None:
    today = date(2026, 8, 15)
    assert _reminder_kind(date(2026, 8, 18), today) == "soon"
    assert _reminder_kind(today, today) == "today"
    assert _reminder_kind(date(2026, 8, 14), today) == "overdue"
    assert _reminder_kind(date(2026, 8, 13), today) is None
    assert _reminder_kind(date(2026, 8, 12), today) == "overdue"
    assert _reminder_kind(date(2026, 8, 7), today) is None
    assert _reminder_kind(date(2026, 8, 1), today) == "overdue"


def test_telegram_action_url_rejects_localhost(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        notification_service,
        "settings",
        get_settings().model_copy(
            update={"app_env": "development", "web_frontend_url": "http://localhost:5173"}
        ),
    )
    assert notification_service.telegram_action_url("/interviews/catalog/test") is None


def test_telegram_action_url_accepts_public_https(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        notification_service,
        "settings",
        get_settings().model_copy(
            update={
                "app_env": "production",
                "web_frontend_url": "https://platform.codewaste.ru",
            }
        ),
    )
    assert notification_service.telegram_action_url("/payments") == (
        "https://platform.codewaste.ru/payments"
    )


def test_telegram_interview_text_respects_api_limit() -> None:
    prefix = "Новое собеседование\nhttps://platform.codewaste.ru/interviews/catalog/test"
    message = notification_service._fit_telegram_message(prefix, "Описание\n" * 2_000)
    assert len(message) <= 4_096
    assert message.endswith("…")


def test_interview_destination_is_selected_by_direction(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        notification_service,
        "settings",
        get_settings().model_copy(
            update={
                "telegram_interview_chat_id": "-1000000000000",
                "telegram_group_topic_id": 10,
                "telegram_interview_python_chat_id": "-1001111111111",
                "telegram_interview_python_topic_id": 11,
                "telegram_interview_go_chat_id": "-1002222222222",
                "telegram_interview_go_topic_id": 22,
            }
        ),
    )
    assert notification_service._telegram_interview_destination("python") == (
        "-1001111111111",
        11,
    )
    assert notification_service._telegram_interview_destination("Go") == (
        "-1002222222222",
        22,
    )
    assert notification_service._telegram_interview_destination("other") == (
        "-1000000000000",
        10,
    )


async def test_group_call_reminders_follow_track_and_mentor_visibility(
    seeded: SeededData, monkeypatch: MonkeyPatch
) -> None:
    second_student_id = uuid4()
    mentor_event_id = uuid4()
    platform_event_id = uuid4()
    now = datetime.now(UTC)
    monkeypatch.setattr(notification_jobs, "async_session_factory", TestSession)
    monkeypatch.setattr(
        notification_jobs,
        "settings",
        get_settings().model_copy(
            update={
                "telegram_bot_token": SecretStr("test-token"),
                "telegram_group_call_reminders_enabled": True,
                "telegram_group_call_reminder_minutes": 30,
            }
        ),
    )
    async with TestSession() as session:
        student = await session.get(User, seeded.student_id)
        assert student is not None
        student.telegram_id = 1001
        session.add(
            User(
                id=second_student_id,
                first_name="Пётр",
                role=UserRole.STUDENT,
                telegram_id=1002,
            )
        )
        await session.flush()
        session.add(
            LearningTrackEnrollment(
                user_id=second_student_id,
                track_id=seeded.python_track_id,
            )
        )
        session.add_all(
            [
                ScheduleEvent(
                    id=mentor_event_id,
                    track_id=seeded.python_track_id,
                    mentor_id=seeded.mentor_id,
                    created_by_user_id=seeded.mentor_id,
                    kind=ScheduleEventKind.MEETING,
                    title="Созвон с ментором",
                    description="Разберём вопросы",
                    meeting_url="https://meet.example.test/mentor",
                    starts_at=now + timedelta(minutes=20),
                ),
                ScheduleEvent(
                    id=platform_event_id,
                    track_id=seeded.python_track_id,
                    mentor_id=None,
                    created_by_user_id=seeded.admin_id,
                    kind=ScheduleEventKind.MEETING,
                    title="Общий созвон",
                    meeting_url="https://meet.example.test/platform",
                    starts_at=now + timedelta(minutes=25),
                ),
            ]
        )
        await session.commit()

    await schedule_group_call_reminders({})
    await schedule_group_call_reminders({})

    async with TestSession() as session:
        rows = list(
            await session.scalars(
                select(TelegramOutbox).where(
                    TelegramOutbox.event_key.like("telegram:group-call:%")
                )
            )
        )
    assert len(rows) == 3
    assert {row.chat_id for row in rows if str(mentor_event_id) in row.event_key} == {
        "1001"
    }
    assert {row.chat_id for row in rows if str(platform_event_id) in row.event_key} == {
        "1001",
        "1002",
    }
    assert all(row.action_label == "Подключиться к созвону ↗" for row in rows)


async def test_daily_reminder_is_personal_idempotent_and_skips_finished_students(
    seeded: SeededData, monkeypatch: MonkeyPatch
) -> None:
    finished_id = uuid4()
    local_now = datetime.now(ZoneInfo("Europe/Moscow"))
    monkeypatch.setattr(notification_jobs, "async_session_factory", TestSession)
    monkeypatch.setattr(
        notification_jobs,
        "settings",
        get_settings().model_copy(
            update={
                "telegram_bot_token": SecretStr("test-token"),
                "telegram_daily_reminders_enabled": True,
                "telegram_daily_reminder_hour": local_now.hour,
                "notification_reminder_timezone": "Europe/Moscow",
            }
        ),
    )
    async with TestSession() as session:
        student = await session.get(User, seeded.student_id)
        assert student is not None
        student.telegram_id = 2001
        session.add(
            User(
                id=finished_id,
                first_name="Завершивший",
                role=UserRole.STUDENT,
                telegram_id=2002,
            )
        )
        await session.flush()
        session.add(
            StudentMentorshipState(
                student_id=finished_id,
                learning_status=StudentLearningStatus.FINISHED,
            )
        )
        await session.commit()

    await schedule_daily_reminders({})
    await schedule_daily_reminders({})

    async with TestSession() as session:
        rows = list(
            await session.scalars(
                select(TelegramOutbox).where(
                    TelegramOutbox.event_key.like("telegram:daily-reminder:%")
                )
            )
        )
    assert len(rows) == 1
    assert rows[0].chat_id == "2001"
    assert "написать дейлик" in rows[0].text
