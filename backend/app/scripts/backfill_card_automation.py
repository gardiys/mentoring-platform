from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import or_, select

from app.db import models as _db_models  # noqa: F401
from app.db.session import async_session_factory
from app.interviews.card_automation_models import CardAutomationSettings
from app.interviews.card_automation_types import QuestionOccurrenceStatus
from app.interviews.intelligence_models import (
    IntelligenceInterview,
    IntelligenceQuestion,
    IntelligenceQuestionModerationStatus,
)
from app.interviews.intelligence_queue import enqueue_card_automation_job
from app.interviews.models import InterviewProcess, InterviewProcessStage
from app.interviews.question_matching import normalize_question
from app.tracks.models import LearningTrack

logger = logging.getLogger(__name__)

# One occurrence can call routing and one pairwise judge. ARQ allows four
# attempts, therefore a budgeted backfill reserves the safe upper bound rather
# than pretending that one queued occurrence always equals one API request.
# Answer generation is explicitly disallowed in budgeted mode below.
AI_REQUEST_RESERVATION_PER_OCCURRENCE = 8


@dataclass(frozen=True, slots=True)
class BackfillOptions:
    direction: str | None
    batch_size: int
    dry_run: bool
    unreviewed_only: bool
    max_ai_requests: int | None


async def run(options: BackfillOptions) -> dict[str, int]:
    max_occurrences: int | None = None
    if options.max_ai_requests is not None:
        max_occurrences = options.max_ai_requests // AI_REQUEST_RESERVATION_PER_OCCURRENCE
        if max_occurrences < 1:
            raise ValueError(
                "max_ai_requests is lower than the safe per-occurrence reservation "
                f"({AI_REQUEST_RESERVATION_PER_OCCURRENCE})"
            )
        if not options.dry_run:
            await _ensure_budgeted_mode_is_safe(options)
    examined = 0
    prepared = 0
    enqueued = 0
    cursor: UUID | None = None
    while True:
        async with async_session_factory() as session:
            statement = (
                select(IntelligenceQuestion, InterviewProcess.track_id)
                .join(
                    IntelligenceInterview,
                    IntelligenceInterview.id == IntelligenceQuestion.interview_id,
                )
                .join(
                    InterviewProcessStage,
                    InterviewProcessStage.id == IntelligenceInterview.stage_id,
                )
                .join(InterviewProcess, InterviewProcess.id == InterviewProcessStage.process_id)
                .join(LearningTrack, LearningTrack.id == InterviewProcess.track_id)
                .where(
                    IntelligenceQuestion.alias_human_confirmed.is_(False),
                    IntelligenceQuestion.published_card_id.is_(None),
                    # Backfill is deliberately limited to untouched legacy
                    # rows. APPROVED, REJECTED and MENTOR_APPROVED are all
                    # human decisions and must remain byte-for-byte intact.
                    IntelligenceQuestion.moderation_status
                    == IntelligenceQuestionModerationStatus.PENDING,
                )
                .order_by(IntelligenceQuestion.id)
                .limit(options.batch_size)
            )
            if cursor is not None:
                statement = statement.where(IntelligenceQuestion.id > cursor)
            if options.direction is not None:
                statement = statement.where(LearningTrack.slug == options.direction)
            # All eligible rows are unreviewed by design. Keep the option for
            # backwards-compatible runbooks and explicit operator intent.
            if options.unreviewed_only:
                statement = statement.where(
                    IntelligenceQuestion.moderation_status
                    == IntelligenceQuestionModerationStatus.PENDING
                )
            # A restarted run naturally resumes because terminal questions are
            # excluded and deterministic ARQ keys deduplicate queued work.
            statement = statement.where(
                or_(
                    IntelligenceQuestion.automation_status == QuestionOccurrenceStatus.CREATED,
                    IntelligenceQuestion.automation_status == QuestionOccurrenceStatus.FAILED,
                )
            )
            rows = (await session.execute(statement)).all()
            if not rows:
                break
            queue_items: list[tuple[UUID, int]] = []
            for question, track_id in rows:
                if max_occurrences is not None and prepared >= max_occurrences:
                    break
                cursor = question.id
                examined += 1
                prepared += 1
                if options.dry_run:
                    continue
                question.direction_id = track_id
                question.normalized_question_text = normalize_question(question.question_text)
                if question.automation_status is QuestionOccurrenceStatus.FAILED:
                    question.automation_revision += 1
                    question.automation_attempts = 0
                    question.automation_error = None
                    question.automation_status = QuestionOccurrenceStatus.CREATED
                queue_items.append((question.id, question.automation_revision))
            if not options.dry_run:
                await session.commit()
        for question_id, revision in queue_items:
            await enqueue_card_automation_job(
                "route_question_occurrence",
                str(question_id),
                revision,
            )
            enqueued += 1
        logger.info(
            "Card automation backfill progress examined=%s prepared=%s enqueued=%s "
            "reserved_ai_requests=%s cursor=%s",
            examined,
            prepared,
            enqueued,
            prepared * AI_REQUEST_RESERVATION_PER_OCCURRENCE,
            cursor,
        )
        if max_occurrences is not None and prepared >= max_occurrences:
            break
    return {
        "examined": examined,
        "prepared": prepared,
        "enqueued": enqueued,
        "reserved_ai_requests": (
            prepared * AI_REQUEST_RESERVATION_PER_OCCURRENCE
            if options.max_ai_requests is not None
            else 0
        ),
    }


async def _ensure_budgeted_mode_is_safe(options: BackfillOptions) -> None:
    """Reject a budget that could be bypassed by answer generation jobs.

    This is a startup safety check, so operators must keep cluster moderation
    disabled until all jobs from the bounded run are drained.
    """

    async with async_session_factory() as session:
        statement = (
            select(CardAutomationSettings.direction_id)
            .join(LearningTrack, LearningTrack.id == CardAutomationSettings.direction_id)
            .where(
                CardAutomationSettings.enabled.is_(True),
                CardAutomationSettings.cluster_moderation_enabled.is_(True),
            )
            .limit(1)
        )
        if options.direction is not None:
            statement = statement.where(LearningTrack.slug == options.direction)
        unsafe_direction = await session.scalar(statement)
    if unsafe_direction is not None:
        raise RuntimeError(
            "--max-ai-requests requires cluster_moderation_enabled=false for the "
            "selected direction until queued backfill jobs are drained"
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill interview question automation")
    parser.add_argument("--direction", choices=("python", "go"))
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Accepted for explicit runbooks")
    parser.add_argument("--unreviewed-only", action="store_true")
    parser.add_argument("--max-ai-requests", type=int)
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    args = _parser().parse_args()
    if not 1 <= args.batch_size <= 10_000:
        raise SystemExit("--batch-size must be between 1 and 10000")
    if args.max_ai_requests is not None and args.max_ai_requests < 1:
        raise SystemExit("--max-ai-requests must be positive")
    if (
        args.max_ai_requests is not None
        and args.max_ai_requests < AI_REQUEST_RESERVATION_PER_OCCURRENCE
    ):
        raise SystemExit(
            "--max-ai-requests must be at least "
            f"{AI_REQUEST_RESERVATION_PER_OCCURRENCE} (safe retry reservation)"
        )
    result = asyncio.run(
        run(
            BackfillOptions(
                direction=args.direction,
                batch_size=args.batch_size,
                dry_run=args.dry_run,
                unreviewed_only=args.unreviewed_only,
                max_ai_requests=args.max_ai_requests,
            )
        )
    )
    logger.info("Card automation backfill complete %s", result)


if __name__ == "__main__":
    main()
