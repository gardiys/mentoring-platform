"""Reconcile interview_catalog_views/favorites with their stage-scoped schema.

Revision 20260807_0037 was edited in place after it had already run in some
environments (once when these tables were process-scoped, again when they
became stage-scoped). Alembic tracks migrations by revision id, not content,
so any environment that already applied 20260807_0037 before its last edit
is stuck with a `process_id` column the current code no longer queries,
breaking every catalog listing with an undefined-column error. This
migration converges any such environment (and any that were already in the
correct state) onto the exact current schema; the underlying data is
per-user view/favorite bookkeeping recreated automatically as users browse,
so recreating the tables outright is simpler and safer than reverse
engineering which historical shape a given environment is in.

Revision ID: 20260807_0038
Revises: 20260807_0037
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260807_0038"
down_revision: str | None = "20260807_0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS interview_catalog_favorites"))
    op.execute(sa.text("DROP TABLE IF EXISTS interview_catalog_views"))

    op.create_table(
        "interview_catalog_views",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("first_viewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_viewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["stage_id"],
            ["interview_process_stages.id"],
            ondelete="CASCADE",
            name="fk_interview_catalog_views_stage_id_interview_process_stages",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_interview_catalog_views_user_id_users",
        ),
        sa.PrimaryKeyConstraint("user_id", "stage_id", name="pk_interview_catalog_views"),
    )
    op.create_index(
        "ix_interview_catalog_views_user",
        "interview_catalog_views",
        ["user_id", "last_viewed_at"],
    )
    op.create_table(
        "interview_catalog_favorites",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["stage_id"],
            ["interview_process_stages.id"],
            ondelete="CASCADE",
            name="fk_interview_catalog_favorites_stage_id_process_stages",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_interview_catalog_favorites_user_id_users",
        ),
        sa.PrimaryKeyConstraint("user_id", "stage_id", name="pk_interview_catalog_favorites"),
    )
    op.create_index(
        "ix_interview_catalog_favorites_user",
        "interview_catalog_favorites",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    # No prior state to restore: the whole point of this migration is that
    # 20260807_0037 may have already been applied under a different (and
    # incompatible) definition of these tables in some environments, so
    # there is no single well-defined "previous shape" to roll back to.
    # Leave the tables as this migration created them; 20260807_0037's own
    # downgrade() drops them by name when the chain continues past this one.
    pass
