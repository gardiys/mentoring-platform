"""Ranked card admission and recoverable financial reservations."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261009_0098"
down_revision = "20261007_0097"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE answer_contract_status ADD VALUE IF NOT EXISTS 'not_selected'")
        op.execute("ALTER TYPE automation_decision_type ADD VALUE IF NOT EXISTS 'card_ai_deferred'")
    for name in ("ai_started_at", "ai_ready_at"):
        op.add_column(
            "intelligence_interviews", sa.Column(name, sa.DateTime(timezone=True), nullable=True)
        )
    uuid = postgresql.UUID(as_uuid=True)
    op.add_column(
        "question_clusters",
        sa.Column("generation_backlog", sa.Boolean(), server_default="false", nullable=False),
    )
    for name, kind in [
        ("generation_deferred_reason", sa.String(100)),
        ("generation_retry_after", sa.DateTime(timezone=True)),
        ("generation_selected_revision", sa.Integer()),
        ("generation_source_interview_id", uuid),
        ("generation_admitted_at", sa.DateTime(timezone=True)),
    ]:
        op.add_column("question_clusters", sa.Column(name, kind, nullable=True))
    for name, kind, default in [
        ("card_ai_max_topics_per_interview", sa.Integer(), "10"),
        ("card_ai_budget_per_interview_usd", sa.Numeric(18, 10), "0.40"),
        ("card_ai_daily_budget_usd", sa.Numeric(18, 10), "5"),
        ("card_ai_maintenance_budget_usd", sa.Numeric(18, 10), "1"),
        ("card_ai_min_priority_score", sa.Float(), "4"),
    ]:
        op.add_column(
            "card_automation_settings",
            sa.Column(name, kind, server_default=default, nullable=False),
        )
    for name, kind, default in [
        ("request_reserve_usd", sa.Numeric(18, 10), "0"),
        ("operation", sa.String(60), "generate_answer_contract"),
        ("manual", sa.Boolean(), "false"),
        ("maintenance", sa.Boolean(), "false"),
        ("status", sa.String(30), "reserved"),
        ("released_pledge_usd", sa.Numeric(18, 10), "0"),
    ]:
        op.add_column(
            "card_ai_charges", sa.Column(name, kind, server_default=default, nullable=False)
        )
    for name, kind in [
        ("direction_id", uuid),
        ("settled_at", sa.DateTime(timezone=True)),
        ("reserve_expires_at", sa.DateTime(timezone=True)),
        ("pledge_request_id", uuid),
        ("reason", sa.String(100)),
    ]:
        op.add_column("card_ai_charges", sa.Column(name, kind, nullable=True))
    op.create_index("ix_card_ai_charges_direction_id", "card_ai_charges", ["direction_id"])
    for name in ("interview_id", "cluster_id"):
        op.add_column("ai_request_logs", sa.Column(name, uuid, nullable=True))
        op.create_index(f"ix_ai_request_logs_{name}", "ai_request_logs", [name])
    op.execute(
        "UPDATE card_ai_charges c "
        "SET request_reserve_usd = amount_usd - validation_reserve_usd "
        "WHERE NOT EXISTS (SELECT 1 FROM ai_request_logs l "
        "WHERE l.id = c.request_id AND l.estimated_cost_usd IS NOT NULL)"
    )
    op.execute("""UPDATE card_ai_charges c SET direction_id = q.direction_id,
        reserve_expires_at = c.created_at + interval '24 hours'
        FROM question_clusters q WHERE q.id = c.cluster_id""")
    op.execute(
        "UPDATE card_ai_charges c SET operation = l.operation "
        "FROM ai_request_logs l WHERE l.id = c.request_id"
    )
    op.execute(
        "UPDATE ai_request_logs l SET interview_id = c.interview_id, cluster_id = c.cluster_id "
        "FROM card_ai_charges c WHERE c.request_id = l.id"
    )
    op.execute(
        "UPDATE question_clusters SET generation_backlog = true, "
        "generation_selected_revision = membership_revision"
    )
    op.execute("""UPDATE intelligence_interviews i SET ai_started_at = i.created_at,
        ai_ready_at = (SELECT max(a.finished_at) FROM intelligence_processing_attempts a
          WHERE a.interview_id = i.id AND a.stage = 'ai_review' AND a.status = 'completed')
        WHERE i.processing_status = 'ready' AND i.analysis_revision = 1""")
    op.execute("""UPDATE question_clusters SET answer_status = 'not_selected',
        generation_deferred_reason = 'CARD_AI_NOT_SELECTED',
        generation_selected_revision = membership_revision,
        generation_retry_after = now(), ai_error_code = NULL
        WHERE ai_error_code = 'CARD_AI_BUDGET_LIMIT' AND status = 'needs_review'
          AND answer_status = 'needs_manual_review'""")


def downgrade():
    for name in ("ai_started_at", "ai_ready_at"):
        op.drop_column("intelligence_interviews", name)
    op.execute(
        "UPDATE question_clusters SET answer_status = 'needs_manual_review' "
        "WHERE answer_status = 'not_selected'"
    )
    op.execute("DELETE FROM automation_decisions WHERE decision_type = 'card_ai_deferred'")
    for table, fields in [
        (
            "question_clusters",
            [
                "generation_backlog",
                "generation_deferred_reason",
                "generation_retry_after",
                "generation_selected_revision",
                "generation_source_interview_id",
                "generation_admitted_at",
            ],
        ),
        (
            "card_automation_settings",
            [
                "card_ai_max_topics_per_interview",
                "card_ai_budget_per_interview_usd",
                "card_ai_daily_budget_usd",
                "card_ai_maintenance_budget_usd",
                "card_ai_min_priority_score",
            ],
        ),
        (
            "card_ai_charges",
            [
                "direction_id",
                "request_reserve_usd",
                "operation",
                "manual",
                "maintenance",
                "status",
                "settled_at",
                "reserve_expires_at",
                "pledge_request_id",
                "released_pledge_usd",
                "reason",
            ],
        ),
        ("ai_request_logs", ["interview_id", "cluster_id"]),
    ]:
        for name in fields:
            op.drop_column(table, name)
