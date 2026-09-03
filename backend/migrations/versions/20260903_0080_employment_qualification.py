"""Extend employment with actual-work profile qualification.

Revision ID: 20260903_0080
Revises: 20260903_0079
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260903_0080"
down_revision: str | None = "20260903_0079"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.execute("ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'employment'")
    enums = {
        "activity": _enum(
            "employment_activity_type",
            "employment_contract",
            "civil_contract",
            "self_employed",
            "individual_entrepreneur",
            "foreign_contract",
            "controlled_legal_entity",
            "internal_transfer",
            "actual_admission",
            "other",
        ),
        "case": _enum(
            "employment_case_status",
            "reported",
            "awaiting_initial_documents",
            "awaiting_actual_duties",
            "awaiting_staff_review",
            "monitoring_non_profile",
            "profile_confirmed",
            "non_profile_confirmed",
            "disputed",
            "ended",
            "closed",
        ),
        "direction": _enum("employment_direction", "python", "go"),
        "event": _enum(
            "employment_event_type",
            "offer_received",
            "offer_accepted",
            "contract_signed",
            "employment_started",
            "actual_duties_requested",
            "actual_duties_reported",
            "project_assigned",
            "stack_confirmed",
            "job_title_changed",
            "team_changed",
            "project_changed",
            "duties_changed",
            "profile_activity_started",
            "profile_activity_confirmed",
            "profile_activity_ended",
            "employment_ended",
            "assessment_changed",
            "dispute_opened",
            "dispute_resolved",
        ),
        "source": _enum("employment_event_source", "student", "staff", "system"),
        "usage": _enum(
            "employment_technology_usage_type",
            "coding",
            "refactoring",
            "testing",
            "code_review",
            "architecture",
            "maintenance",
            "operations",
            "automation",
            "data_processing",
            "technical_leadership",
            "other",
        ),
        "frequency": _enum(
            "employment_technology_frequency", "one_time", "occasional", "regular", "primary"
        ),
        "tri": _enum("employment_tri_state", "yes", "no", "unknown"),
        "classification": _enum(
            "employment_profile_classification",
            "profile",
            "mixed_profile",
            "non_profile",
            "insufficient_data",
            "disputed",
        ),
        "window": _enum(
            "employment_window_classification",
            "within_main_period",
            "within_control_period",
            "within_specific_process_extension",
            "outside_billable_window",
            "insufficient_data",
        ),
        "evidence_type": _enum(
            "employment_evidence_type",
            "vacancy",
            "offer",
            "contract_excerpt",
            "job_description",
            "employer_message",
            "manager_message",
            "project_assignment",
            "role_change",
            "payslip",
            "status_report",
            "student_statement",
            "public_profile_snapshot",
            "public_post",
            "meeting_note",
            "other",
        ),
        "evidence_status": _enum(
            "employment_evidence_verification_status", "unverified", "verified", "rejected"
        ),
        "followup_type": _enum(
            "employment_followup_type",
            "actual_duties",
            "monthly_change_check",
            "additional_information",
        ),
        "followup_status": _enum("employment_followup_status", "open", "answered", "cancelled"),
        "dispute": _enum(
            "employment_dispute_status", "open", "under_review", "resolved", "rejected"
        ),
        "billing": _enum(
            "employment_billing_event_status",
            "awaiting_compensation",
            "processed",
            "hold",
            "not_applicable",
        ),
        "ai_suggestion": _enum(
            "employment_ai_suggestion_status", "queued", "running", "completed", "failed"
        ),
    }
    bind = op.get_bind()
    for enum in enums.values():
        enum.create(bind, checkfirst=True)

    op.create_table(
        "employment_contract_policy_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("track_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_code", sa.String(100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("direction", enums["direction"], nullable=False),
        sa.Column("direction_language", sa.String(32), nullable=False),
        sa.Column("control_period_started_at", sa.Date(), nullable=False),
        sa.Column("control_period_ended_at", sa.Date(), nullable=False),
        sa.Column("extension_ended_at", sa.Date(), nullable=True),
        sa.Column("rules", postgresql.JSONB(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_legacy", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "version > 0", name=op.f("ck_employment_contract_policy_snapshots_version_positive")
        ),
        sa.CheckConstraint(
            "control_period_ended_at >= control_period_started_at",
            name=op.f("ck_employment_contract_policy_snapshots_control_period_ordered"),
        ),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["track_id"], ["learning_tracks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "student_id",
            "track_id",
            "policy_code",
            "version",
            name="uq_employment_policy_student_track_version",
        ),
    )
    op.create_index(
        "ix_employment_policy_student_track",
        "employment_contract_policy_snapshots",
        ["student_id", "track_id", "accepted_at"],
    )

    op.drop_constraint(
        op.f("ck_student_employments_net_salary_positive"),
        "student_employments",
        type_="check",
    )
    op.alter_column("student_employments", "start_date", existing_type=sa.Date(), nullable=True)
    op.alter_column(
        "student_employments", "net_salary_kopecks", existing_type=sa.BigInteger(), nullable=True
    )
    op.create_check_constraint(
        "net_salary_positive",
        "student_employments",
        "net_salary_kopecks IS NULL OR net_salary_kopecks > 0",
    )
    columns = [
        sa.Column("track_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("contract_policy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expected_start_date", sa.Date(), nullable=True),
        sa.Column("official_job_title", sa.String(240), nullable=True),
        sa.Column("vacancy_title", sa.String(240), nullable=True),
        sa.Column("activity_type", enums["activity"], nullable=True),
        sa.Column("offer_received_at", sa.Date(), nullable=True),
        sa.Column("offer_accepted_at", sa.Date(), nullable=True),
        sa.Column("contract_signed_at", sa.Date(), nullable=True),
        sa.Column("vacancy_duties", sa.Text(), nullable=True),
        sa.Column("initial_vacancy_stack", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("offer_stack", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("actual_stack", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("actual_duties", sa.Text(), nullable=True),
        sa.Column("project_description", sa.Text(), nullable=True),
        sa.Column("team_description", sa.Text(), nullable=True),
        sa.Column("student_comment", sa.Text(), nullable=True),
        sa.Column("differences_description", sa.Text(), nullable=True),
        sa.Column("case_status", enums["case"], nullable=True),
        sa.Column("profile_activity_started_at", sa.Date(), nullable=True),
        sa.Column("profile_activity_ended_at", sa.Date(), nullable=True),
        sa.Column("billing_started_at", sa.Date(), nullable=True),
        sa.Column("billing_on_hold", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("monitoring_due_at", sa.Date(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lock_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("legacy_policy_snapshot", postgresql.JSONB(), nullable=True),
    ]
    for column in columns:
        op.add_column("student_employments", column)
    op.create_foreign_key(
        "fk_student_employments_track_id_learning_tracks",
        "student_employments",
        "learning_tracks",
        ["track_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_student_employments_contract_policy_id_employment_policy",
        "student_employments",
        "employment_contract_policy_snapshots",
        ["contract_policy_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_student_employments_case_status", "student_employments", ["case_status", "updated_at"]
    )
    op.create_index(
        "ix_student_employments_student_track",
        "student_employments",
        ["student_id", "track_id", "created_at"],
    )
    op.create_index(
        "ix_student_employments_profile_started",
        "student_employments",
        ["profile_activity_started_at"],
    )
    op.create_index(
        "ix_student_employments_monitoring",
        "student_employments",
        ["monitoring_due_at", "case_status"],
    )
    op.execute(
        """
        UPDATE student_employments
        SET billing_started_at = start_date,
            legacy_policy_snapshot = jsonb_build_object(
                'policy_code', 'legacy-payment-v1',
                'profile_qualification_enabled', false,
                'migration_note', 'Existing billing schedule retained without requalification'
            )
        """
    )

    op.create_table(
        "employment_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", enums["event"], nullable=False),
        sa.Column("effective_at", sa.Date(), nullable=False),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", enums["source"], nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_ids", postgresql.JSONB(), nullable=False),
        sa.Column("correlation_id", sa.String(100), nullable=True),
        sa.Column("idempotency_key", sa.String(180), nullable=False),
        sa.ForeignKeyConstraint(["employment_id"], ["student_employments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_employment_events_idempotency"),
    )
    op.create_index(
        "ix_employment_events_case_effective",
        "employment_events",
        ["employment_id", "effective_at"],
    )

    op.create_table(
        "employment_technology_usages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("normalized_name", sa.String(100), nullable=False),
        sa.Column("usage_type", enums["usage"], nullable=False),
        sa.Column("frequency", enums["frequency"], nullable=False),
        sa.Column("part_of_official_duties", enums["tri"], nullable=False),
        sa.Column("part_of_project", enums["tri"], nullable=False),
        sa.Column("started_at", sa.Date(), nullable=True),
        sa.Column("ended_at", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("confirmed_by_student", sa.Boolean(), nullable=False),
        sa.Column("confirmed_by_staff", sa.Boolean(), nullable=False),
        sa.Column("evidence_ids", postgresql.JSONB(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["employment_id"], ["student_employments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_employment_technology_case_name",
        "employment_technology_usages",
        ["employment_id", "normalized_name"],
    )

    op.create_table(
        "employment_profile_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("track_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("direction", enums["direction"], nullable=False),
        sa.Column("direction_language", sa.String(32), nullable=False),
        sa.Column("classification", enums["classification"], nullable=False),
        sa.Column("effective_profile_started_at", sa.Date(), nullable=True),
        sa.Column("effective_profile_ended_at", sa.Date(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("qualifying_criteria", postgresql.JSONB(), nullable=False),
        sa.Column("non_qualifying_reasons", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_ids", postgresql.JSONB(), nullable=False),
        sa.Column("ai_suggestion", postgresql.JSONB(), nullable=True),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("supersedes_assessment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(180), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["employment_id"], ["student_employments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["policy_snapshot_id"], ["employment_contract_policy_snapshots.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["track_id"], ["learning_tracks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["supersedes_assessment_id"], ["employment_profile_assessments.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_employment_assessments_idempotency"),
    )
    op.create_index(
        "ix_employment_assessments_pending",
        "employment_profile_assessments",
        ["employment_id", "reviewed_at"],
    )
    op.create_index(
        "ix_employment_assessments_classification",
        "employment_profile_assessments",
        ["classification", "created_at"],
    )
    op.add_column(
        "student_employments",
        sa.Column("current_assessment_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_student_employments_current_assessment",
        "student_employments",
        "employment_profile_assessments",
        ["current_assessment_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "employment_qualification_windows",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("control_period_started_at", sa.Date(), nullable=True),
        sa.Column("control_period_ended_at", sa.Date(), nullable=True),
        sa.Column("extension_ended_at", sa.Date(), nullable=True),
        sa.Column("classification", enums["window"], nullable=False),
        sa.Column("linked_offer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("linked_interview_process_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("evaluation_reason", sa.Text(), nullable=False),
        sa.Column("billing_trigger_allowed", sa.Boolean(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("policy_version", sa.String(100), nullable=False),
        sa.ForeignKeyConstraint(
            ["assessment_id"], ["employment_profile_assessments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["policy_snapshot_id"], ["employment_contract_policy_snapshots.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["linked_interview_process_id"], ["interview_processes.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assessment_id", name="uq_employment_windows_assessment"),
    )
    op.create_index(
        "ix_employment_windows_classification",
        "employment_qualification_windows",
        ["classification", "evaluated_at"],
    )

    op.create_table(
        "employment_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_type", enums["evidence_type"], nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=True),
        sa.Column("filename", sa.String(500), nullable=True),
        sa.Column("content_type", sa.String(160), nullable=True),
        sa.Column("size", sa.BigInteger(), nullable=True),
        sa.Column("checksum_sha256", sa.String(64), nullable=True),
        sa.Column("text_extract", sa.Text(), nullable=True),
        sa.Column("source_url", sa.String(1000), nullable=True),
        sa.Column("source_date", sa.Date(), nullable=True),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("access_scope", sa.String(32), nullable=False),
        sa.Column("redaction_metadata", postgresql.JSONB(), nullable=False),
        sa.Column("verification_status", enums["evidence_status"], nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["employment_id"], ["student_employments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key", name="uq_employment_evidence_storage_key"),
    )
    op.create_index(
        "ix_employment_evidence_case_created",
        "employment_evidence",
        ["employment_id", "created_at"],
    )

    op.create_table(
        "employment_followups",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("followup_type", enums["followup_type"], nullable=False),
        sa.Column("status", enums["followup_status"], nullable=False),
        sa.Column("due_at", sa.Date(), nullable=False),
        sa.Column("requested_fields", postgresql.JSONB(), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(180), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["employment_id"], ["student_employments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_employment_followups_idempotency"),
    )
    op.create_index(
        "ix_employment_followups_due_status", "employment_followups", ["due_at", "status"]
    )

    op.create_table(
        "employment_disputes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("disputed_conclusion", sa.String(100), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("alternative_started_at", sa.Date(), nullable=True),
        sa.Column("actual_duties", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("evidence_ids", postgresql.JSONB(), nullable=False),
        sa.Column("status", enums["dispute"], nullable=False),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("resolved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["employment_id"], ["student_employments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["assessment_id"], ["employment_profile_assessments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_employment_disputes_open",
        "employment_disputes",
        ["employment_id", "status", "created_at"],
    )

    op.create_table(
        "employment_billing_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", enums["billing"], nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(500), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["employment_id"], ["student_employments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["assessment_id"], ["employment_profile_assessments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["policy_snapshot_id"], ["employment_contract_policy_snapshots.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_employment_billing_events_idempotency"),
        sa.UniqueConstraint("assessment_id", name="uq_employment_billing_events_assessment"),
    )
    op.create_index(
        "ix_employment_billing_events_status", "employment_billing_events", ["status", "created_at"]
    )

    op.create_table(
        "employment_ai_suggestions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", enums["ai_suggestion"], nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("prompt_version", sa.String(100), nullable=False),
        sa.Column("output", postgresql.JSONB(), nullable=True),
        sa.Column("evidence_ids", postgresql.JSONB(), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(180), nullable=False),
        sa.Column("correlation_id", sa.String(100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("safe_error_message", sa.String(500), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["employment_id"], ["student_employments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_employment_ai_suggestions_idempotency"),
    )
    op.create_index(
        "ix_employment_ai_suggestions_case_created",
        "employment_ai_suggestions",
        ["employment_id", "created_at"],
    )

    op.execute(
        """
        CREATE FUNCTION reject_employment_snapshot_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'employment qualification snapshots are immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in (
        "employment_contract_policy_snapshots",
        "employment_events",
        "employment_profile_assessments",
        "employment_qualification_windows",
    ):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_employment_snapshot_mutation()"
        )


def downgrade() -> None:
    for table in (
        "employment_qualification_windows",
        "employment_profile_assessments",
        "employment_events",
        "employment_contract_policy_snapshots",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS reject_employment_snapshot_mutation()")
    op.drop_index(
        "ix_employment_ai_suggestions_case_created", table_name="employment_ai_suggestions"
    )
    op.drop_table("employment_ai_suggestions")
    op.drop_index("ix_employment_billing_events_status", table_name="employment_billing_events")
    op.drop_table("employment_billing_events")
    op.drop_index("ix_employment_disputes_open", table_name="employment_disputes")
    op.drop_table("employment_disputes")
    op.drop_index("ix_employment_followups_due_status", table_name="employment_followups")
    op.drop_table("employment_followups")
    op.drop_index("ix_employment_evidence_case_created", table_name="employment_evidence")
    op.drop_table("employment_evidence")
    op.drop_index(
        "ix_employment_windows_classification", table_name="employment_qualification_windows"
    )
    op.drop_table("employment_qualification_windows")
    op.drop_constraint(
        "fk_student_employments_current_assessment", "student_employments", type_="foreignkey"
    )
    op.drop_column("student_employments", "current_assessment_id")
    op.drop_index(
        "ix_employment_assessments_classification", table_name="employment_profile_assessments"
    )
    op.drop_index("ix_employment_assessments_pending", table_name="employment_profile_assessments")
    op.drop_table("employment_profile_assessments")
    op.drop_index("ix_employment_technology_case_name", table_name="employment_technology_usages")
    op.drop_table("employment_technology_usages")
    op.drop_index("ix_employment_events_case_effective", table_name="employment_events")
    op.drop_table("employment_events")
    op.drop_index("ix_student_employments_monitoring", table_name="student_employments")
    op.drop_index("ix_student_employments_profile_started", table_name="student_employments")
    op.drop_index("ix_student_employments_case_status", table_name="student_employments")
    op.drop_index("ix_student_employments_student_track", table_name="student_employments")
    op.drop_constraint(
        "fk_student_employments_contract_policy_id_employment_policy",
        "student_employments",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_student_employments_track_id_learning_tracks", "student_employments", type_="foreignkey"
    )
    for column in (
        "legacy_policy_snapshot",
        "lock_version",
        "closed_at",
        "monitoring_due_at",
        "billing_on_hold",
        "billing_started_at",
        "profile_activity_ended_at",
        "profile_activity_started_at",
        "case_status",
        "differences_description",
        "student_comment",
        "team_description",
        "project_description",
        "actual_duties",
        "actual_stack",
        "offer_stack",
        "initial_vacancy_stack",
        "vacancy_duties",
        "contract_signed_at",
        "offer_accepted_at",
        "offer_received_at",
        "activity_type",
        "vacancy_title",
        "official_job_title",
        "expected_start_date",
        "contract_policy_id",
        "track_id",
    ):
        op.drop_column("student_employments", column)
    op.drop_constraint(
        op.f("ck_student_employments_net_salary_positive"),
        "student_employments",
        type_="check",
    )
    op.alter_column(
        "student_employments", "net_salary_kopecks", existing_type=sa.BigInteger(), nullable=False
    )
    op.alter_column("student_employments", "start_date", existing_type=sa.Date(), nullable=False)
    op.create_check_constraint(
        "net_salary_positive", "student_employments", "net_salary_kopecks > 0"
    )
    op.drop_index(
        "ix_employment_policy_student_track", table_name="employment_contract_policy_snapshots"
    )
    op.drop_table("employment_contract_policy_snapshots")
    bind = op.get_bind()
    for name in reversed(list(enums_for_downgrade())):
        sa.Enum(name=name).drop(bind, checkfirst=True)


def enums_for_downgrade() -> tuple[str, ...]:
    return (
        "employment_activity_type",
        "employment_case_status",
        "employment_direction",
        "employment_event_type",
        "employment_event_source",
        "employment_technology_usage_type",
        "employment_technology_frequency",
        "employment_tri_state",
        "employment_profile_classification",
        "employment_window_classification",
        "employment_evidence_type",
        "employment_evidence_verification_status",
        "employment_followup_type",
        "employment_followup_status",
        "employment_dispute_status",
        "employment_billing_event_status",
        "employment_ai_suggestion_status",
    )
