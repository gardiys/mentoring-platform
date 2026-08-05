from __future__ import annotations

import hashlib
import logging
import math
import re
from dataclasses import dataclass
from typing import Protocol

import httpx
from openai import (
    APIConnectionError,
    APIStatusError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)
from pydantic import BaseModel, Field

from app.core.config import Settings
from app.interviews.intelligence_models import (
    IntelligenceAssessment,
    IntelligenceDifficulty,
    IntelligenceQuestionKind,
)

EXTRACTION_PROMPT_VERSION = "interview-extraction-classification-v2"
TECHNICAL_REVIEW_PROMPT_VERSION = "technical-answer-review-v2"
LIGHT_REVIEW_PROMPT_VERSION = "nontechnical-answer-review-v1"
SUMMARY_PROMPT_VERSION = "interview-summary-v1"
logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Extract every meaningful question asked to the candidate in an interview
and classify it before any answer review. Use only utterance IDs present in the input. Exclude only
greetings, connection checks, and small talk that do not expect a meaningful candidate answer.
Include technical, HR/behavioral, and organizational questions such as motivation, job changes,
salary expectations, availability, relocation, and interview process details.

Set question_kind using these strict definitions:
- technical: knowledge, engineering decisions, coding, systems, architecture,
  or technical experience;
- hr: motivation, career history, behavior, teamwork, conflict, strengths,
  or reasons for job changes;
- organizational: salary, availability, relocation, work format, documents, or hiring logistics;
- other: a meaningful question that does not fit the definitions above.

Return the interviewer utterance IDs that form each question and candidate utterance IDs that form
its logical answer. Never invent timestamps or speech. Keep category as a narrow topic label and do
not use it for routing. Lower confidence when transcription, classification,
or boundaries are ambiguous."""

TECHNICAL_REVIEW_PROMPT = """You review a candidate's answer to one technical interview question.
This is a preliminary recommendation for a human mentor, never a hiring verdict.
Do not penalize alternate wording when the technical meaning is correct. Distinguish factual
errors, missing detail, imprecise wording, and irrelevant content. If transcription is damaged,
use unable_to_assess. Do not infer personality, age, gender, accent, or employability. Base every
claim only on the supplied question, answer, and limited neighboring utterances. The context is
provided only to resolve references and conversational boundaries.
Do not review unrelated speech."""

LIGHT_REVIEW_PROMPT = """Give concise, supportive feedback on one non-technical interview answer.
This is coaching feedback, never a hiring verdict. Evaluate only clarity, relevance, answer
structure, and whether concrete examples or requested logistical details are missing. Do not judge
whether a personal motivation is right or wrong. Use unable_to_assess and a null score because
non-technical answers do not have a single factually correct solution. Do not infer personality,
emotions, age, gender, accent, health, or employability. Keep the suggested answer optional and
phrase it as an example structure rather than an invented personal story."""

SUMMARY_PROMPT = """You summarize a technical interview transcript and assess only observable
verbal communication. Describe the topics discussed, the candidate's approach, and important
outcomes without making a hiring decision. For communication, assess clarity, answer structure,
listening and responsiveness, conciseness, and clarification behavior. Use only utterance IDs
present in the input as evidence. Do not infer personality, confidence from voice, age, gender,
accent, health, emotions, or employability. If the transcript is incomplete or damaged, lower
confidence, use null scores when evidence is insufficient, and state the limitation."""


class ExtractedQuestion(BaseModel):
    question: str = Field(min_length=1)
    question_utterance_ids: list[str] = Field(min_length=1)
    answer_utterance_ids: list[str] = Field(default_factory=list)
    question_kind: IntelligenceQuestionKind
    category: str = Field(min_length=1, max_length=120)
    subcategory: str | None = Field(default=None, max_length=160)
    difficulty: IntelligenceDifficulty = IntelligenceDifficulty.UNKNOWN
    confidence: float = Field(ge=0, le=1)


class ExtractionOutput(BaseModel):
    questions: list[ExtractedQuestion]


class ReviewStrength(BaseModel):
    point: str = Field(min_length=1, description="A specific strength in the answer")
    evidence: str | None = Field(
        default=None,
        description="A short quote or precise reference to the candidate answer",
    )


class ReviewProblem(BaseModel):
    problem: str = Field(min_length=1, description="A specific problem in the answer")
    explanation: str = Field(
        min_length=1,
        description="Why this is a problem and how it affects the answer",
    )
    evidence: str | None = Field(
        default=None,
        description="A short quote or precise reference to the candidate answer",
    )


class ReviewIncorrectStatement(BaseModel):
    statement: str = Field(min_length=1, description="The incorrect candidate statement")
    correction: str = Field(min_length=1, description="A factually correct replacement")
    evidence: str | None = Field(
        default=None,
        description="A short quote or precise reference to the candidate answer",
    )


class ReviewOutput(BaseModel):
    assessment: IntelligenceAssessment
    score: float | None = Field(default=None, ge=0, le=1)
    summary: str | None = None
    strengths: list[ReviewStrength] = Field(default_factory=list)
    problems: list[ReviewProblem] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    incorrect_statements: list[ReviewIncorrectStatement] = Field(default_factory=list)
    suggested_better_answer: str | None = None


class CommunicationDimension(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    score: float | None = Field(default=None, ge=0, le=1)
    summary: str = Field(min_length=1)
    evidence_utterance_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class InterviewSummaryOutput(BaseModel):
    overall_summary: str = Field(min_length=1)
    key_topics: list[str] = Field(default_factory=list)
    communication_summary: str = Field(min_length=1)
    communication_score: float | None = Field(default=None, ge=0, le=1)
    communication_dimensions: list[CommunicationDimension] = Field(default_factory=list)
    communication_strengths: list[str] = Field(default_factory=list)
    communication_growth_areas: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class AIUsageResult:
    provider_request_id: str | None
    model: str
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class AIExtractionResult:
    output: ExtractionOutput
    usage: AIUsageResult


@dataclass(frozen=True)
class AIReviewResult:
    output: ReviewOutput
    usage: AIUsageResult


@dataclass(frozen=True)
class AISummaryResult:
    output: InterviewSummaryOutput
    usage: AIUsageResult


@dataclass(frozen=True)
class AIEmbeddingResult:
    embeddings: list[list[float]]
    usage: AIUsageResult


class InterviewAIError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.retryable = retryable


class InterviewAIProvider(Protocol):
    name: str
    embedding_model: str
    embedding_dimensions: int

    async def extract(self, transcript: str) -> AIExtractionResult: ...

    async def review(
        self,
        *,
        question: str,
        answer: str,
        category: str,
        question_kind: IntelligenceQuestionKind,
        context: str,
    ) -> AIReviewResult: ...

    async def summarize(self, transcript: str) -> AISummaryResult: ...

    async def embed(self, texts: list[str]) -> AIEmbeddingResult: ...

    async def close(self) -> None: ...


class FakeInterviewAIProvider:
    name = "fake"
    model = "fake-interview-v1"
    embedding_model = "fake-embedding-v1"
    embedding_dimensions = 64

    def __init__(self) -> None:
        self.review_calls: list[dict[str, object]] = []

    async def extract(self, transcript: str) -> AIExtractionResult:
        del transcript
        return AIExtractionResult(
            output=ExtractionOutput(
                questions=[
                    ExtractedQuestion(
                        question="Как работает GIL в Python?",
                        question_utterance_ids=["U001"],
                        answer_utterance_ids=["U002"],
                        question_kind=IntelligenceQuestionKind.TECHNICAL,
                        category="python",
                        subcategory="gil",
                        difficulty=IntelligenceDifficulty.MIDDLE,
                        confidence=0.96,
                    ),
                    ExtractedQuestion(
                        question="Почему решили сменить работу?",
                        question_utterance_ids=["U003"],
                        answer_utterance_ids=["U004"],
                        question_kind=IntelligenceQuestionKind.HR,
                        category="career",
                        subcategory="job_change",
                        difficulty=IntelligenceDifficulty.UNKNOWN,
                        confidence=0.93,
                    ),
                ]
            ),
            usage=AIUsageResult(None, self.model, 120, 48),
        )

    async def review(
        self,
        *,
        question: str,
        answer: str,
        category: str,
        question_kind: IntelligenceQuestionKind,
        context: str,
    ) -> AIReviewResult:
        self.review_calls.append(
            {
                "question": question,
                "answer": answer,
                "category": category,
                "question_kind": question_kind,
                "context": context,
            }
        )
        if question_kind is not IntelligenceQuestionKind.TECHNICAL:
            return AIReviewResult(
                output=ReviewOutput(
                    assessment=IntelligenceAssessment.UNABLE_TO_ASSESS,
                    score=None,
                    summary="Ответ можно сделать конкретнее и лучше связать с карьерной целью.",
                    strengths=[],
                    problems=[],
                    missing_points=["Добавить короткий конкретный пример"],
                    incorrect_statements=[],
                    suggested_better_answer=None,
                ),
                usage=AIUsageResult(None, "fake-light-v1", 40, 32),
            )
        return AIReviewResult(
            output=ReviewOutput(
                assessment=IntelligenceAssessment.MOSTLY_CORRECT,
                score=0.82,
                summary="Основная техническая идея сформулирована верно.",
                strengths=[
                    ReviewStrength(
                        point="Верно передана основная идея",
                        evidence="ответ",
                    )
                ],
                problems=[],
                missing_points=["Можно было привести больше практических ограничений"],
                incorrect_statements=[],
                suggested_better_answer="Краткий улучшенный ответ с примером применения.",
            ),
            usage=AIUsageResult(None, "fake-analysis-v1", 80, 72),
        )

    async def summarize(self, transcript: str) -> AISummaryResult:
        del transcript
        return AISummaryResult(
            output=InterviewSummaryOutput(
                overall_summary=("Кандидат ответил на вопросы о Python и применении потоков."),
                key_topics=["Python", "GIL", "потоки"],
                communication_summary=(
                    "Ответы сформулированы понятно, но некоторым тезисам не хватило примеров."
                ),
                communication_score=0.78,
                communication_dimensions=[
                    CommunicationDimension(
                        name="clarity",
                        score=0.8,
                        summary="Основные мысли сформулированы понятно.",
                        evidence_utterance_ids=["U002", "U004"],
                        confidence=0.9,
                    )
                ],
                communication_strengths=["Понятно формулирует основную мысль"],
                communication_growth_areas=["Добавлять практические примеры"],
                caveats=[],
            ),
            usage=AIUsageResult(None, "fake-light-v1", 160, 90),
        )

    async def embed(self, texts: list[str]) -> AIEmbeddingResult:
        return AIEmbeddingResult(
            embeddings=[self._fake_embedding(text) for text in texts],
            usage=AIUsageResult(
                None,
                self.embedding_model,
                sum(max(1, len(text.split())) for text in texts),
                0,
            ),
        )

    def _fake_embedding(self, text: str) -> list[float]:
        vector = [0.0] * self.embedding_dimensions
        for token in re.findall(r"[\w+#.-]+", text.casefold()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.embedding_dimensions
            vector[index] += 1.0 if digest[4] & 1 else -1.0
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector

    async def close(self) -> None:
        return None


class OpenAIInterviewAIProvider:
    name = "openai"

    def __init__(self, settings: Settings) -> None:
        if settings.openai_api_key is None:
            raise InterviewAIError(
                "OPENAI_AUTH_ERROR", "OpenAI API key is not configured", retryable=False
            )
        extraction_model = settings.openai_extraction_model or settings.openai_analysis_model
        if not extraction_model or not settings.openai_analysis_model:
            raise InterviewAIError(
                "OPENAI_CONFIG_ERROR", "OpenAI analysis models are not configured", retryable=False
            )
        self.extraction_model = extraction_model
        self.analysis_model = settings.openai_analysis_model
        self.light_review_model = settings.openai_light_review_model or extraction_model
        self.embedding_model = settings.openai_embedding_model
        self.embedding_dimensions = settings.openai_embedding_dimensions
        self.extraction_max_output_tokens = settings.openai_extraction_max_output_tokens
        self.review_max_output_tokens = settings.openai_review_max_output_tokens
        self.summary_max_output_tokens = settings.openai_summary_max_output_tokens
        http_client = httpx.AsyncClient(
            proxy=(
                settings.openai_proxy_url.get_secret_value()
                if settings.openai_proxy_url is not None
                else None
            ),
            timeout=httpx.Timeout(settings.openai_timeout_seconds),
        )
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=settings.openai_timeout_seconds,
            max_retries=settings.openai_max_retries,
            http_client=http_client,
        )

    async def extract(self, transcript: str) -> AIExtractionResult:
        try:
            response = await self.client.responses.parse(
                model=self.extraction_model,
                input=[
                    {"role": "developer", "content": EXTRACTION_PROMPT},
                    {"role": "user", "content": transcript},
                ],
                text_format=ExtractionOutput,
                max_output_tokens=self.extraction_max_output_tokens,
            )
            parsed = response.output_parsed
            if parsed is None:
                raise InterviewAIError(
                    "OPENAI_INVALID_RESPONSE",
                    "OpenAI returned no structured extraction",
                    retryable=False,
                )
            return AIExtractionResult(parsed, self._usage(response, self.extraction_model))
        except InterviewAIError:
            raise
        except Exception as error:
            raise self._translate_error(error) from error

    async def review(
        self,
        *,
        question: str,
        answer: str,
        category: str,
        question_kind: IntelligenceQuestionKind,
        context: str,
    ) -> AIReviewResult:
        request = (
            f"Question:\n{question}\n\nCandidate answer:\n{answer}\n\n"
            f"Category: {category}\n\nLimited context:\n{context}"
        )
        model, prompt = self._review_route(question_kind)
        try:
            response = await self.client.responses.parse(
                model=model,
                input=[
                    {"role": "developer", "content": prompt},
                    {"role": "user", "content": request},
                ],
                text_format=ReviewOutput,
                max_output_tokens=self.review_max_output_tokens,
            )
            parsed = response.output_parsed
            if parsed is None:
                raise InterviewAIError(
                    "OPENAI_INVALID_RESPONSE",
                    "OpenAI returned no structured review",
                    retryable=False,
                )
            return AIReviewResult(parsed, self._usage(response, model))
        except InterviewAIError:
            raise
        except Exception as error:
            raise self._translate_error(error) from error

    async def summarize(self, transcript: str) -> AISummaryResult:
        try:
            response = await self.client.responses.parse(
                model=self.light_review_model,
                input=[
                    {"role": "developer", "content": SUMMARY_PROMPT},
                    {"role": "user", "content": transcript},
                ],
                text_format=InterviewSummaryOutput,
                max_output_tokens=self.summary_max_output_tokens,
            )
            parsed = response.output_parsed
            if parsed is None:
                raise InterviewAIError(
                    "OPENAI_INVALID_RESPONSE",
                    "OpenAI returned no structured interview summary",
                    retryable=False,
                )
            return AISummaryResult(parsed, self._usage(response, self.light_review_model))
        except InterviewAIError:
            raise
        except Exception as error:
            raise self._translate_error(error) from error

    async def embed(self, texts: list[str]) -> AIEmbeddingResult:
        if not texts:
            return AIEmbeddingResult(
                embeddings=[],
                usage=AIUsageResult(None, self.embedding_model, 0, 0),
            )
        try:
            response = await self.client.embeddings.create(
                model=self.embedding_model,
                input=texts,
                dimensions=self.embedding_dimensions,
                encoding_format="float",
            )
            ordered = sorted(response.data, key=lambda item: item.index)
            if [item.index for item in ordered] != list(range(len(texts))):
                raise InterviewAIError(
                    "OPENAI_INVALID_RESPONSE",
                    "OpenAI returned invalid embedding indexes",
                    retryable=False,
                )
            embeddings = [list(item.embedding) for item in ordered]
            if len(embeddings) != len(texts):
                raise InterviewAIError(
                    "OPENAI_INVALID_RESPONSE",
                    "OpenAI returned an incomplete embedding batch",
                    retryable=False,
                )
            usage = response.usage
            return AIEmbeddingResult(
                embeddings=embeddings,
                usage=AIUsageResult(
                    provider_request_id=getattr(response, "id", None),
                    model=str(getattr(response, "model", None) or self.embedding_model),
                    input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
                    output_tokens=0,
                ),
            )
        except InterviewAIError:
            raise
        except Exception as error:
            raise self._translate_error(error) from error

    async def close(self) -> None:
        await self.client.close()

    def _review_route(self, question_kind: IntelligenceQuestionKind) -> tuple[str, str]:
        if question_kind is IntelligenceQuestionKind.TECHNICAL:
            return self.analysis_model, TECHNICAL_REVIEW_PROMPT
        return self.light_review_model, LIGHT_REVIEW_PROMPT

    @staticmethod
    def _usage(response: object, model: str) -> AIUsageResult:
        usage = getattr(response, "usage", None)
        return AIUsageResult(
            provider_request_id=getattr(response, "id", None),
            model=str(getattr(response, "model", None) or model),
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        )

    @staticmethod
    def _translate_error(error: Exception) -> InterviewAIError:
        if isinstance(error, APIStatusError):
            error_type, error_code = _openai_error_metadata(error)
            logger.warning(
                "OpenAI API request failed status=%s request_id=%s type=%s code=%s",
                error.status_code,
                getattr(error, "request_id", None),
                error_type,
                error_code,
            )
        if isinstance(error, AuthenticationError):
            return InterviewAIError(
                "OPENAI_AUTH_ERROR", "OpenAI credentials were rejected", retryable=False
            )
        if isinstance(error, RateLimitError):
            error_type, error_code = _openai_error_metadata(error)
            if error_type == "insufficient_quota" or error_code in {
                "insufficient_quota",
                "billing_hard_limit_reached",
                "usage_limit_reached",
            }:
                return InterviewAIError(
                    "OPENAI_QUOTA_EXCEEDED",
                    "OpenAI quota or billing limit was reached",
                    retryable=False,
                )
            return InterviewAIError(
                "OPENAI_RATE_LIMIT", "OpenAI rate limit was reached", retryable=True
            )
        if isinstance(error, APIConnectionError):
            return InterviewAIError(
                "OPENAI_PROXY_ERROR", "Could not connect to OpenAI", retryable=True
            )
        if isinstance(error, APIStatusError):
            retryable = error.status_code >= 500
            return InterviewAIError(
                "OPENAI_PROVIDER_ERROR" if retryable else "OPENAI_INVALID_REQUEST",
                "OpenAI request failed",
                retryable=retryable,
            )
        return InterviewAIError(
            "OPENAI_INVALID_RESPONSE", "OpenAI returned an invalid response", retryable=False
        )


def _openai_error_metadata(error: APIStatusError) -> tuple[str | None, str | None]:
    """Return non-sensitive provider error fields without logging the response message."""
    body = error.body
    if not isinstance(body, dict):
        return None, None
    payload = body.get("error", body)
    if not isinstance(payload, dict):
        return None, None
    error_type = payload.get("type")
    error_code = payload.get("code")
    return (
        str(error_type) if error_type is not None else None,
        str(error_code) if error_code is not None else None,
    )


def build_ai_provider(settings: Settings) -> InterviewAIProvider:
    if settings.interview_ai_provider == "fake":
        if settings.app_env == "production":
            raise RuntimeError("Fake interview AI provider is forbidden in production")
        return FakeInterviewAIProvider()
    if settings.interview_ai_provider == "openai":
        return OpenAIInterviewAIProvider(settings)
    raise RuntimeError(f"Unsupported interview AI provider: {settings.interview_ai_provider}")


def build_transcript(utterances: list[tuple[str, int, int, str]]) -> str:
    lines: list[str] = []
    for sequence, (speaker, start_ms, end_ms, text) in enumerate(utterances, start=1):
        lines.append(
            f"[U{sequence:03d}] [{_timestamp(start_ms)} - {_timestamp(end_ms)}] {speaker}:\n{text}"
        )
    return "\n\n".join(lines)


def transcript_chunks(
    transcript_blocks: list[str],
    *,
    size: int = 70,
    overlap: int = 10,
    max_chars: int = 60_000,
) -> list[str]:
    if size <= overlap:
        raise ValueError("Transcript chunk size must be greater than overlap")
    if max_chars <= 0:
        raise ValueError("Transcript chunk character limit must be positive")
    chunks: list[str] = []
    start = 0
    while start < len(transcript_blocks):
        end = min(start + size, len(transcript_blocks))
        chunk = "\n\n".join(transcript_blocks[start:end])
        while end > start + 1 and len(chunk) > max_chars:
            end -= 1
            chunk = "\n\n".join(transcript_blocks[start:end])
        chunks.append(chunk[:max_chars])
        if end >= len(transcript_blocks):
            break
        start = max(start + 1, end - overlap)
    return chunks


def _timestamp(milliseconds: int) -> str:
    total_seconds, millis = divmod(milliseconds, 1_000)
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"
