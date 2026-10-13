"""BREP-01 / BREP-02: list rows carry the bucketing date of the active mode (T37).

The drill-down reads `GET /transactions?user_pnl_only=true&from=&to=`. In
`settlement` that list holds a paid bill's purchases at the payment date and
an unpaid bill's purchases flagged `is_bill_projected` at the bill's
effective due date (today when overdue). `cash` and the bill view keep their
rows.
"""

from datetime import date

import pytest_asyncio
from httpx import AsyncClient

from tests.settlement_fixtures import freeze_today, pay, seed_reference, set_mode


@pytest_asyncio.fixture
async def ref(monkeypatch, session, test_user, test_workspace):
    freeze_today(monkeypatch, date(2026, 9, 25))
    return await seed_reference(session, test_user, test_workspace)


async def _pnl_rows(client, headers, start, end):
    resp = await client.get(
        "/api/transactions",
        headers=headers,
        params={"user_pnl_only": "true", "from": start, "to": end},
    )
    assert resp.status_code == 200
    return {
        row["id"]: (row["reporting_date"], row["is_bill_projected"])
        for row in resp.json()["items"]
    }


async def test_settlement_lists_paid_purchases_at_the_payment_date(
    client: AsyncClient, auth_headers, session, ref
):
    await set_mode(session, "settlement")
    payment = await pay(session, ref, "1000.00", date(2026, 9, 14))

    september = await _pnl_rows(client, auth_headers, "2026-09-01", "2026-09-30")

    assert september == {
        str(ref.market_purchase.id): ("2026-09-14", False),
        str(ref.restaurant_purchase.id): ("2026-09-14", False),
    }
    assert str(payment.id) not in september
    assert await _pnl_rows(client, auth_headers, "2026-08-01", "2026-08-31") == {}


async def test_settlement_lists_unpaid_purchases_as_projected(
    client: AsyncClient, auth_headers, session, ref
):
    await set_mode(session, "settlement")
    await pay(session, ref, "500.00", date(2026, 9, 14))

    september = await _pnl_rows(client, auth_headers, "2026-09-01", "2026-09-30")

    assert september == {
        str(ref.market_purchase.id): ("2026-09-14", True),
        str(ref.restaurant_purchase.id): ("2026-09-14", True),
    }


async def test_settlement_lists_overdue_purchases_today(
    monkeypatch, client: AsyncClient, auth_headers, session, ref
):
    freeze_today(monkeypatch, date(2026, 10, 12))
    await set_mode(session, "settlement")

    october = await _pnl_rows(client, auth_headers, "2026-10-01", "2026-10-31")

    assert october == {
        str(ref.market_purchase.id): ("2026-10-12", True),
        str(ref.restaurant_purchase.id): ("2026-10-12", True),
    }
    assert await _pnl_rows(client, auth_headers, "2026-09-01", "2026-09-30") == {}


async def test_cash_list_keeps_the_purchase_date(
    client: AsyncClient, auth_headers, session, ref
):
    await set_mode(session, "cash")
    await pay(session, ref, "1000.00", date(2026, 9, 14))

    assert await _pnl_rows(client, auth_headers, "2026-08-01", "2026-08-31") == {
        str(ref.market_purchase.id): ("2026-08-10", False),
        str(ref.restaurant_purchase.id): ("2026-08-20", False),
    }
    assert await _pnl_rows(client, auth_headers, "2026-09-01", "2026-09-30") == {}


async def test_bill_view_is_the_same_in_every_mode(
    client: AsyncClient, auth_headers, session, ref
):
    params = {"bill_id": str(ref.bill.id), "from": "2026-08-05", "to": "2026-09-04"}
    listed = {}
    for mode in ("cash", "settlement"):
        await set_mode(session, mode)
        resp = await client.get("/api/transactions", headers=auth_headers, params=params)
        assert resp.status_code == 200
        listed[mode] = [row["id"] for row in resp.json()["items"]]

    assert listed["settlement"] == listed["cash"]
    assert listed["cash"] == [str(ref.restaurant_purchase.id), str(ref.market_purchase.id)]
