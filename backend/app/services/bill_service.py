"""Credit-card bill lifecycle and stored aggregates.

`refresh_bills` is the only writer of a bill's `computed_total`,
`paid_amount` and `settled_on` (AD-003). Status, remaining and overpaid
amounts depend on "today" and are derived at read time by the pure
`bill_status` and `bill_amounts`.
"""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Iterable, Sequence

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.app_clock import app_today
from app.core.business_days import next_business_day
from app.models.account import Account
from app.models.category import Category
from app.models.credit_card_bill import CreditCardBill
from app.models.transaction import Transaction
from app.services.credit_card_service import (
    BillPeriod,
    _clamp_day,
    _shift_month,
    bill_period_for,
    bill_period_for_month,
)

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



# --- Linking card transactions -------------------------------------------------


@dataclass(frozen=True)
class LinkSummary:
    linked: int = 0
    bills_created: int = 0


def _cycle(account: Account) -> tuple[int, int] | None:
    """The card's (close day, due day), or None when it has no bill cycle."""
    if account.type != "credit_card":
        return None
    if not account.statement_close_day or not account.payment_due_day:
        return None
    return account.statement_close_day, account.payment_due_day


async def _account_bills(session: AsyncSession, account_id: uuid.UUID) -> list[CreditCardBill]:
    return list(
        (
            await session.execute(
                select(CreditCardBill).where(CreditCardBill.account_id == account_id)
            )
        ).scalars().all()
    )


async def _bills_with_payments(session: AsyncSession, bill_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    ids = list(bill_ids)
    if not ids:
        return set()
    rows = await session.execute(
        select(Transaction.paid_bill_id).where(Transaction.paid_bill_id.in_(ids)).distinct()
    )
    return {bill_id for (bill_id,) in rows if bill_id is not None}


async def _target_bill(
    session: AsyncSession,
    account: Account,
    cycle: tuple[int, int],
    tx: Transaction,
    bills: list[CreditCardBill],
) -> tuple[CreditCardBill | None, bool]:
    """The bill a card row belongs to, and whether it had to be created."""
    override = tx.effective_bill_date
    if override is not None:
        # A manual override names the bill by its due date; it never creates one.
        match = next(
            (b for b in bills if override in (b.effective_due_date, b.due_date)), None
        )
        return match, False
    containing = sorted(
        (b for b in bills if b.period_start <= tx.date <= b.period_end),
        key=lambda b: b.source != "provider",
    )
    if containing:
        return containing[0], False
    period = bill_period_for(tx.date, *cycle)
    bill, created = await get_or_create_bill(session, account, period)
    if created or bill not in bills:
        bills.append(bill)
    return bill, created


async def _link_rows(
    session: AsyncSession,
    account: Account,
    cycle: tuple[int, int],
    rows: Sequence[Transaction],
    bills: list[CreditCardBill],
    frozen: set[uuid.UUID],
) -> tuple[int, int, set[uuid.UUID]]:
    """Point each row at its bill. Rows on a provider bill or on a `frozen`
    bill stay put, and no row moves into a frozen bill."""
    by_id = {b.id: b for b in bills}
    linked = created_count = 0
    touched: set[uuid.UUID] = set()
    for tx in rows:
        current = by_id.get(tx.bill_id) if tx.bill_id else None
        if current is not None and (current.source == "provider" or current.id in frozen):
            continue
        target, created = await _target_bill(session, account, cycle, tx, bills)
        by_id.update({b.id: b for b in bills})
        created_count += int(created)
        if target is not None and target.id in frozen:
            continue
        new_id = target.id if target is not None else None
        if new_id == tx.bill_id:
            continue
        if tx.bill_id is not None:
            touched.add(tx.bill_id)
        tx.bill_id = new_id
        if new_id is not None:
            touched.add(new_id)
            linked += 1
    return linked, created_count, touched


async def _card_rows(
    session: AsyncSession, account: Account, tx_ids: list[uuid.UUID] | None = None
) -> Sequence[Transaction]:
    query = select(Transaction).where(
        Transaction.account_id == account.id,
        Transaction.source != "opening_balance",
    )
    if tx_ids is not None:
        query = query.where(Transaction.id.in_(tx_ids))
    return (await session.execute(query.order_by(Transaction.date))).scalars().all()


async def link_account_transactions(
    session: AsyncSession, account: Account, tx_ids: list[uuid.UUID] | None = None
) -> LinkSummary:
    """Link a card's rows (all, or `tx_ids`) to the bill of their period.

    Creates the `auto` bill of a period that has none, honors the manual
    `effective_bill_date` override, and leaves rows on provider bills alone.
    A card without close or due day gets no bills."""
    cycle = _cycle(account)
    if cycle is None or (tx_ids is not None and not tx_ids):
        return LinkSummary()
    await session.flush()
    bills = await _account_bills(session, account.id)
    rows = await _card_rows(session, account, tx_ids)
    linked, created, touched = await _link_rows(session, account, cycle, rows, bills, frozen=set())
    await refresh_bills(session, touched)
    return LinkSummary(linked=linked, bills_created=created)


async def relink_account(session: AsyncSession, account: Account) -> LinkSummary:
    """Apply a changed close or due day to the card's own bills.

    Auto and manual bills without payments get the new cycle's dates and
    their rows are relinked; bills with payments keep their dates and rows.
    Non-provider bills left with no rows, no payments and no declared total
    are deleted."""
    cycle = _cycle(account)
    if cycle is None:
        return LinkSummary()
    await session.flush()
    bills = await _account_bills(session, account.id)
    own = [b for b in bills if b.source != "provider"]
    frozen = await _bills_with_payments(session, (b.id for b in own))
    for bill in own:
        if bill.id in frozen:
            continue
        period = bill_period_for_month(bill.reference_month, *cycle)
        bill.period_start = period.period_start
        bill.period_end = period.period_end
        bill.close_date = period.close_date
        bill.due_date = period.nominal_due_date
        bill.effective_due_date = period.effective_due_date

    rows = await _card_rows(session, account)
    linked, created, touched = await _link_rows(session, account, cycle, rows, bills, frozen)
    await session.flush()

    used = {
        bill_id
        for (bill_id,) in await session.execute(
            select(Transaction.bill_id).where(Transaction.account_id == account.id).distinct()
        )
    }
    for bill in bills:
        if (
            bill.source != "provider"
            and bill.id not in frozen
            and bill.id not in used
            and bill.declared_total is None
        ):
            touched.discard(bill.id)
            await session.delete(bill)
    await session.flush()
    await refresh_bills(session, touched)
    return LinkSummary(linked=linked, bills_created=created)


async def collect_bill_ids(session: AsyncSession, tx_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    """The bills the rows belong to (`bill_id`) or pay (`paid_bill_id`)."""
    ids = list(tx_ids)
    if not ids:
        return set()
    await session.flush()
    rows = await session.execute(
        select(Transaction.bill_id, Transaction.paid_bill_id).where(Transaction.id.in_(ids))
    )
    return {bill_id for pair in rows for bill_id in pair if bill_id is not None}


async def touch(session: AsyncSession, tx_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    """Refresh every bill the rows belong to or pay; returns those bill ids.

    Call after an update. Before a delete, collect the ids with
    `collect_bill_ids`, delete, then `refresh_bills` them."""
    bill_ids = await collect_bill_ids(session, tx_ids)
    await refresh_bills(session, bill_ids)
    return bill_ids


# --- Reading bills -----------------------------------------------------------


async def list_bills(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    reference_month: date | None = None,
    account_id: uuid.UUID | None = None,
) -> list[CreditCardBill]:
    """The workspace's bills, newest reference month first."""
    query = select(CreditCardBill).where(CreditCardBill.workspace_id == workspace_id)
    if reference_month is not None:
        query = query.where(CreditCardBill.reference_month == reference_month)
    if account_id is not None:
        query = query.where(CreditCardBill.account_id == account_id)
    query = query.order_by(
        CreditCardBill.reference_month.desc(), CreditCardBill.effective_due_date, CreditCardBill.id
    )
    return list((await session.execute(query)).scalars().all())


async def get_bill(
    session: AsyncSession, workspace_id: uuid.UUID, bill_id: uuid.UUID
) -> CreditCardBill | None:
    return (
        await session.execute(
            select(CreditCardBill).where(
                CreditCardBill.id == bill_id, CreditCardBill.workspace_id == workspace_id
            )
        )
    ).scalar_one_or_none()


async def describe_bills(
    session: AsyncSession, bills: Sequence[CreditCardBill], today: date | None = None
) -> list[dict[str, Any]]:
    """Bills with their derived status and amounts, and their linked payments."""
    today = today or app_today()
    payments: dict[uuid.UUID, list[dict[str, Any]]] = {b.id: [] for b in bills}
    if bills:
        rows = (
            await session.execute(
                select(Transaction)
                .where(Transaction.paid_bill_id.in_(list(payments)))
                .order_by(Transaction.date, Transaction.created_at)
            )
        ).scalars().all()
        for tx in rows:
            payments[tx.paid_bill_id].append(
                {
                    "id": tx.id,
                    "account_id": tx.account_id,
                    "date": tx.date,
                    "description": tx.description,
                    "amount": float(abs(tx.amount)),
                    "currency": tx.currency,
                }
            )
    described = []
    for bill in bills:
        amounts = bill_amounts(bill)
        described.append(
            {
                "id": bill.id,
                "account_id": bill.account_id,
                "external_id": bill.external_id,
                "due_date": bill.due_date,
                "total_amount": float(bill.total_amount),
                "currency": bill.currency,
                "minimum_payment": (
                    float(bill.minimum_payment) if bill.minimum_payment is not None else None
                ),
                "source": bill.source,
                "reference_month": bill.reference_month,
                "period_start": bill.period_start,
                "period_end": bill.period_end,
                "close_date": bill.close_date,
                "effective_due_date": bill.effective_due_date,
                "declared_total": (
                    float(bill.declared_total) if bill.declared_total is not None else None
                ),
                "computed_total": float(bill.computed_total or ZERO),
                "target_amount": float(amounts.target),
                "paid_amount": float(bill.paid_amount or ZERO),
                "remaining_amount": float(amounts.remaining),
                "overpaid_amount": float(amounts.overpaid),
                "settled_on": bill.settled_on,
                "status": bill_status(bill, today),
                "payments": payments[bill.id],
            }
        )
    return described


# --- Manual bill management --------------------------------------------------


class BillError(Exception):
    """A bill request the service refuses; `status_code` is the HTTP answer."""

    status_code = 422

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class BillNotFoundError(BillError):
    status_code = 404


class BillConflictError(BillError):
    status_code = 409


class BillValidationError(BillError):
    status_code = 422


_DATE_FIELDS = ("reference_month", "close_date", "due_date")


def _check_declared_total(value: Decimal | None) -> None:
    if value is not None and Decimal(value) < 0:
        raise BillValidationError("declared_total must not be negative")


def _manual_period(account: Account, close_date: date, due_date: date) -> BillPeriod:
    if due_date <= close_date:
        raise BillValidationError("due_date must be after close_date")
    close_day = account.statement_close_day or close_date.day
    return BillPeriod(
        reference_month=due_date.replace(day=1),
        period_start=_clamp_day(*_shift_month(close_date, -1), close_day),
        period_end=close_date - timedelta(days=1),
        close_date=close_date,
        nominal_due_date=due_date,
        effective_due_date=next_business_day(due_date),
    )


def _apply_period(bill: CreditCardBill, period: BillPeriod) -> None:
    bill.reference_month = period.reference_month
    bill.period_start = period.period_start
    bill.period_end = period.period_end
    bill.close_date = period.close_date
    bill.due_date = period.nominal_due_date
    bill.effective_due_date = period.effective_due_date


async def _card(session: AsyncSession, workspace_id: uuid.UUID, account_id: uuid.UUID) -> Account:
    account = (
        await session.execute(
            select(Account).where(Account.id == account_id, Account.workspace_id == workspace_id)
        )
    ).scalar_one_or_none()
    if account is None:
        raise BillNotFoundError("Account not found")
    if account.type != "credit_card":
        raise BillValidationError("Bills exist only for credit card accounts")
    return account


async def _claim_period_rows(session: AsyncSession, bill: CreditCardBill) -> set[uuid.UUID]:
    """Move into `bill` the card rows dated in its period that have no manual
    override and are not on a provider bill; returns the bills they left."""
    provider_bills = select(CreditCardBill.id).where(CreditCardBill.source == "provider")
    rows = (
        await session.execute(
            select(Transaction).where(
                Transaction.account_id == bill.account_id,
                Transaction.source != "opening_balance",
                Transaction.effective_bill_date.is_(None),
                Transaction.date >= bill.period_start,
                Transaction.date <= bill.period_end,
                or_(Transaction.bill_id.is_(None), Transaction.bill_id.not_in(provider_bills)),
            )
        )
    ).scalars().all()
    left: set[uuid.UUID] = set()
    for tx in rows:
        if tx.bill_id != bill.id:
            if tx.bill_id is not None:
                left.add(tx.bill_id)
            tx.bill_id = bill.id
    return left


async def create_manual_bill(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    account_id: uuid.UUID,
    *,
    reference_month: date,
    close_date: date,
    due_date: date,
    declared_total: Decimal | None = None,
) -> CreditCardBill:
    """Store a `manual` bill and link the card rows dated in its period (P1 AC 7)."""
    account = await _card(session, workspace_id, account_id)
    _check_declared_total(declared_total)
    period = _manual_period(account, close_date, due_date)
    if period.reference_month != reference_month.replace(day=1):
        raise BillValidationError("reference_month must be the month of due_date")
    if await _find_bill(session, account.id, period.reference_month) is not None:
        raise BillConflictError("The card already has a bill for this reference month")
    bill = CreditCardBill(
        user_id=account.user_id,
        workspace_id=account.workspace_id,
        account_id=account.id,
        source="manual",
        total_amount=ZERO,
        currency=account.currency,
        declared_total=declared_total,
    )
    _apply_period(bill, period)
    try:
        async with session.begin_nested():
            session.add(bill)
    except IntegrityError:
        raise BillConflictError("The card already has a bill for this reference month")
    left = await _claim_period_rows(session, bill)
    await refresh_bills(session, left | {bill.id})
    return bill


async def update_bill(
    session: AsyncSession, workspace_id: uuid.UUID, bill_id: uuid.UUID, changes: dict[str, Any]
) -> CreditCardBill:
    """Edit a bill's declared total (any bill) or dates (auto and manual bills)."""
    bill = await get_bill(session, workspace_id, bill_id)
    if bill is None:
        raise BillNotFoundError("Bill not found")
    date_changes = {k: v for k, v in changes.items() if k in _DATE_FIELDS}
    if date_changes and bill.source == "provider":
        raise BillValidationError("The dates of a provider bill cannot be edited")
    if "declared_total" in changes:
        _check_declared_total(changes["declared_total"])
        bill.declared_total = changes["declared_total"]
    touched = {bill.id}
    if date_changes:
        account = await _card(session, workspace_id, bill.account_id)
        period = _manual_period(
            account,
            date_changes.get("close_date") or bill.close_date,
            date_changes.get("due_date") or bill.due_date,
        )
        wanted = date_changes.get("reference_month")
        if wanted is not None and wanted.replace(day=1) != period.reference_month:
            raise BillValidationError("reference_month must be the month of due_date")
        if period.reference_month != bill.reference_month:
            other = await _find_bill(session, account.id, period.reference_month)
            if other is not None and other.id != bill.id:
                raise BillConflictError("The card already has a bill for this reference month")
        _apply_period(bill, period)
        # Rows that no longer fall in the period go back to the bill of their date.
        outside = (
            await session.execute(
                select(Transaction).where(
                    Transaction.bill_id == bill.id,
                    Transaction.effective_bill_date.is_(None),
                    or_(Transaction.date < bill.period_start, Transaction.date > bill.period_end),
                )
            )
        ).scalars().all()
        for tx in outside:
            tx.bill_id = None
        touched |= await _claim_period_rows(session, bill)
        await session.flush()
        if outside:
            await link_account_transactions(session, account, [tx.id for tx in outside])
    await refresh_bills(session, touched)
    return bill


async def delete_bill(session: AsyncSession, workspace_id: uuid.UUID, bill_id: uuid.UUID) -> None:
    """Delete an `auto` or `manual` bill; its rows and payments stay, unlinked (P1 AC 11)."""
    bill = await get_bill(session, workspace_id, bill_id)
    if bill is None:
        raise BillNotFoundError("Bill not found")
    if bill.source == "provider":
        raise BillValidationError("A provider bill cannot be deleted")
    await session.execute(
        update(Transaction).where(Transaction.bill_id == bill.id).values(bill_id=None)
    )
    await session.execute(
        update(Transaction).where(Transaction.paid_bill_id == bill.id).values(paid_bill_id=None)
    )
    await session.delete(bill)
    await session.flush()
