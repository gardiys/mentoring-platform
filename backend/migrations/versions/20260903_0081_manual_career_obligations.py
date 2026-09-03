"""Make career package payment obligations an explicit admin action.

Revision ID: 20260903_0081
Revises: 20260903_0080
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260903_0081"
down_revision: str | None = "20260903_0080"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE career_obligation_status ADD VALUE IF NOT EXISTS "
        "'awaiting_notice' BEFORE 'active'"
    )
    delivery_purpose = postgresql.ENUM(
        "package_provided",
        "payment_obligation",
        name="career_delivery_purpose",
    )
    delivery_purpose.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "career_package_deliveries",
        sa.Column(
            "purpose",
            postgresql.ENUM(
                "package_provided",
                "payment_obligation",
                name="career_delivery_purpose",
                create_type=False,
            ),
            nullable=False,
            server_default="package_provided",
        ),
    )
    op.add_column(
        "career_package_obligations",
        sa.Column("offer_accepted_on", sa.Date(), nullable=True),
    )
    op.add_column(
        "career_package_obligations",
        sa.Column("accrued_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "career_package_obligations",
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "career_package_obligations",
        sa.Column("recorded_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "career_package_obligations",
        sa.Column("record_comment", sa.String(length=1000), nullable=True),
    )
    op.add_column(
        "career_package_obligations",
        sa.Column("notice_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_career_package_obligations_recorded_by_user_id_users",
        "career_package_obligations",
        "users",
        ["recorded_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column(
        "career_package_obligations",
        "due_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
    op.alter_column(
        "career_package_objections",
        "deadline_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )

    # Obligations created before this revision were generated automatically when
    # a package was published. Preserve the audit rows, but stop treating unpaid
    # automatic rows as an amount currently due. An administrator can explicitly
    # reuse the same row after verifying the applicable offer and actual delivery.
    op.execute(
        """
        INSERT INTO career_package_events (
            id, package_id, version_id, event_type, actor_user_id,
            actor_role, correlation_id, metadata_json, created_at
        )
        SELECT gen_random_uuid(), package_id, source_version_id,
               'automatic_obligation_cancelled_by_policy', NULL, 'system', NULL,
               jsonb_build_object('previous_status', status::text), now()
         FROM career_package_obligations
         WHERE status IN ('active', 'hold')
           AND recorded_at IS NULL
        """
    )
    op.execute(
        """
        UPDATE career_package_obligations
           SET status = 'cancelled'
         WHERE status IN ('active', 'hold')
           AND recorded_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM career_package_events
         WHERE event_type = 'automatic_obligation_cancelled_by_policy'
        """
    )
    op.execute(
        """
        UPDATE career_package_obligations
           SET due_at = COALESCE(due_at, recorded_at + INTERVAL '10 days', now()),
               status = CASE
                   WHEN status = 'awaiting_notice' THEN 'active'::career_obligation_status
                   ELSE status
               END
        """
    )
    op.drop_constraint(
        "fk_career_package_obligations_recorded_by_user_id_users",
        "career_package_obligations",
        type_="foreignkey",
    )
    op.execute(
        """
        UPDATE career_package_objections
           SET deadline_at = COALESCE(deadline_at, submitted_at + INTERVAL '7 days')
         WHERE deadline_at IS NULL
        """
    )
    op.alter_column(
        "career_package_objections",
        "deadline_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.alter_column(
        "career_package_obligations",
        "due_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.drop_column("career_package_obligations", "notice_sent_at")
    op.drop_column("career_package_obligations", "record_comment")
    op.drop_column("career_package_obligations", "recorded_by_user_id")
    op.drop_column("career_package_obligations", "recorded_at")
    op.drop_column("career_package_obligations", "accrued_at")
    op.drop_column("career_package_obligations", "offer_accepted_on")
    op.drop_column("career_package_deliveries", "purpose")
    postgresql.ENUM(name="career_delivery_purpose").drop(op.get_bind(), checkfirst=True)
