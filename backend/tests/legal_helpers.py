from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from httpx import AsyncClient, Response
from sqlalchemy import select

from app.legal.catalog import PRODUCTS, financial_terms, manifest
from app.legal.models import LegalEmailVerification, LegalOfferVersion
from app.users.models import User
from tests.conftest import TestSession, auth

ANSWERS = {
    "employment_status": "employed",
    "position": "Python developer",
    "work_format": "remote",
    "technologies": "Python, PostgreSQL",
    "existing_offers": False,
    "selection_processes": False,
    "previous_obligations": False,
    "go_in_current_work": False,
    "previous_contract": "Previous contract reference",
}


async def seed_legal_offers(user_id: UUID, *, verify_email: bool = True) -> None:
    async with TestSession() as session:
        for data in manifest():
            if await session.scalar(
                select(LegalOfferVersion.id).where(
                    LegalOfferVersion.product_code == data["product_code"]
                )
            ):
                continue
            values = dict(data)
            values["publication_date"] = date.fromisoformat(values["publication_date"])
            session.add(
                LegalOfferVersion(
                    id=uuid4(),
                    **values,
                    title=PRODUCTS[data["product_code"]]["title"],
                    effective_from=datetime(2026, 9, 3, tzinfo=UTC),
                    status="active",
                    financial_terms=financial_terms(),
                )
            )
        user = await session.get(User, user_id)
        if verify_email and user and user.email:
            session.add(
                LegalEmailVerification(
                    user_id=user_id,
                    email=user.email,
                    code_hash="0" * 64,
                    expires_at=datetime.now(UTC) + timedelta(minutes=15),
                    verified_at=datetime.now(UTC),
                )
            )
        await session.commit()


async def legal_checkout(
    client: AsyncClient, user_id: UUID, product: str, application_id: str
) -> Response:
    await seed_legal_offers(user_id)
    details = await client.get(f"/api/v1/legal/products/{product}/checkout", headers=auth(user_id))
    assert details.status_code == 200, details.text
    return await client.post(
        checkout_path(product, application_id),
        headers=auth(user_id),
        json={
            "expected_offer_version_id": details.json()["offer_version_id"],
            "questionnaire_schema_version": 1,
            "answers": ANSWERS,
            "confirmations": {"offer": True, "financial": True, "truthful": True},
            "page_identifier": "/test-checkout",
        },
    )


async def approved_application(client: AsyncClient, seeded, product: str) -> str:
    from tests.test_opportunities import _graduate_python, _seed_python_repeat_product

    await _graduate_python(seeded)
    await seed_legal_offers(seeded.student_id)
    if product == "python_to_go_transition":
        response = await client.post(
            "/api/v1/opportunities/go-transition",
            headers=auth(seeded.student_id),
            json={"motivation": "Хочу изучать Go и перейти в Go backend"},
        )
        assert response.status_code == 200, response.text
        application_id = response.json()["go_transition_applications"][0]["id"]
        response = await client.patch(
            f"/api/v1/admin/opportunities/go-transition/{application_id}",
            headers=auth(seeded.admin_id),
            json={"approved": True},
        )
    else:
        await _seed_python_repeat_product()
        response = await client.post(
            "/api/v1/opportunities/python-repeat/applications",
            headers=auth(seeded.student_id),
            json={
                "employment_status": "employed",
                "reason": "wants_higher_salary",
                "current_position": "Python developer",
                "current_company": "Example",
                "current_stack": "Python",
                "last_interview_at": None,
                "target_position": "Senior Python developer",
                "target_salary_kopecks": 25_000_000,
                "technical_gaps": "System design",
                "hours_per_week": 10,
                "desired_start_date": None,
                "search_mode": "search_while_employed",
                "additional_comment": None,
            },
        )
        assert response.status_code == 200, response.text
        application_id = response.json()["application"]["id"]
        await client.post(
            f"/api/v1/opportunities/python-repeat/applications/{application_id}/submit",
            headers=auth(seeded.student_id),
        )
        for status in ("under_review", "approved"):
            response = await client.post(
                f"/api/v1/admin/opportunities/python-repeat/applications/{application_id}/transition",
                headers=auth(seeded.admin_id),
                json={
                    "status": status,
                    "comment": "Одобрено",
                    "responsible_user_id": str(seeded.admin_id),
                },
            )
    assert response.status_code == 200, response.text
    return application_id


def checkout_path(product: str, application_id: str) -> str:
    if product == "python_to_go_transition":
        return f"/api/v1/opportunities/go-transition/{application_id}/payment-link"
    return f"/api/v1/opportunities/python-repeat/applications/{application_id}/checkout"
