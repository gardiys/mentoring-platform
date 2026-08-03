from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class MentorStudentListItem(BaseModel):
    id: UUID
    first_name: str
    last_name: str | None
    email: str | None
    telegram_username: str | None
    learning_status: StudentLearningStatus
    strength_level: StudentStrengthLevel | None
    roadmaps: list[StudentRoadmapSummary]
    current_topics: list[MentorCurrentTopic]
    last_progress_at: datetime | None
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
    learning_status: StudentLearningStatus
    strength_level: StudentStrengthLevel | None
    roadmaps: list[RoadmapDetail]
    current_topics: list[MentorCurrentTopic]
    last_progress_at: datetime | None
    completed_topics_this_week: int
    is_overdue: bool
    mock_interview_count: int
    interviews: list[InterviewProcessSummary]
    mock_interviews: list[MockInterviewRead]
    documents: list[MentorDocumentRead]
    notes: list[MentorNoteRead]


class MentorDocumentContentMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    text_content: str | None = Field(default=None, max_length=100_000)
    keep_file: bool = True

    @model_validator(mode="after")
    def has_content_or_keeps_file(self) -> "MentorDocumentContentMutation":
        if not self.keep_file and not self.text_content:
            raise ValueError("Document text is required when the file is removed")
        return self
