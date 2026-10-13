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
from app.services import bill_payment_service, bill_service, dashboard_service
from app.services._query_filters import reporting_date_col
from app.services.credit_card_service import bill_period_for_month
from tests.settlement_fixtures import AUG, OCT, SEP, freeze_today, pay, seed_reference, set_mode, tx, unpay


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


# --- T32: projections ---------------------------------------------------------


async def _projected(session, ws, user, month):
    summary = await dashboard_service.get_summary(session, ws.id, user.id, month=month)
    rows = await dashboard_service.get_spending_by_category(session, ws.id, user.id, month=month)
    by_category = {
        row.category_name: (row.total, row.projected_total)
        for row in rows
        if row.projected_total
    }
    return summary.monthly_expenses, summary.projected_expenses, by_category


async def test_unpaid_bill_is_projected_in_its_due_month(
    monkeypatch, session, test_user, test_workspace, ref
):
    """AC 3: an unpaid bill is projected at its effective due date (2026-09-14), not realized."""
    freeze_today(monkeypatch, date(2026, 9, 10))

    assert await _projected(session, test_workspace, test_user, SEP) == (
        0.0,
        1000.0,
        {"Mercado": (0.0, 600.0), "Restaurantes": (0.0, 400.0)},
    )
    assert await _projected(session, test_workspace, test_user, AUG) == (0.0, 0.0, {})


async def test_overdue_bill_is_projected_in_the_current_month(
    monkeypatch, session, test_user, test_workspace, ref
):
    """AC 4: due 2026-09-14 and unpaid on 2026-10-12 → projected in October."""
    freeze_today(monkeypatch, date(2026, 10, 12))

    assert await _projected(session, test_workspace, test_user, OCT) == (
        0.0,
        1000.0,
        {"Mercado": (0.0, 600.0), "Restaurantes": (0.0, 400.0)},
    )
    assert await _projected(session, test_workspace, test_user, SEP) == (0.0, 0.0, {})


async def test_partially_paid_bill_stays_projected(session, test_user, test_workspace, ref):
    """AC 6: 500.00 on 2026-09-14 → September shows 0 realized and 1,000.00 projected."""
    await pay(session, ref, "500.00", date(2026, 9, 14))

    assert await _projected(session, test_workspace, test_user, SEP) == (
        0.0,
        1000.0,
        {"Mercado": (0.0, 600.0), "Restaurantes": (0.0, 400.0)},
    )


async def test_unlinked_completing_payment_moves_the_bill_back_to_projected(
    session, test_user, test_workspace, ref
):
    """AC 8: the purchases return to projected once the completing payment is unlinked."""
    await pay(session, ref, "500.00", date(2026, 9, 14))
    completing = await pay(session, ref, "500.00", date(2026, 9, 20))
    await unpay(session, ref, completing)

    expenses, projected, by_category = await _projected(session, test_workspace, test_user, SEP)
    assert (expenses, projected) == (500.0, 1500.0)
    assert by_category["Mercado"] == (0.0, 600.0)
    assert by_category["Restaurantes"] == (0.0, 400.0)


async def test_paid_bill_is_not_projected_twice(session, test_user, test_workspace, ref):
    """AC 2: once paid, the purchases are realized and leave the projection."""
    await pay(session, ref, "1000.00", date(2026, 9, 14))

    assert await _projected(session, test_workspace, test_user, SEP) == (
        1000.0,
        1000.0,
        {"Mercado": (600.0, 600.0), "Restaurantes": (400.0, 400.0)},
    )


# --- T33: open bills balance ----------------------------------------------------


async def _bill_with_purchase(session, ref, month, on, amount):
    bill, _ = await bill_service.get_or_create_bill(
        session, ref.card, bill_period_for_month(month, 5, 12)
    )
    session.add(tx(ref.card, on, amount, bill_id=bill.id))
    await bill_service.refresh_bills(session, [bill.id])
    await session.commit()
    return bill


async def test_open_bills_balance_sums_remaining_of_unpaid_bills(
    session, test_user, test_workspace, ref
):
    """AC 11: unpaid 2026-09 bill (500.00 left) + open 2026-10 bill (200.00); paid 2026-08 is out."""
    august = await _bill_with_purchase(session, ref, AUG, date(2026, 7, 20), "300.00")
    await _bill_with_purchase(session, ref, OCT, date(2026, 9, 10), "200.00")
    payment = tx(ref.checking, date(2026, 8, 14), "300.00")
    session.add(payment)
    await session.flush()
    await bill_payment_service.link_payment(session, test_workspace.id, payment.id, august.id)
    await session.commit()
    await pay(session, ref, "500.00", date(2026, 9, 14))

    summary = await dashboard_service.get_summary(
        session, test_workspace.id, test_user.id, month=SEP
    )
    assert summary.open_bills_remaining_primary == 700.0


@pytest.mark.parametrize("mode", ["cash", "accrual"])
async def test_open_bills_balance_is_left_to_the_accounts_in_other_modes(
    session, test_user, test_workspace, ref, mode
):
    await set_mode(session, mode)
    summary = await dashboard_service.get_summary(
        session, test_workspace.id, test_user.id, month=SEP
    )
    assert summary.open_bills_remaining_primary is None


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

    async def test_overdue_bill_trends_in_the_current_month(
        self, monkeypatch, session, test_user, test_workspace, ref
    ):
        """AC 4 on the monthly trend: the unpaid bill lands in October."""
        freeze_today(monkeypatch, date(2026, 10, 12))

        trend = await dashboard_service.get_monthly_trend(
            session, test_workspace.id, test_user.id, months=6
        )
        expenses = {point.month: point.expenses for point in trend}
        assert expenses.get("2026-10") == 1000.0
        assert expenses.get("2026-09", 0.0) == 0.0
