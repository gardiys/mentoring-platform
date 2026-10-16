"""Read the Go application facts captured during checkout, without changing legal evidence."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.legal.models import ContractAcceptance, LegalCheckout
from app.legal.schemas import AdminQuestionnaireRead, Questionnaire

GO_PRODUCT = "python_to_go_transition"


def _answers(snapshot: dict[str, Any]) -> dict[str, str | bool]:
    raw = snapshot.get("questionnaire_answers")
    if not isinstance(raw, dict):
        return {}
    return {
        key: value
        for key, value in raw.items()
        if key in Questionnaire.model_fields and isinstance(value, str | bool)
    }


async def admin_go_questionnaire(
    session: AsyncSession, student_id: UUID, *, application_id: UUID | None = None
) -> AdminQuestionnaireRead | None:
    contract_query = (
        select(ContractAcceptance, LegalCheckout.application_id)
        .join(LegalCheckout, LegalCheckout.id == ContractAcceptance.checkout_session_id)
        .where(
            ContractAcceptance.user_id == student_id,
            ContractAcceptance.product_code == GO_PRODUCT,
            LegalCheckout.user_id == student_id,
            LegalCheckout.product_code == GO_PRODUCT,
        )
        .order_by(ContractAcceptance.accepted_at.desc(), ContractAcceptance.id.desc())
        .limit(1)
    )
    if application_id is not None:
        contract_query = contract_query.where(LegalCheckout.application_id == application_id)
    record = (await session.execute(contract_query)).one_or_none()
    if record:
        contract, contract_application_id = record
        answers = _answers(contract.snapshot)
        if answers:
            return AdminQuestionnaireRead(
                application_id=contract_application_id,
                source="payment",
                recorded_at=contract.provider_paid_at or contract.accepted_at,
                answers=answers,
            )
    checkout_query = (
        select(LegalCheckout)
        .where(LegalCheckout.user_id == student_id, LegalCheckout.product_code == GO_PRODUCT)
        .order_by(LegalCheckout.created_at.desc(), LegalCheckout.id.desc())
        .limit(1)
    )
    if application_id is not None:
        checkout_query = checkout_query.where(LegalCheckout.application_id == application_id)
    checkout = await session.scalar(checkout_query)
    if checkout:
        answers = _answers(checkout.snapshot)
        if answers:
            return AdminQuestionnaireRead(
                application_id=checkout.application_id,
                source="checkout",
                recorded_at=checkout.created_at,
                answers=answers,
            )
    return None
