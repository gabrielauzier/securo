"""BILL-04: `python -m app.cli rebuild-bills` repairs bill links and aggregates."""

import uuid
from datetime import date
from decimal import Decimal

import pytest_asyncio
from sqlalchemy import select

from app import cli
from app.models.account import Account
from app.models.credit_card_bill import CreditCardBill
from app.models.transaction import Transaction
from app.services.bill_service import link_account_transactions
from tests.conftest import TestSessionLocal


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


def _tx(account, on, amount, **extra) -> Transaction:
    return Transaction(
        id=uuid.uuid4(),
        user_id=account.user_id,
        workspace_id=account.workspace_id,
        account_id=account.id,
        description="row",
        amount=Decimal(amount),
        currency="BRL",
        date=on,
        type=extra.pop("type", "debit"),
        source="csv",
        **extra,
    )


async def _bill(account_id) -> CreditCardBill:
    async with TestSessionLocal() as fresh:
        return (
            await fresh.execute(select(CreditCardBill).where(CreditCardBill.account_id == account_id))
        ).scalar_one()


async def test_rebuild_corrects_corrupted_aggregates_and_prints_counts(
    session, card, test_user, monkeypatch, capsys
):
    checking = Account(
        id=uuid.uuid4(), user_id=test_user.id, workspace_id=card.workspace_id,
        name="Nubank", type="checking", currency="BRL",
    )
    session.add(checking)
    purchase = _tx(card, date(2026, 8, 10), "600.00")
    session.add(purchase)
    await session.flush()
    await link_account_transactions(session, card, [purchase.id])
    bill = (await session.execute(select(CreditCardBill))).scalar_one()
    # A row added behind the bill service's back, and a payment whose refresh was missed.
    session.add(_tx(card, date(2026, 8, 20), "400.00"))
    session.add(_tx(checking, date(2026, 9, 14), "1000.00", paid_bill_id=bill.id))
    await session.flush()
    bill.paid_amount = Decimal("1.00")
    bill.computed_total = Decimal("5.00")
    bill.settled_on = None
    await session.commit()

    monkeypatch.setattr(cli, "async_session_maker", TestSessionLocal)
    await cli.rebuild_bills()

    repaired = await _bill(card.id)
    assert repaired.computed_total == Decimal("1000.00")
    assert repaired.paid_amount == Decimal("1000.00")
    assert repaired.settled_on == date(2026, 9, 14)
    out = capsys.readouterr().out
    assert "1 cards: 1 transactions linked, 0 bills created, 1 bills refreshed" in out


async def test_rebuild_limited_to_a_workspace_leaves_other_workspaces_alone(
    session, card, monkeypatch, capsys
):
    row = _tx(card, date(2026, 8, 10), "100.00")
    session.add(row)
    await session.flush()
    await link_account_transactions(session, card, [row.id])
    bill = (await session.execute(select(CreditCardBill))).scalar_one()
    bill.computed_total = Decimal("5.00")
    await session.commit()

    monkeypatch.setattr(cli, "async_session_maker", TestSessionLocal)
    await cli.rebuild_bills(uuid.uuid4())
    assert (await _bill(card.id)).computed_total == Decimal("5.00")
    assert "0 cards" in capsys.readouterr().out

    await cli.rebuild_bills(card.workspace_id)
    assert (await _bill(card.id)).computed_total == Decimal("100.00")
