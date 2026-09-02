from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.opportunities.models import (
    PythonRepeatApplicationStatus,
    PythonRepeatEmploymentStatus,
    PythonRepeatEnrollmentStatus,
    PythonRepeatInstallmentStatus,
    PythonRepeatObligationStatus,
    PythonRepeatOfferStatus,
    PythonRepeatReason,
    PythonRepeatSearchMode,
)


class PythonRepeatEligibilityRead(BaseModel):
    eligible: bool
    code: str
    message: str
    override_allowed: bool = False


class PythonRepeatApplicationCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    employment_status: PythonRepeatEmploymentStatus
    reason: PythonRepeatReason
    current_position: str | None = Field(default=None, max_length=240)
    current_company: str | None = Field(default=None, max_length=240)
    current_stack: str | None = Field(default=None, max_length=5000)
    last_interview_at: datetime | None = None
    target_position: str = Field(min_length=2, max_length=240)
    target_salary_kopecks: int | None = Field(default=None, gt=0)
    technical_gaps: str = Field(min_length=10, max_length=10_000)
    hours_per_week: int = Field(ge=1, le=80)
    desired_start_date: datetime | None = None
    search_mode: PythonRepeatSearchMode
    additional_comment: str | None = Field(default=None, max_length=10_000)

    @field_validator("last_interview_at", "desired_start_date")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("Datetime must include a timezone offset")
        return value


class PythonRepeatStatusHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    old_status: PythonRepeatApplicationStatus | None
    new_status: PythonRepeatApplicationStatus
    actor_user_id: UUID | None
    comment: str | None
    created_at: datetime


class PythonRepeatApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    student_id: UUID
    employment_status: PythonRepeatEmploymentStatus
    reason: PythonRepeatReason
    current_position: str | None
    current_company: str | None
    current_stack: str | None
    last_interview_at: datetime | None
    target_position: str
    target_salary_kopecks: int | None
    technical_gaps: str
    hours_per_week: int
    desired_start_date: datetime | None
    search_mode: PythonRepeatSearchMode
    additional_comment: str | None
    status: PythonRepeatApplicationStatus
    responsible_user_id: UUID | None
    eligibility_override_reason: str | None
    admin_comment: str | None
    terms_version: int | None
    terms_snapshot: dict[str, object] | None
    approved_at: datetime | None
    offer_expires_at: datetime | None
    accepted_at: datetime | None
    acceptance_evidence: dict[str, object] | None
    contract_accepted_at: datetime | None
    acceptance_payment_link_id: str | None
    acceptance_provider_operation_id: str | None
    paid_at: datetime | None
    created_at: datetime
    history: list[PythonRepeatStatusHistoryRead] = []


class PythonRepeatEnrollmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    student_id: UUID
    track_id: UUID
    previous_track_id: UUID
    mentor_id: UUID | None
    mentor_assigned_at: datetime | None
    status: PythonRepeatEnrollmentStatus
    started_at: datetime
    ended_at: datetime | None
    personal_plan_markdown: str | None
    terms_snapshot: dict[str, object]


class PythonRepeatOfferCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    position: str = Field(min_length=2, max_length=240)
    company: str = Field(min_length=2, max_length=240)
    fixed_monthly_salary_kopecks: int = Field(gt=0)
    employment_type: str | None = Field(default=None, max_length=100)
    received_at: datetime
    expected_start_date: datetime

    @field_validator("received_at", "expected_start_date")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("Datetime must include a timezone offset")
        return value

    @model_validator(mode="after")
    def validate_offer_dates(self) -> PythonRepeatOfferCreate:
        if self.expected_start_date < self.received_at:
            raise ValueError("Expected start date cannot precede offer date")
        return self


class PythonRepeatOfferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    enrollment_id: UUID
    student_id: UUID
    position: str
    company: str
    technology_direction: str
    fixed_monthly_salary_kopecks: int
    currency: str
    employment_type: str | None
    received_at: datetime
    expected_start_date: datetime
    status: PythonRepeatOfferStatus
    submitted_at: datetime | None
    verified_at: datetime | None
    verification_comment: str | None
    created_at: datetime


class PythonRepeatInstallmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sequence_number: int
    amount_kopecks: int
    salary_percent: int
    due_at: datetime
    status: PythonRepeatInstallmentStatus
    paid_at: datetime | None
    actual_received_kopecks: int | None
    refunded_at: datetime | None


class PythonRepeatObligationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    enrollment_id: UUID
    verified_offer_id: UUID
    salary_base_kopecks: int
    success_fee_percent: int
    total_amount_kopecks: int
    installments_count: int
    status: PythonRepeatObligationStatus
    terms_snapshot: dict[str, object]
    installments: list[PythonRepeatInstallmentRead] = []


class PythonRepeatDashboard(BaseModel):
    enabled: bool
    eligibility: PythonRepeatEligibilityRead
    product: dict[str, object]
    application: PythonRepeatApplicationRead | None
    enrollment: PythonRepeatEnrollmentRead | None
    offers: list[PythonRepeatOfferRead]
    obligation: PythonRepeatObligationRead | None


class PythonRepeatTermsAcceptance(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    accepted: bool
    terms_version: int = Field(gt=0)
    public_offer_revision: str = Field(min_length=1, max_length=32)
    public_offer_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    acceptance_statement: str = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def require_acceptance(self) -> PythonRepeatTermsAcceptance:
        if not self.accepted:
            raise ValueError("Terms must be accepted explicitly")
        return self


class AdminPythonRepeatTransition(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    status: PythonRepeatApplicationStatus
    comment: str = Field(min_length=3, max_length=5000)
    responsible_user_id: UUID | None = None


class AdminPythonRepeatOverride(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    reason: str = Field(min_length=10, max_length=5000)


class AdminPythonRepeatMentorAssignment(BaseModel):
    mentor_id: UUID


class AdminPythonRepeatOfferDecision(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    verified: bool
    salary_base_kopecks: int | None = Field(default=None, gt=0)
    comment: str = Field(min_length=3, max_length=5000)

    @model_validator(mode="after")
    def require_salary_for_verification(self) -> AdminPythonRepeatOfferDecision:
        if self.verified and self.salary_base_kopecks is None:
            raise ValueError("Verified offer requires salary base")
        return self


class AdminPythonRepeatStudentRead(BaseModel):
    id: UUID
    first_name: str
    last_name: str | None
    telegram_username: str | None
    email: str | None


class AdminPythonRepeatApplicationRead(PythonRepeatApplicationRead):
    student: AdminPythonRepeatStudentRead
    eligibility: PythonRepeatEligibilityRead
    enrollment: PythonRepeatEnrollmentRead | None = None
    offers: list[PythonRepeatOfferRead] = []
    obligation: PythonRepeatObligationRead | None = None
    revenue_received_kopecks: int = 0
    mentor_accrued_kopecks: int = 0
    mentor_paid_kopecks: int = 0
    gross_remainder_kopecks: int = 0


class AdminPythonRepeatDashboard(BaseModel):
    applications: list[AdminPythonRepeatApplicationRead]
    mentors: list[AdminPythonRepeatStudentRead]
