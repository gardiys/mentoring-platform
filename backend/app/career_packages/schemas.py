from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.career_packages.models import (
    CareerDeliveryChannel,
    CareerDeliveryPurpose,
    CareerDeliveryStatus,
    CareerGenerationComponent,
    CareerGenerationStatus,
    CareerObjectionComponent,
    CareerObjectionStatus,
    CareerObligationStatus,
    CareerPackageStatus,
)

ShortText = Annotated[str, Field(min_length=1, max_length=1_000)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CareerMissingData(StrictModel):
    field: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=500)
    blocking: bool = True


class CareerWarning(StrictModel):
    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=1_000)
    staff_only: bool = False


class CareerSourceSummary(StrictModel):
    """Closed structured-output schema accepted by OpenAI Responses API."""

    used_sources: list[str] = Field(default_factory=list, max_length=20)


class SelfPresentationCard(StrictModel):
    target_position: str = Field(min_length=1, max_length=240)
    target_seniority: str = Field(min_length=1, max_length=100)
    short_positioning: str = Field(min_length=1, max_length=2_000)
    self_presentation_structure: list[ShortText] = Field(min_length=1, max_length=20)
    key_experience_points: list[ShortText] = Field(default_factory=list, max_length=30)
    key_projects: list[ShortText] = Field(default_factory=list, max_length=30)
    achievements_to_highlight: list[ShortText] = Field(default_factory=list, max_length=30)
    technologies_to_highlight: list[ShortText] = Field(default_factory=list, max_length=50)
    personal_contribution_points: list[ShortText] = Field(default_factory=list, max_length=30)
    difficult_or_risky_topics: list[ShortText] = Field(default_factory=list, max_length=30)
    questions_to_prepare: list[ShortText] = Field(default_factory=list, max_length=50)
    inconsistencies_or_missing_facts: list[ShortText] = Field(default_factory=list, max_length=30)
    preparation_checklist: list[ShortText] = Field(min_length=1, max_length=50)
    additional_notes: str | None = Field(default=None, max_length=10_000)


class ActiveSearchParameters(StrictModel):
    target_positions: list[ShortText] = Field(min_length=1, max_length=10)
    target_seniority: str = Field(min_length=1, max_length=100)
    primary_technology_stack: list[ShortText] = Field(min_length=1, max_length=30)
    secondary_technology_stack: list[ShortText] = Field(default_factory=list, max_length=30)
    employment_formats: list[ShortText] = Field(min_length=1, max_length=10)
    work_schedule_preferences: list[ShortText] = Field(default_factory=list, max_length=10)
    geography: list[ShortText] = Field(min_length=1, max_length=20)
    remote_preferences: str = Field(min_length=1, max_length=500)
    relocation_preferences: str = Field(min_length=1, max_length=500)
    salary_min: int = Field(ge=0, le=100_000_000)
    salary_target: int = Field(ge=0, le=100_000_000)
    salary_currency: Literal["RUB", "USD", "EUR"]
    search_channels: list[ShortText] = Field(min_length=1, max_length=30)
    applications_per_workday: int = Field(ge=0, le=500)
    applications_per_week: int = Field(ge=1, le=2_000)
    resume_refresh_schedule: str = Field(min_length=1, max_length=1_000)
    inbound_processing_rules: list[ShortText] = Field(min_length=1, max_length=30)
    interview_logging_rules: list[ShortText] = Field(min_length=1, max_length=30)
    interview_preparation_priorities: list[ShortText] = Field(min_length=1, max_length=30)
    funnel_control_points: list[ShortText] = Field(min_length=1, max_length=30)
    resume_revision_threshold: str = Field(min_length=1, max_length=1_000)
    strategy_revision_threshold: str = Field(min_length=1, max_length=1_000)
    start_date: date
    additional_notes: str | None = Field(default=None, max_length=10_000)

class CareerPackageAIOutput(StrictModel):
    self_presentation_card: SelfPresentationCard | None = None
    active_search_parameters: ActiveSearchParameters | None = None
    missing_data: list[CareerMissingData] = Field(default_factory=list, max_length=100)
    warnings: list[CareerWarning] = Field(default_factory=list, max_length=100)
    source_summary: CareerSourceSummary = Field(default_factory=CareerSourceSummary)


class CareerSourceData(StrictModel):
    target_positions: list[str] = Field(min_length=1, max_length=10)
    target_seniority: str = Field(min_length=1, max_length=100)
    primary_stack: list[str] = Field(min_length=1, max_length=30)
    employment_formats: list[str] = Field(min_length=1, max_length=10)
    geography: list[str] = Field(min_length=1, max_length=20)
    remote_preferences: str = Field(min_length=1, max_length=500)
    relocation_preferences: str = Field(min_length=1, max_length=500)
    salary_min: int = Field(ge=0, le=100_000_000)
    salary_target: int = Field(ge=0, le=100_000_000)
    salary_currency: Literal["RUB", "USD", "EUR"] = "RUB"
    search_start_date: date
    applications_per_week: int = Field(ge=1, le=2_000)
    preparation_priorities: list[str] = Field(min_length=1, max_length=30)
    mentor_context: str | None = Field(default=None, max_length=10_000)

    @field_validator(
        "target_positions",
        "primary_stack",
        "employment_formats",
        "geography",
        "preparation_priorities",
    )
    @classmethod
    def non_empty_values(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if not normalized:
            raise ValueError("At least one value is required")
        return normalized

    @model_validator(mode="after")
    def validate_salary_range(self) -> CareerSourceData:
        if self.salary_target < self.salary_min:
            raise ValueError("salary_target must not be lower than salary_min")
        return self


class CareerDraftMutation(StrictModel):
    lock_version: int = Field(ge=1)
    source_data: CareerSourceData | None = None
    self_presentation_card: SelfPresentationCard | None = None
    active_search_parameters: ActiveSearchParameters | None = None
    missing_data: list[CareerMissingData] | None = None
    warnings: list[CareerWarning] | None = None

    @model_validator(mode="after")
    def validate_generated_salary_range(self) -> CareerDraftMutation:
        search = self.active_search_parameters
        if search is not None and search.salary_target < search.salary_min:
            raise ValueError("salary_target must not be lower than salary_min")
        return self


class CareerResumeVersionRead(BaseModel):
    id: UUID
    version_number: int
    filename: str | None
    content_sha256: str
    finalized_at: datetime
    finalized_by_user_id: UUID | None


class CareerPackageCreate(StrictModel):
    track_id: UUID


class CareerTrackOption(BaseModel):
    id: UUID
    slug: str
    title: str


class CareerGenerationRequest(StrictModel):
    component: CareerGenerationComponent = CareerGenerationComponent.ALL


class CareerGenerationRunRead(BaseModel):
    id: UUID
    status: CareerGenerationStatus
    component: CareerGenerationComponent
    provider: str
    model: str
    prompt_version: str
    started_at: datetime | None
    finished_at: datetime | None
    safe_error_message: str | None
    token_usage: dict[str, object] | None
    created_at: datetime


class CareerReadinessRead(BaseModel):
    complete: bool
    missing: list[str]
    blocking_missing_data: list[CareerMissingData]


class CareerDeliveryRead(BaseModel):
    id: UUID
    channel: CareerDeliveryChannel
    status: CareerDeliveryStatus
    purpose: CareerDeliveryPurpose
    attempted_at: datetime
    delivered_at: datetime | None
    safe_error_message: str | None


class CareerObligationRead(BaseModel):
    id: UUID
    amount_kopecks: int
    currency: str
    due_at: datetime | None
    status: CareerObligationStatus
    offer_accepted_on: date | None
    accrued_at: datetime | None
    recorded_at: datetime | None
    recorded_by_user_id: UUID | None
    record_comment: str | None
    notice_sent_at: datetime | None


class CareerObligationCreate(StrictModel):
    offer_accepted_on: date
    record_comment: str | None = Field(default=None, max_length=1000)
    eligibility_confirmed: Literal[True]


class CareerObligationNoticeCreate(StrictModel):
    delivery_confirmed: Literal[True]


class CareerVersionRead(BaseModel):
    id: UUID
    version_number: int
    snapshot: dict[str, object]
    snapshot_sha256: str
    pdf_sha256: str
    published_at: datetime
    provided_at: datetime | None
    objection_deadline_at: datetime | None
    payment_due_at: datetime | None


class CareerObjectionCreate(StrictModel):
    package_version_id: UUID
    component: CareerObjectionComponent
    reason: str = Field(min_length=10, max_length=20_000)
    expected_result: str = Field(min_length=3, max_length=20_000)


class CareerObjectionResolution(StrictModel):
    status: Literal["accepted", "partially_accepted", "rejected", "resolved"]
    resolution_comment: str = Field(min_length=3, max_length=20_000)
    create_revision: bool = False


class CareerObjectionRead(BaseModel):
    id: UUID
    package_version_id: UUID
    component: CareerObjectionComponent
    reason: str
    expected_result: str
    submitted_at: datetime
    deadline_at: datetime | None
    is_late: bool
    status: CareerObjectionStatus
    resolution_comment: str | None
    resolved_at: datetime | None


class CareerReviewMutation(StrictModel):
    held_at: datetime
    strengths: str = Field(min_length=1, max_length=20_000)
    improvements: str = Field(min_length=1, max_length=20_000)
    preparation_for_next_attempt: str = Field(min_length=1, max_length=20_000)
    additional_notes: str | None = Field(default=None, max_length=20_000)
    send_to_student: bool = True
    create_draft_from_review: bool = False


class CareerReviewRead(BaseModel):
    id: UUID
    held_at: datetime
    reviewer_id: UUID | None
    strengths: str
    improvements: str
    preparation_for_next_attempt: str
    additional_notes: str | None
    sent_to_student_at: datetime | None
    created_at: datetime


class CareerEventRead(BaseModel):
    id: UUID
    event_type: str
    actor_role: str | None
    version_id: UUID | None
    metadata: dict[str, object]
    created_at: datetime


class CareerPackageRead(BaseModel):
    id: UUID
    student_id: UUID
    track_id: UUID
    direction: str
    status: CareerPackageStatus
    lock_version: int
    source_resume_version: CareerResumeVersionRead | None
    source_data: CareerSourceData | None
    self_presentation_card: SelfPresentationCard | None
    active_search_parameters: ActiveSearchParameters | None
    missing_data: list[CareerMissingData]
    warnings: list[CareerWarning]
    is_stale: bool
    readiness: CareerReadinessRead
    generation_runs: list[CareerGenerationRunRead]
    versions: list[CareerVersionRead]
    deliveries: list[CareerDeliveryRead]
    obligation: CareerObligationRead | None
    objections: list[CareerObjectionRead]
    reviews: list[CareerReviewRead]
    audit_timeline: list[CareerEventRead] | None = None
    created_at: datetime
    updated_at: datetime


class CareerStudentPackageRead(BaseModel):
    id: UUID
    direction: str
    status: CareerPackageStatus
    current_version: CareerVersionRead
    versions: list[CareerVersionRead]
    obligation: CareerObligationRead | None
    objections: list[CareerObjectionRead]
    reviews: list[CareerReviewRead]


class CareerAcknowledgeRead(BaseModel):
    acknowledged_at: datetime
