"""Revocable Copilot desktop access grants.

Revision ID: 20260907_0082
Revises: 20260903_0081
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260907_0082"
down_revision = "20260903_0081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "desktop_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("device_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("user_code", sa.String(12), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("requester_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("polled_at", sa.DateTime(timezone=True)),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE")
        ),
        sa.Column("session_version", sa.Integer()),
        sa.Column("token_hash", sa.String(64), unique=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_desktop_grants_requester_hash", "desktop_grants", ["requester_hash"])
    op.create_index("ix_desktop_grants_expires_at", "desktop_grants", ["expires_at"])


def downgrade() -> None:
    op.drop_table("desktop_grants")
