from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.opportunities.python_repeat_schemas import AdminPythonRepeatApplicationRead
from app.opportunities.schemas import (
    AdminConsultationMentorRead,
    AdminConsultationRead,
    AdminGoTransitionRead,
    AdminOpportunityStudentRead,
    ConsultationTypeRead,
    MentorOptionRead,
)


class OpportunitySummary(BaseModel):
    needs_action_total: int = 0
    overdue_total: int = 0
    consultations: dict[str, int] = Field(default_factory=dict)
    go_transition: dict[str, int] = Field(default_factory=dict)
    python_repeat: dict[str, int] = Field(default_factory=dict)


class WorkspaceStageRead(BaseModel):
    stage: str
    next_action: str
    waiting_since: datetime | None
    overdue: bool


class WorkspaceItem(WorkspaceStageRead):
    product: Literal["consultations", "go_transition", "python_repeat"]
    id: UUID
    student: AdminOpportunityStudentRead
    title: str
    status: str
    key_date: datetime | None
    amount_kopecks: int | None = None
    mentor: MentorOptionRead | None = None


class WorkspacePage(BaseModel):
    items: list[WorkspaceItem]
    total: int
    counts: dict[str, int]
    page: int
    page_size: int


class WorkspaceHistoryRead(BaseModel):
    id: UUID | None = None
    old_status: str | None = None
    new_status: str
    actor_user_id: UUID | None = None
    actor_name: str | None = None
    comment: str | None = None
    snapshot: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class WorkspacePaymentRead(BaseModel):
    attempt_id: UUID
    status: str
    created_at: datetime


class AdminConsultationDetail(AdminConsultationRead, WorkspaceStageRead):
    available_mentors: list[MentorOptionRead] = Field(default_factory=list)
    requested_mentor: MentorOptionRead | None = None
    requested_mentor_known: bool = False
    internal_note: str | None
    updated_at: datetime
    last_payment: WorkspacePaymentRead | None
    history: list[WorkspaceHistoryRead]
    refund_required: bool | None = None


class AdminGoTransitionDetail(AdminGoTransitionRead, WorkspaceStageRead):
    internal_note: str | None
    updated_at: datetime
    last_payment: WorkspacePaymentRead | None
    payment_block_reason: str | None
    history: list[WorkspaceHistoryRead]


class AdminPythonRepeatDetail(AdminPythonRepeatApplicationRead, WorkspaceStageRead):
    pass


class WorkspaceSettings(BaseModel):
    consultation_types: list[ConsultationTypeRead]
    consultation_mentors: list[AdminConsultationMentorRead]
    go_transition_description_markdown: str


class WorkspaceCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class ConsultationApproveCommand(WorkspaceCommand):
    mentor_id: UUID
    message_to_student: str | None = Field(default=None, max_length=5000)


class MentorCommand(WorkspaceCommand):
    mentor_id: UUID


class ReasonCommand(WorkspaceCommand):
    reason: str = Field(min_length=10, max_length=2000)


class ConsultationCancelCommand(ReasonCommand):
    refund_required: bool | None = None


class ConsultationScheduleCommand(WorkspaceCommand):
    scheduled_at: AwareDatetime


class ConsultationSummaryCommand(WorkspaceCommand):
    written_summary: str = Field(min_length=10, max_length=10000)


class ConsultationCompleteCommand(ConsultationSummaryCommand):
    held_at: AwareDatetime | None = None


class InternalNoteCommand(WorkspaceCommand):
    internal_note: str | None = Field(default=None, max_length=5000)


class GoApproveCommand(WorkspaceCommand):
    message_to_student: str | None = Field(default=None, max_length=5000)
