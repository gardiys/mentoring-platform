"""Read-only card/Flex rollout metrics; no prompts, API calls or mutations."""

import argparse
import asyncio
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from statistics import median
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import async_session_factory
from app.interviews.card_ai_budget import FREE_ERRORS
from app.interviews.card_automation_models import AutomationDecision, CardAICharge, QuestionCluster
from app.interviews.card_automation_types import AutomationDecisionType
from app.interviews.card_cluster_workflow import manual_review_condition, not_selected_condition
from app.interviews.intelligence_ai import ANSWER_VALIDATION_PROMPT_VERSION
from app.interviews.intelligence_models import AIRequestLog, IntelligenceInterview


async def report(
    days: int = 7,
    session_factory: async_sessionmaker[AsyncSession] = async_session_factory,
) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(days=days)
    async with session_factory() as session:
        logs = list(
            await session.scalars(select(AIRequestLog).where(AIRequestLog.created_at >= since))
        )
        charges = list(
            await session.scalars(
                select(CardAICharge).where(
                    or_(
                        CardAICharge.created_at >= since,
                        CardAICharge.status.in_(["reserved", "unknown"]),
                        CardAICharge.validation_reserve_usd > 0,
                    )
                )
            )
        )
        interviews = list(
            await session.scalars(
                select(IntelligenceInterview).where(IntelligenceInterview.ai_started_at >= since)
            )
        )
        clusters = list(await session.scalars(select(QuestionCluster)))
        latest = list(
            await session.scalars(
                select(AutomationDecision)
                .where(
                    AutomationDecision.decision_type
                    == AutomationDecisionType.ANSWER_CONTRACT_VALIDATED
                )
                .distinct(AutomationDecision.entity_id)
                .order_by(
                    AutomationDecision.entity_id,
                    AutomationDecision.created_at.desc(),
                    AutomationDecision.id,
                )
            )
        )
        decisions = list(
            await session.scalars(
                select(AutomationDecision).where(
                    AutomationDecision.created_at >= since,
                    AutomationDecision.decision_type == AutomationDecisionType.CARD_AI_DEFERRED,
                )
            )
        )
        new_card_ids = set(
            await session.scalars(
                select(AutomationDecision.entity_id).where(
                    AutomationDecision.decision_type == AutomationDecisionType.CARD_CREATED,
                    AutomationDecision.created_at >= since,
                )
            )
        )
        manual = await session.scalar(
            select(func.count()).select_from(QuestionCluster).where(manual_review_condition())
        )
        deferred = await session.scalar(
            select(func.count()).select_from(QuestionCluster).where(not_selected_condition())
        )
    by_log = {log.id: log for log in logs}
    zero = Decimal("0")
    spend: defaultdict[str, Decimal] = defaultdict(lambda: zero)
    attempts: Counter[str] = Counter()

    def booked_cost(charge: CardAICharge) -> Decimal:
        log = by_log.get(charge.request_id)
        if log and log.estimated_cost_usd is not None:
            return log.estimated_cost_usd
        if charge.status == "written_off" and charge.created_at >= since:
            return charge.amount_usd - charge.validation_reserve_usd
        return zero

    for charge in charges:
        cost = booked_cost(charge)
        if cost:
            spend[str(charge.cluster_id)] += cost
            attempts[str(charge.cluster_id)] += 1
    usable = {str(id) for id in new_card_ids} & spend.keys()
    personal = sum(
        (
            log.estimated_cost_usd or zero
            for log in logs
            if log.cluster_id is None and log.interview_id is not None
        ),
        zero,
    )
    interview_spend: defaultdict[str, dict[str, Decimal]] = defaultdict(
        lambda: {"personal_known_usd": zero, "card_known_usd": zero, "manual_card_known_usd": zero}
    )
    for log in logs:
        if log.interview_id is not None and log.cluster_id is None:
            interview_spend[str(log.interview_id)]["personal_known_usd"] += (
                log.estimated_cost_usd or zero
            )
    for charge in charges:
        cost = booked_cost(charge)
        interview_spend[str(charge.interview_id)]["card_known_usd"] += cost
        if charge.manual:
            interview_spend[str(charge.interview_id)]["manual_card_known_usd"] += cost
    reserve_ratios: list[float] = []
    for charge in charges:
        priced_log = by_log.get(charge.request_id)
        if priced_log and priced_log.estimated_cost_usd and charge.request_reserve_usd > 0:
            reserve_ratios.append(float(charge.request_reserve_usd / priced_log.estimated_cost_usd))
    reserve_ratios.sort()
    request_reserves = sum(
        (
            c.amount_usd - c.validation_reserve_usd
            for c in charges
            if c.status in {"reserved", "unknown"}
        ),
        zero,
    )
    validation_pledges = sum((c.validation_reserve_usd for c in charges), zero)
    durations = {}
    for tier in ("flex", "default"):
        values = [
            (i.ai_ready_at - i.ai_started_at).total_seconds() / 60
            for i in interviews
            if i.ai_service_tier == tier
            and i.ai_ready_at
            and i.ai_started_at
            and i.ai_ready_at >= i.ai_started_at
        ]
        durations[tier] = {
            "measured": len(values),
            "median_minutes": round(median(values), 1) if values else None,
        }
    validation_by_id = {d.entity_id: d for d in latest}
    wave = Counter(
        str(c.direction_id)
        for c in clusters
        if c.linked_card_id is None
        and c.answer_validation is not None
        and (
            c.id not in validation_by_id
            or validation_by_id[c.id].prompt_version != ANSWER_VALIDATION_PROMPT_VERSION
        )
    )
    flex_errors = Counter(
        (str(log.interview_id), log.error_code)
        for log in logs
        if log.interview_id
        and log.service_tier == "flex"
        and log.error_code in {"RateLimitError", "APITimeoutError"}
    )
    return {
        "since_utc": since.isoformat(),
        "personal_ai_known_usd": personal,
        "known_costs_per_interview": dict(interview_spend),
        "unattributed_ai_known_usd": sum(
            (
                log.estimated_cost_usd or zero
                for log in logs
                if log.interview_id is None and log.cluster_id is None
            ),
            zero,
        ),
        "card_ai_known_usd": sum(spend.values(), zero),
        "card_ai_written_off_usd": sum(
            (
                c.amount_usd - c.validation_reserve_usd
                for c in charges
                if c.status == "written_off" and c.created_at >= since
            ),
            zero,
        ),
        "card_ai_reserves_usd": request_reserves + validation_pledges,
        "card_ai_request_reserves_usd": request_reserves,
        "card_ai_validation_pledges_usd": validation_pledges,
        "usable_new_cards": len(usable),
        # Include failed themes and repeated attempts: dividing only the spend
        # attributed to successful cards would hide the cost of wasted work.
        "known_usd_per_usable_card": sum(spend.values(), zero) / len(usable) if usable else None,
        "paid_attempts_per_theme": dict(attempts),
        "reserve_to_actual_ratio": {
            "measured": len(reserve_ratios),
            "median": median(reserve_ratios) if reserve_ratios else None,
            "p99": reserve_ratios[min(len(reserve_ratios) - 1, int(len(reserve_ratios) * 0.99))]
            if reserve_ratios
            else None,
        },
        "unknown_cost_attempts": len(
            {
                log.id
                for log in logs
                if log.estimated_cost_usd is None
                and log.error_code not in FREE_ERRORS
                and log.id not in {c.request_id for c in charges if c.status == "written_off"}
            }
            | {
                c.request_id
                for c in charges
                if c.status in {"reserved", "unknown"} and c.request_id not in by_log
            }
        ),
        "manual_queue_now": manual,
        "not_selected_now": deferred,
        "budget_refusals": dict(
            Counter(d.retrieval_scores.get("budget_reason", "unknown") for d in decisions)
        ),
        "duration_by_tier": durations,
        "standard_share_started": sum(i.ai_service_tier == "default" for i in interviews)
        / len(interviews)
        if interviews
        else None,
        "flex_errors_per_interview": [
            {"interview_id": id, "error": error, "count": n}
            for (id, error), n in flex_errors.items()
        ],
        "stale_validation_wave_by_direction": dict(wave),
        "note": (
            "Unknown costs remain unknown; USD, no exchange-rate assumptions. "
            "Queue history requires daily snapshots. Durations are measured only for "
            "new runs and first historical analyses with recorded completion times."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    if args.days < 1:
        parser.error("--days must be positive")
    print(json.dumps(asyncio.run(report(args.days)), default=str, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
