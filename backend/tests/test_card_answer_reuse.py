"""Paid-operation and publication regressions for shared interview/card answers."""

from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.interviews import card_automation_jobs as jobs
from app.interviews.card_automation_models import AutomationDecision, QuestionCluster
from app.interviews.card_automation_pipeline import answer_contract_from_analysis_draft
from app.interviews.card_automation_schemas import AnswerValidationResult
from app.interviews.card_automation_types import AnswerContractStatus, QuestionClusterStatus
from app.interviews.intelligence_ai import FakeInterviewAIProvider
from app.interviews.intelligence_checkpoints import InterviewAICheckpoints
from app.interviews.intelligence_models import IntelligenceQuestion, IntelligenceQuestionKind
from app.interviews.intelligence_reference_answers import published_review_reference
from app.interviews.models import InterviewCard, InterviewDeck
from tests.conftest import TestSession
from tests.test_card_auto_publish import ready as _ready
from tests.test_card_automation_jobs import RecordingRedis
from tests.test_card_automation_pipeline import _create_card, _create_source


@pytest.fixture(name="ready")
async def ready_for_reuse(seeded, monkeypatch):
    return await _ready.__wrapped__(seeded, monkeypatch)


DRAFT = "Python освобождает объекты с нулевым счётчиком ссылок и собирает недостижимые циклы."


class AttributingProvider(FakeInterviewAIProvider):
    def __init__(self, changes=None):
        super().__init__()
        self.changes = changes or {}
        self.repairs = []

    async def validate_answer_contract(self, question, contract, trusted_sources):
        result = await super().validate_answer_contract(question, contract, trusted_sources)
        return replace(
            result,
            output=AnswerValidationResult(
                supported=True,
                supporting_source_references=[trusted_sources[0]["source_id"]],
                question_is_self_contained=True,
                answer_is_substantive=True,
                generator_warnings_resolved=True,
                confidence=0.98,
            ).model_copy(update=self.changes),
        )

    async def generate_answer_contract(self, question, trusted_sources, *, repair_context=None):
        self.repairs.append(repair_context)
        return await super().generate_answer_contract(
            question, trusted_sources, repair_context=repair_context
        )


async def prepare_draft(ready):
    async with TestSession() as session:
        cluster = await session.get_one(QuestionCluster, ready[0])
        cluster.answer_contract = answer_contract_from_analysis_draft(DRAFT)
        cluster.answer_validation = None
        cluster.answer_status = None
        # The reference really contains the draft's claims; no inference from an ID.
        source = await session.get_one(InterviewCard, ready[2].card_id)
        source.answer_markdown = DRAFT
        await session.commit()


async def test_source_attribution_publishes_existing_text_without_generation(ready):
    await prepare_draft(ready)
    ai, redis = AttributingProvider(), RecordingRedis()
    ctx = {"ai_provider": ai, "redis": redis, "job_try": 1}
    await jobs.validate_cluster_answer(ctx, str(ready[0]), 1)
    await jobs.validate_cluster_answer(ctx, str(ready[0]), 1)
    async with TestSession() as session:
        cluster = await session.get_one(QuestionCluster, ready[0])
        assert cluster.status == QuestionClusterStatus.CARD_CREATED
        assert cluster.answer_contract["short_answer"] == DRAFT
        assert cluster.answer_contract["source_references"] == [ready[3]]
        card = await session.get_one(InterviewCard, cluster.linked_card_id)
        assert DRAFT in card.answer_markdown
        decisions = list(
            await session.scalars(
                select(AutomationDecision).where(
                    AutomationDecision.entity_id == cluster.id,
                )
            )
        )
        assert any(
            d.judge_result and d.judge_result.get("supporting_source_references") == [ready[3]]
            for d in decisions
        )
    assert ai.answer_contract_calls == []
    assert len(ai.answer_validation_calls) == 1
    assert ai.answer_validation_calls[0]["contract"]["source_references"] == []


async def test_statistics_preserve_unverified_review_and_schedule_validation(ready):
    await prepare_draft(ready)
    redis = RecordingRedis()
    await jobs.recalculate_cluster_stats({"redis": redis}, str(ready[0]), 1)
    async with TestSession() as session:
        cluster = await session.get_one(QuestionCluster, ready[0])
        assert cluster.answer_contract["short_answer"] == DRAFT
    assert [name for name, _, _ in redis.calls] == ["validate_cluster_answer"]


@pytest.mark.parametrize(
    "changes",
    [
        {"supporting_source_references": ["interview_card:" + str(uuid4())]},
        {"supporting_source_references": []},
        {"supported": False, "missing_required_points": ["Не объяснён сбор циклов"]},
        {"unverified_personal_claims": ["Выдуманный опыт"]},
        {"contradictions": ["Противоречит материалам"]},
    ],
)
async def test_missing_or_bad_evidence_never_publishes_and_keeps_draft(ready, changes):
    await prepare_draft(ready)
    ai = AttributingProvider(changes)
    await jobs.validate_cluster_answer(
        {"ai_provider": ai, "redis": RecordingRedis(), "job_try": 1}, str(ready[0]), 1
    )
    async with TestSession() as session:
        cluster = await session.get_one(QuestionCluster, ready[0])
        assert cluster.linked_card_id is None
        assert cluster.answer_status == AnswerContractStatus.REVIEW_PENDING
        assert cluster.answer_contract["short_answer"] == DRAFT
        assert cluster.answer_contract["source_references"] == []
    assert ai.answer_contract_calls == []


async def test_incomplete_review_is_repaired_with_preserved_answer_and_findings(ready):
    await prepare_draft(ready)
    ai = AttributingProvider(
        {"supported": False, "missing_required_points": ["Не объяснён сбор циклов"]}
    )
    redis = RecordingRedis()
    ctx = {"ai_provider": ai, "redis": redis, "job_try": 1}
    await jobs.validate_cluster_answer(ctx, str(ready[0]), 1)
    await jobs.review_cluster_for_automation(ctx, str(ready[0]), 1)
    await jobs.generate_cluster_candidate(ctx, str(ready[0]), 1)
    assert len(ai.repairs) == 1
    assert ai.repairs[0]["previous_contract"]["short_answer"] == DRAFT
    assert ai.repairs[0]["validation"]["missing_required_points"] == ["Не объяснён сбор циклов"]
    assert redis.calls[-1][0] == "validate_cluster_answer"


@pytest.mark.parametrize(
    "blocked", ["other_direction", "unpublished", "hidden_deck", "ambiguous", "different_question"]
)
async def test_shared_reference_requires_unique_published_exact_match(seeded, blocked):
    question = "Что такое GIL?"
    fixture = await _create_card(seeded, question)
    if blocked == "ambiguous":
        await _create_card(seeded, question)
    async with TestSession() as session:
        card = await session.get_one(InterviewCard, fixture.card_id)
        deck = await session.get_one(InterviewDeck, fixture.deck_id)
        if blocked == "unpublished":
            card.is_published = False
        elif blocked == "hidden_deck":
            deck.is_published = False
        elif blocked == "other_direction":
            deck.track_id = seeded.go_track_id
        elif blocked == "different_question":
            card.question_markdown = "Как GIL влияет на многопоточность?"
        await session.flush()
        assert (
            await published_review_reference(
                session, question=question, direction_id=seeded.python_track_id
            )
            is None
        )


async def test_reference_changes_invalidate_review_checkpoint_without_becoming_candidate_speech(
    seeded,
):
    question = "Что такое GIL?"
    fixture = await _create_card(seeded, question)
    occurrence = await _create_source(seeded, question, answer_text="Не знаю.")
    ai = FakeInterviewAIProvider()
    async with TestSession() as session:
        q = await session.get_one(IntelligenceQuestion, occurrence.question_id)
        interview_id = q.interview_id
        reference = await published_review_reference(
            session, question=question, direction_id=seeded.python_track_id
        )
    assert reference is not None
    checkpoints = InterviewAICheckpoints(TestSession, interview_id, ai)
    kwargs = dict(
        question_id=occurrence.question_id,
        question=question,
        answer="Не знаю.",
        category="Python",
        question_kind=IntelligenceQuestionKind.TECHNICAL,
        context="",
        direction="python",
        reference_answer=reference,
    )
    await checkpoints.review(**kwargs)
    await checkpoints.review(**kwargs)
    assert len(ai.review_calls) == 1
    assert ai.review_calls[0]["answer"] == "Не знаю."
    assert ai.review_calls[0]["reference_answer"]["card_id"] == str(fixture.card_id)
    async with TestSession() as session:
        card = await session.get_one(InterviewCard, fixture.card_id)
        card.answer_markdown = "Обновлённый проверенный ответ."
        await session.commit()
        kwargs["reference_answer"] = await published_review_reference(
            session, question=question, direction_id=seeded.python_track_id
        )
    await checkpoints.review(**kwargs)
    assert len(ai.review_calls) == 2


async def test_automatic_clustering_keeps_interview_review(seeded):
    from app.interviews.intelligence_models import IntelligenceAssessment
    from tests.test_card_automation_pipeline import _configure, _process

    await _configure(seeded, global_auto_publish_enabled=True, shadow_mode=False)
    source = await _create_source(
        seeded, "Как работают дескрипторы в Python?", assessment=IntelligenceAssessment.INCORRECT
    )
    ai = FakeInterviewAIProvider()
    await _process(ai, source.question_id)
    async with TestSession() as session:
        question = await session.get_one(IntelligenceQuestion, source.question_id)
        cluster = await session.get_one(QuestionCluster, question.cluster_id)
        assert cluster.answer_contract["short_answer"] == "Краткий корректный ответ."
        assert cluster.answer_contract["source_references"] == []
    assert ai.answer_contract_calls == []


async def test_automatic_generation_uses_late_review_without_llm_generation(ready):
    from app.interviews.intelligence_models import (
        IntelligenceAnswer,
        IntelligenceAnswerReview,
        IntelligenceAssessment,
        IntelligenceReviewSource,
        IntelligenceReviewStatus,
    )

    async with TestSession() as session:
        cluster = await session.get_one(QuestionCluster, ready[0])
        cluster.answer_contract = cluster.answer_validation = cluster.answer_status = None
        answer = await session.scalar(
            select(IntelligenceAnswer).where(IntelligenceAnswer.question_id == ready[1])
        )
        session.add(
            IntelligenceAnswerReview(
                answer_id=answer.id,
                source=IntelligenceReviewSource.AI,
                status=IntelligenceReviewStatus.SUGGESTED,
                assessment=IntelligenceAssessment.INCORRECT,
                summary="Нужно дополнить ответ.",
                suggested_better_answer=DRAFT,
            )
        )
        await session.commit()
    ai, redis = AttributingProvider(), RecordingRedis()
    await jobs.generate_cluster_candidate({"ai_provider": ai, "redis": redis}, str(ready[0]), 1)
    async with TestSession() as session:
        cluster = await session.get_one(QuestionCluster, ready[0])
        assert cluster.answer_contract["short_answer"] == DRAFT
        assert cluster.answer_contract["source_references"] == []
    assert ai.answer_contract_calls == []
    assert redis.calls[-1][0] == "validate_cluster_answer"


async def test_source_order_change_does_not_repeat_paid_validation(ready, seeded, monkeypatch):
    from app.roadmaps.models import Topic

    await prepare_draft(ready)
    async with TestSession() as session:
        topic = await session.get_one(Topic, seeded.topic_ids[0])
        topic.content_markdown = DRAFT
        await session.commit()
    load_sources = jobs.load_trusted_sources
    calls = []

    async def reordered(session, cluster, **kwargs):
        sources = await load_sources(session, cluster, **kwargs)
        if len(sources) < 2:
            return sources
        calls.append(True)
        return sources if len(calls) == 1 else sources[::-1]

    monkeypatch.setattr(jobs, "load_trusted_sources", reordered)
    ai = AttributingProvider()
    await jobs.validate_cluster_answer(
        {"ai_provider": ai, "redis": RecordingRedis()}, str(ready[0]), 1
    )
    async with TestSession() as session:
        cluster = await session.get_one(QuestionCluster, ready[0])
        assert cluster.status == QuestionClusterStatus.CARD_CREATED
    assert len(ai.answer_validation_calls) == 1
    assert len(calls) >= 2
