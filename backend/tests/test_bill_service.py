"""Bill aggregates and status (spec BILL-01: P1 AC 1, 5, 6; BPAY AC 5-8 at service level)."""

import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models.account import Account
from app.models.category import Category
from app.models.credit_card_bill import CreditCardBill
from app.models.transaction import Transaction
from app.models.user import User
from app.models.workspace import Workspace
from app.services.bill_service import (
    bill_amounts,
    bill_status,
    get_or_create_bill,
    refresh_bills,
)
from app.services.credit_card_service import bill_period_for_month

SEPT = bill_period_for_month(date(2026, 9, 1), 5, 12)  # close 09-05, due 09-12, effective 09-14


def _bill(*, computed="0", declared=None, paid="0") -> CreditCardBill:
    return CreditCardBill(
        source="auto",
        reference_month=SEPT.reference_month,
        period_start=SEPT.period_start,
        period_end=SEPT.period_end,
        close_date=SEPT.close_date,
        due_date=SEPT.nominal_due_date,
        effective_due_date=SEPT.effective_due_date,
        total_amount=Decimal("0"),
        computed_total=Decimal(computed),
        declared_total=None if declared is None else Decimal(declared),
        paid_amount=Decimal(paid),
    )


# --- Pure status and amounts -------------------------------------------------


class TestBillStatus:
    def test_full_payment_after_close_is_paid_with_zero_remaining(self):
        # BPAY AC 5: target 1,283.20 paid by 1,283.20 on 2026-09-14.
        bill = _bill(computed="1283.20", paid="1283.20")
        assert bill_status(bill, date(2026, 9, 14)) == "paid"
        assert bill_amounts(bill).remaining == Decimal("0.00")

    def test_partial_payment_on_or_before_effective_due_is_partially_paid(self):
        # BPAY AC 6: 500.00 against 1,283.20 -> remaining 783.20.
        bill = _bill(computed="1283.20", paid="500.00")
        assert bill_status(bill, date(2026, 9, 14)) == "partially_paid"
        assert bill_amounts(bill).remaining == Decimal("783.20")

    def test_two_partials_summing_target_are_paid(self):
        # BPAY AC 7
        bill = _bill(computed="1283.20", paid=str(Decimal("500.00") + Decimal("783.20")))
        assert bill_status(bill, date(2026, 9, 20)) == "paid"

    def test_overpayment_is_paid_and_reports_overpaid(self):
        # BPAY AC 8
        bill = _bill(computed="1283.20", paid="1300.00")
        assert bill_status(bill, date(2026, 9, 14)) == "paid"
        amounts = bill_amounts(bill)
        assert amounts.overpaid == Decimal("16.80")
        assert amounts.remaining == Decimal("0.00")

    def test_before_close_is_open_even_when_fully_paid(self):
        # Precedence 1 requires today >= close date; precedence 2: today < close.
        bill = _bill(computed="1283.20", paid="1283.20")
        assert bill_status(bill, date(2026, 9, 4)) == "open"

    def test_after_effective_due_unpaid_is_overdue(self):
        bill = _bill(computed="1283.20")
        assert bill_status(bill, date(2026, 9, 15)) == "overdue"

    def test_after_effective_due_partially_paid_is_overdue(self):
        # Precedence 3 (overdue) beats 4 (partially_paid).
        bill = _bill(computed="1283.20", paid="500.00")
        assert bill_status(bill, date(2026, 9, 15)) == "overdue"

    def test_on_effective_due_unpaid_is_closed(self):
        bill = _bill(computed="1283.20")
        assert bill_status(bill, date(2026, 9, 5)) == "closed"
        assert bill_status(bill, date(2026, 9, 14)) == "closed"

    def test_zero_target_bill_is_open_before_close_and_paid_after(self):
        # Edge case: no linked rows, no declared total.
        bill = _bill()
        assert bill_amounts(bill).target == Decimal("0")
        assert bill_status(bill, date(2026, 9, 4)) == "open"
        assert bill_status(bill, date(2026, 9, 5)) == "paid"

    def test_declared_total_is_the_target(self):
        bill = _bill(computed="1283.20", declared="1000.00", paid="1000.00")
        assert bill_amounts(bill).target == Decimal("1000.00")
        assert bill_status(bill, date(2026, 9, 14)) == "paid"

    def test_status_follows_today_without_storing_it(self):
        # P1 AC 6: same stored bill, different "today", different status.
        bill = _bill(computed="1283.20", paid="500.00")
        assert [bill_status(bill, d) for d in (date(2026, 9, 1), date(2026, 9, 10), date(2026, 9, 30))] == [
            "open",
            "partially_paid",
            "overdue",
        ]
        assert not hasattr(bill, "status")


# --- DB-backed: get_or_create_bill and refresh_bills ---------------------------


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
        source=extra.pop("source", "manual"),
        **extra,
    )


async def test_get_or_create_bill_creates_one_auto_bill_per_month(session, card):
    # P1 AC 1
    bill, created = await get_or_create_bill(session, card, SEPT)
    again, created_again = await get_or_create_bill(session, card, SEPT)
    await session.commit()
    assert created is True and created_again is False
    assert again.id == bill.id
    assert (bill.source, bill.close_date, bill.due_date, bill.effective_due_date) == (
        "auto",
        date(2026, 9, 5),
        date(2026, 9, 12),
        date(2026, 9, 14),
    )
    count = await session.scalar(
        select(func.count()).select_from(CreditCardBill).where(CreditCardBill.account_id == card.id)
    )
    assert count == 1


async def test_second_non_provider_bill_for_same_month_is_rejected(session, card):
    # P1 AC 1: the partial unique index guards the invariant.
    await get_or_create_bill(session, card, SEPT)
    await session.commit()
    duplicate = _bill()
    duplicate.user_id = card.user_id
    duplicate.account_id = card.id
    duplicate.source = "manual"
    session.add(duplicate)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


async def test_get_or_create_returns_provider_bill_covering_the_month(session, card):
    provider = CreditCardBill(
        user_id=card.user_id,
        account_id=card.id,
        external_id="pluggy-1",
        due_date=date(2026, 9, 12),
        total_amount=Decimal("1283.20"),
    )
    session.add(provider)
    await session.commit()
    bill, created = await get_or_create_bill(session, card, SEPT)
    assert created is False
    assert bill.id == provider.id
    assert bill.declared_total == Decimal("1283.20")


async def test_computed_total_excludes_non_purchase_rows(session, card, checking):
    bill, _ = await get_or_create_bill(session, card, SEPT)
    bill_payment_cat = Category(user_id=card.user_id, name="Pagamento de fatura", is_bill_payment=True)
    ignored_cat = Category(user_id=card.user_id, name="Ignorar", is_ignored=True)
    session.add_all([bill_payment_cat, ignored_cat])
    await session.flush()
    pair_id = uuid.uuid4()
    payment = _tx(
        checking, "1283.20", on=date(2026, 9, 14), paid_bill_id=bill.id, transfer_pair_id=pair_id
    )
    session.add_all(
        [
            _tx(card, "600.00", bill_id=bill.id),
            _tx(card, "400.00", bill_id=bill.id),
            _tx(card, "50.00", "credit", bill_id=bill.id),  # refund reduces the total
            _tx(card, "1000.00", "credit", bill_id=bill.id, source="opening_balance"),
            _tx(card, "70.00", bill_id=bill.id, is_ignored=True),
            _tx(card, "80.00", bill_id=bill.id, category_id=bill_payment_cat.id),
            _tx(card, "90.00", bill_id=bill.id, category_id=ignored_cat.id),
            # Card leg of the payment pair.
            _tx(card, "1283.20", "credit", bill_id=bill.id, transfer_pair_id=pair_id),
            payment,
        ]
    )
    await session.flush()
    await refresh_bills(session, [bill.id])
    assert bill.computed_total == Decimal("950.00")


async def test_settled_on_is_date_of_payment_reaching_target(session, card, checking):
    bill, _ = await get_or_create_bill(session, card, SEPT)
    session.add(_tx(card, "1000.00", bill_id=bill.id))
    first = _tx(checking, "500.00", on=date(2026, 9, 14), paid_bill_id=bill.id)
    session.add(first)
    await session.flush()

    await refresh_bills(session, [bill.id])
    assert (bill.paid_amount, bill.settled_on) == (Decimal("500.00"), None)

    session.add(_tx(checking, "500.00", on=date(2026, 9, 20), paid_bill_id=bill.id))
    await session.flush()
    await refresh_bills(session, [bill.id])
    assert bill.paid_amount == Decimal("1000.00")
    assert bill.settled_on == date(2026, 9, 20)


async def test_settled_on_orders_same_day_payments_by_creation(session, card, checking):
    bill, _ = await get_or_create_bill(session, card, SEPT)
    session.add(_tx(card, "1000.00", bill_id=bill.id))
    early = datetime(2026, 9, 14, 8, tzinfo=timezone.utc)
    session.add_all(
        [
            _tx(checking, "400.00", on=date(2026, 9, 14), paid_bill_id=bill.id, created_at=early),
            _tx(checking, "600.00", on=date(2026, 9, 14), paid_bill_id=bill.id,
                created_at=early + timedelta(hours=1)),
            _tx(checking, "10.00", on=date(2026, 9, 16), paid_bill_id=bill.id),
        ]
    )
    await session.flush()
    await refresh_bills(session, [bill.id])
    assert bill.paid_amount == Decimal("1010.00")
    assert bill.settled_on == date(2026, 9, 14)


async def test_settled_on_uses_declared_total_as_target(session, card, checking):
    bill, _ = await get_or_create_bill(session, card, SEPT)
    bill.declared_total = Decimal("1200.00")
    session.add(_tx(card, "1000.00", bill_id=bill.id))
    session.add(_tx(checking, "1000.00", on=date(2026, 9, 14), paid_bill_id=bill.id))
    await session.flush()
    await refresh_bills(session, [bill.id])
    assert bill.computed_total == Decimal("1000.00")
    assert bill.settled_on is None


async def test_zero_target_bill_settles_on_close_date(session, card):
    # Target <= 0 (no purchases, or refunds exceed purchases) -> close date.
    bill, _ = await get_or_create_bill(session, card, SEPT)
    await refresh_bills(session, [bill.id])
    assert (bill.computed_total, bill.settled_on) == (Decimal("0.00"), date(2026, 9, 5))

    session.add(_tx(card, "30.00", "credit", bill_id=bill.id))
    await session.flush()
    await refresh_bills(session, [bill.id])
    assert (bill.computed_total, bill.settled_on) == (Decimal("-30.00"), date(2026, 9, 5))


# --- PostgreSQL: concurrent creation ------------------------------------------


async def test_concurrent_get_or_create_keeps_one_bill(postgres_sessions):
    # Edge case: two imports create the same bill concurrently -> one bill.
    async with postgres_sessions() as setup:
        user = User(id=uuid.uuid4(), email="race@example.com", hashed_password="x")
        setup.add(user)
        await setup.flush()
        workspace = Workspace(id=uuid.uuid4(), name="w", kind="personal", created_by_user_id=user.id)
        setup.add(workspace)
        await setup.flush()
        account = Account(
            id=uuid.uuid4(),
            user_id=user.id,
            workspace_id=workspace.id,
            name="card",
            type="credit_card",
            currency="BRL",
            statement_close_day=5,
            payment_due_day=12,
        )
        setup.add(account)
        await setup.commit()

    async def create():
        async with postgres_sessions() as s:
            acc = await s.get(Account, account.id)
            bill, _ = await get_or_create_bill(s, acc, SEPT)
            await s.commit()
            return bill.id

    ids = await asyncio.gather(create(), create(), create())
    assert len(set(ids)) == 1
    async with postgres_sessions() as check:
        count = await check.scalar(
            select(func.count()).select_from(CreditCardBill).where(CreditCardBill.account_id == account.id)
        )
    assert count == 1
