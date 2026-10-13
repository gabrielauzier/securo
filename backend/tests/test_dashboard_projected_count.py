"""ADJ-04: category spending counts the projected card purchases per category.

The reference 2026-09 bill (effective due 2026-09-14) holds 600.00 in Mercado
and 400.00 in Restaurantes; two more purchases in Compras are added to it.
"""

from datetime import date

import pytest
import pytest_asyncio

from app.models.category import Category
from app.services import bill_service, dashboard_service
from tests.settlement_fixtures import AUG, SEP, freeze_today, pay, seed_reference, set_mode, tx


@pytest_asyncio.fixture
async def ref(monkeypatch, session, test_user, test_workspace):
    freeze_today(monkeypatch, date(2026, 9, 10))
    ref = await seed_reference(session, test_user, test_workspace)
    compras = Category(
        user_id=test_user.id, workspace_id=test_workspace.id, name="Compras"
    )
    session.add(compras)
    await session.flush()
    due = date(2026, 9, 12)
    session.add_all([
        tx(ref.card, date(2026, 8, 12), "150.00", category_id=compras.id,
           bill_id=ref.bill.id, effective_date=due),
        tx(ref.card, date(2026, 8, 22), "50.00", category_id=compras.id,
           bill_id=ref.bill.id, effective_date=due),
    ])
    await bill_service.refresh_bills(session, [ref.bill.id])
    await session.commit()
    return ref


async def _counts(session, ws, user, month):
    rows = await dashboard_service.get_spending_by_category(session, ws.id, user.id, month=month)
    return {row.category_name: row.projected_count for row in rows}


async def test_unpaid_purchases_are_counted_per_category(
    session, test_user, test_workspace, ref
):
    await set_mode(session, "settlement")

    assert await _counts(session, test_workspace, test_user, SEP) == {
        "Compras": 2,
        "Mercado": 1,
        "Restaurantes": 1,
    }


async def test_paid_purchases_are_not_counted(
    monkeypatch, session, test_user, test_workspace, ref
):
    await set_mode(session, "settlement")
    await pay(session, ref, "1200.00", date(2026, 9, 14))
    freeze_today(monkeypatch, date(2026, 9, 25))

    assert await _counts(session, test_workspace, test_user, SEP) == {
        "Compras": 0,
        "Mercado": 0,
        "Restaurantes": 0,
    }


@pytest.mark.parametrize(("mode", "month"), [("cash", AUG), ("accrual", SEP)])
async def test_other_modes_report_zero(
    session, test_user, test_workspace, ref, mode, month
):
    await set_mode(session, mode)

    counts = await _counts(session, test_workspace, test_user, month)

    assert set(counts) == {"Compras", "Mercado", "Restaurantes"}
    assert set(counts.values()) == {0}


def test_projected_count_is_optional_and_defaults_to_zero():
    from app.schemas.dashboard import SpendingByCategory

    row = SpendingByCategory(
        category_id=None, category_name="Sem categoria", category_icon="circle-help",
        category_color="#6B7280", total=10.0, percentage=100.0,
    )

    assert row.projected_count == 0
