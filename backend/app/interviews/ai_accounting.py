from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import async_session_factory
from app.interviews.intelligence_models import AIRequestLog

logger = logging.getLogger(__name__)
PRICING_VERSION = "openai-public-2026-09-22"
# https://developers.openai.com/api/docs/pricing (verified 2026-09-22).
# Rates are USD / million tokens: ordinary input, cached input, output.
_TEXT_PRICES = {
    "gpt-5-mini": ("0.25", "0.025", "2"),
    "gpt-5.6-terra": ("2", "0.2", "12"),
    "gpt-5.6-luna": ("0.2", "0.02", "1.2"),
}


def pricing_model(model: str) -> str:
    """Recognize dated snapshots of supported families, never similarly named models."""
    return re.sub(r"-\d{4}-\d{2}-\d{2}$", "", model)


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def estimated_cost(
    model: str,
    tier: str,
    input_tokens: int,
    cached_tokens: int,
    output_tokens: int,
    *,
    cache_write_tokens: int | None = None,
) -> Decimal | None:
    """Estimate only known prices and complete, consistent token usage."""
    model = pricing_model(model)
    if min(input_tokens, cached_tokens, output_tokens) < 0 or cached_tokens > input_tokens:
        return None
    writes = cache_write_tokens or 0
    if writes < 0 or writes + cached_tokens > input_tokens:
        return None
    if model in _TEXT_PRICES:
        if tier not in {"default", "flex", "batch", "priority", "fast"}:
            return None
        input_rate, cached_rate, output_rate = map(Decimal, _TEXT_PRICES[model])
        has_write_pricing = model.startswith("gpt-5.6-")
        # Old logs lack write-token details. Do not silently count them as ordinary input.
        if has_write_pricing and cache_write_tokens is None:
            return None
        if not has_write_pricing and writes:
            return None
        multiplier = Decimal("0.5") if tier in {"flex", "batch"} else Decimal("1")
        if tier in {"priority", "fast"}:
            multiplier = Decimal("2") if has_write_pricing else Decimal("1.8")
        if has_write_pricing and input_tokens > 272_000:
            input_rate *= 2
            cached_rate *= 2
            output_rate *= Decimal("1.5")
        write_rate = input_rate * Decimal("1.25")
    elif model == "text-embedding-3-small" and tier == "default" and not writes:
        input_rate, cached_rate, output_rate, write_rate = map(Decimal, ("0.02", "0.02", "0", "0"))
        multiplier = Decimal("1")
    else:
        return None
    return (
        (
            (input_tokens - cached_tokens - writes) * input_rate
            + cached_tokens * cached_rate
            + writes * write_rate
            + output_tokens * output_rate
        )
        * multiplier
        / Decimal(1_000_000)
    ).quantize(Decimal("0.0000000001"))


class AIRequestRecorder:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] = async_session_factory,
    ) -> None:
        self.session_factory = session_factory

    async def start(self, operation: str, model: str, tier: str, recovery: bool) -> UUID:
        # Persist intent before spending. An interrupted/unknown call is not a zero-cost call.
        async with self.session_factory() as session:
            row = AIRequestLog(
                operation=operation,
                model=model,
                service_tier=tier,
                status="started",
                recovery=recovery,
            )
            session.add(row)
            await session.commit()
            return row.id

    async def received(
        self,
        call_id: UUID,
        payload: dict[str, Any],
        request_id: str | None,
        model: str,
        tier: str,
    ) -> None:
        values: dict[str, Any] = {
            "status": "received",
            "finished_at": datetime.now(UTC),
            "provider_request_id": request_id,
            "response_id": payload.get("id"),
            "model": str(payload.get("model") or model),
            "service_tier": str(payload.get("service_tier") or tier),
        }
        usage = payload.get("usage")
        if isinstance(usage, dict):
            input_tokens = _count(usage.get("input_tokens", usage.get("prompt_tokens")))
            output_tokens = _count(
                usage.get("output_tokens", 0 if "prompt_tokens" in usage else None)
            )
            if input_tokens is None or output_tokens is None:
                # Missing usage is unknown, even on a successful HTTP response.
                await self._update(call_id, values)
                return
            input_details = usage.get("input_tokens_details")
            output_details = usage.get("output_tokens_details")
            cached = min(
                (_count(input_details.get("cached_tokens")) or 0)
                if isinstance(input_details, dict)
                else 0,
                input_tokens,
            )
            reasoning = min(
                (_count(output_details.get("reasoning_tokens")) or 0)
                if isinstance(output_details, dict)
                else 0,
                output_tokens,
            )
            writes = (
                _count(input_details.get("cache_write_tokens"))
                if isinstance(input_details, dict)
                else None
            )
            cost = estimated_cost(
                values["model"],
                values["service_tier"],
                input_tokens,
                cached,
                output_tokens,
                cache_write_tokens=writes,
            )
            values.update(
                input_tokens=input_tokens,
                cached_input_tokens=cached,
                cache_write_tokens=writes,
                output_tokens=output_tokens,
                reasoning_tokens=reasoning,
                estimated_cost_usd=cost,
                pricing_version=PRICING_VERSION if cost is not None else None,
            )
        await self._update(call_id, values)

    async def failed(self, call_id: UUID, error_code: str) -> None:
        await self._update(
            call_id,
            {
                "status": "error",
                "error_code": error_code[:100],
                "finished_at": datetime.now(UTC),
            },
        )

    async def _update(self, call_id: UUID, values: dict[str, Any]) -> None:
        try:
            async with self.session_factory() as session:
                await session.execute(
                    update(AIRequestLog).where(AIRequestLog.id == call_id).values(**values)
                )
                await session.commit()
        except Exception:
            # A billing DB failure after a paid response must not trigger another paid request.
            # Only financial metadata is logged; the durable started row remains reconcilable.
            logger.error(
                "AI accounting persistence failed call_id=%s metadata=%s",
                call_id,
                values,
                exc_info=True,
            )
