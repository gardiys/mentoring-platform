from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.interviews.card_automation_types import (
    AnswerContractStatus,
    AutomationDecisionSource,
    AutomationDecisionType,
    AutomationReviewResult,
    LearningObjectType,
    PairwiseCardMatchDecision,
    PersonalReviewStatus,
    QuestionClusterStatus,
    QuestionOccurrenceStatus,
)
from app.interviews.models import (
    InterviewCardFrequency,
    InterviewCardFrequencyMode,
    InterviewReviewRating,
)


class StrictAPIModel(BaseModel):
    """Base contract for card-automation endpoints.

    Unknown fields are rejected so a typo cannot silently alter the meaning of a
    moderation command. ``from_attributes`` keeps read models usable with ORM
    projections as well as explicit dictionaries.
    """

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
        validate_default=True,
    )


class QuestionClusterAction(StrEnum):
    UPDATE_DRAFT = "update_draft"
    LINK_CARD = "link_card"
    CREATE_CARD = "create_card"
    SPLIT = "split"
    MERGE = "merge"
    IGNORE = "ignore"
    DEFER = "defer"
    MARK_IMPORTANT = "mark_important"
    REOPEN = "reopen"


class QuestionClusterBulkAction(StrEnum):
    CONFIRM_EXACT_MATCHES = "confirm_exact_matches"
    CONFIRM_HIGH_CONFIDENCE_MATCHES = "confirm_high_confidence_matches"
    IGNORE_NOISE = "ignore_noise"
    DEFER_SINGLETONS = "defer_singletons"
    LINK_CARD = "link_card"
    APPLY_TOPIC = "apply_topic"


_CARD_TARGET_OVERRIDE_TYPES = frozenset(
    {
        AutomationDecisionType.EXACT_CARD_MATCH,
        AutomationDecisionType.ALIAS_CARD_MATCH,
        AutomationDecisionType.SEMANTIC_CARD_MATCH,
        AutomationDecisionType.CLUSTER_LINKED,
        AutomationDecisionType.MANUAL_OVERRIDE,
    }
)
_CLUSTER_TARGET_OVERRIDE_TYPES = frozenset(
    {
        AutomationDecisionType.CLUSTER_MATCH,
        AutomationDecisionType.CLUSTER_MERGED,
        AutomationDecisionType.MANUAL_OVERRIDE,
    }
)


class AnswerContract(StrictAPIModel):
    short_answer: str = Field(min_length=1)
    required_points: list[str] = Field(default_factory=list)
    optional_points: list[str] = Field(default_factory=list)
    common_mistakes: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    difficulty: Literal["junior", "middle", "senior", "mixed"]
    version_scope: list[str] = Field(default_factory=list)
    source_references: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class AnswerValidationResult(StrictAPIModel):
    supported: bool
    unsupported_claims: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    missing_required_points: list[str] = Field(default_factory=list)
    version_sensitive_claims: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class QuestionClusterAllowedActions(StrictAPIModel):
    cluster_id: UUID
    version: int = Field(ge=1)
    actions: list[QuestionClusterAction] = Field(default_factory=list)


class QuestionClusterCardMatch(StrictAPIModel):
    card_id: UUID
    question_markdown: str
    answer_markdown: str
    category: str
    semantic_score: float = Field(ge=0, le=1)
    combined_score: float | None = Field(default=None, ge=0, le=1)
    judge_decision: PairwiseCardMatchDecision | None = None
    judge_confidence: float | None = Field(default=None, ge=0, le=1)
    judge_reason: str | None = None
    is_confirmed_alias: bool = False


class QuestionClusterSummary(StrictAPIModel):
    id: UUID
    direction_id: UUID
    direction_slug: str
    direction_title: str
    status: QuestionClusterStatus
    canonical_question: str
    learning_object_type: LearningObjectType
    deck_id: UUID | None = None
    topic_name: str | None = None
    subtopic_name: str | None = None
    topic_candidates: list[str] = Field(default_factory=list)
    linked_card_id: UUID | None = None
    best_match: QuestionClusterCardMatch | None = None
    last_decision_source: AutomationDecisionSource | None = None
    occurrences_count: int = Field(ge=0)
    distinct_interviews_count: int = Field(ge=0)
    distinct_companies_count: int = Field(ge=0)
    distinct_students_count: int = Field(ge=0)
    failed_answers_count: int = Field(ge=0)
    priority_score: float = Field(ge=0)
    quality_score: float = Field(ge=0, le=1)
    cluster_confidence: float = Field(ge=0, le=1)
    first_seen_at: datetime
    last_seen_at: datetime
    manual_important: bool
    version: int = Field(ge=1)
    allowed_actions: list[QuestionClusterAction] = Field(default_factory=list)


class QuestionClusterListFilters(StrictAPIModel):
    direction_id: UUID | None = None
    statuses: list[QuestionClusterStatus] = Field(default_factory=list)
    topic_name: str | None = Field(default=None, min_length=1, max_length=240)
    learning_object_types: list[LearningObjectType] = Field(default_factory=list)
    min_distinct_interviews: int | None = Field(default=None, ge=1)
    min_distinct_companies: int | None = Field(default=None, ge=1)
    has_failed_answers: bool | None = None
    min_confidence: float | None = Field(default=None, ge=0, le=1)
    max_confidence: float | None = Field(default=None, ge=0, le=1)
    has_possible_duplicate: bool | None = None
    decision_source: AutomationDecisionSource | None = None
    seen_from: datetime | None = None
    seen_to: datetime | None = None
    needs_action_only: bool = False
    sort_by: Literal[
        "priority_score",
        "last_seen_at",
        "first_seen_at",
        "occurrences_count",
        "cluster_confidence",
    ] = "priority_score"
    sort_order: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_ranges(self) -> QuestionClusterListFilters:
        if (
            self.min_confidence is not None
            and self.max_confidence is not None
            and self.min_confidence > self.max_confidence
        ):
            raise ValueError("min_confidence cannot exceed max_confidence")
        if (
            self.seen_from is not None
            and self.seen_to is not None
            and self.seen_from > self.seen_to
        ):
            raise ValueError("seen_from cannot be after seen_to")
        return self


class QuestionClusterPage(StrictAPIModel):
    items: list[QuestionClusterSummary]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class QuestionClusterVariantRead(StrictAPIModel):
    question_text: str
    normalized_question_text: str
    occurrences_count: int = Field(ge=1)
    first_seen_at: datetime
    last_seen_at: datetime


class QuestionClusterCompanyRead(StrictAPIModel):
    company_id: UUID | None = None
    company_name: str
    occurrences_count: int = Field(ge=1)


class QuestionClusterInterviewRead(StrictAPIModel):
    interview_id: UUID
    company_id: UUID | None = None
    company_name: str
    interviewed_at: datetime
    occurrences_count: int = Field(ge=1)


class QuestionClusterOccurrenceRead(StrictAPIModel):
    id: UUID
    interview_id: UUID
    student_id: UUID
    student_name: str
    company_id: UUID | None = None
    company_name: str
    interviewed_at: datetime
    question_text: str
    canonical_question_candidate: str | None = None
    source_context: str | None = None
    answer_text: str | None = None
    answer_assessment: str | None = None
    learning_object_type: LearningObjectType
    routing_confidence: float | None = Field(default=None, ge=0, le=1)
    quality_flags: list[str] = Field(default_factory=list)
    automation_status: QuestionOccurrenceStatus
    automation_revision: int = Field(ge=1)
    automation_error: str | None = None
    created_at: datetime


class QuestionOccurrenceReprocessMutation(StrictAPIModel):
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2_000)


class QuestionOccurrenceReprocessResult(StrictAPIModel):
    question_id: UUID
    revision: int = Field(ge=1)
    job_id: str = Field(min_length=1)


class QuestionClusterAnswerGenerationMutation(StrictAPIModel):
    expected_version: int = Field(ge=1)


class QuestionClusterAnswerGenerationResult(StrictAPIModel):
    cluster_id: UUID
    version: int = Field(ge=1)
    job_id: str = Field(min_length=1)


class AutomationDecisionRead(StrictAPIModel):
    id: UUID
    entity_type: str
    entity_id: UUID
    entity_version: int | None = Field(default=None, ge=1)
    question_text: str | None = None
    decision_type: AutomationDecisionType
    decision_source: AutomationDecisionSource
    selected_card_id: UUID | None = None
    selected_card_question: str | None = None
    selected_cluster_id: UUID | None = None
    selected_cluster_question: str | None = None
    candidate_card_ids: list[UUID] = Field(default_factory=list)
    candidate_cluster_ids: list[UUID] = Field(default_factory=list)
    retrieval_scores: dict[str, object] = Field(default_factory=dict)
    judge_result: dict[str, object] | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    similarity_score: float | None = Field(default=None, ge=0, le=1)
    reason: str
    model_provider: str | None = None
    model_name: str | None = None
    prompt_version: str | None = None
    schema_version: str | None = None
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cost: Decimal | None = Field(default=None, ge=0)
    latency_ms: int | None = Field(default=None, ge=0)
    is_audit_sample: bool
    review_result: AutomationReviewResult | None = None
    reviewed_by_user_id: UUID | None = None
    reviewed_by_name: str | None = None
    reviewed_at: datetime | None = None
    review_reason: str | None = None
    is_overridden: bool
    overridden_by_user_id: UUID | None = None
    overridden_by_name: str | None = None
    override_reason: str | None = None
    overridden_at: datetime | None = None
    created_at: datetime


class QuestionClusterManualHistoryRead(StrictAPIModel):
    id: UUID
    action: str
    actor_user_id: UUID | None = None
    actor_name: str | None = None
    reason: str | None = None
    changes: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class QuestionClusterTopicOption(StrictAPIModel):
    deck_id: UUID
    deck_title: str
    topics: list[str] = Field(default_factory=list)


class QuestionClusterDetail(QuestionClusterSummary):
    normalized_canonical_question: str
    representative_occurrence_id: UUID | None = None
    merged_into_cluster_id: UUID | None = None
    parent_cluster_id: UUID | None = None
    question_variants: list[QuestionClusterVariantRead] = Field(default_factory=list)
    companies: list[QuestionClusterCompanyRead] = Field(default_factory=list)
    interviews: list[QuestionClusterInterviewRead] = Field(default_factory=list)
    occurrences: list[QuestionClusterOccurrenceRead] = Field(default_factory=list)
    top_card_matches: list[QuestionClusterCardMatch] = Field(default_factory=list)
    answer_contract: AnswerContract | None = None
    answer_validation: AnswerValidationResult | None = None
    answer_status: AnswerContractStatus | None = None
    decisions: list[AutomationDecisionRead] = Field(default_factory=list)
    manual_history: list[QuestionClusterManualHistoryRead] = Field(default_factory=list)
    topic_options: list[QuestionClusterTopicOption] = Field(default_factory=list)
    promoted_at: datetime | None = None
    promotion_reason: str | None = None
    membership_revision: int = Field(ge=0)
    stats_revision: int = Field(ge=0)


class _QuestionClusterMutationBase(StrictAPIModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2_000)


class QuestionClusterDraftMutation(_QuestionClusterMutationBase):
    canonical_question: str | None = Field(default=None, min_length=1, max_length=20_000)
    topic_name: str | None = Field(default=None, min_length=1, max_length=240)
    subtopic_name: str | None = Field(default=None, min_length=1, max_length=240)
    answer_contract: AnswerContract | None = None
    preserve_answer_status: bool = False

    @model_validator(mode="after")
    def validate_draft_changes(self) -> QuestionClusterDraftMutation:
        changed_fields = {
            "canonical_question",
            "topic_name",
            "subtopic_name",
            "answer_contract",
        } & self.model_fields_set
        if not changed_fields:
            raise ValueError("at least one cluster draft field must be provided")
        if "canonical_question" in self.model_fields_set and self.canonical_question is None:
            raise ValueError("canonical_question cannot be null")
        if "answer_contract" in self.model_fields_set and self.answer_contract is None:
            raise ValueError("answer_contract cannot be null")
        if self.preserve_answer_status and "answer_contract" in self.model_fields_set:
            raise ValueError(
                "preserve_answer_status cannot be used when answer_contract is provided"
            )
        return self


class QuestionClusterLinkCardMutation(_QuestionClusterMutationBase):
    card_id: UUID
    confirm_alias: bool = False


class QuestionClusterCreateCardMutation(_QuestionClusterMutationBase):
    deck_id: UUID
    category: str = Field(min_length=1, max_length=240)
    subcategory: str | None = Field(default=None, max_length=240)
    question_markdown: str = Field(min_length=1)
    answer_markdown: str = Field(min_length=1)
    frequency: InterviewCardFrequency = InterviewCardFrequency.OCCASIONAL
    frequency_mode: InterviewCardFrequencyMode = InterviewCardFrequencyMode.MANUAL


class QuestionClusterSplitMutation(_QuestionClusterMutationBase):
    occurrence_ids: list[UUID] = Field(min_length=1, max_length=500)
    new_canonical_question: str = Field(min_length=1)
    new_topic_name: str | None = Field(default=None, min_length=1, max_length=240)
    new_subtopic_name: str | None = Field(default=None, min_length=1, max_length=240)

    @field_validator("occurrence_ids")
    @classmethod
    def occurrence_ids_are_unique(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("occurrence_ids must be unique")
        return value


class QuestionClusterMergeMutation(_QuestionClusterMutationBase):
    target_cluster_id: UUID
    target_expected_version: int = Field(ge=1)


class QuestionClusterActionMutation(_QuestionClusterMutationBase):
    pass


class QuestionClusterMutationResult(StrictAPIModel):
    cluster: QuestionClusterSummary
    decision_id: UUID
    created_card_id: UUID | None = None
    affected_cluster_ids: list[UUID] = Field(default_factory=list)


class QuestionClusterBulkMutation(StrictAPIModel):
    action: QuestionClusterBulkAction
    cluster_ids: list[UUID] = Field(min_length=1, max_length=100)
    expected_versions: dict[UUID, int] = Field(min_length=1, max_length=100)
    confirmation: Literal[True]
    reason: str = Field(min_length=1, max_length=2_000)
    card_id: UUID | None = None
    topic_name: str | None = Field(default=None, min_length=1, max_length=240)

    @field_validator("cluster_ids")
    @classmethod
    def cluster_ids_are_unique(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("cluster_ids must be unique")
        return value

    @field_validator("expected_versions")
    @classmethod
    def expected_versions_are_positive(cls, value: dict[UUID, int]) -> dict[UUID, int]:
        if any(version < 1 for version in value.values()):
            raise ValueError("expected_versions values must be positive")
        return value

    @model_validator(mode="after")
    def validate_action_arguments(self) -> QuestionClusterBulkMutation:
        if set(self.expected_versions) != set(self.cluster_ids):
            raise ValueError("expected_versions must contain exactly every selected cluster")
        if self.action is QuestionClusterBulkAction.LINK_CARD:
            if self.card_id is None:
                raise ValueError("card_id is required for link_card")
            if self.topic_name is not None:
                raise ValueError("topic_name is not allowed for link_card")
        elif self.action is QuestionClusterBulkAction.APPLY_TOPIC:
            if self.topic_name is None:
                raise ValueError("topic_name is required for apply_topic")
            if self.card_id is not None:
                raise ValueError("card_id is not allowed for apply_topic")
        elif self.card_id is not None or self.topic_name is not None:
            raise ValueError("card_id and topic_name are not allowed for this action")
        return self


class QuestionClusterBulkItemResult(StrictAPIModel):
    cluster_id: UUID
    succeeded: bool
    cluster: QuestionClusterSummary | None = None
    decision_id: UUID | None = None
    error_code: str | None = None
    error_message: str | None = None


class QuestionClusterBulkResult(StrictAPIModel):
    requested_count: int = Field(ge=1)
    succeeded_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    items: list[QuestionClusterBulkItemResult]

    @model_validator(mode="after")
    def validate_counts(self) -> QuestionClusterBulkResult:
        if self.succeeded_count + self.failed_count != self.requested_count:
            raise ValueError("bulk result counters do not add up to requested_count")
        if len(self.items) != self.requested_count:
            raise ValueError("bulk result must contain one item per requested cluster")
        return self


class AutomationDecisionPage(StrictAPIModel):
    items: list[AutomationDecisionRead]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class AutomationDecisionListFilters(StrictAPIModel):
    direction_id: UUID | None = None
    entity_type: str | None = Field(default=None, min_length=1, max_length=60)
    decision_types: list[AutomationDecisionType] = Field(default_factory=list)
    decision_sources: list[AutomationDecisionSource] = Field(default_factory=list)
    is_audit_sample: bool | None = None
    is_reviewed: bool | None = None
    is_overridden: bool | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    sort_order: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_created_range(self) -> AutomationDecisionListFilters:
        if (
            self.created_from is not None
            and self.created_to is not None
            and self.created_from > self.created_to
        ):
            raise ValueError("created_from cannot be after created_to")
        return self


class AutomationDecisionReviewMutation(StrictAPIModel):
    result: AutomationReviewResult
    reason: str | None = Field(default=None, min_length=1, max_length=2_000)

    @model_validator(mode="after")
    def require_other_reason(self) -> AutomationDecisionReviewMutation:
        if self.result is AutomationReviewResult.OTHER and self.reason is None:
            raise ValueError("reason is required for an 'other' review result")
        return self


class AutomationDecisionOverrideMutation(StrictAPIModel):
    expected_entity_version: int = Field(ge=1)
    replacement_decision_type: AutomationDecisionType
    selected_card_id: UUID | None = None
    selected_cluster_id: UUID | None = None
    reason: str = Field(min_length=1, max_length=2_000)

    @model_validator(mode="after")
    def validate_replacement_target(self) -> AutomationDecisionOverrideMutation:
        if self.selected_card_id is not None and self.selected_cluster_id is not None:
            raise ValueError("an override can select either a card or a cluster, not both")
        if (
            self.selected_card_id is not None
            and self.replacement_decision_type not in _CARD_TARGET_OVERRIDE_TYPES
        ):
            raise ValueError("replacement_decision_type is incompatible with a card target")
        if (
            self.selected_cluster_id is not None
            and self.replacement_decision_type not in _CLUSTER_TARGET_OVERRIDE_TYPES
        ):
            raise ValueError("replacement_decision_type is incompatible with a cluster target")
        target_required_types = (_CARD_TARGET_OVERRIDE_TYPES | _CLUSTER_TARGET_OVERRIDE_TYPES) - {
            AutomationDecisionType.MANUAL_OVERRIDE
        }
        if (
            self.selected_card_id is None
            and self.selected_cluster_id is None
            and self.replacement_decision_type in target_required_types
        ):
            raise ValueError("replacement_decision_type requires a compatible target")
        return self


class CardAutomationSettingsRead(StrictAPIModel):
    direction_id: UUID
    direction_slug: str
    direction_title: str
    enabled: bool
    shadow_mode: bool
    auto_ignore_noise_enabled: bool
    auto_link_exact_enabled: bool
    auto_link_alias_enabled: bool
    auto_link_semantic_enabled: bool
    semantic_similarity_threshold: float = Field(ge=0, le=1)
    pairwise_judge_confidence_threshold: float = Field(ge=0, le=1)
    candidate_score_gap_threshold: float = Field(ge=0, le=1)
    cluster_match_threshold: float = Field(ge=0, le=1)
    min_distinct_interviews_for_promotion: int = Field(ge=1)
    min_distinct_companies_for_promotion: int = Field(ge=1)
    min_failed_answers_for_promotion: int = Field(ge=1)
    audit_sample_percent: float = Field(ge=0, le=100)
    personal_review_enabled: bool
    global_auto_publish_enabled: bool
    cluster_moderation_enabled: bool
    legacy_queue_enabled: bool
    version: int = Field(ge=1)
    updated_at: datetime


class CardAutomationSettingsList(StrictAPIModel):
    items: list[CardAutomationSettingsRead]


class CardAutomationSettingsUpdate(StrictAPIModel):
    direction_id: UUID
    expected_version: int = Field(ge=1)
    enabled: bool
    shadow_mode: bool
    auto_ignore_noise_enabled: bool
    auto_link_exact_enabled: bool
    auto_link_alias_enabled: bool
    auto_link_semantic_enabled: bool
    semantic_similarity_threshold: float = Field(ge=0, le=1)
    pairwise_judge_confidence_threshold: float = Field(ge=0, le=1)
    candidate_score_gap_threshold: float = Field(ge=0, le=1)
    cluster_match_threshold: float = Field(ge=0, le=1)
    min_distinct_interviews_for_promotion: int = Field(ge=1)
    min_distinct_companies_for_promotion: int = Field(ge=1)
    min_failed_answers_for_promotion: int = Field(ge=1)
    audit_sample_percent: float = Field(ge=0, le=100)
    personal_review_enabled: bool
    global_auto_publish_enabled: Literal[False]
    cluster_moderation_enabled: bool
    legacy_queue_enabled: bool

    @model_validator(mode="after")
    def preserve_a_moderation_path(self) -> CardAutomationSettingsUpdate:
        if not self.legacy_queue_enabled and not (self.enabled and self.cluster_moderation_enabled):
            raise ValueError(
                "legacy_queue_enabled can be disabled only with cluster moderation enabled"
            )
        return self


class PersonalReviewItemRead(StrictAPIModel):
    id: UUID
    direction_id: UUID
    direction_slug: str
    direction_title: str
    source_occurrence_id: UUID | None = None
    source_analysis_id: UUID | None = None
    source_analysis_url: str | None = None
    canonical_card_id: UUID | None = None
    replaced_by_card_id: UUID | None = None
    question_text: str
    answer_summary: str | None = None
    answer_contract: AnswerContract | None = None
    status: PersonalReviewStatus
    due_at: datetime
    last_reviewed_at: datetime | None = None
    successful_reviews_count: int = Field(ge=0)
    expires_at: datetime | None = None
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class PersonalReviewItemPage(StrictAPIModel):
    items: list[PersonalReviewItemRead]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class PersonalReviewItemListFilters(StrictAPIModel):
    direction_id: UUID | None = None
    statuses: list[PersonalReviewStatus] = Field(default_factory=list)
    due_only: bool = True
    due_before: datetime | None = None
    sort_order: Literal["asc", "desc"] = "asc"
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class PersonalReviewItemReviewMutation(StrictAPIModel):
    rating: InterviewReviewRating
    expected_version: int = Field(ge=1)


class PersonalReviewItemReviewResult(StrictAPIModel):
    item: PersonalReviewItemRead
    rating: InterviewReviewRating
    became_mastered: bool


class PersonalReviewItemCorrectionMutation(StrictAPIModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2_000)
    question_text: str | None = Field(default=None, min_length=1)
    answer_summary: str | None = None
    answer_contract: AnswerContract | None = None
    due_at: datetime | None = None
    status: PersonalReviewStatus | None = None

    @model_validator(mode="after")
    def require_a_change(self) -> PersonalReviewItemCorrectionMutation:
        changed_fields = self.model_fields_set - {"expected_version", "reason"}
        if not changed_fields:
            raise ValueError("at least one personal review field must be changed")
        if "question_text" in changed_fields and self.question_text is None:
            raise ValueError("question_text cannot be null")
        if "due_at" in changed_fields and self.due_at is None:
            raise ValueError("due_at cannot be null")
        return self


class PersonalReviewItemCorrectionResult(StrictAPIModel):
    item: PersonalReviewItemRead
    decision_id: UUID


class CardAutomationMetricsFilters(StrictAPIModel):
    period_from: date
    period_to: date
    direction_id: UUID | None = None

    @model_validator(mode="after")
    def validate_period(self) -> CardAutomationMetricsFilters:
        if self.period_from > self.period_to:
            raise ValueError("period_from cannot be after period_to")
        return self


class CardAutomationMetricsRead(StrictAPIModel):
    period_from: date
    period_to: date
    direction_id: UUID | None = None
    direction_slug: str | None = None
    extracted_questions_total: int = Field(ge=0)
    routed_as_noise_total: int = Field(ge=0)
    routed_as_non_flashcard_total: int = Field(ge=0)
    auto_linked_exact_total: int = Field(ge=0)
    auto_linked_alias_total: int = Field(ge=0)
    auto_linked_semantic_total: int = Field(ge=0)
    shadow_clusters_created_total: int = Field(ge=0)
    clusters_promoted_total: int = Field(ge=0)
    clusters_reviewed_total: int = Field(ge=0)
    personal_review_items_created_total: int = Field(ge=0)
    manual_tasks_per_100_interviews: float = Field(ge=0)
    average_cluster_moderation_time: float = Field(ge=0)
    oldest_moderation_task_age: float = Field(ge=0)
    automatic_decision_override_rate: float = Field(ge=0, le=1)
    false_merge_rate: float = Field(ge=0, le=1)
    noise_false_positive_rate: float = Field(ge=0, le=1)
    average_ai_cost_per_interview: Decimal = Field(ge=0)
    average_ai_cost_per_question: Decimal = Field(ge=0)
    average_ai_cost_per_promoted_cluster: Decimal = Field(ge=0)
    generated_at: datetime
