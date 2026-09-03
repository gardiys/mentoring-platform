from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.employment_qualification.models import (
    EmploymentAISuggestionStatus,
    EmploymentBillingEventStatus,
    EmploymentDirection,
    EmploymentDisputeStatus,
    EmploymentEventSource,
    EmploymentEventType,
    EmploymentEvidenceType,
    EmploymentFollowUpStatus,
    EmploymentFollowUpType,
    ProfileAssessmentClassification,
    QualificationWindowClassification,
    TechnologyUsageFrequency,
    TechnologyUsageType,
    TriState,
)
from app.payments.models import (
    EmploymentActivityType,
    EmploymentCaseStatus,
    StudentEmploymentStatus,
)


class TechnologyUsageInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    normalized_name: str = Field(min_length=1, max_length=100)
    usage_type: TechnologyUsageType
    frequency: TechnologyUsageFrequency
    part_of_official_duties: TriState
    part_of_project: TriState
    started_at: date | None = None
    ended_at: date | None = None
    description: str | None = Field(default=None, max_length=2_000)
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=50)


class EmploymentOfferReport(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    track_id: UUID
    employer_name: str = Field(min_length=1, max_length=240)
    employer_id: UUID | None = None
    vacancy_title: str = Field(min_length=1, max_length=240)
    official_job_title: str | None = Field(default=None, max_length=240)
    activity_type: EmploymentActivityType
    offer_received_at: date
    offer_accepted_at: date | None = None
    contract_signed_at: date | None = None
    expected_start_date: date | None = None
    vacancy_stack: list[str] = Field(default_factory=list, max_length=50)
    offer_stack: list[str] = Field(default_factory=list, max_length=50)
    vacancy_duties: str | None = Field(default=None, max_length=10_000)
    net_salary_rubles: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    student_comment: str | None = Field(default=None, max_length=5_000)
    idempotency_key: str = Field(min_length=8, max_length=180)


class EmploymentWorkStartReport(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    employment_started_at: date
    official_job_title: str = Field(min_length=1, max_length=240)
    team_description: str | None = Field(default=None, max_length=2_000)
    project_description: str | None = Field(default=None, max_length=5_000)
    actual_duties: str | None = Field(default=None, max_length=10_000)
    actual_stack: list[str] = Field(default_factory=list, max_length=50)
    differences_description: str | None = Field(default=None, max_length=5_000)
    technology_usages: list[TechnologyUsageInput] = Field(default_factory=list, max_length=50)
    expected_lock_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=180)


class EmploymentOfferStatusReport(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    event: Literal["offer_accepted", "contract_signed"]
    effective_at: date
    expected_lock_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=180)


class EmploymentActualDutiesReport(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    actual_duties: str = Field(min_length=10, max_length=10_000)
    actual_stack: list[str] = Field(default_factory=list, max_length=50)
    team_description: str | None = Field(default=None, max_length=2_000)
    project_description: str | None = Field(default=None, max_length=5_000)
    differences_description: str | None = Field(default=None, max_length=5_000)
    technology_usages: list[TechnologyUsageInput] = Field(default_factory=list, max_length=50)
    expected_lock_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=180)


class EmploymentChangeReport(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    change_type: Literal["job_title", "team", "project", "duties", "stack", "profile_usage"]
    effective_at: date
    previous_state: str | None = Field(default=None, max_length=5_000)
    new_state: str = Field(min_length=1, max_length=10_000)
    description: str | None = Field(default=None, max_length=5_000)
    actual_stack: list[str] | None = Field(default=None, max_length=50)
    technology_usages: list[TechnologyUsageInput] = Field(default_factory=list, max_length=50)
    expected_lock_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=180)


class EmploymentEndReport(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    employment_ended_at: date
    reason: str = Field(min_length=3, max_length=2_000)
    expected_lock_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=180)


class EmploymentAssessmentCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    classification: ProfileAssessmentClassification
    effective_profile_started_at: date | None = None
    effective_profile_ended_at: date | None = None
    rationale: str = Field(min_length=10, max_length=10_000)
    qualifying_criteria: list[dict[str, object]] = Field(default_factory=list, max_length=50)
    non_qualifying_reasons: list[str] = Field(default_factory=list, max_length=50)
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=50)
    expected_lock_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=180)

    @model_validator(mode="after")
    def validate_profile_decision(self) -> EmploymentAssessmentCreate:
        profile = self.classification in {
            ProfileAssessmentClassification.PROFILE,
            ProfileAssessmentClassification.MIXED_PROFILE,
        }
        if profile and self.effective_profile_started_at is None:
            raise ValueError("Profile start date is required for a profile decision")
        if profile and not self.qualifying_criteria:
            raise ValueError("At least one qualifying criterion is required")
        if not profile and self.classification is not ProfileAssessmentClassification.DISPUTED:
            if self.effective_profile_started_at is not None:
                raise ValueError("Non-profile decisions cannot have a profile start date")
        return self


class EmploymentDisputeCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    disputed_conclusion: Literal[
        "profile_activity",
        "start_date",
        "duties",
        "frequency",
        "direction",
        "window",
        "compensation",
    ]
    reason: str = Field(min_length=10, max_length=10_000)
    alternative_started_at: date | None = None
    actual_duties: str | None = Field(default=None, max_length=10_000)
    comment: str | None = Field(default=None, max_length=5_000)
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=50)
    idempotency_key: str = Field(min_length=8, max_length=180)


class EmploymentDisputeResolution(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    resolution: str = Field(min_length=10, max_length=10_000)
    outcome: Literal["resolved", "rejected"]
    replacement_assessment: EmploymentAssessmentCreate | None = None


class EmploymentInformationRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    requested_fields: list[str] = Field(min_length=1, max_length=30)
    due_at: date
    idempotency_key: str = Field(min_length=8, max_length=180)


class EmploymentPolicyCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    track_id: UUID
    policy_code: str = Field(min_length=1, max_length=100)
    version: int = Field(gt=0)
    accepted_at: datetime
    control_period_started_at: date
    control_period_ended_at: date
    extension_ended_at: date | None = None
    rules: dict[str, object]

    @model_validator(mode="after")
    def dates_are_ordered(self) -> EmploymentPolicyCreate:
        if self.control_period_ended_at < self.control_period_started_at:
            raise ValueError("Control period end cannot precede its start")
        if self.extension_ended_at and self.extension_ended_at < self.control_period_ended_at:
            raise ValueError("Extension cannot end before the control period")
        main_period = self.rules.get("main_period_ended_at")
        if main_period is not None:
            try:
                main_period_date = date.fromisoformat(str(main_period))
            except ValueError as error:
                raise ValueError("main_period_ended_at must be an ISO date") from error
            if (
                not self.control_period_started_at
                <= main_period_date
                <= self.control_period_ended_at
            ):
                raise ValueError("Main period must be inside the control period")
        linked_process = self.rules.get("linked_interview_process_id")
        if linked_process is not None:
            try:
                UUID(str(linked_process))
            except ValueError as error:
                raise ValueError("linked_interview_process_id must be a UUID") from error
        return self


class EmploymentPolicyRead(BaseModel):
    id: UUID
    student_id: UUID
    track_id: UUID
    policy_code: str
    version: int
    accepted_at: datetime
    direction: EmploymentDirection
    direction_language: str
    control_period_started_at: date
    control_period_ended_at: date
    extension_ended_at: date | None
    rules: dict[str, object]
    is_legacy: bool


class EmploymentAIRequest(BaseModel):
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=50)
    idempotency_key: str = Field(min_length=8, max_length=180)


class EmploymentEvidenceCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    evidence_type: EmploymentEvidenceType
    text_extract: str | None = Field(default=None, max_length=20_000)
    source_url: str | None = Field(default=None, max_length=1_000)
    source_date: date | None = None

    @field_validator("source_url")
    @classmethod
    def safe_source_url(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith(("https://", "http://")):
            raise ValueError("Source URL must be an absolute HTTP(S) URL")
        return value


class TechnologyUsageRead(BaseModel):
    id: UUID
    normalized_name: str
    usage_type: TechnologyUsageType
    frequency: TechnologyUsageFrequency
    part_of_official_duties: TriState
    part_of_project: TriState
    started_at: date | None
    ended_at: date | None
    description: str | None
    confirmed_by_student: bool
    confirmed_by_staff: bool
    evidence_ids: list[str]


class EmploymentEventRead(BaseModel):
    id: UUID
    event_type: EmploymentEventType
    effective_at: date
    recorded_at: datetime
    source: EmploymentEventSource
    payload: dict[str, object]
    evidence_ids: list[str]


class EmploymentAssessmentRead(BaseModel):
    id: UUID
    classification: ProfileAssessmentClassification
    direction: EmploymentDirection
    direction_language: str
    effective_profile_started_at: date | None
    effective_profile_ended_at: date | None
    rationale: str
    qualifying_criteria: list[dict[str, object]]
    non_qualifying_reasons: list[str]
    evidence_ids: list[str]
    ai_suggestion: dict[str, object] | None
    reviewed_by_user_id: UUID
    reviewed_at: datetime
    supersedes_assessment_id: UUID | None


class QualificationWindowRead(BaseModel):
    classification: QualificationWindowClassification
    control_period_started_at: date | None
    control_period_ended_at: date | None
    extension_ended_at: date | None
    billing_trigger_allowed: bool
    evaluation_reason: str
    policy_version: str


class EmploymentEvidenceRead(BaseModel):
    id: UUID
    evidence_type: EmploymentEvidenceType
    filename: str | None
    content_type: str | None
    size: int | None
    checksum_sha256: str | None
    text_extract: str | None
    source_url: str | None
    source_date: date | None
    collected_at: datetime
    verification_status: str


class EmploymentFollowUpRead(BaseModel):
    id: UUID
    followup_type: EmploymentFollowUpType
    status: EmploymentFollowUpStatus
    due_at: date
    requested_fields: list[str]


class EmploymentDisputeRead(BaseModel):
    id: UUID
    disputed_conclusion: str
    reason: str
    alternative_started_at: date | None
    status: EmploymentDisputeStatus
    resolution: str | None
    created_at: datetime
    resolved_at: datetime | None


class EmploymentCaseRead(BaseModel):
    id: UUID
    student_id: UUID
    track_id: UUID | None
    direction: EmploymentDirection | None
    company_name: str
    vacancy_title: str | None
    official_job_title: str | None
    activity_type: EmploymentActivityType | None
    offer_received_at: date | None
    offer_accepted_at: date | None
    contract_signed_at: date | None
    expected_start_date: date | None
    employment_started_at: date | None
    employment_ended_at: date | None
    vacancy_stack: list[str]
    offer_stack: list[str]
    actual_stack: list[str]
    actual_duties: str | None
    project_description: str | None
    team_description: str | None
    differences_description: str | None
    net_salary_kopecks: int | None
    case_status: EmploymentCaseStatus | None
    employment_status: StudentEmploymentStatus
    profile_activity_started_at: date | None
    profile_activity_ended_at: date | None
    billing_on_hold: bool
    lock_version: int
    policy_version: str | None
    policy_is_legacy: bool
    policy_control_period_started_at: date | None
    policy_control_period_ended_at: date | None
    policy_extension_ended_at: date | None
    events: list[EmploymentEventRead]
    technology_usages: list[TechnologyUsageRead]
    assessments: list[EmploymentAssessmentRead]
    qualification_window: QualificationWindowRead | None
    evidence: list[EmploymentEvidenceRead]
    followups: list[EmploymentFollowUpRead]
    disputes: list[EmploymentDisputeRead]
    billing_status: EmploymentBillingEventStatus | None
    ai_suggestions: list[EmploymentAISuggestionRead]
    expected_information: list[str]
    created_at: datetime
    updated_at: datetime


class EmploymentCaseList(BaseModel):
    items: list[EmploymentCaseRead]
    total: int


class EmploymentQualificationMetrics(BaseModel):
    employment_cases_reported_total: int
    actual_duties_requests_total: int
    profile_assessments_total: dict[str, int]
    profile_assessment_review_duration_seconds: float | None
    profile_activity_late_start_total: int
    employment_stack_changes_total: int
    qualification_window_results_total: dict[str, int]
    billing_events_from_profile_activity_total: int
    profile_disputes_total: int
    open_profile_reviews: int
    overdue_actual_duties_requests: int


class EmploymentTrackOption(BaseModel):
    id: UUID
    slug: str
    title: str


class EmploymentAIQualifyingCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion: TechnologyUsageType
    technology: Literal["Python", "Go"]
    evidence_ids: list[UUID]
    reason: str = Field(min_length=1, max_length=2_000)


class EmploymentAINonQualifyingSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[
        "one_time_usage", "personal_script", "employer_stack_only", "vacancy_only", "other"
    ]
    reason: str = Field(min_length=1, max_length=2_000)
    evidence_ids: list[UUID]


class EmploymentAIContradiction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str = Field(min_length=1, max_length=100)
    values: list[str] = Field(min_length=2, max_length=10)
    evidence_ids: list[UUID]


class EmploymentAIMissingData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1, max_length=2_000)


class EmploymentAIOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggested_classification: Literal[
        "profile", "mixed_profile", "non_profile", "insufficient_data"
    ]
    suggested_profile_started_at: date | None
    qualifying_criteria: list[EmploymentAIQualifyingCriterion]
    non_qualifying_signals: list[EmploymentAINonQualifyingSignal]
    contradictions: list[EmploymentAIContradiction]
    missing_data: list[EmploymentAIMissingData]
    confidence: float = Field(ge=0, le=1)
    summary: str = Field(min_length=1, max_length=5_000)


class EmploymentAISuggestionRead(BaseModel):
    id: UUID
    status: EmploymentAISuggestionStatus
    provider: str
    model: str
    prompt_version: str
    output: EmploymentAIOutput | None
    evidence_ids: list[str]
    started_at: datetime | None
    finished_at: datetime | None
    safe_error_message: str | None
    created_at: datetime


EmploymentCaseRead.model_rebuild()
