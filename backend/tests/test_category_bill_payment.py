"""BPAY-03: categories flagged as bill payments, through /categories, keep bill totals current."""

import uuid
from datetime import date
from decimal import Decimal

from httpx import AsyncClient

from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction
from app.services import bill_service
from app.services.credit_card_service import bill_period_for_month


async def test_flag_is_readable_and_writable(client: AsyncClient, auth_headers):
    created = await client.post(
        "/api/categories", headers=auth_headers,
        json={"name": "Pagamento de fatura", "is_bill_payment": True},
    )
    assert created.status_code == 201, created.text
    assert created.json()["is_bill_payment"] is True
    category_id = created.json()["id"]

    listed = await client.get("/api/categories", headers=auth_headers)
    row = next(c for c in listed.json() if c["id"] == category_id)
    assert row["is_bill_payment"] is True

    patched = await client.patch(
        f"/api/categories/{category_id}", headers=auth_headers, json={"is_bill_payment": False}
    )
    assert patched.status_code == 200
    assert patched.json()["is_bill_payment"] is False

    plain = await client.post("/api/categories", headers=auth_headers, json={"name": "Mercado"})
    assert plain.json()["is_bill_payment"] is False


async def _bill_with_rows(session, user, workspace, payment_category, market):
    card = Account(
        id=uuid.uuid4(), user_id=user.id, workspace_id=workspace.id,
        name="Cartão de Crédito Nubank", type="credit_card", currency="BRL",
        statement_close_day=5, payment_due_day=12,
    )
    session.add(card)
    await session.flush()
    bill, _ = await bill_service.get_or_create_bill(
        session, card, bill_period_for_month(date(2026, 9, 1), 5, 12)
    )

    def row(amount, type_, category):
        return Transaction(
            id=uuid.uuid4(), user_id=user.id, workspace_id=workspace.id, account_id=card.id,
            description="row", amount=Decimal(amount), currency="BRL", date=date(2026, 8, 20),
            effective_date=date(2026, 8, 20), type=type_, source="manual",
            category_id=category.id, bill_id=bill.id,
        )

    session.add_all([
        row("1000.00", "debit", market),
        # An unpaired "Pagamento recebido" credit on the card.
        row("200.00", "credit", payment_category),
    ])
    await bill_service.refresh_bills(session, [bill.id])
    await session.commit()
    return bill


async def test_toggling_the_flag_refreshes_bill_totals(
    client: AsyncClient, auth_headers, session, test_user, test_workspace
):
    payment_category = Category(id=uuid.uuid4(), user_id=test_user.id, name="Pagamento recebido")
    market = Category(id=uuid.uuid4(), user_id=test_user.id, name="Mercado")
    session.add_all([payment_category, market])
    await session.commit()
    bill = await _bill_with_rows(session, test_user, test_workspace, payment_category, market)
    assert bill.computed_total == Decimal("800.00")

    resp = await client.patch(
        f"/api/categories/{payment_category.id}", headers=auth_headers,
        json={"is_bill_payment": True},
    )
    assert resp.status_code == 200
    await session.refresh(bill)
    # The credit in a bill-payment category no longer reduces what was spent.
    assert bill.computed_total == Decimal("1000.00")

    resp = await client.patch(
        f"/api/categories/{payment_category.id}", headers=auth_headers,
        json={"is_bill_payment": False},
    )
    assert resp.status_code == 200
    await session.refresh(bill)
    assert bill.computed_total == Decimal("800.00")


async def test_toggling_is_ignored_refreshes_bill_totals(
    client: AsyncClient, auth_headers, session, test_user, test_workspace
):
    payment_category = Category(id=uuid.uuid4(), user_id=test_user.id, name="Pagamento recebido")
    market = Category(id=uuid.uuid4(), user_id=test_user.id, name="Mercado")
    session.add_all([payment_category, market])
    await session.commit()
    bill = await _bill_with_rows(session, test_user, test_workspace, payment_category, market)

    resp = await client.patch(
        f"/api/categories/{market.id}", headers=auth_headers, json={"is_ignored": True}
    )
    assert resp.status_code == 200
    await session.refresh(bill)
    assert bill.computed_total == Decimal("-200.00")
