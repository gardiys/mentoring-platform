from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.opportunities.models import ConsultationStatus, ConsultationType, GoTransitionStatus


class OpportunitySegment(StrEnum):
    ACTIVE_STUDENT = "ACTIVE_STUDENT"
    PYTHON_ALUMNI = "PYTHON_ALUMNI"
    GO_ALUMNI = "GO_ALUMNI"
    MULTI_ALUMNI = "MULTI_ALUMNI"
    OTHER = "OTHER"


class MoneyRead(BaseModel):
    amount_kopecks: int
    currency: str = "RUB"


class MentorOptionRead(BaseModel):
    id: UUID
    first_name: str
    last_name: str | None
    telegram_username: str | None


class ConsultationTypeRead(BaseModel):
    code: ConsultationType
    title: str
    description: str
    price_kopecks: int
    comparison_price_kopecks: int
    mentor_reward_kopecks: int
    duration_minutes: int


class OpportunityRead(BaseModel):
    code: str
    available: bool
    title: str
    unavailable_reason: str | None = None
    price: MoneyRead | None = None
    comparison_price: MoneyRead | None = None
    upfront_price_kopecks: int | None = None
    success_fee_percent: int | None = None
    comparison_upfront_price_kopecks: int | None = None
    comparison_success_fee_percent: int | None = None


class ConsultationCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    mentor_id: UUID | None = None
    consultation_type: ConsultationType
    brief: str = Field(min_length=10, max_length=5000)


class ConsultationRead(BaseModel):
    id: UUID
    mentor: MentorOptionRead | None
    consultation_type: ConsultationType
    brief: str
    price_kopecks: int
    mentor_reward_kopecks: int
    duration_minutes: int
    status: ConsultationStatus
    scheduled_at: datetime | None
    paid_at: datetime | None
    completed_at: datetime | None
    admin_note: str | None
    written_summary: str | None
    created_at: datetime


class GoTransitionCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    motivation: str = Field(min_length=10, max_length=5000)


class GoTransitionRead(BaseModel):
    id: UUID
    motivation: str
    status: GoTransitionStatus
    upfront_price_kopecks: int
    success_fee_percent: int
    approved_at: datetime | None
    terms_accepted_at: datetime | None
    paid_at: datetime | None
    admin_note: str | None
    created_at: datetime


class OpportunitiesDashboard(BaseModel):
    segment: OpportunitySegment
    has_active_program: bool
    has_alumni_access: bool
    opportunities: list[OpportunityRead]
    mentors: list[MentorOptionRead]
    consultation_types: list[ConsultationTypeRead]
    go_transition_description_markdown: str
    consultations: list[ConsultationRead]
    go_transition_applications: list[GoTransitionRead]


class OpportunityPaymentLinkRead(BaseModel):
    payment_url: str
    payment_link_id: str


class AdminConsultationMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    status: ConsultationStatus
    mentor_id: UUID | None = None
    scheduled_at: datetime | None = None
    admin_note: str | None = Field(default=None, max_length=5000)
    written_summary: str | None = Field(default=None, max_length=10000)

    @model_validator(mode="after")
    def scheduled_requires_date(self) -> AdminConsultationMutation:
        if self.status is ConsultationStatus.SCHEDULED and self.scheduled_at is None:
            raise ValueError("Scheduled consultation requires a date")
        if self.status is ConsultationStatus.COMPLETED and (
            not self.written_summary or len(self.written_summary) < 10
        ):
            raise ValueError("Completed consultation requires a written summary")
        return self


class AdminTransitionMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    approved: bool
    admin_note: str | None = Field(default=None, max_length=5000)


class AdminOpportunityStudentRead(BaseModel):
    id: UUID
    first_name: str
    last_name: str | None
    telegram_username: str | None
    email: str | None


class AdminConsultationMentorRead(MentorOptionRead):
    is_enabled: bool


class AdminConsultationMentorMutation(BaseModel):
    is_enabled: bool


class AdminConsultationTypeMutation(BaseModel):
    price_kopecks: int = Field(gt=0)
    comparison_price_kopecks: int = Field(gt=0)
    mentor_reward_kopecks: int = Field(ge=0)
    duration_minutes: int = Field(ge=15, le=480)

    @model_validator(mode="after")
    def validate_prices(self) -> AdminConsultationTypeMutation:
        if self.comparison_price_kopecks < self.price_kopecks:
            raise ValueError("Public price cannot be lower than the alumni price")
        if self.mentor_reward_kopecks > self.price_kopecks:
            raise ValueError("Mentor reward cannot exceed the alumni price")
        return self


class AdminGoTransitionProgramMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    description_markdown: str = Field(min_length=20, max_length=50_000)


class AdminConsultationRead(ConsultationRead):
    student: AdminOpportunityStudentRead


class AdminGoTransitionRead(GoTransitionRead):
    student: AdminOpportunityStudentRead


class AdminOpportunitiesDashboard(BaseModel):
    consultation_types: list[ConsultationTypeRead]
    go_transition_description_markdown: str
    consultation_mentors: list[AdminConsultationMentorRead]
    consultations: list[AdminConsultationRead]
    go_transition_applications: list[AdminGoTransitionRead]
