import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from httpx import AsyncClient
from sqlalchemy import select

from app.payments.models import (
    MentorReward,
    PaymentInstallment,
    StudentEmployment,
    StudentEmploymentStatus,
    StudentPaymentObligation,
)
from tests.conftest import SeededData, TestSession, auth, test_engine
from tests.test_go_obligations import paid_python_then_go


@pytest.mark.schema_change
async def test_migration_separates_existing_contracts_without_repricing(
    client: AsyncClient, seeded: SeededData
) -> None:
    original, _ = await paid_python_then_go(client, seeded)
    response = await client.put(
        f"/api/v1/mentor/students/{seeded.student_id}/employment",
        headers=auth(seeded.mentor_id),
        json={
            "company_name": "Existing Go employer",
            "start_date": datetime.now(UTC).date().isoformat(),
            "net_salary_rubles": 250_000,
            "contract_billing_confirmed": True,
        },
    )
    assert response.status_code == 200, response.text
    go_id = UUID(response.json()["employment"]["id"])
    async with TestSession() as session:
        go = await session.get(StudentEmployment, go_id)
        go.status = StudentEmploymentStatus.TERMINATED
        await session.flush()
        python = await session.get(StudentEmployment, UUID(original["employment"]["id"]))
        python.status = StudentEmploymentStatus.ACTIVE
        await session.commit()
        payments = [
            (row.id, row.amount_kopecks, row.salary_percent, row.status, row.paid_at)
            for row in await session.scalars(
                select(PaymentInstallment).order_by(PaymentInstallment.id)
            )
        ]
        rewards = [
            (row.id, row.mentor_id, row.amount_kopecks)
            for row in await session.scalars(select(MentorReward).order_by(MentorReward.id))
        ]
    path = Path(__file__).parents[1] / "migrations/versions/20261017_0102_payment_obligations.py"
    spec = importlib.util.spec_from_file_location("payment_obligation_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    async with test_engine.connect() as connection:

        def migrate(sync_connection):
            context = MigrationContext.configure(sync_connection)
            with context.begin_transaction(), Operations.context(context):
                migration.downgrade()
            with context.begin_transaction(), Operations.context(context):
                migration.upgrade()

        await connection.run_sync(migrate)
    async with TestSession() as session:
        obligations = list(await session.scalars(select(StudentPaymentObligation)))
        assert len(obligations) == 2
        legacy = next(row for row in obligations if row.contract_id is None)
        go_obligation = next(row for row in obligations if row.contract_id is not None)
        assert legacy.repayment_percent == 200
        assert go_obligation.repayment_percent == 100
        python = await session.get(StudentEmployment, UUID(original["employment"]["id"]))
        assert python.obligation_id == legacy.id
        assert python.status is StudentEmploymentStatus.COMPLETED
        assert python.ended_at is None
        assert (await session.get(StudentEmployment, go_id)).obligation_id == go_obligation.id
        actual = [
            (row.id, row.amount_kopecks, row.salary_percent, row.status, row.paid_at)
            for row in await session.scalars(
                select(PaymentInstallment).order_by(PaymentInstallment.id)
            )
        ]
        assert actual == payments
        actual_rewards = [
            (row.id, row.mentor_id, row.amount_kopecks)
            for row in await session.scalars(select(MentorReward).order_by(MentorReward.id))
        ]
        assert actual_rewards == rewards
