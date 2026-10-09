from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import async_session_factory
from app.interviews.ai_pricing import PRICING_VERSION, _count
from app.interviews.ai_pricing import estimated_cost as estimated_cost
from app.interviews.intelligence_models import AIRequestLog

logger = logging.getLogger(__name__)


class AIRequestRecorder:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] = async_session_factory,
    ) -> None:
        self.session_factory = session_factory

    async def start(
        self,
        operation: str,
        model: str,
        tier: str,
        recovery: bool,
        *,
        request: dict[str, Any] | None = None,
    ) -> UUID:
        # Persist intent before spending. An interrupted/unknown call is not a zero-cost call.
        async with self.session_factory() as session:
            row = AIRequestLog(
                operation=operation,
                model=model,
                service_tier=tier,
                status="started",
                recovery=recovery,
            )
            from app.interviews.intelligence_request_policy import interview_request_id

            row.interview_id = interview_request_id.get()
            session.add(row)
            await session.flush()
            if request is not None:
                from app.interviews.card_ai_budget import reserve_card_request

                await reserve_card_request(session, row.id, operation, model, tier, request)
                from app.interviews.card_ai_budget import card_budget_context
                from app.interviews.card_automation_models import CardAICharge

                context = card_budget_context.get()
                if context is not None:
                    charge = await session.get(CardAICharge, row.id)
                    row.cluster_id = context[0]
                    row.interview_id = charge.interview_id if charge is not None else None
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
                "status": "interrupted" if error_code == "interrupted" else "error",
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
                operation = await session.scalar(
                    select(AIRequestLog.operation).where(AIRequestLog.id == call_id)
                )
            if operation in {"generate_answer_contract", "validate_answer_contract"}:
                from app.interviews.card_ai_budget import settle_card_request

                async with self.session_factory() as session:
                    await settle_card_request(session, call_id)
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
