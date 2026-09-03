from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx
import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy import func, select

from app.career_packages import router as career_router
from app.career_packages.email import CareerPackageEmailError, CareerPackageEmailService
from app.career_packages.models import (
    CareerDeliveryPurpose,
    CareerPackage,
    CareerPackageDelivery,
    CareerPackageObligation,
    CareerPackageStatus,
)
from app.career_packages.rendering import render_package_pdf
from app.career_packages.resume_text import _extract_path
from app.career_packages.schemas import (
    ActiveSearchParameters,
    CareerDraftMutation,
    CareerPackageAIOutput,
    CareerSourceData,
    SelfPresentationCard,
)
from app.career_packages.state_machine import transition
from app.core.config import get_settings
from app.mentors.models import MentorDocumentKind, MentorStudentDocument
from app.users.models import User
from tests.conftest import SeededData, TestSession, auth


@pytest.fixture(autouse=True)
def enable_career_packages(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings().model_copy(
        update={"career_package_enabled": True, "career_package_ai_enabled": False}
    )
    monkeypatch.setattr(career_router, "settings", settings)


def source_data() -> CareerSourceData:
    return CareerSourceData(
        target_positions=["Python backend developer"],
        target_seniority="middle",
        primary_stack=["Python", "FastAPI", "PostgreSQL"],
        employment_formats=["полная занятость"],
        geography=["Москва"],
        remote_preferences="удалённо или гибрид",
        relocation_preferences="не готов",
        salary_min=200_000,
        salary_target=250_000,
        salary_currency="RUB",
        search_start_date=date(2026, 9, 10),
        applications_per_week=25,
        preparation_priorities=["архитектура", "PostgreSQL"],
    )


def presentation() -> SelfPresentationCard:
    return SelfPresentationCard(
        target_position="Python backend developer",
        target_seniority="middle",
        short_positioning="Backend-разработчик с опытом продуктовой разработки.",
        self_presentation_structure=["Роль", "Проект", "Личный вклад"],
        preparation_checklist=["Проверить даты", "Подготовить метрики"],
    )


def search_parameters() -> ActiveSearchParameters:
    return ActiveSearchParameters(
        target_positions=["Python backend developer"],
        target_seniority="middle",
        primary_technology_stack=["Python", "FastAPI"],
        employment_formats=["полная занятость"],
        geography=["Москва"],
        remote_preferences="удалённо или гибрид",
        relocation_preferences="не готов",
        salary_min=200_000,
        salary_target=250_000,
        salary_currency="RUB",
        search_channels=["hh.ru", "Telegram"],
        applications_per_workday=5,
        applications_per_week=25,
        resume_refresh_schedule="раз в три дня",
        inbound_processing_rules=["ответить в течение часа"],
        interview_logging_rules=["добавить этап в платформу"],
        interview_preparation_priorities=["архитектура"],
        funnel_control_points=["ответы рекрутеров", "технические этапы"],
        resume_revision_threshold="нет ответов после 50 откликов",
        strategy_revision_threshold="нет технических интервью две недели",
        start_date=date(2026, 9, 10),
    )


@pytest.mark.asyncio
async def test_staff_create_is_idempotent_and_respects_assignment(
    client: AsyncClient, seeded: SeededData
) -> None:
    path = f"/api/v1/mentor/students/{seeded.student_id}/career-packages"
    payload = {"track_id": str(seeded.python_track_id)}
    first = await client.post(path, json=payload, headers=auth(seeded.mentor_id))
    second = await client.post(path, json=payload, headers=auth(seeded.mentor_id))
    forbidden = await client.get(path, headers=auth(seeded.other_mentor_id))

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["id"] == second.json()["id"]
    assert forbidden.status_code == 403
    async with TestSession() as session:
        assert await session.scalar(select(func.count(CareerPackage.id))) == 1


@pytest.mark.asyncio
async def test_draft_validation_is_strict(client: AsyncClient, seeded: SeededData) -> None:
    path = f"/api/v1/mentor/students/{seeded.student_id}/career-packages"
    created = await client.post(
        path,
        json={"track_id": str(seeded.python_track_id)},
        headers=auth(seeded.mentor_id),
    )
    package = created.json()
    invalid = await client.put(
        f"/api/v1/career-packages/{package['id']}/draft",
        json={"lock_version": package["lock_version"], "source_data": {"salary_min": -1}},
        headers=auth(seeded.mentor_id),
    )
    assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_staff_can_save_source_data(client: AsyncClient, seeded: SeededData) -> None:
    path = f"/api/v1/mentor/students/{seeded.student_id}/career-packages"
    created = await client.post(
        path,
        json={"track_id": str(seeded.python_track_id)},
        headers=auth(seeded.mentor_id),
    )
    package = created.json()

    saved = await client.put(
        f"/api/v1/career-packages/{package['id']}/draft",
        json={
            "lock_version": package["lock_version"],
            "source_data": source_data().model_dump(mode="json"),
        },
        headers=auth(seeded.mentor_id),
    )

    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["lock_version"] == package["lock_version"] + 1
    assert body["source_data"]["target_positions"] == ["Python backend developer"]
    assert body["source_data"]["salary_target"] == 250_000


def test_state_machine_rejects_skipping_human_review() -> None:
    package = CareerPackage(status=CareerPackageStatus.GENERATING)
    with pytest.raises(ValueError, match="Invalid career package transition"):
        transition(package, CareerPackageStatus.PROVIDED)


def test_reviewed_draft_can_be_marked_ready_to_publish() -> None:
    package = CareerPackage(status=CareerPackageStatus.DRAFT)

    transition(package, CareerPackageStatus.READY_TO_PUBLISH)

    assert package.status is CareerPackageStatus.READY_TO_PUBLISH


def test_pdf_contains_unicode_and_snapshot_identity() -> None:
    snapshot = {
        "package_number": "CP-1",
        "version_number": 1,
        "student_name": "Иван Иванов",
        "direction": "Python",
        "published_at": "2026-09-03T10:00:00+03:00",
        "provided_at": "2026-09-03T10:00:00+03:00",
        "resume": {
            "version_number": 1,
            "filename": "Резюме.pdf",
            "content_sha256": "a" * 64,
        },
        "self_presentation_card": presentation().model_dump(mode="json"),
        "active_search_parameters": search_parameters().model_dump(mode="json"),
    }
    result = render_package_pdf(snapshot, "b" * 64)
    assert result.startswith(b"%PDF")
    assert len(result) > 5_000


def test_fixed_obligation_is_unique_per_package() -> None:
    constraints = CareerPackageObligation.__table__.constraints
    assert any(
        constraint.__class__.__name__ == "UniqueConstraint"
        and [column.name for column in constraint.columns] == ["package_id"]
        for constraint in constraints
    )


@pytest.mark.asyncio
async def test_admin_records_obligation_then_starts_deadline_with_notice(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UploadStoreStub:
        async def upload_path(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        async def delete_for_processing(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

    monkeypatch.setattr(career_router, "store", UploadStoreStub())
    async with TestSession() as session:
        student = await session.get_one(User, seeded.student_id)
        student.email = "student@example.com"
        session.add(
            MentorStudentDocument(
                mentor_id=seeded.mentor_id,
                student_id=seeded.student_id,
                kind=MentorDocumentKind.RESUME,
                text_content="Python backend developer with production experience",
            )
        )
        await session.commit()

    created = await client.post(
        f"/api/v1/mentor/students/{seeded.student_id}/career-packages",
        json={"track_id": str(seeded.python_track_id)},
        headers=auth(seeded.mentor_id),
    )
    package = created.json()
    finalized = await client.post(
        f"/api/v1/career-packages/{package['id']}/final-resume",
        headers=auth(seeded.mentor_id),
    )
    package = finalized.json()
    saved = await client.put(
        f"/api/v1/career-packages/{package['id']}/draft",
        json={
            "lock_version": package["lock_version"],
            "source_data": source_data().model_dump(mode="json"),
            "self_presentation_card": presentation().model_dump(mode="json"),
            "active_search_parameters": search_parameters().model_dump(mode="json"),
        },
        headers=auth(seeded.mentor_id),
    )
    validated = await client.post(
        f"/api/v1/career-packages/{package['id']}/validate",
        headers=auth(seeded.mentor_id),
    )
    assert saved.status_code == 200, saved.text
    assert validated.status_code == 200, validated.text
    published = await client.post(
        f"/api/v1/career-packages/{package['id']}/publish",
        headers=auth(seeded.mentor_id),
    )
    assert published.status_code == 200, published.text
    published_body = published.json()
    assert published_body["obligation"] is None
    assert published_body["versions"][0]["payment_due_at"] is None
    assert published_body["versions"][0]["objection_deadline_at"] is None

    rejected_old_offer = await client.post(
        f"/api/v1/career-packages/{package['id']}/obligation",
        json={
            "offer_accepted_on": "2026-09-02",
            "record_comment": None,
            "eligibility_confirmed": True,
        },
        headers=auth(seeded.admin_id),
    )
    assert rejected_old_offer.status_code == 422

    mentor_forbidden = await client.post(
        f"/api/v1/career-packages/{package['id']}/obligation",
        json={
            "offer_accepted_on": "2026-09-03",
            "record_comment": None,
            "eligibility_confirmed": True,
        },
        headers=auth(seeded.mentor_id),
    )
    assert mentor_forbidden.status_code == 403

    recorded = await client.post(
        f"/api/v1/career-packages/{package['id']}/obligation",
        json={
            "offer_accepted_on": "2026-09-03",
            "record_comment": "Проверены акцепт оферты и состав пакета",
            "eligibility_confirmed": True,
        },
        headers=auth(seeded.admin_id),
    )
    assert recorded.status_code == 200, recorded.text
    recorded_body = recorded.json()
    assert recorded_body["obligation"]["status"] == "awaiting_notice"
    assert recorded_body["obligation"]["due_at"] is None
    assert recorded_body["obligation"]["notice_sent_at"] is None
    assert recorded_body["obligation"]["offer_accepted_on"] == "2026-09-03"

    student_before_notice = await client.get(
        "/api/v1/career-packages/me",
        headers=auth(seeded.student_id),
    )
    assert student_before_notice.status_code == 200
    assert student_before_notice.json()[0]["obligation"] is None

    repeated = await client.post(
        f"/api/v1/career-packages/{package['id']}/obligation",
        json={
            "offer_accepted_on": "2026-09-03",
            "record_comment": "Повторный клик",
            "eligibility_confirmed": True,
        },
        headers=auth(seeded.admin_id),
    )
    assert repeated.status_code == 200
    assert repeated.json()["obligation"]["id"] == recorded_body["obligation"]["id"]
    async with TestSession() as session:
        assert (
            await session.scalar(select(func.count(CareerPackageObligation.id)))
        ) == 1
        purposes = list(await session.scalars(select(CareerPackageDelivery.purpose)))
        assert CareerDeliveryPurpose.PAYMENT_OBLIGATION not in purposes

    notice = await client.post(
        f"/api/v1/career-packages/{package['id']}/obligation/notice",
        json={"delivery_confirmed": True},
        headers=auth(seeded.admin_id),
    )
    assert notice.status_code == 200, notice.text
    notice_body = notice.json()
    assert notice_body["obligation"]["status"] == "active"
    assert notice_body["obligation"]["due_at"] is not None
    assert notice_body["obligation"]["notice_sent_at"] is not None
    assert notice_body["versions"][0]["payment_due_at"] == notice_body["obligation"]["due_at"]
    assert notice_body["versions"][0]["objection_deadline_at"] is not None

    repeated_notice = await client.post(
        f"/api/v1/career-packages/{package['id']}/obligation/notice",
        json={"delivery_confirmed": True},
        headers=auth(seeded.admin_id),
    )
    assert repeated_notice.status_code == 200
    assert repeated_notice.json()["obligation"]["due_at"] == notice_body["obligation"]["due_at"]

    student_after_notice = await client.get(
        "/api/v1/career-packages/me",
        headers=auth(seeded.student_id),
    )
    assert student_after_notice.status_code == 200
    assert student_after_notice.json()[0]["obligation"]["status"] == "active"

    async with TestSession() as session:
        purposes = list(await session.scalars(select(CareerPackageDelivery.purpose)))
        assert purposes.count(CareerDeliveryPurpose.PAYMENT_OBLIGATION) >= 1


def test_ai_draft_can_be_reviewed_before_cross_field_salary_validation() -> None:
    raw_search = search_parameters().model_dump(mode="json")
    raw_search.update({"salary_min": 300_000, "salary_target": 250_000})
    output = CareerPackageAIOutput.model_validate(
        {
            "self_presentation_card": presentation().model_dump(mode="json"),
            "active_search_parameters": raw_search,
            "missing_data": [],
            "warnings": [],
            "source_summary": {"used_sources": ["resume", "questionnaire"]},
        }
    )
    assert output.active_search_parameters is not None
    with pytest.raises(ValueError, match="salary_target"):
        CareerDraftMutation(
            lock_version=1,
            active_search_parameters=output.active_search_parameters,
        )


def test_resume_pdf_text_can_be_extracted(tmp_path: Path) -> None:
    snapshot = {
        "package_number": "CP-EXTRACT",
        "version_number": 1,
        "student_name": "Иван Иванов",
        "direction": "Python",
        "published_at": "2026-09-03T10:00:00+03:00",
        "provided_at": "2026-09-03T10:00:00+03:00",
        "resume": {"version_number": 1, "filename": "resume.pdf", "content_sha256": "a" * 64},
        "self_presentation_card": presentation().model_dump(mode="json"),
        "active_search_parameters": search_parameters().model_dump(mode="json"),
    }
    path = tmp_path / "resume.pdf"
    path.write_bytes(render_package_pdf(snapshot, "b" * 64))

    assert "Иван Иванов" in _extract_path(path, "application/pdf")


@pytest.mark.asyncio
async def test_career_package_email_uses_brevo_and_attaches_pdf() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        assert request.headers["api-key"] == "secret"
        return httpx.Response(201, json={"messageId": "brevo-1"})

    settings = get_settings().model_copy(
        update={
            "brevo_api_key": SecretStr("secret"),
            "brevo_from_email": "platform@example.com",
        }
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.brevo.com/v3"
    ) as client:
        message_id = await CareerPackageEmailService(settings, client).send_package(
            recipient_email="student@example.com",
            recipient_name="Иван",
            package_number="CP-1",
            version_number=2,
            body="Пакет готов",
            action_url="https://platform.example.com/career-package",
            pdf=b"%PDF-test",
        )

    assert message_id == "brevo-1"
    assert captured["to"] == [{"email": "student@example.com", "name": "Иван"}]
    assert captured["attachment"]


@pytest.mark.asyncio
async def test_career_package_email_exposes_safe_brevo_status_and_code() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(401, json={"code": "unauthorized", "message": "sensitive"})

    settings = get_settings().model_copy(
        update={
            "brevo_api_key": SecretStr("invalid"),
            "brevo_from_email": "platform@example.com",
        }
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.brevo.com/v3"
    ) as client:
        with pytest.raises(
            CareerPackageEmailError,
            match=r"Brevo rejected email: HTTP 401 \(unauthorized\)",
        ):
            await CareerPackageEmailService(settings, client).send_package(
                recipient_email="student@example.com",
                recipient_name="Иван",
                package_number="CP-1",
                version_number=1,
                body="Пакет готов",
                action_url="https://platform.example.com/career-package",
                pdf=b"%PDF-test",
            )
