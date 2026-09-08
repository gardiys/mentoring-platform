"""Persist paid request metadata and resumable interview AI results."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260908_0084"
down_revision = "20260908_0083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_request_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("operation", sa.String(60), nullable=False),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("service_tier", sa.String(30), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("recovery", sa.Boolean(), nullable=False),
        sa.Column("provider_request_id", sa.String(500)),
        sa.Column("response_id", sa.String(500)),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("cached_input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("reasoning_tokens", sa.Integer()),
        sa.Column("estimated_cost_usd", sa.Numeric(16, 10)),
        sa.Column("pricing_version", sa.String(80)),
        sa.Column("error_code", sa.String(100)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_ai_request_logs_created_operation", "ai_request_logs", ["created_at", "operation"]
    )
    op.create_table(
        "intelligence_ai_checkpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "interview_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("intelligence_interviews.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("operation", sa.String(40), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("output", postgresql.JSONB(), nullable=False),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "interview_id", "operation", "input_hash", name="uq_ai_checkpoint_input"
        ),
    )
    op.create_index(
        "ix_intelligence_ai_checkpoints_interview_id",
        "intelligence_ai_checkpoints",
        ["interview_id"],
    )


def downgrade() -> None:
    op.drop_table("intelligence_ai_checkpoints")
    op.drop_table("ai_request_logs")
