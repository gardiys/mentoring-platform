from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import api_error
from app.employment_qualification.models import (
    EmploymentAISuggestion,
    EmploymentAISuggestionStatus,
    EmploymentBillingEvent,
    EmploymentBillingEventStatus,
    EmploymentContractPolicySnapshot,
    EmploymentDirection,
    EmploymentDispute,
    EmploymentDisputeStatus,
    EmploymentEvent,
    EmploymentEventSource,
    EmploymentEventType,
    EmploymentEvidence,
    EmploymentEvidenceType,
    EmploymentFollowUp,
    EmploymentFollowUpStatus,
    EmploymentFollowUpType,
    EmploymentProfileAssessment,
    EmploymentQualificationWindow,
    EmploymentTechnologyUsage,
    ProfileAssessmentClassification,
    QualificationWindowClassification,
)
from app.employment_qualification.schemas import (
    EmploymentActualDutiesReport,
    EmploymentAIRequest,
    EmploymentAISuggestionRead,
    EmploymentAssessmentCreate,
    EmploymentAssessmentRead,
    EmploymentCaseList,
    EmploymentCaseRead,
    EmploymentChangeReport,
    EmploymentDisputeCreate,
    EmploymentDisputeRead,
    EmploymentDisputeResolution,
    EmploymentEndReport,
    EmploymentEventRead,
    EmploymentEvidenceCreate,
    EmploymentEvidenceRead,
    EmploymentFollowUpRead,
    EmploymentInformationRequest,
    EmploymentOfferReport,
    EmploymentOfferStatusReport,
    EmploymentPolicyCreate,
    EmploymentQualificationMetrics,
    EmploymentTrackOption,
    EmploymentWorkStartReport,
    QualificationWindowRead,
    TechnologyUsageInput,
    TechnologyUsageRead,
)
from app.employment_qualification.state_machine import transition
from app.interviews.companies import get_or_create_company
from app.interviews.intelligence_ai import EMPLOYMENT_PROFILE_PROMPT_VERSION
from app.interviews.models import Company
from app.interviews.uploads import StoredUpload
from app.mentors.service import assigned_student
from app.notifications.models import NotificationKind
from app.notifications.service import create_notification, notify_student
from app.payments.models import (
    EmploymentCaseStatus,
    StudentEmployment,
    StudentEmploymentStatus,
)
from app.payments.service import ensure_profile_billing_installments
from app.tracks.models import LearningTrack, LearningTrackEnrollment
from app.users.models import User, UserRole

PROFILE_CLASSIFICATIONS = {
    ProfileAssessmentClassification.PROFILE,
    ProfileAssessmentClassification.MIXED_PROFILE,
}
settings = get_settings()


def _require_staff(actor: User) -> None:
    if actor.role not in {UserRole.MENTOR, UserRole.ADMIN}:
        api_error(403, "employment_staff_action_forbidden", "Staff access is required")


async def _direction_for_track(session: AsyncSession, track_id: UUID) -> EmploymentDirection:
    track = await session.get(LearningTrack, track_id)
    if track is None:
        api_error(422, "employment_track_not_found", "Learning direction was not found")
    slug = track.slug.casefold()
    if slug == "python":
        return EmploymentDirection.PYTHON
    if slug == "go":
        return EmploymentDirection.GO
    api_error(422, "employment_direction_unsupported", "Only Python and Go are supported")


async def _student_has_track(session: AsyncSession, student_id: UUID, track_id: UUID) -> None:
    exists = await session.scalar(
        select(LearningTrackEnrollment.user_id).where(
            LearningTrackEnrollment.user_id == student_id,
            LearningTrackEnrollment.track_id == track_id,
        )
    )
    if exists is None:
        api_error(
            403, "employment_track_forbidden", "This direction is not assigned to the student"
        )


async def _case_for_actor(
    session: AsyncSession,
    actor: User,
    case_id: UUID,
    *,
    lock: bool = False,
) -> StudentEmployment:
    statement = select(StudentEmployment).where(StudentEmployment.id == case_id)
    if lock:
        statement = statement.with_for_update()
    case = await session.scalar(statement)
    if case is None:
        api_error(404, "employment_case_not_found", "Employment case was not found")
    if actor.role is UserRole.STUDENT:
        if case.student_id != actor.id:
            api_error(404, "employment_case_not_found", "Employment case was not found")
    else:
        await assigned_student(session, actor, case.student_id)
    return case


def _check_lock(case: StudentEmployment, expected: int) -> None:
    if case.lock_version != expected:
        api_error(
            409,
            "employment_case_changed",
            "Employment data changed in another session. Reload and review the latest version.",
        )


def _add_business_days(start: date, days: int) -> date:
    result = start
    remaining = days
    while remaining:
        result += timedelta(days=1)
        if result.weekday() < 5:
            remaining -= 1
    return result


def _event_source(actor: User) -> EmploymentEventSource:
    return (
        EmploymentEventSource.STUDENT
        if actor.role is UserRole.STUDENT
        else EmploymentEventSource.STAFF
    )


async def _record_event(
    session: AsyncSession,
    case: StudentEmployment,
    actor: User | None,
    event_type: EmploymentEventType,
    effective_at: date,
    idempotency_key: str,
    *,
    payload: dict[str, object] | None = None,
    evidence_ids: list[UUID] | None = None,
    source: EmploymentEventSource | None = None,
    correlation_id: str | None = None,
) -> EmploymentEvent:
    statement = (
        insert(EmploymentEvent)
        .values(
            employment_id=case.id,
            event_type=event_type,
            effective_at=effective_at,
            actor_id=actor.id if actor else None,
            source=source or (_event_source(actor) if actor else EmploymentEventSource.SYSTEM),
            payload=payload or {},
            evidence_ids=[str(item) for item in evidence_ids or []],
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )
        .on_conflict_do_nothing(index_elements=[EmploymentEvent.idempotency_key])
        .returning(EmploymentEvent.id)
    )
    event_id = await session.scalar(statement)
    if event_id is None:
        existing = await session.scalar(
            select(EmploymentEvent).where(EmploymentEvent.idempotency_key == idempotency_key)
        )
        if existing is None or existing.employment_id != case.id:
            api_error(409, "idempotency_key_reused", "Idempotency key was already used")
        return existing
    event = await session.get(EmploymentEvent, event_id)
    assert event is not None
    return event


async def _replay_event_result(
    session: AsyncSession,
    actor: User,
    case_id: UUID,
    idempotency_key: str,
) -> EmploymentCaseRead | None:
    existing = await session.scalar(
        select(EmploymentEvent).where(EmploymentEvent.idempotency_key == idempotency_key)
    )
    if existing is None:
        return None
    if existing.employment_id != case_id:
        api_error(409, "idempotency_key_reused", "Idempotency key was already used")
    case = await _case_for_actor(session, actor, case_id)
    return await case_read(session, case)


async def _latest_policy(
    session: AsyncSession, student_id: UUID, track_id: UUID
) -> EmploymentContractPolicySnapshot | None:
    policy: EmploymentContractPolicySnapshot | None = await session.scalar(
        select(EmploymentContractPolicySnapshot)
        .where(
            EmploymentContractPolicySnapshot.student_id == student_id,
            EmploymentContractPolicySnapshot.track_id == track_id,
        )
        .order_by(
            EmploymentContractPolicySnapshot.accepted_at.desc(),
            EmploymentContractPolicySnapshot.version.desc(),
        )
        .limit(1)
    )
    return policy


async def report_offer(
    session: AsyncSession, student: User, payload: EmploymentOfferReport
) -> EmploymentCaseRead:
    await _student_has_track(session, student.id, payload.track_id)
    await _direction_for_track(session, payload.track_id)
    existing_event = await session.scalar(
        select(EmploymentEvent).where(EmploymentEvent.idempotency_key == payload.idempotency_key)
    )
    if existing_event is not None:
        existing_case = await _case_for_actor(session, student, existing_event.employment_id)
        return await case_read(session, existing_case)
    active = await session.scalar(
        select(StudentEmployment).where(
            StudentEmployment.student_id == student.id,
            StudentEmployment.status == StudentEmploymentStatus.ACTIVE,
        )
    )
    if active is not None:
        api_error(
            409,
            "active_employment_case_exists",
            "An active employment case already exists. Report changes in that case.",
        )
    company = (
        await session.get(Company, payload.employer_id)
        if payload.employer_id
        else await get_or_create_company(session, payload.employer_name)
    )
    if company is None:
        api_error(422, "employment_company_not_found", "Employer was not found")
    policy = await _latest_policy(session, student.id, payload.track_id)
    case = StudentEmployment(
        student_id=student.id,
        company_id=company.id,
        company_name=company.name,
        track_id=payload.track_id,
        contract_policy_id=policy.id if policy else None,
        start_date=None,
        expected_start_date=payload.expected_start_date,
        net_salary_kopecks=(
            int(payload.net_salary_rubles * Decimal(100))
            if payload.net_salary_rubles is not None
            else None
        ),
        repayment_percent=student.repayment_percent,
        status=StudentEmploymentStatus.ACTIVE,
        vacancy_title=payload.vacancy_title,
        official_job_title=payload.official_job_title,
        activity_type=payload.activity_type,
        offer_received_at=payload.offer_received_at,
        offer_accepted_at=payload.offer_accepted_at,
        contract_signed_at=payload.contract_signed_at,
        initial_vacancy_stack=_normalized_stack(payload.vacancy_stack),
        offer_stack=_normalized_stack(payload.offer_stack),
        vacancy_duties=payload.vacancy_duties,
        student_comment=payload.student_comment,
        case_status=EmploymentCaseStatus.AWAITING_ACTUAL_DUTIES,
        recorded_by_user_id=student.id,
        legacy_policy_snapshot=(
            None
            if policy
            else {
                "policy_code": "legacy-unversioned",
                "profile_qualification_enabled": False,
                "reason": "No accepted employment policy snapshot is linked",
            }
        ),
    )
    session.add(case)
    await session.flush()
    await _record_event(
        session,
        case,
        student,
        EmploymentEventType.OFFER_RECEIVED,
        payload.offer_received_at,
        payload.idempotency_key,
        payload={
            "vacancy_title": payload.vacancy_title,
            "activity_type": payload.activity_type.value,
            "offer_accepted_at": payload.offer_accepted_at.isoformat()
            if payload.offer_accepted_at
            else None,
            "contract_signed_at": payload.contract_signed_at.isoformat()
            if payload.contract_signed_at
            else None,
        },
    )
    await session.commit()
    return await case_read(session, case)


def _normalized_stack(values: list[str]) -> list[str]:
    normalized = [" ".join(item.split())[:100] for item in values if item.strip()]
    return list(dict.fromkeys(normalized))


async def _replace_usages(
    session: AsyncSession,
    case: StudentEmployment,
    usages: list[TechnologyUsageInput],
    *,
    staff_confirmed: bool = False,
) -> None:
    referenced_evidence = list(
        dict.fromkeys(evidence_id for item in usages for evidence_id in item.evidence_ids)
    )
    await _valid_evidence_ids(session, case.id, referenced_evidence)
    for item in usages:
        session.add(
            EmploymentTechnologyUsage(
                employment_id=case.id,
                normalized_name=" ".join(item.normalized_name.split())[:100],
                usage_type=item.usage_type,
                frequency=item.frequency,
                part_of_official_duties=item.part_of_official_duties,
                part_of_project=item.part_of_project,
                started_at=item.started_at,
                ended_at=item.ended_at,
                description=item.description,
                confirmed_by_student=True,
                confirmed_by_staff=staff_confirmed,
                evidence_ids=[str(value) for value in item.evidence_ids],
            )
        )


async def report_work_start(
    session: AsyncSession,
    student: User,
    case_id: UUID,
    payload: EmploymentWorkStartReport,
) -> EmploymentCaseRead:
    replay = await _replay_event_result(session, student, case_id, payload.idempotency_key)
    if replay is not None:
        return replay
    case = await _case_for_actor(session, student, case_id, lock=True)
    _check_lock(case, payload.expected_lock_version)
    case.start_date = payload.employment_started_at
    case.official_job_title = payload.official_job_title
    case.team_description = payload.team_description
    case.project_description = payload.project_description
    case.actual_duties = payload.actual_duties
    case.actual_stack = _normalized_stack(payload.actual_stack)
    case.differences_description = payload.differences_description
    target = (
        EmploymentCaseStatus.AWAITING_STAFF_REVIEW
        if payload.actual_duties and payload.actual_stack
        else EmploymentCaseStatus.AWAITING_ACTUAL_DUTIES
    )
    transition(case, target)
    if target is EmploymentCaseStatus.AWAITING_ACTUAL_DUTIES:
        due = _add_business_days(payload.employment_started_at, 10)
        case.monitoring_due_at = due
        await _create_followup(
            session,
            case,
            EmploymentFollowUpType.ACTUAL_DUTIES,
            due,
            ["actual_duties", "actual_stack", "project_description"],
            f"actual-duties:{case.id}:{due.isoformat()}",
        )
    await _replace_usages(session, case, payload.technology_usages)
    case.lock_version += 1
    await _record_event(
        session,
        case,
        student,
        EmploymentEventType.EMPLOYMENT_STARTED,
        payload.employment_started_at,
        payload.idempotency_key,
        payload={
            "official_job_title": payload.official_job_title,
            "actual_duties_known": bool(payload.actual_duties),
            "actual_duties": payload.actual_duties,
            "actual_stack": case.actual_stack,
            "project_description": payload.project_description,
            "team_description": payload.team_description,
        },
    )
    await session.commit()
    return await case_read(session, case)


async def report_offer_status(
    session: AsyncSession,
    student: User,
    case_id: UUID,
    payload: EmploymentOfferStatusReport,
) -> EmploymentCaseRead:
    replay = await _replay_event_result(session, student, case_id, payload.idempotency_key)
    if replay is not None:
        return replay
    case = await _case_for_actor(session, student, case_id, lock=True)
    _check_lock(case, payload.expected_lock_version)
    if case.offer_received_at and payload.effective_at < case.offer_received_at:
        api_error(
            422,
            "employment_offer_status_before_offer",
            "Acceptance or signing date cannot precede the offer date",
        )
    event_type = (
        EmploymentEventType.OFFER_ACCEPTED
        if payload.event == "offer_accepted"
        else EmploymentEventType.CONTRACT_SIGNED
    )
    await _record_event(
        session,
        case,
        student,
        event_type,
        payload.effective_at,
        payload.idempotency_key,
    )
    if payload.event == "offer_accepted":
        case.offer_accepted_at = payload.effective_at
    else:
        case.contract_signed_at = payload.effective_at
    case.lock_version += 1
    await session.commit()
    return await case_read(session, case)


async def report_actual_duties(
    session: AsyncSession,
    student: User,
    case_id: UUID,
    payload: EmploymentActualDutiesReport,
) -> EmploymentCaseRead:
    replay = await _replay_event_result(session, student, case_id, payload.idempotency_key)
    if replay is not None:
        return replay
    case = await _case_for_actor(session, student, case_id, lock=True)
    _check_lock(case, payload.expected_lock_version)
    case.actual_duties = payload.actual_duties
    case.actual_stack = _normalized_stack(payload.actual_stack)
    case.team_description = payload.team_description
    case.project_description = payload.project_description
    case.differences_description = payload.differences_description
    target = (
        EmploymentCaseStatus.AWAITING_STAFF_REVIEW
        if payload.actual_stack or payload.technology_usages
        else EmploymentCaseStatus.AWAITING_ACTUAL_DUTIES
    )
    transition(case, target)
    case.monitoring_due_at = None
    if target is EmploymentCaseStatus.AWAITING_ACTUAL_DUTIES:
        due = _add_business_days(date.today(), 10)
        case.monitoring_due_at = due
        await _create_followup(
            session,
            case,
            EmploymentFollowUpType.ACTUAL_DUTIES,
            due,
            ["actual_stack", "technology_usages"],
            f"actual-stack:{case.id}:{due.isoformat()}",
        )
    case.lock_version += 1
    await _replace_usages(session, case, payload.technology_usages)
    await _answer_open_followups(session, case.id)
    effective = case.start_date or date.today()
    await _record_event(
        session,
        case,
        student,
        EmploymentEventType.ACTUAL_DUTIES_REPORTED,
        effective,
        payload.idempotency_key,
        payload={
            "actual_duties": payload.actual_duties,
            "actual_stack": case.actual_stack,
            "project_description": payload.project_description,
            "team_description": payload.team_description,
            "differences_description": payload.differences_description,
        },
    )
    await session.commit()
    return await case_read(session, case)


CHANGE_EVENT = {
    "job_title": EmploymentEventType.JOB_TITLE_CHANGED,
    "team": EmploymentEventType.TEAM_CHANGED,
    "project": EmploymentEventType.PROJECT_CHANGED,
    "duties": EmploymentEventType.DUTIES_CHANGED,
    "stack": EmploymentEventType.STACK_CONFIRMED,
    "profile_usage": EmploymentEventType.PROFILE_ACTIVITY_STARTED,
}


async def report_change(
    session: AsyncSession,
    student: User,
    case_id: UUID,
    payload: EmploymentChangeReport,
) -> EmploymentCaseRead:
    replay = await _replay_event_result(session, student, case_id, payload.idempotency_key)
    if replay is not None:
        return replay
    case = await _case_for_actor(session, student, case_id, lock=True)
    _check_lock(case, payload.expected_lock_version)
    if payload.change_type == "job_title":
        case.official_job_title = payload.new_state[:240]
    elif payload.change_type == "team":
        case.team_description = payload.new_state
    elif payload.change_type == "project":
        case.project_description = payload.new_state
    elif payload.change_type == "duties":
        case.actual_duties = payload.new_state
    if payload.actual_stack is not None:
        case.actual_stack = _normalized_stack(payload.actual_stack)
    await _replace_usages(session, case, payload.technology_usages)
    transition(case, EmploymentCaseStatus.AWAITING_STAFF_REVIEW)
    case.lock_version += 1
    await _record_event(
        session,
        case,
        student,
        CHANGE_EVENT[payload.change_type],
        payload.effective_at,
        payload.idempotency_key,
        payload={
            "change_type": payload.change_type,
            "previous_state": payload.previous_state,
            "new_state": payload.new_state,
            "description": payload.description,
        },
    )
    await session.commit()
    return await case_read(session, case)


async def report_end(
    session: AsyncSession,
    student: User,
    case_id: UUID,
    payload: EmploymentEndReport,
) -> EmploymentCaseRead:
    replay = await _replay_event_result(session, student, case_id, payload.idempotency_key)
    if replay is not None:
        return replay
    case = await _case_for_actor(session, student, case_id, lock=True)
    _check_lock(case, payload.expected_lock_version)
    if case.start_date and payload.employment_ended_at < case.start_date:
        api_error(422, "employment_end_before_start", "End date cannot precede work start")
    case.status = StudentEmploymentStatus.TERMINATED
    case.ended_at = payload.employment_ended_at
    case.end_reason = payload.reason
    case.monitoring_due_at = None
    transition(case, EmploymentCaseStatus.ENDED)
    case.lock_version += 1
    await _cancel_open_followups(session, case.id)
    await _record_event(
        session,
        case,
        student,
        EmploymentEventType.EMPLOYMENT_ENDED,
        payload.employment_ended_at,
        payload.idempotency_key,
        payload={"reason": payload.reason},
    )
    await session.commit()
    return await case_read(session, case)


async def create_policy_snapshot(
    session: AsyncSession,
    admin: User,
    student_id: UUID,
    payload: EmploymentPolicyCreate,
) -> EmploymentContractPolicySnapshot:
    if admin.role is not UserRole.ADMIN:
        api_error(
            403, "employment_policy_forbidden", "Only an administrator can record contract terms"
        )
    student = await session.get(User, student_id)
    if student is None:
        api_error(404, "student_not_found", "Student was not found")
    await _student_has_track(session, student_id, payload.track_id)
    direction = await _direction_for_track(session, payload.track_id)
    rules = dict(payload.rules)
    rules.setdefault("requires_any_software_work_report", True)
    rules.setdefault("profile_definition", "substantial_non_ephemeral_direction_language_usage")
    rules.setdefault("actual_duties_followup_business_days", 10)
    rules.setdefault("non_profile_monitoring_days", 30)
    rules.setdefault("billing_formula", "student_repayment_percent_of_confirmed_net_salary")
    rules.setdefault("profile_qualification_enabled", True)
    policy = EmploymentContractPolicySnapshot(
        student_id=student_id,
        track_id=payload.track_id,
        policy_code=payload.policy_code,
        version=payload.version,
        accepted_at=payload.accepted_at,
        direction=direction,
        direction_language="Python" if direction is EmploymentDirection.PYTHON else "Go",
        control_period_started_at=payload.control_period_started_at,
        control_period_ended_at=payload.control_period_ended_at,
        extension_ended_at=payload.extension_ended_at,
        rules=rules,
        created_by_user_id=admin.id,
        is_legacy=False,
    )
    session.add(policy)
    await session.commit()
    await session.refresh(policy)
    return policy


async def create_assessment(
    session: AsyncSession,
    actor: User,
    case_id: UUID,
    payload: EmploymentAssessmentCreate,
    *,
    ai_suggestion: dict[str, object] | None = None,
) -> EmploymentCaseRead:
    _require_staff(actor)
    existing = await session.scalar(
        select(EmploymentProfileAssessment).where(
            EmploymentProfileAssessment.idempotency_key == payload.idempotency_key
        )
    )
    if existing is not None:
        if existing.employment_id != case_id:
            api_error(409, "idempotency_key_reused", "Idempotency key was already used")
        existing_case = await _case_for_actor(session, actor, case_id)
        return await case_read(session, existing_case)
    case = await _case_for_actor(session, actor, case_id, lock=True)
    _check_lock(case, payload.expected_lock_version)
    if case.track_id is None:
        api_error(409, "employment_direction_missing", "Employment direction must be selected")
    direction = await _direction_for_track(session, case.track_id)
    current = (
        await session.get(EmploymentProfileAssessment, case.current_assessment_id)
        if case.current_assessment_id
        else None
    )
    evidence = await _valid_evidence_ids(session, case.id, payload.evidence_ids)
    if ai_suggestion is None:
        latest_ai = await session.scalar(
            select(EmploymentAISuggestion)
            .where(
                EmploymentAISuggestion.employment_id == case.id,
                EmploymentAISuggestion.status == EmploymentAISuggestionStatus.COMPLETED,
            )
            .order_by(EmploymentAISuggestion.created_at.desc())
        )
        ai_suggestion = latest_ai.output if latest_ai is not None else None
    now = datetime.now(UTC)
    assessment = EmploymentProfileAssessment(
        employment_id=case.id,
        policy_snapshot_id=case.contract_policy_id,
        track_id=case.track_id,
        direction=direction,
        direction_language="Python" if direction is EmploymentDirection.PYTHON else "Go",
        classification=payload.classification,
        effective_profile_started_at=payload.effective_profile_started_at,
        effective_profile_ended_at=payload.effective_profile_ended_at,
        rationale=payload.rationale,
        qualifying_criteria=payload.qualifying_criteria,
        non_qualifying_reasons=payload.non_qualifying_reasons,
        evidence_ids=[str(item) for item in evidence],
        ai_suggestion=ai_suggestion,
        reviewed_by_user_id=actor.id,
        reviewed_at=now,
        supersedes_assessment_id=current.id if current else None,
        idempotency_key=payload.idempotency_key,
    )
    session.add(assessment)
    await session.flush()
    window = await _evaluate_window(session, case, assessment)
    session.add(window)
    case.current_assessment_id = assessment.id
    case.profile_activity_started_at = payload.effective_profile_started_at
    case.profile_activity_ended_at = payload.effective_profile_ended_at
    case.lock_version += 1
    if payload.classification in PROFILE_CLASSIFICATIONS:
        transition(case, EmploymentCaseStatus.PROFILE_CONFIRMED)
        case.monitoring_due_at = None
        if window.billing_trigger_allowed:
            await _handoff_billing(session, case, assessment, window)
    elif payload.classification is ProfileAssessmentClassification.NON_PROFILE:
        if _monitoring_allowed(case, window):
            transition(case, EmploymentCaseStatus.MONITORING_NON_PROFILE)
            due = date.today() + timedelta(days=30)
            case.monitoring_due_at = due
            await _create_followup(
                session,
                case,
                EmploymentFollowUpType.MONTHLY_CHANGE_CHECK,
                due,
                ["official_job_title", "team", "project", "actual_duties", "actual_stack"],
                f"monthly-monitoring:{case.id}:{due.isoformat()}",
            )
        else:
            transition(case, EmploymentCaseStatus.NON_PROFILE_CONFIRMED)
    elif payload.classification is ProfileAssessmentClassification.DISPUTED:
        transition(case, EmploymentCaseStatus.DISPUTED)
        case.billing_on_hold = True
    else:
        transition(case, EmploymentCaseStatus.AWAITING_ACTUAL_DUTIES)
    await _record_event(
        session,
        case,
        actor,
        EmploymentEventType.ASSESSMENT_CHANGED,
        payload.effective_profile_started_at or date.today(),
        f"assessment-event:{assessment.id}",
        payload={
            "assessment_id": str(assessment.id),
            "classification": payload.classification.value,
        },
    )
    await notify_student(
        session,
        student_id=case.student_id,
        actor=actor,
        event_key=f"employment-assessment:{assessment.id}",
        kind=NotificationKind.EMPLOYMENT,
        title="Решение по фактической работе",
        body=_assessment_notification(case, assessment, window),
        action_url="/payments",
    )
    await session.commit()
    return await case_read(session, case)


async def _evaluate_window(
    session: AsyncSession,
    case: StudentEmployment,
    assessment: EmploymentProfileAssessment,
) -> EmploymentQualificationWindow:
    now = datetime.now(UTC)
    policy = (
        await session.get(EmploymentContractPolicySnapshot, case.contract_policy_id)
        if case.contract_policy_id
        else None
    )
    started = assessment.effective_profile_started_at
    if policy is None or policy.is_legacy or not policy.rules.get("profile_qualification_enabled"):
        return EmploymentQualificationWindow(
            assessment_id=assessment.id,
            policy_snapshot_id=policy.id if policy else None,
            classification=QualificationWindowClassification.INSUFFICIENT_DATA,
            evaluation_reason=(
                "No accepted versioned policy permits automatic billing qualification."
            ),
            billing_trigger_allowed=False,
            evaluated_at=now,
            policy_version="legacy-unversioned",
        )
    if assessment.classification not in PROFILE_CLASSIFICATIONS or started is None:
        classification = QualificationWindowClassification.INSUFFICIENT_DATA
        reason = "Profile activity and its effective start date must both be confirmed."
        allowed = False
    elif policy.control_period_started_at <= started <= policy.control_period_ended_at:
        main_end_raw = policy.rules.get("main_period_ended_at")
        main_end = date.fromisoformat(str(main_end_raw)) if main_end_raw else None
        classification = (
            QualificationWindowClassification.WITHIN_MAIN_PERIOD
            if main_end and started <= main_end
            else QualificationWindowClassification.WITHIN_CONTROL_PERIOD
        )
        reason = "Confirmed profile activity began within the accepted contract control period."
        allowed = True
    elif policy.extension_ended_at and started <= policy.extension_ended_at:
        linked_process = policy.rules.get("linked_interview_process_id")
        if linked_process:
            classification = QualificationWindowClassification.WITHIN_SPECIFIC_PROCESS_EXTENSION
            reason = "Confirmed profile activity is linked to the specific accepted extension."
            allowed = True
        else:
            classification = QualificationWindowClassification.OUTSIDE_BILLABLE_WINDOW
            reason = "No confirmed link to a specific interview process exists for the extension."
            allowed = False
    else:
        classification = QualificationWindowClassification.OUTSIDE_BILLABLE_WINDOW
        reason = "Profile activity began outside the accepted billable window."
        allowed = False
    return EmploymentQualificationWindow(
        assessment_id=assessment.id,
        policy_snapshot_id=policy.id,
        control_period_started_at=policy.control_period_started_at,
        control_period_ended_at=policy.control_period_ended_at,
        extension_ended_at=policy.extension_ended_at,
        classification=classification,
        linked_interview_process_id=(
            UUID(str(policy.rules["linked_interview_process_id"]))
            if policy.rules.get("linked_interview_process_id")
            else None
        ),
        evaluation_reason=reason,
        billing_trigger_allowed=allowed,
        evaluated_at=now,
        policy_version=f"{policy.policy_code}:v{policy.version}",
    )


async def _handoff_billing(
    session: AsyncSession,
    case: StudentEmployment,
    assessment: EmploymentProfileAssessment,
    window: EmploymentQualificationWindow,
) -> EmploymentBillingEvent:
    key_source = ":".join(
        (
            str(case.student_id),
            str(case.track_id),
            str(case.id),
            str(assessment.id),
            str(case.contract_policy_id),
            str(assessment.effective_profile_started_at),
        )
    )
    idempotency_key = hashlib.sha256(key_source.encode()).hexdigest()
    existing = await session.scalar(
        select(EmploymentBillingEvent).where(
            EmploymentBillingEvent.idempotency_key == idempotency_key
        )
    )
    if existing is not None:
        return existing
    status = (
        EmploymentBillingEventStatus.AWAITING_COMPENSATION
        if case.net_salary_kopecks is None
        else EmploymentBillingEventStatus.PROCESSED
    )
    billing_event = EmploymentBillingEvent(
        employment_id=case.id,
        assessment_id=assessment.id,
        policy_snapshot_id=case.contract_policy_id,
        status=status,
        idempotency_key=idempotency_key,
        payload={
            "student_id": str(case.student_id),
            "track_id": str(case.track_id),
            "employment_case_id": str(case.id),
            "assessment_id": str(assessment.id),
            "direction": assessment.direction.value,
            "profile_activity_started_at": str(assessment.effective_profile_started_at),
            "qualification_window": window.classification.value,
            "policy_version": window.policy_version,
            "evidence_ids": assessment.evidence_ids,
        },
        processed_at=datetime.now(UTC)
        if status is EmploymentBillingEventStatus.PROCESSED
        else None,
    )
    session.add(billing_event)
    if status is EmploymentBillingEventStatus.PROCESSED:
        case.billing_started_at = assessment.effective_profile_started_at
        case.billing_on_hold = False
        await ensure_profile_billing_installments(session, case)
    return billing_event


def _monitoring_allowed(case: StudentEmployment, window: EmploymentQualificationWindow) -> bool:
    today = date.today()
    final = window.extension_ended_at or window.control_period_ended_at
    return case.status is StudentEmploymentStatus.ACTIVE and final is not None and today <= final


async def open_dispute(
    session: AsyncSession,
    student: User,
    case_id: UUID,
    payload: EmploymentDisputeCreate,
) -> EmploymentCaseRead:
    case = await _case_for_actor(session, student, case_id, lock=True)
    duplicate = await session.scalar(
        select(EmploymentDispute).where(
            EmploymentDispute.employment_id == case.id,
            EmploymentDispute.status.in_(
                [EmploymentDisputeStatus.OPEN, EmploymentDisputeStatus.UNDER_REVIEW]
            ),
        )
    )
    if duplicate is not None:
        return await case_read(session, case)
    await _valid_evidence_ids(session, case.id, payload.evidence_ids)
    dispute = EmploymentDispute(
        employment_id=case.id,
        assessment_id=case.current_assessment_id,
        student_id=student.id,
        disputed_conclusion=payload.disputed_conclusion,
        reason=payload.reason,
        alternative_started_at=payload.alternative_started_at,
        actual_duties=payload.actual_duties,
        comment=payload.comment,
        evidence_ids=[str(item) for item in payload.evidence_ids],
        status=EmploymentDisputeStatus.OPEN,
    )
    session.add(dispute)
    case.billing_on_hold = True
    transition(case, EmploymentCaseStatus.DISPUTED)
    case.lock_version += 1
    billing = await session.scalar(
        select(EmploymentBillingEvent)
        .where(EmploymentBillingEvent.employment_id == case.id)
        .order_by(EmploymentBillingEvent.created_at.desc())
    )
    if billing is not None:
        billing.status = EmploymentBillingEventStatus.HOLD
    await _record_event(
        session,
        case,
        student,
        EmploymentEventType.DISPUTE_OPENED,
        date.today(),
        payload.idempotency_key,
        payload={"disputed_conclusion": payload.disputed_conclusion},
    )
    admin_ids = list(await session.scalars(select(User.id).where(User.role == UserRole.ADMIN)))
    for admin_id in admin_ids:
        await create_notification(
            session,
            user_id=admin_id,
            event_key=f"employment-dispute:{dispute.id}",
            kind=NotificationKind.EMPLOYMENT,
            title="Открыт спор по квалификации работы",
            body="Ученик оспорил решение по фактической работе. Требуется повторное рассмотрение.",
            action_url=f"/mentor/students/{student.id}",
            actor_user_id=student.id,
        )
    await session.commit()
    return await case_read(session, case)


async def resolve_dispute(
    session: AsyncSession,
    actor: User,
    case_id: UUID,
    dispute_id: UUID,
    payload: EmploymentDisputeResolution,
) -> EmploymentCaseRead:
    _require_staff(actor)
    case = await _case_for_actor(session, actor, case_id, lock=True)
    dispute = await session.scalar(
        select(EmploymentDispute)
        .where(
            EmploymentDispute.id == dispute_id,
            EmploymentDispute.employment_id == case.id,
        )
        .with_for_update()
    )
    if dispute is None:
        api_error(404, "employment_dispute_not_found", "Dispute was not found")
    if dispute.status not in {EmploymentDisputeStatus.OPEN, EmploymentDisputeStatus.UNDER_REVIEW}:
        api_error(409, "employment_dispute_closed", "Dispute is already closed")
    if case.current_assessment_id:
        current = await session.get(EmploymentProfileAssessment, case.current_assessment_id)
        if current and current.reviewed_by_user_id == actor.id and actor.role is not UserRole.ADMIN:
            api_error(
                403,
                "independent_dispute_review_required",
                "Another reviewer or administrator is required",
            )
    dispute.status = (
        EmploymentDisputeStatus.RESOLVED
        if payload.outcome == "resolved"
        else EmploymentDisputeStatus.REJECTED
    )
    dispute.resolution = payload.resolution
    dispute.resolved_by_user_id = actor.id
    dispute.resolved_at = datetime.now(UTC)
    await _record_event(
        session,
        case,
        actor,
        EmploymentEventType.DISPUTE_RESOLVED,
        date.today(),
        f"dispute-resolved:{dispute.id}:{payload.outcome}",
        payload={"outcome": payload.outcome},
    )
    if payload.replacement_assessment is None:
        current = (
            await session.get(EmploymentProfileAssessment, case.current_assessment_id)
            if case.current_assessment_id
            else None
        )
        if current and current.classification in PROFILE_CLASSIFICATIONS:
            transition(case, EmploymentCaseStatus.PROFILE_CONFIRMED)
            case.billing_on_hold = False
            billing = await session.scalar(
                select(EmploymentBillingEvent)
                .where(EmploymentBillingEvent.assessment_id == current.id)
                .with_for_update()
            )
            if billing is not None and billing.status is EmploymentBillingEventStatus.HOLD:
                billing.status = (
                    EmploymentBillingEventStatus.PROCESSED
                    if case.net_salary_kopecks is not None
                    else EmploymentBillingEventStatus.AWAITING_COMPENSATION
                )
        else:
            transition(case, EmploymentCaseStatus.NON_PROFILE_CONFIRMED)
        case.lock_version += 1
        await session.commit()
        return await case_read(session, case)
    await session.flush()
    replacement = payload.replacement_assessment.model_copy(
        update={"expected_lock_version": case.lock_version}
    )
    return await create_assessment(session, actor, case.id, replacement)


async def request_information(
    session: AsyncSession,
    actor: User,
    case_id: UUID,
    payload: EmploymentInformationRequest,
) -> EmploymentCaseRead:
    _require_staff(actor)
    replay = await _replay_event_result(
        session, actor, case_id, f"request-event:{payload.idempotency_key}"
    )
    if replay is not None:
        return replay
    case = await _case_for_actor(session, actor, case_id, lock=True)
    await _create_followup(
        session,
        case,
        EmploymentFollowUpType.ADDITIONAL_INFORMATION,
        payload.due_at,
        payload.requested_fields,
        payload.idempotency_key,
    )
    transition(case, EmploymentCaseStatus.AWAITING_ACTUAL_DUTIES)
    case.monitoring_due_at = payload.due_at
    case.lock_version += 1
    await _record_event(
        session,
        case,
        actor,
        EmploymentEventType.ACTUAL_DUTIES_REQUESTED,
        date.today(),
        f"request-event:{payload.idempotency_key}",
        payload={
            "requested_fields": payload.requested_fields,
            "due_at": payload.due_at.isoformat(),
        },
    )
    await notify_student(
        session,
        student_id=case.student_id,
        actor=actor,
        event_key=f"employment-info-request:{payload.idempotency_key}",
        kind=NotificationKind.EMPLOYMENT,
        title="Нужно уточнить данные о работе",
        body="Укажите: " + ", ".join(payload.requested_fields),
        action_url="/payments",
    )
    await session.commit()
    return await case_read(session, case)


async def add_text_evidence(
    session: AsyncSession,
    actor: User,
    case_id: UUID,
    payload: EmploymentEvidenceCreate,
) -> EmploymentCaseRead:
    case = await _case_for_actor(session, actor, case_id, lock=True)
    if payload.text_extract is None and payload.source_url is None:
        api_error(
            422, "employment_evidence_empty", "Evidence text or a public source URL is required"
        )
    evidence = EmploymentEvidence(
        employment_id=case.id,
        evidence_type=payload.evidence_type,
        text_extract=payload.text_extract,
        source_url=payload.source_url,
        source_date=payload.source_date,
        uploaded_by_user_id=actor.id,
        collected_at=datetime.now(UTC),
        checksum_sha256=(
            hashlib.sha256(payload.text_extract.encode()).hexdigest()
            if payload.text_extract
            else hashlib.sha256(str(payload.source_url).encode()).hexdigest()
        ),
    )
    session.add(evidence)
    case.lock_version += 1
    await session.commit()
    return await case_read(session, case)


async def authorize_case_access(
    session: AsyncSession,
    actor: User,
    case_id: UUID,
    *,
    expected_student_id: UUID | None = None,
) -> StudentEmployment:
    case = await _case_for_actor(session, actor, case_id)
    if expected_student_id is not None and case.student_id != expected_student_id:
        # Return the same result as for an unknown case so a mismatched nested URL
        # cannot be used to probe whether another student's case exists.
        api_error(404, "employment_case_not_found", "Employment case was not found")
    return case


async def add_file_evidence(
    session: AsyncSession,
    actor: User,
    case_id: UUID,
    evidence_type: EmploymentEvidenceType,
    upload: StoredUpload,
    checksum_sha256: str,
) -> EmploymentCaseRead:
    case = await _case_for_actor(session, actor, case_id, lock=True)
    evidence = EmploymentEvidence(
        employment_id=case.id,
        evidence_type=evidence_type,
        storage_key=upload.storage_key,
        filename=upload.filename,
        content_type=upload.content_type,
        size=upload.size,
        checksum_sha256=checksum_sha256,
        uploaded_by_user_id=actor.id,
        collected_at=datetime.now(UTC),
    )
    session.add(evidence)
    case.lock_version += 1
    await session.commit()
    return await case_read(session, case)


async def evidence_file_for_actor(
    session: AsyncSession,
    actor: User,
    case_id: UUID,
    evidence_id: UUID,
) -> StoredUpload:
    case = await _case_for_actor(session, actor, case_id)
    evidence = await session.scalar(
        select(EmploymentEvidence).where(
            EmploymentEvidence.id == evidence_id,
            EmploymentEvidence.employment_id == case.id,
            EmploymentEvidence.storage_key.is_not(None),
        )
    )
    if evidence is None or not evidence.storage_key:
        api_error(404, "employment_evidence_file_not_found", "Evidence file was not found")
    return StoredUpload(
        storage_key=evidence.storage_key,
        filename=evidence.filename or "evidence",
        content_type=evidence.content_type or "application/octet-stream",
        size=evidence.size or 0,
    )


async def request_ai_suggestion(
    session: AsyncSession,
    actor: User,
    case_id: UUID,
    payload: EmploymentAIRequest,
) -> EmploymentAISuggestion:
    _require_staff(actor)
    if not settings.employment_qualification_ai_enabled:
        api_error(
            409,
            "employment_ai_disabled",
            "Employment qualification AI is disabled",
        )
    case = await _case_for_actor(session, actor, case_id)
    evidence_ids = await _valid_evidence_ids(session, case.id, payload.evidence_ids)
    existing = await session.scalar(
        select(EmploymentAISuggestion).where(
            EmploymentAISuggestion.idempotency_key == payload.idempotency_key
        )
    )
    if existing is not None:
        if existing.employment_id != case.id:
            api_error(409, "idempotency_key_reused", "Idempotency key was already used")
        return existing
    suggestion = EmploymentAISuggestion(
        employment_id=case.id,
        status=EmploymentAISuggestionStatus.QUEUED,
        provider=settings.interview_ai_provider,
        model=settings.openai_analysis_model or "configured-analysis-model",
        prompt_version=EMPLOYMENT_PROFILE_PROMPT_VERSION,
        evidence_ids=[str(item) for item in evidence_ids],
        requested_by_user_id=actor.id,
        idempotency_key=payload.idempotency_key,
        correlation_id=payload.idempotency_key,
    )
    session.add(suggestion)
    await session.commit()
    await session.refresh(suggestion)
    return suggestion


async def _valid_evidence_ids(session: AsyncSession, case_id: UUID, ids: list[UUID]) -> list[UUID]:
    if not ids:
        return []
    found = list(
        await session.scalars(
            select(EmploymentEvidence.id).where(
                EmploymentEvidence.employment_id == case_id,
                EmploymentEvidence.id.in_(ids),
            )
        )
    )
    if set(found) != set(ids):
        api_error(
            422,
            "employment_evidence_invalid",
            "One or more evidence items do not belong to this case",
        )
    return found


async def _create_followup(
    session: AsyncSession,
    case: StudentEmployment,
    kind: EmploymentFollowUpType,
    due_at: date,
    fields: list[str],
    key: str,
) -> None:
    await session.execute(
        insert(EmploymentFollowUp)
        .values(
            employment_id=case.id,
            followup_type=kind,
            status=EmploymentFollowUpStatus.OPEN,
            due_at=due_at,
            requested_fields=fields,
            idempotency_key=key,
        )
        .on_conflict_do_nothing(index_elements=[EmploymentFollowUp.idempotency_key])
    )


async def _answer_open_followups(session: AsyncSession, case_id: UUID) -> None:
    items = list(
        await session.scalars(
            select(EmploymentFollowUp).where(
                EmploymentFollowUp.employment_id == case_id,
                EmploymentFollowUp.status == EmploymentFollowUpStatus.OPEN,
            )
        )
    )
    now = datetime.now(UTC)
    for item in items:
        item.status = EmploymentFollowUpStatus.ANSWERED
        item.answered_at = now


async def _cancel_open_followups(session: AsyncSession, case_id: UUID) -> None:
    items = list(
        await session.scalars(
            select(EmploymentFollowUp).where(
                EmploymentFollowUp.employment_id == case_id,
                EmploymentFollowUp.status == EmploymentFollowUpStatus.OPEN,
            )
        )
    )
    for item in items:
        item.status = EmploymentFollowUpStatus.CANCELLED


def _assessment_notification(
    case: StudentEmployment,
    assessment: EmploymentProfileAssessment,
    window: EmploymentQualificationWindow,
) -> str:
    title = case.official_job_title or case.vacancy_title or "должность не указана"
    if assessment.classification in PROFILE_CLASSIFICATIONS:
        criteria = ", ".join(
            str(item.get("criterion", "")) for item in assessment.qualifying_criteria
        )
        return (
            f"Работа в {case.company_name} ({title}) признана профильной по направлению "
            f"{assessment.direction_language} с "
            f"{assessment.effective_profile_started_at:%d.%m.%Y}. "
            f"Критерии: {criteria}. Окно: {window.classification.value}. Решение можно оспорить."
        )
    if assessment.classification is ProfileAssessmentClassification.NON_PROFILE:
        return (
            f"Работа в {case.company_name} зафиксирована, но сейчас не признана профильной. "
            "Начисление не создано. Сообщите, если изменятся проект, обязанности или стек."
        )
    return (
        "Для решения по фактической работе не хватает данных. Проверьте открытый запрос сведений."
    )


async def list_cases(
    session: AsyncSession, actor: User, student_id: UUID | None = None
) -> EmploymentCaseList:
    owner_id = actor.id if actor.role is UserRole.STUDENT else student_id
    if owner_id is None:
        api_error(422, "student_id_required", "Student must be selected")
    if actor.role is not UserRole.STUDENT:
        await assigned_student(session, actor, owner_id)
    cases = list(
        await session.scalars(
            select(StudentEmployment)
            .where(StudentEmployment.student_id == owner_id)
            .order_by(StudentEmployment.created_at.desc())
        )
    )
    return EmploymentCaseList(
        items=[await case_read(session, item) for item in cases], total=len(cases)
    )


async def student_track_options(
    session: AsyncSession, student: User
) -> list[EmploymentTrackOption]:
    rows = (
        await session.execute(
            select(LearningTrack.id, LearningTrack.slug, LearningTrack.title)
            .join(
                LearningTrackEnrollment,
                LearningTrackEnrollment.track_id == LearningTrack.id,
            )
            .where(
                LearningTrackEnrollment.user_id == student.id,
                func.lower(LearningTrack.slug).in_(["python", "go"]),
            )
            .order_by(LearningTrack.position, LearningTrack.title)
        )
    ).all()
    return [EmploymentTrackOption(id=item.id, slug=item.slug, title=item.title) for item in rows]


async def employment_qualification_metrics(
    session: AsyncSession, admin: User
) -> EmploymentQualificationMetrics:
    if admin.role is not UserRole.ADMIN:
        api_error(403, "employment_metrics_forbidden", "Administrator access is required")

    assessment_rows = (
        await session.execute(
            select(EmploymentProfileAssessment.classification, func.count()).group_by(
                EmploymentProfileAssessment.classification
            )
        )
    ).all()
    window_rows = (
        await session.execute(
            select(EmploymentQualificationWindow.classification, func.count()).group_by(
                EmploymentQualificationWindow.classification
            )
        )
    ).all()
    review_duration = await session.scalar(
        select(
            func.avg(
                func.extract(
                    "epoch",
                    EmploymentProfileAssessment.reviewed_at - StudentEmployment.created_at,
                )
            )
        ).join(
            StudentEmployment,
            StudentEmployment.id == EmploymentProfileAssessment.employment_id,
        )
    )
    return EmploymentQualificationMetrics(
        employment_cases_reported_total=int(
            await session.scalar(
                select(func.count(StudentEmployment.id)).where(
                    StudentEmployment.case_status.is_not(None)
                )
            )
            or 0
        ),
        actual_duties_requests_total=int(
            await session.scalar(
                select(func.count(EmploymentEvent.id)).where(
                    EmploymentEvent.event_type == EmploymentEventType.ACTUAL_DUTIES_REQUESTED
                )
            )
            or 0
        ),
        profile_assessments_total={item.value: int(count) for item, count in assessment_rows},
        profile_assessment_review_duration_seconds=(
            float(review_duration) if review_duration is not None else None
        ),
        profile_activity_late_start_total=int(
            await session.scalar(
                select(func.count(StudentEmployment.id)).where(
                    StudentEmployment.profile_activity_started_at.is_not(None),
                    StudentEmployment.start_date.is_not(None),
                    StudentEmployment.profile_activity_started_at > StudentEmployment.start_date,
                )
            )
            or 0
        ),
        employment_stack_changes_total=int(
            await session.scalar(
                select(func.count(EmploymentEvent.id)).where(
                    EmploymentEvent.event_type == EmploymentEventType.STACK_CONFIRMED
                )
            )
            or 0
        ),
        qualification_window_results_total={item.value: int(count) for item, count in window_rows},
        billing_events_from_profile_activity_total=int(
            await session.scalar(select(func.count(EmploymentBillingEvent.id))) or 0
        ),
        profile_disputes_total=int(
            await session.scalar(select(func.count(EmploymentDispute.id))) or 0
        ),
        open_profile_reviews=int(
            await session.scalar(
                select(func.count(StudentEmployment.id)).where(
                    StudentEmployment.case_status == EmploymentCaseStatus.AWAITING_STAFF_REVIEW
                )
            )
            or 0
        ),
        overdue_actual_duties_requests=int(
            await session.scalar(
                select(func.count(EmploymentFollowUp.id)).where(
                    EmploymentFollowUp.followup_type == EmploymentFollowUpType.ACTUAL_DUTIES,
                    EmploymentFollowUp.status == EmploymentFollowUpStatus.OPEN,
                    EmploymentFollowUp.due_at < date.today(),
                )
            )
            or 0
        ),
    )


async def case_read(session: AsyncSession, case: StudentEmployment) -> EmploymentCaseRead:
    # Server-side updated_at/on-update values may be expired after commit even when the
    # AsyncSession itself uses expire_on_commit=False. Refresh explicitly so response
    # serialization never performs implicit async IO through a synchronous attribute getter.
    await session.refresh(case)
    events = list(
        await session.scalars(
            select(EmploymentEvent)
            .where(EmploymentEvent.employment_id == case.id)
            .order_by(EmploymentEvent.effective_at, EmploymentEvent.recorded_at)
        )
    )
    usages = list(
        await session.scalars(
            select(EmploymentTechnologyUsage)
            .where(EmploymentTechnologyUsage.employment_id == case.id)
            .order_by(EmploymentTechnologyUsage.created_at)
        )
    )
    assessments = list(
        await session.scalars(
            select(EmploymentProfileAssessment)
            .where(EmploymentProfileAssessment.employment_id == case.id)
            .order_by(EmploymentProfileAssessment.created_at)
        )
    )
    evidence = list(
        await session.scalars(
            select(EmploymentEvidence)
            .where(EmploymentEvidence.employment_id == case.id)
            .order_by(EmploymentEvidence.created_at)
        )
    )
    followups = list(
        await session.scalars(
            select(EmploymentFollowUp)
            .where(EmploymentFollowUp.employment_id == case.id)
            .order_by(EmploymentFollowUp.due_at)
        )
    )
    disputes = list(
        await session.scalars(
            select(EmploymentDispute)
            .where(EmploymentDispute.employment_id == case.id)
            .order_by(EmploymentDispute.created_at.desc())
        )
    )
    ai_suggestions = list(
        await session.scalars(
            select(EmploymentAISuggestion)
            .where(EmploymentAISuggestion.employment_id == case.id)
            .order_by(EmploymentAISuggestion.created_at.desc())
        )
    )
    current_window = None
    if case.current_assessment_id:
        current_window = await session.scalar(
            select(EmploymentQualificationWindow).where(
                EmploymentQualificationWindow.assessment_id == case.current_assessment_id
            )
        )
    billing = await session.scalar(
        select(EmploymentBillingEvent)
        .where(EmploymentBillingEvent.employment_id == case.id)
        .order_by(EmploymentBillingEvent.created_at.desc())
    )
    policy = (
        await session.get(EmploymentContractPolicySnapshot, case.contract_policy_id)
        if case.contract_policy_id
        else None
    )
    direction = await _direction_for_track(session, case.track_id) if case.track_id else None
    expected = []
    if case.start_date is None:
        expected.append("employment_started_at")
    if not case.actual_duties:
        expected.append("actual_duties")
    if not case.actual_stack:
        expected.append("actual_stack")
    return EmploymentCaseRead(
        id=case.id,
        student_id=case.student_id,
        track_id=case.track_id,
        direction=direction,
        company_name=case.company_name,
        vacancy_title=case.vacancy_title,
        official_job_title=case.official_job_title,
        activity_type=case.activity_type,
        offer_received_at=case.offer_received_at,
        offer_accepted_at=case.offer_accepted_at,
        contract_signed_at=case.contract_signed_at,
        expected_start_date=case.expected_start_date,
        employment_started_at=case.start_date,
        employment_ended_at=case.ended_at,
        vacancy_stack=case.initial_vacancy_stack,
        offer_stack=case.offer_stack,
        actual_stack=case.actual_stack,
        actual_duties=case.actual_duties,
        project_description=case.project_description,
        team_description=case.team_description,
        differences_description=case.differences_description,
        net_salary_kopecks=case.net_salary_kopecks,
        case_status=case.case_status,
        employment_status=case.status,
        profile_activity_started_at=case.profile_activity_started_at,
        profile_activity_ended_at=case.profile_activity_ended_at,
        billing_on_hold=case.billing_on_hold,
        lock_version=case.lock_version,
        policy_version=f"{policy.policy_code}:v{policy.version}" if policy else None,
        policy_is_legacy=policy.is_legacy if policy else True,
        policy_control_period_started_at=(policy.control_period_started_at if policy else None),
        policy_control_period_ended_at=(policy.control_period_ended_at if policy else None),
        policy_extension_ended_at=(policy.extension_ended_at if policy else None),
        events=[EmploymentEventRead.model_validate(item, from_attributes=True) for item in events],
        technology_usages=[
            TechnologyUsageRead.model_validate(item, from_attributes=True) for item in usages
        ],
        assessments=[
            EmploymentAssessmentRead.model_validate(item, from_attributes=True)
            for item in assessments
        ],
        qualification_window=(
            QualificationWindowRead.model_validate(current_window, from_attributes=True)
            if current_window
            else None
        ),
        evidence=[
            EmploymentEvidenceRead.model_validate(item, from_attributes=True) for item in evidence
        ],
        followups=[
            EmploymentFollowUpRead.model_validate(item, from_attributes=True) for item in followups
        ],
        disputes=[
            EmploymentDisputeRead.model_validate(item, from_attributes=True) for item in disputes
        ],
        billing_status=billing.status if billing else None,
        ai_suggestions=[
            EmploymentAISuggestionRead.model_validate(item, from_attributes=True)
            for item in ai_suggestions
        ],
        expected_information=expected,
        created_at=case.created_at,
        updated_at=case.updated_at,
    )
