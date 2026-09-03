from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.payments.models import (
    MentorPayoutOrigin,
    MentorPayoutStatus,
    MentorRewardKind,
    PaymentAttemptStatus,
    PaymentInstallmentStatus,
    StudentEmploymentStatus,
)


class AdminEmploymentPaymentStatus(StrEnum):
    OUTSTANDING = "outstanding"
    PAID = "paid"
    ALL = "all"


class AdminTochkaTestPaymentCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: str = Field(min_length=5, max_length=320)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        local, separator, domain = value.rpartition("@")
        if not separator or not local or "." not in domain or domain.startswith("."):
            raise ValueError("A valid email is required for the fiscal receipt")
        return value


class AdminTochkaTestPaymentRead(BaseModel):
    id: UUID
    amount_kopecks: int
    status: PaymentAttemptStatus
    payment_url: str | None
    provider_operation_id: str | None
    approved_at: datetime | None
    created_at: datetime


class EmploymentMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    company_name: str = Field(min_length=1, max_length=240)
    company_id: UUID | None = None
    start_date: date
    net_salary_rubles: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class EmploymentTerminationMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    ended_at: date
    reason: str | None = Field(default=None, max_length=500)


class PaymentDaysMutation(BaseModel):
    payment_days: list[int] = Field(min_length=2, max_length=2)

    @field_validator("payment_days")
    @classmethod
    def valid_payment_days(cls, value: list[int]) -> list[int]:
        normalized = sorted(value)
        if len(set(normalized)) != 2:
            raise ValueError("Payment days must be different")
        if normalized[0] < 1 or normalized[1] > 28:
            raise ValueError("Payment days must be between 1 and 28")
        return normalized


class PaymentRevocationMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    reason: str = Field(min_length=3, max_length=500)


class PaymentDueDateMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    due_date: date
    reason: str = Field(min_length=3, max_length=500)


class EmploymentRead(BaseModel):
    id: UUID
    company_id: UUID | None
    company_name: str
    start_date: date | None
    net_salary_kopecks: int | None
    repayment_percent: Decimal
    status: StudentEmploymentStatus
    ended_at: date | None
    end_reason: str | None
    payment_days: list[int]
    total_owed_kopecks: int
    created_at: datetime
    updated_at: datetime


class PaymentInstallmentRead(BaseModel):
    id: UUID
    sequence_number: int
    due_date: date
    amount_kopecks: int
    salary_percent: Decimal
    employment_id: UUID
    company_name: str
    status: PaymentInstallmentStatus
    paid_at: datetime | None
    revoked_at: datetime | None
    revocation_reason: str | None
    due_date_changed_at: datetime | None = None
    previous_due_date: date | None = None
    due_date_change_reason: str | None = None
    payment_url: str | None = None
    can_pay: bool = False


class PaymentSummaryRead(BaseModel):
    total_owed_kopecks: int
    paid_kopecks: int
    remaining_kopecks: int
    overdue_kopecks: int
    paid_installments: int
    total_installments: int
    paid_salary_percent: Decimal
    remaining_salary_percent: Decimal


class StudentPaymentDashboard(BaseModel):
    student_id: UUID
    student_name: str
    repayment_percent: Decimal
    mentor_reward_percent: Decimal | None
    employment: EmploymentRead | None
    employment_history: list[EmploymentRead]
    installments: list[PaymentInstallmentRead]
    summary: PaymentSummaryRead
    can_manage_employment: bool = False
    can_manage_payment_days: bool = False


class PaymentLinkRead(BaseModel):
    installment_id: UUID
    payment_url: str
    expires_in: int | None = None


class AdminPaymentListItem(BaseModel):
    installment_id: UUID
    student_id: UUID
    student_name: str
    student_telegram_username: str | None
    mentor_id: UUID | None
    mentor_name: str | None
    company_name: str
    due_date: date
    amount_kopecks: int
    status: PaymentInstallmentStatus
    paid_at: datetime | None
    mentor_reward_kopecks: int | None
    mentor_reward_id: UUID | None
    mentor_reward_paid_at: datetime | None
    requires_manual_review: bool = False


class AdminPaymentStudentRead(BaseModel):
    employment_id: UUID
    student_id: UUID
    student_name: str
    student_telegram_username: str | None
    mentor_id: UUID | None
    mentor_name: str | None
    company_name: str
    employment_start_date: date
    net_salary_kopecks: int
    repayment_percent: Decimal
    total_owed_kopecks: int
    paid_kopecks: int
    remaining_kopecks: int
    overdue_kopecks: int
    overdue_payments: int
    next_payment_date: date | None
    paid_installments: int
    total_installments: int


class AdminPaymentStudentPage(BaseModel):
    items: list[AdminPaymentStudentRead]
    total: int
    limit: int
    offset: int
    total_remaining_kopecks: int
    total_paid_kopecks: int
    total_overdue_kopecks: int


class MentorRewardRead(BaseModel):
    id: UUID
    kind: MentorRewardKind
    mentor_id: UUID
    mentor_name: str
    mentor_telegram_username: str | None
    student_id: UUID
    student_name: str
    student_telegram_username: str | None
    company_name: str | None
    basis_kopecks: int | None
    reward_percent: Decimal | None
    amount_kopecks: int
    paid_kopecks: int
    reserved_kopecks: int
    available_kopecks: int
    created_at: datetime
    paid_at: datetime | None


class MentorRewardVoidMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    reason: str = Field(min_length=3, max_length=500)


class MentorPayoutAmountMutation(BaseModel):
    amount_rubles: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    payment_reference: str | None = Field(default=None, max_length=500)


class MentorPayoutMarkPaidMutation(BaseModel):
    payment_reference: str | None = Field(default=None, max_length=500)


class MentorPayoutCancelMutation(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class AdminMentorPayoutCancelMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    reason: str | None = Field(default=None, max_length=500)


class MentorPayoutEditMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    amount_rubles: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    payment_reference: str | None = Field(default=None, max_length=500)
    paid_at: datetime | None = None
    reason: str = Field(min_length=3, max_length=500)


class MentorPayoutRead(BaseModel):
    id: UUID
    mentor_id: UUID
    mentor_name: str
    mentor_telegram_username: str | None
    amount_kopecks: int
    origin: MentorPayoutOrigin
    status: MentorPayoutStatus
    payment_reference: str | None
    created_at: datetime
    paid_at: datetime | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    edited_at: datetime | None
    edit_reason: str | None
    receipt_filename: str | None
    receipt_content_type: str | None
    receipt_size: int | None
    receipt_uploaded_at: datetime | None


class AdminMentorPayoutBalanceRead(BaseModel):
    mentor_id: UUID
    mentor_name: str
    mentor_telegram_username: str | None
    accrued_kopecks: int
    paid_kopecks: int
    reserved_kopecks: int
    available_kopecks: int


class AdminMentorPayoutDashboard(BaseModel):
    balances: list[AdminMentorPayoutBalanceRead]
    payouts: list[MentorPayoutRead]


class AdminMentorPayoutDetail(BaseModel):
    mentor_id: UUID
    mentor_name: str
    mentor_telegram_username: str | None
    accrued_kopecks: int
    paid_kopecks: int
    reserved_kopecks: int
    available_kopecks: int
    rewards: list[MentorRewardRead]
    payouts: list[MentorPayoutRead]


class AdminPaymentPage(BaseModel):
    items: list[AdminPaymentListItem]
    total: int
    limit: int
    offset: int
    scheduled_kopecks: int
    paid_kopecks: int
    overdue_kopecks: int
    mentor_rewards_accrued_kopecks: int
    mentor_rewards_paid_kopecks: int
    mentor_rewards: list[MentorRewardRead]


class MentorRewardSummary(BaseModel):
    mentor_id: UUID
    accrued_kopecks: int
    paid_kopecks: int
    unpaid_kopecks: int
    reserved_kopecks: int
    available_kopecks: int
    rewards: list[MentorRewardRead]
    payouts: list[MentorPayoutRead]


class WebhookResult(BaseModel):
    status: str
