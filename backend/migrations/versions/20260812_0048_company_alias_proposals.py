"""Moderate user-submitted company aliases before publishing them.

Revision ID: 20260812_0048
Revises: 20260812_0047
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260812_0048"
down_revision: str | None = "20260812_0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


proposal_status = postgresql.ENUM(
    "pending",
    "approved",
    "rejected",
    name="company_alias_proposal_status",
    create_type=False,
)


def upgrade() -> None:
    proposal_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "company_alias_proposals",
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("company_name", sa.String(length=240), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("normalized_name", sa.String(length=240), nullable=False),
        sa.Column("transliterated_name", sa.String(length=500), nullable=False),
        sa.Column("suggested_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            proposal_status,
            server_default="pending",
            nullable=False,
        ),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.String(length=500), nullable=True),
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
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["suggested_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "normalized_name",
            "suggested_by_user_id",
            name="uq_company_alias_proposals_company_alias_suggester",
        ),
    )
    op.create_index(
        "ix_company_alias_proposals_company_id",
        "company_alias_proposals",
        ["company_id"],
    )
    op.create_index(
        "ix_company_alias_proposals_normalized_name",
        "company_alias_proposals",
        ["normalized_name"],
    )
    op.create_index(
        "ix_company_alias_proposals_status_created",
        "company_alias_proposals",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_company_alias_proposals_suggested_by_user_id",
        "company_alias_proposals",
        ["suggested_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_company_alias_proposals_suggested_by_user_id",
        table_name="company_alias_proposals",
    )
    op.drop_index(
        "ix_company_alias_proposals_status_created",
        table_name="company_alias_proposals",
    )
    op.drop_index(
        "ix_company_alias_proposals_normalized_name",
        table_name="company_alias_proposals",
    )
    op.drop_index(
        "ix_company_alias_proposals_company_id",
        table_name="company_alias_proposals",
    )
    op.drop_table("company_alias_proposals")
    proposal_status.drop(op.get_bind(), checkfirst=True)
