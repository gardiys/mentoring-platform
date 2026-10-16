"""Separate legacy repayments from each accepted Go contract."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261017_0102"
down_revision = "20261016_0101"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE student_employment_status ADD VALUE IF NOT EXISTS 'completed'")
    op.create_table(
        "student_payment_obligations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "student_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "contract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contract_acceptances.id", ondelete="RESTRICT"),
            unique=True,
        ),
        sa.Column(
            "track_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learning_tracks.id", ondelete="RESTRICT"),
        ),
        sa.Column("repayment_percent", sa.Numeric(6, 2), nullable=False),
        sa.Column("terms_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "repayment_percent > 0 AND repayment_percent <= 1000",
            name=op.f("ck_student_payment_obligations_percent_range"),
        ),
    )
    op.create_index(
        "uq_student_payment_obligation_legacy",
        "student_payment_obligations",
        ["student_id"],
        unique=True,
        postgresql_where=sa.text("contract_id IS NULL"),
    )
    op.add_column("student_employments", sa.Column("obligation_id", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key(
        "fk_student_employments_obligation",
        "student_employments",
        "student_payment_obligations",
        ["obligation_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_student_employments_obligation_id", "student_employments", ["obligation_id"]
    )
    op.execute("""
        INSERT INTO student_payment_obligations
            (id, student_id, contract_id, track_id, repayment_percent, terms_snapshot)
        SELECT gen_random_uuid(), c.user_id, c.id, g.track_id,
               (c.snapshot->'financial_terms'->>'success_fee_percent')::numeric,
               c.snapshot->'financial_terms'
        FROM contract_acceptances c
        JOIN legal_checkouts l ON l.id = c.checkout_session_id
        JOIN go_transition_enrollments g ON g.application_id = l.application_id
        WHERE c.product_code = 'python_to_go_transition'
    """)
    op.execute("""
        UPDATE student_employments e SET obligation_id = (
            SELECT o.id FROM student_payment_obligations o
            JOIN contract_acceptances c ON c.id = o.contract_id
            WHERE o.student_id = e.student_id AND o.track_id = e.track_id
                AND c.accepted_at <= e.created_at
            ORDER BY c.accepted_at DESC, c.id DESC LIMIT 1
        )
        WHERE e.track_id IS NOT NULL
    """)
    op.execute("""
        INSERT INTO student_payment_obligations
            (id, student_id, repayment_percent, terms_snapshot)
        SELECT gen_random_uuid(), student_id, repayment_percent, '{}'::jsonb
        FROM (SELECT DISTINCT ON (student_id) student_id, repayment_percent
              FROM student_employments WHERE obligation_id IS NULL
              ORDER BY student_id, created_at, id) original
    """)
    op.execute("""
        UPDATE student_employments e SET obligation_id = o.id
        FROM student_payment_obligations o
        WHERE e.obligation_id IS NULL AND o.contract_id IS NULL AND o.student_id = e.student_id
    """)
    op.execute("""
        UPDATE student_employments e SET status = 'completed', closed_at = now(),
            case_status = CASE WHEN case_status IS NULL THEN NULL
                               ELSE 'closed'::employment_case_status END
        WHERE e.status = 'active'
          AND EXISTS (SELECT 1 FROM student_payment_obligations o
                      JOIN contract_acceptances c ON c.id = o.contract_id
                      WHERE o.student_id = e.student_id AND o.id <> e.obligation_id
                        AND c.status = 'active' AND c.accepted_at >= e.created_at)
          AND NOT EXISTS (SELECT 1 FROM payment_installments p WHERE p.employment_id = e.id
                          AND p.status IN ('scheduled', 'pending'))
          AND (SELECT coalesce(sum(p.salary_percent), 0) FROM payment_installments p
               WHERE p.employment_id = e.id AND p.status = 'paid') >= e.repayment_percent
    """)


def downgrade() -> None:
    op.execute("UPDATE student_employments SET status = 'terminated' WHERE status = 'completed'")
    op.drop_index("ix_student_employments_obligation_id", "student_employments")
    op.drop_constraint(
        "fk_student_employments_obligation", "student_employments", type_="foreignkey"
    )
    op.drop_column("student_employments", "obligation_id")
    op.drop_table("student_payment_obligations")
