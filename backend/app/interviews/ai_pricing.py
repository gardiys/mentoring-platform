"""Pure pricing rules shared by startup validation and financial accounting."""

import re
from decimal import Decimal

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
