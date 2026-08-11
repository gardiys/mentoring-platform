"""Make signed browser sessions revocable.

Revision ID: 20260812_0049
Revises: 20260812_0048
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260812_0049"
down_revision: str | None = "20260812_0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("session_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.create_check_constraint(
        "session_version_positive",
        "users",
        "session_version >= 1",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_users_session_version_positive"),
        "users",
        type_="check",
    )
    op.drop_column("users", "session_version")
