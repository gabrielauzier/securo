import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from app.core.app_clock import app_today
from app.core.business_days import next_business_day


def _clamp_day(year: int, month: int, day: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last_day))


def _next_day_occurrence(target_day: int, reference: date) -> date:
    candidate = _clamp_day(reference.year, reference.month, target_day)
    if candidate >= reference:
        return candidate
    if reference.month == 12:
        return _clamp_day(reference.year + 1, 1, target_day)
    return _clamp_day(reference.year, reference.month + 1, target_day)


def get_cycle_dates(
    statement_close_day: Optional[int],
    payment_due_day: Optional[int],
    reference: Optional[date] = None,
) -> dict:
    """Return the close + due dates of the nearest upcoming billing cycle.

    Both dates are from the SAME cycle: the due is anchored on the nearest upcoming
    occurrence of payment_due_day, and the close is the most recent occurrence of
    statement_close_day on or before that due date. This guarantees close <= due."""
    if reference is None:
        reference = app_today()

    next_due = _next_day_occurrence(payment_due_day, reference) if payment_due_day else None

    next_close: Optional[date] = None
    if statement_close_day:
        if next_due:
            # Pick the close that belongs to next_due's cycle: try same month first;
            # if it lands after the due date, walk back one month (with end-of-month clamping).
            anchor = next_due
            candidate = _clamp_day(anchor.year, anchor.month, statement_close_day)
            if candidate > anchor:
                if anchor.month == 1:
                    candidate = _clamp_day(anchor.year - 1, 12, statement_close_day)
                else:
                    candidate = _clamp_day(anchor.year, anchor.month - 1, statement_close_day)
            next_close = candidate
        else:
            next_close = _next_day_occurrence(statement_close_day, reference)

    return {
        "next_close_date": next_close,
        "next_due_date": next_due,
    }


def compute_available_credit(
    credit_limit: Optional[Decimal],
    current_balance: Decimal,
) -> Optional[Decimal]:
    """available = limit − utilized. current_balance for a credit card is negative when debt."""
    if credit_limit is None:
        return None
    utilized = -current_balance if current_balance < 0 else Decimal("0")
    return credit_limit - utilized


def apply_effective_date(transaction, account, *, bill_due_date: Optional[date] = None) -> None:
    """Populate `transaction.effective_date` based on the account type.

    Resolution order (highest priority first):
    1. `transaction.effective_bill_date` — manual user override; whatever
       the user set wins, since they're hand-correcting a bucketing they
       disagree with (issue #92's LucasFidelis suggestion).
    2. `bill_due_date` — bank-truth from Pluggy /bills (passed in by the
       sync layer when a bill is linked).
    3. Cycle math from `account.statement_close_day` / `payment_due_day`.

    For non-CC accounts, effective_date is always equal to `date`.

    Call this from every tx create/update path (manual, sync, import,
    transfers, opening balances). `effective_date` is stored on every row
    regardless of the user's reporting mode; the mode only affects which
    date the aggregation queries read from."""
    override = getattr(transaction, "effective_bill_date", None)
    if override is not None:
        transaction.effective_date = override
        return
    if account is not None and getattr(account, "type", None) == "credit_card":
        if bill_due_date is not None:
            transaction.effective_date = bill_due_date
        else:
            transaction.effective_date = compute_effective_date(
                transaction.date,
                getattr(account, "statement_close_day", None),
                getattr(account, "payment_due_day", None),
            )
    else:
        transaction.effective_date = transaction.date


def compute_effective_date(
    tx_date: date,
    statement_close_day: Optional[int],
    payment_due_day: Optional[int],
) -> date:
    """Return the *cash-flow* date for a credit card transaction.

    In accrual reporting mode, a credit card purchase doesn't impact cash flow
    on the purchase date — it impacts cash flow when the bill is paid. This
    helper computes that "effective" date:

      1. Find the cycle the transaction belongs to: the next statement close
         date *strictly after* tx_date. Per Brazilian banking convention
         (Nubank, Itaú, etc.), a transaction ON the close day belongs to the
         next invoice, not the one closing that day.
      2. The bill for that cycle is due on the next occurrence of payment_due_day
         strictly after the close.
      3. Return that bill's due date.

    Returns tx_date as-is when either close_day or due_day is not configured
    (nothing we can do without the cycle metadata)."""
    if not statement_close_day or not payment_due_day:
        return tx_date

    # Step 1: find the cycle end — the first close day strictly after tx_date.
    same_month_close = _clamp_day(tx_date.year, tx_date.month, statement_close_day)
    if same_month_close > tx_date:
        cycle_end = same_month_close
    else:
        if tx_date.month == 12:
            cycle_end = _clamp_day(tx_date.year + 1, 1, statement_close_day)
        else:
            cycle_end = _clamp_day(tx_date.year, tx_date.month + 1, statement_close_day)

    # Step 2: find the bill due date — the first due day strictly after cycle_end.
    same_month_due = _clamp_day(cycle_end.year, cycle_end.month, payment_due_day)
    if same_month_due > cycle_end:
        return same_month_due
    if cycle_end.month == 12:
        return _clamp_day(cycle_end.year + 1, 1, payment_due_day)
    return _clamp_day(cycle_end.year, cycle_end.month + 1, payment_due_day)


@dataclass(frozen=True)
class BillPeriod:
    """The dates of one credit-card bill.

    `reference_month` is day 1 of the nominal due date's month (the Brazilian
    "fatura de setembro" convention). Purchases dated in
    `[period_start, period_end]` belong to the bill; `period_end` is the day
    before `close_date`, so a purchase on the close day goes to the next bill.
    """

    reference_month: date
    period_start: date
    period_end: date
    close_date: date
    nominal_due_date: date
    effective_due_date: date


def _shift_month(d: date, months: int) -> tuple[int, int]:
    index = d.year * 12 + (d.month - 1) + months
    return index // 12, index % 12 + 1


def _period(close_date: date, close_day: int, due_day: int) -> BillPeriod:
    prev_year, prev_month = _shift_month(close_date, -1)
    nominal_due = _clamp_day(close_date.year, close_date.month, due_day)
    if nominal_due <= close_date:
        nominal_due = _clamp_day(*_shift_month(close_date, 1), due_day)
    return BillPeriod(
        reference_month=nominal_due.replace(day=1),
        period_start=_clamp_day(prev_year, prev_month, close_day),
        period_end=close_date - timedelta(days=1),
        close_date=close_date,
        nominal_due_date=nominal_due,
        effective_due_date=next_business_day(nominal_due),
    )


def bill_period_for(tx_date: date, close_day: int, due_day: int) -> BillPeriod:
    """The bill a purchase dated `tx_date` belongs to.

    Same rules as `compute_effective_date`: the close is the first close day
    strictly after the purchase, the nominal due the first due day strictly
    after the close."""
    close_date = _clamp_day(tx_date.year, tx_date.month, close_day)
    if close_date <= tx_date:
        close_date = _clamp_day(*_shift_month(tx_date, 1), close_day)
    return _period(close_date, close_day, due_day)


def bill_period_for_month(reference_month: date, close_day: int, due_day: int) -> BillPeriod:
    """The bill whose nominal due date falls in `reference_month`.

    The close is the last close day strictly before that month's due day."""
    nominal_due = _clamp_day(reference_month.year, reference_month.month, due_day)
    close_date = _clamp_day(reference_month.year, reference_month.month, close_day)
    if close_date >= nominal_due:
        close_date = _clamp_day(*_shift_month(reference_month, -1), close_day)
    return _period(close_date, close_day, due_day)
