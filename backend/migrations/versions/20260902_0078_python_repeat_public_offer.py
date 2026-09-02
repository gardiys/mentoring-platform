"""Publish and audit acceptance of the repeat-Python public offer.

Revision ID: 20260902_0078
Revises: 20260831_0077
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260902_0078"
down_revision: str | None = "20260831_0077"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OFFER_ID = "e6916bee-8c78-4a89-9116-32ac846e56c3"
OFFER_REVISION = "02.09.2026"
OFFER_URL = "/legal/python-repeat-mentorship-offer-2026-09-02.pdf"
OFFER_SHA256 = "2f7a2c4e01609f37a9ebb04b7c93943d4f616cb2f55691ec409d41e9270bbd3f"
ACCEPTANCE_STATEMENT = (
    "Я ознакомился и полностью принимаю Публичную оферту на оказание "
    "информационно-консультационных услуг по программе повторного менторства по "
    "Python-разработке в редакции от 02.09.2026. Я понимаю, что стоимость услуг "
    "составляет 30 000 ₽ предоплаты и дополнительно 100% расчетного ежемесячного "
    "вознаграждения при новом трудоустройстве, выплачиваемые двумя равными платежами."
)


def upgrade() -> None:
    op.add_column(
        "python_repeat_product_offers",
        sa.Column("public_offer_revision", sa.String(32), nullable=True),
    )
    op.add_column(
        "python_repeat_product_offers",
        sa.Column("public_offer_published_at", sa.Date(), nullable=True),
    )
    op.add_column(
        "python_repeat_product_offers",
        sa.Column("public_offer_url", sa.String(500), nullable=True),
    )
    op.add_column(
        "python_repeat_product_offers",
        sa.Column("public_offer_sha256", sa.String(64), nullable=True),
    )
    op.add_column(
        "python_repeat_product_offers",
        sa.Column("acceptance_statement", sa.Text(), nullable=True),
    )
    op.add_column(
        "python_repeat_applications",
        sa.Column("acceptance_evidence", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "python_repeat_applications",
        sa.Column("contract_accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "python_repeat_applications",
        sa.Column("acceptance_payment_link_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "python_repeat_applications",
        sa.Column("acceptance_provider_operation_id", sa.String(255), nullable=True),
    )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE python_repeat_product_offers
            SET is_active = false,
                valid_until = COALESCE(valid_until, TIMESTAMPTZ '2026-09-02 00:00:00+00'),
                updated_at = now()
            WHERE is_active = true
            """
        )
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO python_repeat_product_offers (
                id, version, is_active, upfront_price_kopecks, success_fee_percent,
                success_fee_installments_count, mentor_fixed_accrual_kopecks,
                mentor_success_fee_share_percent, active_support_months,
                probation_support_days, included_mock_interviews, offer_valid_days,
                public_offer_revision, public_offer_published_at, public_offer_url,
                public_offer_sha256, acceptance_statement, valid_from, valid_until,
                created_at, updated_at
            )
            SELECT
                CAST(:offer_id AS uuid), 3, true, 3000000, 100, 2,
                mentor_fixed_accrual_kopecks, mentor_success_fee_share_percent,
                active_support_months, probation_support_days, included_mock_interviews,
                offer_valid_days, :offer_revision, DATE '2026-09-02', :offer_url,
                :offer_sha256, :acceptance_statement, TIMESTAMPTZ '2026-09-02 00:00:00+00',
                NULL, now(), now()
            FROM python_repeat_product_offers
            ORDER BY version DESC
            LIMIT 1
            """
        ),
        {
            "offer_id": OFFER_ID,
            "offer_revision": OFFER_REVISION,
            "offer_url": OFFER_URL,
            "offer_sha256": OFFER_SHA256,
            "acceptance_statement": ACCEPTANCE_STATEMENT,
        },
    )
    bind.execute(
        sa.text(
            """
            UPDATE python_repeat_applications application
            SET product_offer_id = product.id,
                terms_version = product.version,
                terms_snapshot = jsonb_build_object(
                    'product_code', 'PYTHON_REPEAT_MENTORSHIP',
                    'terms_version', product.version,
                    'upfront_price_kopecks', product.upfront_price_kopecks,
                    'currency', 'RUB',
                    'success_fee_percent', product.success_fee_percent,
                    'success_fee_installments_count', product.success_fee_installments_count,
                    'success_fee_installment_percent', 50,
                    'success_fee_first_due_months_after_employment', 1,
                    'success_fee_second_due_months_after_employment', 2,
                    'success_fee_minimum_kopecks', 0,
                    'pre_acceptance_employment_processes_excluded', true,
                    'mentor_fixed_accrual_kopecks', product.mentor_fixed_accrual_kopecks,
                    'mentor_success_fee_share_percent', product.mentor_success_fee_share_percent,
                    'active_support_months', product.active_support_months,
                    'probation_support_days', product.probation_support_days,
                    'included_mock_interviews', product.included_mock_interviews,
                    'offer_valid_days', product.offer_valid_days,
                    'public_offer_revision', product.public_offer_revision,
                    'public_offer_published_at',
                        to_char(product.public_offer_published_at, 'YYYY-MM-DD'),
                    'public_offer_url', product.public_offer_url,
                    'public_offer_sha256', product.public_offer_sha256,
                    'acceptance_statement', product.acceptance_statement,
                    'contract_acceptance_method', 'payment_crediting'
                ),
                offer_expires_at = now() + make_interval(days => product.offer_valid_days),
                updated_at = now()
            FROM python_repeat_product_offers product
            WHERE product.id = CAST(:offer_id AS uuid)
              AND application.status = 'approved'
            """
        ),
        {"offer_id": OFFER_ID},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE python_repeat_applications application
            SET product_offer_id = previous.id
            FROM python_repeat_product_offers previous
            WHERE application.product_offer_id = CAST(:offer_id AS uuid)
              AND previous.version = 2
            """
        ),
        {"offer_id": OFFER_ID},
    )
    bind.execute(
        sa.text("DELETE FROM python_repeat_product_offers WHERE id = CAST(:offer_id AS uuid)"),
        {"offer_id": OFFER_ID},
    )
    bind.execute(
        sa.text(
            """
            UPDATE python_repeat_product_offers
            SET is_active = true, valid_until = NULL, updated_at = now()
            WHERE version = 2
            """
        )
    )
    op.drop_column("python_repeat_applications", "acceptance_provider_operation_id")
    op.drop_column("python_repeat_applications", "acceptance_payment_link_id")
    op.drop_column("python_repeat_applications", "contract_accepted_at")
    op.drop_column("python_repeat_applications", "acceptance_evidence")
    op.drop_column("python_repeat_product_offers", "acceptance_statement")
    op.drop_column("python_repeat_product_offers", "public_offer_sha256")
    op.drop_column("python_repeat_product_offers", "public_offer_url")
    op.drop_column("python_repeat_product_offers", "public_offer_published_at")
    op.drop_column("python_repeat_product_offers", "public_offer_revision")
