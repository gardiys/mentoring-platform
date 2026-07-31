"""Import all models so SQLAlchemy and Alembic discover their metadata."""

from app.interviews.models import (
    InterviewCard,
    InterviewCardFrequency,
    InterviewCardProgress,
    InterviewDeck,
    InterviewReviewRating,
    InterviewTopicSelection,
)
from app.knowledge.models import KnowledgeEntry, KnowledgeEntryKind, KnowledgeTopic
from app.mentors.models import MentorStudent
from app.progress.models import ProgressStatus, TopicProgress
from app.roadmaps.models import Roadmap, RoadmapEnrollment, RoadmapSection, Topic
from app.tracks.models import LearningTrack, LearningTrackEnrollment, LearningTrackRoadmap
from app.users.models import User, UserRole

__all__ = [
    "MentorStudent",
    "KnowledgeEntry",
    "KnowledgeEntryKind",
    "KnowledgeTopic",
    "InterviewCard",
    "InterviewCardFrequency",
    "InterviewCardProgress",
    "InterviewDeck",
    "InterviewReviewRating",
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
