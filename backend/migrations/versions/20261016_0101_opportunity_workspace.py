"""Administrative notes and opportunity history, without backfilling events."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261016_0101"
down_revision = "20261016_0100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("consultation_requests", "go_transition_applications"):
        op.add_column(table, sa.Column("internal_note", sa.Text(), nullable=True))
    for table, column, target in [
        ("consultation_request_history", "consultation_request_id", "consultation_requests"),
        ("go_transition_application_history", "application_id", "go_transition_applications"),
    ]:
        op.create_table(
            table,
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                column,
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey(f"{target}.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("old_status", sa.String(32), nullable=True),
            sa.Column("new_status", sa.String(32), nullable=False),
            sa.Column(
                "actor_user_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("snapshot", postgresql.JSONB(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
    op.create_index(
        "ix_consultation_history_request_created",
        "consultation_request_history",
        ["consultation_request_id", "created_at"],
    )
    op.create_index(
        "ix_go_transition_history_application_created",
        "go_transition_application_history",
        ["application_id", "created_at"],
    )
    op.create_index("ix_consultation_requests_mentor", "consultation_requests", ["mentor_id"])
    op.create_index(
        "ix_consultation_requests_status_scheduled",
        "consultation_requests",
        ["status", "scheduled_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_consultation_requests_status_scheduled", "consultation_requests")
    op.drop_index("ix_consultation_requests_mentor", "consultation_requests")
    op.drop_table("go_transition_application_history")
    op.drop_table("consultation_request_history")
    for table in ("consultation_requests", "go_transition_applications"):
        op.drop_column(table, "internal_note")
