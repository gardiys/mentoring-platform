from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EmploymentDirection(StrEnum):
    PYTHON = "python"
    GO = "go"


class EmploymentEventType(StrEnum):
    OFFER_RECEIVED = "offer_received"
    OFFER_ACCEPTED = "offer_accepted"
    CONTRACT_SIGNED = "contract_signed"
    EMPLOYMENT_STARTED = "employment_started"
    ACTUAL_DUTIES_REQUESTED = "actual_duties_requested"
    ACTUAL_DUTIES_REPORTED = "actual_duties_reported"
    PROJECT_ASSIGNED = "project_assigned"
    STACK_CONFIRMED = "stack_confirmed"
    JOB_TITLE_CHANGED = "job_title_changed"
    TEAM_CHANGED = "team_changed"
    PROJECT_CHANGED = "project_changed"
    DUTIES_CHANGED = "duties_changed"
    PROFILE_ACTIVITY_STARTED = "profile_activity_started"
    PROFILE_ACTIVITY_CONFIRMED = "profile_activity_confirmed"
    PROFILE_ACTIVITY_ENDED = "profile_activity_ended"
    EMPLOYMENT_ENDED = "employment_ended"
    ASSESSMENT_CHANGED = "assessment_changed"
    DISPUTE_OPENED = "dispute_opened"
    DISPUTE_RESOLVED = "dispute_resolved"


class EmploymentEventSource(StrEnum):
    STUDENT = "student"
    STAFF = "staff"
    SYSTEM = "system"


class TechnologyUsageType(StrEnum):
    CODING = "coding"
    REFACTORING = "refactoring"
    TESTING = "testing"
    CODE_REVIEW = "code_review"
    ARCHITECTURE = "architecture"
    MAINTENANCE = "maintenance"
    OPERATIONS = "operations"
    AUTOMATION = "automation"
    DATA_PROCESSING = "data_processing"
    TECHNICAL_LEADERSHIP = "technical_leadership"
    OTHER = "other"


class TechnologyUsageFrequency(StrEnum):
    ONE_TIME = "one_time"
    OCCASIONAL = "occasional"
    REGULAR = "regular"
    PRIMARY = "primary"


class TriState(StrEnum):
    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


class ProfileAssessmentClassification(StrEnum):
    PROFILE = "profile"
    MIXED_PROFILE = "mixed_profile"
    NON_PROFILE = "non_profile"
    INSUFFICIENT_DATA = "insufficient_data"
    DISPUTED = "disputed"


class QualificationWindowClassification(StrEnum):
    WITHIN_MAIN_PERIOD = "within_main_period"
    WITHIN_CONTROL_PERIOD = "within_control_period"
    WITHIN_SPECIFIC_PROCESS_EXTENSION = "within_specific_process_extension"
    OUTSIDE_BILLABLE_WINDOW = "outside_billable_window"
    INSUFFICIENT_DATA = "insufficient_data"


class EmploymentEvidenceType(StrEnum):
    VACANCY = "vacancy"
    OFFER = "offer"
    CONTRACT_EXCERPT = "contract_excerpt"
    JOB_DESCRIPTION = "job_description"
    EMPLOYER_MESSAGE = "employer_message"
    MANAGER_MESSAGE = "manager_message"
    PROJECT_ASSIGNMENT = "project_assignment"
    ROLE_CHANGE = "role_change"
    PAYSLIP = "payslip"
    STATUS_REPORT = "status_report"
    STUDENT_STATEMENT = "student_statement"
    PUBLIC_PROFILE_SNAPSHOT = "public_profile_snapshot"
    PUBLIC_POST = "public_post"
    MEETING_NOTE = "meeting_note"
    OTHER = "other"


class EvidenceVerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    REJECTED = "rejected"


class EmploymentDisputeStatus(StrEnum):
    OPEN = "open"
    UNDER_REVIEW = "under_review"
    RESOLVED = "resolved"
    REJECTED = "rejected"


class EmploymentFollowUpType(StrEnum):
    ACTUAL_DUTIES = "actual_duties"
    MONTHLY_CHANGE_CHECK = "monthly_change_check"
    ADDITIONAL_INFORMATION = "additional_information"


class EmploymentFollowUpStatus(StrEnum):
    OPEN = "open"
    ANSWERED = "answered"
    CANCELLED = "cancelled"


class EmploymentBillingEventStatus(StrEnum):
    AWAITING_COMPENSATION = "awaiting_compensation"
    PROCESSED = "processed"
    HOLD = "hold"
    NOT_APPLICABLE = "not_applicable"


class EmploymentAISuggestionStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EmploymentContractPolicySnapshot(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "employment_contract_policy_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "track_id",
            "policy_code",
            "version",
            name="uq_employment_policy_student_track_version",
        ),
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint(
            "control_period_ended_at >= control_period_started_at",
            name="control_period_ordered",
        ),
        Index("ix_employment_policy_student_track", "student_id", "track_id", "accepted_at"),
    )

    student_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    track_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("learning_tracks.id", ondelete="RESTRICT"), nullable=False
    )
    policy_code: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    direction: Mapped[EmploymentDirection] = mapped_column(
        Enum(
            EmploymentDirection,
            name="employment_direction",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    direction_language: Mapped[str] = mapped_column(String(32), nullable=False)
    control_period_started_at: Mapped[date] = mapped_column(Date, nullable=False)
    control_period_ended_at: Mapped[date] = mapped_column(Date, nullable=False)
    extension_ended_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    rules: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_legacy: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EmploymentEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "employment_events"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_employment_events_idempotency"),
        Index("ix_employment_events_case_effective", "employment_id", "effective_at"),
    )

    employment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("student_employments.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[EmploymentEventType] = mapped_column(
        Enum(
            EmploymentEventType,
            name="employment_event_type",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    effective_at: Mapped[date] = mapped_column(Date, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[EmploymentEventSource] = mapped_column(
        Enum(
            EmploymentEventSource,
            name="employment_event_source",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    correlation_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)


class EmploymentTechnologyUsage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "employment_technology_usages"
    __table_args__ = (
        Index("ix_employment_technology_case_name", "employment_id", "normalized_name"),
    )

    employment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("student_employments.id", ondelete="CASCADE"),
        nullable=False,
    )
    normalized_name: Mapped[str] = mapped_column(String(100), nullable=False)
    usage_type: Mapped[TechnologyUsageType] = mapped_column(
        Enum(
            TechnologyUsageType,
            name="employment_technology_usage_type",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    frequency: Mapped[TechnologyUsageFrequency] = mapped_column(
        Enum(
            TechnologyUsageFrequency,
            name="employment_technology_frequency",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    part_of_official_duties: Mapped[TriState] = mapped_column(
        Enum(
            TriState,
            name="employment_tri_state",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    part_of_project: Mapped[TriState] = mapped_column(
        Enum(
            TriState,
            name="employment_tri_state",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    started_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    ended_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_by_student: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    confirmed_by_staff: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)


class EmploymentProfileAssessment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "employment_profile_assessments"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_employment_assessments_idempotency"),
        Index("ix_employment_assessments_pending", "employment_id", "reviewed_at"),
        Index("ix_employment_assessments_classification", "classification", "created_at"),
    )

    employment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("student_employments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    policy_snapshot_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("employment_contract_policy_snapshots.id", ondelete="RESTRICT"),
        nullable=True,
    )
    track_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("learning_tracks.id", ondelete="RESTRICT"), nullable=False
    )
    direction: Mapped[EmploymentDirection] = mapped_column(
        Enum(
            EmploymentDirection,
            name="employment_direction",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    direction_language: Mapped[str] = mapped_column(String(32), nullable=False)
    classification: Mapped[ProfileAssessmentClassification] = mapped_column(
        Enum(
            ProfileAssessmentClassification,
            name="employment_profile_classification",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    effective_profile_started_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_profile_ended_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    qualifying_criteria: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    non_qualifying_reasons: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    ai_suggestion: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    reviewed_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    supersedes_assessment_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employment_profile_assessments.id", ondelete="RESTRICT")
    )
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EmploymentQualificationWindow(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "employment_qualification_windows"
    __table_args__ = (
        UniqueConstraint("assessment_id", name="uq_employment_windows_assessment"),
        Index("ix_employment_windows_classification", "classification", "evaluated_at"),
    )

    assessment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("employment_profile_assessments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    policy_snapshot_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("employment_contract_policy_snapshots.id", ondelete="RESTRICT"),
        nullable=True,
    )
    control_period_started_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    control_period_ended_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    extension_ended_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    classification: Mapped[QualificationWindowClassification] = mapped_column(
        Enum(
            QualificationWindowClassification,
            name="employment_window_classification",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    linked_offer_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    linked_interview_process_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("interview_processes.id", ondelete="SET NULL"),
        nullable=True,
    )
    evaluation_reason: Mapped[str] = mapped_column(Text, nullable=False)
    billing_trigger_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(100), nullable=False)


class EmploymentEvidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "employment_evidence"
    __table_args__ = (
        Index("ix_employment_evidence_case_created", "employment_id", "created_at"),
        UniqueConstraint("storage_key", name="uq_employment_evidence_storage_key"),
    )

    employment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("student_employments.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_type: Mapped[EmploymentEvidenceType] = mapped_column(
        Enum(
            EmploymentEvidenceType,
            name="employment_evidence_type",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    text_extract: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    uploaded_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    access_scope: Mapped[str] = mapped_column(
        String(32), nullable=False, default="case_participants"
    )
    redaction_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    verification_status: Mapped[EvidenceVerificationStatus] = mapped_column(
        Enum(
            EvidenceVerificationStatus,
            name="employment_evidence_verification_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=EvidenceVerificationStatus.UNVERIFIED,
    )


class EmploymentFollowUp(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "employment_followups"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_employment_followups_idempotency"),
        Index("ix_employment_followups_due_status", "due_at", "status"),
    )

    employment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("student_employments.id", ondelete="CASCADE"),
        nullable=False,
    )
    followup_type: Mapped[EmploymentFollowUpType] = mapped_column(
        Enum(
            EmploymentFollowUpType,
            name="employment_followup_type",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    status: Mapped[EmploymentFollowUpStatus] = mapped_column(
        Enum(
            EmploymentFollowUpStatus,
            name="employment_followup_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=EmploymentFollowUpStatus.OPEN,
    )
    due_at: Mapped[date] = mapped_column(Date, nullable=False)
    requested_fields: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)


class EmploymentDispute(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "employment_disputes"
    __table_args__ = (
        Index("ix_employment_disputes_open", "employment_id", "status", "created_at"),
    )

    employment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("student_employments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    assessment_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("employment_profile_assessments.id", ondelete="RESTRICT"),
        nullable=True,
    )
    student_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    disputed_conclusion: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    alternative_started_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_duties: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[EmploymentDisputeStatus] = mapped_column(
        Enum(
            EmploymentDisputeStatus,
            name="employment_dispute_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=EmploymentDisputeStatus.OPEN,
    )
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EmploymentBillingEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "employment_billing_events"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_employment_billing_events_idempotency"),
        UniqueConstraint("assessment_id", name="uq_employment_billing_events_assessment"),
        Index("ix_employment_billing_events_status", "status", "created_at"),
    )

    employment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("student_employments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    assessment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("employment_profile_assessments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    policy_snapshot_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("employment_contract_policy_snapshots.id", ondelete="RESTRICT"),
        nullable=True,
    )
    status: Mapped[EmploymentBillingEventStatus] = mapped_column(
        Enum(
            EmploymentBillingEventStatus,
            name="employment_billing_event_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)


class EmploymentAISuggestion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "employment_ai_suggestions"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_employment_ai_suggestions_idempotency"),
        Index("ix_employment_ai_suggestions_case_created", "employment_id", "created_at"),
    )

    employment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("student_employments.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[EmploymentAISuggestionStatus] = mapped_column(
        Enum(
            EmploymentAISuggestionStatus,
            name="employment_ai_suggestion_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    requested_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    safe_error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
