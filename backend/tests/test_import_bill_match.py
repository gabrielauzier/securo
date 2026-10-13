"""BMATCH-01: bill payments match their bill after an import (Independent Test, AC 7)."""

import uuid
from datetime import date
from decimal import Decimal

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.models.account import Account
from app.models.credit_card_bill import CreditCardBill
from app.models.transaction import Transaction
from app.services import bill_service
from app.services.import_service import import_transactions, parse_csv

SEP = date(2026, 9, 1)
DUE = date(2026, 9, 14)  # effective due date of the 2026-09 bill (close 5, due 12)

# Purchases of the 2026-09 bill (period 2026-08-05..2026-09-04): 1,283.20.
CARD_CSV = (
    b"date,description,amount\n"
    b"2026-08-10,MERCADO,-1000.00\n"
    b"2026-09-01,RESTAURANTE,-283.20\n"
)
# The reference payment: 1,283.20 on 2026-09-14 from "Nubank".
CHECKING_CSV = (
    b"date,description,amount\n"
    b"2026-09-14,PAGAMENTO FATURA,-1283.20\n"
)


@pytest_asyncio.fixture
async def accounts(session, test_user, test_workspace):
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
    await session.commit()
    return card, checking


async def _import(session, account, user, content):
    parsed, failed = parse_csv(content, date_format="YYYY-MM-DD")
    assert failed == []
    return await import_transactions(
        session, account.workspace_id, user.id, account.id, parsed, "import",
        detected_format="csv",
    )


async def _september_bill(session, card) -> CreditCardBill:
    bill = (
        await session.execute(
            select(CreditCardBill).where(
                CreditCardBill.account_id == card.id, CreditCardBill.reference_month == SEP
            )
        )
    ).scalar_one()
    await session.refresh(bill)
    return bill


async def _payment(session, checking) -> Transaction:
    tx = (
        await session.execute(select(Transaction).where(Transaction.account_id == checking.id))
    ).scalar_one()
    await session.refresh(tx)
    return tx


async def test_checking_import_links_the_reference_payment(session, accounts, test_user):
    card, checking = accounts
    await _import(session, card, test_user, CARD_CSV)

    result = await _import(session, checking, test_user, CHECKING_CSV)

    # BMATCH Independent Test: the payment links automatically; the bill reads paid.
    bill = await _september_bill(session, card)
    payment = await _payment(session, checking)
    assert result.payments_matched == 1
    assert payment.paid_bill_id == bill.id
    assert bill.paid_amount == Decimal("1283.20")
    assert bill_service.bill_status(bill, DUE) == "paid"


async def test_card_import_that_creates_the_bill_matches_an_existing_payment(
    session, accounts, test_user
):
    card, checking = accounts
    first = await _import(session, checking, test_user, CHECKING_CSV)
    assert first.payments_matched == 0

    result = await _import(session, card, test_user, CARD_CSV)

    # BMATCH AC 7: a new bill on a card runs the matcher over existing payments.
    bill = await _september_bill(session, card)
    payment = await _payment(session, checking)
    assert result.bills_created >= 1
    assert result.payments_matched == 1
    assert payment.paid_bill_id == bill.id


async def test_import_endpoint_reports_matched_payments(
    client: AsyncClient, auth_headers, session, accounts, test_user
):
    card, checking = accounts
    await _import(session, card, test_user, CARD_CSV)
    payload = {
        "account_id": str(checking.id),
        "transactions": [
            {"description": "PAGAMENTO FATURA", "amount": "1283.20", "date": "2026-09-14",
             "type": "debit"},
        ],
    }

    response = await client.post("/api/transactions/import", headers=auth_headers, json=payload)

    assert response.status_code == 201
    assert response.json()["payments_matched"] == 1
