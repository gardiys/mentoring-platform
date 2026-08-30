"""Add student public privacy and personal data erasure state.

Revision ID: 20260830_0069
Revises: 20260825_0068
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260830_0069"
down_revision: str | None = "20260825_0068"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    media_anonymization_status = postgresql.ENUM(
        "queued",
        "processing",
        "ready",
        "failed",
        name="interview_media_anonymization_status",
    )
    media_anonymization_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "users",
        sa.Column("public_identity_hidden_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "public_identity_hidden_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column("public_identity_hidden_reason", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("personal_data_erased_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "personal_data_erased_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column("personal_data_erasure_reason", sa.String(length=500), nullable=True),
    )
    op.create_foreign_key(
        "fk_users_public_identity_hidden_by_user_id_users",
        "users",
        "users",
        ["public_identity_hidden_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "interview_process_stages",
        sa.Column("anonymized_media_storage_key", sa.String(length=180), nullable=True),
    )
    op.add_column(
        "interview_process_stages",
        sa.Column("anonymized_media_filename", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "interview_process_stages",
        sa.Column("anonymized_media_content_type", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "interview_process_stages",
        sa.Column("anonymized_media_size", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "interview_process_stages",
        sa.Column(
            "media_anonymization_status",
            postgresql.ENUM(
                "queued",
                "processing",
                "ready",
                "failed",
                name="interview_media_anonymization_status",
                create_type=False,
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "interview_process_stages",
        sa.Column("media_anonymization_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "interview_process_stages",
        sa.Column("media_anonymization_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "interview_process_stages",
        sa.Column("media_anonymization_error", sa.String(length=500), nullable=True),
    )
    op.create_index(
        "ix_interview_process_stages_media_anonymization_status",
        "interview_process_stages",
        ["media_anonymization_status", "updated_at"],
    )
    op.create_foreign_key(
        "fk_users_personal_data_erased_by_user_id_users",
        "users",
        "users",
        ["personal_data_erased_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_interview_process_stages_media_anonymization_status",
        table_name="interview_process_stages",
    )
    op.drop_column("interview_process_stages", "media_anonymization_error")
    op.drop_column("interview_process_stages", "media_anonymization_completed_at")
    op.drop_column("interview_process_stages", "media_anonymization_started_at")
    op.drop_column("interview_process_stages", "media_anonymization_status")
    op.drop_column("interview_process_stages", "anonymized_media_size")
    op.drop_column("interview_process_stages", "anonymized_media_content_type")
    op.drop_column("interview_process_stages", "anonymized_media_filename")
    op.drop_column("interview_process_stages", "anonymized_media_storage_key")
    op.drop_constraint(
        "fk_users_personal_data_erased_by_user_id_users", "users", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_users_public_identity_hidden_by_user_id_users", "users", type_="foreignkey"
    )
    op.drop_column("users", "personal_data_erasure_reason")
    op.drop_column("users", "personal_data_erased_by_user_id")
    op.drop_column("users", "personal_data_erased_at")
    op.drop_column("users", "public_identity_hidden_reason")
    op.drop_column("users", "public_identity_hidden_by_user_id")
    op.drop_column("users", "public_identity_hidden_at")
    postgresql.ENUM(name="interview_media_anonymization_status").drop(
        op.get_bind(), checkfirst=True
    )
