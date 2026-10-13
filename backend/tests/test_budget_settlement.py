"""BREP-01 on budgets in the `settlement` accounting mode (T35).

The Mercado budget's September actual is the reference bill's 600.00 only
once the bill is paid; until then the 600.00 is projected (BREP AC 3, 5).
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest_asyncio

from app.models.budget import Budget
from app.services import budget_service
from tests.settlement_fixtures import AUG, SEP, freeze_today, pay, seed_reference, set_mode


@pytest_asyncio.fixture
async def ref(monkeypatch, session, test_user, test_workspace):
    freeze_today(monkeypatch, date(2026, 9, 25))
    await set_mode(session, "settlement")
    ref = await seed_reference(session, test_user, test_workspace)
    session.add(Budget(
        id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
        category_id=ref.market.id, amount=Decimal("800"), currency="BRL", month=SEP,
    ))
    await session.commit()
    return ref


async def _mercado(session, ws, user, ref, month):
    rows = await budget_service.get_budget_vs_actual(session, ws.id, user.id, month)
    row = next((r for r in rows if r.category_id == ref.market.id), None)
    if row is None:
        return None
    return float(row.actual_amount), float(row.projected_amount)


async def test_mercado_actual_counts_only_after_the_bill_is_paid(
    session, test_user, test_workspace, ref
):
    assert await _mercado(session, test_workspace, test_user, ref, SEP) == (0.0, 600.0)

    await pay(session, ref, "1000.00", date(2026, 9, 14))

    assert await _mercado(session, test_workspace, test_user, ref, SEP) == (600.0, 600.0)


async def test_partially_paid_bill_keeps_mercado_projected(
    session, test_user, test_workspace, ref
):
    await pay(session, ref, "500.00", date(2026, 9, 14))

    assert await _mercado(session, test_workspace, test_user, ref, SEP) == (0.0, 600.0)


async def test_august_budget_never_sees_the_purchases(session, test_user, test_workspace, ref):
    await pay(session, ref, "1000.00", date(2026, 9, 14))

    assert await _mercado(session, test_workspace, test_user, ref, AUG) in (None, (0.0, 0.0))
