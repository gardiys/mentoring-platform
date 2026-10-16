from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.legal.models import LegalCheckout, LegalOfferVersion
from app.opportunities.models import (
    ConsultationMentorSetting,
    ConsultationRequest,
    ConsultationStatus,
    GoTransitionApplication,
    GoTransitionStatus,
    OpportunityPaymentAttempt,
)
from app.opportunities.service import approve_opportunity_payment
from app.opportunities.workspace_models import ConsultationRequestHistory
from app.payments.models import MentorReward, PaymentAttemptStatus
from tests.conftest import SeededData, TestSession, auth
from tests.legal_helpers import approved_application, legal_checkout
from tests.test_opportunities import _graduate_python


async def consultation(client: AsyncClient, seeded: SeededData, status: str = "requested") -> UUID:
    await _graduate_python(seeded)
    response = await client.post(
        "/api/v1/opportunities/consultations",
        headers=auth(seeded.student_id),
        json={
            "consultation_type": "technical_mock",
            "mentor_id": str(seeded.mentor_id),
            "brief": "Подготовиться к техническому собеседованию",
        },
    )
    assert response.status_code == 200, response.text
    resource_id = UUID(response.json()["consultations"][0]["id"])
    if status != "requested":
        async with TestSession() as session:
            item = await session.get(ConsultationRequest, resource_id)
            item.status = ConsultationStatus(status)
            if status in {"paid", "scheduled", "completed"}:
                item.paid_at = datetime.now(UTC)
            if status == "scheduled":
                item.scheduled_at = datetime.now(UTC) - timedelta(hours=4)
            await session.commit()
    return resource_id


async def test_consultation_commands_keep_private_notes_and_accrue_once_to_current_mentor(
    client: AsyncClient, seeded: SeededData
):
    resource_id = await consultation(client, seeded)
    prefix = f"/api/v1/admin/opportunities/consultations/{resource_id}"
    approved = await client.post(
        prefix + "/approve",
        headers=auth(seeded.admin_id),
        json={"mentor_id": str(seeded.mentor_id), "message_to_student": "Можно оплатить"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["stage"] == "awaiting_payment"
    async with TestSession() as session:
        item = await session.get(ConsultationRequest, resource_id)
        item.status, item.paid_at = ConsultationStatus.PAID, datetime.now(UTC)
        session.add(ConsultationMentorSetting(mentor_id=seeded.admin_id, is_enabled=True))
        await session.commit()
    changed = await client.post(
        prefix + "/mentor", headers=auth(seeded.admin_id), json={"mentor_id": str(seeded.admin_id)}
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["mentor"]["id"] == str(seeded.admin_id)
    note = await client.patch(
        prefix + "/internal-note",
        headers=auth(seeded.admin_id),
        json={"internal_note": "Только для команды"},
    )
    assert note.status_code == 200, note.text
    student = await client.get("/api/v1/opportunities/me", headers=auth(seeded.student_id))
    public = student.json()["consultations"][0]
    assert (
        "internal_note" not in public
        and "last_payment" not in public
        and "mentor_reward_kopecks" not in public
    )
    naive = await client.post(
        prefix + "/schedule",
        headers=auth(seeded.admin_id),
        json={"scheduled_at": "2026-10-15T10:00:00"},
    )
    assert naive.status_code == 422
    scheduled = await client.post(
        prefix + "/schedule",
        headers=auth(seeded.admin_id),
        json={"scheduled_at": (datetime.now(UTC) - timedelta(hours=4)).isoformat()},
    )
    assert scheduled.status_code == 200, scheduled.text
    assert scheduled.json()["stage"] == "needs_completion"
    completed = await client.post(
        prefix + "/complete",
        headers=auth(seeded.admin_id),
        json={"written_summary": "Рекомендации и дальнейший план действий"},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["internal_note"] == "Только для команды"
    duplicate = await client.post(
        prefix + "/complete",
        headers=auth(seeded.admin_id),
        json={"written_summary": "Повторное завершение консультации"},
    )
    assert duplicate.status_code == 409
    fixed = await client.patch(
        prefix + "/summary",
        headers=auth(seeded.admin_id),
        json={"written_summary": "Исправленные рекомендации и следующий шаг"},
    )
    assert fixed.status_code == 200, fixed.text
    async with TestSession() as session:
        rewards = list(
            await session.scalars(
                select(MentorReward).where(MentorReward.consultation_request_id == resource_id)
            )
        )
        assert len(rewards) == 1 and rewards[0].mentor_id == seeded.admin_id
        history = list(
            await session.scalars(
                select(ConsultationRequestHistory).where(
                    ConsultationRequestHistory.consultation_request_id == resource_id
                )
            )
        )
        assert {event.snapshot.get("action") for event in history} >= {
            "approve",
            "mentor",
            "internal-note",
            "schedule",
            "complete",
            "summary",
        }


@pytest.mark.parametrize("status", ["paid", "scheduled"])
@pytest.mark.parametrize("refund", [True, False])
async def test_paid_cancellation_requires_refund_choice_and_never_accrues(
    client: AsyncClient, seeded: SeededData, status: str, refund: bool
):
    resource_id = await consultation(client, seeded, status)
    path = f"/api/v1/admin/opportunities/consultations/{resource_id}/cancel"
    reason = "Встреча не состоялась по договорённости"
    rejected = await client.post(path, headers=auth(seeded.admin_id), json={"reason": reason})
    assert rejected.status_code == 422
    response = await client.post(
        path, headers=auth(seeded.admin_id), json={"reason": reason, "refund_required": refund}
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled" and response.json()["refund_required"] is refund
    async with TestSession() as session:
        assert await session.scalar(select(func.count()).select_from(MentorReward)) == 0


async def test_failed_completion_does_not_mutate_fields(client: AsyncClient, seeded: SeededData):
    resource_id = await consultation(client, seeded, "payment_pending")
    async with TestSession() as session:
        item = await session.get(ConsultationRequest, resource_id)
        item.status = ConsultationStatus.PAID
        await session.commit()
    response = await client.post(
        f"/api/v1/admin/opportunities/consultations/{resource_id}/complete",
        headers=auth(seeded.admin_id),
        json={"written_summary": "Не должно сохраниться без оплаты"},
    )
    assert response.status_code == 409
    async with TestSession() as session:
        item = await session.get(ConsultationRequest, resource_id)
        assert item.written_summary is None and item.completed_at is None
        assert await session.scalar(select(func.count()).select_from(MentorReward)) == 0


async def test_manual_review_of_old_link_is_visible_and_confirmation_unblocks_scheduling(
    client: AsyncClient, seeded: SeededData
):
    resource_id = await consultation(client, seeded, "payment_pending")
    async with TestSession() as session:
        old = OpportunityPaymentAttempt(
            id=uuid4(),
            consultation_request_id=resource_id,
            payment_link_id="old-link",
            status=PaymentAttemptStatus.REVOKED,
            created_at=datetime.now(UTC) - timedelta(hours=1),
        )
        current = OpportunityPaymentAttempt(
            id=uuid4(),
            consultation_request_id=resource_id,
            payment_link_id="current-link",
            status=PaymentAttemptStatus.PENDING,
        )
        session.add_all([old, current])
        await session.flush()
        await approve_opportunity_payment(session, old)
        await session.commit()
        old_id, current_id = old.id, current.id
    detail = await client.get(
        f"/api/v1/admin/opportunities/consultations/{resource_id}", headers=auth(seeded.admin_id)
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["stage"] == "payment_review"
    inbox = await client.get("/api/v1/admin/opportunities/inbox", headers=auth(seeded.admin_id))
    assert inbox.status_code == 200, inbox.text
    assert inbox.json()["items"][0]["stage"] == "payment_review"
    confirmed = await client.post(
        f"/api/v1/admin/opportunities/payments/{old_id}/confirm", headers=auth(seeded.admin_id)
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "paid"
    assert confirmed.json()["stage"] == "needs_schedule"
    async with TestSession() as session:
        assert (
            await session.get(OpportunityPaymentAttempt, current_id)
        ).status is PaymentAttemptStatus.REVOKED
        history = list(
            await session.scalars(
                select(ConsultationRequestHistory).where(
                    ConsultationRequestHistory.consultation_request_id == resource_id
                )
            )
        )
        assert any(
            row.snapshot.get("action") == "payment" and row.actor_user_id is None for row in history
        )


async def test_go_extension_resets_acceptance_and_makes_checkout_available(
    client: AsyncClient, seeded: SeededData
):
    application_id = await approved_application(client, seeded, "python_to_go_transition")
    async with TestSession() as session:
        item = await session.get(GoTransitionApplication, UUID(application_id))
        item.terms_expires_at = datetime.now(UTC) - timedelta(days=1)
        item.terms_accepted_at = datetime.now(UTC) - timedelta(days=2)
        item.accepted_terms_snapshot = {"old": True}
        await session.commit()
    result = await client.post(
        f"/api/v1/admin/opportunities/go-transition/{application_id}/extend",
        headers=auth(seeded.admin_id),
    )
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "approved"
    assert result.json()["accepted_terms_snapshot"] is None
    assert datetime.fromisoformat(result.json()["terms_expires_at"]) > datetime.now(
        UTC
    ) + timedelta(days=13)
    checkout = await legal_checkout(
        client, seeded.student_id, "python_to_go_transition", application_id
    )
    assert checkout.status_code == 200, checkout.text


async def test_go_cancellation_allows_new_application_and_keeps_notes_private(
    client: AsyncClient, seeded: SeededData
):
    application_id = await approved_application(client, seeded, "python_to_go_transition")
    path = f"/api/v1/admin/opportunities/go-transition/{application_id}"
    note = await client.patch(
        path + "/internal-note",
        headers=auth(seeded.admin_id),
        json={"internal_note": "Служебная заметка"},
    )
    assert note.status_code == 200, note.text
    public = await client.get("/api/v1/opportunities/me", headers=auth(seeded.student_id))
    assert "internal_note" not in public.json()["go_transition_applications"][0]
    cancelled = await client.post(
        path + "/cancel",
        headers=auth(seeded.admin_id),
        json={"reason": "Отмена по просьбе выпускника"},
    )
    assert cancelled.status_code == 200, cancelled.text
    created = await client.post(
        "/api/v1/opportunities/go-transition",
        headers=auth(seeded.student_id),
        json={"motivation": "Хочу подать новую заявку на Go"},
    )
    assert created.status_code == 200, created.text


@pytest.mark.parametrize("blocker", ["pending", "approved", "manual_review", "checkout"])
async def test_go_cancel_and_extend_cannot_race_an_active_payment(
    client: AsyncClient, seeded: SeededData, blocker: str
):
    application_id = UUID(await approved_application(client, seeded, "python_to_go_transition"))
    async with TestSession() as session:
        item = await session.get(GoTransitionApplication, application_id)
        item.terms_expires_at = datetime.now(UTC) - timedelta(days=1)
        if blocker == "checkout":
            offer_id = await session.scalar(
                select(LegalOfferVersion.id).where(
                    LegalOfferVersion.product_code == "python_to_go_transition"
                )
            )
            session.add(
                LegalCheckout(
                    user_id=seeded.student_id,
                    product_code="python_to_go_transition",
                    application_id=application_id,
                    offer_version_id=offer_id,
                    status="pending",
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                    snapshot={},
                )
            )
        else:
            session.add(
                OpportunityPaymentAttempt(
                    transition_application_id=application_id,
                    payment_link_id=str(uuid4()),
                    status=PaymentAttemptStatus(blocker),
                )
            )
        await session.commit()
    for action in ["extend", "cancel"]:
        response = await client.post(
            f"/api/v1/admin/opportunities/go-transition/{application_id}/{action}",
            headers=auth(seeded.admin_id),
            json={"reason": "Отмена по просьбе выпускника"} if action == "cancel" else {},
        )
        assert response.status_code == 409, response.text
    async with TestSession() as session:
        assert (
            await session.get(GoTransitionApplication, application_id)
        ).status is GoTransitionStatus.APPROVED


@pytest.mark.parametrize(
    "action, method, body",
    [
        ("schedule", "POST", {"scheduled_at": "2026-10-16T10:00:00+03:00"}),
        ("complete", "POST", {"written_summary": "Разобрали дальнейший план действий"}),
        ("summary", "PATCH", {"written_summary": "Исправленный дальнейший план действий"}),
        ("cancel", "POST", {"reason": "Отмена по просьбе выпускника"}),
    ],
)
async def test_commands_reject_wrong_source_status(
    client: AsyncClient, seeded: SeededData, action: str, method: str, body: dict
):
    resource_id = await consultation(client, seeded)
    response = await client.request(
        method,
        f"/api/v1/admin/opportunities/consultations/{resource_id}/{action}",
        headers=auth(seeded.admin_id),
        json=body,
    )
    assert response.status_code == 409, response.text


@pytest.mark.parametrize("role", ["student", "mentor"])
@pytest.mark.parametrize(
    "path, method, body",
    [
        ("inbox", "GET", {}),
        ("settings", "GET", {}),
        ("consultations", "GET", {}),
        ("go-transition", "GET", {}),
        ("python-repeat", "GET", {}),
        ("consultations/{id}", "GET", {}),
        ("go-transition/{id}", "GET", {}),
        ("python-repeat/{id}", "GET", {}),
        ("consultations/{id}/approve", "POST", {"mentor_id": str(uuid4())}),
        ("consultations/{id}/reject", "POST", {"reason": "Достаточно длинная причина"}),
        ("consultations/{id}/mentor", "POST", {"mentor_id": str(uuid4())}),
        ("consultations/{id}/schedule", "POST", {"scheduled_at": "2026-10-16T10:00:00+03:00"}),
        (
            "consultations/{id}/complete",
            "POST",
            {"written_summary": "Достаточно длинный итог встречи"},
        ),
        ("consultations/{id}/summary", "PATCH", {"written_summary": "Исправленный итог встречи"}),
        ("consultations/{id}/cancel", "POST", {"reason": "Достаточно длинная причина"}),
        ("consultations/{id}/internal-note", "PATCH", {"internal_note": "Заметка"}),
        ("go-transition/{id}/approve", "POST", {}),
        ("go-transition/{id}/reject", "POST", {"reason": "Достаточно длинная причина"}),
        ("go-transition/{id}/cancel", "POST", {"reason": "Достаточно длинная причина"}),
        ("go-transition/{id}/extend", "POST", {}),
        ("go-transition/{id}/internal-note", "PATCH", {"internal_note": "Заметка"}),
    ],
)
async def test_workspace_endpoints_are_admin_only(
    client: AsyncClient, seeded: SeededData, role: str, path: str, method: str, body: dict
):
    response = await client.request(
        method,
        "/api/v1/admin/opportunities/" + path.format(id=uuid4()),
        headers=auth(getattr(seeded, role + "_id")),
        json=body,
    )
    assert response.status_code == 403, response.text


async def test_lists_paginate_beyond_200_and_inbox_prioritizes_oldest_overdue(
    client: AsyncClient, seeded: SeededData
):
    await consultation(client, seeded)
    ids = [uuid4() for _ in range(205)]
    now = datetime.now(UTC)
    async with TestSession() as session:
        session.add_all(
            [
                ConsultationRequest(
                    id=resource_id,
                    student_id=seeded.student_id,
                    mentor_id=seeded.mentor_id,
                    consultation_type="work_task" if index == 2 else "technical_mock",
                    brief="Проверка очереди заявок",
                    price_kopecks=400_000,
                    mentor_reward_kopecks=250_000,
                    duration_minutes=60,
                    status=ConsultationStatus.COMPLETED
                    if index == 0
                    else ConsultationStatus.PAID
                    if index == 1
                    else ConsultationStatus.REQUESTED,
                    created_at=now - timedelta(days=2),
                    paid_at=now - timedelta(days=5) if index == 1 else None,
                )
                for index, resource_id in enumerate(ids)
            ]
        )
        await session.commit()
    root = "/api/v1/admin/opportunities"
    page = await client.get(
        root + "/consultations?group=all&page=3&page_size=100", headers=auth(seeded.admin_id)
    )
    assert page.status_code == 200, page.text
    assert page.json()["total"] == 206 and len(page.json()["items"]) == 6
    active = await client.get(root + "/consultations", headers=auth(seeded.admin_id))
    assert active.json()["total"] == 205 and len(active.json()["items"]) == 25
    found = await client.get(root + f"/consultations?q={ids[2]}", headers=auth(seeded.admin_id))
    assert found.json()["total"] == 1 and found.json()["items"][0]["id"] == str(ids[2])
    typed = await client.get(
        root + f"/consultations?consultation_type=work_task&mentor_id={seeded.mentor_id}",
        headers=auth(seeded.admin_id),
    )
    assert typed.json()["total"] == 1
    inbox = await client.get(root + "/inbox", headers=auth(seeded.admin_id))
    assert inbox.status_code == 200, inbox.text
    assert inbox.json()["items"][0]["id"] == str(ids[1])
    assert inbox.json()["items"][0]["overdue"] is True
    assert str(ids[0]) not in {item["id"] for item in inbox.json()["items"]}


async def test_repeat_drafts_are_hidden_and_sql_stages_agree_with_details(
    client: AsyncClient, seeded: SeededData
):
    from app.opportunities.models import PythonRepeatApplication, PythonRepeatApplicationStatus

    application_id = UUID(await approved_application(client, seeded, "repeat_python_mentorship"))
    for status, expected in [
        ("draft", None),
        ("submitted", "new"),
        ("under_review", "review"),
        ("needs_clarification", "awaiting_student"),
        ("approved", "awaiting_payment"),
        ("paid", "needs_mentor"),
        ("enrolled", "needs_mentor"),
        ("cancelled", "closed"),
    ]:
        async with TestSession() as session:
            item = await session.get(PythonRepeatApplication, application_id)
            item.status = PythonRepeatApplicationStatus(status)
            await session.commit()
        result = await client.get(
            "/api/v1/admin/opportunities/python-repeat?group=all", headers=auth(seeded.admin_id)
        )
        assert result.status_code == 200, result.text
        detail = await client.get(
            f"/api/v1/admin/opportunities/python-repeat/{application_id}",
            headers=auth(seeded.admin_id),
        )
        if expected is None:
            assert result.json()["total"] == 0 and detail.status_code == 404
        else:
            assert detail.status_code == 200, detail.text
            assert result.json()["items"][0]["stage"] == expected
            assert detail.json()["stage"] == expected


@pytest.mark.schema_change
async def test_workspace_migration_downgrades_and_upgrades_without_touching_financial_tables(
    seeded: SeededData,
):
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect, text

    from tests.conftest import test_engine

    file = Path(__file__).parents[1] / "migrations/versions/20261016_0101_opportunity_workspace.py"
    spec = importlib.util.spec_from_file_location("opportunity_workspace_migration", file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    async with test_engine.begin() as connection:

        def exercise(sync):
            context = MigrationContext.configure(sync)
            with Operations.context(context):
                module.downgrade()
                assert "consultation_request_history" not in inspect(sync).get_table_names()
                assert "internal_note" not in {
                    column["name"] for column in inspect(sync).get_columns("consultation_requests")
                }
                assert "legal_checkouts" in inspect(sync).get_table_names()
                assert "opportunity_payment_attempts" in inspect(sync).get_table_names()
                assert sync.scalar(text("SELECT count(*) FROM users")) >= 4
                module.upgrade()
                assert "consultation_request_history" in inspect(sync).get_table_names()
                assert "internal_note" in {
                    column["name"] for column in inspect(sync).get_columns("consultation_requests")
                }

        await connection.run_sync(exercise)


async def test_scheduling_notifies_student_and_mentor_with_moscow_time_and_contacts(
    client: AsyncClient, seeded: SeededData
):
    from app.notifications.models import PlatformNotification, TelegramOutbox
    from app.users.models import User

    resource_id = await consultation(client, seeded, "paid")
    async with TestSession() as session:
        student = await session.get(User, seeded.student_id)
        mentor = await session.get(User, seeded.mentor_id)
        student.telegram_id, student.telegram_username = 330011, "graduate_handle"
        mentor.telegram_id = 330012
        await session.commit()
    result = await client.post(
        f"/api/v1/admin/opportunities/consultations/{resource_id}/schedule",
        headers=auth(seeded.admin_id),
        json={"scheduled_at": "2026-10-20T16:00:00Z"},
    )
    assert result.status_code == 200, result.text
    assert result.json()["requested_mentor"]["id"] == str(seeded.mentor_id)
    async with TestSession() as session:
        telegram = list(
            await session.scalars(
                select(TelegramOutbox).where(
                    TelegramOutbox.event_key.like("telegram:consultation:%")
                )
            )
        )
        assert len(telegram) == 2
        mentor_message = next(message for message in telegram if message.chat_id == "330012")
        assert "19:00 МСК" in mentor_message.text
        assert "@graduate_handle" in mentor_message.text
        assert "Техническое мок-собеседование" in mentor_message.text
        assert mentor_message.action_url is None
        bell = await session.scalar(
            select(PlatformNotification).where(PlatformNotification.user_id == seeded.mentor_id)
        )
        assert bell is not None and bell.action_url == ""


async def test_reject_consultation_revokes_no_payment_and_notifies_with_reason(
    client: AsyncClient, seeded: SeededData
):
    resource_id = await consultation(client, seeded)
    reason = "Запрос не подходит для разовой консультации"
    response = await client.post(
        f"/api/v1/admin/opportunities/consultations/{resource_id}/reject",
        headers=auth(seeded.admin_id),
        json={"reason": reason},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"
    assert response.json()["admin_note"] == reason
    repeated = await client.post(
        f"/api/v1/admin/opportunities/consultations/{resource_id}/approve",
        headers=auth(seeded.admin_id),
        json={"mentor_id": str(seeded.mentor_id)},
    )
    assert repeated.status_code == 409


async def test_concurrent_completion_creates_one_reward(client: AsyncClient, seeded: SeededData):
    import asyncio

    resource_id = await consultation(client, seeded, "paid")

    async def complete():
        return await client.post(
            f"/api/v1/admin/opportunities/consultations/{resource_id}/complete",
            headers=auth(seeded.admin_id),
            json={"written_summary": "Обсудили рекомендации и дальнейшие шаги"},
        )

    results = await asyncio.gather(complete(), complete())
    assert sorted(result.status_code for result in results) == [200, 409]
    async with TestSession() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(MentorReward)
                .where(MentorReward.consultation_request_id == resource_id)
            )
            == 1
        )
