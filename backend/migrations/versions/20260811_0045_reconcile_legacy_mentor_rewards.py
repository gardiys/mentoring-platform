"""Limit legacy mentor rewards to student payments already received.

Revision ID: 20260811_0045
Revises: 20260811_0044
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from uuid import UUID, uuid5

import sqlalchemy as sa
from alembic import op

revision: str = "20260811_0045"
down_revision: str | None = "20260811_0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PAYOUT_FILES = (
    DATA_DIR / "mentor_payouts_roman_mamin.csv",
    DATA_DIR / "mentor_payouts_daniil_diakonov.csv",
    DATA_DIR / "mentor_payouts_konstantin_oleshko.csv",
    DATA_DIR / "mentor_payouts_oleg_chernikov.csv",
    DATA_DIR / "mentor_payouts_mikhail_zubko.csv",
    DATA_DIR / "mentor_payouts_oleg_bogomolov.csv",
    DATA_DIR / "mentor_payouts_ilya_bochkarev.csv",
)
MENTOR_PAYOUT_IMPORT_NAMESPACE = UUID("337a3916-49fb-48c1-9563-c86120636998")
EXPECTED_IMPORTED_REWARDS = 186
EXPECTED_EMPLOYMENT_REWARDS = 113


def _identity(kind: str, value: str) -> UUID:
    return uuid5(MENTOR_PAYOUT_IMPORT_NAMESPACE, f"{kind}:{value}")


def _imported_reward_ids() -> list[UUID]:
    reward_ids: list[UUID] = []
    for path in PAYOUT_FILES:
        with path.open(encoding="utf-8-sig", newline="") as source:
            for row_number, row in enumerate(csv.DictReader(source), start=2):
                if row["Имя"].strip():
                    reward_ids.append(_identity("reward", f"{path.name}:{row_number}"))
    return reward_ids


def _round_kopecks(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _reserved_kopecks(connection: sa.Connection, reward_id: UUID) -> int:
    return int(
        connection.execute(
            sa.text(
                """
                SELECT COALESCE(sum(allocation.amount_kopecks), 0)
                FROM mentor_payout_allocations AS allocation
                JOIN mentor_payouts AS payout ON payout.id = allocation.payout_id
                WHERE allocation.reward_id = :reward_id
                  AND payout.status = 'requested'
                """
            ),
            {"reward_id": reward_id},
        ).scalar_one()
    )


def _cancel_unbacked_requests(
    connection: sa.Connection,
    corrected_amounts: dict[UUID, int],
    paid_amounts: dict[UUID, int],
) -> None:
    requested_rows = list(
        connection.execute(
            sa.text(
                """
                SELECT allocation.payout_id, allocation.reward_id,
                       allocation.amount_kopecks
                FROM mentor_payout_allocations AS allocation
                JOIN mentor_payouts AS payout ON payout.id = allocation.payout_id
                WHERE allocation.reward_id IN :reward_ids
                  AND payout.status = 'requested'
                """
            ).bindparams(sa.bindparam("reward_ids", expanding=True)),
            {"reward_ids": list(corrected_amounts)},
        ).mappings()
    )
    reserved_by_reward: dict[UUID, int] = {}
    for row in requested_rows:
        reserved_by_reward[row["reward_id"]] = (
            reserved_by_reward.get(row["reward_id"], 0) + row["amount_kopecks"]
        )
    unbacked_reward_ids = {
        reward_id
        for reward_id, reserved_kopecks in reserved_by_reward.items()
        if paid_amounts[reward_id] + reserved_kopecks > corrected_amounts[reward_id]
    }
    if not unbacked_reward_ids:
        return

    invalid_payout_ids = {
        row["payout_id"]
        for row in requested_rows
        if row["reward_id"] in unbacked_reward_ids
    }
    connection.execute(
        sa.text(
            """
            UPDATE mentor_payouts
            SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP
            WHERE id IN :payout_ids AND status = 'requested'
            """
        ).bindparams(sa.bindparam("payout_ids", expanding=True)),
        {"payout_ids": list(invalid_payout_ids)},
    )


def _accrued_from_paid_installments(
    connection: sa.Connection,
    *,
    student_id: UUID,
    salary_kopecks: int,
    reward_percent: Decimal,
) -> int:
    """Return only the mentor share backed by confirmed student payments.

    A historical reward row describes the mentor's share of one salary. The
    matching employment describes how many salary-percent points the student
    owes. Thus a paid 25% installment for a 200% Python contract unlocks
    ``25% * mentor_percent / 200%``: at a 60% mentor rate this is 7.5% of the
    salary, not the whole 60% entitlement.
    """

    rows = connection.execute(
        sa.text(
            """
            SELECT employment.repayment_percent,
                   COALESCE(sum(installment.amount_kopecks) FILTER (
                       WHERE installment.status = 'paid'
                   ), 0) AS paid_kopecks
            FROM student_employments AS employment
            LEFT JOIN payment_installments AS installment
                ON installment.employment_id = employment.id
            WHERE employment.student_id = :student_id
              AND employment.net_salary_kopecks = :salary_kopecks
            GROUP BY employment.id, employment.repayment_percent
            """
        ),
        {"student_id": student_id, "salary_kopecks": salary_kopecks},
    ).mappings()
    return sum(
        _round_kopecks(
            Decimal(row["paid_kopecks"])
            * reward_percent
            / Decimal(row["repayment_percent"])
        )
        for row in rows
        if row["paid_kopecks"] > 0
    )


def upgrade() -> None:
    connection = op.get_bind()
    reward_ids = _imported_reward_ids()
    imported_rewards = list(
        connection.execute(
            sa.text(
                """
                SELECT id, student_id, kind, reward_percent, basis_kopecks,
                       amount_kopecks, paid_kopecks
                FROM mentor_rewards
                WHERE id IN :ids
                ORDER BY id
                """
            ).bindparams(sa.bindparam("ids", expanding=True)),
            {"ids": reward_ids},
        ).mappings()
    )
    if len(imported_rewards) != EXPECTED_IMPORTED_REWARDS:
        raise RuntimeError(
            "Expected 186 imported mentor rewards before reconciliation, "
            f"got {len(imported_rewards)}"
        )

    employment_rewards = [
        reward for reward in imported_rewards if reward["kind"] == "employment_payment"
    ]
    if len(employment_rewards) != EXPECTED_EMPLOYMENT_REWARDS:
        raise RuntimeError(
            "Expected 113 imported employment rewards before reconciliation, "
            f"got {len(employment_rewards)}"
        )

    corrected_amounts: dict[UUID, int] = {}
    paid_amounts: dict[UUID, int] = {}
    for reward in employment_rewards:
        reward_percent = Decimal(reward["reward_percent"])
        accrued_kopecks = _accrued_from_paid_installments(
            connection,
            student_id=reward["student_id"],
            salary_kopecks=reward["basis_kopecks"],
            reward_percent=reward_percent,
        )
        # Never accrue more than the full historical entitlement. Already paid
        # amounts remain immutable facts; open payout requests also stay valid.
        backed_kopecks = min(accrued_kopecks, reward["amount_kopecks"])
        corrected_amounts[reward["id"]] = max(backed_kopecks, reward["paid_kopecks"])
        paid_amounts[reward["id"]] = reward["paid_kopecks"]

    # A request created before this revision may have reserved the old,
    # unearned future entitlement. Such a request is not a completed payment
    # and is cancelled so it cannot be approved after reconciliation.
    _cancel_unbacked_requests(connection, corrected_amounts, paid_amounts)

    for reward in employment_rewards:
        corrected_kopecks = corrected_amounts[reward["id"]]
        protected_kopecks = reward["paid_kopecks"] + _reserved_kopecks(connection, reward["id"])
        if protected_kopecks > corrected_kopecks:
            raise RuntimeError("A mentor payout request still exceeds its earned reward")
        connection.execute(
            sa.text(
                """
                UPDATE mentor_rewards
                SET amount_kopecks = :amount_kopecks,
                    paid_at = CASE
                        WHEN paid_kopecks > 0 AND paid_kopecks = :amount_kopecks
                            THEN COALESCE(paid_at, updated_at)
                        ELSE NULL
                    END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :reward_id
                """
            ),
            {"reward_id": reward["id"], "amount_kopecks": corrected_kopecks},
        )


def downgrade() -> None:
    connection = op.get_bind()
    reward_ids = _imported_reward_ids()
    rewards = list(
        connection.execute(
            sa.text(
                """
                SELECT id, basis_kopecks, reward_percent, paid_kopecks
                FROM mentor_rewards
                WHERE id IN :ids AND kind = 'employment_payment'
                """
            ).bindparams(sa.bindparam("ids", expanding=True)),
            {"ids": reward_ids},
        ).mappings()
    )
    for reward in rewards:
        entitlement_kopecks = _round_kopecks(
            Decimal(reward["basis_kopecks"])
            * Decimal(reward["reward_percent"])
            / Decimal(100)
        )
        connection.execute(
            sa.text(
                """
                UPDATE mentor_rewards
                SET amount_kopecks = :amount_kopecks,
                    paid_at = CASE
                        WHEN paid_kopecks = :amount_kopecks AND paid_kopecks > 0
                            THEN COALESCE(paid_at, updated_at)
                        ELSE NULL
                    END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :reward_id
                """
            ),
            {
                "reward_id": reward["id"],
                "amount_kopecks": max(entitlement_kopecks, reward["paid_kopecks"]),
            },
        )
