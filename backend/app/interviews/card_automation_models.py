from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.interviews.card_automation_types import (
    AnswerContractStatus,
    AutomationDecisionSource,
    AutomationDecisionType,
    AutomationReviewResult,
    LearningObjectType,
    PersonalReviewStatus,
    QuestionClusterStatus,
)


def _enum(enum_type: type, name: str) -> Enum:
    return Enum(
        enum_type,
        name=name,
        values_callable=lambda values: [item.value for item in values],
    )


class QuestionCluster(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "question_clusters"
    __table_args__ = (
        Index(
            "uq_question_clusters_direction_type_normalized_active",
            "direction_id",
            "learning_object_type",
            "normalized_canonical_question",
            unique=True,
            postgresql_where=text("status IN ('shadow', 'candidate', 'needs_review', 'deferred')"),
        ),
        CheckConstraint("occurrences_count >= 0", name="occurrences_count_non_negative"),
        CheckConstraint(
            "distinct_interviews_count >= 0", name="distinct_interviews_count_non_negative"
        ),
        CheckConstraint(
            "distinct_companies_count >= 0", name="distinct_companies_count_non_negative"
        ),
        CheckConstraint(
            "distinct_students_count >= 0", name="distinct_students_count_non_negative"
        ),
        CheckConstraint("failed_answers_count >= 0", name="failed_answers_count_non_negative"),
        CheckConstraint("priority_score >= 0", name="priority_score_non_negative"),
        CheckConstraint("quality_score >= 0 AND quality_score <= 1", name="quality_score_range"),
        CheckConstraint(
            "cluster_confidence >= 0 AND cluster_confidence <= 1",
            name="cluster_confidence_range",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("membership_revision >= 0", name="membership_revision_non_negative"),
        CheckConstraint("stats_revision >= 0", name="stats_revision_non_negative"),
        CheckConstraint("stats_revision <= membership_revision", name="stats_revision_not_ahead"),
        Index(
            "ix_question_clusters_direction_status_priority",
            "direction_id",
            "status",
            text("priority_score DESC"),
        ),
        Index("ix_question_clusters_status_last_seen", "status", "last_seen_at"),
        Index("ix_question_clusters_linked_card", "linked_card_id"),
    )

    direction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("learning_tracks.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[QuestionClusterStatus] = mapped_column(
        _enum(QuestionClusterStatus, "question_cluster_status"),
        default=QuestionClusterStatus.SHADOW,
        server_default=QuestionClusterStatus.SHADOW.value,
        nullable=False,
    )
    canonical_question: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_canonical_question: Mapped[str] = mapped_column(Text, nullable=False)
    learning_object_type: Mapped[LearningObjectType] = mapped_column(
        _enum(LearningObjectType, "learning_object_type"), nullable=False
    )
    deck_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("interview_decks.id", ondelete="SET NULL"), nullable=True
    )
    topic_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    subtopic_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    topic_candidates: Mapped[list[str]] = mapped_column(
        ARRAY(String(240)), default=list, server_default="{}", nullable=False
    )
    representative_occurrence_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("intelligence_questions.id", ondelete="SET NULL"),
        nullable=True,
    )
    linked_card_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("interview_cards.id", ondelete="SET NULL"), nullable=True
    )
    merged_into_cluster_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("question_clusters.id", ondelete="SET NULL"),
        nullable=True,
    )
    parent_cluster_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("question_clusters.id", ondelete="SET NULL"),
        nullable=True,
    )
    answer_contract: Mapped[dict[str, object] | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    answer_validation: Mapped[dict[str, object] | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    answer_status: Mapped[AnswerContractStatus | None] = mapped_column(
        _enum(AnswerContractStatus, "answer_contract_status"), nullable=True
    )
    occurrences_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    distinct_interviews_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    distinct_companies_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    distinct_students_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    failed_answers_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    priority_score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    quality_score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    cluster_confidence: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    promotion_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(ARRAY(Float), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding_source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    manual_important: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    membership_revision: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    stats_revision: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )


class AutomationDecision(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "automation_decisions"
    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="input_tokens_non_negative",
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0", name="output_tokens_non_negative"
        ),
        CheckConstraint("cost IS NULL OR cost >= 0", name="cost_non_negative"),
        CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="latency_non_negative"),
        Index("ix_automation_decisions_entity", "entity_type", "entity_id", "created_at"),
        Index("ix_automation_decisions_type_created", "decision_type", "created_at"),
        Index("ix_automation_decisions_audit", "is_audit_sample", "reviewed_at"),
        Index(
            "ix_automation_decisions_not_overridden",
            "is_overridden",
            "created_at",
            postgresql_where=text("is_overridden = false"),
        ),
    )

    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(240), unique=True, nullable=False)
    decision_type: Mapped[AutomationDecisionType] = mapped_column(
        _enum(AutomationDecisionType, "automation_decision_type"), nullable=False
    )
    decision_source: Mapped[AutomationDecisionSource] = mapped_column(
        _enum(AutomationDecisionSource, "automation_decision_source"), nullable=False
    )
    selected_card_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("interview_cards.id", ondelete="SET NULL"), nullable=True
    )
    selected_cluster_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("question_clusters.id", ondelete="SET NULL"), nullable=True
    )
    candidate_card_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    candidate_cluster_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    retrieval_scores: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    judge_result: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    model_provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    schema_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 8), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_audit_sample: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    review_result: Mapped[AutomationReviewResult | None] = mapped_column(
        _enum(AutomationReviewResult, "automation_review_result"), nullable=True
    )
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_overridden: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    overridden_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    overridden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PersonalReviewItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "personal_review_items"
    __table_args__ = (
        UniqueConstraint(
            "student_id", "source_occurrence_id", name="uq_personal_review_student_occurrence"
        ),
        CheckConstraint("successful_reviews_count >= 0", name="successful_reviews_non_negative"),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_personal_review_student_status_due", "student_id", "status", "due_at"),
        Index("ix_personal_review_due", "status", "due_at"),
    )

    student_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    direction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("learning_tracks.id", ondelete="CASCADE"), nullable=False
    )
    source_occurrence_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("intelligence_questions.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_analysis_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("intelligence_interviews.id", ondelete="SET NULL"),
        nullable=True,
    )
    canonical_card_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("interview_cards.id", ondelete="SET NULL"), nullable=True
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_contract: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[PersonalReviewStatus] = mapped_column(
        _enum(PersonalReviewStatus, "personal_review_status"),
        default=PersonalReviewStatus.ACTIVE,
        server_default=PersonalReviewStatus.ACTIVE.value,
        nullable=False,
    )
    due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    successful_reviews_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_card_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("interview_cards.id", ondelete="SET NULL"), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)


class InterviewCardDuplicateReview(UUIDPrimaryKeyMixin, Base):
    """Immutable audit entry for a reviewed pair of canonical cards."""

    __tablename__ = "interview_card_duplicate_reviews"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('merged', 'not_duplicate')",
            name="decision_supported",
        ),
        CheckConstraint("left_card_id <> right_card_id", name="different_cards"),
        CheckConstraint(
            "similarity >= 0 AND similarity <= 1",
            name="similarity_range",
        ),
        UniqueConstraint(
            "left_card_id",
            "right_card_id",
            name="uq_interview_card_duplicate_reviews_reviewed_pair",
        ),
        Index("ix_interview_card_duplicate_reviews_created", "created_at"),
    )

    left_card_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("interview_cards.id", ondelete="RESTRICT"), nullable=False
    )
    right_card_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("interview_cards.id", ondelete="RESTRICT"), nullable=False
    )
    primary_card_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("interview_cards.id", ondelete="RESTRICT"), nullable=True
    )
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    similarity: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    left_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    right_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    merge_summary: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CardAutomationSettings(TimestampMixin, Base):
    __tablename__ = "card_automation_settings"
    __table_args__ = (
        CheckConstraint(
            "semantic_similarity_threshold >= 0 AND semantic_similarity_threshold <= 1",
            name="semantic_threshold_range",
        ),
        CheckConstraint(
            "pairwise_judge_confidence_threshold >= 0 AND pairwise_judge_confidence_threshold <= 1",
            name="judge_threshold_range",
        ),
        CheckConstraint(
            "candidate_score_gap_threshold >= 0 AND candidate_score_gap_threshold <= 1",
            name="score_gap_range",
        ),
        CheckConstraint(
            "cluster_match_threshold >= 0 AND cluster_match_threshold <= 1",
            name="cluster_threshold_range",
        ),
        CheckConstraint(
            "audit_sample_percent >= 0 AND audit_sample_percent <= 100",
            name="audit_range",
        ),
        CheckConstraint(
            "min_distinct_interviews_for_promotion >= 1", name="min_interviews_positive"
        ),
        CheckConstraint("min_distinct_companies_for_promotion >= 1", name="min_companies_positive"),
        CheckConstraint("min_failed_answers_for_promotion >= 1", name="min_failures_positive"),
        CheckConstraint(
            "global_auto_publish_enabled = false",
            name="global_auto_publish_forbidden",
        ),
        CheckConstraint(
            "legacy_queue_enabled OR (enabled AND cluster_moderation_enabled)",
            name="moderation_path_required",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
    )

    direction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("learning_tracks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    shadow_mode: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    auto_ignore_noise_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    auto_link_exact_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    auto_link_alias_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    auto_link_semantic_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    semantic_similarity_threshold: Mapped[float] = mapped_column(
        Float, default=0.90, server_default="0.90"
    )
    pairwise_judge_confidence_threshold: Mapped[float] = mapped_column(
        Float, default=0.92, server_default="0.92"
    )
    candidate_score_gap_threshold: Mapped[float] = mapped_column(
        Float, default=0.08, server_default="0.08"
    )
    cluster_match_threshold: Mapped[float] = mapped_column(
        Float, default=0.86, server_default="0.86"
    )
    min_distinct_interviews_for_promotion: Mapped[int] = mapped_column(
        Integer, default=3, server_default="3"
    )
    min_distinct_companies_for_promotion: Mapped[int] = mapped_column(
        Integer, default=2, server_default="2"
    )
    min_failed_answers_for_promotion: Mapped[int] = mapped_column(
        Integer, default=2, server_default="2"
    )
    audit_sample_percent: Mapped[float] = mapped_column(Float, default=5.0, server_default="5.0")
    personal_review_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    global_auto_publish_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    cluster_moderation_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    legacy_queue_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
