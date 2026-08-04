"""Add private audio and video attachments to learning content.

Revision ID: 20260804_0033
Revises: 20260804_0032
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260804_0033"
down_revision: str | None = "20260804_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "protected_content_media",
        sa.Column(
            "knowledge_entry_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "roadmap_topic_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "uploaded_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("storage_key", sa.String(length=180), nullable=False),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=160), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=True),
        sa.Column(
            "position",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.CheckConstraint(
            "(knowledge_entry_id IS NOT NULL) <> (roadmap_topic_id IS NOT NULL)",
            name="exactly_one_parent",
        ),
        sa.CheckConstraint(
            "position >= 0",
            name="position_non_negative",
        ),
        sa.CheckConstraint(
            "size > 0",
            name="size_positive",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_entry_id"],
            ["knowledge_entries.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["roadmap_topic_id"],
            ["topics.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "storage_key",
            name="uq_protected_content_media_storage_key",
        ),
    )
    op.create_index(
        "ix_protected_content_media_knowledge_position",
        "protected_content_media",
        ["knowledge_entry_id", "position"],
    )
    op.create_index(
        "ix_protected_content_media_roadmap_position",
        "protected_content_media",
        ["roadmap_topic_id", "position"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_protected_content_media_roadmap_position",
        table_name="protected_content_media",
    )
    op.drop_index(
        "ix_protected_content_media_knowledge_position",
        table_name="protected_content_media",
    )
    op.drop_table("protected_content_media")
