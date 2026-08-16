from __future__ import annotations

from enum import StrEnum


class LearningObjectType(StrEnum):
    FLASHCARD = "flashcard"
    OPEN_TECHNICAL_QUESTION = "open_technical_question"
    CODING_TASK = "coding_task"
    SYSTEM_DESIGN_CASE = "system_design_case"
    BEHAVIORAL_QUESTION = "behavioral_question"
    ORGANIZATIONAL_QUESTION = "organizational_question"
    CONTEXT_DEPENDENT = "context_dependent"
    NOISE = "noise"


CARD_ELIGIBLE_TYPES = frozenset(
    {LearningObjectType.FLASHCARD, LearningObjectType.OPEN_TECHNICAL_QUESTION}
)


class QuestionOccurrenceStatus(StrEnum):
    CREATED = "created"
    ROUTING = "routing"
    ROUTED = "routed"
    AUTO_IGNORED = "auto_ignored"
    SEARCHING_CARD = "searching_card"
    AUTO_LINKED = "auto_linked"
    SEARCHING_CLUSTER = "searching_cluster"
    CLUSTERED = "clustered"
    NEEDS_REVIEW = "needs_review"
    PERSONAL_ONLY = "personal_only"
    FAILED = "failed"


class QuestionClusterStatus(StrEnum):
    SHADOW = "shadow"
    CANDIDATE = "candidate"
    NEEDS_REVIEW = "needs_review"
    LINKED = "linked"
    CARD_CREATED = "card_created"
    DEFERRED = "deferred"
    IGNORED = "ignored"
    SPLIT = "split"
    MERGED = "merged"


class AnswerContractStatus(StrEnum):
    GENERATED_FROM_SOURCES = "generated_from_sources"
    NEEDS_EXPERT_SOURCE = "needs_expert_source"
    NEEDS_MANUAL_REVIEW = "needs_manual_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class PersonalReviewStatus(StrEnum):
    ACTIVE = "active"
    MASTERED = "mastered"
    ARCHIVED = "archived"
    REPLACED_BY_CANONICAL_CARD = "replaced_by_canonical_card"


class AutomationDecisionType(StrEnum):
    QUESTION_ROUTED = "question_routed"
    ROUTED_AS_NOISE = "routed_as_noise"
    ROUTED_AS_NON_FLASHCARD = "routed_as_non_flashcard"
    EXACT_CARD_MATCH = "exact_card_match"
    ALIAS_CARD_MATCH = "alias_card_match"
    SEMANTIC_CARD_MATCH = "semantic_card_match"
    CLUSTER_MATCH = "cluster_match"
    SHADOW_CLUSTER_CREATED = "shadow_cluster_created"
    CLUSTER_PROMOTED = "cluster_promoted"
    PERSONAL_REVIEW_CREATED = "personal_review_created"
    PERSONAL_REVIEW_REVIEWED = "personal_review_reviewed"
    PERSONAL_REVIEW_ARCHIVED = "personal_review_archived"
    ANSWER_CONTRACT_GENERATED = "answer_contract_generated"
    ANSWER_CONTRACT_VALIDATED = "answer_contract_validated"
    ANSWER_CONTRACT_NEEDS_SOURCE = "answer_contract_needs_source"
    ANSWER_CONTRACT_FAILED = "answer_contract_failed"
    ANSWER_VALIDATION_FAILED = "answer_validation_failed"
    MANUAL_OVERRIDE = "manual_override"
    CLUSTER_LINKED = "cluster_linked"
    CARD_CREATED = "card_created"
    CLUSTER_SPLIT = "cluster_split"
    CLUSTER_MERGED = "cluster_merged"
    CLUSTER_IGNORED = "cluster_ignored"
    CLUSTER_DEFERRED = "cluster_deferred"
    CLUSTER_REOPENED = "cluster_reopened"
    CLUSTER_MARKED_IMPORTANT = "cluster_marked_important"
    OCCURRENCE_REPROCESSED = "occurrence_reprocessed"
    OCCURRENCE_FAILED = "occurrence_failed"


class AutomationDecisionSource(StrEnum):
    RULE = "rule"
    AI_ROUTING = "ai_routing"
    EXACT = "exact"
    CONFIRMED_ALIAS = "confirmed_alias"
    SEMANTIC_JUDGE = "semantic_judge"
    CLUSTERING = "clustering"
    HUMAN = "human"
    BACKFILL = "backfill"


class AutomationReviewResult(StrEnum):
    CORRECT = "correct"
    MERGE_ERROR = "merge_error"
    CLASSIFICATION_ERROR = "classification_error"
    WRONG_OBJECT_TYPE = "wrong_object_type"
    WRONG_TOPIC = "wrong_topic"
    OTHER = "other"


class PairwiseCardMatchDecision(StrEnum):
    SAME_CARD = "same_card"
    RELATED_DIFFERENT_SCOPE = "related_different_scope"
    NOT_RELATED = "not_related"
    UNCERTAIN = "uncertain"


CRITICAL_QUALITY_FLAGS = frozenset(
    {
        "bad_transcription",
        "missing_context",
        "depends_on_code",
        "depends_on_diagram",
        "depends_on_previous_answer",
        "candidate_question_not_interviewer_question",
        "contains_personal_data",
    }
)

ALLOWED_QUALITY_FLAGS = frozenset(
    {
        *CRITICAL_QUALITY_FLAGS,
        "too_broad",
        "too_narrow",
        "rhetorical",
        "duplicate_inside_interview",
        "version_sensitive",
    }
)
