"""Initial MVP schema."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260731_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

user_role = postgresql.ENUM("student", "mentor", "admin", name="user_role", create_type=False)
progress_status = postgresql.ENUM(
    "not_started", "in_progress", "completed", name="progress_status", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    user_role.create(bind, checkfirst=True)
    progress_status.create(bind, checkfirst=True)
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("first_name", sa.String(120), nullable=False),
        sa.Column("last_name", sa.String(120), nullable=True),
        sa.Column("role", user_role, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)
    op.create_table(
        "roadmaps",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(160), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("position >= 0", name="ck_roadmaps_position_non_negative"),
        sa.PrimaryKeyConstraint("id", name="pk_roadmaps"),
        sa.UniqueConstraint("slug", name="uq_roadmaps_slug"),
    )
    op.create_table(
        "mentor_students",
        sa.Column("mentor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("mentor_id <> student_id", name="ck_mentor_students_different_users"),
        sa.ForeignKeyConstraint(["mentor_id"], ["users.id"], ondelete="CASCADE", name="fk_mentor_students_mentor_id_users"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE", name="fk_mentor_students_student_id_users"),
        sa.PrimaryKeyConstraint("mentor_id", "student_id", name="pk_mentor_students"),
    )
    op.create_index("ix_mentor_students_mentor", "mentor_students", ["mentor_id", "student_id"])
    op.create_table(
        "roadmap_sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("roadmap_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("position >= 0", name="ck_roadmap_sections_position_non_negative"),
        sa.ForeignKeyConstraint(["roadmap_id"], ["roadmaps.id"], ondelete="CASCADE", name="fk_roadmap_sections_roadmap_id_roadmaps"),
        sa.PrimaryKeyConstraint("id", name="pk_roadmap_sections"),
    )
    op.create_index("ix_roadmap_sections_position", "roadmap_sections", ["roadmap_id", "position"])
    op.create_table(
        "roadmap_enrollments",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("roadmap_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["roadmap_id"], ["roadmaps.id"], ondelete="CASCADE", name="fk_roadmap_enrollments_roadmap_id_roadmaps"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name="fk_roadmap_enrollments_user_id_users"),
        sa.PrimaryKeyConstraint("user_id", "roadmap_id", name="pk_roadmap_enrollments"),
    )
    op.create_table(
        "topics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(160), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("content_markdown", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=True),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("estimated_minutes IS NULL OR estimated_minutes > 0", name="ck_topics_estimated_minutes_positive"),
        sa.CheckConstraint("position >= 0", name="ck_topics_position_non_negative"),
        sa.ForeignKeyConstraint(["section_id"], ["roadmap_sections.id"], ondelete="CASCADE", name="fk_topics_section_id_roadmap_sections"),
        sa.PrimaryKeyConstraint("id", name="pk_topics"),
        sa.UniqueConstraint("slug", name="uq_topics_slug"),
    )
    op.create_index("ix_topics_section_position", "topics", ["section_id", "position"])
    op.create_table(
        "topic_progress",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", progress_status, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="CASCADE", name="fk_topic_progress_topic_id_topics"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name="fk_topic_progress_user_id_users"),
        sa.PrimaryKeyConstraint("user_id", "topic_id", name="pk_topic_progress"),
    )
    op.create_index("ix_topic_progress_user_updated", "topic_progress", ["user_id", "updated_at"])


def downgrade() -> None:
    op.drop_table("topic_progress")
    op.drop_table("topics")
    op.drop_table("roadmap_enrollments")
    op.drop_table("roadmap_sections")
    op.drop_table("mentor_students")
    op.drop_table("roadmaps")
    op.drop_table("users")
    progress_status.drop(op.get_bind(), checkfirst=True)
    user_role.drop(op.get_bind(), checkfirst=True)
