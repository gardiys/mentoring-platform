"""Store configurable prices for every consultation type.

Revision ID: 20260831_0072
Revises: 20260831_0071
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260831_0072"
down_revision: str | None = "20260831_0071"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "consultation_type_settings",
        sa.Column(
            "consultation_type",
            postgresql.ENUM(name="consultation_type", create_type=False),
            nullable=False,
        ),
        sa.Column("alumni_price_kopecks", sa.BigInteger(), nullable=False),
        sa.Column("standard_price_kopecks", sa.BigInteger(), nullable=False),
        sa.Column("mentor_reward_kopecks", sa.BigInteger(), nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.CheckConstraint("alumni_price_kopecks > 0", name="alumni_price_positive"),
        sa.CheckConstraint("standard_price_kopecks > 0", name="standard_price_positive"),
        sa.CheckConstraint(
            "standard_price_kopecks >= alumni_price_kopecks",
            name="standard_price_not_lower_than_alumni",
        ),
        sa.CheckConstraint("mentor_reward_kopecks >= 0", name="mentor_reward_non_negative"),
        sa.CheckConstraint(
            "mentor_reward_kopecks <= alumni_price_kopecks",
            name="mentor_reward_not_higher_than_price",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("consultation_type"),
    )

    settings = sa.table(
        "consultation_type_settings",
        sa.column(
            "consultation_type",
            postgresql.ENUM(name="consultation_type", create_type=False),
        ),
        sa.column("alumni_price_kopecks", sa.BigInteger()),
        sa.column("standard_price_kopecks", sa.BigInteger()),
        sa.column("mentor_reward_kopecks", sa.BigInteger()),
    )
    regular = (400_000, 500_000, 250_000)
    premium = (600_000, 700_000, 300_000)
    op.bulk_insert(
        settings,
        [
            {
                "consultation_type": consultation_type,
                "alumni_price_kopecks": prices[0],
                "standard_price_kopecks": prices[1],
                "mentor_reward_kopecks": prices[2],
            }
            for consultation_type, prices in (
                ("free_topic", regular),
                ("technical_mock", regular),
                ("legend_mock", regular),
                ("resume_legend", premium),
                ("system_design_mock", premium),
                ("work_task", premium),
            )
        ],
    )


def downgrade() -> None:
    op.drop_table("consultation_type_settings")
