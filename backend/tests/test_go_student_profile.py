from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.legal.models import LegalQuestionnaireDraft
from app.mentors.models import MentorStudent
from app.opportunities.models import GoTransitionApplication
from app.payments.models import (
    MentorReward,
    PaymentInstallment,
    PaymentInstallmentStatus,
    StudentEmployment,
)
from app.users.models import User
from tests.conftest import SeededData, TestSession, auth
from tests.legal_helpers import ANSWERS, approved_application, legal_checkout
from tests.test_admin_students import student_payload
from tests.test_legal_contracts import make_purchase, webhook


async def test_actual_repayment_change_before_first_payment_still_updates_schedule(
    client: AsyncClient, seeded: SeededData
) -> None:
    created = await client.put(
        f"/api/v1/mentor/students/{seeded.student_id}/employment",
        headers=auth(seeded.mentor_id),
        json={
            "company_name": "Python employer",
            "start_date": datetime.now(UTC).date().isoformat(),
            "net_salary_rubles": 200_000,
        },
    )
    assert created.status_code == 200, created.text
    employment_id = UUID(created.json()["employment"]["id"])
    response = await client.put(
        f"/api/v1/admin/students/{seeded.student_id}",
        headers=auth(seeded.admin_id),
        json=student_payload(seeded)
        | {"mentor_id": str(seeded.mentor_id), "repayment_percent": 150},
    )
    assert response.status_code == 200, response.text
    assert Decimal(response.json()["repayment_percent"]) == 150
    async with TestSession() as session:
        assert (await session.get(StudentEmployment, employment_id)).repayment_percent == 150
        installments = list(
            await session.scalars(
                select(PaymentInstallment).where(PaymentInstallment.employment_id == employment_id)
            )
        )
        assert all(row.status is PaymentInstallmentStatus.SCHEDULED for row in installments)
        assert sum(row.amount_kopecks for row in installments) == 30_000_000
        assert sum(row.salary_percent for row in installments) == 150


@pytest.mark.parametrize("terminate_python", [False, True])
@pytest.mark.parametrize("pay_for_go", [False, True])
@pytest.mark.parametrize("pay_python_in_full", [False, True])
async def test_admin_can_assign_go_mentor_after_python_payment_without_repricing(
    client: AsyncClient,
    seeded: SeededData,
    terminate_python: bool,
    pay_for_go: bool,
    pay_python_in_full: bool,
) -> None:
    employment = await client.put(
        f"/api/v1/mentor/students/{seeded.student_id}/employment",
        headers=auth(seeded.mentor_id),
        json={
            "company_name": "Python employer",
            "start_date": (datetime.now(UTC).date() - timedelta(days=10)).isoformat(),
            "net_salary_rubles": 200_000,
        },
    )
    assert employment.status_code == 200, employment.text
    employment_id = UUID(employment.json()["employment"]["id"])
    installments_to_pay = employment.json()["installments"]
    if not pay_python_in_full:
        installments_to_pay = installments_to_pay[:1]
    for installment in installments_to_pay:
        installment_id = installment["id"]
        confirmed = await client.post(
            f"/api/v1/admin/payments/installments/{installment_id}/confirm",
            headers=auth(seeded.admin_id),
        )
        assert confirmed.status_code == 200, confirmed.text
    if terminate_python:
        ended = await client.post(
            f"/api/v1/mentor/students/{seeded.student_id}/employment/terminate",
            headers=auth(seeded.mentor_id),
            json={
                "ended_at": datetime.now(UTC).date().isoformat(),
                "reason": "Завершил работу по Python",
            },
        )
        assert ended.status_code == 200, ended.text
    if pay_for_go:
        checkout = await make_purchase(client, seeded, "python_to_go_transition")
        payment = await webhook(client, checkout)
        assert payment.status_code == 200, payment.text
        assert payment.json()["status"] == "ok"
    percent = 100 if pay_for_go else 200
    async with TestSession() as session:
        old_installments = [
            (row.id, row.amount_kopecks, row.salary_percent, row.status, row.paid_at)
            for row in await session.scalars(
                select(PaymentInstallment)
                .where(PaymentInstallment.employment_id == employment_id)
                .order_by(PaymentInstallment.id)
            )
        ]
        old_rewards = [
            (row.id, row.mentor_id, row.amount_kopecks, row.paid_kopecks)
            for row in await session.scalars(
                select(MentorReward).where(MentorReward.student_id == seeded.student_id)
            )
        ]
    payload = student_payload(
        seeded, track_ids=[str(seeded.python_track_id), str(seeded.go_track_id)]
    ) | {
        "mentor_id": str(seeded.other_mentor_id),
        "mentor_reward_percent": 45,
        "repayment_percent": percent,
        "entry_payment_rubles": 30_000 if pay_for_go else 45_000,
        "entry_payment_paid": pay_for_go,
    }
    saved = await client.put(
        f"/api/v1/admin/students/{seeded.student_id}",
        headers=auth(seeded.admin_id),
        json=payload,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["mentor"]["id"] == str(seeded.other_mentor_id)
    assert Decimal(saved.json()["repayment_percent"]) == percent
    forbidden = await client.put(
        f"/api/v1/admin/students/{seeded.student_id}",
        headers=auth(seeded.admin_id),
        json=payload | {"repayment_percent": 150, "first_name": "Не сохранять"},
    )
    assert forbidden.status_code == 409, forbidden.text
    assert forbidden.json()["detail"]["code"] == "repayment_percent_locked"
    async with TestSession() as session:
        student = await session.get(User, seeded.student_id)
        assert student.repayment_percent == percent
        assert student.first_name != "Не сохранять"
        relation = await session.scalar(
            select(MentorStudent).where(MentorStudent.student_id == seeded.student_id)
        )
        assert relation.mentor_id == seeded.other_mentor_id
        assert (await session.get(StudentEmployment, employment_id)).repayment_percent == 200
        installments = [
            (row.id, row.amount_kopecks, row.salary_percent, row.status, row.paid_at)
            for row in await session.scalars(
                select(PaymentInstallment)
                .where(PaymentInstallment.employment_id == employment_id)
                .order_by(PaymentInstallment.id)
            )
        ]
        assert installments == old_installments
        for reward_id, mentor_id, amount, paid in old_rewards:
            reward = await session.get(MentorReward, reward_id)
            assert (reward.mentor_id, reward.amount_kopecks, reward.paid_kopecks) == (
                mentor_id,
                amount,
                paid,
            )


@pytest.mark.parametrize("paid", [False, True])
async def test_admin_reads_go_questionnaire_from_the_payment_evidence(
    client: AsyncClient, seeded: SeededData, paid: bool
) -> None:
    application_id = await approved_application(client, seeded, "python_to_go_transition")
    empty = await client.get(
        f"/api/v1/admin/opportunities/go-transition/{application_id}",
        headers=auth(seeded.admin_id),
    )
    assert empty.json()["questionnaire"] is None
    response = await legal_checkout(
        client, seeded.student_id, "python_to_go_transition", application_id
    )
    assert response.status_code == 200, response.text
    if paid:
        result = await webhook(client, response.json())
        assert result.json()["status"] == "ok", result.text
    async with TestSession() as session:
        session.add(
            LegalQuestionnaireDraft(
                user_id=seeded.student_id,
                product_code="python_to_go_transition",
                answers=ANSWERS | {"position": "Более поздний черновик"},
            )
        )
        other_application = GoTransitionApplication(
            student_id=seeded.student_id,
            motivation="Другая заявка без заполненной анкеты",
            upfront_price_kopecks=3_000_000,
            success_fee_percent=100,
            terms_version=1,
            terms_snapshot={},
        )
        session.add(other_application)
        await session.commit()
        other_application_id = other_application.id
    student = await client.get(
        f"/api/v1/admin/students/{seeded.student_id}", headers=auth(seeded.admin_id)
    )
    application = await client.get(
        f"/api/v1/admin/opportunities/go-transition/{application_id}",
        headers=auth(seeded.admin_id),
    )
    assert student.status_code == application.status_code == 200
    profile = student.json()["go_transition_questionnaire"]
    assert profile == application.json()["questionnaire"]
    assert profile["source"] == ("payment" if paid else "checkout")
    assert profile["application_id"] == application_id
    assert profile["recorded_at"]
    for name, value in ANSWERS.items():
        assert profile["answers"][name] == value
    assert "ip_address" not in profile["answers"]
    assert "user_agent" not in profile["answers"]
    other = await client.get(
        f"/api/v1/admin/opportunities/go-transition/{other_application_id}",
        headers=auth(seeded.admin_id),
    )
    assert other.status_code == 200, other.text
    assert other.json()["questionnaire"] is None


@pytest.mark.parametrize("actor", ["student_id", "mentor_id"])
async def test_go_questionnaire_admin_views_deny_student_and_mentor(
    client: AsyncClient, seeded: SeededData, actor: str
) -> None:
    application_id = await approved_application(client, seeded, "python_to_go_transition")
    checkout = await legal_checkout(
        client, seeded.student_id, "python_to_go_transition", application_id
    )
    assert checkout.status_code == 200, checkout.text
    for path in (
        f"/api/v1/admin/students/{seeded.student_id}",
        f"/api/v1/admin/opportunities/go-transition/{application_id}",
    ):
        response = await client.get(path, headers=auth(getattr(seeded, actor)))
        assert response.status_code == 403, response.text
        assert "questionnaire" not in response.json()


async def test_python_repeat_questionnaire_is_not_used_as_go_profile(
    client: AsyncClient, seeded: SeededData
) -> None:
    await make_purchase(client, seeded, "repeat_python_mentorship")
    response = await client.get(
        f"/api/v1/admin/students/{seeded.student_id}", headers=auth(seeded.admin_id)
    )
    assert response.status_code == 200, response.text
    assert response.json()["go_transition_questionnaire"] is None


async def test_erased_student_profile_does_not_restore_questionnaire_answers(
    client: AsyncClient, seeded: SeededData
) -> None:
    application_id = await approved_application(client, seeded, "python_to_go_transition")
    checkout = await legal_checkout(
        client, seeded.student_id, "python_to_go_transition", application_id
    )
    assert checkout.status_code == 200, checkout.text
    async with TestSession() as session:
        student = await session.get(User, seeded.student_id)
        student.personal_data_erased_at = datetime.now(UTC)
        await session.commit()
    student = await client.get(
        f"/api/v1/admin/students/{seeded.student_id}", headers=auth(seeded.admin_id)
    )
    application = await client.get(
        f"/api/v1/admin/opportunities/go-transition/{application_id}",
        headers=auth(seeded.admin_id),
    )
    assert student.status_code == application.status_code == 200
    assert student.json()["go_transition_questionnaire"] is None
    assert application.json()["questionnaire"] is None
