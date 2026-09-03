from __future__ import annotations

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import UniqueConstraint, func, select

from app.core.config import get_settings
from app.employment_qualification import service as employment_service
from app.employment_qualification.models import (
    EmploymentBillingEvent,
    EmploymentContractPolicySnapshot,
    EmploymentProfileAssessment,
    EmploymentQualificationWindow,
)
from app.payments.models import PaymentInstallment, StudentEmployment
from tests.conftest import SeededData, TestSession, auth


@pytest.fixture(autouse=True)
def employment_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        employment_service,
        "settings",
        get_settings().model_copy(update={"employment_qualification_ai_enabled": False}),
    )


async def create_policy(
    client: AsyncClient,
    seeded: SeededData,
    *,
    start: str = "2026-01-01",
    end: str = "2026-12-31",
    extension: str | None = None,
    rules: dict[str, object] | None = None,
) -> None:
    response = await client.post(
        f"/api/v1/admin/students/{seeded.student_id}/employment-policies",
        headers=auth(seeded.admin_id),
        json={
            "track_id": str(seeded.python_track_id),
            "policy_code": "repeat-python-2026",
            "version": 1,
            "accepted_at": "2026-01-01T10:00:00Z",
            "control_period_started_at": start,
            "control_period_ended_at": end,
            "extension_ended_at": extension,
            "rules": rules or {"main_period_ended_at": "2026-03-31"},
        },
    )
    assert response.status_code == 201, response.text


async def report_offer(
    client: AsyncClient,
    seeded: SeededData,
    *,
    vacancy_title: str = "PHP Developer",
    vacancy_stack: list[str] | None = None,
    salary: int | None = 200_000,
) -> dict[str, object]:
    response = await client.post(
        "/api/v1/employment-cases/me/report-offer",
        headers=auth(seeded.student_id),
        json={
            "track_id": str(seeded.python_track_id),
            "employer_name": "Example Corp",
            "vacancy_title": vacancy_title,
            "activity_type": "employment_contract",
            "offer_received_at": "2026-02-01",
            "expected_start_date": "2026-03-01",
            "vacancy_stack": vacancy_stack or ["PHP"],
            "offer_stack": vacancy_stack or ["PHP"],
            "net_salary_rubles": salary,
            "idempotency_key": "offer-idempotency-0001",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def report_work(
    client: AsyncClient,
    seeded: SeededData,
    case: dict[str, object],
    *,
    started_at: str = "2026-03-01",
    actual_stack: list[str] | None = None,
    usages: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    response = await client.post(
        f"/api/v1/employment-cases/{case['id']}/work-start",
        headers=auth(seeded.student_id),
        json={
            "employment_started_at": started_at,
            "official_job_title": "PHP Developer",
            "actual_duties": "Регулярно разрабатываю и сопровождаю внутренние сервисы.",
            "actual_stack": actual_stack or ["PHP", "Python"],
            "technology_usages": usages
            or [
                {
                    "normalized_name": "Python",
                    "usage_type": "coding",
                    "frequency": "regular",
                    "part_of_official_duties": "yes",
                    "part_of_project": "yes",
                    "started_at": started_at,
                }
            ],
            "expected_lock_version": case["lock_version"],
            "idempotency_key": "work-idempotency-0001",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def assess(
    client: AsyncClient,
    seeded: SeededData,
    case: dict[str, object],
    *,
    classification: str = "mixed_profile",
    profile_started_at: str | None = "2026-03-01",
    key: str = "assessment-idempotency-0001",
) -> dict[str, object]:
    response = await client.post(
        f"/api/v1/mentor/students/{seeded.student_id}/employment-cases/{case['id']}/assessments",
        headers=auth(seeded.mentor_id),
        json={
            "classification": classification,
            "effective_profile_started_at": profile_started_at,
            "rationale": "Подтверждена регулярная работа с кодом выбранного направления.",
            "qualifying_criteria": (
                [{"criterion": "coding", "technology": "Python"}] if profile_started_at else []
            ),
            "non_qualifying_reasons": (
                ["Нет существенного использования языка"] if classification == "non_profile" else []
            ),
            "evidence_ids": [],
            "expected_lock_version": case["lock_version"],
            "idempotency_key": key,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_title_and_vacancy_stack_never_create_profile_or_billing(
    client: AsyncClient, seeded: SeededData
) -> None:
    await create_policy(client, seeded)
    case = await report_offer(
        client, seeded, vacancy_title="Python Developer", vacancy_stack=["Python"]
    )
    assert case["profile_activity_started_at"] is None
    assert case["assessments"] == []
    assert case["billing_status"] is None
    async with TestSession() as session:
        assert await session.scalar(select(func.count(PaymentInstallment.id))) == 0


@pytest.mark.asyncio
async def test_php_title_regular_python_can_be_confirmed_mixed_and_billed_once(
    client: AsyncClient, seeded: SeededData
) -> None:
    await create_policy(client, seeded)
    case = await report_work(client, seeded, await report_offer(client, seeded))
    confirmed = await assess(client, seeded, case)
    replay = await client.post(
        f"/api/v1/mentor/students/{seeded.student_id}/employment-cases/{case['id']}/assessments",
        headers=auth(seeded.mentor_id),
        json={
            "classification": "mixed_profile",
            "effective_profile_started_at": "2026-03-01",
            "rationale": "Подтверждена регулярная работа с кодом выбранного направления.",
            "qualifying_criteria": [{"criterion": "coding", "technology": "Python"}],
            "non_qualifying_reasons": [],
            "evidence_ids": [],
            "expected_lock_version": confirmed["lock_version"],
            "idempotency_key": "assessment-idempotency-0001",
        },
    )
    assert replay.status_code == 200, replay.text
    assert confirmed["official_job_title"] == "PHP Developer"
    assert confirmed["assessments"][-1]["classification"] == "mixed_profile"
    assert confirmed["qualification_window"]["billing_trigger_allowed"] is True
    async with TestSession() as session:
        assert await session.scalar(select(func.count(EmploymentProfileAssessment.id))) == 1
        assert await session.scalar(select(func.count(EmploymentBillingEvent.id))) == 1
        assert (await session.scalar(select(func.count(PaymentInstallment.id))) or 0) > 0


@pytest.mark.asyncio
async def test_profile_activity_date_not_job_start_drives_window(
    client: AsyncClient, seeded: SeededData
) -> None:
    await create_policy(client, seeded, start="2026-01-01", end="2026-04-30")
    case = await report_work(
        client,
        seeded,
        await report_offer(client, seeded),
        started_at="2026-02-01",
        usages=[
            {
                "normalized_name": "Python",
                "usage_type": "coding",
                "frequency": "regular",
                "part_of_official_duties": "yes",
                "part_of_project": "yes",
                "started_at": "2026-06-01",
            }
        ],
    )
    confirmed = await assess(client, seeded, case, profile_started_at="2026-06-01")
    assert confirmed["employment_started_at"] == "2026-02-01"
    assert confirmed["profile_activity_started_at"] == "2026-06-01"
    assert confirmed["qualification_window"]["classification"] == "outside_billable_window"
    assert confirmed["billing_status"] is None


@pytest.mark.asyncio
async def test_one_time_personal_usage_can_be_marked_non_profile_and_monitored(
    client: AsyncClient, seeded: SeededData
) -> None:
    await create_policy(client, seeded)
    case = await report_work(
        client,
        seeded,
        await report_offer(client, seeded),
        actual_stack=["PHP", "Python"],
        usages=[
            {
                "normalized_name": "Python",
                "usage_type": "automation",
                "frequency": "one_time",
                "part_of_official_duties": "no",
                "part_of_project": "no",
                "description": "Личный вспомогательный скрипт",
            }
        ],
    )
    reviewed = await assess(
        client,
        seeded,
        case,
        classification="non_profile",
        profile_started_at=None,
    )
    assert reviewed["case_status"] == "monitoring_non_profile"
    assert reviewed["billing_status"] is None
    assert any(item["followup_type"] == "monthly_change_check" for item in reviewed["followups"])


@pytest.mark.asyncio
async def test_legacy_case_does_not_receive_retroactive_debt(
    client: AsyncClient, seeded: SeededData
) -> None:
    case = await report_work(client, seeded, await report_offer(client, seeded))
    reviewed = await assess(client, seeded, case)
    assert reviewed["policy_is_legacy"] is True
    assert reviewed["qualification_window"]["classification"] == "insufficient_data"
    async with TestSession() as session:
        assert await session.scalar(select(func.count(EmploymentBillingEvent.id))) == 0
        assert await session.scalar(select(func.count(PaymentInstallment.id))) == 0


@pytest.mark.asyncio
async def test_student_case_is_hidden_from_unassigned_mentor(
    client: AsyncClient, seeded: SeededData
) -> None:
    await report_offer(client, seeded)
    response = await client.get(
        f"/api/v1/mentor/students/{seeded.student_id}/employment-cases",
        headers=auth(seeded.other_mentor_id),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_offer_acceptance_and_contract_signing_are_separate_events(
    client: AsyncClient, seeded: SeededData
) -> None:
    case = await report_offer(client, seeded)
    accepted = await client.post(
        f"/api/v1/employment-cases/{case['id']}/offer-status",
        headers=auth(seeded.student_id),
        json={
            "event": "offer_accepted",
            "effective_at": "2026-02-03",
            "expected_lock_version": case["lock_version"],
            "idempotency_key": "offer-accepted-event-0001",
        },
    )
    assert accepted.status_code == 200, accepted.text
    accepted_case = accepted.json()
    replay = await client.post(
        f"/api/v1/employment-cases/{case['id']}/offer-status",
        headers=auth(seeded.student_id),
        json={
            "event": "offer_accepted",
            "effective_at": "2026-02-03",
            "expected_lock_version": case["lock_version"],
            "idempotency_key": "offer-accepted-event-0001",
        },
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["lock_version"] == accepted_case["lock_version"]
    signed = await client.post(
        f"/api/v1/employment-cases/{case['id']}/offer-status",
        headers=auth(seeded.student_id),
        json={
            "event": "contract_signed",
            "effective_at": "2026-02-05",
            "expected_lock_version": accepted_case["lock_version"],
            "idempotency_key": "contract-signed-event-0001",
        },
    )
    assert signed.status_code == 200, signed.text
    body = signed.json()
    assert body["offer_accepted_at"] == "2026-02-03"
    assert body["contract_signed_at"] == "2026-02-05"
    assert {event["event_type"] for event in body["events"]} >= {
        "offer_accepted",
        "contract_signed",
    }


@pytest.mark.asyncio
async def test_nested_staff_case_url_rejects_mismatched_student(
    client: AsyncClient, seeded: SeededData
) -> None:
    case = await report_offer(client, seeded)
    response = await client.post(
        f"/api/v1/mentor/students/{seeded.admin_id}/employment-cases/{case['id']}/request-information",
        headers=auth(seeded.admin_id),
        json={
            "requested_fields": ["actual_duties"],
            "due_at": "2026-03-10",
            "idempotency_key": "mismatched-student-0001",
        },
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_dispute_holds_and_admin_resolution_releases_billing(
    client: AsyncClient, seeded: SeededData
) -> None:
    await create_policy(client, seeded)
    case = await assess(
        client,
        seeded,
        await report_work(client, seeded, await report_offer(client, seeded)),
    )
    opened = await client.post(
        f"/api/v1/employment-cases/{case['id']}/disputes",
        headers=auth(seeded.student_id),
        json={
            "disputed_conclusion": "start_date",
            "reason": "Дата начала профильной работы указана неверно и требует проверки.",
            "alternative_started_at": "2026-03-10",
            "idempotency_key": "dispute-idempotency-0001",
        },
    )
    assert opened.status_code == 200, opened.text
    opened_case = opened.json()
    assert opened_case["billing_on_hold"] is True
    dispute_id = opened_case["disputes"][0]["id"]
    same_reviewer = await client.post(
        f"/api/v1/mentor/students/{seeded.student_id}/employment-cases/{case['id']}/disputes/{dispute_id}/resolve",
        headers=auth(seeded.mentor_id),
        json={
            "resolution": "Проверили исходные сведения, решение оставлено без изменений.",
            "outcome": "rejected",
        },
    )
    assert same_reviewer.status_code == 403
    resolved = await client.post(
        f"/api/v1/mentor/students/{seeded.student_id}/employment-cases/{case['id']}/disputes/{dispute_id}/resolve",
        headers=auth(seeded.admin_id),
        json={
            "resolution": "Независимая проверка завершена, решение оставлено без изменений.",
            "outcome": "rejected",
        },
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["billing_on_hold"] is False
    assert resolved.json()["billing_status"] == "processed"


def test_policy_and_assessment_models_have_immutable_business_identity() -> None:
    assert EmploymentContractPolicySnapshot.__table__.c.policy_code.nullable is False
    assert EmploymentProfileAssessment.__table__.c.supersedes_assessment_id.nullable is True
    assert any(
        isinstance(constraint, UniqueConstraint)
        and [column.name for column in constraint.columns] == ["assessment_id"]
        for constraint in EmploymentQualificationWindow.__table__.constraints
    )


def test_employment_reuses_existing_payment_employment_model() -> None:
    assert StudentEmployment.__tablename__ == "student_employments"
    assert "profile_activity_started_at" in StudentEmployment.__table__.c


def test_actual_duties_due_date_uses_business_days() -> None:
    assert employment_service._add_business_days(date(2026, 9, 4), 10) == date(2026, 9, 18)
