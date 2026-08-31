from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import parse_qs, urlparse
from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import select

from app.opportunities.models import (
    ConsultationMentorSetting,
    ConsultationRequest,
    ConsultationType,
    GoTransitionApplication,
    GoTransitionStatus,
    ProgramCompletion,
)
from app.payments.models import MentorReward, MentorRewardKind
from app.tracks.models import LearningTrackEnrollment
from app.users.models import User
from tests.conftest import SeededData, TestSession, auth


async def _graduate_python(seeded: SeededData, *, with_email: bool = True) -> None:
    async with TestSession() as session:
        student = await session.get(User, seeded.student_id)
        assert student is not None
        if with_email:
            student.email = "graduate@example.com"
        session.add(
            ProgramCompletion(
                user_id=seeded.student_id,
                track_id=seeded.python_track_id,
                completed_at=datetime.now(UTC),
                recorded_by_user_id=seeded.admin_id,
            )
        )
        session.add(
            ConsultationMentorSetting(
                mentor_id=seeded.mentor_id,
                is_enabled=True,
                updated_by_user_id=seeded.admin_id,
            )
        )
        await session.commit()


async def test_active_student_does_not_see_paid_consultation(
    client: AsyncClient, seeded: SeededData
) -> None:
    response = await client.get("/api/v1/opportunities/me", headers=auth(seeded.student_id))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["segment"] == "ACTIVE_STUDENT"
    assert body["has_active_program"] is True
    assert body["has_alumni_access"] is False
    assert body["opportunities"][0]["available"] is False
    assert body["opportunities"][1]["available"] is False


async def test_alumnus_consultation_uses_backend_price_and_creates_mentor_reward(
    client: AsyncClient, seeded: SeededData
) -> None:
    await _graduate_python(seeded)
    dashboard = await client.get("/api/v1/opportunities/me", headers=auth(seeded.student_id))
    assert dashboard.status_code == 200, dashboard.text
    body = dashboard.json()
    assert body["segment"] == "PYTHON_ALUMNI"
    offer = body["opportunities"][0]
    assert offer["available"] is True
    assert offer["price"]["amount_kopecks"] == 400_000
    assert offer["comparison_price"]["amount_kopecks"] == 500_000
    work_task = next(item for item in body["consultation_types"] if item["code"] == "work_task")
    assert work_task["price_kopecks"] == 600_000
    assert work_task["comparison_price_kopecks"] == 700_000
    assert work_task["mentor_reward_kopecks"] == 300_000
    assert work_task["duration_minutes"] == 60

    created = await client.post(
        "/api/v1/opportunities/consultations",
        headers=auth(seeded.student_id),
        json={
            "mentor_id": str(seeded.mentor_id),
            "consultation_type": "work_task",
            "brief": "Разобрать карьерный план",
        },
    )
    assert created.status_code == 200, created.text
    request_id = created.json()["consultations"][0]["id"]
    async with TestSession() as session:
        request = await session.get(ConsultationRequest, UUID(request_id))
        assert request is not None
        assert request.price_kopecks == 600_000
        assert request.mentor_reward_kopecks == 300_000
        assert request.duration_minutes == 60
        assert request.consultation_type is ConsultationType.WORK_TASK

    approved = await client.patch(
        f"/api/v1/admin/opportunities/consultations/{request_id}",
        headers=auth(seeded.admin_id),
        json={"status": "payment_pending", "mentor_id": str(seeded.mentor_id)},
    )
    assert approved.status_code == 200, approved.text
    link = await client.post(
        f"/api/v1/opportunities/consultations/{request_id}/payment-link",
        headers=auth(seeded.student_id),
    )
    assert link.status_code == 200, link.text
    payment_link_id = parse_qs(urlparse(link.json()["payment_url"]).query)["local_payment"][0]
    webhook = await client.post(
        "/api/v1/payments/tochka/webhook",
        json={
            "eventType": "acquiringInternetPayment",
            "eventId": "evt-alumni-consultation",
            "Data": {
                "paymentLinkId": payment_link_id,
                "operationId": "op-alumni-consultation",
                "status": "APPROVED",
            },
        },
    )
    assert webhook.status_code == 200, webhook.text
    assert webhook.json() == {"status": "ok"}
    paid = await client.get("/api/v1/opportunities/me", headers=auth(seeded.student_id))
    assert paid.status_code == 200, paid.text
    assert paid.json()["consultations"][0]["status"] == "paid"
    async with TestSession() as session:
        reward = await session.scalar(
            select(MentorReward).where(MentorReward.consultation_request_id == UUID(request_id))
        )
        assert reward is not None
        assert reward.kind is MentorRewardKind.CONSULTATION
        assert reward.amount_kopecks == 300_000


async def test_any_mentor_request_requires_admin_assignment_before_payment(
    client: AsyncClient, seeded: SeededData
) -> None:
    await _graduate_python(seeded)
    created = await client.post(
        "/api/v1/opportunities/consultations",
        headers=auth(seeded.student_id),
        json={
            "mentor_id": None,
            "consultation_type": "technical_mock",
            "brief": "Провести техническое мок-собеседование по Python",
        },
    )
    assert created.status_code == 200, created.text
    request = created.json()["consultations"][0]
    assert request["mentor"] is None
    assert request["price_kopecks"] == 400_000
    assert request["mentor_reward_kopecks"] == 250_000

    without_mentor = await client.patch(
        f"/api/v1/admin/opportunities/consultations/{request['id']}",
        headers=auth(seeded.admin_id),
        json={"status": "payment_pending", "mentor_id": None},
    )
    assert without_mentor.status_code == 422, without_mentor.text

    assigned = await client.patch(
        f"/api/v1/admin/opportunities/consultations/{request['id']}",
        headers=auth(seeded.admin_id),
        json={"status": "payment_pending", "mentor_id": str(seeded.mentor_id)},
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["consultations"][0]["mentor"]["id"] == str(seeded.mentor_id)


async def test_admin_controls_which_mentors_offer_consultations(
    client: AsyncClient, seeded: SeededData
) -> None:
    await _graduate_python(seeded)
    disabled = await client.patch(
        f"/api/v1/admin/opportunities/consultation-mentors/{seeded.mentor_id}",
        headers=auth(seeded.admin_id),
        json={"is_enabled": False},
    )
    assert disabled.status_code == 200, disabled.text
    mentor = next(
        item
        for item in disabled.json()["consultation_mentors"]
        if item["id"] == str(seeded.mentor_id)
    )
    assert mentor["is_enabled"] is False

    dashboard = await client.get("/api/v1/opportunities/me", headers=auth(seeded.student_id))
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["opportunities"][0]["available"] is False
    assert dashboard.json()["mentors"] == []


async def test_admin_configures_consultation_type_prices_for_new_requests(
    client: AsyncClient, seeded: SeededData
) -> None:
    configured = await client.patch(
        "/api/v1/admin/opportunities/consultation-types/technical_mock",
        headers=auth(seeded.admin_id),
        json={
            "price_kopecks": 650_000,
            "comparison_price_kopecks": 750_000,
            "mentor_reward_kopecks": 325_000,
            "duration_minutes": 90,
        },
    )
    assert configured.status_code == 200, configured.text
    price = next(
        item for item in configured.json()["consultation_types"] if item["code"] == "technical_mock"
    )
    assert price["price_kopecks"] == 650_000
    assert price["comparison_price_kopecks"] == 750_000
    assert price["mentor_reward_kopecks"] == 325_000
    assert price["duration_minutes"] == 90

    await _graduate_python(seeded)
    created = await client.post(
        "/api/v1/opportunities/consultations",
        headers=auth(seeded.student_id),
        json={
            "mentor_id": None,
            "consultation_type": "technical_mock",
            "brief": "Проверить технические знания перед собеседованием",
        },
    )
    assert created.status_code == 200, created.text
    request = created.json()["consultations"][0]
    assert request["price_kopecks"] == 650_000
    assert request["mentor_reward_kopecks"] == 325_000
    assert request["duration_minutes"] == 90

    invalid = await client.patch(
        "/api/v1/admin/opportunities/consultation-types/technical_mock",
        headers=auth(seeded.admin_id),
        json={
            "price_kopecks": 700_000,
            "comparison_price_kopecks": 600_000,
            "mentor_reward_kopecks": 300_000,
            "duration_minutes": 60,
        },
    )
    assert invalid.status_code == 422, invalid.text


async def test_admin_updates_go_transition_program_description(
    client: AsyncClient, seeded: SeededData
) -> None:
    description = "## Новая программа\n\n- Go core\n- Практика backend\n- Подготовка к офферу"
    updated = await client.patch(
        "/api/v1/admin/opportunities/go-transition-program",
        headers=auth(seeded.admin_id),
        json={"description_markdown": description},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["go_transition_description_markdown"] == description

    student_view = await client.get(
        "/api/v1/opportunities/me",
        headers=auth(seeded.student_id),
    )
    assert student_view.status_code == 200, student_view.text
    assert student_view.json()["go_transition_description_markdown"] == description


async def test_python_alumnus_transition_requires_approval_acceptance_and_payment(
    client: AsyncClient, seeded: SeededData
) -> None:
    await _graduate_python(seeded)
    created = await client.post(
        "/api/v1/opportunities/go-transition",
        headers=auth(seeded.student_id),
        json={"motivation": "Хочу перейти в Go backend и развиваться дальше"},
    )
    assert created.status_code == 200, created.text
    application = created.json()["go_transition_applications"][0]
    assert application["upfront_price_kopecks"] == 3_000_000
    assert application["success_fee_percent"] == 100
    application_id = application["id"]

    decided = await client.patch(
        f"/api/v1/admin/opportunities/go-transition/{application_id}",
        headers=auth(seeded.admin_id),
        json={"approved": True, "admin_note": "Подтверждено"},
    )
    assert decided.status_code == 200, decided.text
    accepted = await client.post(
        f"/api/v1/opportunities/go-transition/{application_id}/accept",
        headers=auth(seeded.student_id),
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["go_transition_applications"][0]["status"] == "payment_pending"
    link = await client.post(
        f"/api/v1/opportunities/go-transition/{application_id}/payment-link",
        headers=auth(seeded.student_id),
    )
    assert link.status_code == 200, link.text
    payment_link_id = parse_qs(urlparse(link.json()["payment_url"]).query)["local_payment"][0]
    paid = await client.post(
        f"/api/v1/opportunities/payments/{payment_link_id}/development/complete",
        headers=auth(seeded.student_id),
    )
    assert paid.status_code == 200, paid.text
    assert paid.json()["go_transition_applications"][0]["status"] == "paid"

    async with TestSession() as session:
        enrollment = await session.get(
            LearningTrackEnrollment,
            {"user_id": seeded.student_id, "track_id": seeded.go_track_id},
        )
        student = await session.get(User, seeded.student_id)
        application_model = await session.get(GoTransitionApplication, UUID(application_id))
        assert enrollment is not None
        assert student is not None
        assert student.repayment_percent == Decimal("100")
        assert student.entry_payment_kopecks == 3_000_000
        assert application_model is not None
        assert application_model.status is GoTransitionStatus.PAID


async def test_go_application_cannot_be_duplicated(client: AsyncClient, seeded: SeededData) -> None:
    await _graduate_python(seeded)
    payload = {"motivation": "Хочу освоить Go для нового рабочего проекта"}
    first = await client.post(
        "/api/v1/opportunities/go-transition",
        headers=auth(seeded.student_id),
        json=payload,
    )
    second = await client.post(
        "/api/v1/opportunities/go-transition",
        headers=auth(seeded.student_id),
        json=payload,
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 409, second.text


async def test_non_admin_cannot_process_opportunity(
    client: AsyncClient, seeded: SeededData
) -> None:
    response = await client.get("/api/v1/admin/opportunities", headers=auth(seeded.student_id))
    assert response.status_code == 403
