"""Add career package workflow and immutable delivery snapshots.

Revision ID: 20260903_0079
Revises: 20260902_0078
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260903_0079"
down_revision: str | None = "20260902_0078"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> postgresql.ENUM:
    # Types are created explicitly below so all table declarations must reuse
    # them without emitting another CREATE TYPE statement.
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    op.execute("ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'career_package'")
    package_status = _enum(
        "career_package_status",
        "not_started",
        "collecting_data",
        "generating",
        "draft",
        "review_required",
        "ready_to_publish",
        "delivery_pending",
        "provided",
        "revision_requested",
        "cancelled",
    )
    generation_status = _enum(
        "career_generation_status", "queued", "running", "completed", "failed", "cancelled"
    )
    generation_component = _enum(
        "career_generation_component", "all", "self_presentation", "active_search"
    )
    delivery_channel = _enum("career_delivery_channel", "platform", "telegram", "email")
    delivery_status = _enum("career_delivery_status", "pending", "delivered", "failed")
    obligation_status = _enum("career_obligation_status", "active", "hold", "paid", "cancelled")
    objection_component = _enum(
        "career_objection_component",
        "resume",
        "self_presentation_card",
        "active_search_parameters",
        "completeness",
        "other",
    )
    objection_status = _enum(
        "career_objection_status",
        "submitted",
        "under_review",
        "accepted",
        "partially_accepted",
        "rejected",
        "resolved",
    )
    bind = op.get_bind()
    for enum in (
        package_status,
        generation_status,
        generation_component,
        delivery_channel,
        delivery_status,
        obligation_status,
        objection_component,
        objection_status,
    ):
        enum.create(bind, checkfirst=True)

    op.create_table(
        "career_resume_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("storage_key", sa.String(500), nullable=True),
        sa.Column("filename", sa.String(500), nullable=True),
        sa.Column("content_type", sa.String(160), nullable=True),
        sa.Column("size", sa.BigInteger(), nullable=True),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("finalized_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "finalized_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "text_content IS NOT NULL OR storage_key IS NOT NULL",
            name=op.f("ck_career_resume_versions_has_content"),
        ),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_document_id"], ["mentor_student_documents.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["finalized_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "student_id", "version_number", name="uq_career_resume_student_version"
        ),
        sa.UniqueConstraint("student_id", "content_sha256", name="uq_career_resume_student_hash"),
    )
    op.create_index(
        "ix_career_resume_versions_student_finalized",
        "career_resume_versions",
        ["student_id", "finalized_at"],
        unique=False,
    )

    op.create_table(
        "career_packages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("track_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", package_status, nullable=False),
        sa.Column("source_resume_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("latest_published_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lock_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "lock_version >= 1", name=op.f("ck_career_packages_lock_version_positive")
        ),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["track_id"], ["learning_tracks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_resume_version_id"], ["career_resume_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "track_id", name="uq_career_packages_student_track"),
    )
    op.create_index(
        "ix_career_packages_status_updated",
        "career_packages",
        ["status", "updated_at"],
        unique=False,
    )

    op.create_table(
        "career_package_generation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("package_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", generation_status, nullable=False),
        sa.Column("component", generation_component, nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("prompt_version", sa.String(100), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("correlation_id", sa.String(100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("safe_error_message", sa.String(500), nullable=True),
        sa.Column("token_usage", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["package_id"], ["career_packages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_career_generation_idempotency"),
    )
    op.create_index(
        "ix_career_generation_package_created",
        "career_package_generation_runs",
        ["package_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "career_package_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("package_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_resume_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_data", postgresql.JSONB(), nullable=False),
        sa.Column("self_presentation_card", postgresql.JSONB(), nullable=True),
        sa.Column("active_search_parameters", postgresql.JSONB(), nullable=True),
        sa.Column("missing_data", postgresql.JSONB(), nullable=False),
        sa.Column("warnings", postgresql.JSONB(), nullable=False),
        sa.Column("generation_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_edited_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_stale", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["package_id"], ["career_packages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_resume_version_id"], ["career_resume_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["generation_run_id"], ["career_package_generation_runs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["last_edited_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("package_id", name="uq_career_package_drafts_package"),
    )

    op.create_table(
        "career_package_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("package_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("source_resume_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("rendered_html", sa.Text(), nullable=False),
        sa.Column("pdf_object_key", sa.String(500), nullable=False),
        sa.Column("pdf_size", sa.BigInteger(), nullable=False),
        sa.Column("pdf_sha256", sa.String(64), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(100), nullable=True),
        sa.Column("generated_by_ai", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("generation_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("objection_deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("supersedes_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["package_id"], ["career_packages.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_resume_version_id"], ["career_resume_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["generation_run_id"], ["career_package_generation_runs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["supersedes_version_id"], ["career_package_versions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("package_id", "version_number", name="uq_career_versions_number"),
        sa.UniqueConstraint("snapshot_sha256", name="uq_career_versions_snapshot_sha256"),
    )
    op.create_index(
        "ix_career_versions_package_published",
        "career_package_versions",
        ["package_id", "published_at"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_career_packages_latest_version",
        "career_packages",
        "career_package_versions",
        ["latest_published_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "career_package_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("package_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", delivery_channel, nullable=False),
        sa.Column("status", delivery_status, nullable=False),
        sa.Column("recipient", sa.String(320), nullable=False),
        sa.Column("external_message_id", sa.String(240), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("safe_error_message", sa.String(500), nullable=True),
        sa.Column("idempotency_key", sa.String(180), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["package_version_id"], ["career_package_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_career_deliveries_idempotency"),
    )
    op.create_index(
        "ix_career_deliveries_version_channel",
        "career_package_deliveries",
        ["package_version_id", "channel"],
        unique=False,
    )

    op.create_table(
        "career_package_obligations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("package_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount_kopecks", sa.BigInteger(), server_default="3000000", nullable=False),
        sa.Column("currency", sa.String(3), server_default="RUB", nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", obligation_status, nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("idempotency_key", sa.String(180), nullable=False),
        sa.Column("disputed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "amount_kopecks = 3000000", name=op.f("ck_career_package_obligations_amount_fixed")
        ),
        sa.ForeignKeyConstraint(["package_id"], ["career_packages.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_version_id"], ["career_package_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("package_id", name="uq_career_obligations_package"),
        sa.UniqueConstraint("idempotency_key", name="uq_career_obligations_idempotency"),
    )
    op.create_index(
        "ix_career_obligations_due_status",
        "career_package_obligations",
        ["due_at", "status"],
        unique=False,
    )

    op.create_table(
        "career_package_objections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("package_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("component", objection_component, nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("expected_result", sa.Text(), nullable=False),
        sa.Column("attachments", postgresql.JSONB(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_late", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("status", objection_status, nullable=False),
        sa.Column("resolution_comment", sa.Text(), nullable=True),
        sa.Column("resolved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["package_version_id"], ["career_package_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_career_objections_version_status",
        "career_package_objections",
        ["package_version_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_career_objections_student_created",
        "career_package_objections",
        ["student_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "career_self_presentation_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("package_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("held_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("strengths", sa.Text(), nullable=False),
        sa.Column("improvements", sa.Text(), nullable=False),
        sa.Column("preparation_for_next_attempt", sa.Text(), nullable=False),
        sa.Column("additional_notes", sa.Text(), nullable=True),
        sa.Column("sent_to_student_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["package_id"], ["career_packages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_career_reviews_package_held",
        "career_self_presentation_reviews",
        ["package_id", "held_at"],
        unique=False,
    )

    op.create_table(
        "career_package_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("package_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_role", sa.String(32), nullable=True),
        sa.Column("correlation_id", sa.String(100), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["package_id"], ["career_packages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["version_id"], ["career_package_versions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_career_events_package_created",
        "career_package_events",
        ["package_id", "created_at"],
        unique=False,
    )
    op.execute(
        """
        CREATE FUNCTION reject_career_snapshot_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'career package snapshots are immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER career_resume_versions_immutable
        BEFORE UPDATE OR DELETE ON career_resume_versions
        FOR EACH ROW EXECUTE FUNCTION reject_career_snapshot_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER career_package_versions_immutable
        BEFORE UPDATE OR DELETE ON career_package_versions
        FOR EACH ROW EXECUTE FUNCTION reject_career_snapshot_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS career_package_versions_immutable ON career_package_versions"
    )
    op.execute("DROP TRIGGER IF EXISTS career_resume_versions_immutable ON career_resume_versions")
    op.execute("DROP FUNCTION IF EXISTS reject_career_snapshot_mutation()")
    op.drop_index("ix_career_events_package_created", table_name="career_package_events")
    op.drop_table("career_package_events")
    op.drop_index("ix_career_reviews_package_held", table_name="career_self_presentation_reviews")
    op.drop_table("career_self_presentation_reviews")
    op.drop_index("ix_career_objections_student_created", table_name="career_package_objections")
    op.drop_index("ix_career_objections_version_status", table_name="career_package_objections")
    op.drop_table("career_package_objections")
    op.drop_index("ix_career_obligations_due_status", table_name="career_package_obligations")
    op.drop_table("career_package_obligations")
    op.drop_index("ix_career_deliveries_version_channel", table_name="career_package_deliveries")
    op.drop_table("career_package_deliveries")
    op.drop_constraint(
        "fk_career_packages_latest_version",
        "career_packages",
        type_="foreignkey",
    )
    op.drop_index("ix_career_versions_package_published", table_name="career_package_versions")
    op.drop_table("career_package_versions")
    op.drop_table("career_package_drafts")
    op.drop_index(
        "ix_career_generation_package_created", table_name="career_package_generation_runs"
    )
    op.drop_table("career_package_generation_runs")
    op.drop_index("ix_career_packages_status_updated", table_name="career_packages")
    op.drop_table("career_packages")
    op.drop_index(
        "ix_career_resume_versions_student_finalized", table_name="career_resume_versions"
    )
    op.drop_table("career_resume_versions")
    bind = op.get_bind()
    for name in (
        "career_objection_status",
        "career_objection_component",
        "career_obligation_status",
        "career_delivery_status",
        "career_delivery_channel",
        "career_generation_component",
        "career_generation_status",
        "career_package_status",
    ):
        sa.Enum(name=name).drop(bind, checkfirst=True)
