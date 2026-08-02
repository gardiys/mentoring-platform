"""Classify AI interview questions for cost-aware model routing."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260802_0029"
down_revision: str | None = "20260802_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    question_kind = postgresql.ENUM(
        "technical",
        "hr",
        "organizational",
        "other",
        name="intelligence_question_kind",
    )
    question_kind.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "intelligence_questions",
        sa.Column(
            "question_kind",
            question_kind,
            server_default="other",
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE intelligence_questions
        SET question_kind = CASE
            WHEN category IN (
                'python', 'go', 'databases', 'backend', 'async', 'architecture',
                'system_design', 'algorithms', 'devops', 'testing', 'processes'
            ) THEN 'technical'::intelligence_question_kind
            WHEN category IN (
                'hr', 'behavioral', 'culture', 'career', 'motivation', 'experience'
            ) THEN 'hr'::intelligence_question_kind
            WHEN category IN (
                'organizational', 'recruiting', 'salary', 'availability', 'relocation'
            ) THEN 'organizational'::intelligence_question_kind
            ELSE 'other'::intelligence_question_kind
        END
        """
    )


def downgrade() -> None:
    op.drop_column("intelligence_questions", "question_kind")
    postgresql.ENUM(name="intelligence_question_kind").drop(op.get_bind(), checkfirst=True)
