from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from arq import Retry
from sqlalchemy import select

from app.db.session import async_session_factory
from app.employment_qualification.models import (
    EmploymentAISuggestion,
    EmploymentAISuggestionStatus,
    EmploymentContractPolicySnapshot,
    EmploymentEvent,
    EmploymentEvidence,
    EmploymentTechnologyUsage,
)
from app.interviews.intelligence_ai import InterviewAIError, InterviewAIProvider
from app.payments.models import StudentEmployment

logger = logging.getLogger(__name__)
MAX_TRIES = 3


async def generate_employment_ai_suggestion(ctx: dict[str, Any], suggestion_id: str) -> None:
    normalized_id = UUID(suggestion_id)
    async with async_session_factory() as session:
        suggestion = await session.scalar(
            select(EmploymentAISuggestion)
            .where(EmploymentAISuggestion.id == normalized_id)
            .with_for_update()
        )
        if suggestion is None or suggestion.status is EmploymentAISuggestionStatus.COMPLETED:
            return
        suggestion.status = EmploymentAISuggestionStatus.RUNNING
        suggestion.started_at = suggestion.started_at or datetime.now(UTC)
        suggestion.safe_error_message = None
        await session.commit()
        payload = await _safe_ai_payload(session, suggestion)

    provider = cast(InterviewAIProvider, ctx["ai_provider"])
    try:
        result = await provider.assess_employment_profile(payload)
    except InterviewAIError as error:
        attempt = int(ctx.get("job_try", 1))
        async with async_session_factory() as session:
            suggestion = cast(
                EmploymentAISuggestion,
                await session.get(EmploymentAISuggestion, normalized_id),
            )
            if error.retryable and attempt < MAX_TRIES:
                suggestion.status = EmploymentAISuggestionStatus.QUEUED
                suggestion.safe_error_message = error.safe_message
                await session.commit()
                raise Retry(defer=30 * attempt) from error
            suggestion.status = EmploymentAISuggestionStatus.FAILED
            suggestion.safe_error_message = error.safe_message
            suggestion.finished_at = datetime.now(UTC)
            await session.commit()
        logger.warning(
            "Employment qualification AI failed suggestion_id=%s code=%s",
            suggestion_id,
            error.code,
        )
        return

    async with async_session_factory() as session:
        suggestion = await session.scalar(
            select(EmploymentAISuggestion)
            .where(EmploymentAISuggestion.id == normalized_id)
            .with_for_update()
        )
        if suggestion is None or suggestion.status is EmploymentAISuggestionStatus.COMPLETED:
            return
        suggestion.status = EmploymentAISuggestionStatus.COMPLETED
        suggestion.output = result.output.model_dump(mode="json")
        suggestion.provider = provider.name
        suggestion.model = result.usage.model
        suggestion.prompt_version = result.prompt_version
        suggestion.finished_at = datetime.now(UTC)
        await session.commit()


async def _safe_ai_payload(session: Any, suggestion: EmploymentAISuggestion) -> dict[str, object]:
    case = cast(StudentEmployment, await session.get(StudentEmployment, suggestion.employment_id))
    policy = (
        await session.get(EmploymentContractPolicySnapshot, case.contract_policy_id)
        if case.contract_policy_id
        else None
    )
    requested_ids = {UUID(value) for value in suggestion.evidence_ids}
    evidence = list(
        await session.scalars(
            select(EmploymentEvidence).where(
                EmploymentEvidence.employment_id == case.id,
                EmploymentEvidence.id.in_(requested_ids),
            )
        )
    )
    events = list(
        await session.scalars(
            select(EmploymentEvent)
            .where(EmploymentEvent.employment_id == case.id)
            .order_by(EmploymentEvent.recorded_at.desc())
            .limit(20)
        )
    )
    usages = list(
        await session.scalars(
            select(EmploymentTechnologyUsage)
            .where(EmploymentTechnologyUsage.employment_id == case.id)
            .order_by(EmploymentTechnologyUsage.created_at.desc())
            .limit(50)
        )
    )
    # No student identity, salary, storage keys, URLs or complete documents are sent.
    evidence_payload = [
        {
            "evidence_id": str(item.id),
            "type": item.evidence_type.value,
            "text": (item.text_extract or "")[:12_000],
            "source_date": item.source_date.isoformat() if item.source_date else None,
        }
        for item in evidence
        if item.text_extract
    ]
    evidence_payload.extend(
        {
            "evidence_id": str(item.id),
            "type": f"reported_event:{item.event_type.value}",
            "text": item.payload,
            "source_date": item.effective_at.isoformat(),
        }
        for item in events
        if item.payload
    )
    allowed_ids = [str(item.id) for item in evidence if item.text_extract]
    allowed_ids.extend(str(item.id) for item in events if item.payload)
    return {
        "direction_language": policy.direction_language if policy else None,
        "official_job_title": case.official_job_title,
        "vacancy_stack": case.initial_vacancy_stack,
        "offer_stack": case.offer_stack,
        "actual_stack": case.actual_stack,
        "actual_duties": case.actual_duties,
        "project_description": case.project_description,
        "team_description": case.team_description,
        "employment_started_at": case.start_date.isoformat() if case.start_date else None,
        "technology_usages": [
            {
                "technology": item.normalized_name,
                "usage_type": item.usage_type.value,
                "frequency": item.frequency.value,
                "part_of_official_duties": item.part_of_official_duties.value,
                "part_of_project": item.part_of_project.value,
                "started_at": item.started_at.isoformat() if item.started_at else None,
                "description": item.description,
            }
            for item in usages
        ],
        "recent_event_types": [item.event_type.value for item in events],
        "evidence": evidence_payload,
        "allowed_evidence_ids": allowed_ids,
    }
