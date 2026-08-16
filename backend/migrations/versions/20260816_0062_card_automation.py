"""Add safe card automation, semantic clusters and personal review items.

Revision ID: 20260816_0062
Revises: 20260815_0061
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260816_0062"
down_revision: str | None = "20260815_0061"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


LEARNING_OBJECT_TYPES = (
    "flashcard",
    "open_technical_question",
    "coding_task",
    "system_design_case",
    "behavioral_question",
    "organizational_question",
    "context_dependent",
    "noise",
)
OCCURRENCE_STATUSES = (
    "created",
    "routing",
    "routed",
    "auto_ignored",
    "searching_card",
    "auto_linked",
    "searching_cluster",
    "clustered",
    "needs_review",
    "personal_only",
    "failed",
)
CLUSTER_STATUSES = (
    "shadow",
    "candidate",
    "needs_review",
    "linked",
    "card_created",
    "deferred",
    "ignored",
    "split",
    "merged",
)
ANSWER_STATUSES = (
    "generated_from_sources",
    "needs_expert_source",
    "needs_manual_review",
    "approved",
    "rejected",
)
PERSONAL_STATUSES = ("active", "mastered", "archived", "replaced_by_canonical_card")
DECISION_TYPES = (
    "question_routed",
    "routed_as_noise",
    "routed_as_non_flashcard",
    "exact_card_match",
    "alias_card_match",
    "semantic_card_match",
    "cluster_match",
    "shadow_cluster_created",
    "cluster_promoted",
    "personal_review_created",
    "personal_review_reviewed",
    "personal_review_archived",
    "answer_contract_generated",
    "answer_contract_validated",
    "answer_contract_needs_source",
    "answer_contract_failed",
    "answer_validation_failed",
    "manual_override",
    "cluster_linked",
    "card_created",
    "cluster_split",
    "cluster_merged",
    "cluster_ignored",
    "cluster_deferred",
    "cluster_reopened",
    "cluster_marked_important",
    "occurrence_reprocessed",
    "occurrence_failed",
)
DECISION_SOURCES = (
    "rule",
    "ai_routing",
    "exact",
    "confirmed_alias",
    "semantic_judge",
    "clustering",
    "human",
    "backfill",
)
REVIEW_RESULTS = (
    "correct",
    "merge_error",
    "classification_error",
    "wrong_object_type",
    "wrong_topic",
    "other",
)


def _pg_enum(name: str, values: tuple[str, ...]) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    enum_specs = (
        ("learning_object_type", LEARNING_OBJECT_TYPES),
        ("question_occurrence_status", OCCURRENCE_STATUSES),
        ("question_cluster_status", CLUSTER_STATUSES),
        ("answer_contract_status", ANSWER_STATUSES),
        ("personal_review_status", PERSONAL_STATUSES),
        ("automation_decision_type", DECISION_TYPES),
        ("automation_decision_source", DECISION_SOURCES),
        ("automation_review_result", REVIEW_RESULTS),
    )
    for name, values in enum_specs:
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    op.add_column("intelligence_questions", sa.Column("direction_id", sa.UUID(), nullable=True))
    op.add_column(
        "intelligence_questions", sa.Column("normalized_question_text", sa.Text(), nullable=True)
    )
    op.add_column(
        "intelligence_questions",
        sa.Column("canonical_question_candidate", sa.Text(), nullable=True),
    )
    op.add_column("intelligence_questions", sa.Column("source_context", sa.Text(), nullable=True))
    op.add_column(
        "intelligence_questions",
        sa.Column(
            "learning_object_type",
            _pg_enum("learning_object_type", LEARNING_OBJECT_TYPES),
            nullable=True,
        ),
    )
    op.add_column(
        "intelligence_questions",
        sa.Column("is_real_interviewer_question", sa.Boolean(), nullable=True),
    )
    op.add_column("intelligence_questions", sa.Column("is_standalone", sa.Boolean()))
    op.add_column("intelligence_questions", sa.Column("routing_confidence", sa.Float()))
    op.add_column(
        "intelligence_questions",
        sa.Column(
            "answer_scope",
            postgresql.ARRAY(sa.String(length=240)),
            server_default="{}",
            nullable=False,
        ),
    )
    op.add_column(
        "intelligence_questions",
        sa.Column(
            "topic_candidates",
            postgresql.ARRAY(sa.String(length=240)),
            server_default="{}",
            nullable=False,
        ),
    )
    op.add_column(
        "intelligence_questions",
        sa.Column(
            "quality_flags",
            postgresql.ARRAY(sa.String(length=80)),
            server_default="{}",
            nullable=False,
        ),
    )
    op.add_column(
        "intelligence_questions",
        sa.Column(
            "automation_status",
            _pg_enum("question_occurrence_status", OCCURRENCE_STATUSES),
            server_default="created",
            nullable=False,
        ),
    )
    op.add_column(
        "intelligence_questions",
        sa.Column(
            "automation_decision_source",
            _pg_enum("automation_decision_source", DECISION_SOURCES),
        ),
    )
    op.add_column("intelligence_questions", sa.Column("automation_decision_reason", sa.Text()))
    op.add_column("intelligence_questions", sa.Column("automation_error", sa.String(500)))
    op.add_column("intelligence_questions", sa.Column("processed_at", sa.DateTime(timezone=True)))
    op.add_column(
        "intelligence_questions",
        sa.Column("automation_revision", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "intelligence_questions",
        sa.Column("automation_attempts", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "intelligence_questions",
        sa.Column("alias_human_confirmed", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_foreign_key(
        "fk_intelligence_questions_direction_id_learning_tracks",
        "intelligence_questions",
        "learning_tracks",
        ["direction_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_intelligence_questions_routing_confidence_range",
        "intelligence_questions",
        "routing_confidence IS NULL OR (routing_confidence >= 0 AND routing_confidence <= 1)",
    )
    op.create_check_constraint(
        "ck_intelligence_questions_automation_revision_positive",
        "intelligence_questions",
        "automation_revision >= 1",
    )
    op.create_check_constraint(
        "ck_intelligence_questions_automation_attempts_non_negative",
        "intelligence_questions",
        "automation_attempts >= 0",
    )

    # This is deliberately only a cheap deterministic data migration. The
    # separate backfill CLI recomputes application-level normalization and all
    # semantic fields in small resumable batches.
    op.execute(
        """
        UPDATE intelligence_questions AS question
        SET direction_id = process.track_id,
            normalized_question_text = replace(
                lower(
                    trim(
                        both ' ?!.,;:' from regexp_replace(
                            question.question_text,
                            '\\s+',
                            ' ',
                            'g'
                        )
                    )
                ),
                'ё',
                'е'
            ),
            learning_object_type = CASE question.question_kind::text
                WHEN 'technical' THEN 'open_technical_question'::learning_object_type
                WHEN 'hr' THEN 'behavioral_question'::learning_object_type
                WHEN 'organizational' THEN 'organizational_question'::learning_object_type
                ELSE 'context_dependent'::learning_object_type
            END,
            is_real_interviewer_question = true,
            is_standalone = true,
            automation_status = CASE
                WHEN question.published_card_id IS NOT NULL
                    THEN 'auto_linked'::question_occurrence_status
                WHEN question.moderation_status::text = 'rejected'
                    THEN 'auto_ignored'::question_occurrence_status
                ELSE 'created'::question_occurrence_status
            END,
            automation_decision_source = CASE
                WHEN question.moderation_status::text IN ('approved', 'rejected')
                    THEN 'human'::automation_decision_source
                ELSE NULL
            END,
            processed_at = CASE
                WHEN question.moderation_status::text IN ('approved', 'rejected')
                    THEN COALESCE(question.admin_reviewed_at, question.updated_at)
                ELSE NULL
            END,
            alias_human_confirmed = CASE
                WHEN question.moderation_status::text = 'approved'
                  AND question.published_card_id IS NOT NULL
                    THEN true
                ELSE false
            END
        FROM intelligence_interviews AS analysis
        JOIN interview_process_stages AS stage ON stage.id = analysis.stage_id
        JOIN interview_processes AS process ON process.id = stage.process_id
        WHERE question.interview_id = analysis.id
        """
    )
    op.alter_column("intelligence_questions", "direction_id", nullable=False)
    op.alter_column("intelligence_questions", "normalized_question_text", nullable=False)
    op.alter_column("intelligence_questions", "learning_object_type", nullable=False)

    op.create_table(
        "question_clusters",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("direction_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            _pg_enum("question_cluster_status", CLUSTER_STATUSES),
            server_default="shadow",
            nullable=False,
        ),
        sa.Column("canonical_question", sa.Text(), nullable=False),
        sa.Column("normalized_canonical_question", sa.Text(), nullable=False),
        sa.Column(
            "learning_object_type",
            _pg_enum("learning_object_type", LEARNING_OBJECT_TYPES),
            nullable=False,
        ),
        sa.Column("deck_id", sa.UUID()),
        sa.Column("topic_name", sa.String(240)),
        sa.Column(
            "topic_candidates",
            postgresql.ARRAY(sa.String(length=240)),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("representative_occurrence_id", sa.UUID()),
        sa.Column("linked_card_id", sa.UUID()),
        sa.Column("merged_into_cluster_id", sa.UUID()),
        sa.Column("parent_cluster_id", sa.UUID()),
        sa.Column("answer_contract", postgresql.JSONB()),
        sa.Column("answer_validation", postgresql.JSONB()),
        sa.Column("answer_status", _pg_enum("answer_contract_status", ANSWER_STATUSES)),
        sa.Column("occurrences_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("distinct_interviews_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("distinct_companies_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("distinct_students_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_answers_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("priority_score", sa.Float(), server_default="0", nullable=False),
        sa.Column("quality_score", sa.Float(), server_default="0", nullable=False),
        sa.Column("cluster_confidence", sa.Float(), server_default="0", nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("promoted_at", sa.DateTime(timezone=True)),
        sa.Column("promotion_reason", sa.String(500)),
        sa.Column("embedding", postgresql.ARRAY(sa.Float())),
        sa.Column("embedding_model", sa.String(120)),
        sa.Column("embedding_dimensions", sa.Integer()),
        sa.Column("embedding_source_hash", sa.String(64)),
        sa.Column("manual_important", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("membership_revision", sa.Integer(), server_default="0", nullable=False),
        sa.Column("stats_revision", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("occurrences_count >= 0", name="occurrences_count_non_negative"),
        sa.CheckConstraint(
            "distinct_interviews_count >= 0", name="distinct_interviews_count_non_negative"
        ),
        sa.CheckConstraint(
            "distinct_companies_count >= 0", name="distinct_companies_count_non_negative"
        ),
        sa.CheckConstraint(
            "distinct_students_count >= 0", name="distinct_students_count_non_negative"
        ),
        sa.CheckConstraint("failed_answers_count >= 0", name="failed_answers_count_non_negative"),
        sa.CheckConstraint("priority_score >= 0", name="priority_score_non_negative"),
        sa.CheckConstraint("quality_score >= 0 AND quality_score <= 1", name="quality_score_range"),
        sa.CheckConstraint(
            "cluster_confidence >= 0 AND cluster_confidence <= 1",
            name="cluster_confidence_range",
        ),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.CheckConstraint("membership_revision >= 0", name="membership_revision_non_negative"),
        sa.CheckConstraint("stats_revision >= 0", name="stats_revision_non_negative"),
        sa.CheckConstraint(
            "stats_revision <= membership_revision", name="stats_revision_not_ahead"
        ),
        sa.ForeignKeyConstraint(["direction_id"], ["learning_tracks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["deck_id"], ["interview_decks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["representative_occurrence_id"], ["intelligence_questions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["linked_card_id"], ["interview_cards.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["merged_into_cluster_id"], ["question_clusters.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["parent_cluster_id"], ["question_clusters.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_question_clusters_direction_type_normalized_active",
        "question_clusters",
        ["direction_id", "learning_object_type", "normalized_canonical_question"],
        unique=True,
        postgresql_where=sa.text("status IN ('shadow', 'candidate', 'needs_review', 'deferred')"),
    )
    op.create_index(
        "ix_question_clusters_direction_status_priority",
        "question_clusters",
        ["direction_id", "status", sa.text("priority_score DESC")],
    )
    op.create_index(
        "ix_question_clusters_status_last_seen", "question_clusters", ["status", "last_seen_at"]
    )
    op.create_index("ix_question_clusters_linked_card", "question_clusters", ["linked_card_id"])
    op.add_column("intelligence_questions", sa.Column("cluster_id", sa.UUID()))
    op.create_foreign_key(
        "fk_intelligence_questions_cluster_id_question_clusters",
        "intelligence_questions",
        "question_clusters",
        ["cluster_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_intelligence_questions_direction_status",
        "intelligence_questions",
        ["direction_id", "automation_status"],
    )
    op.create_index(
        "ix_intelligence_questions_direction_created",
        "intelligence_questions",
        ["direction_id", "created_at"],
    )
    op.create_index("ix_intelligence_questions_cluster", "intelligence_questions", ["cluster_id"])

    op.create_table(
        "automation_decisions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("entity_type", sa.String(60), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("idempotency_key", sa.String(240), nullable=False),
        sa.Column(
            "decision_type", _pg_enum("automation_decision_type", DECISION_TYPES), nullable=False
        ),
        sa.Column(
            "decision_source",
            _pg_enum("automation_decision_source", DECISION_SOURCES),
            nullable=False,
        ),
        sa.Column("selected_card_id", sa.UUID()),
        sa.Column("selected_cluster_id", sa.UUID()),
        sa.Column("candidate_card_ids", postgresql.JSONB(), nullable=False),
        sa.Column("candidate_cluster_ids", postgresql.JSONB(), nullable=False),
        sa.Column("retrieval_scores", postgresql.JSONB(), nullable=False),
        sa.Column("judge_result", postgresql.JSONB()),
        sa.Column("confidence", sa.Float()),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("model_provider", sa.String(80)),
        sa.Column("model_name", sa.String(160)),
        sa.Column("prompt_version", sa.String(100)),
        sa.Column("schema_version", sa.String(100)),
        sa.Column("input_hash", sa.String(64)),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("cost", sa.Numeric(14, 8)),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("is_audit_sample", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("review_result", _pg_enum("automation_review_result", REVIEW_RESULTS)),
        sa.Column("reviewed_by_user_id", sa.UUID()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("review_reason", sa.Text()),
        sa.Column("is_overridden", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("overridden_by_user_id", sa.UUID()),
        sa.Column("override_reason", sa.Text()),
        sa.Column("overridden_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
        sa.CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0", name="input_tokens_non_negative"
        ),
        sa.CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0", name="output_tokens_non_negative"
        ),
        sa.CheckConstraint("cost IS NULL OR cost >= 0", name="cost_non_negative"),
        sa.CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="latency_non_negative"),
        sa.ForeignKeyConstraint(["selected_card_id"], ["interview_cards.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["selected_cluster_id"], ["question_clusters.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["overridden_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        "ix_automation_decisions_entity",
        "automation_decisions",
        ["entity_type", "entity_id", "created_at"],
    )
    op.create_index(
        "ix_automation_decisions_type_created",
        "automation_decisions",
        ["decision_type", "created_at"],
    )
    op.create_index(
        "ix_automation_decisions_audit",
        "automation_decisions",
        ["is_audit_sample", "reviewed_at"],
    )
    op.create_index(
        "ix_automation_decisions_not_overridden",
        "automation_decisions",
        ["is_overridden", "created_at"],
        postgresql_where=sa.text("is_overridden = false"),
    )
    op.create_index("ix_automation_decisions_input_hash", "automation_decisions", ["input_hash"])

    op.create_table(
        "personal_review_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("direction_id", sa.UUID(), nullable=False),
        sa.Column("source_occurrence_id", sa.UUID()),
        sa.Column("source_analysis_id", sa.UUID()),
        sa.Column("canonical_card_id", sa.UUID()),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("answer_summary", sa.Text()),
        sa.Column("answer_contract", postgresql.JSONB()),
        sa.Column(
            "status",
            _pg_enum("personal_review_status", PERSONAL_STATUSES),
            server_default="active",
            nullable=False,
        ),
        sa.Column(
            "due_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("successful_reviews_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("replaced_by_card_id", sa.UUID()),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("successful_reviews_count >= 0", name="successful_reviews_non_negative"),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["direction_id"], ["learning_tracks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_occurrence_id"], ["intelligence_questions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["source_analysis_id"], ["intelligence_interviews.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["canonical_card_id"], ["interview_cards.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["replaced_by_card_id"], ["interview_cards.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "student_id", "source_occurrence_id", name="uq_personal_review_student_occurrence"
        ),
    )
    op.create_index(
        "ix_personal_review_student_status_due",
        "personal_review_items",
        ["student_id", "status", "due_at"],
    )
    op.create_index("ix_personal_review_due", "personal_review_items", ["status", "due_at"])

    op.create_table(
        "card_automation_settings",
        sa.Column("direction_id", sa.UUID(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("shadow_mode", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "auto_ignore_noise_enabled", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column(
            "auto_link_exact_enabled", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column(
            "auto_link_alias_enabled", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column(
            "auto_link_semantic_enabled", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column(
            "semantic_similarity_threshold", sa.Float(), server_default="0.90", nullable=False
        ),
        sa.Column(
            "pairwise_judge_confidence_threshold", sa.Float(), server_default="0.92", nullable=False
        ),
        sa.Column(
            "candidate_score_gap_threshold", sa.Float(), server_default="0.08", nullable=False
        ),
        sa.Column("cluster_match_threshold", sa.Float(), server_default="0.86", nullable=False),
        sa.Column(
            "min_distinct_interviews_for_promotion",
            sa.Integer(),
            server_default="3",
            nullable=False,
        ),
        sa.Column(
            "min_distinct_companies_for_promotion", sa.Integer(), server_default="2", nullable=False
        ),
        sa.Column(
            "min_failed_answers_for_promotion", sa.Integer(), server_default="2", nullable=False
        ),
        sa.Column("audit_sample_percent", sa.Float(), server_default="5.0", nullable=False),
        sa.Column(
            "personal_review_enabled", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column(
            "global_auto_publish_enabled", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column(
            "cluster_moderation_enabled", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("legacy_queue_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "semantic_similarity_threshold >= 0 AND semantic_similarity_threshold <= 1",
            name="semantic_threshold_range",
        ),
        sa.CheckConstraint(
            "pairwise_judge_confidence_threshold >= 0 AND pairwise_judge_confidence_threshold <= 1",
            name="judge_threshold_range",
        ),
        sa.CheckConstraint(
            "candidate_score_gap_threshold >= 0 AND candidate_score_gap_threshold <= 1",
            name="score_gap_range",
        ),
        sa.CheckConstraint(
            "cluster_match_threshold >= 0 AND cluster_match_threshold <= 1",
            name="cluster_threshold_range",
        ),
        sa.CheckConstraint(
            "audit_sample_percent >= 0 AND audit_sample_percent <= 100", name="audit_range"
        ),
        sa.CheckConstraint(
            "min_distinct_interviews_for_promotion >= 1", name="min_interviews_positive"
        ),
        sa.CheckConstraint(
            "min_distinct_companies_for_promotion >= 1", name="min_companies_positive"
        ),
        sa.CheckConstraint("min_failed_answers_for_promotion >= 1", name="min_failures_positive"),
        sa.CheckConstraint(
            "global_auto_publish_enabled = false", name="global_auto_publish_forbidden"
        ),
        sa.CheckConstraint(
            "legacy_queue_enabled OR (enabled AND cluster_moderation_enabled)",
            name="moderation_path_required",
        ),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.ForeignKeyConstraint(["direction_id"], ["learning_tracks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("direction_id"),
    )
    op.execute(
        """
        INSERT INTO card_automation_settings (direction_id)
        SELECT id FROM learning_tracks
        ON CONFLICT (direction_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("card_automation_settings")
    op.drop_index("ix_personal_review_due", table_name="personal_review_items")
    op.drop_index("ix_personal_review_student_status_due", table_name="personal_review_items")
    op.drop_table("personal_review_items")
    op.drop_index("ix_automation_decisions_input_hash", table_name="automation_decisions")
    op.drop_index("ix_automation_decisions_not_overridden", table_name="automation_decisions")
    op.drop_index("ix_automation_decisions_audit", table_name="automation_decisions")
    op.drop_index("ix_automation_decisions_type_created", table_name="automation_decisions")
    op.drop_index("ix_automation_decisions_entity", table_name="automation_decisions")
    op.drop_table("automation_decisions")
    op.drop_index("ix_intelligence_questions_cluster", table_name="intelligence_questions")
    op.drop_index(
        "ix_intelligence_questions_direction_created",
        table_name="intelligence_questions",
    )
    op.drop_index("ix_intelligence_questions_direction_status", table_name="intelligence_questions")
    op.drop_constraint(
        "fk_intelligence_questions_cluster_id_question_clusters",
        "intelligence_questions",
        type_="foreignkey",
    )
    op.drop_column("intelligence_questions", "cluster_id")
    op.drop_index("ix_question_clusters_linked_card", table_name="question_clusters")
    op.drop_index("ix_question_clusters_status_last_seen", table_name="question_clusters")
    op.drop_index("ix_question_clusters_direction_status_priority", table_name="question_clusters")
    op.drop_index(
        "uq_question_clusters_direction_type_normalized_active",
        table_name="question_clusters",
    )
    op.drop_table("question_clusters")

    op.drop_constraint(
        "ck_intelligence_questions_routing_confidence_range",
        "intelligence_questions",
        type_="check",
    )
    op.drop_constraint(
        "ck_intelligence_questions_automation_revision_positive",
        "intelligence_questions",
        type_="check",
    )
    op.drop_constraint(
        "ck_intelligence_questions_automation_attempts_non_negative",
        "intelligence_questions",
        type_="check",
    )
    op.drop_constraint(
        "fk_intelligence_questions_direction_id_learning_tracks",
        "intelligence_questions",
        type_="foreignkey",
    )
    for column in (
        "alias_human_confirmed",
        "automation_attempts",
        "automation_revision",
        "processed_at",
        "automation_error",
        "automation_decision_reason",
        "automation_decision_source",
        "automation_status",
        "quality_flags",
        "topic_candidates",
        "answer_scope",
        "routing_confidence",
        "is_standalone",
        "is_real_interviewer_question",
        "learning_object_type",
        "source_context",
        "canonical_question_candidate",
        "normalized_question_text",
        "direction_id",
    ):
        op.drop_column("intelligence_questions", column)

    bind = op.get_bind()
    for name in (
        "automation_review_result",
        "automation_decision_source",
        "automation_decision_type",
        "personal_review_status",
        "answer_contract_status",
        "question_cluster_status",
        "question_occurrence_status",
        "learning_object_type",
    ):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
