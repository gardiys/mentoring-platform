"""Allow erroneous mentor rewards to be voided with an audit trail.

Revision ID: 20260812_0047
Revises: 20260812_0046
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260812_0047"
down_revision: str | None = "20260812_0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "mentor_rewards",
        sa.Column("voided_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "mentor_rewards",
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "mentor_rewards",
        sa.Column("void_reason", sa.String(length=500), nullable=True),
    )
    op.create_foreign_key(
        "fk_mentor_rewards_voided_by_user_id_users",
        "mentor_rewards",
        "users",
        ["voided_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_mentor_rewards_voided_by_user_id_users",
        "mentor_rewards",
        type_="foreignkey",
    )
    op.drop_column("mentor_rewards", "void_reason")
    op.drop_column("mentor_rewards", "voided_at")
    op.drop_column("mentor_rewards", "voided_by_user_id")
