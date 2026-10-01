"""Stable, versioned communication rubric shared by generation and API validation."""

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class CommunicationSkill(StrEnum):
    STRUCTURE = "structure"
    SPECIFICITY = "specificity"
    CONCISENESS = "conciseness"
    CLARIFICATION = "clarification"
    HANDLING_UNKNOWN = "handling_unknown"
    HANDLING_PUSHBACK = "handling_pushback"
    REASONING_ALOUD = "reasoning_aloud"
    OWNERSHIP = "ownership"


SKILL_LABELS = {
    "structure": "Структура ответа",
    "specificity": "Конкретность",
    "conciseness": "Соразмерность ответа",
    "clarification": "Уточнение условий",
    "handling_unknown": "Работа с незнанием",
    "handling_pushback": "Реакция на уточнения и поправки",
    "reasoning_aloud": "Рассуждение вслух",
    "ownership": "Личный вклад",
}


class CommunicationRewrite(BaseModel):
    original: str = Field(min_length=1, max_length=600)
    improved: str = Field(min_length=1, max_length=900)


class CommunicationExercise(BaseModel):
    task: str = Field(min_length=1, max_length=600)
    success_criterion: str = Field(min_length=1, max_length=400)


class CommunicationDimension(BaseModel):
    # Legacy snapshots can still be parsed; grounding excludes entries without a skill/quote.
    name: str = Field(default="", max_length=80)
    skill: CommunicationSkill | None = None
    score: float | None = Field(default=None, ge=0, le=1)
    summary: str = Field(min_length=1, max_length=800)
    evidence_utterance_ids: list[str] = Field(default_factory=list, max_length=12)
    evidence_quote: str = Field(default="", max_length=600)
    confidence: float = Field(ge=0, le=1)
    rewrite: CommunicationRewrite | None = None
    exercise: CommunicationExercise | None = None


class CandidateQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=1200)
    evidence_quote: str = Field(min_length=1, max_length=600)
    question_utterance_ids: list[str] = Field(min_length=1, max_length=12)
    response_utterance_ids: list[str] = Field(default_factory=list, max_length=12)


class CoachingState(BaseModel):
    completed_at: datetime | None = None
    decision: Literal["approved", "rejected"] | None = None
    reviewer_id: UUID | None = None
    reviewed_at: datetime | None = None


class GroundedCommunicationDimension(CommunicationDimension):
    observation_count: int = Field(default=1, ge=1)
    scored_observation_count: int = Field(default=0, ge=0)
    example_score: float | None = Field(default=None, ge=0, le=1)


class CoachingObservation(GroundedCommunicationDimension):
    interview_id: UUID
    analysis_revision: int
    date: datetime
    interview_type: str
    completed_at: datetime | None = None
    decision: Literal["approved", "rejected"] | None = None


class CommunicationHistory(BaseModel):
    student_id: UUID
    observations: list[CoachingObservation]
    interview_count: int = 0
    limit: int = 30
    truncated: bool = False
