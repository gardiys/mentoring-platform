from datetime import UTC, datetime, timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.notifications.models import PlatformNotification
from app.opportunities import python_repeat_service
from app.opportunities import service as opportunity_service
from app.opportunities.models import (
    ConsultationMentorSetting,
    ConsultationRequest,
    ConsultationType,
    GoTransitionApplication,
    GoTransitionEnrollment,
    GoTransitionStatus,
    OpportunityPaymentAttempt,
    ProgramCompletion,
    PythonRepeatApplication,
    PythonRepeatApplicationStatus,
    PythonRepeatEnrollment,
    PythonRepeatInstallment,
    PythonRepeatProductOffer,
    PythonRepeatSuccessFeeObligation,
)
from app.payments.models import (
    MentorReward,
    MentorRewardKind,
    StudentEmployment,
    StudentEmploymentStatus,
)
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


async def _seed_python_repeat_product() -> None:
    async with TestSession() as session:
        session.add(
            PythonRepeatProductOffer(
                version=2,
                is_active=True,
                upfront_price_kopecks=3_000_000,
                success_fee_percent=100,
                success_fee_installments_count=4,
                mentor_fixed_accrual_kopecks=1_000_000,
                mentor_success_fee_share_percent=30,
                active_support_months=4,
                probation_support_days=30,
                included_mock_interviews=2,
                offer_valid_days=14,
                valid_from=datetime.now(UTC),
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


async def test_alumnus_consultation_accrues_reward_only_after_completion(
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
            "consultation_type": "technical_mock",
            "brief": "Разобрать карьерный план",
        },
    )
    assert created.status_code == 200, created.text
    request_id = created.json()["consultations"][0]["id"]
    async with TestSession() as session:
        request = await session.get(ConsultationRequest, UUID(request_id))
        assert request is not None
        assert request.price_kopecks == 400_000
        assert request.mentor_reward_kopecks == 250_000
        assert request.duration_minutes == 60
        assert request.consultation_type is ConsultationType.TECHNICAL_MOCK

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
        assert reward is None

    completed = await client.patch(
        f"/api/v1/admin/opportunities/consultations/{request_id}",
        headers=auth(seeded.admin_id),
        json={
            "status": "completed",
            "mentor_id": str(seeded.mentor_id),
            "written_summary": "Разобрали задачу и зафиксировали следующие шаги.",
        },
    )
    assert completed.status_code == 200, completed.text
    repeated = await client.patch(
        f"/api/v1/admin/opportunities/consultations/{request_id}",
        headers=auth(seeded.admin_id),
        json={
            "status": "completed",
            "mentor_id": str(seeded.mentor_id),
            "written_summary": "Разобрали задачу и зафиксировали следующие шаги.",
        },
    )
    assert repeated.status_code == 200, repeated.text
    async with TestSession() as session:
        rewards = list(
            await session.scalars(
                select(MentorReward).where(
                    MentorReward.consultation_request_id == UUID(request_id)
                )
            )
        )
        assert len(rewards) == 1
        reward = rewards[0]
        assert reward.kind is MentorRewardKind.CONSULTATION
        assert reward.amount_kopecks == 250_000


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
    assert "mentor_reward_kopecks" not in request

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
    assert "mentor_reward_kopecks" not in request
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
        json={"accepted": True},
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
        source_enrollment = await session.scalar(
            select(GoTransitionEnrollment).where(
                GoTransitionEnrollment.application_id == UUID(application_id)
            )
        )
        assert enrollment is not None
        assert student is not None
        assert student.repayment_percent == Decimal("100")
        assert student.entry_payment_kopecks == 3_000_000
        assert application_model is not None
        assert application_model.status is GoTransitionStatus.PAID
        assert application_model.accepted_terms_snapshot is not None
        assert application_model.accepted_terms_snapshot["upfront_price_kopecks"] == 3_000_000
        assert source_enrollment is not None
        assert source_enrollment.source == "python_to_go"
        assert source_enrollment.track_id == seeded.go_track_id
        assert source_enrollment.previous_python_track_id == seeded.python_track_id


async def test_python_repeat_clarification_can_be_edited_before_resubmit(
    client: AsyncClient, seeded: SeededData
) -> None:
    await _graduate_python(seeded)
    await _seed_python_repeat_product()
    payload = {
        "employment_status": "employed",
        "reason": "wants_higher_salary",
        "current_position": "Python Developer",
        "current_company": "Current",
        "current_stack": "Python and PostgreSQL",
        "last_interview_at": None,
        "target_position": "Senior Python Developer",
        "target_salary_kopecks": 25_000_000,
        "technical_gaps": "Нужно улучшить системный дизайн",
        "hours_per_week": 10,
        "desired_start_date": None,
        "search_mode": "search_while_employed",
        "additional_comment": None,
    }
    created = await client.post(
        "/api/v1/opportunities/python-repeat/applications",
        headers=auth(seeded.student_id),
        json=payload,
    )
    application_id = created.json()["application"]["id"]
    assert (
        await client.post(
            f"/api/v1/opportunities/python-repeat/applications/{application_id}/submit",
            headers=auth(seeded.student_id),
        )
    ).status_code == 200
    assert (
        await client.post(
            f"/api/v1/admin/opportunities/python-repeat/applications/{application_id}/transition",
            headers=auth(seeded.admin_id),
            json={"status": "under_review", "comment": "Проверяем заявку"},
        )
    ).status_code == 200
    assert (
        await client.post(
            f"/api/v1/admin/opportunities/python-repeat/applications/{application_id}/transition",
            headers=auth(seeded.admin_id),
            json={"status": "needs_clarification", "comment": "Уточните целевую роль"},
        )
    ).status_code == 200

    payload["target_position"] = "Lead Python Developer"
    updated = await client.patch(
        f"/api/v1/opportunities/python-repeat/applications/{application_id}",
        headers=auth(seeded.student_id),
        json=payload,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["application"]["target_position"] == "Lead Python Developer"
    resubmitted = await client.post(
        f"/api/v1/opportunities/python-repeat/applications/{application_id}/submit",
        headers=auth(seeded.student_id),
    )
    assert resubmitted.status_code == 200, resubmitted.text
    assert resubmitted.json()["application"]["status"] == "submitted"


async def test_python_repeat_is_blocked_during_initial_employment_support(
    client: AsyncClient, seeded: SeededData
) -> None:
    await _graduate_python(seeded)
    await _seed_python_repeat_product()
    async with TestSession() as session:
        session.add(
            StudentEmployment(
                student_id=seeded.student_id,
                company_name="Новый работодатель",
                start_date=datetime.now(UTC).date() - timedelta(days=7),
                net_salary_kopecks=30_000_000,
                repayment_percent=Decimal("200"),
                status=StudentEmploymentStatus.ACTIVE,
                payment_day_first=10,
                payment_day_second=25,
                recorded_by_user_id=seeded.admin_id,
            )
        )
        await session.commit()

    response = await client.get(
        "/api/v1/opportunities/python-repeat/eligibility",
        headers=auth(seeded.student_id),
    )
    assert response.status_code == 200, response.text
    assert response.json()["code"] == "INITIAL_SUPPORT_ACTIVE"
    assert response.json()["eligible"] is False


async def test_python_repeat_rejects_naive_business_datetimes(
    client: AsyncClient, seeded: SeededData
) -> None:
    await _graduate_python(seeded)
    await _seed_python_repeat_product()
    response = await client.post(
        "/api/v1/opportunities/python-repeat/applications",
        headers=auth(seeded.student_id),
        json={
            "employment_status": "employed",
            "reason": "wants_higher_salary",
            "target_position": "Senior Python Developer",
            "technical_gaps": "Нужно улучшить системный дизайн",
            "hours_per_week": 10,
            "desired_start_date": "2026-10-01T10:00:00",
            "search_mode": "search_while_employed",
        },
    )
    assert response.status_code == 422, response.text


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


async def test_python_repeat_feature_flag_hides_offer_and_blocks_new_applications(
    client: AsyncClient, seeded: SeededData, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _graduate_python(seeded)
    await _seed_python_repeat_product()
    disabled = get_settings().model_copy(update={"python_repeat_mentorship_enabled": False})
    monkeypatch.setattr(opportunity_service, "get_settings", lambda: disabled)
    monkeypatch.setattr(python_repeat_service, "get_settings", lambda: disabled)

    opportunities = await client.get("/api/v1/opportunities/me", headers=auth(seeded.student_id))
    assert opportunities.status_code == 200, opportunities.text
    assert "PYTHON_REPEAT_MENTORSHIP" not in {
        item["code"] for item in opportunities.json()["opportunities"]
    }
    eligibility = await client.get(
        "/api/v1/opportunities/python-repeat/eligibility", headers=auth(seeded.student_id)
    )
    assert eligibility.status_code == 200, eligibility.text
    assert eligibility.json()["code"] == "FEATURE_DISABLED"


async def test_python_repeat_development_payment_endpoint_is_hidden_in_production(
    client: AsyncClient, seeded: SeededData, monkeypatch: pytest.MonkeyPatch
) -> None:
    production = get_settings().model_copy(update={"app_env": "production"})
    monkeypatch.setattr(python_repeat_service, "get_settings", lambda: production)
    response = await client.post(
        "/api/v1/opportunities/python-repeat/development/payments/not-a-real-link/succeed",
        headers=auth(seeded.student_id),
    )
    assert response.status_code == 404


async def test_python_repeat_full_payment_and_mentor_reward_flow(
    client: AsyncClient, seeded: SeededData
) -> None:
    await _graduate_python(seeded)
    await _seed_python_repeat_product()

    detail = await client.get(
        "/api/v1/opportunities/python-repeat", headers=auth(seeded.student_id)
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["eligibility"]["eligible"] is True
    assert detail.json()["product"]["upfront_price_kopecks"] == 3_000_000
    assert detail.json()["product"]["success_fee_percent"] == 100

    created = await client.post(
        "/api/v1/opportunities/python-repeat/applications",
        headers=auth(seeded.student_id),
        json={
            "employment_status": "employed",
            "reason": "wants_higher_salary",
            "current_position": "Python Developer",
            "current_company": "Current",
            "current_stack": "Python, FastAPI, PostgreSQL",
            "last_interview_at": None,
            "target_position": "Senior Python Developer",
            "target_salary_kopecks": 25_000_000,
            "technical_gaps": "Хочу улучшить system design и алгоритмы",
            "hours_per_week": 10,
            "desired_start_date": None,
            "search_mode": "search_while_employed",
            "additional_comment": None,
        },
    )
    assert created.status_code == 200, created.text
    application_id = created.json()["application"]["id"]

    submitted = await client.post(
        f"/api/v1/opportunities/python-repeat/applications/{application_id}/submit",
        headers=auth(seeded.student_id),
    )
    assert submitted.status_code == 200, submitted.text
    review = await client.post(
        f"/api/v1/admin/opportunities/python-repeat/applications/{application_id}/transition",
        headers=auth(seeded.admin_id),
        json={
            "status": "under_review",
            "comment": "Начали рассмотрение",
            "responsible_user_id": str(seeded.admin_id),
        },
    )
    assert review.status_code == 200, review.text
    approved = await client.post(
        f"/api/v1/admin/opportunities/python-repeat/applications/{application_id}/transition",
        headers=auth(seeded.admin_id),
        json={
            "status": "approved",
            "comment": "Условия подтверждены",
            "responsible_user_id": str(seeded.admin_id),
        },
    )
    assert approved.status_code == 200, approved.text
    application = approved.json()["applications"][0]
    assert application["terms_snapshot"]["upfront_price_kopecks"] == 3_000_000
    assert application["terms_snapshot"]["success_fee_percent"] == 100
    async with TestSession() as session:
        product = await session.scalar(
            select(PythonRepeatProductOffer).where(PythonRepeatProductOffer.version == 2)
        )
        assert product is not None
        product.upfront_price_kopecks = 9_999_999
        product.success_fee_percent = 125
        product.mentor_fixed_accrual_kopecks = 999_999
        product.mentor_success_fee_share_percent = 45
        await session.commit()

    accepted = await client.post(
        f"/api/v1/opportunities/python-repeat/applications/{application_id}/accept-terms",
        headers=auth(seeded.student_id),
        json={"accepted": True},
    )
    assert accepted.status_code == 200, accepted.text
    payment_link = await client.post(
        f"/api/v1/opportunities/python-repeat/applications/{application_id}/checkout",
        headers=auth(seeded.student_id),
    )
    assert payment_link.status_code == 200, payment_link.text
    failed_link = await client.post(
        "/api/v1/opportunities/python-repeat/development/payments/"
        f"{payment_link.json()['payment_link_id']}/fail",
        headers=auth(seeded.student_id),
    )
    assert failed_link.status_code == 200, failed_link.text
    refreshed_link = await client.post(
        f"/api/v1/opportunities/python-repeat/applications/{application_id}/checkout",
        headers=auth(seeded.student_id),
    )
    assert refreshed_link.status_code == 200, refreshed_link.text
    assert refreshed_link.json()["payment_link_id"] != payment_link.json()["payment_link_id"]
    async with TestSession() as session:
        attempt = await session.scalar(
            select(OpportunityPaymentAttempt).where(
                OpportunityPaymentAttempt.payment_link_id
                == refreshed_link.json()["payment_link_id"]
            )
        )
        assert attempt is not None
        assert attempt.terms_snapshot is not None
        assert attempt.terms_snapshot["upfront_price_kopecks"] == 3_000_000
        assert attempt.terms_snapshot["success_fee_percent"] == 100
    paid = await client.post(
        "/api/v1/opportunities/python-repeat/development/payments/"
        f"{refreshed_link.json()['payment_link_id']}/succeed",
        headers=auth(seeded.student_id),
    )
    assert paid.status_code == 200, paid.text
    assert paid.json()["application"]["status"] == "enrolled"
    enrollment_id = paid.json()["enrollment"]["id"]
    repeated_upfront = await client.post(
        "/api/v1/opportunities/python-repeat/development/payments/"
        f"{refreshed_link.json()['payment_link_id']}/succeed",
        headers=auth(seeded.student_id),
    )
    assert repeated_upfront.status_code == 200, repeated_upfront.text

    assigned = await client.post(
        f"/api/v1/admin/opportunities/python-repeat/enrollments/{enrollment_id}/assign-mentor",
        headers=auth(seeded.admin_id),
        json={"mentor_id": str(seeded.mentor_id)},
    )
    assert assigned.status_code == 200, assigned.text

    now = datetime.now(UTC)
    offer = await client.post(
        "/api/v1/opportunities/python-repeat/offers",
        headers=auth(seeded.student_id),
        json={
            "position": "Senior Python Developer",
            "company": "New Company",
            "fixed_monthly_salary_kopecks": 25_000_000,
            "employment_type": "Трудовой договор",
            "received_at": now.isoformat(),
            "expected_start_date": now.isoformat(),
        },
    )
    assert offer.status_code == 200, offer.text
    offer_id = offer.json()["offers"][0]["id"]
    submitted_offer = await client.post(
        f"/api/v1/opportunities/python-repeat/offers/{offer_id}/submit",
        headers=auth(seeded.student_id),
    )
    assert submitted_offer.status_code == 200, submitted_offer.text
    verified = await client.post(
        f"/api/v1/admin/opportunities/python-repeat/offers/{offer_id}/decision",
        headers=auth(seeded.admin_id),
        json={
            "verified": True,
            "salary_base_kopecks": 25_000_000,
            "comment": "Python Backend оффер подтверждён",
        },
    )
    assert verified.status_code == 200, verified.text
    obligation = verified.json()["applications"][0]["obligation"]
    assert obligation["total_amount_kopecks"] == 25_000_000
    assert [item["amount_kopecks"] for item in obligation["installments"]] == [
        6_250_000,
        6_250_000,
        6_250_000,
        6_250_000,
    ]

    first_installment = obligation["installments"][0]
    installment_link = await client.post(
        f"/api/v1/opportunities/python-repeat/installments/{first_installment['id']}/checkout",
        headers=auth(seeded.student_id),
    )
    assert installment_link.status_code == 200, installment_link.text
    installment_paid = await client.post(
        "/api/v1/opportunities/python-repeat/development/payments/"
        f"{installment_link.json()['payment_link_id']}/succeed",
        headers=auth(seeded.student_id),
    )
    assert installment_paid.status_code == 200, installment_paid.text
    repeated_installment = await client.post(
        "/api/v1/opportunities/python-repeat/development/payments/"
        f"{installment_link.json()['payment_link_id']}/succeed",
        headers=auth(seeded.student_id),
    )
    assert repeated_installment.status_code == 200, repeated_installment.text

    finance = await client.get(
        "/api/v1/admin/opportunities/python-repeat", headers=auth(seeded.admin_id)
    )
    assert finance.status_code == 200, finance.text
    finance_item = finance.json()["applications"][0]
    assert finance_item["revenue_received_kopecks"] == 9_250_000
    assert finance_item["mentor_accrued_kopecks"] == 2_875_000
    assert finance_item["mentor_paid_kopecks"] == 0
    assert finance_item["gross_remainder_kopecks"] == 6_375_000

    for installment in obligation["installments"][1:]:
        next_link = await client.post(
            f"/api/v1/opportunities/python-repeat/installments/{installment['id']}/checkout",
            headers=auth(seeded.student_id),
        )
        assert next_link.status_code == 200, next_link.text
        next_paid = await client.post(
            "/api/v1/opportunities/python-repeat/development/payments/"
            f"{next_link.json()['payment_link_id']}/succeed",
            headers=auth(seeded.student_id),
        )
        assert next_paid.status_code == 200, next_paid.text

    final_finance = await client.get(
        "/api/v1/admin/opportunities/python-repeat", headers=auth(seeded.admin_id)
    )
    assert final_finance.status_code == 200, final_finance.text
    final_item = final_finance.json()["applications"][0]
    assert final_item["revenue_received_kopecks"] == 28_000_000
    assert final_item["mentor_accrued_kopecks"] == 8_500_000
    assert final_item["mentor_paid_kopecks"] == 0
    assert final_item["gross_remainder_kopecks"] == 19_500_000

    async with TestSession() as session:
        application_model = await session.get(PythonRepeatApplication, UUID(application_id))
        enrollment = await session.get(PythonRepeatEnrollment, UUID(enrollment_id))
        obligation_model = await session.scalar(
            select(PythonRepeatSuccessFeeObligation).where(
                PythonRepeatSuccessFeeObligation.enrollment_id == UUID(enrollment_id)
            )
        )
        installments = list(
            await session.scalars(
                select(PythonRepeatInstallment).order_by(PythonRepeatInstallment.sequence_number)
            )
        )
        rewards = list(
            await session.scalars(
                select(MentorReward).where(
                    MentorReward.kind.in_(
                        [
                            MentorRewardKind.PYTHON_REPEAT_FIXED,
                            MentorRewardKind.PYTHON_REPEAT_SUCCESS_FEE,
                        ]
                    )
                )
            )
        )
        notifications = list(
            await session.scalars(
                select(PlatformNotification).where(
                    PlatformNotification.user_id.in_([seeded.student_id, seeded.admin_id])
                )
            )
        )
        assert application_model is not None
        assert application_model.status is PythonRepeatApplicationStatus.ENROLLED
        assert enrollment is not None
        assert enrollment.terms_snapshot["upfront_price_kopecks"] == 3_000_000
        assert enrollment.terms_snapshot["success_fee_percent"] == 100
        assert enrollment.terms_snapshot["mentor_fixed_accrual_kopecks"] == 1_000_000
        assert enrollment.terms_snapshot["mentor_success_fee_share_percent"] == 30
        assert enrollment.terms_snapshot["application_id"] == application_id
        assert enrollment.terms_snapshot["previous_enrollment_id"] == {
            "user_id": str(seeded.student_id),
            "track_id": str(seeded.python_track_id),
        }
        assert obligation_model is not None
        assert len(installments) == 4
        assert sorted(reward.amount_kopecks for reward in rewards) == [
            1_000_000,
            1_875_000,
            1_875_000,
            1_875_000,
            1_875_000,
        ]
        assert any("application-submitted" in item.event_key for item in notifications)
        assert any("installment-paid" in item.event_key for item in notifications)
