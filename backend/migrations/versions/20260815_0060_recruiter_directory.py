"""Add recruiter contact directory, contact counters and feedback.

Revision ID: 20260815_0060
Revises: 20260815_0059
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260815_0060"
down_revision: str | None = "20260815_0059"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    feedback_kind = postgresql.ENUM(
        "helpful",
        "ignores",
        "no_longer_works",
        "account_missing",
        "other",
        name="recruiter_feedback_kind",
        create_type=False,
    )
    feedback_kind.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "recruiter_contacts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("telegram_username", sa.String(length=32), nullable=False),
        sa.Column("normalized_username", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_username"),
    )
    op.create_table(
        "recruiter_contact_processes",
        sa.Column("recruiter_id", sa.UUID(), nullable=False),
        sa.Column("process_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["process_id"], ["interview_processes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recruiter_id"], ["recruiter_contacts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("recruiter_id", "process_id"),
    )
    op.create_index(
        "ix_recruiter_contact_processes_process",
        "recruiter_contact_processes",
        ["process_id"],
    )
    op.create_table(
        "recruiter_contact_opens",
        sa.Column("recruiter_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("open_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "first_opened_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_opened_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("open_count > 0", name="open_count_positive"),
        sa.ForeignKeyConstraint(["recruiter_id"], ["recruiter_contacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("recruiter_id", "user_id"),
    )
    op.create_index(
        "ix_recruiter_contact_opens_recruiter_last",
        "recruiter_contact_opens",
        ["recruiter_id", "last_opened_at"],
    )
    op.create_table(
        "recruiter_feedback",
        sa.Column("recruiter_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("kind", feedback_kind, nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["recruiter_id"], ["recruiter_contacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("recruiter_id", "user_id"),
    )
    op.create_index(
        "ix_recruiter_feedback_recruiter_kind",
        "recruiter_feedback",
        ["recruiter_id", "kind"],
    )

    # Backfill every valid recruiter already imported with interview processes.
    op.execute(
        """
        INSERT INTO recruiter_contacts (id, telegram_username, normalized_username)
        SELECT gen_random_uuid(), MIN(username), lower(username)
        FROM interview_processes process,
             LATERAL unnest(process.recruiter_telegram_usernames) AS username
        WHERE username ~ '^[A-Za-z][A-Za-z0-9_]{4,31}$'
        GROUP BY lower(username)
        ON CONFLICT (normalized_username) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO recruiter_contact_processes (recruiter_id, process_id)
        SELECT DISTINCT recruiter.id, process.id
        FROM interview_processes process,
             LATERAL unnest(process.recruiter_telegram_usernames) AS username
        JOIN recruiter_contacts recruiter ON recruiter.normalized_username = lower(username)
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_recruiter_feedback_recruiter_kind", table_name="recruiter_feedback")
    op.drop_table("recruiter_feedback")
    op.drop_index("ix_recruiter_contact_opens_recruiter_last", table_name="recruiter_contact_opens")
    op.drop_table("recruiter_contact_opens")
    op.drop_index(
        "ix_recruiter_contact_processes_process", table_name="recruiter_contact_processes"
    )
    op.drop_table("recruiter_contact_processes")
    op.drop_table("recruiter_contacts")
    postgresql.ENUM(name="recruiter_feedback_kind").drop(op.get_bind(), checkfirst=True)
