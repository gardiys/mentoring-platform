from decimal import Decimal
from uuid import UUID

from httpx import AsyncClient
from pydantic import SecretStr
from pytest import MonkeyPatch
from sqlalchemy import func, select

from app.auth import dependencies as auth_dependencies
from app.integrations import dependencies as integration_dependencies
from app.mentors.models import MentorStudent
from app.payments.models import MentorReward, MentorRewardKind
from app.roadmaps.models import RoadmapEnrollment
from app.tracks.models import LearningTrackEnrollment
from app.users.models import User
from tests.conftest import SeededData, TestSession
from tests.test_auth_and_health import BOT_TOKEN, telegram_auth

INTEGRATION_TOKEN = "integration-test-token-with-enough-entropy"


def integration_auth(token: str = INTEGRATION_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def student_payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "telegram_id": 987654321,
        "telegram_username": "@paid_student",
        "first_name": "Оплаченный",
        "last_name": "Ученик",
        "email": "paid@example.com",
        "track_slug": "python",
    }
    payload.update(changes)
    return payload


async def test_bot_integration_requires_configured_valid_token(
    client: AsyncClient, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(integration_dependencies.settings, "bot_integration_token", None)
    unavailable = await client.post(
        "/api/v1/integrations/telegram/students", json=student_payload()
    )

    monkeypatch.setattr(
        integration_dependencies.settings,
        "bot_integration_token",
        SecretStr(INTEGRATION_TOKEN),
    )
    invalid = await client.post(
        "/api/v1/integrations/telegram/students",
        headers=integration_auth("wrong-token"),
        json=student_payload(),
    )

    assert unavailable.status_code == 503
    assert unavailable.json()["detail"]["code"] == "bot_integration_unavailable"
    assert invalid.status_code == 401


async def test_bot_provisions_paid_student_and_grants_selected_track(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        integration_dependencies.settings,
        "bot_integration_token",
        SecretStr(INTEGRATION_TOKEN),
    )
    monkeypatch.setattr(auth_dependencies.settings, "telegram_bot_token", SecretStr(BOT_TOKEN))

    provisioned = await client.post(
        "/api/v1/integrations/telegram/students",
        headers=integration_auth(),
        json=student_payload(),
    )
    async with TestSession() as session:
        student = await session.scalar(select(User).where(User.telegram_id == 987654321))
        assert student is not None
        assert student.telegram_username == "paid_student"
        assert student.repayment_percent == Decimal("200.00")
    me = await client.get("/api/v1/me", headers=telegram_auth())
    roadmaps = await client.get("/api/v1/roadmaps", headers=telegram_auth())

    assert provisioned.status_code == 200
    assert provisioned.json()["created"] is True
    assert provisioned.json()["access_created"] is True
    assert provisioned.json()["track"]["id"] == str(seeded.python_track_id)
    assert provisioned.json()["roadmaps"][0]["id"] == str(seeded.roadmap_id)
    assert me.status_code == 200
    assert me.json()["telegram_id"] == 987654321
    assert me.json()["onboarding_completed_at"] is not None
    assert [item["slug"] for item in roadmaps.json()] == ["python-backend"]


async def test_bot_can_set_custom_student_repayment_percent(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        integration_dependencies.settings,
        "bot_integration_token",
        SecretStr(INTEGRATION_TOKEN),
    )
    response = await client.post(
        "/api/v1/integrations/telegram/students",
        headers=integration_auth(),
        json=student_payload(track_slug="go", repayment_percent=175),
    )

    assert response.status_code == 200, response.text
    assert response.json()["track"]["id"] == str(seeded.go_track_id)
    async with TestSession() as session:
        student = await session.scalar(select(User).where(User.telegram_id == 987654321))
        assert student is not None
        assert student.repayment_percent == Decimal("175.00")


async def test_bot_sets_custom_mentor_terms_and_entry_reward(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        integration_dependencies.settings,
        "bot_integration_token",
        SecretStr(INTEGRATION_TOKEN),
    )
    async with TestSession() as session:
        mentor = await session.get(User, seeded.mentor_id)
        assert mentor is not None
        mentor.telegram_id = 123450001
        await session.commit()

    response = await client.post(
        "/api/v1/integrations/telegram/students",
        headers=integration_auth(),
        json=student_payload(
            mentor_telegram_id=123450001,
            mentor_reward_percent=55,
            entry_payment_rubles=50_000,
            entry_payment_paid=True,
        ),
    )
    assert response.status_code == 200, response.text
    student_id = response.json()["user"]["id"]

    async with TestSession() as session:
        relation = await session.scalar(
            select(MentorStudent).where(MentorStudent.student_id == student_id)
        )
        reward = await session.scalar(
            select(MentorReward).where(
                MentorReward.student_id == student_id,
                MentorReward.kind == MentorRewardKind.ENTRY_PAYMENT,
            )
        )
        student = await session.get(User, student_id)
        assert relation is not None
        assert relation.reward_percent == Decimal("55.00")
        assert student is not None
        assert student.entry_payment_kopecks == 5_000_000
        assert reward is not None
        assert reward.amount_kopecks == 1_000_000
        assert reward.basis_kopecks == 5_000_000


async def test_bot_provisioning_is_idempotent_without_overwriting_student_data(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        integration_dependencies.settings,
        "bot_integration_token",
        SecretStr(INTEGRATION_TOKEN),
    )
    first = await client.post(
        "/api/v1/integrations/telegram/students",
        headers=integration_auth(),
        json=student_payload(),
    )
    second = await client.post(
        "/api/v1/integrations/telegram/students",
        headers=integration_auth(),
        json=student_payload(first_name="Новое имя"),
    )

    async with TestSession() as session:
        user_count = await session.scalar(
            select(func.count(User.id)).where(User.telegram_id == 987654321)
        )
        enrollment_count = await session.scalar(
            select(func.count(RoadmapEnrollment.user_id)).where(
                RoadmapEnrollment.user_id == first.json()["user"]["id"]
            )
        )
        access_count = await session.scalar(
            select(func.count(LearningTrackEnrollment.user_id)).where(
                LearningTrackEnrollment.user_id == first.json()["user"]["id"]
            )
        )

    assert first.status_code == second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["access_created"] is False
    assert second.json()["user"]["id"] == first.json()["user"]["id"]
    assert second.json()["user"]["first_name"] == "Оплаченный"
    assert user_count == enrollment_count == access_count == 1


async def test_replayed_bot_event_cannot_clear_confirmed_entry_payment(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        integration_dependencies.settings,
        "bot_integration_token",
        SecretStr(INTEGRATION_TOKEN),
    )
    first = await client.post(
        "/api/v1/integrations/telegram/students",
        headers=integration_auth(),
        json=student_payload(entry_payment_paid=True),
    )
    replay = await client.post(
        "/api/v1/integrations/telegram/students",
        headers=integration_auth(),
        json=student_payload(entry_payment_paid=False),
    )

    assert first.status_code == replay.status_code == 200
    async with TestSession() as session:
        student = await session.scalar(select(User).where(User.telegram_id == 987654321))
        assert student is not None
        assert student.entry_payment_paid_at is not None


async def test_replayed_bot_event_cannot_restore_suspended_student_access(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        integration_dependencies.settings,
        "bot_integration_token",
        SecretStr(INTEGRATION_TOKEN),
    )
    first = await client.post(
        "/api/v1/integrations/telegram/students",
        headers=integration_auth(),
        json=student_payload(),
    )
    await client.patch(
        f"/api/v1/admin/students/{first.json()['user']['id']}/access",
        headers={"X-Dev-User-Id": str(seeded.admin_id)},
        json={"is_active": False},
    )
    revoked = await client.delete(
        f"/api/v1/admin/tracks/{seeded.python_track_id}/students/{first.json()['user']['id']}",
        headers={"X-Dev-User-Id": str(seeded.admin_id)},
    )

    restored = await client.post(
        "/api/v1/integrations/telegram/students",
        headers=integration_auth(),
        json=student_payload(),
    )

    assert revoked.status_code == 204
    assert restored.status_code == 200
    assert restored.json()["access_created"] is False
    assert restored.json()["roadmaps"] == []
    assert restored.json()["user"]["is_active"] is False
    async with TestSession() as session:
        access = await session.get(
            LearningTrackEnrollment,
            {
                "user_id": UUID(first.json()["user"]["id"]),
                "track_id": seeded.python_track_id,
            },
        )
        assert access is None


async def test_replayed_bot_event_cannot_overwrite_admin_managed_student_terms(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        integration_dependencies.settings,
        "bot_integration_token",
        SecretStr(INTEGRATION_TOKEN),
    )
    async with TestSession() as session:
        mentor = await session.get(User, seeded.mentor_id)
        other_mentor = await session.get(User, seeded.other_mentor_id)
        assert mentor is not None and other_mentor is not None
        mentor.telegram_id = 123450001
        other_mentor.telegram_id = 123450002
        await session.commit()

    first = await client.post(
        "/api/v1/integrations/telegram/students",
        headers=integration_auth(),
        json=student_payload(
            mentor_telegram_id=123450001,
            repayment_percent=210,
            mentor_reward_percent=55,
            entry_payment_rubles=50_000,
            entry_payment_paid=True,
        ),
    )
    assert first.status_code == 200, first.text
    student_id = first.json()["user"]["id"]

    async with TestSession() as session:
        student = await session.get(User, student_id)
        relation = await session.scalar(
            select(MentorStudent).where(MentorStudent.student_id == student_id)
        )
        assert student is not None and relation is not None
        student.first_name = "Исправленное имя"
        student.last_name = "Администратором"
        student.email = "canonical@example.com"
        student.is_active = False
        student.repayment_percent = Decimal("180")
        student.entry_payment_kopecks = 4_500_000
        relation.mentor_id = seeded.other_mentor_id
        relation.reward_percent = Decimal("40")
        await session.commit()

    replay = await client.post(
        "/api/v1/integrations/telegram/students",
        headers=integration_auth(),
        json=student_payload(
            first_name="Устаревшее имя",
            last_name="Из бота",
            email="stale@example.com",
            track_slug="go",
            mentor_telegram_id=123450001,
            repayment_percent=300,
            mentor_reward_percent=90,
            entry_payment_rubles=90_000,
            entry_payment_paid=False,
        ),
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["created"] is False
    assert replay.json()["access_created"] is False

    async with TestSession() as session:
        student = await session.get(User, student_id)
        relation = await session.scalar(
            select(MentorStudent).where(MentorStudent.student_id == student_id)
        )
        go_access = await session.get(
            LearningTrackEnrollment,
            {"user_id": student_id, "track_id": seeded.go_track_id},
        )
        assert student is not None and relation is not None
        assert go_access is None
        assert student.first_name == "Исправленное имя"
        assert student.last_name == "Администратором"
        assert student.email == "canonical@example.com"
        assert student.is_active is False
        assert student.repayment_percent == Decimal("180.00")
        assert student.entry_payment_kopecks == 4_500_000
        assert student.entry_payment_paid_at is not None
        assert relation.mentor_id == seeded.other_mentor_id
        assert relation.reward_percent == Decimal("40.00")


async def test_bot_rejects_unknown_direction_without_creating_student(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        integration_dependencies.settings,
        "bot_integration_token",
        SecretStr(INTEGRATION_TOKEN),
    )
    response = await client.post(
        "/api/v1/integrations/telegram/students",
        headers=integration_auth(),
        json=student_payload(track_slug="unknown-direction"),
    )

    async with TestSession() as session:
        user = await session.scalar(select(User).where(User.telegram_id == 987654321))

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "track_not_found"
    assert user is None
