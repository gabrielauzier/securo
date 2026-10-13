"""Credit-card bill lifecycle and stored aggregates.

`refresh_bills` is the only writer of a bill's `computed_total`,
`paid_amount` and `settled_on` (AD-003). Status, remaining and overpaid
amounts depend on "today" and are derived at read time by the pure
`bill_status` and `bill_amounts`.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Iterable, Sequence

from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.category import Category
from app.models.credit_card_bill import CreditCardBill
from app.models.transaction import Transaction
from app.services.credit_card_service import BillPeriod

ZERO = Decimal("0.00")

STATUS_PAID = "paid"
STATUS_OPEN = "open"
STATUS_OVERDUE = "overdue"
STATUS_PARTIALLY_PAID = "partially_paid"
STATUS_CLOSED = "closed"


@dataclass(frozen=True)
class BillAmounts:
    target: Decimal
    remaining: Decimal
    overpaid: Decimal


def bill_target(bill: CreditCardBill) -> Decimal:
    """What the bill asks to be paid: the declared total when set, else the computed one."""
    if bill.declared_total is not None:
        return Decimal(bill.declared_total)
    return Decimal(bill.computed_total or ZERO)


def bill_amounts(bill: CreditCardBill) -> BillAmounts:
    target = bill_target(bill)
    paid = Decimal(bill.paid_amount or ZERO)
    return BillAmounts(
        target=target,
        remaining=max(target - paid, ZERO),
        overpaid=max(paid - target, ZERO),
    )


def bill_status(bill: CreditCardBill, today: date) -> str:
    """Derived status, evaluated in the spec's precedence order."""
    paid = Decimal(bill.paid_amount or ZERO)
    if today >= bill.close_date and paid >= bill_target(bill):
        return STATUS_PAID
    if today < bill.close_date:
        return STATUS_OPEN
    if today > bill.effective_due_date:
        return STATUS_OVERDUE
    if paid > 0:
        return STATUS_PARTIALLY_PAID
    return STATUS_CLOSED


async def _find_bill(
    session: AsyncSession, account_id: uuid.UUID, reference_month: date
) -> CreditCardBill | None:
    # A provider bill covering the month wins over any other.
    return (
        await session.execute(
            select(CreditCardBill)
            .where(
                CreditCardBill.account_id == account_id,
                CreditCardBill.reference_month == reference_month,
            )
            .order_by(case((CreditCardBill.source == "provider", 0), else_=1))
            .limit(1)
        )
    ).scalar_one_or_none()


async def get_or_create_bill(
    session: AsyncSession, account: Account, period: BillPeriod
) -> tuple[CreditCardBill, bool]:
    """The card's bill for the period's reference month, creating an `auto` one when missing.

    Two writers creating the same bill race on the partial unique index; the
    loser's savepoint rolls back and it re-reads the winner's bill."""
    existing = await _find_bill(session, account.id, period.reference_month)
    if existing is not None:
        return existing, False
    bill = CreditCardBill(
        user_id=account.user_id,
        workspace_id=account.workspace_id,
        account_id=account.id,
        source="auto",
        reference_month=period.reference_month,
        period_start=period.period_start,
        period_end=period.period_end,
        close_date=period.close_date,
        due_date=period.nominal_due_date,
        effective_due_date=period.effective_due_date,
        total_amount=ZERO,
        currency=account.currency,
    )
    try:
        async with session.begin_nested():
            session.add(bill)
    except IntegrityError:
        winner = await _find_bill(session, account.id, period.reference_month)
        if winner is None:
            raise
        return winner, False
    return bill, True


def _excluded_category_ids():
    return select(Category.id).where(
        or_(Category.is_bill_payment.is_(True), Category.is_ignored.is_(True))
    )


def _payment_pair_ids():
    return select(Transaction.transfer_pair_id).where(
        Transaction.paid_bill_id.is_not(None),
        Transaction.transfer_pair_id.is_not(None),
    )


async def _computed_total(session: AsyncSession, bill_id: uuid.UUID) -> Decimal:
    signed = case(
        (Transaction.type == "debit", func.abs(Transaction.amount)),
        else_=-func.abs(Transaction.amount),
    )
    total = await session.scalar(
        select(func.coalesce(func.sum(signed), 0)).where(
            Transaction.bill_id == bill_id,
            Transaction.source != "opening_balance",
            Transaction.is_ignored.is_(False),
            or_(
                Transaction.category_id.is_(None),
                Transaction.category_id.not_in(_excluded_category_ids()),
            ),
            # The card credit of a bill payment pays the bill; it is not a refund.
            or_(
                Transaction.transfer_pair_id.is_(None),
                Transaction.transfer_pair_id.not_in(_payment_pair_ids()),
            ),
        )
    )
    return Decimal(total or 0).quantize(Decimal("0.01"))


async def refresh_bills(session: AsyncSession, bill_ids: Iterable[uuid.UUID]) -> None:
    """Recompute `computed_total`, `paid_amount` and `settled_on` from the linked rows."""
    ids = {bill_id for bill_id in bill_ids if bill_id is not None}
    if not ids:
        return
    await session.flush()
    bills = (
        await session.execute(select(CreditCardBill).where(CreditCardBill.id.in_(ids)))
    ).scalars().all()
    for bill in bills:
        bill.computed_total = await _computed_total(session, bill.id)
        payments = (
            await session.execute(
                select(Transaction.date, func.abs(Transaction.amount))
                .where(Transaction.paid_bill_id == bill.id)
                .order_by(Transaction.date, Transaction.created_at)
            )
        ).all()
        paid = sum((Decimal(amount) for _, amount in payments), ZERO)
        bill.paid_amount = paid
        bill.settled_on = _settled_on(bill, payments)
    await session.flush()


def _settled_on(bill: CreditCardBill, payments: Sequence[Any]) -> date | None:
    target = bill_target(bill)
    if target <= 0:
        return bill.close_date
    running = ZERO
    for paid_on, amount in payments:
        running += Decimal(amount)
        if running >= target:
            return paid_on
    return None

