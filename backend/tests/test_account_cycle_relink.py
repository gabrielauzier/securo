"""BILL-03: changing a card's cycle relinks its bills (P1 AC 12), and cycles
that would map two bills to one reference month are refused (edge case,
owner decision 2026-10-12)."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select

from app.models.account import Account
from app.models.credit_card_bill import CreditCardBill
from app.schemas.account import AccountCreate, AccountUpdate
from app.schemas.transaction import TransactionCreate
from app.services import bill_service
from app.services.account_service import (
    IncompatibleCycleDaysError,
    create_account,
    update_account,
)
from app.services.credit_card_service import cycle_days_compatible
from app.services.transaction_service import create_transaction

AUG, SEP, OCT = date(2026, 8, 1), date(2026, 9, 1), date(2026, 10, 1)


@pytest_asyncio.fixture
async def card(session, test_user, test_workspace) -> Account:
    account = Account(
        id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
        name="Cartão de Crédito Nubank", type="credit_card", currency="BRL",
        statement_close_day=5, payment_due_day=12,
    )
    session.add(account)
    await session.commit()
    return account


async def _create(session, ws, user, account, on, amount="100.00"):
    return await create_transaction(
        session, ws.id, user.id,
        TransactionCreate(
            account_id=account.id, description="row", amount=Decimal(amount), date=on, type="debit"
        ),
    )


async def _bills(session, account) -> dict[date, CreditCardBill]:
    rows = (
        await session.execute(select(CreditCardBill).where(CreditCardBill.account_id == account.id))
    ).scalars().all()
    for bill in rows:
        await session.refresh(bill)
    return {b.reference_month: b for b in rows}


async def test_cycle_change_relinks_bills_without_payments_and_keeps_paid_ones(
    session, test_user, test_workspace, card
):
    # Close 5 / due 12: 07-10 -> bill 2026-08 (paid), 08-20 -> 2026-09, 09-10 -> 2026-10.
    july = await _create(session, test_workspace, test_user, card, date(2026, 7, 10))
    aug = await _create(session, test_workspace, test_user, card, date(2026, 8, 20), "50.00")
    sep = await _create(session, test_workspace, test_user, card, date(2026, 9, 10), "30.00")
    checking = Account(
        id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
        name="Nubank", type="checking", currency="BRL",
    )
    session.add(checking)
    await session.commit()
    payment = await _create(session, test_workspace, test_user, checking, date(2026, 8, 12))
    payment.paid_bill_id = (await _bills(session, card))[AUG].id
    await bill_service.touch(session, [payment.id])
    await session.commit()

    await update_account(
        session, card.id, test_workspace.id,
        AccountUpdate(statement_close_day=15, payment_due_day=22),
    )

    bills = await _bills(session, card)
    # The paid 2026-08 bill keeps its dates and its row.
    paid = bills[AUG]
    assert (paid.close_date, paid.due_date) == (date(2026, 8, 5), date(2026, 8, 12))
    assert july.bill_id == paid.id
    # The 2026-09 bill takes the new cycle's dates and gains the 09-10 row.
    moved = bills[SEP]
    assert (moved.period_start, moved.period_end) == (date(2026, 8, 15), date(2026, 9, 14))
    assert moved.close_date == date(2026, 9, 15)
    assert moved.due_date == date(2026, 9, 22)
    assert moved.effective_due_date == date(2026, 9, 22)
    await session.refresh(aug)
    await session.refresh(sep)
    assert aug.bill_id == sep.bill_id == moved.id
    assert moved.computed_total == Decimal("80.00")
    # The 2026-10 bill was left empty, without payments or declared total.
    assert OCT not in bills


async def test_update_without_cycle_change_leaves_bills_alone(session, test_user, test_workspace, card):
    row = await _create(session, test_workspace, test_user, card, date(2026, 8, 20))
    before = (await _bills(session, card))[SEP]
    await update_account(session, card.id, test_workspace.id, AccountUpdate(name="Nubank Roxinho"))
    after = await _bills(session, card)
    assert list(after) == [SEP]
    assert after[SEP].id == before.id
    assert row.bill_id == before.id


@pytest.mark.parametrize(("close_day", "due_day"), [(5, 12), (28, 5), (10, 10)])
def test_compatible_cycles_are_accepted(close_day, due_day):
    assert cycle_days_compatible(close_day, due_day) is True


@pytest.mark.parametrize(("close_day", "due_day"), [(30, 31), (29, 30), (28, 29)])
def test_cycles_mapping_two_closes_to_one_month_are_refused(close_day, due_day):
    # Close 30 / due 31: the bills closing on 28 Feb and 30 Mar are both due in March.
    assert cycle_days_compatible(close_day, due_day) is False


async def test_update_account_rejects_an_incompatible_cycle_and_stores_nothing(
    session, test_workspace, card
):
    with pytest.raises(IncompatibleCycleDaysError, match="incompatible_cycle_days"):
        await update_account(
            session, card.id, test_workspace.id,
            AccountUpdate(statement_close_day=30, payment_due_day=31),
        )
    await session.rollback()
    await session.refresh(card)
    assert (card.statement_close_day, card.payment_due_day) == (5, 12)


async def test_create_account_rejects_an_incompatible_cycle(session, test_user, test_workspace):
    with pytest.raises(IncompatibleCycleDaysError):
        await create_account(
            session, test_workspace.id, test_user.id,
            AccountCreate(name="X", type="credit_card", currency="BRL",
                          statement_close_day=30, payment_due_day=31),
        )


async def test_create_endpoint_responds_422_and_stores_nothing(
    client: AsyncClient, auth_headers, session
):
    response = await client.post(
        "/api/accounts", headers=auth_headers,
        json={"name": "Cartão", "type": "credit_card", "currency": "BRL",
              "statement_close_day": 30, "payment_due_day": 31},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "incompatible_cycle_days"
    count = await session.scalar(select(func.count()).select_from(Account).where(Account.name == "Cartão"))
    assert count == 0


async def test_create_endpoint_accepts_a_compatible_cycle(client: AsyncClient, auth_headers):
    response = await client.post(
        "/api/accounts", headers=auth_headers,
        json={"name": "Cartão", "type": "credit_card", "currency": "BRL",
              "statement_close_day": 28, "payment_due_day": 5},
    )
    assert response.status_code == 201
    assert (response.json()["statement_close_day"], response.json()["payment_due_day"]) == (28, 5)


async def test_update_endpoint_responds_422_and_stores_nothing(
    client: AsyncClient, auth_headers, session, card
):
    response = await client.patch(
        f"/api/accounts/{card.id}", headers=auth_headers,
        json={"statement_close_day": 30, "payment_due_day": 31},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "incompatible_cycle_days"
    await session.refresh(card)
    assert (card.statement_close_day, card.payment_due_day) == (5, 12)


async def test_update_endpoint_accepts_a_compatible_cycle(client: AsyncClient, auth_headers, card):
    response = await client.patch(
        f"/api/accounts/{card.id}", headers=auth_headers,
        json={"statement_close_day": 10, "payment_due_day": 10},
    )
    assert response.status_code == 200
    assert (response.json()["statement_close_day"], response.json()["payment_due_day"]) == (10, 10)


async def test_cycle_change_on_a_bank_connected_card_relinks_its_bills(
    session, test_user, test_workspace
):
    from datetime import datetime, timezone

    from app.models.bank_connection import BankConnection

    conn = BankConnection(
        id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id, provider="test",
        external_id="ext-1", institution_name="Nubank", credentials={}, status="active",
        created_at=datetime.now(timezone.utc),
    )
    session.add(conn)
    synced = Account(
        id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
        connection_id=conn.id, external_id="cc-1", name="Cartão", type="credit_card",
        currency="BRL", statement_close_day=5, payment_due_day=12,
    )
    session.add(synced)
    await session.commit()
    row = await _create(session, test_workspace, test_user, synced, date(2026, 9, 10))
    assert row.bill_id == (await _bills(session, synced))[OCT].id

    await update_account(
        session, synced.id, test_workspace.id,
        AccountUpdate(statement_close_day=15, payment_due_day=22),
    )
    await session.refresh(row)
    bills = await _bills(session, synced)
    assert row.bill_id == bills[SEP].id
    assert bills[SEP].close_date == date(2026, 9, 15)
    assert OCT not in bills
