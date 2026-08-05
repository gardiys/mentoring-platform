"""Add durable normalization state for protected learning videos.

Revision ID: 20260805_0035
Revises: 20260804_0034
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260805_0035"
down_revision: str | None = "20260804_0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PROCESSING_STATUS_ENUM = postgresql.ENUM(
    "queued",
    "processing",
    "ready",
    "failed",
    name="content_media_processing_status",
)


def upgrade() -> None:
    bind = op.get_bind()
    PROCESSING_STATUS_ENUM.create(bind, checkfirst=True)
    processing_status = postgresql.ENUM(
        "queued",
        "processing",
        "ready",
        "failed",
        name="content_media_processing_status",
        create_type=False,
    )

    op.add_column(
        "protected_content_media",
        sa.Column(
            "processing_status",
            processing_status,
            server_default="ready",
            nullable=False,
        ),
    )
    op.add_column(
        "protected_content_media",
        sa.Column(
            "normalization_attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "protected_content_media",
        sa.Column(
            "normalization_revision",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "protected_content_media",
        sa.Column("normalization_source_key", sa.String(length=180), nullable=True),
    )
    op.add_column(
        "protected_content_media",
        sa.Column("normalization_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "protected_content_media",
        sa.Column("normalization_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "protected_content_media",
        sa.Column("normalization_error_code", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "protected_content_media",
        sa.Column("normalization_error_message", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "protected_content_media",
        sa.Column(
            "allow_original_playback_during_normalization",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )

    # Previously uploaded MP4/MOV videos have never been inspected for a
    # browser-friendly layout. Queue only the containers that the lossless
    # normalizer supports; other video formats remain playable as uploaded.
    op.execute(
        sa.text(
            """
            UPDATE protected_content_media
            SET processing_status = 'queued',
                normalization_source_key = storage_key,
                normalization_started_at = NULL,
                normalization_completed_at = NULL,
                normalization_error_code = NULL,
                normalization_error_message = NULL,
                allow_original_playback_during_normalization = true
            WHERE lower(trim(split_part(content_type, ';', 1)))
                  IN ('video/mp4', 'video/quicktime')
            """
        )
    )

    op.create_check_constraint(
        "normalization_attempts_non_negative",
        "protected_content_media",
        "normalization_attempts >= 0",
    )
    op.create_check_constraint(
        "normalization_revision_non_negative",
        "protected_content_media",
        "normalization_revision >= 0",
    )
    op.create_check_constraint(
        "normalization_timestamps_ordered",
        "protected_content_media",
        "normalization_completed_at IS NULL "
        "OR normalization_started_at IS NULL "
        "OR normalization_completed_at >= normalization_started_at",
    )
    op.create_check_constraint(
        "processing_requires_started_at",
        "protected_content_media",
        "processing_status <> 'processing' OR normalization_started_at IS NOT NULL",
    )
    op.create_check_constraint(
        "original_playback_source_consistent",
        "protected_content_media",
        "NOT allow_original_playback_during_normalization "
        "OR processing_status = 'ready' "
        "OR normalization_source_key = storage_key",
    )
    op.create_index(
        "ix_protected_content_media_processing_status_updated_at",
        "protected_content_media",
        ["processing_status", "updated_at"],
    )
    op.create_index(
        "ux_protected_content_media_normalization_source_key",
        "protected_content_media",
        ["normalization_source_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ux_protected_content_media_normalization_source_key",
        table_name="protected_content_media",
    )
    op.drop_index(
        "ix_protected_content_media_processing_status_updated_at",
        table_name="protected_content_media",
    )
    op.drop_constraint(
        op.f("ck_protected_content_media_original_playback_source_consistent"),
        "protected_content_media",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_protected_content_media_processing_requires_started_at"),
        "protected_content_media",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_protected_content_media_normalization_timestamps_ordered"),
        "protected_content_media",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_protected_content_media_normalization_revision_non_negative"),
        "protected_content_media",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_protected_content_media_normalization_attempts_non_negative"),
        "protected_content_media",
        type_="check",
    )
    op.drop_column("protected_content_media", "normalization_error_message")
    op.drop_column("protected_content_media", "normalization_error_code")
    op.drop_column("protected_content_media", "normalization_completed_at")
    op.drop_column("protected_content_media", "normalization_started_at")
    op.drop_column("protected_content_media", "normalization_source_key")
    op.drop_column("protected_content_media", "normalization_revision")
    op.drop_column("protected_content_media", "normalization_attempts")
    op.drop_column(
        "protected_content_media",
        "allow_original_playback_during_normalization",
    )
    op.drop_column("protected_content_media", "processing_status")
    PROCESSING_STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
