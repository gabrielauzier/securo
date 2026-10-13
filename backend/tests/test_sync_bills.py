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


# --- T27: auto-match after sync (BMATCH AC 7) ---------------------------------


def _checking_provider(transactions: list[TransactionData]) -> AsyncMock:
    mock = AsyncMock()
    mock.refresh_credentials = AsyncMock(return_value={"token": "t"})
    mock.get_accounts = AsyncMock(
        return_value=[
            AccountData(
                external_id="chk-1", name="Nubank", type="checking",
                balance=Decimal("0"), currency="BRL",
            )
        ]
    )
    mock.get_transactions = AsyncMock(return_value=transactions)
    mock.get_bills = AsyncMock(return_value=[])
    return mock


async def _manual_card_bill(session, user, workspace) -> CreditCardBill:
    from app.models.account import Account
    from app.services import bill_service
    from app.services.credit_card_service import bill_period_for_month

    card = Account(
        id=uuid.uuid4(), user_id=user.id, workspace_id=workspace.id,
        name="Cartão de Crédito Nubank", type="credit_card", currency="BRL",
        statement_close_day=5, payment_due_day=12,
    )
    session.add(card)
    await session.flush()
    bill, _ = await bill_service.get_or_create_bill(
        session, card, bill_period_for_month(SEP, 5, 12)
    )
    session.add(
        Transaction(
            id=uuid.uuid4(), user_id=user.id, workspace_id=workspace.id, account_id=card.id,
            description="MERCADO", amount=Decimal("1283.20"), currency="BRL",
            date=date(2026, 8, 20), effective_date=date(2026, 8, 20), type="debit",
            source="manual", bill_id=bill.id,
        )
    )
    await bill_service.refresh_bills(session, [bill.id])
    await session.commit()
    return bill


PAYMENT = [_tx("pagamento-fatura", date(2026, 9, 14), "1283.20")]


async def test_synced_checking_payment_links_to_its_bill(session, test_user, test_workspace):
    bill = await _manual_card_bill(session, test_user, test_workspace)
    conn = await _connection(session, test_user.id)

    await _sync(session, conn, test_workspace, test_user, _checking_provider(PAYMENT))

    _, rows = await _state(session)
    await session.refresh(bill)
    assert rows["pagamento-fatura"].paid_bill_id == bill.id
    assert bill.paid_amount == Decimal("1283.20")


async def test_a_failed_match_keeps_the_synced_rows(session, test_user, test_workspace):
    await _manual_card_bill(session, test_user, test_workspace)
    conn = await _connection(session, test_user.id)

    with patch(
        "app.services.bill_match_service.run_auto_match",
        new_callable=AsyncMock, side_effect=RuntimeError("boom"),
    ):
        await _sync(session, conn, test_workspace, test_user, _checking_provider(PAYMENT))

    _, rows = await _state(session)
    await session.refresh(conn)
    assert rows["pagamento-fatura"].paid_bill_id is None
    assert conn.status == "active"


# --- T57: phantom cleanup refreshes the bills of the rows it deletes (AD-004) --


async def test_phantom_cleanup_drops_the_deleted_payment_from_its_bill(
    session, test_user, test_workspace
):
    # Edge case: WHEN a linked payment transaction is deleted THEN the system SHALL
    # drop the link and recompute the bill status. Here the sync cleanup deletes it.
    from app.models.account import Account
    from app.services import bill_service
    from app.services.connection_service import _cleanup_phantom_duplicates

    bill = await _manual_card_bill(session, test_user, test_workspace)
    conn = await _connection(session, test_user.id)
    checking = Account(
        id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
        connection_id=conn.id, name="Nubank", type="checking", currency="BRL",
    )
    session.add(checking)

    def _payment(on: date, **extra) -> Transaction:
        return Transaction(
            id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
            account_id=checking.id, description="PAGAMENTO FATURA", amount=Decimal("1283.20"),
            currency="BRL", date=on, effective_date=on, type="debit", source="sync", **extra,
        )

    # The phantom twin pays the bill; its real sibling is the paired one.
    phantom = _payment(date(2026, 9, 14), paid_bill_id=bill.id)
    session.add_all([phantom, _payment(date(2026, 9, 15), transfer_pair_id=uuid.uuid4())])
    await session.flush()
    await bill_service.refresh_bills(session, [bill.id])
    await session.commit()
    await session.refresh(bill)
    assert bill.paid_amount == Decimal("1283.20")
    phantom_id = phantom.id

    assert await _cleanup_phantom_duplicates(session, conn.id) == {checking.id}
    await session.commit()

    assert await session.get(Transaction, phantom_id) is None
    await session.refresh(bill)
    assert bill.paid_amount == Decimal("0.00")
    assert bill.settled_on is None
