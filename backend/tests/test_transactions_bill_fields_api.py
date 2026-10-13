"""BPAY-01/02: the transactions list and detail show the bill a payment pays."""

import uuid
from datetime import date
from decimal import Decimal

import pytest_asyncio
from httpx import AsyncClient

from app.models.account import Account
from app.models.transaction import Transaction
from app.services import bill_service
from app.services.credit_card_service import bill_period_for_month


def _tx(account, on, amount, type_="debit", **extra) -> Transaction:
    return Transaction(
        id=uuid.uuid4(), user_id=account.user_id, workspace_id=account.workspace_id,
        account_id=account.id, description="row", amount=Decimal(amount), currency="BRL",
        date=on, effective_date=on, type=type_, source="manual", **extra,
    )


@pytest_asyncio.fixture
async def ref(session, test_user, test_workspace):
    card = Account(
        id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
        name="Cartão de Crédito Nubank", type="credit_card", currency="BRL",
        statement_close_day=5, payment_due_day=12,
    )
    checking = Account(
        id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
        name="Nubank", type="checking", currency="BRL",
    )
    session.add_all([card, checking])
    await session.flush()
    bill, _ = await bill_service.get_or_create_bill(
        session, card, bill_period_for_month(date(2026, 9, 1), 5, 12)
    )
    payment = _tx(checking, date(2026, 9, 14), "1283.20")
    other = _tx(checking, date(2026, 9, 3), "100.00")
    session.add_all([payment, other])
    await session.commit()
    return {"card": card, "checking": checking, "bill": bill, "payment": payment, "other": other}


async def _link(client, headers, ref):
    resp = await client.post(
        f"/api/credit-card-bills/{ref['bill'].id}/payments", headers=headers,
        json={"transaction_id": str(ref["payment"].id)},
    )
    assert resp.status_code == 200, resp.text


async def _listed(client, headers, ref) -> dict[str, dict]:
    resp = await client.get(
        "/api/transactions", headers=headers, params={"account_id": str(ref["checking"].id)}
    )
    assert resp.status_code == 200
    return {item["id"]: item for item in resp.json()["items"]}


async def test_linked_payment_exposes_its_bill_and_missing_counterpart(
    client: AsyncClient, auth_headers, ref
):
    await _link(client, auth_headers, ref)
    expected = {
        "id": str(ref["bill"].id),
        "account_id": str(ref["card"].id),
        "account_name": "Cartão de Crédito Nubank",
        "reference_month": "2026-09-01",
    }

    items = await _listed(client, auth_headers, ref)
    payment = items[str(ref["payment"].id)]
    assert payment["paid_bill"] == expected
    # BPAY AC 4: no card credit was paired.
    assert payment["needs_counterpart"] is True

    detail = await client.get(f"/api/transactions/{ref['payment'].id}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["paid_bill"] == expected
    assert detail.json()["needs_counterpart"] is True


async def test_unlinked_transactions_return_null(client: AsyncClient, auth_headers, ref):
    await _link(client, auth_headers, ref)
    items = await _listed(client, auth_headers, ref)
    other = items[str(ref["other"].id)]
    assert other["paid_bill"] is None
    assert other["needs_counterpart"] is False

    await client.delete(f"/api/credit-card-bills/payments/{ref['payment'].id}", headers=auth_headers)
    detail = await client.get(f"/api/transactions/{ref['payment'].id}", headers=auth_headers)
    assert detail.json()["paid_bill"] is None
    assert detail.json()["needs_counterpart"] is False


async def test_paired_payment_needs_no_counterpart(
    client: AsyncClient, auth_headers, session, ref
):
    session.add(_tx(ref["card"], date(2026, 9, 15), "1283.20", "credit"))
    await session.commit()
    await _link(client, auth_headers, ref)

    detail = await client.get(f"/api/transactions/{ref['payment'].id}", headers=auth_headers)
    assert detail.json()["paid_bill"]["id"] == str(ref["bill"].id)
    assert detail.json()["needs_counterpart"] is False
