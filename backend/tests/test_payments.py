from datetime import date
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import select

from app.interviews.uploads import StoredUpload
from app.mentors.models import MentorStudent
from app.payments.models import (
    MentorPayout,
    MentorPayoutAllocation,
    MentorPayoutStatus,
    MentorReward,
    MentorRewardKind,
    PaymentAttempt,
    PaymentAttemptStatus,
    PaymentInstallment,
    PaymentInstallmentStatus,
    StudentEmployment,
)
from app.payments.service import (
    calculate_due_dates,
    calculate_installment_amounts,
    ensure_mentor_payout_receipt_upload_allowed,
    payout_receipt_upload,
    set_mentor_payout_receipt,
)
from app.users.models import User
from tests.conftest import SeededData, TestSession, auth


def test_python_payment_schedule_contains_eight_salary_quarters() -> None:
    assert calculate_installment_amounts(20_000_000, Decimal("200")) == [5_000_000] * 8


def test_go_payment_schedule_contains_six_salary_quarters() -> None:
    assert calculate_installment_amounts(20_000_000, Decimal("150")) == [5_000_000] * 6


def test_last_installment_closes_non_standard_percentage_exactly() -> None:
    amounts = calculate_installment_amounts(10_001, Decimal("110"))
    assert sum(amounts) == 11_001
    assert amounts == [2_500, 2_500, 2_500, 2_500, 1_001]


def test_first_payment_is_first_selected_day_after_full_month() -> None:
    assert calculate_due_dates(date(2026, 8, 12), (10, 25), 4) == [
        date(2026, 9, 25),
        date(2026, 10, 10),
        date(2026, 10, 25),
        date(2026, 11, 10),
    ]


async def _seed_mentor_rewards(seeded: SeededData, *amounts: int) -> None:
    async with TestSession() as session:
        session.add_all(
            [
                MentorReward(
                    student_id=seeded.student_id,
                    mentor_id=seeded.mentor_id,
                    kind=MentorRewardKind.EMPLOYMENT_PAYMENT,
                    amount_kopecks=amount,
                    paid_kopecks=0,
                )
                for amount in amounts
            ]
        )
        await session.commit()


async def test_admin_can_pay_aggregate_mentor_balance_partially(
    client: AsyncClient, seeded: SeededData
) -> None:
    await _seed_mentor_rewards(seeded, 1_000_000, 1_000_000)

    before = await client.get(
        "/api/v1/admin/payments/mentor-payouts",
        headers=auth(seeded.admin_id),
    )
    assert before.status_code == 200, before.text
    assert before.json()["balances"][0]["available_kopecks"] == 2_000_000

    paid = await client.post(
        f"/api/v1/admin/payments/mentors/{seeded.mentor_id}/payouts",
        headers=auth(seeded.admin_id),
        json={"amount_rubles": 15_000, "payment_reference": "Акт №15"},
    )
    assert paid.status_code == 200, paid.text
    balance = paid.json()["balances"][0]
    assert balance["paid_kopecks"] == 1_500_000
    assert balance["available_kopecks"] == 500_000
    payout = paid.json()["payouts"][0]
    assert payout["status"] == "paid"
    assert payout["payment_reference"] == "Акт №15"

    async with TestSession() as session:
        rewards = list(
            await session.scalars(
                select(MentorReward).where(MentorReward.mentor_id == seeded.mentor_id)
            )
        )
        allocations = list(
            await session.scalars(
                select(MentorPayoutAllocation).where(
                    MentorPayoutAllocation.payout_id == payout["id"]
                )
            )
        )
    assert sorted(reward.paid_kopecks for reward in rewards) == [500_000, 1_000_000]
    assert sum(item.amount_kopecks for item in allocations) == 1_500_000


async def test_mentor_request_reserves_balance_until_admin_pays_it(
    client: AsyncClient, seeded: SeededData
) -> None:
    await _seed_mentor_rewards(seeded, 3_000_000)

    requested = await client.post(
        "/api/v1/mentor/payouts",
        headers=auth(seeded.mentor_id),
        json={"amount_rubles": 20_000},
    )
    assert requested.status_code == 200, requested.text
    summary = requested.json()
    assert summary["reserved_kopecks"] == 2_000_000
    assert summary["available_kopecks"] == 1_000_000
    payout_id = summary["payouts"][0]["id"]

    duplicate = await client.post(
        "/api/v1/mentor/payouts",
        headers=auth(seeded.mentor_id),
        json={"amount_rubles": 1_000},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "mentor_payout_already_requested"

    double_spend = await client.post(
        f"/api/v1/admin/payments/mentors/{seeded.mentor_id}/payouts",
        headers=auth(seeded.admin_id),
        json={"amount_rubles": 15_000},
    )
    assert double_spend.status_code == 409
    assert double_spend.json()["detail"]["code"] == "mentor_payout_exceeds_available"

    paid = await client.post(
        f"/api/v1/admin/payments/payouts/{payout_id}/mark-paid",
        headers=auth(seeded.admin_id),
        json={"payment_reference": "Акт №20"},
    )
    assert paid.status_code == 200, paid.text
    assert paid.json()["balances"][0]["paid_kopecks"] == 2_000_000
    assert paid.json()["balances"][0]["reserved_kopecks"] == 0
    assert paid.json()["balances"][0]["available_kopecks"] == 1_000_000


async def test_cancelled_mentor_request_releases_balance(
    client: AsyncClient, seeded: SeededData
) -> None:
    await _seed_mentor_rewards(seeded, 1_000_000)
    requested = await client.post(
        "/api/v1/mentor/payouts",
        headers=auth(seeded.mentor_id),
        json={"amount_rubles": 7_500},
    )
    payout_id = requested.json()["payouts"][0]["id"]

    cancelled = await client.post(
        f"/api/v1/mentor/payouts/{payout_id}/cancel",
        headers=auth(seeded.mentor_id),
        json={"reason": "Передумал"},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["reserved_kopecks"] == 0
    assert cancelled.json()["available_kopecks"] == 1_000_000
    assert cancelled.json()["payouts"][0]["status"] == "cancelled"


async def test_paid_mentor_can_optionally_attach_private_receipt(
    client: AsyncClient, seeded: SeededData
) -> None:
    await _seed_mentor_rewards(seeded, 1_000_000)
    requested = await client.post(
        "/api/v1/mentor/payouts",
        headers=auth(seeded.mentor_id),
        json={"amount_rubles": 10_000},
    )
    payout_id = requested.json()["payouts"][0]["id"]

    async with TestSession() as session:
        mentor = await session.get(User, seeded.mentor_id)
        assert mentor is not None
        with pytest.raises(HTTPException) as error:
            await ensure_mentor_payout_receipt_upload_allowed(session, mentor, payout_id)
        assert error.value.status_code == 409

    paid = await client.post(
        f"/api/v1/admin/payments/payouts/{payout_id}/mark-paid",
        headers=auth(seeded.admin_id),
        json={"payment_reference": None},
    )
    assert paid.status_code == 200, paid.text
    assert paid.json()["payouts"][0]["receipt_filename"] is None

    upload = StoredUpload(
        storage_key="mentor-payout-receipt/test/receipt.pdf",
        filename="receipt.pdf",
        content_type="application/pdf",
        size=1024,
    )
    async with TestSession() as session:
        mentor = await session.get(User, seeded.mentor_id)
        assert mentor is not None
        summary, previous_key = await set_mentor_payout_receipt(session, mentor, payout_id, upload)
        assert previous_key is None
        assert summary.payouts[0].receipt_filename == "receipt.pdf"

    async with TestSession() as session:
        admin = await session.get(User, seeded.admin_id)
        assert admin is not None
        stored = await payout_receipt_upload(session, admin, payout_id)
        assert stored.storage_key == upload.storage_key

        payout = await session.get(MentorPayout, payout_id)
        assert payout is not None
        assert payout.status is MentorPayoutStatus.PAID


async def test_mentor_records_employment_and_student_sees_schedule(
    client: AsyncClient, seeded: SeededData
) -> None:
    response = await client.put(
        f"/api/v1/mentor/students/{seeded.student_id}/employment",
        headers=auth(seeded.mentor_id),
        json={
            "company_name": "ООО Яндекс",
            "company_id": None,
            "start_date": "2026-08-12",
            "net_salary_rubles": 200_000,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["employment"]["company_name"] == "Яндекс"
    assert payload["summary"]["total_owed_kopecks"] == 40_000_000
    assert len(payload["installments"]) == 8
    assert payload["installments"][0]["due_date"] == "2026-09-25"

    student_response = await client.get("/api/v1/payments/me", headers=auth(seeded.student_id))
    assert student_response.status_code == 200
    assert student_response.json()["installments"][0]["can_pay"] is True


async def test_other_mentor_cannot_manage_student_payments(
    client: AsyncClient, seeded: SeededData
) -> None:
    response = await client.put(
        f"/api/v1/mentor/students/{seeded.student_id}/employment",
        headers=auth(seeded.other_mentor_id),
        json={
            "company_name": "Yandex",
            "start_date": "2026-08-12",
            "net_salary_rubles": 200_000,
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "student_not_assigned_to_mentor"


async def test_student_can_change_two_payment_days(client: AsyncClient, seeded: SeededData) -> None:
    await client.put(
        f"/api/v1/mentor/students/{seeded.student_id}/employment",
        headers=auth(seeded.mentor_id),
        json={
            "company_name": "Yandex",
            "start_date": "2026-08-12",
            "net_salary_rubles": 200_000,
        },
    )
    response = await client.put(
        "/api/v1/payments/me/schedule",
        headers=auth(seeded.student_id),
        json={"payment_days": [5, 20]},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["employment"]["payment_days"] == [5, 20]
    assert payload["installments"][0]["due_date"] == "2026-09-20"

    invalid = await client.put(
        "/api/v1/payments/me/schedule",
        headers=auth(seeded.student_id),
        json={"payment_days": [10, 10]},
    )
    assert invalid.status_code == 422


async def test_admin_manual_confirmation_accrues_configured_mentor_reward(
    client: AsyncClient, seeded: SeededData
) -> None:
    async with TestSession() as session:
        relation = await session.scalar(
            select(MentorStudent).where(MentorStudent.student_id == seeded.student_id)
        )
        assert relation is not None
        relation.reward_percent = Decimal("40")
        await session.commit()

    dashboard = await client.put(
        f"/api/v1/mentor/students/{seeded.student_id}/employment",
        headers=auth(seeded.mentor_id),
        json={
            "company_name": "Yandex",
            "start_date": "2026-08-12",
            "net_salary_rubles": 200_000,
        },
    )
    installment_id = dashboard.json()["installments"][0]["id"]
    response = await client.post(
        f"/api/v1/admin/payments/installments/{installment_id}/confirm",
        headers=auth(seeded.admin_id),
    )
    assert response.status_code == 200, response.text
    assert response.json()["summary"]["paid_kopecks"] == 5_000_000

    async with TestSession() as session:
        installment = await session.get(PaymentInstallment, installment_id)
        reward = await session.scalar(
            select(MentorReward).where(MentorReward.installment_id == installment_id)
        )
        assert installment is not None
        assert installment.status is PaymentInstallmentStatus.PAID
        assert reward is not None
        assert reward.mentor_id == seeded.mentor_id
        # 40% is the mentor's share of one full salary. The student owes 200%,
        # so a 25%-of-salary installment pays 25 / 200 of that mentor share.
        assert reward.amount_kopecks == 1_000_000


async def test_python_mentor_gets_seven_and_a_half_percent_after_one_installment(
    client: AsyncClient, seeded: SeededData
) -> None:
    async with TestSession() as session:
        student = await session.get(User, seeded.student_id)
        relation = await session.scalar(
            select(MentorStudent).where(MentorStudent.student_id == seeded.student_id)
        )
        assert student is not None
        assert relation is not None
        student.repayment_percent = Decimal("200")
        relation.reward_percent = Decimal("60")
        await session.commit()

    dashboard = await client.put(
        f"/api/v1/mentor/students/{seeded.student_id}/employment",
        headers=auth(seeded.mentor_id),
        json={
            "company_name": "Yandex",
            "start_date": "2026-08-12",
            "net_salary_rubles": 200_000,
        },
    )
    assert dashboard.status_code == 200, dashboard.text
    installment_id = dashboard.json()["installments"][0]["id"]

    async with TestSession() as session:
        before_payment = await session.scalar(
            select(MentorReward).where(MentorReward.mentor_id == seeded.mentor_id)
        )
        assert before_payment is None

    confirmed = await client.post(
        f"/api/v1/admin/payments/installments/{installment_id}/confirm",
        headers=auth(seeded.admin_id),
    )
    assert confirmed.status_code == 200, confirmed.text

    after_payment = await client.get(
        f"/api/v1/admin/payments/mentors/{seeded.mentor_id}",
        headers=auth(seeded.admin_id),
    )
    assert after_payment.status_code == 200, after_payment.text
    # The student paid 25% of salary. At a 60% mentor share on a 200%
    # repayment contract this unlocks 25 * 60 / 200 = 7.5% of salary.
    assert after_payment.json()["available_kopecks"] == 1_500_000


async def test_admin_finance_registry_groups_students_and_exposes_overdue_detail(
    client: AsyncClient, seeded: SeededData
) -> None:
    dashboard = await client.put(
        f"/api/v1/mentor/students/{seeded.student_id}/employment",
        headers=auth(seeded.mentor_id),
        json={
            "company_name": "Yandex",
            "start_date": "2025-01-01",
            "net_salary_rubles": 200_000,
        },
    )
    assert dashboard.status_code == 200, dashboard.text

    registry = await client.get(
        "/api/v1/admin/payments/students",
        headers=auth(seeded.admin_id),
    )
    assert registry.status_code == 200, registry.text
    payload = registry.json()
    assert payload["total"] == 1
    assert payload["items"][0]["student_id"] == str(seeded.student_id)
    assert payload["items"][0]["company_name"] == "Yandex"
    assert payload["items"][0]["remaining_kopecks"] == 40_000_000
    assert payload["items"][0]["overdue_kopecks"] == 40_000_000
    assert payload["items"][0]["overdue_payments"] == 8
    assert payload["total_overdue_kopecks"] == 40_000_000

    detail = await client.get(
        f"/api/v1/admin/payments/students/{seeded.student_id}",
        headers=auth(seeded.admin_id),
    )
    assert detail.status_code == 200, detail.text
    assert len(detail.json()["installments"]) == 8
    assert detail.json()["can_manage_payment_days"] is True

    overdue = await client.get(
        "/api/v1/admin/payments/overdue",
        headers=auth(seeded.admin_id),
    )
    assert overdue.status_code == 200, overdue.text
    assert overdue.json()["total"] == 8
    assert {item["student_id"] for item in overdue.json()["items"]} == {str(seeded.student_id)}

    async with TestSession() as session:
        relation = await session.scalar(
            select(MentorStudent).where(MentorStudent.student_id == seeded.student_id)
        )
        assert relation is not None
        relation.reward_percent = Decimal("40")
        await session.commit()

    installment_id = dashboard.json()["installments"][0]["id"]
    confirmed = await client.post(
        f"/api/v1/admin/payments/installments/{installment_id}/confirm",
        headers=auth(seeded.admin_id),
    )
    assert confirmed.status_code == 200, confirmed.text

    mentor_detail = await client.get(
        f"/api/v1/admin/payments/mentors/{seeded.mentor_id}",
        headers=auth(seeded.admin_id),
    )
    assert mentor_detail.status_code == 200, mentor_detail.text
    mentor_payload = mentor_detail.json()
    assert mentor_payload["mentor_id"] == str(seeded.mentor_id)
    assert mentor_payload["rewards"][0]["student_id"] == str(seeded.student_id)
    assert mentor_payload["rewards"][0]["company_name"] == "Yandex"
    assert mentor_payload["available_kopecks"] > 0


async def test_admin_can_revoke_an_incorrectly_confirmed_payment(
    client: AsyncClient, seeded: SeededData
) -> None:
    async with TestSession() as session:
        relation = await session.scalar(
            select(MentorStudent).where(MentorStudent.student_id == seeded.student_id)
        )
        assert relation is not None
        relation.reward_percent = Decimal("40")
        await session.commit()

    dashboard = await client.put(
        f"/api/v1/mentor/students/{seeded.student_id}/employment",
        headers=auth(seeded.mentor_id),
        json={
            "company_name": "Yandex",
            "start_date": "2026-08-12",
            "net_salary_rubles": 200_000,
        },
    )
    installment_id = dashboard.json()["installments"][0]["id"]
    confirmed = await client.post(
        f"/api/v1/admin/payments/installments/{installment_id}/confirm",
        headers=auth(seeded.admin_id),
    )
    assert confirmed.status_code == 200, confirmed.text

    revoked = await client.post(
        f"/api/v1/admin/payments/installments/{installment_id}/revoke",
        headers=auth(seeded.admin_id),
        json={"reason": "Подтверждено по ошибке"},
    )
    assert revoked.status_code == 200, revoked.text
    item = next(item for item in revoked.json()["installments"] if item["id"] == installment_id)
    assert item["status"] == "scheduled"
    assert item["paid_at"] is None
    assert item["revoked_at"] is not None
    assert item["revocation_reason"] == "Подтверждено по ошибке"
    assert revoked.json()["summary"]["paid_kopecks"] == 0

    async with TestSession() as session:
        installment = await session.get(PaymentInstallment, installment_id)
        reward = await session.scalar(
            select(MentorReward).where(MentorReward.installment_id == installment_id)
        )
        assert installment is not None
        assert installment.revoked_by_user_id == seeded.admin_id
        assert reward is None


async def test_payment_revocation_is_blocked_after_mentor_reward_was_paid(
    client: AsyncClient, seeded: SeededData
) -> None:
    async with TestSession() as session:
        relation = await session.scalar(
            select(MentorStudent).where(MentorStudent.student_id == seeded.student_id)
        )
        assert relation is not None
        relation.reward_percent = Decimal("40")
        await session.commit()

    dashboard = await client.put(
        f"/api/v1/mentor/students/{seeded.student_id}/employment",
        headers=auth(seeded.mentor_id),
        json={
            "company_name": "Yandex",
            "start_date": "2026-08-12",
            "net_salary_rubles": 200_000,
        },
    )
    installment_id = dashboard.json()["installments"][0]["id"]
    await client.post(
        f"/api/v1/admin/payments/installments/{installment_id}/confirm",
        headers=auth(seeded.admin_id),
    )
    paid_to_mentor = await client.post(
        f"/api/v1/admin/payments/mentors/{seeded.mentor_id}/payouts",
        headers=auth(seeded.admin_id),
        json={"amount_rubles": 10_000, "payment_reference": "Акт №1"},
    )
    assert paid_to_mentor.status_code == 200, paid_to_mentor.text

    revoked = await client.post(
        f"/api/v1/admin/payments/installments/{installment_id}/revoke",
        headers=auth(seeded.admin_id),
        json={"reason": "Ошибочное подтверждение"},
    )
    assert revoked.status_code == 409
    assert revoked.json()["detail"]["code"] == "mentor_reward_already_distributed"


async def test_terminated_employment_carries_paid_percent_to_new_job(
    client: AsyncClient, seeded: SeededData
) -> None:
    first = await client.put(
        f"/api/v1/mentor/students/{seeded.student_id}/employment",
        headers=auth(seeded.mentor_id),
        json={
            "company_name": "Первая компания",
            "start_date": "2026-08-01",
            "net_salary_rubles": 200_000,
        },
    )
    for installment in first.json()["installments"][:3]:
        confirmed = await client.post(
            f"/api/v1/admin/payments/installments/{installment['id']}/confirm",
            headers=auth(seeded.admin_id),
        )
        assert confirmed.status_code == 200, confirmed.text

    terminated = await client.post(
        f"/api/v1/mentor/students/{seeded.student_id}/employment/terminate",
        headers=auth(seeded.mentor_id),
        json={"ended_at": "2026-11-01", "reason": "Сокращение"},
    )
    assert terminated.status_code == 200, terminated.text
    terminated_data = terminated.json()
    assert terminated_data["employment"] is None
    assert terminated_data["summary"]["paid_salary_percent"] == "75.00"
    assert terminated_data["summary"]["remaining_salary_percent"] == "125.00"
    assert sum(item["status"] == "cancelled" for item in terminated_data["installments"]) == 5

    second = await client.put(
        f"/api/v1/mentor/students/{seeded.student_id}/employment",
        headers=auth(seeded.mentor_id),
        json={
            "company_name": "Новая компания",
            "start_date": "2027-01-15",
            "net_salary_rubles": 300_000,
        },
    )
    assert second.status_code == 200, second.text
    data = second.json()
    assert data["employment"]["repayment_percent"] == "125.00"
    active = [item for item in data["installments"] if item["status"] != "cancelled"]
    assert [item["salary_percent"] for item in active[-5:]] == ["25.00"] * 5
    assert sum(item["amount_kopecks"] for item in active[-5:]) == 37_500_000


async def test_terminated_employment_without_payments_restarts_full_obligation(
    client: AsyncClient, seeded: SeededData
) -> None:
    first = await client.put(
        f"/api/v1/mentor/students/{seeded.student_id}/employment",
        headers=auth(seeded.mentor_id),
        json={
            "company_name": "Первая компания",
            "start_date": "2026-08-01",
            "net_salary_rubles": 200_000,
        },
    )
    assert first.status_code == 200, first.text

    terminated = await client.post(
        f"/api/v1/mentor/students/{seeded.student_id}/employment/terminate",
        headers=auth(seeded.mentor_id),
        json={"ended_at": "2026-08-20", "reason": "Увольнение"},
    )
    assert terminated.status_code == 200, terminated.text
    assert Decimal(terminated.json()["summary"]["paid_salary_percent"]) == Decimal("0")
    assert Decimal(terminated.json()["summary"]["remaining_salary_percent"]) == Decimal("200")
    assert all(item["status"] == "cancelled" for item in terminated.json()["installments"])

    second = await client.put(
        f"/api/v1/mentor/students/{seeded.student_id}/employment",
        headers=auth(seeded.mentor_id),
        json={
            "company_name": "Новая компания",
            "start_date": "2026-10-01",
            "net_salary_rubles": 250_000,
        },
    )
    assert second.status_code == 200, second.text
    assert second.json()["employment"]["repayment_percent"] == "200.00"
    active = [item for item in second.json()["installments"] if item["status"] == "scheduled"]
    assert len(active) == 8
    assert sum(item["amount_kopecks"] for item in active) == 50_000_000


async def test_entry_and_exclusion_create_one_time_mentor_rewards(
    client: AsyncClient, seeded: SeededData
) -> None:
    create_payload = {
        "telegram_id": 700000001,
        "telegram_username": "payment_student",
        "first_name": "Платёжный",
        "last_name": "Ученик",
        "email": "payment-student@example.com",
        "learning_start_date": "2026-08-10",
        "mentor_id": str(seeded.mentor_id),
        "track_ids": [str(seeded.python_track_id)],
        "repayment_percent": 200,
        "mentor_reward_percent": 60,
        "entry_payment_rubles": 45_000,
        "entry_payment_paid": True,
        "program_excluded": False,
        "program_exclusion_reason": None,
    }
    created = await client.post(
        "/api/v1/admin/students",
        headers=auth(seeded.admin_id),
        json=create_payload,
    )
    assert created.status_code == 201, created.text
    student_id = created.json()["id"]

    employment = await client.put(
        f"/api/v1/mentor/students/{student_id}/employment",
        headers=auth(seeded.mentor_id),
        json={
            "company_name": "Компания до исключения",
            "start_date": "2026-08-10",
            "net_salary_rubles": 150_000,
        },
    )
    assert employment.status_code == 200, employment.text

    excluded = await client.put(
        f"/api/v1/admin/students/{student_id}",
        headers=auth(seeded.admin_id),
        json={
            **create_payload,
            "program_excluded": True,
            "program_exclusion_reason": "Не продолжил обучение",
        },
    )
    assert excluded.status_code == 200, excluded.text
    assert excluded.json()["is_active"] is False

    async with TestSession() as session:
        rewards = list(
            await session.scalars(select(MentorReward).where(MentorReward.student_id == student_id))
        )
        installments = list(
            await session.scalars(
                select(PaymentInstallment)
                .join(StudentEmployment)
                .where(StudentEmployment.student_id == student_id)
            )
        )
    assert {reward.kind for reward in rewards} == {
        MentorRewardKind.ENTRY_PAYMENT,
        MentorRewardKind.PROGRAM_EXCLUSION,
    }
    assert {reward.amount_kopecks for reward in rewards} == {1_000_000}
    assert installments
    assert all(item.status is PaymentInstallmentStatus.CANCELLED for item in installments)

    admin_page = await client.get(
        "/api/v1/admin/payments",
        headers=auth(seeded.admin_id),
    )
    assert admin_page.status_code == 200, admin_page.text
    student_rewards = [
        reward
        for reward in admin_page.json()["mentor_rewards"]
        if reward["student_id"] == student_id
    ]
    assert len(student_rewards) == 2
    assert {reward["mentor_id"] for reward in student_rewards} == {str(seeded.mentor_id)}
    assert {reward["mentor_name"] for reward in student_rewards} == {"Антон"}


async def test_development_payment_link_is_idempotent(
    client: AsyncClient, seeded: SeededData
) -> None:
    dashboard = await client.put(
        f"/api/v1/mentor/students/{seeded.student_id}/employment",
        headers=auth(seeded.mentor_id),
        json={
            "company_name": "Yandex",
            "start_date": "2026-08-12",
            "net_salary_rubles": 200_000,
        },
    )
    installment_id = dashboard.json()["installments"][0]["id"]
    first = await client.post(
        f"/api/v1/payments/installments/{installment_id}/link",
        headers=auth(seeded.student_id),
    )
    second = await client.post(
        f"/api/v1/payments/installments/{installment_id}/link",
        headers=auth(seeded.student_id),
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["payment_url"] == second.json()["payment_url"]


async def test_tochka_webhook_confirms_payment_once(
    client: AsyncClient, seeded: SeededData
) -> None:
    dashboard = await client.put(
        f"/api/v1/mentor/students/{seeded.student_id}/employment",
        headers=auth(seeded.mentor_id),
        json={
            "company_name": "Yandex",
            "start_date": "2026-08-12",
            "net_salary_rubles": 200_000,
        },
    )
    installment_id = dashboard.json()["installments"][0]["id"]
    link = await client.post(
        f"/api/v1/payments/installments/{installment_id}/link",
        headers=auth(seeded.student_id),
    )
    payment_link_id = parse_qs(urlparse(link.json()["payment_url"]).query)["local_payment"][0]
    payload = {
        "eventType": "acquiringInternetPayment",
        "eventId": "evt-payment-1",
        "Data": {
            "paymentLinkId": payment_link_id,
            "operationId": "operation-1",
            "status": "APPROVED",
        },
    }
    first = await client.post("/api/v1/payments/tochka/webhook", json=payload)
    duplicate = await client.post("/api/v1/payments/tochka/webhook", json=payload)
    assert first.status_code == duplicate.status_code == 200
    assert first.json() == {"status": "ok"}
    assert duplicate.json() == {"status": "duplicate"}

    result = await client.get("/api/v1/payments/me", headers=auth(seeded.student_id))
    assert result.json()["installments"][0]["status"] == "paid"


async def test_revoked_bank_payment_is_not_restored_by_a_late_webhook(
    client: AsyncClient, seeded: SeededData
) -> None:
    dashboard = await client.put(
        f"/api/v1/mentor/students/{seeded.student_id}/employment",
        headers=auth(seeded.mentor_id),
        json={
            "company_name": "Yandex",
            "start_date": "2026-08-12",
            "net_salary_rubles": 200_000,
        },
    )
    installment_id = dashboard.json()["installments"][0]["id"]
    link = await client.post(
        f"/api/v1/payments/installments/{installment_id}/link",
        headers=auth(seeded.student_id),
    )
    payment_link_id = parse_qs(urlparse(link.json()["payment_url"]).query)["local_payment"][0]

    first_webhook = await client.post(
        "/api/v1/payments/tochka/webhook",
        json={
            "eventType": "acquiringInternetPayment",
            "eventId": "evt-before-revocation",
            "Data": {
                "paymentLinkId": payment_link_id,
                "operationId": "revoked-operation",
                "status": "APPROVED",
            },
        },
    )
    assert first_webhook.status_code == 200, first_webhook.text
    revoked = await client.post(
        f"/api/v1/admin/payments/installments/{installment_id}/revoke",
        headers=auth(seeded.admin_id),
        json={"reason": "Банк не подтвердил фактическое списание"},
    )
    assert revoked.status_code == 200, revoked.text

    late_webhook = await client.post(
        "/api/v1/payments/tochka/webhook",
        json={
            "eventType": "acquiringInternetPayment",
            "eventId": "evt-after-revocation",
            "Data": {
                "paymentLinkId": payment_link_id,
                "operationId": "revoked-operation",
                "status": "APPROVED",
            },
        },
    )
    assert late_webhook.status_code == 200, late_webhook.text

    async with TestSession() as session:
        installment = await session.get(PaymentInstallment, installment_id)
        attempt = await session.scalar(
            select(PaymentAttempt).where(PaymentAttempt.installment_id == installment_id)
        )
        assert installment is not None
        assert installment.status is PaymentInstallmentStatus.SCHEDULED
        assert attempt is not None
        assert attempt.status is PaymentAttemptStatus.MANUAL_REVIEW


async def test_late_bank_approval_does_not_restore_cancelled_installment(
    client: AsyncClient, seeded: SeededData
) -> None:
    dashboard = await client.put(
        f"/api/v1/mentor/students/{seeded.student_id}/employment",
        headers=auth(seeded.mentor_id),
        json={
            "company_name": "Yandex",
            "start_date": "2026-08-12",
            "net_salary_rubles": 200_000,
        },
    )
    installment_id = dashboard.json()["installments"][0]["id"]
    link = await client.post(
        f"/api/v1/payments/installments/{installment_id}/link",
        headers=auth(seeded.student_id),
    )
    payment_link_id = parse_qs(urlparse(link.json()["payment_url"]).query)["local_payment"][0]

    terminated = await client.post(
        f"/api/v1/mentor/students/{seeded.student_id}/employment/terminate",
        headers=auth(seeded.mentor_id),
        json={"ended_at": "2026-08-20", "reason": "Увольнение"},
    )
    assert terminated.status_code == 200, terminated.text
    retry_link = await client.post(
        f"/api/v1/payments/installments/{installment_id}/link",
        headers=auth(seeded.student_id),
    )
    assert retry_link.status_code == 409

    webhook = await client.post(
        "/api/v1/payments/tochka/webhook",
        json={
            "eventType": "acquiringInternetPayment",
            "eventId": "evt-cancelled-payment",
            "Data": {
                "paymentLinkId": payment_link_id,
                "operationId": "late-operation",
                "status": "APPROVED",
            },
        },
    )
    assert webhook.status_code == 200, webhook.text

    async with TestSession() as session:
        installment = await session.get(PaymentInstallment, installment_id)
        attempt = await session.scalar(
            select(PaymentAttempt).where(PaymentAttempt.installment_id == installment_id)
        )
        reward = await session.scalar(
            select(MentorReward).where(MentorReward.installment_id == installment_id)
        )
        assert installment is not None
        assert installment.status is PaymentInstallmentStatus.CANCELLED
        assert attempt is not None
        assert attempt.status is PaymentAttemptStatus.MANUAL_REVIEW
        assert reward is None

    admin_page = await client.get(
        "/api/v1/admin/payments?status=cancelled",
        headers=auth(seeded.admin_id),
    )
    assert admin_page.status_code == 200, admin_page.text
    cancelled_item = next(
        item for item in admin_page.json()["items"] if item["installment_id"] == installment_id
    )
    assert cancelled_item["requires_manual_review"] is True
