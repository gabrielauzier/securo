"""BIMP-01: imported card transactions join their bill (BIMP AC 1-3, 6, 7)."""

import uuid
from datetime import date

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.models.account import Account
from app.models.credit_card_bill import CreditCardBill
from app.models.transaction import Transaction
from app.services.import_service import import_transactions, parse_csv

CSV = (
    b"date,description,amount\n"
    b"2026-09-04,MERCADO,-100.00\n"
    b"2026-09-05,RESTAURANTE,-50.00\n"
    b"2026-10-06,FARMACIA,-25.00\n"
)


@pytest_asyncio.fixture
async def card(session, test_user, test_workspace) -> Account:
    account = Account(
        id=uuid.uuid4(),
        user_id=test_user.id,
        workspace_id=test_workspace.id,
        name="Cartão de Crédito Nubank",
        type="credit_card",
        currency="BRL",
        statement_close_day=5,
        payment_due_day=12,
    )
    session.add(account)
    await session.commit()
    return account


async def _bills(session, account) -> dict[date, CreditCardBill]:
    rows = (
        await session.execute(select(CreditCardBill).where(CreditCardBill.account_id == account.id))
    ).scalars().all()
    return {b.reference_month: b for b in rows}


async def _rows_by_bill(session, account) -> dict[uuid.UUID | None, list[date]]:
    rows = (
        await session.execute(select(Transaction).where(Transaction.account_id == account.id))
    ).scalars().all()
    grouped: dict[uuid.UUID | None, list[date]] = {}
    for row in rows:
        grouped.setdefault(row.bill_id, []).append(row.date)
    return grouped


async def _import(session, card, test_user):
    parsed, failed = parse_csv(CSV, date_format="YYYY-MM-DD")
    assert failed == []
    return await import_transactions(
        session, card.workspace_id, test_user.id, card.id, parsed, "import", detected_format="csv"
    )


async def test_import_links_rows_to_their_bills_and_reports_counts(session, card, test_user):
    # BIMP Independent Test: 09-04, 09-05 (close day) and 10-06 with close 5.
    result = await _import(session, card, test_user)
    assert result[0] == 3
    assert (result.bills_linked, result.bills_created) == (3, 3)

    bills = await _bills(session, card)
    assert sorted(bills) == [date(2026, 9, 1), date(2026, 10, 1), date(2026, 11, 1)]
    rows = await _rows_by_bill(session, card)
    assert rows[bills[date(2026, 9, 1)].id] == [date(2026, 9, 4)]
    assert rows[bills[date(2026, 10, 1)].id] == [date(2026, 9, 5)]
    assert rows[bills[date(2026, 11, 1)].id] == [date(2026, 10, 6)]
    assert None not in rows


async def test_importing_the_same_csv_twice_creates_no_bill(session, card, test_user):
    # BIMP AC 7.
    await _import(session, card, test_user)
    again = await _import(session, card, test_user)
    assert again[1] == 3  # all rows skipped as duplicates
    assert (again.bills_linked, again.bills_created) == (0, 0)
    assert len(await _bills(session, card)) == 3


async def test_import_endpoint_reports_bill_counts(client: AsyncClient, auth_headers, card):
    # BIMP AC 6 through the route.
    payload = {
        "account_id": str(card.id),
        "transactions": [
            {"description": "MERCADO", "amount": "100.00", "date": "2026-09-04", "type": "debit"},
            {"description": "RESTAURANTE", "amount": "50.00", "date": "2026-09-05", "type": "debit"},
        ],
    }
    response = await client.post("/api/transactions/import", headers=auth_headers, json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["imported"] == 2
    assert data["bills_linked"] == 2
    assert data["bills_created"] == 2


async def test_import_into_a_non_card_account_reports_zero_bill_counts(
    client: AsyncClient, auth_headers, test_account
):
    payload = {
        "account_id": str(test_account.id),
        "transactions": [
            {"description": "PIX", "amount": "10.00", "date": "2026-09-04", "type": "debit"},
        ],
    }
    response = await client.post("/api/transactions/import", headers=auth_headers, json=payload)
    assert response.status_code == 201
    assert (response.json()["bills_linked"], response.json()["bills_created"]) == (0, 0)
