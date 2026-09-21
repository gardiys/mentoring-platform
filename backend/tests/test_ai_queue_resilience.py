import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from arq import Retry
from arq.constants import retry_key_prefix
from openai import RateLimitError
from sqlalchemy import func, select

from app.interviews import card_automation_jobs as jobs
from app.interviews.ai_accounting import estimated_cost
from app.interviews.ai_rate_limit import (
    COOLDOWN_ERROR,
    ModelCooldown,
    retry_after_seconds,
)
from app.interviews.card_automation_models import AutomationDecision, QuestionCluster
from app.interviews.card_automation_types import AnswerContractStatus, QuestionClusterStatus
from app.interviews.intelligence_ai import FakeInterviewAIProvider, InterviewAIError
from app.interviews.intelligence_models import AIRequestLog
from tests.conftest import TestSession
from tests.test_ai_cost_optimizations import SmallOutput, _provider, _response
from tests.test_card_auto_publish import ready as ready_fixture
from tests.test_card_automation_jobs import RecordingRedis
from tests.test_card_automation_service import _cluster

ready = ready_fixture


@pytest.fixture
async def cooldown():
    url = os.getenv("TEST_REDIS_URL")
    if not url:
        pytest.skip("Set TEST_REDIS_URL to an isolated Redis for cooldown integration tests")
    gate = ModelCooldown(url, account_key=f"offline-{uuid4()}")
    try:
        yield gate
    finally:
        keys = [
            key async for key in gate.redis.scan_iter(match=f"ai:model-cooldown:v1:{gate.scope}:*")
        ]
        if keys:
            await gate.redis.delete(*keys)
        await gate.redis.delete(gate.quota_key())
        await gate.close()


async def test_source_blocked_backlog_cannot_starve_new_answers(ready, seeded):
    async with TestSession() as session:
        blocked = []
        for index in range(205):
            cluster = _cluster(
                seeded.python_track_id, index, status=QuestionClusterStatus.NEEDS_REVIEW
            )
            cluster.canonical_question = f"недостающийматериал{index}"
            cluster.normalized_canonical_question = cluster.canonical_question
            cluster.answer_status = AnswerContractStatus.NEEDS_EXPERT_SOURCE
            cluster.membership_revision = cluster.stats_revision = 1
            blocked.append(cluster)
        fresh = _cluster(seeded.python_track_id, 999, status=QuestionClusterStatus.NEEDS_REVIEW)
        fresh.membership_revision = fresh.stats_revision = 1
        session.add_all([*blocked, fresh])
        await session.commit()
    redis = RecordingRedis()
    await jobs.reconcile_card_automation_jobs({"redis": redis})
    queued_ids = {args[0] for _, args, _ in redis.calls}
    assert str(fresh.id) in queued_ids and str(ready[0]) in queued_ids
    assert not queued_ids.intersection(str(c.id) for c in blocked)
    async with TestSession() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(QuestionCluster)
                .where(QuestionCluster.source_retry_after.is_not(None))
            )
            == 50
        )
    await jobs.reconcile_card_automation_jobs({"redis": RecordingRedis()})
    async with TestSession() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(QuestionCluster)
                .where(QuestionCluster.source_retry_after.is_not(None))
            )
            == 100
        )


async def test_source_recheck_waits_then_recovers_without_ai(ready):
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        cluster.answer_contract = cluster.answer_validation = None
        cluster.answer_status = AnswerContractStatus.NEEDS_EXPERT_SOURCE
        cluster.source_retry_after = datetime.now(UTC) + timedelta(hours=6)
        await session.commit()
    assert await jobs.recheck_source_blocked_clusters() == 0
    ai = FakeInterviewAIProvider()
    await jobs.generate_cluster_candidate(
        {"redis": RecordingRedis(), "ai_provider": ai}, str(ready[0]), 1
    )
    assert not ai.answer_contract_calls
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        cluster.source_retry_after = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    assert await jobs.recheck_source_blocked_clusters() == 1
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        assert cluster.answer_status is None and cluster.source_retry_after is None


async def test_shared_cooldown_is_model_scoped_atomic_and_does_not_shorten(cooldown):
    other_worker = ModelCooldown(os.environ["TEST_REDIS_URL"], account_key="unused")
    other_worker.scope = cooldown.scope
    try:
        await asyncio.gather(cooldown.extend("terra", 200), other_worker.extend("terra", 1))
        assert await other_worker.remaining("terra") > 190
        assert await other_worker.remaining("luna") == 0
        assert "offline" not in cooldown.key("terra")
        await cooldown.redis.delete(cooldown.key("terra"))
        assert await other_worker.remaining("terra") == 0
    finally:
        await other_worker.close()


async def test_429_stops_other_workers_before_request_or_accounting(cooldown):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            429,
            headers={"Retry-After": "321"},
            json={
                "error": {
                    "message": "Slow down",
                    "type": "rate_limit_exceeded",
                    "code": "rate_limit_exceeded",
                }
            },
        )

    first = await _provider(handler)
    second = await _provider(handler)
    first.model_cooldown = second.model_cooldown = cooldown
    try:
        with pytest.raises(RateLimitError):
            await first._request(
                operation="route_question", model="terra", input="test", text_format=SmallOutput
            )
        with pytest.raises(InterviewAIError) as blocked:
            await second._request(
                operation="route_question", model="terra", input="test", text_format=SmallOutput
            )
        assert blocked.value.code == COOLDOWN_ERROR
        assert blocked.value.retry_after_seconds > 310
        assert len(requests) == 1
        async with TestSession() as session:
            assert await session.scalar(select(func.count()).select_from(AIRequestLog)) == 1
    finally:
        first.model_cooldown = second.model_cooldown = None
        await first.close()
        await second.close()


async def test_shared_wait_does_not_exhaust_last_job_attempt_or_fail_cluster(ready, cooldown):
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        cluster.answer_status = cluster.answer_validation = None
        await session.commit()

    class PausedProvider(FakeInterviewAIProvider):
        async def validate_answer_contract(self, **kwargs):
            raise InterviewAIError(COOLDOWN_ERROR, "Wait", retryable=True, retry_after_seconds=90)

    job_id = f"cooldown-test-{uuid4()}"
    key = retry_key_prefix + job_id
    await cooldown.redis.set(key, 4, ex=600)
    try:
        with pytest.raises(Retry) as deferred:
            await jobs.validate_cluster_answer(
                {
                    "redis": cooldown.redis,
                    "job_id": job_id,
                    "job_try": 4,
                    "ai_provider": PausedProvider(),
                },
                str(ready[0]),
                1,
            )
        assert deferred.value.defer_score >= 90_000
        assert int(await cooldown.redis.get(key)) == 3
        async with TestSession() as session:
            cluster = await session.get(QuestionCluster, ready[0])
            assert cluster.answer_status is None and cluster.answer_validation is None
            assert await session.scalar(select(func.count()).select_from(AutomationDecision)) == 0
    finally:
        await cooldown.redis.delete(key)


def test_retry_after_headers_respect_server_delay():
    assert retry_after_seconds(httpx.Headers({"Retry-After": "7200"})) == 7200
    assert retry_after_seconds(httpx.Headers({"Retry-After-Ms": "1500"})) == 1.5
    assert retry_after_seconds(httpx.Headers({"Retry-After": "NaN"})) == 60
    assert retry_after_seconds(httpx.Headers({"Retry-After": "-2"})) == 60
    from email.utils import format_datetime

    date = format_datetime(datetime.now(UTC) + timedelta(minutes=5), usegmt=True)
    assert 298 < retry_after_seconds(httpx.Headers({"Retry-After": date})) <= 300


@pytest.mark.parametrize(
    "model, tier, expected",
    [
        ("gpt-5.6-terra", "default", "0.009350"),
        ("gpt-5.6-terra-2026-09-01", "flex", "0.004675"),
        ("gpt-5.6-luna", "default", "0.000935"),
        ("gpt-5.6-luna", "batch", "0.0004675"),
        ("gpt-5.6-luna", "priority", "0.00187"),
        ("gpt-5.6-luna", "fast", "0.00187"),
    ],
)
def test_model_pricing_includes_cache_reads_writes_and_tier(model, tier, expected):
    # 2,000 input = 1,000 ordinary + 500 read + 500 written; 500 output.
    assert estimated_cost(model, tier, 2000, 500, 500, cache_write_tokens=500) == Decimal(expected)


def test_long_context_and_unknown_usage_never_silently_underprice():
    assert estimated_cost(
        "gpt-5.6-terra", "default", 272_000, 0, 1000, cache_write_tokens=0
    ) == Decimal("0.556")
    assert estimated_cost(
        "gpt-5.6-terra", "default", 272_001, 0, 1000, cache_write_tokens=0
    ) == Decimal("1.106004")
    assert estimated_cost("gpt-5.6-terra", "default", 1000, 0, 1000) is None
    assert (
        estimated_cost("gpt-5.6-terra-custom", "flex", 1000, 0, 1000, cache_write_tokens=0) is None
    )
    assert estimated_cost("gpt-5.6-terra", "unknown", 1000, 0, 1000, cache_write_tokens=0) is None
    assert (
        estimated_cost("gpt-5.6-terra", "default", 1000, 500, 1000, cache_write_tokens=501) is None
    )


async def test_recorder_prices_actual_response_model_tier_and_retains_write_tokens():
    payload = _response('{"value":1}', tier="flex")
    payload["model"] = "gpt-5.6-luna"
    payload["usage"]["input_tokens_details"]["cache_write_tokens"] = 200
    provider = await _provider(lambda request: httpx.Response(200, json=payload))
    try:
        await provider._request(
            operation="route_question",
            model="requested-alias",
            input="test",
            text_format=SmallOutput,
        )
    finally:
        await provider.close()
    async with TestSession() as session:
        row = await session.scalar(select(AIRequestLog))
        assert row.model == "gpt-5.6-luna" and row.service_tier == "flex"
        assert row.cache_write_tokens == 200
        assert row.estimated_cost_usd == Decimal("0.000333")
        assert row.pricing_version == "openai-public-2026-09-22"


async def test_real_arq_cooldown_retry_keeps_one_attempt_budget(cooldown):
    from arq.connections import RedisSettings, create_pool
    from arq.worker import Worker, func

    from app.interviews.ai_rate_limit import defer_model_cooldown

    pool = await create_pool(RedisSettings.from_dsn(os.environ["TEST_REDIS_URL"]))
    queue = f"test-cooldown-queue:{uuid4()}"
    attempts = []

    async def paused_job(ctx):
        attempts.append(ctx["job_try"])
        if len(attempts) == 1:
            await defer_model_cooldown(
                ctx,
                InterviewAIError(
                    COOLDOWN_ERROR,
                    "Wait",
                    retryable=True,
                    retry_after_seconds=10,
                ),
            )

    job = await pool.enqueue_job("paused_job", _queue_name=queue)
    worker = Worker(
        [func(paused_job, name="paused_job")],
        redis_pool=pool,
        queue_name=queue,
        burst=True,
        max_tries=1,
        max_burst_jobs=1,
        handle_signals=False,
        poll_delay=0.01,
        keep_result=0,
    )
    resumed_worker = Worker(
        [func(paused_job, name="paused_job")],
        redis_pool=pool,
        queue_name=queue,
        burst=True,
        max_tries=1,
        max_burst_jobs=1,
        handle_signals=False,
        poll_delay=0.01,
        keep_result=0,
    )
    try:
        await asyncio.wait_for(worker.main(), timeout=5)
        await pool.zadd(queue, {job.job_id: 1})
        # Run the same task after the deferred deadline, with no real sleep.
        await asyncio.wait_for(resumed_worker.main(), timeout=5)
        assert attempts == [1, 1]
        assert resumed_worker.jobs_complete == 1
        assert worker.jobs_failed == resumed_worker.jobs_failed == 0
    finally:
        await pool.delete(queue, retry_key_prefix + job.job_id)
        await worker.close()
        await resumed_worker.close()


async def test_quota_errors_do_not_pause_other_requests(cooldown):
    provider = await _provider(
        lambda request: httpx.Response(
            429,
            json={
                "error": {
                    "message": "Quota",
                    "type": "insufficient_quota",
                    "code": "insufficient_quota",
                }
            },
        )
    )
    provider.model_cooldown = cooldown
    try:
        with pytest.raises(RateLimitError):
            await provider._request(
                operation="route_question", model="terra", input="test", text_format=SmallOutput
            )
        assert await cooldown.remaining("terra") == 0
        assert await cooldown.quota_remaining() > 3500
        # The account-level pause also blocks other models before another paid request.
        with pytest.raises(InterviewAIError) as blocked:
            await provider._request(
                operation="route_question", model="luna", input="test", text_format=SmallOutput
            )
        assert blocked.value.code == "OPENAI_QUOTA_EXCEEDED"
        async with TestSession() as session:
            assert await session.scalar(select(func.count()).select_from(AIRequestLog)) == 1
    finally:
        provider.model_cooldown = None
        await provider.close()


async def test_queue_pricing_migration_preserves_existing_clusters(ready):
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect

    from tests.conftest import test_engine

    spec = importlib.util.spec_from_file_location(
        "queue_pricing_migration",
        Path(__file__).parents[1] / "migrations/versions/20260922_0089_ai_queue_and_pricing.py",
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def migrate(connection):
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            assert "source_retry_after" not in {
                c["name"] for c in inspect(connection).get_columns("question_clusters")
            }
            migration.upgrade()
            assert "cache_write_tokens" in {
                c["name"] for c in inspect(connection).get_columns("ai_request_logs")
            }

    async with test_engine.begin() as connection:
        await connection.run_sync(migrate)
    async with TestSession() as session:
        cluster = await session.get(QuestionCluster, ready[0])
        assert cluster.answer_contract and cluster.source_retry_after is None
