from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.notifications.models import PlatformNotification, TelegramOutbox
from app.opportunities.models import (
    ConsultationRequest,
    ConsultationStatus,
    OpportunityPaymentAttempt,
)
from app.opportunities.notifications import (
    mark_payment_for_review,
    notify_admins,
    opportunity_digest,
)
from app.opportunities.stages import consultation_stage, go_transition_stage, python_repeat_stage
from app.users.models import User, UserRole
from tests.conftest import SeededData, TestSession, auth
from tests.test_opportunities import _graduate_python

NOW = datetime(2026, 10, 16, 7, tzinfo=UTC)


@pytest.mark.parametrize(
    "status, hours, manual, expected, overdue",
    [
        ("requested", 24, False, "new", False),
        ("requested", 25, False, "new", True),
        ("payment_pending", 0, False, "awaiting_payment", False),
        ("payment_pending", 0, True, "payment_review", True),
        ("paid", 48, False, "needs_schedule", False),
        ("paid", 49, False, "needs_schedule", True),
        ("scheduled", -2, False, "scheduled", False),
        ("scheduled", 1, False, "needs_completion", False),
        ("scheduled", 3, False, "needs_completion", False),
        ("scheduled", 4, False, "needs_completion", True),
        ("completed", 100, False, "completed", False),
        ("cancelled", 100, False, "cancelled", False),
    ],
)
def test_consultation_stages(status, hours, manual, expected, overdue):
    since = NOW - timedelta(hours=hours)
    item = SimpleNamespace(
        status=status,
        created_at=since,
        paid_at=since,
        updated_at=since,
        scheduled_at=since,
        duration_minutes=60,
    )
    result = consultation_stage(item, at=NOW, manual_review_at=NOW if manual else None)
    assert result.stage == expected
    assert result.overdue is overdue


@pytest.mark.parametrize(
    "status, expired, expected",
    [
        ("submitted", False, "new"),
        ("approved", False, "awaiting_student"),
        ("payment_pending", False, "awaiting_student"),
        ("approved", True, "expired"),
        ("payment_pending", True, "expired"),
        ("paid", True, "enrolled"),
        ("rejected", True, "closed"),
        ("cancelled", True, "closed"),
    ],
)
def test_go_stages(status, expired, expected):
    item = SimpleNamespace(
        status=status,
        created_at=NOW,
        terms_expires_at=NOW + timedelta(seconds=-1 if expired else 1),
    )
    assert go_transition_stage(item, at=NOW).stage == expected


@pytest.mark.parametrize(
    "status, mentor, offer, expected",
    [
        ("submitted", False, False, "new"),
        ("under_review", False, False, "review"),
        ("needs_diagnostic", False, False, "awaiting_student"),
        ("needs_clarification", False, False, "awaiting_student"),
        ("approved", False, False, "awaiting_payment"),
        ("terms_accepted", False, False, "awaiting_payment"),
        ("payment_pending", False, False, "awaiting_payment"),
        ("paid", False, False, "needs_mentor"),
        ("enrolled", False, True, "needs_mentor"),
        ("enrolled", True, True, "offer_review"),
        ("enrolled", True, False, "active"),
        ("rejected", True, False, "closed"),
        ("cancelled", False, True, "closed"),
        ("expired", False, False, "closed"),
    ],
)
def test_repeat_stages(status, mentor, offer, expected):
    item = SimpleNamespace(status=status, created_at=NOW, updated_at=NOW, paid_at=NOW)
    enrollment = SimpleNamespace(mentor_id=uuid4() if mentor else None)
    assert (
        python_repeat_stage(
            item, enrollment=enrollment, submitted_offer_at=NOW if offer else None, at=NOW
        ).stage
        == expected
    )


async def test_new_application_notifications_summary_and_daily_digest(
    client: AsyncClient, seeded: SeededData
):
    await _graduate_python(seeded)
    second_admin, inactive_admin = uuid4(), uuid4()
    async with TestSession() as session:
        admin = await session.get(User, seeded.admin_id)
        admin.telegram_id = 990010
        session.add_all(
            [
                User(
                    id=second_admin,
                    telegram_id=990011,
                    first_name="Второй",
                    role=UserRole.ADMIN,
                    is_active=True,
                ),
                User(
                    id=inactive_admin,
                    telegram_id=990012,
                    first_name="Неактивный",
                    role=UserRole.ADMIN,
                    is_active=False,
                ),
            ]
        )
        await session.commit()
    created = await client.post(
        "/api/v1/opportunities/consultations",
        headers=auth(seeded.student_id),
        json={"consultation_type": "technical_mock", "brief": "Разобрать карьерный план"},
    )
    assert created.status_code == 200, created.text
    resource_id = UUID(created.json()["consultations"][0]["id"])
    async with TestSession() as session:
        notes = list(await session.scalars(select(PlatformNotification)))
        assert {note.user_id for note in notes} == {seeded.admin_id, second_admin}
        assert all(
            note.action_url == f"/admin/opportunities?consultation={resource_id}" for note in notes
        )
        telegram = list(await session.scalars(select(TelegramOutbox)))
        assert len(telegram) == 2
        assert len({message.event_key for message in telegram}) == 2
        await notify_admins(
            session,
            event_key=f"consultation-requested:{resource_id}",
            title="Повтор",
            body="Повтор",
            link="/admin/opportunities",
        )
        item = await session.get(ConsultationRequest, resource_id)
        item.created_at = NOW - timedelta(days=2)
        await session.commit()
        await opportunity_digest(session, at=NOW)
        await opportunity_digest(session, at=NOW)
        await session.commit()
        assert len(list(await session.scalars(select(PlatformNotification)))) == 4
        assert len(list(await session.scalars(select(TelegramOutbox)))) == 4
    response = await client.get(
        "/api/v1/admin/opportunities/summary", headers=auth(seeded.admin_id)
    )
    assert response.status_code == 200, response.text
    assert response.json()["needs_action_total"] == 1
    assert response.json()["consultations"] == {"new": 1}
    assert response.json()["overdue_total"] == 1
    for user_id in [seeded.student_id, seeded.mentor_id]:
        assert (
            await client.get("/api/v1/admin/opportunities/summary", headers=auth(user_id))
        ).status_code == 403
    async with TestSession() as session:
        item = await session.get(ConsultationRequest, resource_id)
        item.status = ConsultationStatus.PAYMENT_PENDING
        attempt = OpportunityPaymentAttempt(
            consultation_request_id=resource_id, payment_link_id="test-review"
        )
        session.add(attempt)
        await session.flush()
        await mark_payment_for_review(session, attempt)
        await mark_payment_for_review(session, attempt)
        await session.commit()
    response = await client.get(
        "/api/v1/admin/opportunities/summary", headers=auth(seeded.admin_id)
    )
    assert response.json()["consultations"] == {"payment_review": 1}
