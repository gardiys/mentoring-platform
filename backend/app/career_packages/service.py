from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.career_packages.models import (
    CareerDeliveryChannel,
    CareerDeliveryPurpose,
    CareerDeliveryStatus,
    CareerGenerationComponent,
    CareerGenerationStatus,
    CareerObjectionStatus,
    CareerObligationStatus,
    CareerPackage,
    CareerPackageDelivery,
    CareerPackageDraft,
    CareerPackageEvent,
    CareerPackageGenerationRun,
    CareerPackageObjection,
    CareerPackageObligation,
    CareerPackageStatus,
    CareerPackageVersion,
    CareerResumeVersion,
    CareerSelfPresentationReview,
)
from app.career_packages.rendering import render_package_html, render_package_pdf
from app.career_packages.resume_text import resume_file_can_be_extracted
from app.career_packages.schemas import (
    ActiveSearchParameters,
    CareerDeliveryRead,
    CareerDraftMutation,
    CareerEventRead,
    CareerGenerationRunRead,
    CareerMissingData,
    CareerObjectionCreate,
    CareerObjectionRead,
    CareerObjectionResolution,
    CareerObligationCreate,
    CareerObligationNoticeCreate,
    CareerObligationRead,
    CareerPackageRead,
    CareerReadinessRead,
    CareerResumeVersionRead,
    CareerReviewMutation,
    CareerReviewRead,
    CareerSourceData,
    CareerStudentPackageRead,
    CareerTrackOption,
    CareerVersionRead,
    CareerWarning,
    SelfPresentationCard,
)
from app.career_packages.state_machine import transition
from app.core.config import Settings
from app.core.errors import api_error
from app.interviews.uploads import InterviewStorageWriteError, InterviewUploadStore, StoredUpload
from app.mentors.models import MentorDocumentKind, MentorStudent, MentorStudentDocument
from app.notifications.models import NotificationKind
from app.notifications.service import (
    create_notification,
    queue_telegram_message,
    telegram_action_url,
)
from app.tracks.models import LearningTrack, LearningTrackEnrollment
from app.users.models import User, UserRole

PROMPT_VERSION = "career-package-v1"
NOTIFICATION_TEMPLATE_VERSION = "career-package-provided-v2-no-payment"
OBLIGATION_NOTIFICATION_TEMPLATE_VERSION = "career-package-payment-obligation-v1"
FIXED_FEE_KOPECKS = 3_000_000
CAREER_OFFER_EFFECTIVE_ON = date(2026, 9, 3)


def _settings_guard(settings: Settings) -> None:
    if not settings.career_package_enabled:
        api_error(404, "career_package_disabled", "Career packages are not enabled")


async def _staff_student(
    session: AsyncSession, actor: User, student_id: UUID, *, lock: bool = False
) -> User:
    statement = select(User).where(User.id == student_id, User.role == UserRole.STUDENT)
    if lock:
        statement = statement.with_for_update()
    student = await session.scalar(statement)
    if student is None:
        api_error(404, "student_not_found", "Student was not found")
    if actor.role is UserRole.ADMIN:
        return student
    if actor.role is not UserRole.MENTOR:
        api_error(403, "career_package_staff_required", "Staff access is required")
    assigned = await session.scalar(
        select(MentorStudent.student_id).where(
            MentorStudent.student_id == student_id,
            MentorStudent.mentor_id == actor.id,
        )
    )
    if assigned is None:
        api_error(403, "student_not_assigned_to_mentor", "Student is not assigned to this mentor")
    return student


async def _package(session: AsyncSession, package_id: UUID, *, lock: bool = False) -> CareerPackage:
    statement = select(CareerPackage).where(CareerPackage.id == package_id)
    if lock:
        statement = statement.with_for_update()
    package = await session.scalar(statement)
    if package is None:
        api_error(404, "career_package_not_found", "Career package was not found")
    return package


async def staff_package(
    session: AsyncSession, actor: User, package_id: UUID, *, lock: bool = False
) -> CareerPackage:
    package = await _package(session, package_id, lock=lock)
    await _staff_student(session, actor, package.student_id)
    return package


def _event(
    session: AsyncSession,
    package: CareerPackage,
    event_type: str,
    actor: User | None,
    *,
    version_id: UUID | None = None,
    correlation_id: str | None = None,
    metadata: dict[str, object] | None = None,
) -> None:
    session.add(
        CareerPackageEvent(
            package_id=package.id,
            version_id=version_id,
            event_type=event_type,
            actor_user_id=actor.id if actor else None,
            actor_role=actor.role.value if actor else None,
            correlation_id=correlation_id,
            metadata_json=metadata or {},
        )
    )


def _resume_hash(document: MentorStudentDocument) -> str:
    material = json.dumps(
        {
            "text": document.text_content,
            "storage_key": document.storage_key,
            "filename": document.filename,
            "content_type": document.content_type,
            "size": document.size,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode()).hexdigest()


async def create_package(
    session: AsyncSession,
    settings: Settings,
    actor: User,
    student_id: UUID,
    track_id: UUID,
) -> CareerPackageRead:
    _settings_guard(settings)
    await _staff_student(session, actor, student_id)
    enrolled = await session.scalar(
        select(LearningTrackEnrollment.user_id).where(
            LearningTrackEnrollment.user_id == student_id,
            LearningTrackEnrollment.track_id == track_id,
        )
    )
    track = await session.get(LearningTrack, track_id)
    if track is None or enrolled is None:
        api_error(422, "career_package_track_unavailable", "Student is not enrolled in this track")
    existing = await session.scalar(
        select(CareerPackage).where(
            CareerPackage.student_id == student_id, CareerPackage.track_id == track_id
        )
    )
    if existing is not None:
        return await package_read(session, existing, include_audit=True)
    package = CareerPackage(
        student_id=student_id,
        track_id=track_id,
        status=CareerPackageStatus.COLLECTING_DATA,
        created_by_user_id=actor.id,
    )
    session.add(package)
    await session.flush()
    session.add(
        CareerPackageDraft(package_id=package.id, source_data={}, missing_data=[], warnings=[])
    )
    _event(session, package, "package_created", actor, metadata={"track_id": str(track_id)})
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        package = cast(
            CareerPackage,
            await session.scalar(
                select(CareerPackage).where(
                    CareerPackage.student_id == student_id,
                    CareerPackage.track_id == track_id,
                )
            ),
        )
    return await package_read(session, package, include_audit=True)


async def get_staff_package_for_student(
    session: AsyncSession, settings: Settings, actor: User, student_id: UUID
) -> list[CareerPackageRead]:
    _settings_guard(settings)
    await _staff_student(session, actor, student_id)
    packages = list(
        await session.scalars(
            select(CareerPackage)
            .where(CareerPackage.student_id == student_id)
            .order_by(CareerPackage.created_at.desc())
        )
    )
    return [await package_read(session, package, include_audit=True) for package in packages]


async def get_staff_track_options(
    session: AsyncSession, settings: Settings, actor: User, student_id: UUID
) -> list[CareerTrackOption]:
    _settings_guard(settings)
    await _staff_student(session, actor, student_id)
    tracks = list(
        await session.scalars(
            select(LearningTrack)
            .join(LearningTrackEnrollment, LearningTrackEnrollment.track_id == LearningTrack.id)
            .where(LearningTrackEnrollment.user_id == student_id)
            .order_by(LearningTrack.position, LearningTrack.title)
        )
    )
    return [CareerTrackOption(id=item.id, slug=item.slug, title=item.title) for item in tracks]


async def finalize_resume(
    session: AsyncSession,
    settings: Settings,
    actor: User,
    package_id: UUID,
) -> CareerPackageRead:
    _settings_guard(settings)
    package = await staff_package(session, actor, package_id, lock=True)
    document = await session.scalar(
        select(MentorStudentDocument).where(
            MentorStudentDocument.student_id == package.student_id,
            MentorStudentDocument.kind == MentorDocumentKind.RESUME,
        )
    )
    if document is None:
        api_error(422, "career_resume_missing", "Create the student's resume first")
    checksum = _resume_hash(document)
    existing = await session.scalar(
        select(CareerResumeVersion).where(
            CareerResumeVersion.student_id == package.student_id,
            CareerResumeVersion.content_sha256 == checksum,
        )
    )
    if existing is None:
        number = (
            int(
                await session.scalar(
                    select(func.count(CareerResumeVersion.id)).where(
                        CareerResumeVersion.student_id == package.student_id
                    )
                )
                or 0
            )
            + 1
        )
        existing = CareerResumeVersion(
            student_id=package.student_id,
            source_document_id=document.id,
            version_number=number,
            text_content=document.text_content,
            storage_key=document.storage_key,
            filename=document.filename,
            content_type=document.content_type,
            size=document.size,
            content_sha256=checksum,
            finalized_by_user_id=actor.id,
        )
        session.add(existing)
        await session.flush()
    draft = await _draft(session, package.id)
    if package.source_resume_version_id != existing.id:
        draft.is_stale = bool(draft.self_presentation_card or draft.active_search_parameters)
    package.source_resume_version_id = existing.id
    draft.source_resume_version_id = existing.id
    package.lock_version += 1
    _event(
        session,
        package,
        "final_resume_selected",
        actor,
        metadata={"resume_version_id": str(existing.id), "checksum": checksum},
    )
    await session.commit()
    if (
        settings.career_package_auto_generate_on_final_resume
        and settings.career_package_ai_enabled
        and draft.source_data
    ):
        await request_generation(
            session,
            settings,
            actor,
            package.id,
            CareerGenerationComponent.ALL,
            f"auto-final-resume-{uuid4()}",
        )
        package = await _package(session, package.id)
    return await package_read(session, package, include_audit=True)


async def _draft(session: AsyncSession, package_id: UUID) -> CareerPackageDraft:
    draft = await session.scalar(
        select(CareerPackageDraft).where(CareerPackageDraft.package_id == package_id)
    )
    if draft is None:
        api_error(409, "career_package_draft_missing", "Career package draft is unavailable")
    return draft


def readiness(package: CareerPackage, draft: CareerPackageDraft) -> CareerReadinessRead:
    missing: list[str] = []
    if package.source_resume_version_id is None:
        missing.append("Финальная версия резюме")
    try:
        CareerSourceData.model_validate(draft.source_data)
    except ValueError:
        missing.append("Исходные параметры поиска")
    if draft.self_presentation_card is None:
        missing.append("Карта подготовки к самопрезентации")
    else:
        try:
            SelfPresentationCard.model_validate(draft.self_presentation_card)
        except ValueError:
            missing.append("Корректная карта подготовки к самопрезентации")
    if draft.active_search_parameters is None:
        missing.append("Параметры активного поиска")
    else:
        try:
            search = ActiveSearchParameters.model_validate(draft.active_search_parameters)
            if search.salary_target < search.salary_min:
                raise ValueError("salary_target must not be lower than salary_min")
        except ValueError:
            missing.append("Корректные параметры активного поиска")
    blocking = [
        CareerMissingData.model_validate(item)
        for item in draft.missing_data
        if bool(item.get("blocking", True))
    ]
    return CareerReadinessRead(
        complete=not missing and not blocking, missing=missing, blocking_missing_data=blocking
    )


async def update_draft(
    session: AsyncSession,
    settings: Settings,
    actor: User,
    package_id: UUID,
    payload: CareerDraftMutation,
) -> CareerPackageRead:
    _settings_guard(settings)
    package = await staff_package(session, actor, package_id, lock=True)
    if package.status in {
        CareerPackageStatus.GENERATING,
        CareerPackageStatus.DELIVERY_PENDING,
        CareerPackageStatus.CANCELLED,
    }:
        api_error(409, "career_package_not_editable", "Career package cannot be edited now")
    if package.lock_version != payload.lock_version:
        api_error(409, "career_package_changed", "Career package was changed; reload the page")
    draft = await _draft(session, package.id)
    if payload.source_data is not None:
        draft.source_data = payload.source_data.model_dump(mode="json")
        _event(session, package, "source_data_updated", actor)
    if payload.self_presentation_card is not None:
        draft.self_presentation_card = payload.self_presentation_card.model_dump(mode="json")
    if payload.active_search_parameters is not None:
        draft.active_search_parameters = payload.active_search_parameters.model_dump(mode="json")
    if payload.missing_data is not None:
        draft.missing_data = [item.model_dump(mode="json") for item in payload.missing_data]
    if payload.warnings is not None:
        draft.warnings = [item.model_dump(mode="json") for item in payload.warnings]
    draft.last_edited_by_user_id = actor.id
    draft.is_stale = False
    package.lock_version += 1
    if package.status in {CareerPackageStatus.NOT_STARTED, CareerPackageStatus.COLLECTING_DATA}:
        transition(package, CareerPackageStatus.DRAFT)
    elif package.status in {
        CareerPackageStatus.REVIEW_REQUIRED,
        CareerPackageStatus.READY_TO_PUBLISH,
        CareerPackageStatus.PROVIDED,
    }:
        transition(package, CareerPackageStatus.DRAFT)
    _event(session, package, "draft_updated", actor)
    await session.commit()
    return await package_read(session, package, include_audit=True)


async def validate_completeness(
    session: AsyncSession, settings: Settings, actor: User, package_id: UUID
) -> CareerPackageRead:
    _settings_guard(settings)
    package = await staff_package(session, actor, package_id, lock=True)
    draft = await _draft(session, package.id)
    result = readiness(package, draft)
    if result.complete:
        if package.status not in {
            CareerPackageStatus.READY_TO_PUBLISH,
            CareerPackageStatus.PROVIDED,
        }:
            transition(package, CareerPackageStatus.READY_TO_PUBLISH)
    elif package.status is CareerPackageStatus.READY_TO_PUBLISH:
        transition(package, CareerPackageStatus.DRAFT)
    package.lock_version += 1
    _event(
        session,
        package,
        "completeness_validated",
        actor,
        metadata={"complete": result.complete, "missing_count": len(result.missing)},
    )
    await session.commit()
    return await package_read(session, package, include_audit=True)


def _stable_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


async def request_generation(
    session: AsyncSession,
    settings: Settings,
    actor: User,
    package_id: UUID,
    component: CareerGenerationComponent,
    correlation_id: str,
) -> CareerPackageGenerationRun:
    _settings_guard(settings)
    if not settings.career_package_ai_enabled:
        api_error(503, "career_package_ai_disabled", "Career package AI generation is disabled")
    package = await staff_package(session, actor, package_id, lock=True)
    draft = await _draft(session, package.id)
    if package.source_resume_version_id is None:
        api_error(422, "career_resume_missing", "Select a final resume version first")
    try:
        CareerSourceData.model_validate(draft.source_data)
    except ValueError:
        api_error(422, "career_source_data_incomplete", "Complete the source questionnaire first")
    active = await session.scalar(
        select(CareerPackageGenerationRun.id).where(
            CareerPackageGenerationRun.package_id == package.id,
            CareerPackageGenerationRun.status.in_(
                [CareerGenerationStatus.QUEUED, CareerGenerationStatus.RUNNING]
            ),
        )
    )
    if active is not None:
        api_error(
            409, "career_generation_in_progress", "Career package generation is already running"
        )
    resume = (
        await session.get(CareerResumeVersion, package.source_resume_version_id)
        if package.source_resume_version_id is not None
        else None
    )
    assert resume is not None
    if not (resume.text_content or "").strip() and not resume_file_can_be_extracted(resume):
        api_error(
            422,
            "career_resume_text_missing",
            "Upload a searchable PDF, DOCX or text resume before AI generation",
        )
    input_hash = hashlib.sha256(
        _stable_json(
            {
                "resume_checksum": resume.content_sha256,
                "source_data": draft.source_data,
                "component": component.value,
            }
        )
    ).hexdigest()
    key = hashlib.sha256(
        f"{package.id}:{resume.id}:{input_hash}:{PROMPT_VERSION}:{component.value}".encode()
    ).hexdigest()
    existing = await session.scalar(
        select(CareerPackageGenerationRun).where(CareerPackageGenerationRun.idempotency_key == key)
    )
    if existing is not None and existing.status not in {
        CareerGenerationStatus.FAILED,
        CareerGenerationStatus.CANCELLED,
    }:
        return existing
    model = (
        settings.openai_light_review_model or settings.openai_extraction_model or "fake-career-v1"
    )
    if existing is None:
        run = CareerPackageGenerationRun(
            package_id=package.id,
            status=CareerGenerationStatus.QUEUED,
            component=component,
            provider=settings.interview_ai_provider,
            model=model,
            prompt_version=PROMPT_VERSION,
            input_hash=input_hash,
            idempotency_key=key,
            requested_by_user_id=actor.id,
            correlation_id=correlation_id,
        )
        session.add(run)
    else:
        if package.status is CareerPackageStatus.CANCELLED:
            transition(package, CareerPackageStatus.COLLECTING_DATA)
        if package.status is CareerPackageStatus.PROVIDED:
            api_error(
                409,
                "career_package_already_provided",
                "Create a revision before generating the package again",
            )
        run = existing
        run.status = CareerGenerationStatus.QUEUED
        run.requested_by_user_id = actor.id
        run.correlation_id = correlation_id
        run.started_at = None
        run.finished_at = None
        run.error_code = None
        run.safe_error_message = None
        run.token_usage = None
    await session.flush()
    draft.generation_run_id = run.id
    transition(package, CareerPackageStatus.GENERATING)
    package.lock_version += 1
    _event(
        session,
        package,
        "generation_requested",
        actor,
        correlation_id=correlation_id,
        metadata={"component": component.value, "retried": existing is not None},
    )
    await session.commit()
    from app.career_packages.queue import enqueue_career_generation

    try:
        await enqueue_career_generation(run.id)
    except Exception:
        run = cast(
            CareerPackageGenerationRun, await session.get(CareerPackageGenerationRun, run.id)
        )
        run.status = CareerGenerationStatus.FAILED
        run.error_code = "QUEUE_UNAVAILABLE"
        run.safe_error_message = "Не удалось поставить генерацию в очередь"
        run.finished_at = datetime.now(UTC)
        package = await _package(session, package.id, lock=True)
        transition(package, CareerPackageStatus.COLLECTING_DATA)
        _event(
            session,
            package,
            "generation_failed",
            actor,
            correlation_id=correlation_id,
            metadata={"code": "QUEUE_UNAVAILABLE"},
        )
        await session.commit()
        api_error(503, "career_generation_queue_unavailable", "Generation queue is unavailable")
    return run


def _notification_text(package_number: str, version: CareerPackageVersion) -> str:
    assert version.provided_at
    return (
        f"Карьерный пакет № {package_number}, версия {version.version_number}, готов и доступен "
        "в личном кабинете.\n\n"
        "В состав входят: финальная версия резюме, карта подготовки к самопрезентации и "
        "параметры активного поиска работы.\n\n"
        f"Дата предоставления: {version.provided_at:%d.%m.%Y}. Сейчас оплачивать Карьерный "
        "пакет не нужно. Юридически значимое уведомление со сроками оплаты и направления "
        "возражений будет направлено отдельно."
    )


def _obligation_notification_text(
    package_number: str,
    version: CareerPackageVersion,
    obligation: CareerPackageObligation,
) -> str:
    assert version.provided_at and version.objection_deadline_at and obligation.due_at
    return (
        f"В соответствии с условиями Публичной оферты Вам предоставлен полный "
        f"Карьерный пакет № {package_number}, версия {version.version_number}.\n\n"
        "В состав входят: финальная версия резюме, карта подготовки к самопрезентации и "
        "параметры активного поиска работы.\n\n"
        f"Дата предоставления: {version.provided_at:%d.%m.%Y}. "
        f"Мотивированные возражения можно направить до "
        f"{version.objection_deadline_at:%d.%m.%Y}.\n\n"
        f"Фиксированный компонент стоимости составляет 30 000 ₽. "
        f"Срок оплаты: до {obligation.due_at:%d.%m.%Y}."
    )


async def publish_and_provide(
    session: AsyncSession,
    settings: Settings,
    store: InterviewUploadStore,
    actor: User,
    package_id: UUID,
) -> CareerPackageRead:
    _settings_guard(settings)
    package = await staff_package(session, actor, package_id, lock=True)
    if package.latest_published_version_id is not None:
        latest = await session.get(CareerPackageVersion, package.latest_published_version_id)
        if (
            latest is not None
            and latest.provided_at is not None
            and package.status is CareerPackageStatus.PROVIDED
        ):
            return await package_read(session, package, include_audit=True)
    draft = await _draft(session, package.id)
    result = readiness(package, draft)
    if not result.complete:
        api_error(422, "career_package_incomplete", "Career package is not ready to publish")
    if package.status is not CareerPackageStatus.READY_TO_PUBLISH:
        api_error(409, "career_package_not_approved", "Validate completeness before publishing")
    resume = await session.get(CareerResumeVersion, package.source_resume_version_id)
    student = await session.get(User, package.student_id)
    track = await session.get(LearningTrack, package.track_id)
    assert resume is not None and student is not None and track is not None
    version_number = (
        int(
            await session.scalar(
                select(func.count(CareerPackageVersion.id)).where(
                    CareerPackageVersion.package_id == package.id
                )
            )
            or 0
        )
        + 1
    )
    now = datetime.now(UTC)
    snapshot: dict[str, Any] = {
        "schema_version": 1,
        "package_number": str(package.id),
        "version_number": version_number,
        "student_name": " ".join(filter(None, [student.first_name, student.last_name])),
        "direction": track.title,
        "published_at": now.isoformat(),
        "provided_at": now.isoformat(),
        "resume": {
            "id": str(resume.id),
            "version_number": resume.version_number,
            "filename": resume.filename,
            "content_sha256": resume.content_sha256,
            "text_content": resume.text_content,
        },
        "self_presentation_card": draft.self_presentation_card,
        "active_search_parameters": draft.active_search_parameters,
        "notification_template_version": NOTIFICATION_TEMPLATE_VERSION,
    }
    snapshot_hash = hashlib.sha256(_stable_json(snapshot)).hexdigest()
    rendered_html = render_package_html(snapshot)
    try:
        pdf = render_package_pdf(snapshot, snapshot_hash)
    except Exception as error:
        _event(
            session,
            package,
            "delivery_failed",
            actor,
            metadata={"stage": "pdf", "error": type(error).__name__},
        )
        await session.commit()
        api_error(503, "career_package_pdf_failed", "Could not create the career package PDF")
    pdf_hash = hashlib.sha256(pdf).hexdigest()
    object_key = (
        f"career-packages/{package.student_id}/{package.id}/v{version_number}-{pdf_hash[:16]}.pdf"
    )
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="career-package-", suffix=".pdf", delete=False
        ) as output:
            output.write(pdf)
            temp_path = Path(output.name)
        await store.upload_path(
            temp_path,
            storage_key=object_key,
            content_type="application/pdf",
            expected_size=len(pdf),
        )
    except (OSError, InterviewStorageWriteError):
        _event(session, package, "delivery_failed", actor, metadata={"stage": "s3"})
        await session.commit()
        api_error(503, "career_package_pdf_storage_failed", "Could not save the career package PDF")
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    previous_version_id = package.latest_published_version_id
    version = CareerPackageVersion(
        package_id=package.id,
        version_number=version_number,
        source_resume_version_id=resume.id,
        snapshot=snapshot,
        rendered_html=rendered_html,
        pdf_object_key=object_key,
        pdf_size=len(pdf),
        pdf_sha256=pdf_hash,
        snapshot_sha256=snapshot_hash,
        prompt_version=PROMPT_VERSION if draft.generation_run_id else None,
        generated_by_ai=draft.generation_run_id is not None,
        generation_run_id=draft.generation_run_id,
        created_by_user_id=actor.id,
        approved_by_user_id=actor.id,
        published_at=now,
        provided_at=now,
        objection_deadline_at=None,
        payment_due_at=None,
        supersedes_version_id=previous_version_id,
    )
    session.add(version)
    await session.flush()
    package.latest_published_version_id = version.id
    transition(package, CareerPackageStatus.DELIVERY_PENDING)
    _event(
        session,
        package,
        "version_published",
        actor,
        version_id=version.id,
        metadata={"version": version_number, "snapshot_sha256": snapshot_hash},
    )
    path = f"/career-package?version={version.id}"
    body = _notification_text(str(package.id), version)
    await create_notification(
        session,
        user_id=student.id,
        actor_user_id=actor.id,
        event_key=f"career-package-provided:{version.id}",
        kind=NotificationKind.CAREER_PACKAGE,
        title="Карьерный пакет готов",
        body=body,
        action_url=path,
    )
    session.add(
        CareerPackageDelivery(
            package_version_id=version.id,
            channel=CareerDeliveryChannel.PLATFORM,
            status=CareerDeliveryStatus.DELIVERED,
            purpose=CareerDeliveryPurpose.PACKAGE_PROVIDED,
            recipient=str(student.id),
            attempted_at=now,
            delivered_at=now,
            idempotency_key=f"{version.id}:platform:{student.id}",
        )
    )
    _event(
        session,
        package,
        "delivery_attempted",
        actor,
        version_id=version.id,
        metadata={"channel": "platform"},
    )
    if student.telegram_id and settings.telegram_bot_token:
        public_url = telegram_action_url(path)
        await queue_telegram_message(
            session,
            event_key=f"career-package-provided:{version.id}:telegram",
            chat_id=student.telegram_id,
            text=body,
            action_label="Открыть Карьерный пакет" if public_url else None,
            action_url=public_url,
        )
        session.add(
            CareerPackageDelivery(
                package_version_id=version.id,
                channel=CareerDeliveryChannel.TELEGRAM,
                status=CareerDeliveryStatus.PENDING,
                purpose=CareerDeliveryPurpose.PACKAGE_PROVIDED,
                recipient=str(student.telegram_id),
                attempted_at=now,
                idempotency_key=f"{version.id}:telegram:{student.telegram_id}",
            )
        )
    if student.email:
        session.add(
            CareerPackageDelivery(
                package_version_id=version.id,
                channel=CareerDeliveryChannel.EMAIL,
                status=CareerDeliveryStatus.PENDING,
                purpose=CareerDeliveryPurpose.PACKAGE_PROVIDED,
                recipient=student.email,
                attempted_at=now,
                idempotency_key=f"{version.id}:email:{student.email.casefold()}",
            )
        )
    if previous_version_id is not None:
        obligation = await session.scalar(
            select(CareerPackageObligation).where(
                CareerPackageObligation.package_id == package.id
            )
        )
        if obligation is not None and obligation.status in {
            CareerObligationStatus.AWAITING_NOTICE,
            CareerObligationStatus.HOLD,
        }:
            obligation.source_version_id = version.id
            obligation.status = CareerObligationStatus.AWAITING_NOTICE
            obligation.notice_sent_at = None
            obligation.due_at = None
            obligation.disputed_at = None
    transition(package, CareerPackageStatus.PROVIDED)
    package.lock_version += 1
    _event(
        session,
        package,
        "package_provided" if previous_version_id is None else "revision_provided",
        actor,
        version_id=version.id,
        metadata={"notification_template_version": NOTIFICATION_TEMPLATE_VERSION},
    )
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        await store.delete_for_processing(object_key, suppress_errors=True)
        raise
    return await package_read(session, package, include_audit=True)


async def record_payment_obligation(
    session: AsyncSession,
    settings: Settings,
    actor: User,
    package_id: UUID,
    payload: CareerObligationCreate,
) -> CareerPackageRead:
    """Record an accrued fee without starting its payment period or notifying the student."""

    _settings_guard(settings)
    if actor.role is not UserRole.ADMIN:
        api_error(403, "career_package_admin_required", "Действие доступно только администратору")
    package = await _package(session, package_id, lock=True)
    if package.latest_published_version_id is None:
        api_error(409, "career_package_not_provided", "Сначала предоставьте Карьерный пакет")
    if package.status is not CareerPackageStatus.PROVIDED:
        api_error(
            409,
            "career_package_not_settled",
            "Перед созданием обязательства разрешите возражения по пакету",
        )
    version = await session.get(CareerPackageVersion, package.latest_published_version_id)
    student = await session.get(User, package.student_id)
    assert version is not None and student is not None
    if version.provided_at is None:
        api_error(409, "career_package_not_provided", "Сначала предоставьте Карьерный пакет")
    if payload.offer_accepted_on < CAREER_OFFER_EFFECTIVE_ON:
        api_error(
            422,
            "career_offer_not_applicable",
            "Ученик должен принять редакцию оферты от 03.09.2026 или более позднюю",
        )
    now = datetime.now(UTC)
    if payload.offer_accepted_on > version.provided_at.date():
        api_error(
            422,
            "career_offer_accepted_after_package",
            "Дата акцепта оферты не может быть позднее предоставления пакета",
        )

    obligation = await session.scalar(
        select(CareerPackageObligation)
        .where(CareerPackageObligation.package_id == package.id)
        .with_for_update()
    )
    if obligation is not None and obligation.status is not CareerObligationStatus.CANCELLED:
        return await package_read(session, package, include_audit=True)

    if obligation is None:
        obligation = CareerPackageObligation(
            package_id=package.id,
            source_version_id=version.id,
            student_id=student.id,
            amount_kopecks=FIXED_FEE_KOPECKS,
            currency="RUB",
            due_at=None,
            status=CareerObligationStatus.AWAITING_NOTICE,
            description="Фиксированный компонент стоимости Карьерного пакета",
            idempotency_key=f"career-package-fixed:{package.id}",
        )
        session.add(obligation)
    else:
        obligation.source_version_id = version.id
        obligation.due_at = None
        obligation.status = CareerObligationStatus.AWAITING_NOTICE
        obligation.disputed_at = None
    obligation.offer_accepted_on = payload.offer_accepted_on
    obligation.accrued_at = version.provided_at
    obligation.recorded_at = now
    obligation.recorded_by_user_id = actor.id
    obligation.record_comment = payload.record_comment or None
    obligation.notice_sent_at = None
    await session.flush()
    _event(
        session,
        package,
        "fixed_fee_obligation_recorded",
        actor,
        version_id=version.id,
        metadata={
            "amount_kopecks": FIXED_FEE_KOPECKS,
            "offer_accepted_on": payload.offer_accepted_on.isoformat(),
            "accrued_at": version.provided_at.isoformat(),
        },
    )
    await session.commit()
    return await package_read(session, package, include_audit=True)


async def send_payment_obligation_notice(
    session: AsyncSession,
    settings: Settings,
    actor: User,
    package_id: UUID,
    payload: CareerObligationNoticeCreate,
) -> CareerPackageRead:
    """Deliver the legal notice and start the ten-day payment period."""

    del payload
    _settings_guard(settings)
    if actor.role is not UserRole.ADMIN:
        api_error(403, "career_package_admin_required", "Действие доступно только администратору")
    package = await _package(session, package_id, lock=True)
    if package.status is not CareerPackageStatus.PROVIDED:
        api_error(
            409,
            "career_package_not_settled",
            "Перед отправкой уведомления разрешите возражения по пакету",
        )
    obligation = await session.scalar(
        select(CareerPackageObligation)
        .where(CareerPackageObligation.package_id == package.id)
        .with_for_update()
    )
    if obligation is None or obligation.status is CareerObligationStatus.CANCELLED:
        api_error(409, "career_obligation_missing", "Сначала зафиксируйте обязательство")
    if obligation.status is not CareerObligationStatus.AWAITING_NOTICE:
        return await package_read(session, package, include_audit=True)
    version = await session.get(CareerPackageVersion, obligation.source_version_id)
    student = await session.get(User, package.student_id)
    assert version is not None and student is not None
    now = datetime.now(UTC)
    obligation.notice_sent_at = now
    obligation.due_at = now + timedelta(days=10)
    obligation.status = CareerObligationStatus.ACTIVE
    version.objection_deadline_at = now + timedelta(days=7)
    version.payment_due_at = obligation.due_at
    await session.flush()

    path = f"/career-package?version={version.id}"
    body = _obligation_notification_text(str(package.id), version, obligation)
    await create_notification(
        session,
        user_id=student.id,
        actor_user_id=actor.id,
        event_key=f"career-package-payment-obligation:{obligation.id}",
        kind=NotificationKind.CAREER_PACKAGE,
        title="Уведомление о предоставлении и оплате Карьерного пакета",
        body=body,
        action_url=path,
    )
    session.add(
        CareerPackageDelivery(
            package_version_id=version.id,
            channel=CareerDeliveryChannel.PLATFORM,
            status=CareerDeliveryStatus.DELIVERED,
            purpose=CareerDeliveryPurpose.PAYMENT_OBLIGATION,
            recipient=str(student.id),
            attempted_at=now,
            delivered_at=now,
            idempotency_key=f"{version.id}:obligation-platform:{obligation.id}",
        )
    )
    if student.telegram_id and settings.telegram_bot_token:
        public_url = telegram_action_url(path)
        await queue_telegram_message(
            session,
            event_key=f"career-package-payment-obligation:{obligation.id}:telegram",
            chat_id=student.telegram_id,
            text=body,
            action_label="Открыть Карьерный пакет" if public_url else None,
            action_url=public_url,
        )
        session.add(
            CareerPackageDelivery(
                package_version_id=version.id,
                channel=CareerDeliveryChannel.TELEGRAM,
                status=CareerDeliveryStatus.PENDING,
                purpose=CareerDeliveryPurpose.PAYMENT_OBLIGATION,
                recipient=str(student.telegram_id),
                attempted_at=now,
                idempotency_key=f"{version.id}:obligation-telegram:{obligation.id}",
            )
        )
    if student.email:
        session.add(
            CareerPackageDelivery(
                package_version_id=version.id,
                channel=CareerDeliveryChannel.EMAIL,
                status=CareerDeliveryStatus.PENDING,
                purpose=CareerDeliveryPurpose.PAYMENT_OBLIGATION,
                recipient=student.email,
                attempted_at=now,
                idempotency_key=f"{version.id}:obligation-email:{obligation.id}",
            )
        )
    _event(
        session,
        package,
        "fixed_fee_notice_delivered",
        actor,
        version_id=version.id,
        metadata={
            "amount_kopecks": FIXED_FEE_KOPECKS,
            "notice_sent_at": now.isoformat(),
            "due_at": obligation.due_at.isoformat(),
            "objection_deadline_at": version.objection_deadline_at.isoformat(),
            "notification_template_version": OBLIGATION_NOTIFICATION_TEMPLATE_VERSION,
        },
    )
    await session.commit()
    return await package_read(session, package, include_audit=True)


async def retry_email_delivery(
    session: AsyncSession,
    settings: Settings,
    actor: User,
    package_id: UUID,
) -> CareerPackageRead:
    return await _retry_email_delivery(
        session,
        settings,
        actor,
        package_id,
        purpose=CareerDeliveryPurpose.PACKAGE_PROVIDED,
    )


async def retry_obligation_email_delivery(
    session: AsyncSession,
    settings: Settings,
    actor: User,
    package_id: UUID,
) -> CareerPackageRead:
    if actor.role is not UserRole.ADMIN:
        api_error(403, "career_package_admin_required", "Действие доступно только администратору")
    obligation = await session.scalar(
        select(CareerPackageObligation).where(
            CareerPackageObligation.package_id == package_id,
            CareerPackageObligation.status != CareerObligationStatus.CANCELLED,
        )
    )
    if obligation is None:
        api_error(409, "career_obligation_missing", "Сначала создайте обязательство по оплате")
    if obligation.notice_sent_at is None or obligation.due_at is None:
        api_error(
            409,
            "career_obligation_notice_not_sent",
            "Сначала отправьте ученику уведомление и запустите срок оплаты",
        )
    return await _retry_email_delivery(
        session,
        settings,
        actor,
        package_id,
        purpose=CareerDeliveryPurpose.PAYMENT_OBLIGATION,
    )


async def _retry_email_delivery(
    session: AsyncSession,
    settings: Settings,
    actor: User,
    package_id: UUID,
    *,
    purpose: CareerDeliveryPurpose,
) -> CareerPackageRead:
    _settings_guard(settings)
    package = await staff_package(session, actor, package_id, lock=True)
    if (
        package.latest_published_version_id is None
        or package.status is not CareerPackageStatus.PROVIDED
    ):
        api_error(409, "career_package_not_provided", "Publish the career package first")
    version = await session.get(CareerPackageVersion, package.latest_published_version_id)
    student = await session.get(User, package.student_id)
    assert version is not None and student is not None
    recipient = (student.email or "").strip()
    if not recipient:
        api_error(422, "career_package_email_missing", "Add the student's email first")

    deliveries = list(
        await session.scalars(
            select(CareerPackageDelivery)
            .where(
                CareerPackageDelivery.package_version_id == version.id,
                CareerPackageDelivery.channel == CareerDeliveryChannel.EMAIL,
                CareerPackageDelivery.purpose == purpose,
            )
            .order_by(CareerPackageDelivery.created_at.desc())
        )
    )
    current = next(
        (item for item in deliveries if item.recipient.casefold() == recipient.casefold()),
        None,
    )
    if current is not None and current.status is CareerDeliveryStatus.DELIVERED:
        return await package_read(session, package, include_audit=True)
    if current is None:
        current = CareerPackageDelivery(
            package_version_id=version.id,
            channel=CareerDeliveryChannel.EMAIL,
            status=CareerDeliveryStatus.PENDING,
            purpose=purpose,
            recipient=recipient,
            attempted_at=datetime.now(UTC),
            idempotency_key=(
                f"{version.id}:email:{recipient.casefold()}"
                if purpose is CareerDeliveryPurpose.PACKAGE_PROVIDED
                else f"{version.id}:obligation-email:{package.id}"
            ),
        )
        session.add(current)
    else:
        current.status = CareerDeliveryStatus.PENDING
        current.attempted_at = datetime.now(UTC)
        current.delivered_at = None
        current.failed_at = None
        current.external_message_id = None
        current.safe_error_message = None
    await session.flush()
    _event(
        session,
        package,
        "email_delivery_retried",
        actor,
        version_id=version.id,
        metadata={"delivery_id": str(current.id), "purpose": purpose.value},
    )
    await session.commit()
    return await package_read(session, package, include_audit=True)


async def submit_objection(
    session: AsyncSession,
    settings: Settings,
    student: User,
    payload: CareerObjectionCreate,
) -> CareerObjectionRead:
    _settings_guard(settings)
    version = await session.get(CareerPackageVersion, payload.package_version_id)
    if version is None:
        api_error(404, "career_package_version_not_found", "Career package version was not found")
    package = await _package(session, version.package_id, lock=True)
    if package.student_id != student.id or version.provided_at is None:
        api_error(404, "career_package_version_not_found", "Career package version was not found")
    now = datetime.now(UTC)
    objection = CareerPackageObjection(
        package_version_id=version.id,
        student_id=student.id,
        component=payload.component,
        reason=payload.reason,
        expected_result=payload.expected_result,
        attachments=[],
        submitted_at=now,
        deadline_at=version.objection_deadline_at,
        is_late=(
            version.objection_deadline_at is not None
            and now > version.objection_deadline_at
        ),
        status=CareerObjectionStatus.SUBMITTED,
    )
    session.add(objection)
    if package.status is CareerPackageStatus.PROVIDED:
        transition(package, CareerPackageStatus.REVISION_REQUESTED)
    obligation = await session.scalar(
        select(CareerPackageObligation).where(CareerPackageObligation.package_id == package.id)
    )
    if (
        obligation is not None
        and obligation.status is CareerObligationStatus.ACTIVE
        and not objection.is_late
    ):
        obligation.status = CareerObligationStatus.HOLD
        obligation.disputed_at = now
    _event(
        session,
        package,
        "objection_submitted",
        student,
        version_id=version.id,
        metadata={"component": payload.component.value, "is_late": objection.is_late},
    )
    staff_ids = set(
        await session.scalars(select(User.id).where(User.role == UserRole.ADMIN, User.is_active))
    )
    assigned_mentor_id = await session.scalar(
        select(MentorStudent.mentor_id).where(MentorStudent.student_id == student.id)
    )
    if assigned_mentor_id is not None:
        staff_ids.add(assigned_mentor_id)
    for staff_id in staff_ids:
        await create_notification(
            session,
            user_id=staff_id,
            actor_user_id=student.id,
            event_key=f"career-objection:{objection.id}:{staff_id}",
            kind=NotificationKind.CAREER_PACKAGE,
            title="Новое возражение по Карьерному пакету",
            body="Ученик направил мотивированное возражение. Требуется рассмотрение.",
            action_url=f"/mentor/students/{student.id}",
        )
    await session.commit()
    await session.refresh(objection)
    return _objection_read(objection)


async def resolve_objection(
    session: AsyncSession,
    settings: Settings,
    actor: User,
    package_id: UUID,
    objection_id: UUID,
    payload: CareerObjectionResolution,
) -> CareerPackageRead:
    _settings_guard(settings)
    package = await staff_package(session, actor, package_id, lock=True)
    objection = await session.scalar(
        select(CareerPackageObjection).where(
            CareerPackageObjection.id == objection_id,
            CareerPackageObjection.package_version_id.in_(
                select(CareerPackageVersion.id).where(CareerPackageVersion.package_id == package.id)
            ),
        )
    )
    if objection is None:
        api_error(404, "career_objection_not_found", "Objection was not found")
    if objection.status not in {
        CareerObjectionStatus.SUBMITTED,
        CareerObjectionStatus.UNDER_REVIEW,
    }:
        api_error(409, "career_objection_already_resolved", "Objection has already been resolved")
    status_value = CareerObjectionStatus(payload.status)
    if status_value in {
        CareerObjectionStatus.ACCEPTED,
        CareerObjectionStatus.PARTIALLY_ACCEPTED,
    } and not payload.create_revision:
        api_error(
            422,
            "career_objection_revision_required",
            "Для принятого возражения необходимо создать исправленную редакцию",
        )
    objection.status = status_value
    objection.resolution_comment = payload.resolution_comment
    objection.resolved_by_user_id = actor.id
    objection.resolved_at = datetime.now(UTC)
    if status_value in {CareerObjectionStatus.ACCEPTED, CareerObjectionStatus.PARTIALLY_ACCEPTED}:
        obligation = await session.scalar(
            select(CareerPackageObligation).where(CareerPackageObligation.package_id == package.id)
        )
        if obligation is not None and obligation.status in {
            CareerObligationStatus.AWAITING_NOTICE,
            CareerObligationStatus.ACTIVE,
        }:
            obligation.status = CareerObligationStatus.HOLD
            obligation.disputed_at = datetime.now(UTC)
        if payload.create_revision:
            draft = await _draft(session, package.id)
            current_version = await session.get(
                CareerPackageVersion, package.latest_published_version_id
            )
            if current_version is not None:
                draft.source_resume_version_id = current_version.source_resume_version_id
                draft.self_presentation_card = current_version.snapshot["self_presentation_card"]
                draft.active_search_parameters = current_version.snapshot[
                    "active_search_parameters"
                ]
                draft.is_stale = False
            transition(package, CareerPackageStatus.DRAFT)
            _event(
                session, package, "revision_created", actor, version_id=objection.package_version_id
            )
    elif package.status is CareerPackageStatus.REVISION_REQUESTED:
        transition(package, CareerPackageStatus.PROVIDED)
        obligation = await session.scalar(
            select(CareerPackageObligation).where(
                CareerPackageObligation.package_id == package.id
            )
        )
        if obligation is not None and obligation.status is CareerObligationStatus.HOLD:
            if obligation.notice_sent_at is None:
                obligation.status = CareerObligationStatus.AWAITING_NOTICE
                obligation.due_at = None
            else:
                obligation.status = CareerObligationStatus.ACTIVE
                obligation.due_at = datetime.now(UTC) + timedelta(days=10)
            obligation.disputed_at = None
    _event(
        session,
        package,
        "objection_resolved",
        actor,
        version_id=objection.package_version_id,
        metadata={"status": status_value.value},
    )
    await create_notification(
        session,
        user_id=package.student_id,
        actor_user_id=actor.id,
        event_key=f"career-objection-resolved:{objection.id}:{status_value.value}",
        kind=NotificationKind.CAREER_PACKAGE,
        title="Возражение по Карьерному пакету рассмотрено",
        body=payload.resolution_comment,
        action_url="/career-package",
    )
    await session.commit()
    return await package_read(session, package, include_audit=True)


async def save_review(
    session: AsyncSession,
    settings: Settings,
    actor: User,
    package_id: UUID,
    payload: CareerReviewMutation,
) -> CareerPackageRead:
    _settings_guard(settings)
    package = await staff_package(session, actor, package_id)
    now = datetime.now(UTC)
    review = CareerSelfPresentationReview(
        package_id=package.id,
        reviewer_id=actor.id,
        held_at=payload.held_at,
        strengths=payload.strengths,
        improvements=payload.improvements,
        preparation_for_next_attempt=payload.preparation_for_next_attempt,
        additional_notes=payload.additional_notes,
        sent_to_student_at=now if payload.send_to_student else None,
    )
    session.add(review)
    if payload.create_draft_from_review:
        draft = await _draft(session, package.id)
        if draft.self_presentation_card:
            card = dict(draft.self_presentation_card)
            notes = str(card.get("additional_notes") or "").strip()
            addition = f"Итоги созвона: {payload.preparation_for_next_attempt}"
            card["additional_notes"] = f"{notes}\n\n{addition}".strip()
            draft.self_presentation_card = card
            if package.status is CareerPackageStatus.PROVIDED:
                transition(package, CareerPackageStatus.DRAFT)
    if payload.send_to_student:
        await create_notification(
            session,
            user_id=package.student_id,
            actor_user_id=actor.id,
            event_key=f"career-self-presentation-review:{review.id}",
            kind=NotificationKind.CAREER_PACKAGE,
            title="Итоги созвона по самопрезентации",
            body="Сотрудник сохранил рекомендации по итогам созвона.",
            action_url="/career-package",
        )
    _event(
        session,
        package,
        "self_presentation_review_saved",
        actor,
        metadata={"sent_to_student": payload.send_to_student},
    )
    await session.commit()
    return await package_read(session, package, include_audit=True)


async def student_packages(
    session: AsyncSession, settings: Settings, student: User
) -> list[CareerStudentPackageRead]:
    _settings_guard(settings)
    packages = list(
        await session.scalars(
            select(CareerPackage).where(
                CareerPackage.student_id == student.id,
                CareerPackage.latest_published_version_id.is_not(None),
            )
        )
    )
    result: list[CareerStudentPackageRead] = []
    for package in packages:
        versions = list(
            await session.scalars(
                select(CareerPackageVersion)
                .where(
                    CareerPackageVersion.package_id == package.id,
                    CareerPackageVersion.provided_at.is_not(None),
                )
                .order_by(CareerPackageVersion.version_number.desc())
            )
        )
        if not versions:
            continue
        track = await session.get(LearningTrack, package.track_id)
        obligation = await session.scalar(
            select(CareerPackageObligation).where(CareerPackageObligation.package_id == package.id)
        )
        objections = list(
            await session.scalars(
                select(CareerPackageObjection)
                .where(CareerPackageObjection.student_id == student.id)
                .join(
                    CareerPackageVersion,
                    CareerPackageVersion.id == CareerPackageObjection.package_version_id,
                )
                .where(CareerPackageVersion.package_id == package.id)
                .order_by(CareerPackageObjection.created_at.desc())
            )
        )
        reviews = list(
            await session.scalars(
                select(CareerSelfPresentationReview)
                .where(
                    CareerSelfPresentationReview.package_id == package.id,
                    CareerSelfPresentationReview.sent_to_student_at.is_not(None),
                )
                .order_by(CareerSelfPresentationReview.held_at.desc())
            )
        )
        result.append(
            CareerStudentPackageRead(
                id=package.id,
                direction=track.title if track else "—",
                status=package.status,
                current_version=_version_read(versions[0]),
                versions=[_version_read(version) for version in versions],
                obligation=(
                    _obligation_read(obligation)
                    if obligation is not None
                    and obligation.status
                    not in {
                        CareerObligationStatus.AWAITING_NOTICE,
                        CareerObligationStatus.CANCELLED,
                    }
                    else None
                ),
                objections=[_objection_read(item) for item in objections],
                reviews=[_review_read(item) for item in reviews],
            )
        )
    return result


async def authorized_version(
    session: AsyncSession, viewer: User, version_id: UUID
) -> CareerPackageVersion:
    version = await session.get(CareerPackageVersion, version_id)
    if version is None or version.provided_at is None:
        api_error(404, "career_package_version_not_found", "Career package version was not found")
    package = await _package(session, version.package_id)
    if viewer.role is UserRole.STUDENT:
        if package.student_id != viewer.id:
            api_error(
                404, "career_package_version_not_found", "Career package version was not found"
            )
    else:
        await _staff_student(session, viewer, package.student_id)
    return version


def version_pdf_upload(version: CareerPackageVersion) -> StoredUpload:
    return StoredUpload(
        storage_key=version.pdf_object_key,
        filename=f"career-package-v{version.version_number}.pdf",
        content_type="application/pdf",
        size=version.pdf_size,
    )


def resume_version_upload(resume: CareerResumeVersion) -> StoredUpload:
    if (
        not resume.storage_key
        or not resume.filename
        or not resume.content_type
        or resume.size is None
    ):
        api_error(404, "career_resume_file_missing", "This resume version has no attached file")
    return StoredUpload(
        storage_key=resume.storage_key,
        filename=resume.filename,
        content_type=resume.content_type,
        size=resume.size,
    )


def _resume_read(resume: CareerResumeVersion | None) -> CareerResumeVersionRead | None:
    return CareerResumeVersionRead.model_validate(resume, from_attributes=True) if resume else None


def _version_read(version: CareerPackageVersion) -> CareerVersionRead:
    return CareerVersionRead.model_validate(version, from_attributes=True)


def _obligation_read(obligation: CareerPackageObligation | None) -> CareerObligationRead | None:
    return (
        CareerObligationRead.model_validate(obligation, from_attributes=True)
        if obligation
        else None
    )


def _objection_read(objection: CareerPackageObjection) -> CareerObjectionRead:
    return CareerObjectionRead.model_validate(objection, from_attributes=True)


def _review_read(review: CareerSelfPresentationReview) -> CareerReviewRead:
    return CareerReviewRead.model_validate(review, from_attributes=True)


async def package_read(
    session: AsyncSession, package: CareerPackage, *, include_audit: bool
) -> CareerPackageRead:
    # ``updated_at`` is generated by PostgreSQL on UPDATE and SQLAlchemy expires that
    # attribute after a flush/commit even though the session uses
    # ``expire_on_commit=False``. Refresh explicitly so response construction never
    # triggers implicit async IO from a synchronous attribute getter (MissingGreenlet).
    await session.refresh(package)
    draft = await _draft(session, package.id)
    track = await session.get(LearningTrack, package.track_id)
    resume = (
        await session.get(CareerResumeVersion, package.source_resume_version_id)
        if package.source_resume_version_id is not None
        else None
    )
    runs = list(
        await session.scalars(
            select(CareerPackageGenerationRun)
            .where(CareerPackageGenerationRun.package_id == package.id)
            .order_by(CareerPackageGenerationRun.created_at.desc())
        )
    )
    versions = list(
        await session.scalars(
            select(CareerPackageVersion)
            .where(CareerPackageVersion.package_id == package.id)
            .order_by(CareerPackageVersion.version_number.desc())
        )
    )
    deliveries = list(
        await session.scalars(
            select(CareerPackageDelivery)
            .join(CareerPackageVersion)
            .where(CareerPackageVersion.package_id == package.id)
            .order_by(CareerPackageDelivery.created_at.desc())
        )
    )
    obligation = await session.scalar(
        select(CareerPackageObligation).where(CareerPackageObligation.package_id == package.id)
    )
    objections = list(
        await session.scalars(
            select(CareerPackageObjection)
            .join(CareerPackageVersion)
            .where(CareerPackageVersion.package_id == package.id)
            .order_by(CareerPackageObjection.created_at.desc())
        )
    )
    reviews = list(
        await session.scalars(
            select(CareerSelfPresentationReview)
            .where(CareerSelfPresentationReview.package_id == package.id)
            .order_by(CareerSelfPresentationReview.held_at.desc())
        )
    )
    audit: list[CareerEventRead] | None = None
    if include_audit:
        events = list(
            await session.scalars(
                select(CareerPackageEvent)
                .where(CareerPackageEvent.package_id == package.id)
                .order_by(CareerPackageEvent.created_at.desc(), CareerPackageEvent.id.desc())
            )
        )
        audit = [
            CareerEventRead(
                id=item.id,
                event_type=item.event_type,
                actor_role=item.actor_role,
                version_id=item.version_id,
                metadata=item.metadata_json,
                created_at=item.created_at,
            )
            for item in events
        ]
    source_data = CareerSourceData.model_validate(draft.source_data) if draft.source_data else None
    return CareerPackageRead(
        id=package.id,
        student_id=package.student_id,
        track_id=package.track_id,
        direction=track.title if track else "—",
        status=package.status,
        lock_version=package.lock_version,
        source_resume_version=_resume_read(resume),
        source_data=source_data,
        self_presentation_card=(
            SelfPresentationCard.model_validate(draft.self_presentation_card)
            if draft.self_presentation_card
            else None
        ),
        active_search_parameters=(
            ActiveSearchParameters.model_validate(draft.active_search_parameters)
            if draft.active_search_parameters
            else None
        ),
        missing_data=[CareerMissingData.model_validate(item) for item in draft.missing_data],
        warnings=[CareerWarning.model_validate(item) for item in draft.warnings],
        is_stale=draft.is_stale,
        readiness=readiness(package, draft),
        generation_runs=[
            CareerGenerationRunRead.model_validate(item, from_attributes=True) for item in runs
        ],
        versions=[_version_read(item) for item in versions],
        deliveries=[
            CareerDeliveryRead.model_validate(item, from_attributes=True) for item in deliveries
        ],
        obligation=_obligation_read(obligation),
        objections=[_objection_read(item) for item in objections],
        reviews=[_review_read(item) for item in reviews],
        audit_timeline=audit,
        created_at=package.created_at,
        updated_at=package.updated_at,
    )
