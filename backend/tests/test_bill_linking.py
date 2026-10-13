"""Linking card transactions to bills (spec BIMP-01 AC 1-4, 8; BILL-01 AC 13; BILL-03 AC 12)."""

import uuid
from datetime import date
from decimal import Decimal

import pytest_asyncio
from sqlalchemy import select

from app.models.account import Account
from app.models.credit_card_bill import CreditCardBill
from app.models.transaction import Transaction
from app.services.bill_service import (
    LinkSummary,
    link_account_transactions,
    relink_account,
    touch,
)


@pytest_asyncio.fixture
async def card(session, test_user) -> Account:
    account = Account(
        id=uuid.uuid4(),
        user_id=test_user.id,
        name="Cartão de Crédito Nubank",
        type="credit_card",
        currency="BRL",
        statement_close_day=5,
        payment_due_day=12,
    )
    session.add(account)
    await session.commit()
    return account


@pytest_asyncio.fixture
async def checking(session, test_user) -> Account:
    account = Account(id=uuid.uuid4(), user_id=test_user.id, name="Nubank", type="checking", currency="BRL")
    session.add(account)
    await session.commit()
    return account


def _tx(account, on, amount="100.00", tx_type="debit", **extra) -> Transaction:
    return Transaction(
        id=uuid.uuid4(),
        user_id=account.user_id,
        account_id=account.id,
        description="row",
        amount=Decimal(amount),
        currency="BRL",
        date=on,
        type=tx_type,
        source=extra.pop("source", "csv"),
        **extra,
    )


async def _add(session, *rows):
    session.add_all(rows)
    await session.flush()
    return rows


async def _bills(session, account) -> dict[date, CreditCardBill]:
    bills = (
        await session.execute(select(CreditCardBill).where(CreditCardBill.account_id == account.id))
    ).scalars().all()
    return {b.reference_month: b for b in bills}


async def test_rows_join_the_bill_of_their_period_creating_missing_bills(session, card):
    # BIMP AC 1, 2, 3 and the BIMP Independent Test: 09-04, 09-05 (close day), 10-06.
    a, b, c = await _add(
        session, _tx(card, date(2026, 9, 4)), _tx(card, date(2026, 9, 5)), _tx(card, date(2026, 10, 6))
    )
    summary = await link_account_transactions(session, card, [a.id, b.id, c.id])
    assert summary == LinkSummary(linked=3, bills_created=3)
    bills = await _bills(session, card)
    assert sorted(bills) == [date(2026, 9, 1), date(2026, 10, 1), date(2026, 11, 1)]
    assert a.bill_id == bills[date(2026, 9, 1)].id
    assert b.bill_id == bills[date(2026, 10, 1)].id  # close day -> next bill
    assert c.bill_id == bills[date(2026, 11, 1)].id
    assert {bill.source for bill in bills.values()} == {"auto"}
    assert bills[date(2026, 9, 1)].computed_total == Decimal("100.00")


async def test_existing_bill_is_reused_and_relinking_is_idempotent(session, card):
    # BIMP AC 1 (bill exists) and AC 7 (same data twice creates no duplicate bill).
    first, = await _add(session, _tx(card, date(2026, 8, 10)))
    await link_account_transactions(session, card, [first.id])
    second, = await _add(session, _tx(card, date(2026, 8, 20)))
    assert await link_account_transactions(session, card, [second.id]) == LinkSummary(1, 0)
    assert await link_account_transactions(session, card) == LinkSummary(0, 0)
    bills = await _bills(session, card)
    assert list(bills) == [date(2026, 9, 1)]
    assert first.bill_id == second.bill_id == bills[date(2026, 9, 1)].id
    assert bills[date(2026, 9, 1)].computed_total == Decimal("200.00")


async def test_date_change_moves_row_to_new_period(session, card):
    # BIMP AC 5 at service level: relink after the date changes.
    row, = await _add(session, _tx(card, date(2026, 8, 10)))
    await link_account_transactions(session, card, [row.id])
    row.date = date(2026, 9, 10)
    await link_account_transactions(session, card, [row.id])
    bills = await _bills(session, card)
    assert row.bill_id == bills[date(2026, 10, 1)].id
    assert bills[date(2026, 9, 1)].computed_total == Decimal("0.00")
    assert bills[date(2026, 10, 1)].computed_total == Decimal("100.00")


async def test_manual_override_links_to_bill_with_that_due_date_and_creates_none(session, card):
    # BIMP AC 4: override by effective (2026-09-14) or nominal (2026-09-12) due date.
    anchor, = await _add(session, _tx(card, date(2026, 8, 10)))
    await link_account_transactions(session, card, [anchor.id])
    sept = (await _bills(session, card))[date(2026, 9, 1)]

    by_effective, by_nominal, orphan = await _add(
        session,
        _tx(card, date(2026, 9, 20), effective_bill_date=date(2026, 9, 14)),
        _tx(card, date(2026, 9, 21), effective_bill_date=date(2026, 9, 12)),
        _tx(card, date(2026, 9, 22), effective_bill_date=date(2027, 3, 12)),
    )
    summary = await link_account_transactions(
        session, card, [by_effective.id, by_nominal.id, orphan.id]
    )
    assert summary == LinkSummary(linked=2, bills_created=0)
    assert by_effective.bill_id == sept.id
    assert by_nominal.bill_id == sept.id
    assert orphan.bill_id is None
    assert list(await _bills(session, card)) == [date(2026, 9, 1)]


async def test_installment_row_links_to_bill_of_its_own_date(session, card):
    # BIMP AC 8
    row, = await _add(
        session,
        _tx(
            card,
            date(2026, 10, 6),
            installment_number=3,
            total_installments=10,
            installment_purchase_date=date(2026, 8, 6),
        ),
    )
    await link_account_transactions(session, card, [row.id])
    assert row.bill_id == (await _bills(session, card))[date(2026, 11, 1)].id


async def test_card_without_cycle_gets_no_bills(session, card):
    # P1 AC 13
    card.payment_due_day = None
    row, = await _add(session, _tx(card, date(2026, 8, 10)))
    assert await link_account_transactions(session, card) == LinkSummary(0, 0)
    assert row.bill_id is None
    assert await _bills(session, card) == {}


async def test_opening_balance_rows_are_not_linked(session, card):
    row, = await _add(session, _tx(card, date(2026, 8, 10), source="opening_balance"))
    assert await link_account_transactions(session, card) == LinkSummary(0, 0)
    assert row.bill_id is None


async def test_provider_bill_rows_stay_and_provider_month_gets_no_auto_bill(session, card):
    provider = CreditCardBill(
        user_id=card.user_id,
        account_id=card.id,
        external_id="pluggy-sept",
        due_date=date(2026, 9, 12),
        total_amount=Decimal("500.00"),
    )
    session.add(provider)
    await session.flush()
    # Provider linked this row although its date is outside the cycle period.
    pinned, loose = await _add(
        session,
        _tx(card, date(2026, 9, 20), bill_id=provider.id),
        _tx(card, date(2026, 8, 15)),
    )
    summary = await link_account_transactions(session, card)
    assert summary == LinkSummary(linked=1, bills_created=0)
    assert pinned.bill_id == provider.id
    assert loose.bill_id == provider.id
    bills = await _bills(session, card)
    assert list(bills) == [date(2026, 9, 1)]
    assert bills[date(2026, 9, 1)].source == "provider"


async def test_relink_moves_rows_of_unpaid_bills_and_leaves_paid_bills(session, card, checking):
    # P1 AC 12: close 5/due 12 -> close 10/due 17.
    rows = await _add(
        session,
        _tx(card, date(2026, 8, 10)),  # Sep bill (paid)
        _tx(card, date(2026, 8, 20)),  # Sep bill (paid)
        _tx(card, date(2026, 9, 7)),  # Oct bill
        _tx(card, date(2026, 9, 20)),  # Oct bill
        _tx(card, date(2026, 10, 8)),  # Nov bill
    )
    await link_account_transactions(session, card)
    bills = await _bills(session, card)
    sept, octo, nov = bills[date(2026, 9, 1)], bills[date(2026, 10, 1)], bills[date(2026, 11, 1)]
    payment, = await _add(session, _tx(checking, date(2026, 9, 14), "200.00", paid_bill_id=sept.id))
    await touch(session, [payment.id])
    sept_before = (sept.close_date, sept.due_date, sept.effective_due_date, sept.computed_total)

    card.statement_close_day, card.payment_due_day = 10, 17
    summary = await relink_account(session, card)

    assert summary == LinkSummary(linked=1, bills_created=0)
    # Paid bill: same dates, same rows, same total.
    assert (sept.close_date, sept.due_date, sept.effective_due_date, sept.computed_total) == sept_before
    assert rows[0].bill_id == rows[1].bill_id == sept.id
    # Unpaid bill gets the new cycle: period 09-10..10-09, due 10-17 (Sat) -> 10-19.
    assert (octo.period_start, octo.period_end, octo.close_date, octo.due_date, octo.effective_due_date) == (
        date(2026, 9, 10),
        date(2026, 10, 9),
        date(2026, 10, 10),
        date(2026, 10, 17),
        date(2026, 10, 19),
    )
    assert rows[3].bill_id == octo.id
    assert rows[4].bill_id == octo.id  # 10-08 moved from the Nov bill
    # 09-07 now falls in the paid Sep cycle; it cannot move into a paid bill.
    assert rows[2].bill_id == octo.id
    assert octo.computed_total == Decimal("300.00")
    # The Nov bill, left empty with no payment or declared total, is gone.
    assert date(2026, 11, 1) not in await _bills(session, card)
    assert nov not in session


async def test_touch_refreshes_both_bill_and_paid_bill(session, card, checking):
    purchase, = await _add(session, _tx(card, date(2026, 8, 10)))
    await link_account_transactions(session, card)
    sept = (await _bills(session, card))[date(2026, 9, 1)]
    other, = await _add(session, _tx(card, date(2026, 9, 10)))
    await link_account_transactions(session, card, [other.id])
    octo = (await _bills(session, card))[date(2026, 10, 1)]
    payment, = await _add(session, _tx(checking, date(2026, 10, 13), "40.00", paid_bill_id=octo.id))

    purchase.amount = Decimal("250.00")
    refreshed = await touch(session, [purchase.id, payment.id])

    assert refreshed == {sept.id, octo.id}
    assert sept.computed_total == Decimal("250.00")
    assert octo.paid_amount == Decimal("40.00")
