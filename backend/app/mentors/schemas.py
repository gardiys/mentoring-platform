from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.interviews.models import InterviewStageType
from app.interviews.schemas import (
    InterviewAttachmentRead,
    InterviewCatalogCommentRead,
    InterviewProcessDetail,
    InterviewProcessSummary,
)
from app.mentors.models import (
    MentorDocumentKind,
    MockInterviewStatus,
    StudentLearningStatus,
    StudentStrengthLevel,
)
from app.roadmaps.schemas import RoadmapDetail
from app.users.models import UserRole


class StudentRoadmapSummary(BaseModel):
    id: UUID
    slug: str
    title: str
    completed_topics: int
    total_topics: int
    progress_percent: int
    started_at: datetime | None
    completed_at: datetime | None
    overdue_sections: int = 0


class MentorCurrentTopic(BaseModel):
    id: UUID
    title: str
    section_title: str
    roadmap_title: str
    started_at: datetime
    days_in_topic: int
    deadline_at: datetime | None
    is_overdue: bool


class MentorStudentActivityKind(StrEnum):
    ROADMAP = "roadmap"
    INTERVIEW = "interview"
    INTERVIEW_CARDS = "interview_cards"


class MentorStudentSort(StrEnum):
    NAME_ASC = "name_asc"
    LEARNING_START_DESC = "learning_start_desc"
    LEARNING_START_ASC = "learning_start_asc"
    LAST_ACTIVITY_DESC = "last_activity_desc"
    LAST_ACTIVITY_ASC = "last_activity_asc"


class MentorAnalyticsPeriod(StrEnum):
    WEEK = "week"
    MONTH = "month"
    ALL = "all"


class MentorInterviewStageCount(BaseModel):
    stage_type: InterviewStageType
    count: int


class MentorInterviewRankingItem(BaseModel):
    position: int
    student_id: UUID
    first_name: str
    last_name: str | None
    telegram_username: str | None
    interview_count: int
    company_count: int
    offer_count: int
    ai_analysis_count: int
    last_interview_at: datetime | None


class MentorInterviewAnalytics(BaseModel):
    period: MentorAnalyticsPeriod
    period_start: datetime | None
    period_end: datetime
    selected_student_count: int
    current_interviewing_students: int
    students_with_interviews: int
    students_without_interviews: int
    total_interviews: int
    unique_companies: int
    active_processes: int
    offers_received: int
    ai_analyses_started: int
    ai_analyses_ready: int
    ai_analyses_failed: int
    interviews_with_recording: int
    upcoming_interviews_next_week: int
    average_interviews_per_participant: float
    offer_conversion_percent: float
    ai_success_rate_percent: float
    recording_coverage_percent: float
    stage_counts: list[MentorInterviewStageCount]
    ranking: list[MentorInterviewRankingItem]


class MentorEfficiencyItem(BaseModel):
    mentor_id: UUID
    role: UserRole
    first_name: str
    last_name: str | None
    telegram_username: str | None
    assigned_students: int
    interviewing_students: int
    active_interviewing_students: int
    recording_students: int
    inactive_interviewing_students: int
    interview_count: int
    recording_count: int
    ai_analysis_count: int
    offer_count: int
    upcoming_students: int
    participation_percent: float
    recording_participation_percent: float
    average_interviews_per_active_student: float
    last_interview_at: datetime | None


class MentorEfficiencyAnalytics(BaseModel):
    period: MentorAnalyticsPeriod
    period_start: datetime | None
    period_end: datetime
    mentor_count: int
    assigned_students: int
    interviewing_students: int
    active_interviewing_students: int
    inactive_interviewing_students: int
    unassigned_students: int
    unassigned_interviewing_students: int
    mentors: list[MentorEfficiencyItem]


class MentorStudentStatusPeriod(BaseModel):
    status: StudentLearningStatus
    started_at: datetime
    ended_at: datetime | None
    days: int


class MentorStudentListItem(BaseModel):
    id: UUID
    first_name: str
    last_name: str | None
    email: str | None
    telegram_username: str | None
    learning_start_date: date | None
    is_active: bool
    learning_status: StudentLearningStatus
    strength_level: StudentStrengthLevel | None
    roadmaps: list[StudentRoadmapSummary]
    current_topics: list[MentorCurrentTopic]
    last_progress_at: datetime | None
    last_activity_kind: MentorStudentActivityKind | None
    completed_topics_this_week: int
    is_overdue: bool
    mock_interview_count: int


class MentorStudentDirectionOption(BaseModel):
    id: UUID
    slug: str
    title: str


class MentorStudentMentorOption(BaseModel):
    id: UUID
    role: UserRole
    first_name: str
    last_name: str | None
    telegram_username: str | None


class MentorStudentPage(BaseModel):
    items: list[MentorStudentListItem]
    total: int
    limit: int
    offset: int
    directions: list[MentorStudentDirectionOption]
    mentors: list[MentorStudentMentorOption] = Field(default_factory=list)
    can_filter_by_mentor: bool = False


class MentorStudentStateMutation(BaseModel):
    learning_status: StudentLearningStatus
    strength_level: StudentStrengthLevel | None = None


class MentorNoteMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    body: str = Field(min_length=1, max_length=20_000)


class MentorNoteRead(BaseModel):
    id: UUID
    body: str
    author_name: str
    is_own: bool
    created_at: datetime
    updated_at: datetime


class MentorDocumentMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    text_content: str | None = Field(default=None, max_length=100_000)


class MentorDocumentRead(BaseModel):
    id: UUID
    kind: MentorDocumentKind
    text_content: str | None
    file: InterviewAttachmentRead | None
    created_at: datetime
    updated_at: datetime


class MockInterviewMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    scheduled_at: datetime
    description: str | None = Field(default=None, max_length=10_000)


class MockInterviewFeedbackMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    feedback: str = Field(min_length=1, max_length=20_000)
    conducted_at: datetime | None = None


class MockInterviewRead(BaseModel):
    id: UUID
    mentor_name: str
    student_id: UUID
    scheduled_at: datetime
    status: MockInterviewStatus
    description: str | None
    feedback: str | None
    conducted_at: datetime | None
    media: InterviewAttachmentRead | None
    created_at: datetime
    updated_at: datetime


class MentorInterviewStageFeedback(BaseModel):
    stage_id: UUID
    comments: list[InterviewCatalogCommentRead]


class MentorInterviewDetail(BaseModel):
    process: InterviewProcessDetail
    feedback: list[MentorInterviewStageFeedback]


class MentorStudentDetail(BaseModel):
    id: UUID
    first_name: str
    last_name: str | None
    email: str | None
    telegram_username: str | None
    learning_start_date: date | None
    is_active: bool
    learning_status: StudentLearningStatus
    strength_level: StudentStrengthLevel | None
    roadmaps: list[RoadmapDetail]
    current_topics: list[MentorCurrentTopic]
    last_progress_at: datetime | None
    last_activity_kind: MentorStudentActivityKind | None
    completed_topics_this_week: int
    is_overdue: bool
    mock_interview_count: int
    interviews: list[InterviewProcessSummary]
    mock_interviews: list[MockInterviewRead]
    documents: list[MentorDocumentRead]
    notes: list[MentorNoteRead]
    status_history: list[MentorStudentStatusPeriod]


class MentorDocumentContentMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    text_content: str | None = Field(default=None, max_length=100_000)
    keep_file: bool = True

    @model_validator(mode="after")
    def has_content_or_keeps_file(self) -> "MentorDocumentContentMutation":
        if not self.keep_file and not self.text_content:
            raise ValueError("Document text is required when the file is removed")
        return self
