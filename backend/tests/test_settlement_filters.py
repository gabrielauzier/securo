"""BREP-01: `settlement` bucketing date and recognition filters (T30).

AC 2: a paid bill's purchases are bucketed on the date of the payment that
made it paid. AC 3: an unpaid bill's purchases are bucketed on its effective
due date and are not recognized. AC 4: an unpaid bill due in a past month is
bucketed today. AC 9: a card row without a bill keeps its purchase date.
"""

from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql

from app.models.transaction import Transaction
from app.services._query_filters import (
    is_bill_projected,
    is_recognized,
    reporting_date_col,
)
from tests.settlement_fixtures import freeze_today, pay, seed_reference, tx


async def _bucket(session, row_id):
    mode = "settlement"
    result = await session.execute(
        select(
            reporting_date_col(mode),
            is_recognized(mode),
            is_bill_projected(mode),
        ).where(Transaction.id == row_id)
    )
    when, recognized, projected = result.one()
    # SQLite returns the CASE result as text and booleans as integers.
    if isinstance(when, str):
        when = date.fromisoformat(when)
    return when, bool(recognized), bool(projected)


async def test_paid_bill_buckets_on_the_payment_date(
    monkeypatch, session, test_user, test_workspace
):
    freeze_today(monkeypatch, date(2026, 9, 25))
    ref = await seed_reference(session, test_user, test_workspace)
    await pay(session, ref, "1000.00", date(2026, 9, 14))

    assert await _bucket(session, ref.market_purchase.id) == (date(2026, 9, 14), True, False)


async def test_unpaid_bill_buckets_on_the_effective_due_date(
    monkeypatch, session, test_user, test_workspace
):
    freeze_today(monkeypatch, date(2026, 9, 25))
    ref = await seed_reference(session, test_user, test_workspace)
    await pay(session, ref, "500.00", date(2026, 9, 14))

    assert await _bucket(session, ref.market_purchase.id) == (date(2026, 9, 14), False, True)


async def test_unpaid_bill_due_in_a_past_month_buckets_today(
    monkeypatch, session, test_user, test_workspace
):
    freeze_today(monkeypatch, date(2026, 10, 12))
    ref = await seed_reference(session, test_user, test_workspace)

    assert await _bucket(session, ref.restaurant_purchase.id) == (date(2026, 10, 12), False, True)


async def test_unpaid_bill_due_earlier_this_month_keeps_its_due_date(
    monkeypatch, session, test_user, test_workspace
):
    freeze_today(monkeypatch, date(2026, 9, 30))
    ref = await seed_reference(session, test_user, test_workspace)

    assert await _bucket(session, ref.market_purchase.id) == (date(2026, 9, 14), False, True)


async def test_card_row_without_a_bill_keeps_its_purchase_date(
    monkeypatch, session, test_user, test_workspace
):
    freeze_today(monkeypatch, date(2026, 9, 25))
    ref = await seed_reference(session, test_user, test_workspace)
    loose = tx(ref.card, date(2026, 8, 3), "50.00", effective_date=date(2026, 8, 12))
    session.add(loose)
    await session.commit()

    assert await _bucket(session, loose.id) == (date(2026, 8, 3), True, False)


def _sql(expr) -> str:
    return str(expr.compile(dialect=postgresql.dialect()))


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("cash", func.coalesce(Transaction.effective_bill_date, Transaction.date)),
        ("accrual", func.coalesce(Transaction.effective_bill_date, Transaction.effective_date)),
    ],
)
def test_cash_and_accrual_expressions_are_unchanged(mode, expected):
    assert _sql(reporting_date_col(mode)) == _sql(expected)
    assert _sql(reporting_date_col(mode)) == (
        "coalesce(transactions.effective_bill_date, transactions."
        + ("effective_date" if mode == "accrual" else "date")
        + ")"
    )
    # Neither filter adds anything to a cash/accrual WHERE clause.
    query = select(Transaction.id).where(Transaction.amount > 0, is_recognized(mode))
    assert "WHERE transactions.amount >" in _sql(query)
    assert _sql(query).endswith("transactions.amount > %(amount_1)s")
    assert _sql(select(Transaction.id).where(is_bill_projected(mode))).endswith("WHERE false")


class TestOnPostgres:
    """The settlement expression compiles and runs on PostgreSQL."""

    @pytest_asyncio.fixture
    async def session(self, postgres_sessions):
        async with postgres_sessions() as session:
            yield session
            await session.rollback()

    @pytest.fixture
    def clean_db(self, postgres_sessions):
        """Each test starts in a fresh PostgreSQL schema."""

    async def test_expression_runs(self, monkeypatch, session, test_user, test_workspace):
        freeze_today(monkeypatch, date(2026, 10, 12))
        ref = await seed_reference(session, test_user, test_workspace)
        loose = tx(ref.card, date(2026, 8, 3), "50.00")
        session.add(loose)
        await session.commit()

        assert await _bucket(session, ref.market_purchase.id) == (date(2026, 10, 12), False, True)
        assert await _bucket(session, loose.id) == (date(2026, 8, 3), True, False)

        await pay(session, ref, "1000.00", date(2026, 9, 14))
        assert await _bucket(session, ref.market_purchase.id) == (date(2026, 9, 14), True, False)
