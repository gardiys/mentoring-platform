from __future__ import annotations

import argparse
import asyncio

from app.core.config import get_settings
from app.db import models as _db_models  # noqa: F401
from app.db.session import async_session_factory
from app.interviews.intelligence_ai import build_ai_provider
from app.interviews.question_embeddings import backfill_question_embedding_batch


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill cached embeddings for interview questions and cards."
    )
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--max-records", type=int, default=None)
    args = parser.parse_args()
    if args.batch_size < 1 or args.batch_size > 2_048:
        parser.error("--batch-size must be between 1 and 2048")
    if args.max_records is not None and args.max_records < 1:
        parser.error("--max-records must be positive")
    return args


async def _run(batch_size: int, max_records: int | None) -> int:
    provider = build_ai_provider(get_settings())
    total = 0
    request_count = 0
    input_tokens = 0
    models: set[str] = set()
    try:
        while max_records is None or total < max_records:
            current_limit = min(batch_size, max_records - total) if max_records else batch_size
            async with async_session_factory() as session:
                result = await backfill_question_embedding_batch(
                    session,
                    provider,
                    limit=current_limit,
                )
                await session.commit()
            total += result.refreshed
            request_count += len(result.usages)
            input_tokens += sum(usage.input_tokens for usage in result.usages)
            models.update(usage.model for usage in result.usages)
            if result.refreshed == 0:
                break
            print(
                "Question embeddings refreshed: "
                f"{total}; requests: {request_count}; input_tokens: {input_tokens}"
            )
    finally:
        await provider.close()
    print(
        "Question embedding usage: "
        f"models={','.join(sorted(models)) or '-'}; "
        f"requests={request_count}; input_tokens={input_tokens}"
    )
    return total


def main() -> None:
    args = _arguments()
    total = asyncio.run(_run(args.batch_size, args.max_records))
    print(f"Question embedding backfill complete: {total}")


if __name__ == "__main__":
    main()
