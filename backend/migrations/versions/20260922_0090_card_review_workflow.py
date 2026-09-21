"""Separate provider outages from moderation and bound automatic answer repairs."""

import sqlalchemy as sa
from alembic import op

revision = "20260922_0090"
down_revision = "20260922_0089"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE answer_contract_status ADD VALUE IF NOT EXISTS 'waiting_for_ai'")
        op.execute("ALTER TYPE answer_contract_status ADD VALUE IF NOT EXISTS 'repair_pending'")
    op.add_column("question_clusters", sa.Column("ai_retry_after", sa.DateTime(timezone=True)))
    op.add_column("question_clusters", sa.Column("ai_error_code", sa.String(100)))
    op.add_column(
        "question_clusters",
        sa.Column("answer_repair_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    # Reclassify only a current terminal infrastructure failure. Preserve answers, validation,
    # revisions, and the full audit trail; never reopen a human-reviewed or closed cluster.
    op.execute("""
        UPDATE question_clusters c SET answer_status='waiting_for_ai',
            ai_error_code=d.judge_result->>'error_code',
            ai_retry_after=now()+interval '1 hour', version=c.version+1
        FROM automation_decisions d
        WHERE c.status='needs_review' AND c.linked_card_id IS NULL
          AND c.answer_status='needs_manual_review'
          AND d.id=(SELECT a.id FROM automation_decisions a
              WHERE a.entity_type='cluster' AND a.entity_id=c.id
              ORDER BY a.created_at DESC, a.id DESC LIMIT 1)
          AND d.judge_result->>'error_code' IN
              ('OPENAI_QUOTA_EXCEEDED','OPENAI_AUTH_ERROR','OPENAI_RATE_LIMIT',
               'OPENAI_PROXY_ERROR','OPENAI_PROVIDER_ERROR')
          AND NOT EXISTS (SELECT 1 FROM automation_decisions h
              WHERE h.entity_type='cluster' AND h.entity_id=c.id AND h.decision_source='human')
    """)


def downgrade() -> None:
    op.execute("""UPDATE question_clusters SET answer_status='needs_manual_review'
                  WHERE answer_status IN ('waiting_for_ai','repair_pending')""")
    op.drop_column("question_clusters", "answer_repair_attempts")
    op.drop_column("question_clusters", "ai_error_code")
    op.drop_column("question_clusters", "ai_retry_after")
