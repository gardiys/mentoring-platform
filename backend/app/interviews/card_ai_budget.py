"""Admission and durable reservation of card spending, before the HTTP request."""

import json
import logging
import math
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from time import perf_counter
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import event, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, SessionTransaction
from sqlalchemy.sql.elements import ColumnElement

from app.core.config import get_settings
from app.interviews.ai_pricing import estimated_cost
from app.interviews.card_automation_domain import promotion_result
from app.interviews.card_automation_models import (
    AutomationDecision,
    CardAICharge,
    CardAutomationSettings,
    QuestionCluster,
)
from app.interviews.card_automation_types import AnswerContractStatus, AutomationDecisionType
from app.interviews.intelligence_models import (
    AIRequestLog,
    IntelligenceInterview,
    IntelligenceQuestion,
)

CARD_OPERATIONS = frozenset({"generate_answer_contract", "validate_answer_contract"})
BUDGET_CODES = frozenset(
    {
        "CARD_AI_NOT_SELECTED",
        "CARD_AI_AWAITING_ADMISSION",
        "CARD_AI_TOPIC_LIMIT",
        "CARD_AI_INTERVIEW_BUDGET",
        "CARD_AI_DAILY_BUDGET",
        "CARD_AI_PRICING_UNKNOWN",
        "CARD_AI_NO_SOURCE_INTERVIEW",
        "CARD_AI_RESERVATION_BUSY",
        "CARD_AI_MAINTENANCE_BUDGET",
        "CARD_AI_COST_UNKNOWN",
        "CARD_AI_BACKLOG_DISABLED",
    }
)
FREE_ERRORS = frozenset(
    {
        "RateLimitError",
        "AuthenticationError",
        "PermissionDeniedError",
        "BadRequestError",
        "NotFoundError",
        "connect_error",
    }
)
card_budget_context: ContextVar[tuple[UUID, bool] | None] = ContextVar(
    "card_budget_context", default=None
)
_LOCK = 730071007
ZERO = Decimal("0")
UNKNOWN_ATTEMPT_LIMIT = 2
logger = logging.getLogger(__name__)


def request_deadline(charge: CardAICharge) -> datetime:
    return charge.created_at + timedelta(seconds=get_settings().openai_job_timeout_seconds + 60)


def request_inflight(charge: CardAICharge, now: datetime) -> bool:
    return charge.status == "reserved" and request_deadline(charge) > now


def unknown_charge_condition() -> ColumnElement[bool]:
    cutoff = datetime.now(UTC) - timedelta(seconds=get_settings().openai_job_timeout_seconds + 60)
    return or_(
        CardAICharge.status == "unknown",
        (CardAICharge.status == "reserved") & (CardAICharge.created_at <= cutoff),
    )


def daily_amount(charge: CardAICharge, start: datetime, end: datetime, now: datetime) -> Decimal:
    if start <= charge.created_at < end or request_inflight(charge, now):
        return charge.amount_usd
    # Only a pledge for a future check carries over; historical unknown usage
    # remains charged to its creation day and original interview.
    return (
        charge.validation_reserve_usd
        if (charge.reserve_expires_at and charge.reserve_expires_at > now)
        else ZERO
    )


def new_card_theme(cluster: QuestionCluster, admitted: CardAICharge | None) -> bool:
    # Personal review text is free to reuse, but its first independent check
    # still needs paid admission. Only explicit pre-migration drafts are exempt.
    return (
        admitted is None
        and cluster.linked_card_id is None
        and not (cluster.generation_backlog and cluster.answer_contract is not None)
    )


async def acquire_card_budget_lock(session: AsyncSession, operation: str) -> None:
    started = perf_counter()
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _LOCK})
    session.info.setdefault("card_ai_lock", (perf_counter(), operation, perf_counter() - started))


@event.listens_for(Session, "after_transaction_end")
def log_budget_lock_duration(session: Session, transaction: SessionTransaction) -> None:
    if transaction.parent is None and (timing := session.info.pop("card_ai_lock", None)):
        acquired, operation, waited = timing
        logger.info(
            "Card AI budget lock operation=%s wait_ms=%.1f hold_ms=%.1f",
            operation,
            waited * 1000,
            (perf_counter() - acquired) * 1000,
        )


def check_unknown_attempts(rows: list[CardAICharge], now: datetime) -> None:
    if sum(row.status == "unknown" for row in rows) >= UNKNOWN_ATTEMPT_LIMIT:
        _deny(
            "CARD_AI_COST_UNKNOWN",
            "Стоимость двух попыток неизвестна. Администратору нужно списать резерв перед повтором",
        )
    if any(request_inflight(row, now) for row in rows) or any(
        row.status == "unknown" and request_deadline(row) > now for row in rows
    ):
        _deny("CARD_AI_RESERVATION_BUSY", "Предыдущий запрос ещё может выполняться", retryable=True)


@contextmanager
def card_budget_scope(cluster_id: UUID, *, manual: bool = False) -> Iterator[None]:
    token = card_budget_context.set((cluster_id, manual))
    try:
        yield
    finally:
        card_budget_context.reset(token)


def _deny(code: str, reason: str, *, retryable: bool = False) -> None:
    from app.interviews.intelligence_ai import InterviewAIError

    raise InterviewAIError(code, reason, retryable=retryable)


def request_reserve(model: str, tier: str, request: dict[str, Any]) -> Decimal:
    # Calibrated multilingual estimate: Cyrillic is typically ~2 chars/token,
    # Latin ~4. Use 1.4/2.5 plus 25% margin and 512 framing tokens. Always
    # reserve maximum output (reasoning included); this is an estimate, not a cap.
    schema = request.get("text_format")
    payload = json.dumps(
        {
            "input": request.get("input", []),
            "schema": schema.model_json_schema() if schema is not None else {},
        },
        ensure_ascii=False,
    )
    non_ascii = sum(ord(c) > 127 for c in payload)
    tokens = math.ceil(((len(payload) - non_ascii) / 2.5 + non_ascii / 1.4) * 1.25) + 512
    cost = estimated_cost(
        model,
        tier,
        tokens,
        0,
        int(request["max_output_tokens"]),
        cache_write_tokens=tokens if model.startswith("gpt-5.6-") else 0,
    )
    if cost is None:
        _deny("CARD_AI_PRICING_UNKNOWN", "Цена модели не настроена: платный запрос отложен")
    assert cost is not None
    return cost


def validation_pledge(request: dict[str, Any], tier: str) -> Decimal:
    from app.interviews.card_automation_schemas import AnswerValidationResult
    from app.interviews.intelligence_ai import ANSWER_VALIDATION_PROMPT

    config = get_settings()
    # Keep the exact sources/question and allow the generated contract to occupy
    # the full output ceiling. The validator uses the same maximum output size.
    validation_request = {
        **request,
        "text_format": AnswerValidationResult,
        "input": [
            request.get("input", []),
            ANSWER_VALIDATION_PROMPT,
            "x" * (int(request["max_output_tokens"]) * 4),
        ],
    }
    return request_reserve(
        config.openai_card_validation_model or config.openai_analysis_model or "gpt-5-mini",
        tier,
        validation_request,
    )


def eligible(cluster: QuestionCluster, settings: CardAutomationSettings) -> bool:
    return (
        cluster.linked_card_id is None
        and cluster.priority_score >= settings.card_ai_min_priority_score
        and promotion_result(
            distinct_interviews=cluster.distinct_interviews_count,
            distinct_companies=cluster.distinct_companies_count,
            failed_answers=cluster.failed_answers_count,
            min_interviews=settings.min_distinct_interviews_for_promotion,
            min_companies=settings.min_distinct_companies_for_promotion,
            min_failures=settings.min_failed_answers_for_promotion,
            manual_important=cluster.manual_important,
        ).promoted
    )


def _day_bounds() -> tuple[datetime, datetime]:
    zone = ZoneInfo(get_settings().interview_ai_quota_timezone)
    today = datetime.now(zone).date()
    return (
        datetime.combine(today, time.min, zone).astimezone(UTC),
        datetime.combine(today + timedelta(days=1), time.min, zone).astimezone(UTC),
    )


async def budget_snapshot(
    session: AsyncSession, cluster: QuestionCluster, settings: CardAutomationSettings
) -> dict[str, str]:
    rows = list(
        await session.scalars(
            select(CardAICharge).where(
                or_(
                    CardAICharge.direction_id == cluster.direction_id,
                    CardAICharge.direction_id.is_(None),
                )
            )
        )
    )
    origin = cluster.generation_source_interview_id
    if origin is None:
        first_charge = next(
            (
                row
                for row in rows
                if row.cluster_id == cluster.id and not row.manual and row.amount_usd > 0
            ),
            None,
        )
        origin = (
            first_charge.interview_id
            if first_charge
            else await session.scalar(
                select(IntelligenceQuestion.interview_id)
                .where(IntelligenceQuestion.cluster_id == cluster.id)
                .order_by(IntelligenceQuestion.created_at.desc())
                .limit(1)
            )
        )
    if origin is None:
        origin = await session.scalar(
            select(IntelligenceQuestion.interview_id).where(
                IntelligenceQuestion.id == cluster.representative_occurrence_id
            )
        )
    start, end = _day_bounds()
    day = sum(
        (daily_amount(r, start, end, datetime.now(UTC)) for r in rows),
        ZERO,
    )
    interview = sum(
        (
            r.amount_usd
            for r in rows
            if r.interview_id == origin and not r.manual and not r.maintenance
        ),
        ZERO,
    )
    snapshot = {"daily_remaining_usd": str(max(settings.card_ai_daily_budget_usd - day, ZERO))}
    if origin is not None:
        snapshot["interview_remaining_usd"] = str(
            max(settings.card_ai_budget_per_interview_usd - interview, ZERO)
        )
    return snapshot


async def precheck_manual_budget(
    session: AsyncSession, cluster: QuestionCluster, settings: CardAutomationSettings
) -> dict[str, str]:
    await acquire_card_budget_lock(session, "manual_precheck")
    await reconcile_card_charges(session)
    previous = list(
        await session.scalars(
            select(CardAICharge).where(
                CardAICharge.cluster_id == cluster.id,
                CardAICharge.amount_usd > 0,
            )
        )
    )
    try:
        check_unknown_attempts(previous, datetime.now(UTC))
    except Exception as error:
        from app.core.errors import api_error
        from app.interviews.intelligence_ai import InterviewAIError

        if isinstance(error, InterviewAIError):
            api_error(409, error.code, error.safe_message)
        raise
    snapshot = await budget_snapshot(session, cluster, settings)
    from app.interviews.card_automation_jobs import _trusted_sources
    from app.interviews.card_automation_schemas import AnswerContract
    from app.interviews.intelligence_ai import ANSWER_CONTRACT_PROMPT

    config = get_settings()
    request = {
        "input": [
            ANSWER_CONTRACT_PROMPT,
            cluster.canonical_question,
            await _trusted_sources(session, cluster),
        ],
        "text_format": AnswerContract,
        "max_output_tokens": config.openai_review_max_output_tokens,
    }
    required = request_reserve(
        config.openai_analysis_model or "gpt-5-mini", config.openai_background_service_tier, request
    ) + validation_pledge(request, config.openai_background_service_tier)
    if Decimal(snapshot["daily_remaining_usd"]) < required:
        from app.core.errors import api_error

        api_error(
            409,
            "CARD_AI_DAILY_BUDGET",
            f"Недостаточно суточного бюджета карточек: остаток ${snapshot['daily_remaining_usd']}, "
            f"требуется резерв ${required:.4f}. Повторите завтра или измените лимит направления.",
        )
    return snapshot


async def reserve_card_request(
    session: AsyncSession,
    request_id: UUID,
    operation: str,
    model: str,
    tier: str,
    request: dict[str, Any],
) -> None:
    context = card_budget_context.get()
    if context is None or operation not in CARD_OPERATIONS:
        return
    cluster_id, manual = context
    amount = request_reserve(model, tier, request)
    await acquire_card_budget_lock(session, "reserve")
    await reconcile_card_charges(session)
    cluster = await session.get(QuestionCluster, cluster_id)
    if cluster is None:
        _deny("CARD_AI_NO_SOURCE_INTERVIEW", "Кластер удалён")
    assert cluster is not None
    settings = await session.get(CardAutomationSettings, cluster.direction_id)
    if settings is None:
        _deny("CARD_AI_NOT_SELECTED", "Автоматизация направления не настроена")
    assert settings is not None
    rows = list(
        await session.scalars(
            select(CardAICharge).where(
                or_(
                    CardAICharge.direction_id == cluster.direction_id,
                    CardAICharge.direction_id.is_(None),
                )
            )
        )
    )
    previous = [r for r in rows if r.cluster_id == cluster_id and r.amount_usd > 0]
    check_unknown_attempts(previous, datetime.now(UTC))
    admitted = next((r for r in previous if not r.manual), None)
    interview_id = admitted.interview_id if admitted else cluster.generation_source_interview_id
    if interview_id is None:
        interview_id = await session.scalar(
            select(IntelligenceQuestion.interview_id)
            .where(IntelligenceQuestion.cluster_id == cluster_id)
            .order_by(IntelligenceQuestion.created_at.desc())
            .limit(1)
        )
    if interview_id is None:
        interview_id = await session.scalar(
            select(IntelligenceQuestion.interview_id).where(
                IntelligenceQuestion.id == cluster.representative_occurrence_id
            )
        )
    if interview_id is None:
        _deny("CARD_AI_NO_SOURCE_INTERVIEW", "Нет интервью-источника для учёта расходов")
    now = datetime.now(UTC)
    origin_created = await session.scalar(
        select(IntelligenceInterview.created_at).where(IntelligenceInterview.id == interview_id)
    )
    source_is_backlog = cluster.generation_backlog or now - (
        origin_created or cluster.last_seen_at
    ) > timedelta(days=7)
    prior_validation = (
        await session.scalar(
            select(AutomationDecision)
            .where(
                AutomationDecision.entity_id == cluster_id,
                AutomationDecision.entity_type == "cluster",
                AutomationDecision.decision_type
                == AutomationDecisionType.ANSWER_CONTRACT_VALIDATED,
            )
            .order_by(AutomationDecision.created_at.desc(), AutomationDecision.id)
            .limit(1)
        )
        if operation == "validate_answer_contract" and cluster.answer_validation is None
        else None
    )
    servicing = bool(prior_validation and (prior_validation.judge_result or {}).get("supported"))
    maintenance = bool(
        not manual
        and (
            servicing
            or (admitted and now - admitted.created_at > timedelta(days=7))
            or (not admitted and source_is_backlog)
        )
    )
    new_theme = new_card_theme(cluster, admitted)
    if not manual and not admitted and not servicing and new_theme:
        if (
            cluster.generation_source_interview_id is None
            or cluster.generation_selected_revision != cluster.membership_revision
        ):
            _deny(
                "CARD_AI_AWAITING_ADMISSION",
                "Тема ожидает завершения маршрутизации и отбора по приоритету",
            )
        if cluster.answer_status == AnswerContractStatus.NOT_SELECTED:
            _deny("CARD_AI_NOT_SELECTED", "Тема не прошла отбор для платной обработки")
        if not eligible(cluster, settings):
            _deny(
                "CARD_AI_NOT_SELECTED", "Тема не прошла пороги отбора по повторяемости и приоритету"
            )
        if cluster.generation_backlog and not settings.card_ai_legacy_backlog_enabled:
            _deny("CARD_AI_BACKLOG_DISABLED", "Платная генерация старого бэклога выключена")
        count = len(
            {
                r.cluster_id
                for r in rows
                if r.interview_id == interview_id
                and not r.manual
                and not r.maintenance
                and r.amount_usd > 0
            }
        )
        if not maintenance and count >= settings.card_ai_max_topics_per_interview:
            _deny("CARD_AI_TOPIC_LIMIT", "Достигнут лимит новых тем интервью")
    pledged = (
        [r for r in previous if r.validation_reserve_usd > 0]
        if operation == "validate_answer_contract"
        else []
    )
    pledge = sum((r.validation_reserve_usd for r in pledged), ZERO)
    collateral = (
        validation_pledge(request, tier) if operation == "generate_answer_contract" else ZERO
    )
    start, end = _day_bounds()
    daily_rows = [r for r in rows if daily_amount(r, start, end, now) > ZERO]
    interview_rows = [
        r for r in rows if r.interview_id == interview_id and not r.manual and not r.maintenance
    ]

    def check(
        items: list[CardAICharge], cap: Decimal, code: str, label: str, *, daily: bool = False
    ) -> None:
        def held(row: CardAICharge) -> Decimal:
            return daily_amount(row, start, end, now) if daily else row.amount_usd

        total = sum((held(r) for r in items), ZERO) - sum(
            (r.validation_reserve_usd for r in pledged if r in items), ZERO
        )
        needed = amount + collateral
        if total + needed > cap:
            inflight = sum(
                (held(r) for r in items if request_inflight(r, now)),
                ZERO,
            )
            if total - inflight + needed <= cap:
                _deny(
                    "CARD_AI_RESERVATION_BUSY",
                    "Бюджет временно занят выполняющимися запросами; "
                    "ожидается освобождение резерва",
                    retryable=True,
                )
            _deny(code, f"{label}. Остаток: ${max(cap - total, ZERO):.4f}")

    if not manual and not maintenance:
        check(
            interview_rows,
            settings.card_ai_budget_per_interview_usd,
            "CARD_AI_INTERVIEW_BUDGET",
            "Исчерпан бюджет новых тем интервью",
        )
    if maintenance:
        check(
            [r for r in daily_rows if r.maintenance],
            settings.card_ai_maintenance_budget_usd,
            "CARD_AI_MAINTENANCE_BUDGET",
            "Исчерпан бюджет обслуживания карточек",
            daily=True,
        )
    check(
        daily_rows,
        settings.card_ai_daily_budget_usd,
        "CARD_AI_DAILY_BUDGET",
        "Исчерпан суточный бюджет карточек",
        daily=True,
    )
    for row in pledged:
        row.amount_usd -= row.validation_reserve_usd
        row.validation_reserve_usd = ZERO
    session.add(
        CardAICharge(
            request_id=request_id,
            cluster_id=cluster_id,
            interview_id=interview_id,
            direction_id=cluster.direction_id,
            operation=operation,
            manual=manual,
            maintenance=maintenance,
            request_reserve_usd=amount,
            amount_usd=amount + collateral,
            validation_reserve_usd=collateral,
            reserve_expires_at=now + timedelta(hours=24),
            pledge_request_id=pledged[0].request_id if pledged else None,
            released_pledge_usd=pledge,
        )
    )


async def settle_card_request(
    session: AsyncSession, request_id: UUID, *, locked: bool = False
) -> None:
    if not locked:
        await acquire_card_budget_lock(session, "settle")
    charge = await session.get(CardAICharge, request_id, populate_existing=True)
    log = await session.get(AIRequestLog, request_id)
    if charge is None or log is None:
        return
    if log.estimated_cost_usd is not None:
        charge.amount_usd = log.estimated_cost_usd + charge.validation_reserve_usd
        charge.status = "settled"
        charge.settled_at = log.finished_at
        # A billed invalid response has no usable continuation.
        if log.status == "error" and charge.validation_reserve_usd:
            charge.amount_usd -= charge.validation_reserve_usd
            charge.validation_reserve_usd = ZERO
    elif log.error_code in FREE_ERRORS:
        charge.amount_usd = ZERO
        charge.validation_reserve_usd = ZERO
        charge.status = "free"
        charge.settled_at = log.finished_at
        charge.reason = log.error_code
        if charge.pledge_request_id is not None and charge.released_pledge_usd:
            owner = await session.get(CardAICharge, charge.pledge_request_id)
            if (
                owner is not None
                and owner.reserve_expires_at
                and owner.reserve_expires_at > datetime.now(UTC)
            ):
                owner.amount_usd += charge.released_pledge_usd
                owner.validation_reserve_usd += charge.released_pledge_usd
            charge.released_pledge_usd = ZERO
    elif log.finished_at is not None and charge.status != "written_off":
        charge.status = "unknown"
        charge.reason = log.error_code or "missing_usage"


async def release_validation_pledges(session: AsyncSession, cluster_id: UUID) -> None:
    await acquire_card_budget_lock(session, "release_pledge")
    for row in await session.scalars(
        select(CardAICharge).where(
            CardAICharge.cluster_id == cluster_id, CardAICharge.validation_reserve_usd > 0
        )
    ):
        row.amount_usd -= row.validation_reserve_usd
        row.validation_reserve_usd = ZERO


async def reconcile_card_charges(session: AsyncSession) -> None:
    # Called under the admission lock, and by the periodic recovery job.
    rows = list(
        await session.scalars(
            select(CardAICharge)
            .outerjoin(AIRequestLog, AIRequestLog.id == CardAICharge.request_id)
            .where(
                (
                    AIRequestLog.estimated_cost_usd.is_not(None)
                    & (
                        CardAICharge.amount_usd
                        != AIRequestLog.estimated_cost_usd + CardAICharge.validation_reserve_usd
                    )
                )
                | CardAICharge.status.in_(["reserved", "unknown"])
                | (CardAICharge.validation_reserve_usd > 0)
            )
        )
    )
    for row in rows:
        log = await session.get(AIRequestLog, row.request_id)
        if (
            log is not None
            and log.status == "started"
            and request_deadline(row) <= datetime.now(UTC)
        ):
            log.status = "interrupted"
            log.error_code = "interrupted"
            log.finished_at = datetime.now(UTC)
        if log is None and row.status == "reserved" and request_deadline(row) <= datetime.now(UTC):
            row.status = "unknown"
            row.reason = "interrupted"
        await settle_card_request(session, row.request_id, locked=True)
        if (
            row.validation_reserve_usd
            and row.reserve_expires_at
            and row.reserve_expires_at <= datetime.now(UTC)
        ):
            row.amount_usd -= row.validation_reserve_usd
            row.validation_reserve_usd = ZERO
    await session.flush()
