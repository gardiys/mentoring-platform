"""Snapshot Go transition terms and add a source-specific enrollment.

Revision ID: 20260831_0077
Revises: 20260831_0076
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260831_0077"
down_revision: str | None = "20260831_0076"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "go_transition_applications",
        sa.Column("terms_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "go_transition_applications",
        sa.Column("terms_snapshot", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "go_transition_applications",
        sa.Column("terms_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "go_transition_applications",
        sa.Column("accepted_terms_snapshot", postgresql.JSONB(), nullable=True),
    )
    op.execute(
        """
        UPDATE go_transition_applications
        SET terms_snapshot = jsonb_build_object(
            'product_code', 'PYTHON_TO_GO_ALUMNI',
            'terms_version', 1,
            'upfront_price_kopecks', upfront_price_kopecks,
            'success_fee_percent', success_fee_percent,
            'comparison_upfront_price_kopecks', 4500000,
            'comparison_success_fee_percent', 150,
            'currency', 'RUB'
        ),
        terms_expires_at = CASE
            WHEN approved_at IS NULL THEN NULL
            ELSE approved_at + interval '14 days'
        END,
        accepted_terms_snapshot = CASE
            WHEN terms_accepted_at IS NULL THEN NULL
            ELSE jsonb_build_object(
                'product_code', 'PYTHON_TO_GO_ALUMNI',
                'terms_version', 1,
                'upfront_price_kopecks', upfront_price_kopecks,
                'success_fee_percent', success_fee_percent,
                'comparison_upfront_price_kopecks', 4500000,
                'comparison_success_fee_percent', 150,
                'currency', 'RUB'
            )
        END
        """
    )
    op.alter_column("go_transition_applications", "terms_snapshot", nullable=False)

    op.create_table(
        "go_transition_enrollments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("track_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("previous_python_track_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mentor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.String(32), server_default="python_to_go", nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("terms_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("source = 'python_to_go'", name="source_python_to_go"),
        sa.ForeignKeyConstraint(
            ["application_id"], ["go_transition_applications.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["track_id"], ["learning_tracks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["previous_python_track_id"], ["learning_tracks.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["mentor_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["student_id", "previous_python_track_id"],
            ["learning_track_enrollments.user_id", "learning_track_enrollments.track_id"],
            name="fk_go_transition_previous_python_enrollment",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("application_id", name="uq_go_transition_enrollment_application"),
    )
    op.create_index(
        "ix_go_transition_enrollment_student_created",
        "go_transition_enrollments",
        ["student_id", "created_at"],
    )
    op.create_index(
        "uq_go_transition_enrollment_active_student",
        "go_transition_enrollments",
        ["student_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.execute(
        """
        INSERT INTO go_transition_enrollments (
            id, application_id, student_id, track_id, previous_python_track_id,
            source, status, started_at, terms_snapshot
        )
        SELECT
            gen_random_uuid(), application.id, application.student_id, go_track.id,
            python_completion.track_id, 'python_to_go', 'active',
            COALESCE(application.paid_at, application.updated_at), application.terms_snapshot
        FROM go_transition_applications application
        JOIN LATERAL (
            SELECT completion.track_id
            FROM program_completions completion
            JOIN learning_tracks track ON track.id = completion.track_id
            WHERE completion.user_id = application.student_id
              AND (lower(track.slug) LIKE '%python%' OR lower(track.title) LIKE '%python%')
            ORDER BY completion.completed_at DESC
            LIMIT 1
        ) python_completion ON true
        JOIN LATERAL (
            SELECT track.id
            FROM learning_tracks track
            WHERE lower(track.slug) = 'go'
            ORDER BY track.created_at
            LIMIT 1
        ) go_track ON true
        WHERE application.status = 'paid'
        ON CONFLICT (application_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index(
        "uq_go_transition_enrollment_active_student", table_name="go_transition_enrollments"
    )
    op.drop_index(
        "ix_go_transition_enrollment_student_created", table_name="go_transition_enrollments"
    )
    op.drop_table("go_transition_enrollments")
    op.drop_column("go_transition_applications", "accepted_terms_snapshot")
    op.drop_column("go_transition_applications", "terms_expires_at")
    op.drop_column("go_transition_applications", "terms_snapshot")
    op.drop_column("go_transition_applications", "terms_version")
