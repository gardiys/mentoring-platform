from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from arq import Retry
from sqlalchemy import exists, select

from app.career_packages.models import (
    CareerGenerationStatus,
    CareerPackage,
    CareerPackageDraft,
    CareerPackageEvent,
    CareerPackageGenerationRun,
    CareerPackageStatus,
    CareerPackageVersion,
    CareerResumeVersion,
)
from app.career_packages.resume_text import ResumeTextExtractionError, resume_text_for_ai
from app.career_packages.state_machine import transition
from app.db.session import async_session_factory
from app.interviews.intelligence_ai import InterviewAIError, InterviewAIProvider
from app.interviews.uploads import InterviewUploadStore

logger = logging.getLogger(__name__)
MAX_TRIES = 3


async def expire_career_objection_periods(ctx: dict[str, Any]) -> None:
    del ctx
    now = datetime.now(UTC)
    async with async_session_factory() as session:
        versions = list(
            await session.scalars(
                select(CareerPackageVersion)
                .where(
                    CareerPackageVersion.provided_at.is_not(None),
                    CareerPackageVersion.objection_deadline_at < now,
                    ~exists().where(
                        CareerPackageEvent.version_id == CareerPackageVersion.id,
                        CareerPackageEvent.event_type == "objection_period_expired",
                    ),
                )
                .limit(500)
            )
        )
        for version in versions:
            session.add(
                CareerPackageEvent(
                    package_id=version.package_id,
                    version_id=version.id,
                    event_type="objection_period_expired",
                    metadata_json={},
                )
            )
        await session.commit()


async def generate_career_package(ctx: dict[str, Any], run_id: str) -> None:
    normalized_run_id = UUID(run_id)
    async with async_session_factory() as session:
        run = await session.scalar(
            select(CareerPackageGenerationRun)
            .where(CareerPackageGenerationRun.id == normalized_run_id)
            .with_for_update()
        )
        if run is None or run.status in {
            CareerGenerationStatus.COMPLETED,
            CareerGenerationStatus.CANCELLED,
        }:
            return
        package = cast(CareerPackage, await session.get(CareerPackage, run.package_id))
        draft = cast(
            CareerPackageDraft,
            await session.scalar(
                select(CareerPackageDraft).where(CareerPackageDraft.package_id == package.id)
            ),
        )
        resume = cast(
            CareerResumeVersion,
            await session.get(CareerResumeVersion, package.source_resume_version_id),
        )
        run.status = CareerGenerationStatus.RUNNING
        run.started_at = run.started_at or datetime.now(UTC)
        session.add(
            CareerPackageEvent(
                package_id=package.id,
                event_type="generation_started",
                actor_user_id=run.requested_by_user_id,
                correlation_id=run.correlation_id,
                metadata_json={"run_id": str(run.id), "component": run.component.value},
            )
        )
        await session.commit()

    provider = cast(InterviewAIProvider, ctx["ai_provider"])
    try:
        resume_text = await resume_text_for_ai(
            resume,
            cast(InterviewUploadStore, ctx["upload_store"]),
        )
        result = await provider.generate_career_package(
            resume_text=resume_text,
            source_data=draft.source_data,
            component=run.component.value,
        )
    except ResumeTextExtractionError as error:
        ai_error = InterviewAIError(
            "CAREER_RESUME_TEXT_EXTRACTION_FAILED",
            str(error),
            retryable=False,
        )
        await _record_generation_failure(ctx, normalized_run_id, ai_error)
        return
    except InterviewAIError as error:
        await _record_generation_failure(ctx, normalized_run_id, error)
        return

    async with async_session_factory() as session:
        run = cast(
            CareerPackageGenerationRun,
            await session.scalar(
                select(CareerPackageGenerationRun)
                .where(CareerPackageGenerationRun.id == normalized_run_id)
                .with_for_update()
            ),
        )
        if run.status is CareerGenerationStatus.CANCELLED:
            return
        package = cast(CareerPackage, await session.get(CareerPackage, run.package_id))
        draft = cast(
            CareerPackageDraft,
            await session.scalar(
                select(CareerPackageDraft).where(CareerPackageDraft.package_id == package.id)
            ),
        )
        output = result.output
        if output.self_presentation_card is not None:
            draft.self_presentation_card = output.self_presentation_card.model_dump(mode="json")
        if output.active_search_parameters is not None:
            draft.active_search_parameters = output.active_search_parameters.model_dump(mode="json")
        draft.missing_data = [item.model_dump(mode="json") for item in output.missing_data]
        draft.warnings = [item.model_dump(mode="json") for item in output.warnings]
        draft.generation_run_id = run.id
        draft.is_stale = False
        run.status = CareerGenerationStatus.COMPLETED
        run.finished_at = datetime.now(UTC)
        run.model = result.usage.model
        run.prompt_version = result.prompt_version
        run.token_usage = {
            "provider_request_id": result.usage.provider_request_id,
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
        }
        if package.status is CareerPackageStatus.GENERATING:
            transition(package, CareerPackageStatus.REVIEW_REQUIRED)
        package.lock_version += 1
        session.add(
            CareerPackageEvent(
                package_id=package.id,
                event_type="generation_completed",
                actor_user_id=run.requested_by_user_id,
                correlation_id=run.correlation_id,
                metadata_json={
                    "run_id": str(run.id),
                    "component": run.component.value,
                    "missing_count": len(output.missing_data),
                    "warning_count": len(output.warnings),
                },
            )
        )
        await session.commit()


async def _record_generation_failure(
    ctx: dict[str, Any], run_id: UUID, error: InterviewAIError
) -> None:
    attempt = int(ctx.get("job_try", 1))
    async with async_session_factory() as session:
        run = cast(
            CareerPackageGenerationRun,
            await session.get(CareerPackageGenerationRun, run_id),
        )
        package = cast(CareerPackage, await session.get(CareerPackage, run.package_id))
        if error.retryable and attempt < MAX_TRIES:
            run.status = CareerGenerationStatus.QUEUED
            run.error_code = error.code
            run.safe_error_message = error.safe_message
            await session.commit()
            raise Retry(defer=30 * attempt) from error
        run.status = CareerGenerationStatus.FAILED
        run.error_code = error.code
        run.safe_error_message = error.safe_message
        run.finished_at = datetime.now(UTC)
        if package.status is CareerPackageStatus.GENERATING:
            transition(package, CareerPackageStatus.COLLECTING_DATA)
        session.add(
            CareerPackageEvent(
                package_id=package.id,
                event_type="generation_failed",
                actor_user_id=run.requested_by_user_id,
                correlation_id=run.correlation_id,
                metadata_json={"run_id": str(run.id), "code": error.code},
            )
        )
        await session.commit()
    logger.warning("Career package generation failed run_id=%s code=%s", run_id, error.code)
