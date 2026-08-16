from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import event, func, select

from app.interviews import card_automation_service
from app.interviews.card_automation_models import (
    AutomationDecision,
    CardAutomationSettings,
    PersonalReviewItem,
    QuestionCluster,
)
from app.interviews.card_automation_schemas import (
    AnswerContract,
    AutomationDecisionOverrideMutation,
    CardAutomationMetricsFilters,
    CardAutomationSettingsUpdate,
    PersonalReviewItemCorrectionMutation,
    PersonalReviewItemListFilters,
    PersonalReviewItemReviewMutation,
    QuestionClusterAction,
    QuestionClusterActionMutation,
    QuestionClusterAnswerGenerationMutation,
    QuestionClusterCreateCardMutation,
    QuestionClusterDraftMutation,
    QuestionClusterLinkCardMutation,
    QuestionClusterListFilters,
    QuestionClusterMergeMutation,
    QuestionClusterSplitMutation,
    QuestionOccurrenceReprocessMutation,
)
from app.interviews.card_automation_service import (
    correct_personal_review_item,
    create_question_cluster_card,
    get_card_automation_metrics,
    link_question_cluster_card,
    list_managed_personal_review_items,
    list_personal_review_items,
    list_question_clusters,
    mark_question_cluster_important,
    merge_question_clusters,
    reopen_question_cluster,
    review_personal_review_item,
    split_question_cluster,
    update_card_automation_settings,
    update_question_cluster_draft,
)
from app.interviews.card_automation_types import (
    AnswerContractStatus,
    AutomationDecisionSource,
    AutomationDecisionType,
    LearningObjectType,
    PersonalReviewStatus,
    QuestionClusterStatus,
    QuestionOccurrenceStatus,
)
from app.interviews.intelligence_models import (
    IntelligenceDifficulty,
    IntelligenceInterview,
    IntelligenceInterviewType,
    IntelligenceQuestion,
    IntelligenceQuestionKind,
    IntelligenceQuestionModerationStatus,
)
from app.interviews.intelligence_schemas import IntelligenceQuestionModerationMutation
from app.interviews.intelligence_service import moderate_intelligence_question
from app.interviews.models import (
    Company,
    InterviewCard,
    InterviewCardFrequency,
    InterviewDeck,
    InterviewProcess,
    InterviewProcessStage,
    InterviewProcessStatus,
    InterviewReviewRating,
    InterviewStageType,
)
from app.interviews.question_matching import normalize_question
from app.users.models import User
from tests.conftest import SeededData, TestSession, test_engine


def _cluster(direction_id: UUID, index: int, *, status: QuestionClusterStatus) -> QuestionCluster:
    question = f"What is Python descriptor number {index}?"
    return QuestionCluster(
        id=uuid4(),
        direction_id=direction_id,
        status=status,
        canonical_question=question,
        normalized_canonical_question=question.lower(),
        learning_object_type=LearningObjectType.OPEN_TECHNICAL_QUESTION,
    )


def _topic_catalog(
    direction_id: UUID,
    *categories: str,
) -> tuple[InterviewDeck, list[InterviewCard]]:
    deck = InterviewDeck(
        id=uuid4(),
        track_id=direction_id,
        slug=f"topics-{uuid4().hex}",
        title="Existing interview topics",
        position=0,
        is_published=True,
    )
    cards = [
        InterviewCard(
            id=uuid4(),
            deck_id=deck.id,
            slug=f"topic-{uuid4().hex}",
            category=category,
            question_markdown=f"Existing question for {category}",
            answer_markdown="Existing answer",
            frequency=InterviewCardFrequency.OCCASIONAL,
            position=index,
            is_published=True,
        )
        for index, category in enumerate(categories)
    ]
    return deck, cards


def test_decision_override_rejects_entity_target_mismatch() -> None:
    original = AutomationDecision(
        id=uuid4(),
        entity_type="cluster",
        entity_id=uuid4(),
        idempotency_key=f"test:{uuid4()}",
        decision_type=AutomationDecisionType.CLUSTER_MATCH,
        decision_source=AutomationDecisionSource.CLUSTERING,
        reason="Automated cluster proposal",
    )
    payload = AutomationDecisionOverrideMutation(
        expected_entity_version=1,
        replacement_decision_type=AutomationDecisionType.CLUSTER_MATCH,
        selected_cluster_id=uuid4(),
        reason="Merge into the selected cluster",
    )

    with pytest.raises(HTTPException) as incompatible:
        card_automation_service._ensure_override_compatible(original, payload)

    assert incompatible.value.status_code == 422
    detail = cast(dict[str, str], incompatible.value.detail)
    assert detail == {
        "code": "automation_override_incompatible",
        "message": "The replacement type is incompatible with this cluster target",
    }


async def _create_occurrence(
    seeded: SeededData,
    *,
    revision: int = 3,
    alias_human_confirmed: bool = False,
    moderation_status: IntelligenceQuestionModerationStatus = (
        IntelligenceQuestionModerationStatus.PENDING
    ),
) -> tuple[UUID, UUID]:
    unique = uuid4().hex
    company = Company(
        id=uuid4(),
        name=f"Company {unique[:8]}",
        normalized_name=f"company-{unique}",
        transliterated_name=f"company-{unique}",
    )
    process = InterviewProcess(
        id=uuid4(),
        user_id=seeded.student_id,
        track_id=seeded.python_track_id,
        company_id=company.id,
        company_name=company.name,
        status=InterviewProcessStatus.ACTIVE,
    )
    stage = InterviewProcessStage(
        id=uuid4(),
        process_id=process.id,
        stage_type=InterviewStageType.TECHNICAL_INTERVIEW,
        scheduled_at=datetime.now(UTC),
    )
    interview = IntelligenceInterview(
        id=uuid4(),
        stage_id=stage.id,
        student_id=seeded.student_id,
        interview_type=IntelligenceInterviewType.TECHNICAL,
    )
    question = IntelligenceQuestion(
        id=uuid4(),
        interview_id=interview.id,
        direction_id=seeded.python_track_id,
        sequence_number=0,
        question_text="What is the descriptor protocol?",
        normalized_question_text="what is the descriptor protocol",
        question_start_ms=0,
        question_end_ms=1_000,
        question_utterance_ids=[],
        answer_utterance_ids=[],
        category="Python",
        question_kind=IntelligenceQuestionKind.TECHNICAL,
        difficulty=IntelligenceDifficulty.MIDDLE,
        confidence=0.95,
        automation_status=QuestionOccurrenceStatus.FAILED,
        automation_error="Temporary provider failure",
        automation_revision=revision,
        alias_human_confirmed=alias_human_confirmed,
        moderation_status=moderation_status,
    )
    async with TestSession() as session:
        session.add(company)
        await session.flush()
        session.add(process)
        await session.flush()
        session.add(stage)
        await session.flush()
        session.add(interview)
        await session.flush()
        session.add(question)
        await session.commit()
    return interview.id, question.id


async def _attach_cluster_occurrence(
    seeded: SeededData,
    cluster_id: UUID,
    *,
    text: str,
    confidence: float,
    revision: int = 3,
) -> UUID:
    _interview_id, question_id = await _create_occurrence(seeded, revision=revision)
    async with TestSession() as session:
        question = await session.get_one(IntelligenceQuestion, question_id)
        question.question_text = text
        question.normalized_question_text = text.lower()
        question.learning_object_type = LearningObjectType.OPEN_TECHNICAL_QUESTION
        question.routing_confidence = confidence
        question.confidence = confidence
        question.question_embedding = [confidence, 1.0 - confidence]
        question.question_embedding_model = "test-embedding"
        question.question_embedding_dimensions = 2
        question.question_embedding_source_hash = f"{int(confidence * 100):064d}"
        question.cluster_id = cluster_id
        question.automation_status = QuestionOccurrenceStatus.NEEDS_REVIEW
        question.automation_error = None
        await session.commit()
    return question_id


@pytest.mark.asyncio
async def test_cluster_list_is_scoped_and_has_constant_query_count(seeded: SeededData) -> None:
    async with TestSession() as session:
        mentor = await session.get_one(User, seeded.mentor_id)
        session.add_all(
            [
                *(
                    _cluster(
                        seeded.python_track_id,
                        index,
                        status=QuestionClusterStatus.NEEDS_REVIEW,
                    )
                    for index in range(8)
                ),
                _cluster(
                    seeded.go_track_id,
                    99,
                    status=QuestionClusterStatus.NEEDS_REVIEW,
                ),
            ]
        )
        await session.commit()

        statements = 0

        def count_statement(*_args: object, **_kwargs: object) -> None:
            nonlocal statements
            statements += 1

        event.listen(test_engine.sync_engine, "before_cursor_execute", count_statement)
        try:
            page = await list_question_clusters(
                session,
                mentor,
                QuestionClusterListFilters(limit=100),
            )
        finally:
            event.remove(test_engine.sync_engine, "before_cursor_execute", count_statement)

        assert page.total == 8
        assert {item.direction_id for item in page.items} == {seeded.python_track_id}
        assert statements <= 6
        assert all(
            QuestionClusterAction.LINK_CARD not in item.allowed_actions for item in page.items
        )
        assert all(QuestionClusterAction.IGNORE in item.allowed_actions for item in page.items)


@pytest.mark.asyncio
async def test_mark_important_is_versioned_and_idempotent(seeded: SeededData) -> None:
    cluster = _cluster(seeded.python_track_id, 1, status=QuestionClusterStatus.SHADOW)
    payload = QuestionClusterActionMutation(expected_version=1, reason="Core interview topic")
    async with TestSession() as session:
        mentor = await session.get_one(User, seeded.mentor_id)
        session.add(cluster)
        await session.commit()

        first = await mark_question_cluster_important(session, mentor, cluster.id, payload)
        repeated = await mark_question_cluster_important(session, mentor, cluster.id, payload)

        assert first.decision_id == repeated.decision_id
        assert repeated.cluster.status is QuestionClusterStatus.NEEDS_REVIEW
        assert repeated.cluster.manual_important
        assert repeated.cluster.version == 2
        decision_count = int(
            await session.scalar(
                select(func.count(AutomationDecision.id)).where(
                    AutomationDecision.entity_id == cluster.id,
                    AutomationDecision.decision_type
                    == AutomationDecisionType.CLUSTER_MARKED_IMPORTANT,
                )
            )
            or 0
        )
        assert decision_count == 1

        with pytest.raises(HTTPException) as conflict:
            await mark_question_cluster_important(
                session,
                mentor,
                cluster.id,
                QuestionClusterActionMutation(
                    expected_version=1,
                    reason="A different stale retry",
                ),
            )
        assert conflict.value.status_code == 409


@pytest.mark.asyncio
async def test_personal_review_is_private_and_becomes_mastered(seeded: SeededData) -> None:
    item = PersonalReviewItem(
        id=uuid4(),
        student_id=seeded.student_id,
        direction_id=seeded.python_track_id,
        question_text="What is the descriptor protocol?",
        status=PersonalReviewStatus.ACTIVE,
        successful_reviews_count=3,
        version=1,
    )
    async with TestSession() as session:
        student = await session.get_one(User, seeded.student_id)
        other_user = await session.get_one(User, seeded.mentor_id)
        session.add(item)
        await session.commit()

        payload = PersonalReviewItemReviewMutation(
            rating=InterviewReviewRating.GOOD,
            expected_version=1,
        )
        result = await review_personal_review_item(
            session,
            student,
            item.id,
            payload,
        )
        repeated = await review_personal_review_item(session, student, item.id, payload)
        assert result.became_mastered
        assert repeated.became_mastered
        assert result.item.status is PersonalReviewStatus.MASTERED
        assert result.item.successful_reviews_count == 4
        assert result.item.version == 2
        assert repeated.item.successful_reviews_count == 4
        assert repeated.item.version == 2
        decision_count = int(
            await session.scalar(
                select(func.count(AutomationDecision.id)).where(
                    AutomationDecision.entity_id == item.id,
                    AutomationDecision.decision_type
                    == AutomationDecisionType.PERSONAL_REVIEW_REVIEWED,
                )
            )
            or 0
        )
        assert decision_count == 1

        own_page = await list_personal_review_items(
            session,
            student,
            PersonalReviewItemListFilters(due_only=False),
        )
        other_page = await list_personal_review_items(
            session,
            other_user,
            PersonalReviewItemListFilters(due_only=False),
        )
        assert [listed.id for listed in own_page.items] == [item.id]
        assert other_page.items == []


@pytest.mark.asyncio
async def test_occurrence_reprocess_is_scoped_audited_and_idempotent(
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, question_id = await _create_occurrence(seeded)
    queued: list[tuple[str, str, int]] = []

    async def fake_enqueue(function: str, entity_id: str, revision: int) -> str:
        queued.append((function, entity_id, revision))
        return f"job:{entity_id}:v{revision}"

    monkeypatch.setattr(
        card_automation_service,
        "enqueue_card_automation_job",
        fake_enqueue,
    )
    payload = QuestionOccurrenceReprocessMutation(
        expected_revision=3,
        reason="Retry after a temporary provider failure",
    )
    async with TestSession() as session:
        mentor = await session.get_one(User, seeded.mentor_id)
        other_mentor = await session.get_one(User, seeded.other_mentor_id)
        first = await card_automation_service.reprocess_question_occurrence(
            session, mentor, question_id, payload
        )
        repeated = await card_automation_service.reprocess_question_occurrence(
            session, mentor, question_id, payload
        )

        assert first == repeated
        assert first.revision == 3
        assert queued == [
            ("reprocess_question_occurrence", str(question_id), 3),
            ("reprocess_question_occurrence", str(question_id), 3),
        ]
        decisions = list(
            await session.scalars(
                select(AutomationDecision).where(
                    AutomationDecision.entity_id == question_id,
                    AutomationDecision.decision_type
                    == AutomationDecisionType.OCCURRENCE_REPROCESSED,
                )
            )
        )
        assert len(decisions) == 1
        assert decisions[0].retrieval_scores["actor_user_id"] == str(mentor.id)

        with pytest.raises(HTTPException) as hidden:
            await card_automation_service.reprocess_question_occurrence(
                session, other_mentor, question_id, payload
            )
        assert hidden.value.status_code == 404

        with pytest.raises(HTTPException) as conflict:
            await card_automation_service.reprocess_question_occurrence(
                session,
                mentor,
                question_id,
                QuestionOccurrenceReprocessMutation(
                    expected_revision=3,
                    reason="A different retry request",
                ),
            )
        assert conflict.value.status_code == 409


@pytest.mark.asyncio
async def test_occurrence_reprocess_preserves_human_moderation(seeded: SeededData) -> None:
    _, alias_id = await _create_occurrence(seeded, alias_human_confirmed=True)
    _, moderated_id = await _create_occurrence(
        seeded,
        moderation_status=IntelligenceQuestionModerationStatus.MENTOR_APPROVED,
    )
    payload = QuestionOccurrenceReprocessMutation(expected_revision=3, reason="Unsafe retry")
    async with TestSession() as session:
        admin = await session.get_one(User, seeded.admin_id)
        with pytest.raises(HTTPException) as alias_conflict:
            await card_automation_service.reprocess_question_occurrence(
                session, admin, alias_id, payload
            )
        assert alias_conflict.value.status_code == 409
        await session.rollback()
        admin = await session.get_one(User, seeded.admin_id)

        with pytest.raises(HTTPException) as moderated_conflict:
            await card_automation_service.reprocess_question_occurrence(
                session, admin, moderated_id, payload
            )
        assert moderated_conflict.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cluster_status",
    [
        QuestionClusterStatus.SHADOW,
        QuestionClusterStatus.CANDIDATE,
        QuestionClusterStatus.NEEDS_REVIEW,
    ],
)
async def test_admin_can_request_missing_cluster_answer_generation(
    seeded: SeededData,
    monkeypatch: pytest.MonkeyPatch,
    cluster_status: QuestionClusterStatus,
) -> None:
    cluster = _cluster(
        seeded.python_track_id,
        99,
        status=cluster_status,
    )
    cluster.answer_status = AnswerContractStatus.NEEDS_EXPERT_SOURCE
    queued: list[tuple[str, str, int]] = []

    async def fake_enqueue(function: str, entity_id: str, revision: int) -> str:
        queued.append((function, entity_id, revision))
        return f"job:{entity_id}:v{revision}"

    monkeypatch.setattr(
        card_automation_service,
        "enqueue_card_automation_job",
        fake_enqueue,
    )
    async with TestSession() as session:
        admin = await session.get_one(User, seeded.admin_id)
        settings = await session.get(CardAutomationSettings, seeded.python_track_id)
        initial_version = settings.version if settings is not None else 1
        await update_card_automation_settings(
            session,
            admin,
            _settings_update(seeded.python_track_id, initial_version).model_copy(
                update={"cluster_moderation_enabled": True}
            ),
            "enable-answer-generation-test",
        )
        session.add(cluster)
        await session.commit()

        result = await card_automation_service.request_question_cluster_answer_generation(
            session,
            admin,
            cluster.id,
            QuestionClusterAnswerGenerationMutation(expected_version=1),
        )

        assert result.cluster_id == cluster.id
        assert result.version == 1
        assert queued == [
            ("generate_cluster_candidate", str(cluster.id), cluster.membership_revision)
        ]


@pytest.mark.asyncio
async def test_managed_personal_review_is_assignment_scoped_and_audited(
    seeded: SeededData,
) -> None:
    item = PersonalReviewItem(
        id=uuid4(),
        student_id=seeded.student_id,
        direction_id=seeded.python_track_id,
        question_text="Original private question",
        answer_summary="Original summary",
        status=PersonalReviewStatus.ACTIVE,
        version=1,
    )
    out_of_direction_item = PersonalReviewItem(
        id=uuid4(),
        student_id=seeded.student_id,
        direction_id=seeded.go_track_id,
        question_text="Private Go question",
        status=PersonalReviewStatus.ACTIVE,
        version=1,
    )
    filters = PersonalReviewItemListFilters(due_only=False)
    payload = PersonalReviewItemCorrectionMutation(
        expected_version=1,
        reason="Corrected after mentor review",
        question_text="Corrected private question",
        answer_summary=None,
    )
    async with TestSession() as session:
        session.add_all([item, out_of_direction_item])
        await session.commit()
        mentor = await session.get_one(User, seeded.mentor_id)
        other_mentor = await session.get_one(User, seeded.other_mentor_id)
        admin = await session.get_one(User, seeded.admin_id)

        mentor_page = await list_managed_personal_review_items(
            session, mentor, seeded.student_id, filters
        )
        admin_page = await list_managed_personal_review_items(
            session, admin, seeded.student_id, filters
        )
        assert [listed.id for listed in mentor_page.items] == [item.id]
        assert {listed.id for listed in admin_page.items} == {
            item.id,
            out_of_direction_item.id,
        }
        with pytest.raises(HTTPException) as hidden:
            await list_managed_personal_review_items(
                session, other_mentor, seeded.student_id, filters
            )
        assert hidden.value.status_code == 404

        # Even for an assigned student, the mentor cannot cross their track
        # scope (the primary mentor is assigned only to Python).
        with pytest.raises(HTTPException) as hidden_direction:
            await list_managed_personal_review_items(
                session,
                mentor,
                seeded.student_id,
                PersonalReviewItemListFilters(
                    direction_id=seeded.go_track_id,
                    due_only=False,
                ),
            )
        assert hidden_direction.value.status_code == 404

        first = await correct_personal_review_item(
            session, mentor, seeded.student_id, item.id, payload
        )
        repeated = await correct_personal_review_item(
            session, mentor, seeded.student_id, item.id, payload
        )
        assert first.decision_id == repeated.decision_id
        assert repeated.item.question_text == "Corrected private question"
        assert repeated.item.answer_summary is None
        assert repeated.item.version == 2
        decision = await session.get_one(AutomationDecision, first.decision_id)
        assert decision.decision_type is AutomationDecisionType.MANUAL_OVERRIDE
        before = decision.retrieval_scores["before"]
        after = decision.retrieval_scores["after"]
        assert isinstance(before, dict)
        assert isinstance(after, dict)
        assert before["version"] == 1
        assert after["version"] == 2

        with pytest.raises(HTTPException) as forbidden_correction:
            await correct_personal_review_item(
                session, other_mentor, seeded.student_id, item.id, payload
            )
        assert forbidden_correction.value.status_code == 404
        with pytest.raises(HTTPException) as wrong_direction_correction:
            await correct_personal_review_item(
                session,
                mentor,
                seeded.student_id,
                out_of_direction_item.id,
                payload,
            )
        assert wrong_direction_correction.value.status_code == 404


@pytest.mark.asyncio
async def test_create_card_approves_answer_contract_and_audits_content_hashes(
    seeded: SeededData,
) -> None:
    cluster = _cluster(
        seeded.python_track_id,
        10,
        status=QuestionClusterStatus.NEEDS_REVIEW,
    )
    deck, existing_cards = _topic_catalog(
        seeded.python_track_id,
        "Python internals",
    )
    payload = QuestionClusterCreateCardMutation(
        deck_id=deck.id,
        category="Python internals",
        subcategory="Descriptors",
        question_markdown="How do descriptors work?",
        answer_markdown="Descriptors customize attribute access.",
        frequency=InterviewCardFrequency.OCCASIONAL,
        expected_version=1,
        reason="Expert-approved canonical answer",
    )
    async with TestSession() as session:
        session.add_all([deck, *existing_cards])
        await session.commit()
        session.add(cluster)
        await session.commit()
        admin = await session.get_one(User, seeded.admin_id)

        result = await create_question_cluster_card(session, admin, cluster.id, payload)
        refreshed = await session.get_one(QuestionCluster, cluster.id)
        decision = await session.get_one(AutomationDecision, result.decision_id)

        assert refreshed.answer_status is AnswerContractStatus.APPROVED
        assert decision.retrieval_scores["category"] == "Python internals"
        assert decision.retrieval_scores["subcategory"] == "Descriptors"
        assert len(str(decision.retrieval_scores["question_sha256"])) == 64
        assert len(str(decision.retrieval_scores["answer_sha256"])) == 64


@pytest.mark.asyncio
async def test_create_card_rejects_a_new_broad_topic(seeded: SeededData) -> None:
    cluster = _cluster(
        seeded.python_track_id,
        101,
        status=QuestionClusterStatus.NEEDS_REVIEW,
    )
    deck, existing_cards = _topic_catalog(seeded.python_track_id, "Python core")
    payload = QuestionClusterCreateCardMutation(
        deck_id=deck.id,
        category="Very detailed one-off topic",
        question_markdown="How do descriptors work?",
        answer_markdown="Descriptors customize attribute access.",
        frequency=InterviewCardFrequency.OCCASIONAL,
        expected_version=1,
        reason="Attempt to create a new broad topic",
    )
    async with TestSession() as session:
        session.add_all([deck, *existing_cards])
        await session.commit()
        session.add(cluster)
        await session.commit()
        admin = await session.get_one(User, seeded.admin_id)

        with pytest.raises(HTTPException) as rejected:
            await create_question_cluster_card(session, admin, cluster.id, payload)

        assert rejected.value.status_code == 422
        assert cast(dict[str, str], rejected.value.detail)["code"] == (
            "interview_card_topic_not_found"
        )


@pytest.mark.asyncio
async def test_update_cluster_draft_is_versioned_audited_and_idempotent(
    seeded: SeededData,
) -> None:
    cluster = _cluster(
        seeded.python_track_id,
        11,
        status=QuestionClusterStatus.NEEDS_REVIEW,
    )
    cluster.topic_name = "Python"
    cluster.answer_contract = AnswerContract(
        short_answer="Old answer",
        required_points=["Old point"],
        difficulty="middle",
        confidence=0.8,
    ).model_dump(mode="json")
    cluster.answer_validation = {
        "supported": True,
        "unsupported_claims": [],
        "contradictions": [],
        "missing_required_points": [],
        "version_sensitive_claims": [],
        "confidence": 0.9,
    }
    cluster.answer_status = AnswerContractStatus.APPROVED
    cluster.embedding = [0.1, 0.9]
    cluster.embedding_model = "embedding-test"
    cluster.embedding_dimensions = 2
    cluster.embedding_source_hash = "a" * 64
    deck, existing_cards = _topic_catalog(
        seeded.python_track_id,
        "Python internals",
        "Data model",
    )
    cluster.deck_id = deck.id
    payload = QuestionClusterDraftMutation(
        canonical_question="How does Python descriptor lookup work?",
        topic_name="Python internals",
        subtopic_name="Descriptor protocol",
        answer_contract=AnswerContract(
            short_answer="Descriptors control attribute lookup.",
            required_points=["__get__", "descriptor precedence"],
            difficulty="middle",
            confidence=0.95,
        ),
        expected_version=1,
        reason="Reviewed the AI draft against internal material",
    )
    async with TestSession() as session:
        session.add_all([deck, *existing_cards])
        await session.commit()
        session.add(cluster)
        await session.commit()
        admin = await session.get_one(User, seeded.admin_id)

        first = await update_question_cluster_draft(
            session,
            admin,
            cluster.id,
            payload,
            idempotency_key="draft-update-test",
        )
        repeated = await update_question_cluster_draft(
            session,
            admin,
            cluster.id,
            payload,
            idempotency_key="draft-update-test",
        )

        assert repeated.decision_id == first.decision_id
        refreshed = await session.get_one(QuestionCluster, cluster.id)
        assert refreshed.version == 2
        assert refreshed.canonical_question == payload.canonical_question
        assert refreshed.normalized_canonical_question == normalize_question(
            payload.canonical_question or ""
        )
        assert refreshed.topic_name == "Python internals"
        assert refreshed.subtopic_name == "Descriptor protocol"
        assert refreshed.answer_contract == payload.answer_contract.model_dump(mode="json")
        assert refreshed.answer_status is AnswerContractStatus.NEEDS_MANUAL_REVIEW
        assert refreshed.answer_validation is None
        assert refreshed.embedding is None
        assert refreshed.embedding_model is None
        assert refreshed.embedding_dimensions is None
        assert refreshed.embedding_source_hash is None

        decision = await session.get_one(AutomationDecision, first.decision_id)
        assert decision.decision_type is AutomationDecisionType.MANUAL_OVERRIDE
        assert decision.retrieval_scores["action"] == "cluster_draft_updated"
        assert decision.retrieval_scores["changed_fields"] == [
            "canonical_question",
            "topic_name",
            "subtopic_name",
            "answer_contract",
        ]
        assert decision.retrieval_scores["before"]["version"] == 1
        assert decision.retrieval_scores["after"]["version"] == 2

        with pytest.raises(HTTPException) as reused:
            await update_question_cluster_draft(
                session,
                admin,
                cluster.id,
                QuestionClusterDraftMutation(
                    topic_name="Different topic",
                    expected_version=1,
                    reason="Different request",
                ),
                idempotency_key="draft-update-test",
            )
        assert reused.value.status_code == 409
        assert cast(dict[str, str], reused.value.detail)["code"] == "idempotency_key_reused"

        await update_question_cluster_draft(
            session,
            admin,
            cluster.id,
            QuestionClusterDraftMutation(
                topic_name="Data model",
                expected_version=2,
                reason="Refined the topic after another review",
            ),
            idempotency_key="draft-update-later",
        )
        with pytest.raises(HTTPException) as superseded:
            await update_question_cluster_draft(
                session,
                admin,
                cluster.id,
                payload,
                idempotency_key="draft-update-test",
            )
        assert superseded.value.status_code == 409
        assert cast(dict[str, str], superseded.value.detail)["code"] == (
            "question_cluster_idempotency_result_superseded"
        )


@pytest.mark.asyncio
async def test_mentor_can_update_cluster_draft_only_in_assigned_direction(
    seeded: SeededData,
) -> None:
    cluster = _cluster(
        seeded.python_track_id,
        111,
        status=QuestionClusterStatus.NEEDS_REVIEW,
    )
    cluster.topic_name = "Python core"
    cluster.answer_contract = AnswerContract(
        short_answer="AI draft",
        difficulty="middle",
        confidence=0.5,
    ).model_dump(mode="json")
    deck, cards = _topic_catalog(seeded.python_track_id, "Python core")
    cluster.deck_id = deck.id
    async with TestSession() as session:
        session.add_all([deck, *cards])
        await session.commit()
        session.add(cluster)
        await session.commit()
        mentor = await session.get_one(User, seeded.mentor_id)

        result = await update_question_cluster_draft(
            session,
            mentor,
            cluster.id,
            QuestionClusterDraftMutation(
                answer_contract=AnswerContract(
                    short_answer="Mentor reviewed answer",
                    difficulty="middle",
                    confidence=0.8,
                ),
                expected_version=1,
                reason="Reviewed the generated answer",
            ),
            idempotency_key="mentor-draft-review",
        )

        refreshed = await session.get_one(QuestionCluster, cluster.id)
        assert result.cluster.version == 2
        assert refreshed.answer_contract is not None
        assert refreshed.answer_contract["short_answer"] == "Mentor reviewed answer"
        assert refreshed.answer_status is AnswerContractStatus.NEEDS_MANUAL_REVIEW
        decision = await session.get_one(AutomationDecision, result.decision_id)
        assert decision.decision_source is AutomationDecisionSource.HUMAN
        assert decision.reviewed_by_user_id == mentor.id


@pytest.mark.asyncio
async def test_update_cluster_draft_can_preserve_status_only_for_safe_wording_change(
    seeded: SeededData,
) -> None:
    cluster = _cluster(
        seeded.python_track_id,
        12,
        status=QuestionClusterStatus.NEEDS_REVIEW,
    )
    cluster.canonical_question = "What is a Python descriptor?"
    cluster.normalized_canonical_question = normalize_question(cluster.canonical_question)
    cluster.answer_contract = AnswerContract(
        short_answer="A descriptor implements the descriptor protocol.",
        difficulty="middle",
        confidence=0.9,
    ).model_dump(mode="json")
    cluster.answer_status = AnswerContractStatus.APPROVED
    cluster.embedding = [0.2, 0.8]
    cluster.embedding_model = "embedding-test"
    cluster.embedding_dimensions = 2
    cluster.embedding_source_hash = "b" * 64
    deck, existing_cards = _topic_catalog(seeded.python_track_id, "Data model")
    cluster.deck_id = deck.id
    async with TestSession() as session:
        session.add_all([deck, *existing_cards])
        await session.commit()
        session.add(cluster)
        await session.commit()
        admin = await session.get_one(User, seeded.admin_id)

        await update_question_cluster_draft(
            session,
            admin,
            cluster.id,
            QuestionClusterDraftMutation(
                canonical_question="WHAT IS A PYTHON DESCRIPTOR?!",
                topic_name="Data model",
                preserve_answer_status=True,
                expected_version=1,
                reason="Only punctuation, casing, and topic changed",
            ),
        )
        refreshed = await session.get_one(QuestionCluster, cluster.id)
        assert refreshed.answer_status is AnswerContractStatus.APPROVED
        assert refreshed.embedding == pytest.approx([0.2, 0.8])

        with pytest.raises(HTTPException) as unsafe:
            await update_question_cluster_draft(
                session,
                admin,
                cluster.id,
                QuestionClusterDraftMutation(
                    canonical_question="How does descriptor precedence work?",
                    preserve_answer_status=True,
                    expected_version=2,
                    reason="This changes the scope",
                ),
            )
        assert unsafe.value.status_code == 422
        assert cast(dict[str, str], unsafe.value.detail)["code"] == (
            "unsafe_answer_status_preservation"
        )


@pytest.mark.asyncio
async def test_topic_only_draft_update_keeps_answer_validation_by_default(
    seeded: SeededData,
) -> None:
    cluster = _cluster(
        seeded.python_track_id,
        13,
        status=QuestionClusterStatus.NEEDS_REVIEW,
    )
    cluster.answer_contract = AnswerContract(
        short_answer="A descriptor implements the descriptor protocol.",
        difficulty="middle",
        confidence=0.9,
    ).model_dump(mode="json")
    validation = {
        "supported": True,
        "unsupported_claims": [],
        "contradictions": [],
        "missing_required_points": [],
        "version_sensitive_claims": [],
        "confidence": 0.9,
    }
    cluster.answer_validation = validation
    cluster.answer_status = AnswerContractStatus.APPROVED
    deck, existing_cards = _topic_catalog(
        seeded.python_track_id,
        "Python data model",
    )
    cluster.deck_id = deck.id
    async with TestSession() as session:
        session.add_all([deck, *existing_cards])
        await session.commit()
        session.add(cluster)
        await session.commit()
        admin = await session.get_one(User, seeded.admin_id)

        await update_question_cluster_draft(
            session,
            admin,
            cluster.id,
            QuestionClusterDraftMutation(
                topic_name="Python data model",
                expected_version=1,
                reason="Corrected only the topic",
            ),
        )
        refreshed = await session.get_one(QuestionCluster, cluster.id)
        assert refreshed.answer_status is AnswerContractStatus.APPROVED
        assert refreshed.answer_validation == validation


@pytest.mark.asyncio
async def test_legacy_human_moderation_invalidates_pending_automation(
    seeded: SeededData,
) -> None:
    interview_id, question_id = await _create_occurrence(seeded)
    deck = InterviewDeck(
        id=uuid4(),
        track_id=seeded.python_track_id,
        slug=f"moderation-{uuid4().hex}",
        title="Moderation",
        position=0,
        is_published=True,
    )
    async with TestSession() as session:
        session.add(deck)
        await session.commit()
        mentor = await session.get_one(User, seeded.mentor_id)
        admin = await session.get_one(User, seeded.admin_id)

        await moderate_intelligence_question(
            session,
            mentor,
            interview_id,
            question_id,
            IntelligenceQuestionModerationMutation(action="recommend"),
        )
        recommended = await session.get_one(IntelligenceQuestion, question_id)
        assert recommended.automation_revision == 4
        assert recommended.automation_status is QuestionOccurrenceStatus.NEEDS_REVIEW
        assert recommended.automation_decision_source is AutomationDecisionSource.HUMAN

        await moderate_intelligence_question(
            session,
            admin,
            interview_id,
            question_id,
            IntelligenceQuestionModerationMutation(
                action="approve",
                question_markdown="What is the descriptor protocol?",
                answer_markdown="A verified descriptor answer.",
                deck_id=deck.id,
                category="Python",
                create_category=True,
                create_new_card=True,
                frequency=InterviewCardFrequency.OCCASIONAL,
            ),
        )
        approved = await session.get_one(IntelligenceQuestion, question_id)
        assert approved.automation_revision == 5
        assert approved.automation_status is QuestionOccurrenceStatus.AUTO_LINKED
        assert approved.automation_decision_source is AutomationDecisionSource.HUMAN
        assert approved.alias_human_confirmed

    rejected_interview_id, rejected_question_id = await _create_occurrence(seeded)
    async with TestSession() as session:
        mentor = await session.get_one(User, seeded.mentor_id)
        await moderate_intelligence_question(
            session,
            mentor,
            rejected_interview_id,
            rejected_question_id,
            IntelligenceQuestionModerationMutation(action="reject"),
        )
        rejected = await session.get_one(IntelligenceQuestion, rejected_question_id)
        assert rejected.automation_revision == 4
        assert rejected.automation_status is QuestionOccurrenceStatus.AUTO_IGNORED
        assert rejected.automation_decision_source is AutomationDecisionSource.HUMAN


@pytest.mark.asyncio
async def test_auto_link_metrics_exclude_unapplied_card_proposals(
    seeded: SeededData,
) -> None:
    _interview_id, question_id = await _create_occurrence(seeded)
    deck = InterviewDeck(
        track_id=seeded.python_track_id,
        slug=f"metrics-{uuid4().hex}",
        title="Metrics",
        position=0,
        is_published=True,
    )
    card = InterviewCard(
        id=uuid4(),
        deck=deck,
        slug=f"metrics-card-{uuid4().hex}",
        category="Python",
        question_markdown="What is the descriptor protocol?",
        answer_markdown="A descriptor controls attribute access.",
        frequency=InterviewCardFrequency.OCCASIONAL,
        position=0,
        is_published=True,
    )
    decisions = [
        AutomationDecision(
            entity_type="occurrence",
            entity_id=question_id,
            idempotency_key=f"metrics:{decision_type.value}:{applied}",
            decision_type=decision_type,
            decision_source=decision_source,
            selected_card_id=card.id,
            retrieval_scores={str(card.id): 1.0, "applied": applied},
            reason="Metric fixture",
        )
        for decision_type, decision_source in (
            (AutomationDecisionType.EXACT_CARD_MATCH, AutomationDecisionSource.EXACT),
            (AutomationDecisionType.ALIAS_CARD_MATCH, AutomationDecisionSource.CONFIRMED_ALIAS),
            (
                AutomationDecisionType.SEMANTIC_CARD_MATCH,
                AutomationDecisionSource.SEMANTIC_JUDGE,
            ),
        )
        for applied in (False, True)
    ]
    async with TestSession() as session:
        session.add(card)
        await session.flush()
        session.add_all(decisions)
        await session.commit()
        admin = await session.get_one(User, seeded.admin_id)
        today = datetime.now(UTC).date()
        metrics = await get_card_automation_metrics(
            session,
            admin,
            CardAutomationMetricsFilters(
                period_from=today,
                period_to=today,
                direction_id=seeded.python_track_id,
            ),
        )

    assert metrics.auto_linked_exact_total == 1
    assert metrics.auto_linked_alias_total == 1
    assert metrics.auto_linked_semantic_total == 1


def _settings_update(direction_id: UUID, expected_version: int) -> CardAutomationSettingsUpdate:
    return CardAutomationSettingsUpdate(
        direction_id=direction_id,
        expected_version=expected_version,
        enabled=True,
        shadow_mode=True,
        auto_ignore_noise_enabled=False,
        auto_link_exact_enabled=False,
        auto_link_alias_enabled=False,
        auto_link_semantic_enabled=False,
        semantic_similarity_threshold=0.91,
        pairwise_judge_confidence_threshold=0.93,
        candidate_score_gap_threshold=0.09,
        cluster_match_threshold=0.87,
        min_distinct_interviews_for_promotion=4,
        min_distinct_companies_for_promotion=3,
        min_failed_answers_for_promotion=2,
        audit_sample_percent=7.0,
        personal_review_enabled=False,
        global_auto_publish_enabled=False,
        cluster_moderation_enabled=False,
        legacy_queue_enabled=True,
    )


@pytest.mark.asyncio
async def test_settings_update_is_audited_and_idempotent(seeded: SeededData) -> None:
    async with TestSession() as session:
        admin = await session.get_one(User, seeded.admin_id)
        settings = await session.get(CardAutomationSettings, seeded.python_track_id)
        initial_version = settings.version if settings is not None else 1
        payload = _settings_update(seeded.python_track_id, initial_version)

        first = await update_card_automation_settings(
            session, admin, payload, "settings-request-0001"
        )
        replay = await update_card_automation_settings(
            session, admin, payload, "settings-request-0001"
        )

        assert first.version == initial_version + 1
        assert replay == first
        decisions = list(
            await session.scalars(
                select(AutomationDecision).where(
                    AutomationDecision.entity_type == "settings",
                    AutomationDecision.entity_id == seeded.python_track_id,
                    AutomationDecision.decision_type == AutomationDecisionType.MANUAL_OVERRIDE,
                )
            )
        )
        assert len(decisions) == 1
        decision = decisions[0]
        assert decision.reviewed_by_user_id == admin.id
        assert decision.retrieval_scores["before"]["version"] == initial_version
        assert decision.retrieval_scores["after"]["version"] == initial_version + 1

        with pytest.raises(HTTPException) as stale_request:
            await update_card_automation_settings(session, admin, payload, "settings-request-0002")
        assert stale_request.value.status_code == 409


@pytest.mark.asyncio
async def test_decision_override_rejects_stale_entity_and_superseded_decision(
    seeded: SeededData,
) -> None:
    _interview_id, question_id = await _create_occurrence(seeded)
    now = datetime.now(UTC)
    stale_entity_decision = AutomationDecision(
        entity_type="occurrence",
        entity_id=question_id,
        idempotency_key=f"override-stale-entity:{uuid4()}",
        decision_type=AutomationDecisionType.QUESTION_ROUTED,
        decision_source=AutomationDecisionSource.RULE,
        reason="Original routing",
        created_at=now - timedelta(minutes=2),
    )
    superseded_decision = AutomationDecision(
        entity_type="occurrence",
        entity_id=question_id,
        idempotency_key=f"override-superseded:{uuid4()}",
        decision_type=AutomationDecisionType.QUESTION_ROUTED,
        decision_source=AutomationDecisionSource.RULE,
        reason="Historical routing",
        created_at=now - timedelta(minutes=1),
    )
    latest_decision = AutomationDecision(
        entity_type="occurrence",
        entity_id=question_id,
        idempotency_key=f"override-latest:{uuid4()}",
        decision_type=AutomationDecisionType.OCCURRENCE_FAILED,
        decision_source=AutomationDecisionSource.RULE,
        reason="Latest failure",
        created_at=now,
    )
    async with TestSession() as session:
        session.add_all([stale_entity_decision, superseded_decision, latest_decision])
        await session.commit()
        superseded_decision_id = superseded_decision.id
        latest_decision_id = latest_decision.id
        admin = await session.get_one(User, seeded.admin_id)

        with pytest.raises(HTTPException) as superseded:
            await card_automation_service.override_automation_decision(
                session,
                admin,
                superseded_decision_id,
                AutomationDecisionOverrideMutation(
                    expected_entity_version=3,
                    replacement_decision_type=AutomationDecisionType.MANUAL_OVERRIDE,
                    reason="Unsafe historical override",
                ),
            )
        assert superseded.value.status_code == 409
        assert superseded.value.detail["code"] == "automation_decision_superseded"

        await session.rollback()
        admin = await session.get_one(User, seeded.admin_id)
        question = await session.get_one(IntelligenceQuestion, question_id)
        question.automation_revision = 4
        await session.commit()
        with pytest.raises(HTTPException) as stale_entity:
            await card_automation_service.override_automation_decision(
                session,
                admin,
                latest_decision_id,
                AutomationDecisionOverrideMutation(
                    expected_entity_version=3,
                    replacement_decision_type=AutomationDecisionType.MANUAL_OVERRIDE,
                    reason="Override from a stale browser tab",
                ),
            )
        assert stale_entity.value.status_code == 409
        assert stale_entity.value.detail["code"] == "automation_decision_entity_version_conflict"


@pytest.mark.asyncio
async def test_manual_card_link_and_create_invalidate_worker_revision_once(
    seeded: SeededData,
) -> None:
    link_cluster = _cluster(seeded.python_track_id, 201, status=QuestionClusterStatus.NEEDS_REVIEW)
    create_cluster = _cluster(
        seeded.python_track_id, 202, status=QuestionClusterStatus.NEEDS_REVIEW
    )
    deck = InterviewDeck(
        id=uuid4(),
        track_id=seeded.python_track_id,
        slug=f"manual-race-{uuid4().hex}",
        title="Manual race",
        position=0,
        is_published=True,
    )
    card = InterviewCard(
        id=uuid4(),
        deck_id=deck.id,
        slug=f"manual-link-{uuid4().hex}",
        category="Python",
        question_markdown="How does the GIL work?",
        answer_markdown="It serializes Python bytecode execution in CPython.",
        frequency=InterviewCardFrequency.OCCASIONAL,
        position=0,
        is_published=True,
    )
    async with TestSession() as session:
        session.add_all([link_cluster, create_cluster, deck, card])
        await session.commit()
    linked_question_id = await _attach_cluster_occurrence(
        seeded,
        link_cluster.id,
        text="Explain the GIL",
        confidence=0.9,
    )
    created_question_id = await _attach_cluster_occurrence(
        seeded,
        create_cluster.id,
        text="Explain Python descriptors",
        confidence=0.85,
    )

    async with TestSession() as session:
        admin = await session.get_one(User, seeded.admin_id)
        link_payload = QuestionClusterLinkCardMutation(
            card_id=card.id,
            confirm_alias=True,
            expected_version=1,
            reason="Manual canonical match",
        )
        first_link = await link_question_cluster_card(session, admin, link_cluster.id, link_payload)
        replay_link = await link_question_cluster_card(
            session, admin, link_cluster.id, link_payload
        )
        assert replay_link.decision_id == first_link.decision_id

        await create_question_cluster_card(
            session,
            admin,
            create_cluster.id,
            QuestionClusterCreateCardMutation(
                deck_id=deck.id,
                category="Python",
                question_markdown="How do Python descriptors work?",
                answer_markdown="Descriptors customize attribute access.",
                frequency=InterviewCardFrequency.OCCASIONAL,
                expected_version=1,
                reason="Create reviewed canonical card",
            ),
        )

        linked = await session.get_one(IntelligenceQuestion, linked_question_id)
        created = await session.get_one(IntelligenceQuestion, created_question_id)
        assert linked.automation_revision == 4
        assert created.automation_revision == 4
        assert linked.automation_status is QuestionOccurrenceStatus.AUTO_LINKED
        assert created.automation_status is QuestionOccurrenceStatus.AUTO_LINKED


@pytest.mark.asyncio
async def test_split_merge_and_reopen_preserve_representatives_and_aggregates(
    seeded: SeededData,
) -> None:
    source = _cluster(seeded.python_track_id, 301, status=QuestionClusterStatus.NEEDS_REVIEW)
    source.quality_score = 0.99
    source.cluster_confidence = 0.99
    source.membership_revision = 2
    source.stats_revision = 2
    deck, existing_cards = _topic_catalog(seeded.python_track_id, "Python")
    source.deck_id = deck.id
    source.topic_name = "Python"
    async with TestSession() as session:
        session.add_all([deck, *existing_cards])
        await session.commit()
        session.add(source)
        await session.commit()
    remaining_id = await _attach_cluster_occurrence(
        seeded, source.id, text="What is a descriptor?", confidence=0.2
    )
    moved_id = await _attach_cluster_occurrence(
        seeded, source.id, text="How does descriptor lookup work?", confidence=0.9
    )
    async with TestSession() as session:
        persisted = await session.get_one(QuestionCluster, source.id)
        persisted.representative_occurrence_id = moved_id
        await session.commit()

        admin = await session.get_one(User, seeded.admin_id)
        split = await split_question_cluster(
            session,
            admin,
            source.id,
            QuestionClusterSplitMutation(
                occurrence_ids=[moved_id],
                new_canonical_question="How does descriptor attribute lookup work?",
                new_topic_name="Python",
                new_subtopic_name="Descriptor lookup",
                expected_version=1,
                reason="Separate lookup mechanics from the definition",
            ),
        )
        new_cluster_id = next(item for item in split.affected_cluster_ids if item != source.id)
        original = await session.get_one(QuestionCluster, source.id)
        separated = await session.get_one(QuestionCluster, new_cluster_id)
        moved = await session.get_one(IntelligenceQuestion, moved_id)
        remaining = await session.get_one(IntelligenceQuestion, remaining_id)
        assert original.representative_occurrence_id == remaining_id
        assert separated.representative_occurrence_id == moved_id
        assert separated.topic_name == "Python"
        assert separated.subtopic_name == "Descriptor lookup"
        assert original.occurrences_count == 1
        assert separated.occurrences_count == 1
        assert original.quality_score == pytest.approx(0.2)
        assert separated.quality_score == pytest.approx(0.9)
        assert original.embedding == pytest.approx([0.2, 0.8])
        assert separated.embedding == pytest.approx([0.9, 0.1])
        assert original.embedding_source_hash == f"{20:064d}"
        assert separated.embedding_source_hash == f"{90:064d}"
        assert moved.automation_revision == 4
        assert remaining.automation_revision == 3

        merged = await merge_question_clusters(
            session,
            admin,
            new_cluster_id,
            QuestionClusterMergeMutation(
                target_cluster_id=source.id,
                expected_version=separated.version,
                target_expected_version=original.version,
                reason="Undo the split after expert review",
            ),
        )
        assert merged.cluster.status is QuestionClusterStatus.MERGED
        merged_source = await session.get_one(QuestionCluster, new_cluster_id)
        merged_target = await session.get_one(QuestionCluster, source.id)
        moved = await session.get_one(IntelligenceQuestion, moved_id)
        assert merged_source.occurrences_count == 0
        assert merged_source.quality_score == 0
        assert merged_target.occurrences_count == 2
        assert merged_target.representative_occurrence_id == remaining_id
        assert merged_target.embedding == pytest.approx([0.2, 0.8])
        assert moved.automation_revision == 5

        reopened = await reopen_question_cluster(
            session,
            admin,
            new_cluster_id,
            QuestionClusterActionMutation(
                expected_version=merged_source.version,
                reason="Restore the separated cluster for another review",
            ),
        )
        assert reopened.cluster.status is QuestionClusterStatus.NEEDS_REVIEW
        reopened_source = await session.get_one(QuestionCluster, new_cluster_id)
        reopened_target = await session.get_one(QuestionCluster, source.id)
        moved = await session.get_one(IntelligenceQuestion, moved_id)
        assert reopened_source.occurrences_count == 1
        assert reopened_source.representative_occurrence_id == moved_id
        assert reopened_target.occurrences_count == 1
        assert reopened_target.representative_occurrence_id == remaining_id
        assert reopened_source.embedding == pytest.approx([0.9, 0.1])
        assert reopened_target.embedding == pytest.approx([0.2, 0.8])
        assert moved.automation_revision == 6
