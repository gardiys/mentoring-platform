"""Import all models so SQLAlchemy and Alembic discover their metadata."""

from app.interviews.models import (
    Company,
    CompanyAlias,
    InterviewCard,
    InterviewCardFrequency,
    InterviewCardProgress,
    InterviewDeck,
    InterviewProcess,
    InterviewProcessStage,
    InterviewProcessStageAttachment,
    InterviewProcessStatus,
    InterviewReviewRating,
    InterviewStageComment,
    InterviewStageType,
    InterviewTopicSelection,
)
from app.knowledge.models import KnowledgeEntry, KnowledgeEntryKind, KnowledgeTopic
from app.mentors.models import (
    MentorDocumentKind,
    MentorStudent,
    MentorStudentDocument,
    MentorStudentNote,
    MockInterview,
    MockInterviewStatus,
    StudentLearningStatus,
    StudentStrengthLevel,
)
from app.progress.models import ProgressStatus, TopicProgress
from app.roadmaps.models import Roadmap, RoadmapEnrollment, RoadmapSection, Topic
from app.tracks.models import LearningTrack, LearningTrackEnrollment, LearningTrackRoadmap
from app.users.models import User, UserRole

__all__ = [
    "Company",
    "CompanyAlias",
    "MentorStudent",
    "MentorStudentDocument",
    "MentorStudentNote",
    "MentorDocumentKind",
    "MockInterview",
    "MockInterviewStatus",
    "StudentLearningStatus",
    "StudentStrengthLevel",
    "KnowledgeEntry",
    "KnowledgeEntryKind",
    "KnowledgeTopic",
    "InterviewCard",
    "InterviewCardFrequency",
    "InterviewCardProgress",
    "InterviewDeck",
    "InterviewProcess",
    "InterviewProcessStage",
    "InterviewProcessStageAttachment",
    "InterviewProcessStatus",
    "InterviewReviewRating",
    "InterviewStageType",
    "InterviewStageComment",
    "InterviewTopicSelection",
    "LearningTrack",
    "LearningTrackEnrollment",
    "LearningTrackRoadmap",
    "ProgressStatus",
    "Roadmap",
    "RoadmapEnrollment",
    "RoadmapSection",
    "Topic",
    "TopicProgress",
    "User",
    "UserRole",
]
