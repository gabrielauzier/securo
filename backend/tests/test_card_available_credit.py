"""ADJ-05: the account detail shows the same owed amount as the accounts list.

A card with a 5,000.00 limit and 1,000.00 owed on 2026-09-01 (its balance
date) gets a 300.00 purchase dated before that date, which the balance floor
leaves out (AD-001/AD-002), and a 200.00 purchase after it. The amount owed
is 1,200.00, so available credit is 3,800.00.
"""

import uuid
from datetime import date
from decimal import Decimal

from httpx import AsyncClient

from app.models.transaction import Transaction
from tests.settlement_fixtures import freeze_today


async def _card_with_history(client, auth_headers, session, user, workspace) -> str:
    created = await client.post(
        "/api/accounts", headers=auth_headers,
        json={
            "name": "Cartão de Crédito Nubank", "type": "credit_card", "currency": "BRL",
            "balance": "1000.00", "balance_date": "2026-09-01", "credit_limit": "5000.00",
            "statement_close_day": 5, "payment_due_day": 12,
        },
    )
    assert created.status_code == 201, created.text
    card_id = created.json()["id"]
    for on, amount in ((date(2026, 8, 20), "300.00"), (date(2026, 9, 10), "200.00")):
        session.add(Transaction(
            id=uuid.uuid4(), user_id=user.id, workspace_id=workspace.id,
            account_id=uuid.UUID(card_id), description="Compra", amount=Decimal(amount),
            currency="BRL", date=on, effective_date=on, type="debit", source="manual",
            status="posted",
        ))
    await session.commit()
    return card_id


async def test_detail_and_list_show_the_same_owed_amount_and_available_credit(
    monkeypatch, client: AsyncClient, auth_headers, session, test_user, test_workspace
):
    freeze_today(monkeypatch, date(2026, 9, 25))
    card_id = await _card_with_history(client, auth_headers, session, test_user, test_workspace)

    listed = await client.get("/api/accounts", headers=auth_headers)
    assert listed.status_code == 200
    in_list = next(a for a in listed.json() if a["id"] == card_id)
    detail = await client.get(f"/api/accounts/{card_id}", headers=auth_headers)
    assert detail.status_code == 200

    assert in_list["current_balance"] == -1200.0
    assert in_list["available_credit"] == 3800.0
    assert detail.json()["current_balance"] == -1200.0
    assert detail.json()["available_credit"] == 3800.0
