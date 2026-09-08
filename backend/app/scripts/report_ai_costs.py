"""Read-only daily report of OpenAI attempts recorded after the accounting migration."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import async_session_factory
from app.interviews.intelligence_models import AIRequestLog


async def daily_report(
    day: date,
    timezone: str,
    session_factory: async_sessionmaker[AsyncSession] = async_session_factory,
) -> dict[str, object]:
    zone = ZoneInfo(timezone)
    start = datetime.combine(day, time.min, zone).astimezone(UTC)
    end = datetime.combine(day + timedelta(days=1), time.min, zone).astimezone(UTC)
    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(
                        AIRequestLog.operation,
                        AIRequestLog.model,
                        AIRequestLog.service_tier,
                        func.count().label("attempts"),
                        func.count()
                        .filter(AIRequestLog.recovery.is_(True))
                        .label("recovery_attempts"),
                        func.count()
                        .filter(AIRequestLog.status == "started")
                        .label("unfinished_attempts"),
                        func.count().filter(AIRequestLog.status == "error").label("errors"),
                        func.count()
                        .filter(AIRequestLog.input_tokens.is_(None))
                        .label("unknown_usage_attempts"),
                        func.count()
                        .filter(AIRequestLog.estimated_cost_usd.is_(None))
                        .label("unpriced_attempts"),
                        func.sum(AIRequestLog.input_tokens).label("input_tokens"),
                        func.sum(AIRequestLog.cached_input_tokens).label("cached_input_tokens"),
                        func.sum(AIRequestLog.output_tokens).label("output_tokens"),
                        func.sum(AIRequestLog.reasoning_tokens).label("reasoning_tokens"),
                        func.sum(AIRequestLog.estimated_cost_usd).label("known_estimated_cost_usd"),
                    )
                    .where(
                        AIRequestLog.created_at >= start,
                        AIRequestLog.created_at < end,
                    )
                    .group_by(
                        AIRequestLog.operation,
                        AIRequestLog.model,
                        AIRequestLog.service_tier,
                    )
                    .order_by(func.sum(AIRequestLog.estimated_cost_usd).desc().nulls_last())
                )
            )
            .mappings()
            .all()
        )
    return {
        "date": day.isoformat(),
        "timezone": timezone,
        "note": "Recorded OpenAI attempts only; unknown costs and historical usage are not zero.",
        "groups": [dict(row) for row in rows],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat)
    parser.add_argument("--timezone", default="Europe/Moscow")
    args = parser.parse_args()
    day = args.date or datetime.now(ZoneInfo(args.timezone)).date()
    print(
        json.dumps(
            asyncio.run(daily_report(day, args.timezone)), ensure_ascii=False, indent=2, default=str
        )
    )


if __name__ == "__main__":
    main()
