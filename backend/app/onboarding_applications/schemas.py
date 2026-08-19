from typing import Any, Literal

from pydantic import BaseModel, Field

ApplicationAction = Literal[
    "approve_qualification",
    "reject_qualification",
    "approve_after_call",
    "reject_after_call",
    "request_follow_up",
    "confirm_payment",
    "resend_payment",
    "complete_onboarding",
    "confirm_access",
    "access_missing",
]


class OnboardingApplicationListItem(BaseModel):
    applicant_id: str
    status: str
    name: str | None
    telegram_user_id: int
    telegram_username: str | None
    email: str | None
    direction: str | None
    city: str | None
    admin_comment: str | None
    booking_start_time: str | None
    payment_status: str | None
    created_at: str
    updated_at: str
    available_actions: list[ApplicationAction]


class OnboardingApplicationPage(BaseModel):
    items: list[OnboardingApplicationListItem]
    total: int
    limit: int
    offset: int
    status_counts: dict[str, int]


class OnboardingApplicationEvent(BaseModel):
    event_type: str
    old_status: str | None
    new_status: str | None
    source: str
    payload: dict[str, Any] | None
    created_at: str


class OnboardingBooking(BaseModel):
    status: str
    start_time: str | None
    end_time: str | None
    meeting_url: str | None
    created_at: str


class OnboardingPayment(BaseModel):
    status: str
    amount: str
    currency: str
    payment_url: str | None
    approved_at: str | None
    created_at: str


class OnboardingApplicationDetail(OnboardingApplicationListItem):
    age: str | None
    initial_knowledge: str | None
    life_difficulties: str | None
    study_time_per_day: str | None
    military_document_status: str | None
    referral_source: str | None
    form_answers: dict[str, Any]
    bookings: list[OnboardingBooking]
    payments: list[OnboardingPayment]
    events: list[OnboardingApplicationEvent]


class OnboardingApplicationActionRequest(BaseModel):
    action: ApplicationAction
    comment: str | None = Field(default=None, max_length=2_000)


class OnboardingApplicationActionResponse(BaseModel):
    message: str
    delivered: bool | None
    application: OnboardingApplicationDetail
