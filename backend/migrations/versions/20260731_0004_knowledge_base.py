"""Add knowledge base with PostgreSQL full-text search."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260731_0004"
down_revision: str | None = "20260731_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

entry_kind = postgresql.ENUM("article", "question", name="knowledge_entry_kind", create_type=False)

SEARCH_VECTOR_SQL = """
setweight(to_tsvector('russian'::regconfig, coalesce(title, '')), 'A') ||
setweight(to_tsvector('russian'::regconfig, coalesce(summary, '')), 'B') ||
setweight(to_tsvector('russian'::regconfig, coalesce(content_markdown, '')), 'C')
"""


def upgrade() -> None:
    entry_kind.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "knowledge_topics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(160), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("position >= 0", name="ck_knowledge_topics_position_non_negative"),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_topics"),
        sa.UniqueConstraint("slug", name="uq_knowledge_topics_slug"),
    )
    op.create_table(
        "knowledge_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", entry_kind, nullable=False),
        sa.Column("slug", sa.String(160), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("content_markdown", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(SEARCH_VECTOR_SQL, persisted=True),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("position >= 0", name="ck_knowledge_entries_position_non_negative"),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["knowledge_topics.id"],
            ondelete="CASCADE",
            name="fk_knowledge_entries_topic_id_knowledge_topics",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_entries"),
        sa.UniqueConstraint("slug", name="uq_knowledge_entries_slug"),
    )
    op.create_index(
        "ix_knowledge_entries_topic_position",
        "knowledge_entries",
        ["topic_id", "position"],
    )
    op.create_index(
        "ix_knowledge_entries_search_vector",
        "knowledge_entries",
        ["search_vector"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_table("knowledge_entries")
    op.drop_table("knowledge_topics")
    entry_kind.drop(op.get_bind(), checkfirst=True)
