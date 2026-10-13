"""BREP-01 on the dashboard in the `settlement` accounting mode.

Reference bill (BREP AC 5): 1,000.00 on the 2026-09 bill of a card with close
day 5 and due day 12, 600.00 in Mercado and 400.00 in Restaurantes, both
bought in August.
"""

from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.transaction import Transaction
from app.services import dashboard_service
from app.services._query_filters import reporting_date_col
from tests.settlement_fixtures import AUG, SEP, freeze_today, pay, seed_reference, set_mode, unpay


@pytest_asyncio.fixture
async def ref(monkeypatch, session, test_user, test_workspace):
    freeze_today(monkeypatch, date(2026, 9, 25))
    await set_mode(session, "settlement")
    return await seed_reference(session, test_user, test_workspace)


async def _expenses(session, ws, user, month):
    summary = await dashboard_service.get_summary(session, ws.id, user.id, month=month)
    return summary.monthly_expenses


async def _by_category(session, ws, user, month):
    rows = await dashboard_service.get_spending_by_category(session, ws.id, user.id, month=month)
    return {row.category_name: row.total for row in rows if row.total}


async def _recognized_on(session, row_id):
    value = await session.scalar(
        select(reporting_date_col("settlement")).where(Transaction.id == row_id)
    )
    return date.fromisoformat(value) if isinstance(value, str) else value


# --- T31: realized totals ------------------------------------------------------


async def test_paid_bill_counts_in_the_month_it_was_paid(
    session, test_user, test_workspace, ref
):
    """AC 5: paid on 2026-09-14 → September shows 600.00 and 400.00, August neither."""
    await pay(session, ref, "1000.00", date(2026, 9, 14))

    assert await _expenses(session, test_workspace, test_user, SEP) == 1000.0
    assert await _by_category(session, test_workspace, test_user, SEP) == {
        "Mercado": 600.0,
        "Restaurantes": 400.0,
    }
    assert await _expenses(session, test_workspace, test_user, AUG) == 0.0
    assert await _by_category(session, test_workspace, test_user, AUG) == {}


async def test_second_partial_payment_recognizes_the_bill(
    session, test_user, test_workspace, ref
):
    """AC 7: 500.00 on 2026-09-14, then 500.00 on 2026-09-20 → realized on 2026-09-20."""
    await pay(session, ref, "500.00", date(2026, 9, 14))
    assert await _expenses(session, test_workspace, test_user, SEP) == 0.0
    assert await _by_category(session, test_workspace, test_user, SEP) == {}

    await pay(session, ref, "500.00", date(2026, 9, 20))
    assert await _expenses(session, test_workspace, test_user, SEP) == 1000.0
    assert await _by_category(session, test_workspace, test_user, SEP) == {
        "Mercado": 600.0,
        "Restaurantes": 400.0,
    }
    assert await _recognized_on(session, ref.market_purchase.id) == date(2026, 9, 20)
    assert await _recognized_on(session, ref.restaurant_purchase.id) == date(2026, 9, 20)


async def test_unlinking_the_completing_payment_unrecognizes_the_bill(
    session, test_user, test_workspace, ref
):
    """AC 8: unlinking the payment that completed the bill moves it out of realized."""
    await pay(session, ref, "500.00", date(2026, 9, 14))
    completing = await pay(session, ref, "500.00", date(2026, 9, 20))
    assert await _expenses(session, test_workspace, test_user, SEP) == 1000.0

    await unpay(session, ref, completing)

    # Only the unlinked 500.00 debit is left, now an ordinary expense.
    assert await _expenses(session, test_workspace, test_user, SEP) == 500.0
    assert await _by_category(session, test_workspace, test_user, SEP) == {"Sem categoria": 500.0}


class TestTrendOnPostgres:
    """The monthly trend groups by `to_char`, so it runs on PostgreSQL."""

    @pytest_asyncio.fixture
    async def session(self, postgres_sessions):
        async with postgres_sessions() as session:
            yield session
            await session.rollback()

    @pytest.fixture
    def clean_db(self, postgres_sessions):
        """Each test starts in a fresh PostgreSQL schema."""

    async def test_paid_bill_trends_in_the_month_it_was_paid(
        self, session, test_user, test_workspace, ref
    ):
        """AC 5 on the monthly trend: September carries the bill, August does not."""
        await pay(session, ref, "1000.00", date(2026, 9, 14))

        trend = await dashboard_service.get_monthly_trend(
            session, test_workspace.id, test_user.id, months=6
        )
        expenses = {point.month: point.expenses for point in trend}
        assert expenses.get("2026-09") == 1000.0
        assert expenses.get("2026-08", 0.0) == 0.0
