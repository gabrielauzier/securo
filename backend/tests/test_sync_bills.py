"""BIMP-01 / AD-004: provider sync keeps card bills current.

Card close 5, due 12. The provider sends the 2026-09 bill (due 2026-09-12)
and three purchases: one tagged with that bill, one inside its period
without a tag, and one of the next period (2026-10 bill, no provider bill).
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.models.bank_connection import BankConnection
from app.models.credit_card_bill import CreditCardBill
from app.models.transaction import Transaction
from app.providers.base import AccountData, BillData, TransactionData
from app.services.connection_service import sync_connection

SEP = date(2026, 9, 1)
OCT = date(2026, 10, 1)


async def _connection(session, user_id) -> BankConnection:
    conn = BankConnection(
        id=uuid.uuid4(), user_id=user_id, provider="test",
        external_id=f"ext-{uuid.uuid4().hex[:8]}", institution_name="Nubank",
        credentials={"token": "fake"}, status="active",
        last_sync_at=datetime.now(timezone.utc), created_at=datetime.now(timezone.utc),
    )
    session.add(conn)
    await session.commit()
    return conn


def _provider(bills: list[BillData], transactions: list[TransactionData]) -> AsyncMock:
    mock = AsyncMock()
    mock.refresh_credentials = AsyncMock(return_value={"token": "t"})
    mock.get_accounts = AsyncMock(
        return_value=[
            AccountData(
                external_id="cc-1", name="Cartão de Crédito Nubank", type="credit_card",
                balance=Decimal("0"), currency="BRL", statement_close_day=5, payment_due_day=12,
            )
        ]
    )
    mock.get_transactions = AsyncMock(return_value=transactions)
    mock.get_bills = AsyncMock(return_value=bills)
    return mock


def _bill(due: date, total: str) -> BillData:
    return BillData(external_id="bill-sep", due_date=due, total_amount=Decimal(total), currency="BRL")


def _tx(external_id: str, on: date, amount: str, bill: str | None = None) -> TransactionData:
    return TransactionData(
        external_id=external_id, description=external_id.upper(), amount=Decimal(amount),
        date=on, type="debit", currency="BRL", bill_external_id=bill,
    )


TXS = [
    _tx("tagged", date(2026, 8, 10), "100.00", bill="bill-sep"),
    _tx("untagged", date(2026, 8, 20), "50.00"),
    _tx("next", date(2026, 9, 10), "30.00"),
]


async def _sync(session, conn, workspace, user, provider):
    with patch("app.services.connection_service.get_provider", return_value=provider), \
         patch("app.services.connection_service.detect_transfer_pairs", new_callable=AsyncMock), \
         patch("app.services.connection_service.stamp_primary_amount", new_callable=AsyncMock), \
         patch("app.services.connection_service.apply_rules_to_transaction", new_callable=AsyncMock):
        await sync_connection(session, conn.id, workspace.id, user.id)


async def _state(session):
    bills = (await session.execute(select(CreditCardBill))).scalars().all()
    for bill in bills:
        await session.refresh(bill)
    rows = (
        await session.execute(select(Transaction).where(Transaction.source != "opening_balance"))
    ).scalars().all()
    return {b.reference_month: b for b in bills}, {r.external_id: r for r in rows}


async def test_provider_bill_gets_its_period_and_effective_due_date(
    session, test_user, test_workspace
):
    conn = await _connection(session, test_user.id)
    await _sync(session, conn, test_workspace, test_user, _provider([_bill(date(2026, 9, 12), "180.00")], TXS))

    bills, _ = await _state(session)
    provider = bills[SEP]
    assert provider.source == "provider"
    assert provider.external_id == "bill-sep"
    assert (provider.period_start, provider.period_end) == (date(2026, 8, 5), date(2026, 9, 4))
    assert provider.close_date == date(2026, 9, 5)
    assert provider.due_date == date(2026, 9, 12)
    assert provider.effective_due_date == date(2026, 9, 14)
    assert provider.declared_total == Decimal("180.00")


async def test_synced_rows_without_a_provider_bill_join_their_period_bill(
    session, test_user, test_workspace
):
    conn = await _connection(session, test_user.id)
    await _sync(session, conn, test_workspace, test_user, _provider([_bill(date(2026, 9, 12), "180.00")], TXS))

    bills, rows = await _state(session)
    assert sorted(bills) == [SEP, OCT]
    assert rows["tagged"].bill_id == bills[SEP].id
    assert rows["untagged"].bill_id == bills[SEP].id  # inside the provider bill's period
    assert rows["next"].bill_id == bills[OCT].id
    assert bills[OCT].source == "auto"
    assert bills[SEP].computed_total == Decimal("150.00")
    assert bills[OCT].computed_total == Decimal("30.00")


async def test_resync_moves_a_provider_bill_with_its_new_due_date_and_total(
    session, test_user, test_workspace
):
    conn = await _connection(session, test_user.id)
    await _sync(session, conn, test_workspace, test_user, _provider([_bill(date(2026, 9, 12), "180.00")], TXS))
    # The bank moves the due date to 2026-09-07 (holiday, Monday) and revises the total.
    await _sync(session, conn, test_workspace, test_user, _provider([_bill(date(2026, 9, 7), "200.00")], []))

    bills, _ = await _state(session)
    provider = bills[SEP]
    assert provider.due_date == date(2026, 9, 7)
    assert provider.effective_due_date == date(2026, 9, 8)
    assert provider.close_date == date(2026, 9, 5)
    assert provider.declared_total == Decimal("200.00")


async def test_resync_keeps_a_declared_total_the_user_typed(session, test_user, test_workspace):
    conn = await _connection(session, test_user.id)
    await _sync(session, conn, test_workspace, test_user, _provider([_bill(date(2026, 9, 12), "180.00")], TXS))
    bills, _ = await _state(session)
    bills[SEP].declared_total = Decimal("175.50")
    await session.commit()

    await _sync(session, conn, test_workspace, test_user, _provider([_bill(date(2026, 9, 12), "200.00")], []))
    bills, _ = await _state(session)
    assert bills[SEP].total_amount == Decimal("200.00")
    assert bills[SEP].declared_total == Decimal("175.50")
