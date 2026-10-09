"""Audit unknown card costs and require opt-in for legacy blank generation."""

import sqlalchemy as sa
from alembic import op

revision = "20261009_0099"
down_revision = "20261009_0098"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE automation_decision_type ADD VALUE IF NOT EXISTS 'card_ai_cost_written_off'"
        )
    # A downgrade maps this audit to a type understood by older application
    # versions. Restore it on re-upgrade so it stays a financial, not editorial,
    # decision for admission and publication.
    op.execute(
        "UPDATE automation_decisions SET decision_type = 'card_ai_cost_written_off' "
        "WHERE decision_type = 'manual_override' "
        "AND split_part(idempotency_key, ':', 3) = 'cost-write-off' "
        "AND retrieval_scores->>'cost_basis' = 'reservation' "
        "AND retrieval_scores->>'provider_usage_known' = 'false'"
    )
    op.add_column(
        "card_automation_settings",
        sa.Column(
            "card_ai_legacy_backlog_enabled", sa.Boolean(), server_default="false", nullable=False
        ),
    )


def downgrade():
    # Retain the financial audit trail in a decision type understood by 0098.
    op.execute(
        "UPDATE automation_decisions SET decision_type = 'manual_override' "
        "WHERE decision_type = 'card_ai_cost_written_off'"
    )
    op.drop_column("card_automation_settings", "card_ai_legacy_backlog_enabled")
