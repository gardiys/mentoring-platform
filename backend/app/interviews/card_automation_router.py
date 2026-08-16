from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AdminUser, MentorUser, StudentUser
from app.db.session import get_db_session
from app.interviews.card_automation_schemas import (
    AutomationDecisionListFilters,
    AutomationDecisionOverrideMutation,
    AutomationDecisionPage,
    AutomationDecisionRead,
    AutomationDecisionReviewMutation,
    CardAutomationMetricsFilters,
    CardAutomationMetricsRead,
    CardAutomationSettingsList,
    CardAutomationSettingsRead,
    CardAutomationSettingsUpdate,
    PersonalReviewItemCorrectionMutation,
    PersonalReviewItemCorrectionResult,
    PersonalReviewItemListFilters,
    PersonalReviewItemPage,
    PersonalReviewItemReviewMutation,
    PersonalReviewItemReviewResult,
    QuestionClusterActionMutation,
    QuestionClusterAllowedActions,
    QuestionClusterAnswerGenerationMutation,
    QuestionClusterAnswerGenerationResult,
    QuestionClusterBulkMutation,
    QuestionClusterBulkResult,
    QuestionClusterCreateCardMutation,
    QuestionClusterDetail,
    QuestionClusterDraftMutation,
    QuestionClusterLinkCardMutation,
    QuestionClusterListFilters,
    QuestionClusterMergeMutation,
    QuestionClusterMutationResult,
    QuestionClusterPage,
    QuestionClusterSplitMutation,
    QuestionOccurrenceReprocessMutation,
    QuestionOccurrenceReprocessResult,
)
from app.interviews.card_automation_service import (
    bulk_update_question_clusters,
    correct_personal_review_item,
    create_question_cluster_card,
    defer_question_cluster,
    get_card_automation_metrics,
    get_question_cluster_allowed_actions,
    get_question_cluster_detail,
    ignore_question_cluster,
    link_question_cluster_card,
    list_automation_decisions,
    list_card_automation_settings,
    list_managed_personal_review_items,
    list_personal_review_items,
    list_question_clusters,
    mark_question_cluster_important,
    merge_question_clusters,
    override_automation_decision,
    reopen_question_cluster,
    reprocess_question_occurrence,
    request_question_cluster_answer_generation,
    review_automation_decision,
    review_personal_review_item,
    split_question_cluster,
    update_card_automation_settings,
    update_question_cluster_draft,
)
from app.interviews.card_automation_types import (
    AutomationDecisionSource,
    AutomationDecisionType,
    LearningObjectType,
    PersonalReviewStatus,
    QuestionClusterStatus,
)

Session = Annotated[AsyncSession, Depends(get_db_session)]
IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=8, max_length=200),
]

admin_router = APIRouter(
    prefix="/admin/card-automation",
    tags=["admin-card-automation"],
)
mentor_router = APIRouter(
    prefix="/mentor/card-automation",
    tags=["mentor-card-automation"],
)
student_router = APIRouter(
    prefix="/students/me/personal-review-items",
    tags=["personal-interview-review"],
)


def _cluster_filters(
    *,
    direction_id: UUID | None,
    statuses: list[QuestionClusterStatus] | None,
    topic_name: str | None,
    learning_object_types: list[LearningObjectType] | None,
    min_distinct_interviews: int | None,
    min_distinct_companies: int | None,
    has_failed_answers: bool | None,
    min_confidence: float | None,
    max_confidence: float | None,
    has_possible_duplicate: bool | None,
    decision_source: AutomationDecisionSource | None,
    seen_from: datetime | None,
    seen_to: datetime | None,
    needs_action_only: bool,
    sort_by: str,
    sort_order: str,
    limit: int,
    offset: int,
) -> QuestionClusterListFilters:
    return QuestionClusterListFilters(
        direction_id=direction_id,
        statuses=statuses or [],
        topic_name=topic_name,
        learning_object_types=learning_object_types or [],
        min_distinct_interviews=min_distinct_interviews,
        min_distinct_companies=min_distinct_companies,
        has_failed_answers=has_failed_answers,
        min_confidence=min_confidence,
        max_confidence=max_confidence,
        has_possible_duplicate=has_possible_duplicate,
        decision_source=decision_source,
        seen_from=seen_from,
        seen_to=seen_to,
        needs_action_only=needs_action_only,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )


ClusterSort = Literal[
    "priority_score",
    "last_seen_at",
    "first_seen_at",
    "occurrences_count",
    "cluster_confidence",
]
SortOrder = Literal["asc", "desc"]


async def _clusters(
    session: AsyncSession,
    viewer: AdminUser | MentorUser,
    direction_id: UUID | None,
    statuses: list[QuestionClusterStatus] | None,
    topic_name: str | None,
    learning_object_types: list[LearningObjectType] | None,
    min_distinct_interviews: int | None,
    min_distinct_companies: int | None,
    has_failed_answers: bool | None,
    min_confidence: float | None,
    max_confidence: float | None,
    has_possible_duplicate: bool | None,
    decision_source: AutomationDecisionSource | None,
    seen_from: datetime | None,
    seen_to: datetime | None,
    needs_action_only: bool,
    sort_by: ClusterSort,
    sort_order: SortOrder,
    limit: int,
    offset: int,
) -> QuestionClusterPage:
    return await list_question_clusters(
        session,
        viewer,
        _cluster_filters(
            direction_id=direction_id,
            statuses=statuses,
            topic_name=topic_name,
            learning_object_types=learning_object_types,
            min_distinct_interviews=min_distinct_interviews,
            min_distinct_companies=min_distinct_companies,
            has_failed_answers=has_failed_answers,
            min_confidence=min_confidence,
            max_confidence=max_confidence,
            has_possible_duplicate=has_possible_duplicate,
            decision_source=decision_source,
            seen_from=seen_from,
            seen_to=seen_to,
            needs_action_only=needs_action_only,
            sort_by=sort_by,
            sort_order=sort_order,
            limit=limit,
            offset=offset,
        ),
    )


@admin_router.get("/clusters", response_model=QuestionClusterPage)
async def admin_clusters(
    session: Session,
    admin: AdminUser,
    direction_id: Annotated[UUID | None, Query()] = None,
    statuses: Annotated[list[QuestionClusterStatus] | None, Query()] = None,
    topic_name: Annotated[str | None, Query(min_length=1, max_length=240)] = None,
    learning_object_types: Annotated[list[LearningObjectType] | None, Query()] = None,
    min_distinct_interviews: Annotated[int | None, Query(ge=1)] = None,
    min_distinct_companies: Annotated[int | None, Query(ge=1)] = None,
    has_failed_answers: Annotated[bool | None, Query()] = None,
    min_confidence: Annotated[float | None, Query(ge=0, le=1)] = None,
    max_confidence: Annotated[float | None, Query(ge=0, le=1)] = None,
    has_possible_duplicate: Annotated[bool | None, Query()] = None,
    decision_source: Annotated[AutomationDecisionSource | None, Query()] = None,
    seen_from: Annotated[datetime | None, Query()] = None,
    seen_to: Annotated[datetime | None, Query()] = None,
    needs_action_only: Annotated[bool, Query()] = False,
    sort_by: Annotated[ClusterSort, Query()] = "priority_score",
    sort_order: Annotated[SortOrder, Query()] = "desc",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> QuestionClusterPage:
    return await _clusters(
        session,
        admin,
        direction_id,
        statuses,
        topic_name,
        learning_object_types,
        min_distinct_interviews,
        min_distinct_companies,
        has_failed_answers,
        min_confidence,
        max_confidence,
        has_possible_duplicate,
        decision_source,
        seen_from,
        seen_to,
        needs_action_only,
        sort_by,
        sort_order,
        limit,
        offset,
    )


@mentor_router.get("/clusters", response_model=QuestionClusterPage)
async def mentor_clusters(
    session: Session,
    mentor: MentorUser,
    direction_id: Annotated[UUID | None, Query()] = None,
    statuses: Annotated[list[QuestionClusterStatus] | None, Query()] = None,
    topic_name: Annotated[str | None, Query(min_length=1, max_length=240)] = None,
    learning_object_types: Annotated[list[LearningObjectType] | None, Query()] = None,
    min_distinct_interviews: Annotated[int | None, Query(ge=1)] = None,
    min_distinct_companies: Annotated[int | None, Query(ge=1)] = None,
    has_failed_answers: Annotated[bool | None, Query()] = None,
    min_confidence: Annotated[float | None, Query(ge=0, le=1)] = None,
    max_confidence: Annotated[float | None, Query(ge=0, le=1)] = None,
    has_possible_duplicate: Annotated[bool | None, Query()] = None,
    decision_source: Annotated[AutomationDecisionSource | None, Query()] = None,
    seen_from: Annotated[datetime | None, Query()] = None,
    seen_to: Annotated[datetime | None, Query()] = None,
    needs_action_only: Annotated[bool, Query()] = False,
    sort_by: Annotated[ClusterSort, Query()] = "priority_score",
    sort_order: Annotated[SortOrder, Query()] = "desc",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> QuestionClusterPage:
    return await _clusters(
        session,
        mentor,
        direction_id,
        statuses,
        topic_name,
        learning_object_types,
        min_distinct_interviews,
        min_distinct_companies,
        has_failed_answers,
        min_confidence,
        max_confidence,
        has_possible_duplicate,
        decision_source,
        seen_from,
        seen_to,
        needs_action_only,
        sort_by,
        sort_order,
        limit,
        offset,
    )


@admin_router.post("/clusters/bulk", response_model=QuestionClusterBulkResult)
async def admin_bulk_clusters(
    payload: QuestionClusterBulkMutation,
    session: Session,
    admin: AdminUser,
    _idempotency_key: IdempotencyKey,
) -> QuestionClusterBulkResult:
    # Keep this static route before ``/clusters/{cluster_id}``, otherwise
    # Starlette would route the literal ``bulk`` through UUID validation.
    return await bulk_update_question_clusters(session, admin, payload)


@admin_router.get("/clusters/{cluster_id}", response_model=QuestionClusterDetail)
async def admin_cluster(
    cluster_id: UUID, session: Session, admin: AdminUser
) -> QuestionClusterDetail:
    return await get_question_cluster_detail(session, admin, cluster_id)


@mentor_router.get("/clusters/{cluster_id}", response_model=QuestionClusterDetail)
async def mentor_cluster(
    cluster_id: UUID, session: Session, mentor: MentorUser
) -> QuestionClusterDetail:
    return await get_question_cluster_detail(session, mentor, cluster_id)


@admin_router.get(
    "/clusters/{cluster_id}/allowed-actions",
    response_model=QuestionClusterAllowedActions,
)
async def admin_cluster_allowed_actions(
    cluster_id: UUID, session: Session, admin: AdminUser
) -> QuestionClusterAllowedActions:
    return await get_question_cluster_allowed_actions(session, admin, cluster_id)


@mentor_router.get(
    "/clusters/{cluster_id}/allowed-actions",
    response_model=QuestionClusterAllowedActions,
)
async def mentor_cluster_allowed_actions(
    cluster_id: UUID, session: Session, mentor: MentorUser
) -> QuestionClusterAllowedActions:
    return await get_question_cluster_allowed_actions(session, mentor, cluster_id)


@admin_router.post(
    "/occurrences/{question_id}/reprocess",
    response_model=QuestionOccurrenceReprocessResult,
)
async def admin_reprocess_occurrence(
    question_id: UUID,
    payload: QuestionOccurrenceReprocessMutation,
    session: Session,
    admin: AdminUser,
    _idempotency_key: IdempotencyKey,
) -> QuestionOccurrenceReprocessResult:
    return await reprocess_question_occurrence(session, admin, question_id, payload)


@mentor_router.post(
    "/occurrences/{question_id}/reprocess",
    response_model=QuestionOccurrenceReprocessResult,
)
async def mentor_reprocess_occurrence(
    question_id: UUID,
    payload: QuestionOccurrenceReprocessMutation,
    session: Session,
    mentor: MentorUser,
    _idempotency_key: IdempotencyKey,
) -> QuestionOccurrenceReprocessResult:
    return await reprocess_question_occurrence(session, mentor, question_id, payload)


@admin_router.post(
    "/clusters/{cluster_id}/generate-answer",
    response_model=QuestionClusterAnswerGenerationResult,
)
async def admin_generate_cluster_answer(
    cluster_id: UUID,
    payload: QuestionClusterAnswerGenerationMutation,
    session: Session,
    admin: AdminUser,
    _idempotency_key: IdempotencyKey,
) -> QuestionClusterAnswerGenerationResult:
    return await request_question_cluster_answer_generation(session, admin, cluster_id, payload)


@admin_router.post(
    "/clusters/{cluster_id}/link-card",
    response_model=QuestionClusterMutationResult,
)
async def admin_link_cluster_card(
    cluster_id: UUID,
    payload: QuestionClusterLinkCardMutation,
    session: Session,
    admin: AdminUser,
    _idempotency_key: IdempotencyKey,
) -> QuestionClusterMutationResult:
    return await link_question_cluster_card(session, admin, cluster_id, payload)


@admin_router.patch(
    "/clusters/{cluster_id}/draft",
    response_model=QuestionClusterMutationResult,
)
async def admin_update_cluster_draft(
    cluster_id: UUID,
    payload: QuestionClusterDraftMutation,
    session: Session,
    admin: AdminUser,
    idempotency_key: IdempotencyKey,
) -> QuestionClusterMutationResult:
    return await update_question_cluster_draft(
        session,
        admin,
        cluster_id,
        payload,
        idempotency_key=idempotency_key,
    )


@mentor_router.patch(
    "/clusters/{cluster_id}/draft",
    response_model=QuestionClusterMutationResult,
)
async def mentor_update_cluster_draft(
    cluster_id: UUID,
    payload: QuestionClusterDraftMutation,
    session: Session,
    mentor: MentorUser,
    idempotency_key: IdempotencyKey,
) -> QuestionClusterMutationResult:
    return await update_question_cluster_draft(
        session,
        mentor,
        cluster_id,
        payload,
        idempotency_key=idempotency_key,
    )


@admin_router.post(
    "/clusters/{cluster_id}/create-card",
    response_model=QuestionClusterMutationResult,
)
async def admin_create_cluster_card(
    cluster_id: UUID,
    payload: QuestionClusterCreateCardMutation,
    session: Session,
    admin: AdminUser,
    _idempotency_key: IdempotencyKey,
) -> QuestionClusterMutationResult:
    return await create_question_cluster_card(session, admin, cluster_id, payload)


@admin_router.post(
    "/clusters/{cluster_id}/split",
    response_model=QuestionClusterMutationResult,
)
async def admin_split_cluster(
    cluster_id: UUID,
    payload: QuestionClusterSplitMutation,
    session: Session,
    admin: AdminUser,
    _idempotency_key: IdempotencyKey,
) -> QuestionClusterMutationResult:
    return await split_question_cluster(session, admin, cluster_id, payload)


@admin_router.post(
    "/clusters/{cluster_id}/merge",
    response_model=QuestionClusterMutationResult,
)
async def admin_merge_clusters(
    cluster_id: UUID,
    payload: QuestionClusterMergeMutation,
    session: Session,
    admin: AdminUser,
    _idempotency_key: IdempotencyKey,
) -> QuestionClusterMutationResult:
    return await merge_question_clusters(session, admin, cluster_id, payload)


async def _set_cluster_state(
    action: Literal["ignore", "defer", "mark-important", "reopen"],
    session: AsyncSession,
    viewer: AdminUser | MentorUser,
    cluster_id: UUID,
    payload: QuestionClusterActionMutation,
) -> QuestionClusterMutationResult:
    handlers = {
        "ignore": ignore_question_cluster,
        "defer": defer_question_cluster,
        "mark-important": mark_question_cluster_important,
        "reopen": reopen_question_cluster,
    }
    return await handlers[action](session, viewer, cluster_id, payload)


@admin_router.post(
    "/clusters/{cluster_id}/{action}",
    response_model=QuestionClusterMutationResult,
)
async def admin_set_cluster_state(
    cluster_id: UUID,
    action: Literal["ignore", "defer", "mark-important", "reopen"],
    payload: QuestionClusterActionMutation,
    session: Session,
    admin: AdminUser,
    _idempotency_key: IdempotencyKey,
) -> QuestionClusterMutationResult:
    return await _set_cluster_state(action, session, admin, cluster_id, payload)


@mentor_router.post(
    "/clusters/{cluster_id}/{action}",
    response_model=QuestionClusterMutationResult,
)
async def mentor_set_cluster_state(
    cluster_id: UUID,
    action: Literal["ignore", "defer", "mark-important", "reopen"],
    payload: QuestionClusterActionMutation,
    session: Session,
    mentor: MentorUser,
    _idempotency_key: IdempotencyKey,
) -> QuestionClusterMutationResult:
    return await _set_cluster_state(action, session, mentor, cluster_id, payload)


def _decision_filters(
    *,
    direction_id: UUID | None,
    entity_type: str | None,
    decision_types: list[AutomationDecisionType] | None,
    decision_sources: list[AutomationDecisionSource] | None,
    is_audit_sample: bool | None,
    is_reviewed: bool | None,
    is_overridden: bool | None,
    created_from: datetime | None,
    created_to: datetime | None,
    sort_order: SortOrder,
    limit: int,
    offset: int,
) -> AutomationDecisionListFilters:
    return AutomationDecisionListFilters(
        direction_id=direction_id,
        entity_type=entity_type,
        decision_types=decision_types or [],
        decision_sources=decision_sources or [],
        is_audit_sample=is_audit_sample,
        is_reviewed=is_reviewed,
        is_overridden=is_overridden,
        created_from=created_from,
        created_to=created_to,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )


async def _decisions(
    session: AsyncSession,
    viewer: AdminUser | MentorUser,
    direction_id: UUID | None,
    entity_type: str | None,
    decision_types: list[AutomationDecisionType] | None,
    decision_sources: list[AutomationDecisionSource] | None,
    is_audit_sample: bool | None,
    is_reviewed: bool | None,
    is_overridden: bool | None,
    created_from: datetime | None,
    created_to: datetime | None,
    sort_order: SortOrder,
    limit: int,
    offset: int,
) -> AutomationDecisionPage:
    return await list_automation_decisions(
        session,
        viewer,
        _decision_filters(
            direction_id=direction_id,
            entity_type=entity_type,
            decision_types=decision_types,
            decision_sources=decision_sources,
            is_audit_sample=is_audit_sample,
            is_reviewed=is_reviewed,
            is_overridden=is_overridden,
            created_from=created_from,
            created_to=created_to,
            sort_order=sort_order,
            limit=limit,
            offset=offset,
        ),
    )


@admin_router.get("/decisions", response_model=AutomationDecisionPage)
async def admin_decisions(
    session: Session,
    admin: AdminUser,
    direction_id: Annotated[UUID | None, Query()] = None,
    entity_type: Annotated[str | None, Query(min_length=1, max_length=60)] = None,
    decision_types: Annotated[list[AutomationDecisionType] | None, Query()] = None,
    decision_sources: Annotated[list[AutomationDecisionSource] | None, Query()] = None,
    is_audit_sample: Annotated[bool | None, Query()] = None,
    is_reviewed: Annotated[bool | None, Query()] = None,
    is_overridden: Annotated[bool | None, Query()] = None,
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
    sort_order: Annotated[SortOrder, Query()] = "desc",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AutomationDecisionPage:
    return await _decisions(
        session,
        admin,
        direction_id,
        entity_type,
        decision_types,
        decision_sources,
        is_audit_sample,
        is_reviewed,
        is_overridden,
        created_from,
        created_to,
        sort_order,
        limit,
        offset,
    )


@mentor_router.get("/decisions", response_model=AutomationDecisionPage)
async def mentor_decisions(
    session: Session,
    mentor: MentorUser,
    direction_id: Annotated[UUID | None, Query()] = None,
    entity_type: Annotated[str | None, Query(min_length=1, max_length=60)] = None,
    decision_types: Annotated[list[AutomationDecisionType] | None, Query()] = None,
    decision_sources: Annotated[list[AutomationDecisionSource] | None, Query()] = None,
    is_audit_sample: Annotated[bool | None, Query()] = None,
    is_reviewed: Annotated[bool | None, Query()] = None,
    is_overridden: Annotated[bool | None, Query()] = None,
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
    sort_order: Annotated[SortOrder, Query()] = "desc",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AutomationDecisionPage:
    return await _decisions(
        session,
        mentor,
        direction_id,
        entity_type,
        decision_types,
        decision_sources,
        is_audit_sample,
        is_reviewed,
        is_overridden,
        created_from,
        created_to,
        sort_order,
        limit,
        offset,
    )


@admin_router.post(
    "/decisions/{decision_id}/review",
    response_model=AutomationDecisionRead,
)
async def admin_review_decision(
    decision_id: UUID,
    payload: AutomationDecisionReviewMutation,
    session: Session,
    admin: AdminUser,
    _idempotency_key: IdempotencyKey,
) -> AutomationDecisionRead:
    return await review_automation_decision(session, admin, decision_id, payload)


@mentor_router.post(
    "/decisions/{decision_id}/review",
    response_model=AutomationDecisionRead,
)
async def mentor_review_decision(
    decision_id: UUID,
    payload: AutomationDecisionReviewMutation,
    session: Session,
    mentor: MentorUser,
    _idempotency_key: IdempotencyKey,
) -> AutomationDecisionRead:
    return await review_automation_decision(session, mentor, decision_id, payload)


@admin_router.post(
    "/decisions/{decision_id}/override",
    response_model=AutomationDecisionRead,
)
async def admin_override_decision(
    decision_id: UUID,
    payload: AutomationDecisionOverrideMutation,
    session: Session,
    admin: AdminUser,
    _idempotency_key: IdempotencyKey,
) -> AutomationDecisionRead:
    return await override_automation_decision(session, admin, decision_id, payload)


@mentor_router.post(
    "/decisions/{decision_id}/override",
    response_model=AutomationDecisionRead,
)
async def mentor_override_decision(
    decision_id: UUID,
    payload: AutomationDecisionOverrideMutation,
    session: Session,
    mentor: MentorUser,
    _idempotency_key: IdempotencyKey,
) -> AutomationDecisionRead:
    return await override_automation_decision(session, mentor, decision_id, payload)


@admin_router.get("/settings", response_model=CardAutomationSettingsList)
async def admin_settings(session: Session, admin: AdminUser) -> CardAutomationSettingsList:
    return await list_card_automation_settings(session, admin)


@admin_router.put("/settings", response_model=CardAutomationSettingsRead)
async def admin_update_settings(
    payload: CardAutomationSettingsUpdate,
    session: Session,
    admin: AdminUser,
    idempotency_key: IdempotencyKey,
) -> CardAutomationSettingsRead:
    return await update_card_automation_settings(session, admin, payload, idempotency_key)


@admin_router.get("/metrics", response_model=CardAutomationMetricsRead)
async def admin_metrics(
    session: Session,
    admin: AdminUser,
    period_from: Annotated[date, Query()],
    period_to: Annotated[date, Query()],
    direction_id: Annotated[UUID | None, Query()] = None,
) -> CardAutomationMetricsRead:
    return await get_card_automation_metrics(
        session,
        admin,
        CardAutomationMetricsFilters(
            period_from=period_from,
            period_to=period_to,
            direction_id=direction_id,
        ),
    )


def _personal_filters(
    *,
    direction_id: UUID | None,
    statuses: list[PersonalReviewStatus] | None,
    due_only: bool,
    due_before: datetime | None,
    sort_order: SortOrder,
    limit: int,
    offset: int,
) -> PersonalReviewItemListFilters:
    return PersonalReviewItemListFilters(
        direction_id=direction_id,
        statuses=statuses or [],
        due_only=due_only,
        due_before=due_before,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )


async def _managed_personal_items(
    session: AsyncSession,
    viewer: AdminUser | MentorUser,
    student_id: UUID,
    direction_id: UUID | None,
    statuses: list[PersonalReviewStatus] | None,
    due_only: bool,
    due_before: datetime | None,
    sort_order: SortOrder,
    limit: int,
    offset: int,
) -> PersonalReviewItemPage:
    return await list_managed_personal_review_items(
        session,
        viewer,
        student_id,
        _personal_filters(
            direction_id=direction_id,
            statuses=statuses,
            due_only=due_only,
            due_before=due_before,
            sort_order=sort_order,
            limit=limit,
            offset=offset,
        ),
    )


@admin_router.get(
    "/students/{student_id}/personal-review-items",
    response_model=PersonalReviewItemPage,
)
async def admin_managed_personal_items(
    student_id: UUID,
    session: Session,
    admin: AdminUser,
    direction_id: Annotated[UUID | None, Query()] = None,
    statuses: Annotated[list[PersonalReviewStatus] | None, Query()] = None,
    due_only: Annotated[bool, Query()] = False,
    due_before: Annotated[datetime | None, Query()] = None,
    sort_order: Annotated[SortOrder, Query()] = "asc",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PersonalReviewItemPage:
    return await _managed_personal_items(
        session,
        admin,
        student_id,
        direction_id,
        statuses,
        due_only,
        due_before,
        sort_order,
        limit,
        offset,
    )


@mentor_router.get(
    "/students/{student_id}/personal-review-items",
    response_model=PersonalReviewItemPage,
)
async def mentor_managed_personal_items(
    student_id: UUID,
    session: Session,
    mentor: MentorUser,
    direction_id: Annotated[UUID | None, Query()] = None,
    statuses: Annotated[list[PersonalReviewStatus] | None, Query()] = None,
    due_only: Annotated[bool, Query()] = False,
    due_before: Annotated[datetime | None, Query()] = None,
    sort_order: Annotated[SortOrder, Query()] = "asc",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PersonalReviewItemPage:
    return await _managed_personal_items(
        session,
        mentor,
        student_id,
        direction_id,
        statuses,
        due_only,
        due_before,
        sort_order,
        limit,
        offset,
    )


@admin_router.patch(
    "/students/{student_id}/personal-review-items/{item_id}",
    response_model=PersonalReviewItemCorrectionResult,
)
async def admin_correct_personal_item(
    student_id: UUID,
    item_id: UUID,
    payload: PersonalReviewItemCorrectionMutation,
    session: Session,
    admin: AdminUser,
    _idempotency_key: IdempotencyKey,
) -> PersonalReviewItemCorrectionResult:
    return await correct_personal_review_item(session, admin, student_id, item_id, payload)


@mentor_router.patch(
    "/students/{student_id}/personal-review-items/{item_id}",
    response_model=PersonalReviewItemCorrectionResult,
)
async def mentor_correct_personal_item(
    student_id: UUID,
    item_id: UUID,
    payload: PersonalReviewItemCorrectionMutation,
    session: Session,
    mentor: MentorUser,
    _idempotency_key: IdempotencyKey,
) -> PersonalReviewItemCorrectionResult:
    return await correct_personal_review_item(session, mentor, student_id, item_id, payload)


@student_router.get("", response_model=PersonalReviewItemPage)
async def personal_review_items(
    session: Session,
    student: StudentUser,
    direction_id: Annotated[UUID | None, Query()] = None,
    statuses: Annotated[list[PersonalReviewStatus] | None, Query()] = None,
    due_only: Annotated[bool, Query()] = True,
    due_before: Annotated[datetime | None, Query()] = None,
    sort_order: Annotated[SortOrder, Query()] = "asc",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PersonalReviewItemPage:
    return await list_personal_review_items(
        session,
        student,
        _personal_filters(
            direction_id=direction_id,
            statuses=statuses or [],
            due_only=due_only,
            due_before=due_before,
            sort_order=sort_order,
            limit=limit,
            offset=offset,
        ),
    )


@student_router.post("/{item_id}/review", response_model=PersonalReviewItemReviewResult)
async def review_personal_item(
    item_id: UUID,
    payload: PersonalReviewItemReviewMutation,
    session: Session,
    student: StudentUser,
    _idempotency_key: IdempotencyKey,
) -> PersonalReviewItemReviewResult:
    return await review_personal_review_item(session, student, item_id, payload)
