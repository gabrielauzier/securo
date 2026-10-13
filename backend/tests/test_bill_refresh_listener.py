"""AD-005: committing an ORM change refreshes the touched bills with no explicit call.

Every case writes rows straight through the ORM and only commits, so the
expected aggregates hold only when the session listener refreshes the bill
(BILL-01 computed total, BPAY-02 paid amount and settled date).
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest_asyncio
from sqlalchemy import event, select

from app.models.account import Account
from app.models.category import Category
from app.models.credit_card_bill import CreditCardBill
from app.models.transaction import Transaction
from app.services import bill_service
from app.services.bill_service import get_or_create_bill
from app.services.credit_card_service import bill_period_for_month
from tests.conftest import TestSessionLocal, engine

SEPT = bill_period_for_month(date(2026, 9, 1), 5, 12)  # close 09-05, effective due 09-14
OCT = bill_period_for_month(date(2026, 10, 1), 5, 12)  # rows from 09-06


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
    account = Account(
        id=uuid.uuid4(), user_id=test_user.id, name="Nubank", type="checking", currency="BRL"
    )
    session.add(account)
    await session.commit()
    return account


@pytest_asyncio.fixture
async def bill(session, card) -> CreditCardBill:
    created, _ = await get_or_create_bill(session, card, SEPT)
    await session.commit()
    return created


def _tx(account, amount, tx_type="debit", *, on=date(2026, 8, 20), **extra) -> Transaction:
    return Transaction(
        id=uuid.uuid4(),
        user_id=account.user_id,
        account_id=account.id,
        description="row",
        amount=Decimal(amount),
        currency="BRL",
        date=on,
        type=tx_type,
        source="manual",
        **extra,
    )


async def _stored(bill_id) -> tuple[Decimal, Decimal, date | None]:
    async with TestSessionLocal() as fresh:
        stored = (
            await fresh.execute(select(CreditCardBill).where(CreditCardBill.id == bill_id))
        ).scalar_one()
        return stored.computed_total, stored.paid_amount, stored.settled_on


async def test_inserting_a_card_row_with_a_bill_refreshes_the_total(session, card, bill):
    session.add(_tx(card, "600.00", bill_id=bill.id))
    await session.commit()
    assert await _stored(bill.id) == (Decimal("600.00"), Decimal("0.00"), None)
    # The bill already loaded in the session carries the refreshed value too.
    assert bill.computed_total == Decimal("600.00")


async def test_changing_the_amount_refreshes_the_total(session, card, bill):
    row = _tx(card, "600.00", bill_id=bill.id)
    session.add(row)
    await session.commit()
    row.amount = Decimal("700.00")
    await session.commit()
    assert (await _stored(bill.id))[0] == Decimal("700.00")
    assert bill.computed_total == Decimal("700.00")


async def test_moving_a_row_into_an_ignored_category_drops_it_from_the_total(
    session, card, bill
):
    ignored = Category(user_id=card.user_id, name="Ignorar", is_ignored=True)
    session.add(ignored)
    moved = _tx(card, "400.00", bill_id=bill.id)
    session.add_all([_tx(card, "600.00", bill_id=bill.id), moved])
    await session.commit()
    assert (await _stored(bill.id))[0] == Decimal("1000.00")
    moved.category_id = ignored.id
    await session.commit()
    assert (await _stored(bill.id))[0] == Decimal("600.00")


async def test_ignoring_a_row_drops_it_from_the_total(session, card, bill):
    ignored = _tx(card, "400.00", bill_id=bill.id)
    session.add_all([_tx(card, "600.00", bill_id=bill.id), ignored])
    await session.commit()
    ignored.is_ignored = True
    await session.commit()
    assert (await _stored(bill.id))[0] == Decimal("600.00")


async def test_pairing_a_payment_with_the_card_credit_takes_the_credit_out_of_the_total(
    session, card, checking, bill
):
    # Verifier round 3 gap 1: purchase 1,000.00 and card credit 1,000.00 on the bill.
    credit = _tx(card, "1000.00", "credit", bill_id=bill.id)
    payment = _tx(checking, "1000.00", on=date(2026, 9, 14), paid_bill_id=bill.id)
    session.add_all([_tx(card, "1000.00", bill_id=bill.id), credit, payment])
    await session.commit()
    assert await _stored(bill.id) == (Decimal("0.00"), Decimal("1000.00"), date(2026, 9, 5))

    pair_id = uuid.uuid4()
    payment.transfer_pair_id = pair_id
    credit.transfer_pair_id = pair_id
    await session.commit()
    assert await _stored(bill.id) == (Decimal("1000.00"), Decimal("1000.00"), date(2026, 9, 14))


async def test_linking_and_unlinking_a_payment_refreshes_the_paid_amount(
    session, card, checking, bill
):
    session.add(_tx(card, "1000.00", bill_id=bill.id))
    payment = _tx(checking, "500.00", on=date(2026, 9, 14))
    session.add(payment)
    await session.commit()

    payment.paid_bill_id = bill.id
    await session.commit()
    assert await _stored(bill.id) == (Decimal("1000.00"), Decimal("500.00"), None)

    payment.paid_bill_id = None
    await session.commit()
    assert await _stored(bill.id) == (Decimal("1000.00"), Decimal("0.00"), None)


@pytest_asyncio.fixture
async def october(session, card) -> CreditCardBill:
    created, _ = await get_or_create_bill(session, card, OCT)
    await session.commit()
    return created


async def test_linking_a_paired_payment_refreshes_the_card_leg_bill(
    session, card, checking, bill, october
):
    # The pair exists before the link and the card credit sits on the next
    # bill: only the payment's paid_bill_id changes, yet the credit stops
    # counting as a refund on the October bill.
    pair_id = uuid.uuid4()
    credit = _tx(card, "1000.00", "credit", on=date(2026, 9, 14), bill_id=october.id, transfer_pair_id=pair_id)
    payment = _tx(checking, "1000.00", on=date(2026, 9, 14), transfer_pair_id=pair_id)
    session.add_all(
        [
            _tx(card, "1000.00", bill_id=bill.id),
            _tx(card, "300.00", on=date(2026, 9, 10), bill_id=october.id),
            credit,
            payment,
        ]
    )
    await session.commit()
    assert (await _stored(october.id))[0] == Decimal("-700.00")

    payment.paid_bill_id = bill.id
    await session.commit()
    assert await _stored(bill.id) == (Decimal("1000.00"), Decimal("1000.00"), date(2026, 9, 14))
    assert (await _stored(october.id))[0] == Decimal("300.00")


async def test_deleting_a_payment_refreshes_the_paid_amount_and_the_card_leg(
    session, card, checking, bill, october
):
    pair_id = uuid.uuid4()
    credit = _tx(card, "1000.00", "credit", on=date(2026, 9, 14), bill_id=october.id, transfer_pair_id=pair_id)
    payment = _tx(
        checking, "1000.00", on=date(2026, 9, 14), paid_bill_id=bill.id, transfer_pair_id=pair_id
    )
    session.add_all(
        [
            _tx(card, "1000.00", bill_id=bill.id),
            _tx(card, "300.00", on=date(2026, 9, 10), bill_id=october.id),
            credit,
            payment,
        ]
    )
    await session.commit()
    assert await _stored(bill.id) == (Decimal("1000.00"), Decimal("1000.00"), date(2026, 9, 14))
    assert (await _stored(october.id))[0] == Decimal("300.00")

    await session.delete(payment)
    await session.commit()
    assert await _stored(bill.id) == (Decimal("1000.00"), Decimal("0.00"), None)
    # Without the payment the card credit is a refund on its own bill again.
    assert (await _stored(october.id))[0] == Decimal("-700.00")


class _BillStatements:
    """Counts SQL statements that read or write `credit_card_bills`."""

    def __init__(self):
        self.count = 0

    def __call__(self, conn, cursor, statement, *args):
        if "credit_card_bills" in statement:
            self.count += 1

    def __enter__(self):
        event.listen(engine.sync_engine, "before_cursor_execute", self)
        return self

    def __exit__(self, *exc):
        event.remove(engine.sync_engine, "before_cursor_execute", self)


async def test_commit_without_watched_changes_runs_no_bill_queries(session, card, bill):
    row = _tx(card, "600.00", bill_id=bill.id)
    session.add(row)
    await session.commit()

    row.description = "renamed"
    with _BillStatements() as unwatched:
        await session.commit()
    with _BillStatements() as empty:
        await session.commit()
    row.amount = Decimal("650.00")
    with _BillStatements() as watched:
        await session.commit()

    assert (unwatched.count, empty.count) == (0, 0)
    assert watched.count > 0


async def test_refresh_runs_once_per_commit_and_does_not_recurse(
    session, card, bill, monkeypatch
):
    calls: list[set] = []
    real = bill_service.refresh_bills_sync

    def spy(sync_session, ids):
        calls.append(set(ids))
        real(sync_session, ids)

    monkeypatch.setattr(bill_service, "refresh_bills_sync", spy)
    first = _tx(card, "600.00", bill_id=bill.id)
    session.add(first)
    await session.flush()
    first.amount = Decimal("650.00")
    await session.flush()
    # A savepoint commit is not the commit: no refresh yet.
    async with session.begin_nested():
        session.add(_tx(card, "50.00", bill_id=bill.id))
    assert calls == []

    await session.commit()
    # The refresh itself flushes; that flush must not trigger another refresh.
    assert calls == [{bill.id}]
    assert (await _stored(bill.id))[0] == Decimal("700.00")
