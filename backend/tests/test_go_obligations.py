from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.legal.models import ContractAcceptance, LegalAuditEvent
from app.payments.models import (
    MentorReward,
    PaymentInstallment,
    StudentEmployment,
    StudentEmploymentStatus,
    StudentPaymentObligation,
)
from tests.conftest import SeededData, TestSession, auth
from tests.test_admin_students import student_payload
from tests.test_legal_contracts import make_purchase, webhook


async def paid_python_then_go(client: AsyncClient, seeded: SeededData) -> tuple[dict, dict]:
    original = await client.put(
        f"/api/v1/mentor/students/{seeded.student_id}/employment",
        headers=auth(seeded.mentor_id),
        json={
            "company_name": "Python employer",
            "start_date": datetime.now(UTC).date().isoformat(),
            "net_salary_rubles": 200_000,
        },
    )
    assert original.status_code == 200, original.text
    for installment in original.json()["installments"]:
        response = await client.post(
            f"/api/v1/admin/payments/installments/{installment['id']}/confirm",
            headers=auth(seeded.admin_id),
        )
        assert response.status_code == 200, response.text
    checkout = await make_purchase(client, seeded, "python_to_go_transition")
    assert (await webhook(client, checkout)).json()["status"] == "ok"
    return original.json(), checkout


async def dashboard(client: AsyncClient, seeded: SeededData) -> dict:
    response = await client.get("/api/v1/payments/me", headers=auth(seeded.student_id))
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("via_student", [False, True])
async def test_paid_python_new_go_obligation_end_to_end(
    client: AsyncClient, seeded: SeededData, via_student: bool
) -> None:
    original, checkout = await paid_python_then_go(client, seeded)
    python_id = UUID(original["employment"]["id"])
    async with TestSession() as session:
        python = await session.get(StudentEmployment, python_id)
        assert python.status is StudentEmploymentStatus.COMPLETED
        assert python.ended_at is None  # Repayment completion does not invent a dismissal.
        old_payments = [
            (p.id, p.amount_kopecks, p.salary_percent, p.status, p.paid_at)
            for p in await session.scalars(
                select(PaymentInstallment)
                .where(PaymentInstallment.employment_id == python_id)
                .order_by(PaymentInstallment.id)
            )
        ]
        old_rewards = [
            (r.id, r.mentor_id, r.amount_kopecks)
            for r in await session.scalars(
                select(MentorReward).where(MentorReward.student_id == seeded.student_id)
            )
        ]
    data = await dashboard(client, seeded)
    assert data["employment"] is None
    assert Decimal(data["repayment_percent"]) == 100
    assert Decimal(data["summary"]["paid_salary_percent"]) == 0
    assert Decimal(data["summary"]["remaining_salary_percent"]) == 100
    assert data["summary"]["remaining_kopecks"] == 0  # Contingent until a qualifying new job.
    assert len(data["obligations"]) == 2
    legacy = next(item for item in data["obligations"] if item["contract_id"] is None)
    assert Decimal(legacy["summary"]["paid_salary_percent"]) == 200
    assert Decimal(legacy["summary"]["remaining_salary_percent"]) == 0
    assert legacy["summary"]["paid_kopecks"] == 40_000_000
    contract_id = data["obligation"]["contract_id"]
    saved = await client.put(
        f"/api/v1/admin/students/{seeded.student_id}",
        headers=auth(seeded.admin_id),
        json=student_payload(
            seeded, track_ids=[str(seeded.python_track_id), str(seeded.go_track_id)]
        )
        | {
            "mentor_id": str(seeded.other_mentor_id),
            "mentor_reward_percent": 45,
            "repayment_percent": 100,
            "entry_payment_rubles": 30_000,
            "entry_payment_paid": True,
        },
    )
    assert saved.status_code == 200, saved.text
    start = date(datetime.now(UTC).year + 1, 1, 31).isoformat()
    if via_student:
        offer = await client.post(
            "/api/v1/employment-cases/me/report-offer",
            headers=auth(seeded.student_id),
            json={
                "track_id": str(seeded.go_track_id),
                "employer_name": "Go employer",
                "vacancy_title": "Go Developer",
                "activity_type": "employment_contract",
                "offer_received_at": start,
                "net_salary_rubles": "250000.01",
                "idempotency_key": "go-offer-end-to-end",
            },
        )
        assert offer.status_code == 201, offer.text
        case = offer.json()
        assert case["contract_id"] == contract_id
        assert case["policy_is_legacy"] is False
        work = await client.post(
            f"/api/v1/employment-cases/{case['id']}/work-start",
            headers=auth(seeded.student_id),
            json={
                "employment_started_at": start,
                "official_job_title": "Go Developer",
                "actual_duties": "Разрабатываю сервисы на Go каждый день",
                "actual_stack": ["Go"],
                "expected_lock_version": case["lock_version"],
                "idempotency_key": "go-work-end-to-end",
            },
        )
        assert work.status_code == 200, work.text
        case = work.json()
        assessment_path = (
            f"/api/v1/mentor/students/{seeded.student_id}/employment-cases/{case['id']}/assessments"
        )
        assessment = {
            "classification": "profile",
            "effective_profile_started_at": start,
            "rationale": "Новая работа подтверждена и соответствует договору Go",
            "qualifying_criteria": [{"criterion": "coding", "technology": "Go"}],
            "expected_lock_version": case["lock_version"],
            "idempotency_key": "go-assess-unconfirmed",
        }
        unconfirmed = await client.post(
            assessment_path, headers=auth(seeded.other_mentor_id), json=assessment
        )
        assert unconfirmed.status_code == 200, unconfirmed.text
        assert unconfirmed.json()["qualification_window"]["billing_trigger_allowed"] is False
        assert (await dashboard(client, seeded))["summary"]["total_installments"] == 0
        assessment |= {
            "contract_billing_confirmed": True,
            "expected_lock_version": unconfirmed.json()["lock_version"],
            "idempotency_key": "go-assess-confirmed",
        }
        confirmed = await client.post(
            assessment_path, headers=auth(seeded.other_mentor_id), json=assessment
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["qualification_window"]["billing_trigger_allowed"] is True
        replay = await client.post(
            assessment_path, headers=auth(seeded.other_mentor_id), json=assessment
        )
        assert replay.status_code == 200, replay.text
    else:
        employment_path = f"/api/v1/mentor/students/{seeded.student_id}/employment"
        payload = {
            "company_name": "Go employer",
            "start_date": start,
            "net_salary_rubles": "250000.01",
        }
        rejected = await client.put(
            employment_path, headers=auth(seeded.other_mentor_id), json=payload
        )
        assert rejected.status_code == 422, rejected.text
        confirmed = await client.put(
            employment_path,
            headers=auth(seeded.other_mentor_id),
            json=payload | {"contract_billing_confirmed": True},
        )
        assert confirmed.status_code == 200, confirmed.text
    data = await dashboard(client, seeded)
    go_id = data["employment"]["id"]
    rows = [row for row in data["installments"] if row["employment_id"] == go_id]
    assert len(rows) == 2
    year = datetime.now(UTC).year + 1
    from app.legal.catalog import calendar_due

    assert [row["due_date"] for row in rows] == [
        calendar_due(date(year, 1, 31), offset).isoformat() for offset in (1, 2)
    ]
    assert [row["amount_kopecks"] for row in rows] == [12_500_000, 12_500_001]
    assert [Decimal(row["salary_percent"]) for row in rows] == [50, 50]
    assert data["summary"]["remaining_kopecks"] == 25_000_001
    assert Decimal(data["summary"]["remaining_salary_percent"]) == 100
    assert (await webhook(client, checkout, event_id="go-replayed-upfront")).json()[
        "status"
    ] == "ok"
    for index, row in enumerate(rows):
        link = await client.post(
            f"/api/v1/payments/installments/{row['id']}/link", headers=auth(seeded.student_id)
        )
        assert link.status_code == 200, link.text
        paid = await client.post(
            f"/api/v1/admin/payments/installments/{row['id']}/confirm",
            headers=auth(seeded.admin_id),
        )
        assert paid.status_code == 200, paid.text
        assert Decimal(paid.json()["summary"]["remaining_salary_percent"]) == (
            50 if index == 0 else 0
        )
        assert paid.json()["summary"]["remaining_kopecks"] == (12_500_001 if index == 0 else 0)
    async with TestSession() as session:
        assert await session.scalar(select(func.count()).select_from(StudentPaymentObligation)) == 2
        assert (await session.get(StudentEmployment, UUID(go_id))).obligation_id != (
            await session.get(StudentEmployment, python_id)
        ).obligation_id
        actual = [
            (p.id, p.amount_kopecks, p.salary_percent, p.status, p.paid_at)
            for p in await session.scalars(
                select(PaymentInstallment)
                .where(PaymentInstallment.employment_id == python_id)
                .order_by(PaymentInstallment.id)
            )
        ]
        assert actual == old_payments
        for reward_id, mentor_id, amount in old_rewards:
            reward = await session.get(MentorReward, reward_id)
            assert (reward.mentor_id, reward.amount_kopecks) == (mentor_id, amount)
        new_rewards = list(
            await session.scalars(
                select(MentorReward)
                .join(PaymentInstallment, PaymentInstallment.id == MentorReward.installment_id)
                .where(PaymentInstallment.employment_id == UUID(go_id))
            )
        )
        assert len(new_rewards) == 2
        assert all(reward.mentor_id == seeded.other_mentor_id for reward in new_rewards)
        assert sum(reward.amount_kopecks for reward in new_rewards) == 11_250_000


async def test_go_new_job_carries_only_its_own_paid_percent(
    client: AsyncClient, seeded: SeededData
) -> None:
    await paid_python_then_go(client, seeded)
    path = f"/api/v1/mentor/students/{seeded.student_id}/employment"
    start = datetime.now(UTC).date()
    response = await client.put(
        path,
        headers=auth(seeded.mentor_id),
        json={
            "company_name": "First Go employer",
            "start_date": start.isoformat(),
            "net_salary_rubles": 200_000,
            "contract_billing_confirmed": True,
        },
    )
    assert response.status_code == 200, response.text
    go = response.json()["employment"]["id"]
    first = next(row for row in response.json()["installments"] if row["employment_id"] == go)
    assert (
        await client.post(
            f"/api/v1/admin/payments/installments/{first['id']}/confirm",
            headers=auth(seeded.admin_id),
        )
    ).status_code == 200
    ended = await client.post(
        path + "/terminate",
        headers=auth(seeded.mentor_id),
        json={"ended_at": start.isoformat(), "reason": "Смена Go-работы"},
    )
    assert ended.status_code == 200, ended.text
    assert Decimal(ended.json()["summary"]["remaining_salary_percent"]) == 50
    second = await client.put(
        path,
        headers=auth(seeded.mentor_id),
        json={
            "company_name": "Second Go employer",
            "start_date": (start + timedelta(days=1)).isoformat(),
            "net_salary_rubles": 300_000,
            "contract_billing_confirmed": True,
        },
    )
    assert second.status_code == 200, second.text
    data = second.json()
    rows = [row for row in data["installments"] if row["employment_id"] == data["employment"]["id"]]
    assert len(rows) == 1
    assert Decimal(rows[0]["salary_percent"]) == 50
    assert rows[0]["amount_kopecks"] == 15_000_000


async def test_revoking_archived_python_payment_does_not_reprice_go(
    client: AsyncClient, seeded: SeededData
) -> None:
    original, _ = await paid_python_then_go(client, seeded)
    python_payment = original["installments"][0]["id"]
    response = await client.put(
        f"/api/v1/mentor/students/{seeded.student_id}/employment",
        headers=auth(seeded.mentor_id),
        json={
            "company_name": "Go employer",
            "start_date": datetime.now(UTC).date().isoformat(),
            "net_salary_rubles": 250_000,
            "contract_billing_confirmed": True,
        },
    )
    assert response.status_code == 200, response.text
    revoked = await client.post(
        f"/api/v1/admin/payments/installments/{python_payment}/revoke",
        headers=auth(seeded.admin_id),
        json={"reason": "Ошибочное подтверждение старого платежа"},
    )
    assert revoked.status_code == 200, revoked.text
    data = await dashboard(client, seeded)
    assert Decimal(data["summary"]["remaining_salary_percent"]) == 100
    assert data["summary"]["remaining_kopecks"] == 25_000_000
    python = next(item for item in data["obligations"] if item["contract_id"] is None)
    assert Decimal(python["summary"]["remaining_salary_percent"]) == 25
    assert python["summary"]["remaining_kopecks"] == 5_000_000
    restored = next(item for item in data["installments"] if item["id"] == python_payment)
    assert restored["can_pay"] is True
    link = await client.post(
        f"/api/v1/payments/installments/{python_payment}/link", headers=auth(seeded.student_id)
    )
    assert link.status_code == 200, link.text


async def test_inactive_go_contract_cannot_create_new_payment_links(
    client: AsyncClient, seeded: SeededData
) -> None:
    checkout = await make_purchase(client, seeded, "python_to_go_transition")
    assert (await webhook(client, checkout)).json()["status"] == "ok"
    created = await client.put(
        f"/api/v1/mentor/students/{seeded.student_id}/employment",
        headers=auth(seeded.mentor_id),
        json={
            "company_name": "Go employer",
            "start_date": datetime.now(UTC).date().isoformat(),
            "net_salary_rubles": 250_000,
            "contract_billing_confirmed": True,
        },
    )
    assert created.status_code == 200, created.text
    payment = created.json()["installments"][0]["id"]
    async with TestSession() as session:
        contract = await session.scalar(select(ContractAcceptance))
        contract.status = "refunded"
        await session.commit()
    link = await client.post(
        f"/api/v1/payments/installments/{payment}/link", headers=auth(seeded.student_id)
    )
    assert link.status_code == 409, link.text
    assert link.json()["detail"]["code"] == "go_contract_inactive"
    data = await dashboard(client, seeded)
    assert data["obligation"]["contract_status"] == "refunded"
    assert all(not item["can_pay"] for item in data["installments"])


async def test_go_refuses_old_work_and_inactive_contract_billing(
    client: AsyncClient, seeded: SeededData
) -> None:
    await paid_python_then_go(client, seeded)
    path = f"/api/v1/mentor/students/{seeded.student_id}/employment"
    old = await client.put(
        path,
        headers=auth(seeded.mentor_id),
        json={
            "company_name": "Old employer",
            "start_date": (datetime.now(UTC).date() - timedelta(days=10)).isoformat(),
            "net_salary_rubles": 200_000,
            "contract_billing_confirmed": True,
        },
    )
    assert old.status_code == 422, old.text
    assert old.json()["detail"]["code"] == "go_employment_predates_contract"
    async with TestSession() as session:
        contract = await session.scalar(select(ContractAcceptance))
        contract.status = "disputed"
        await session.commit()
    data = await dashboard(client, seeded)
    assert Decimal(data["summary"]["remaining_salary_percent"]) == 100
    rejected = await client.put(
        path,
        headers=auth(seeded.mentor_id),
        json={
            "company_name": "Another employer",
            "start_date": datetime.now(UTC).date().isoformat(),
            "net_salary_rubles": 200_000,
            "contract_billing_confirmed": True,
        },
    )
    assert rejected.status_code == 409, rejected.text
    async with TestSession() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(LegalAuditEvent)
                .where(LegalAuditEvent.event_type == "go_employment.billing_confirmed")
            )
            == 0
        )
