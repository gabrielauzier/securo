"""Bill period math (spec BILL-01: P1 AC 2-4, close-day edge cases; BIMP AC 3)."""

from datetime import date, timedelta

import pytest

from app.services.credit_card_service import (
    BillPeriod,
    bill_period_for,
    bill_period_for_month,
    compute_effective_date,
)


def test_reference_month_2026_09_close_5_due_12():
    # P1 AC 2
    assert bill_period_for_month(date(2026, 9, 1), 5, 12) == BillPeriod(
        reference_month=date(2026, 9, 1),
        period_start=date(2026, 8, 5),
        period_end=date(2026, 9, 4),
        close_date=date(2026, 9, 5),
        nominal_due_date=date(2026, 9, 12),
        effective_due_date=date(2026, 9, 14),
    )


def test_close_day_31_clamps_to_last_day_of_30_day_month():
    # P1 AC 3: reference month 2026-10, close 31 -> September closes on the 30th.
    period = bill_period_for_month(date(2026, 10, 1), 31, 10)
    assert period.close_date == date(2026, 9, 30)
    assert period.period_start == date(2026, 8, 31)
    assert period.period_end == date(2026, 9, 29)
    assert period.nominal_due_date == date(2026, 10, 10)


def test_period_spanning_year_boundary():
    # P1 AC 4
    period = bill_period_for_month(date(2027, 1, 1), 5, 12)
    assert period.period_start == date(2026, 12, 5)
    assert period.period_end == date(2027, 1, 4)
    assert period.close_date == date(2027, 1, 5)
    assert period.nominal_due_date == date(2027, 1, 12)


def test_close_day_equals_due_day_due_is_in_month_after_close():
    # Edge case: both 10 -> nominal due is the 10th of the month after close.
    period = bill_period_for_month(date(2026, 9, 1), 10, 10)
    assert period.close_date == date(2026, 8, 10)
    assert period.nominal_due_date == date(2026, 9, 10)
    assert bill_period_for(date(2026, 8, 9), 10, 10).nominal_due_date == date(2026, 9, 10)


def test_effective_due_date_on_holiday_rolls_to_next_business_day():
    # Edge case: nominal due 2026-09-07 (holiday, Monday) -> 2026-09-08.
    period = bill_period_for_month(date(2026, 9, 1), 1, 7)
    assert period.nominal_due_date == date(2026, 9, 7)
    assert period.effective_due_date == date(2026, 9, 8)


def test_purchase_on_close_day_belongs_to_next_period():
    # BIMP AC 3: 2026-09-05 is the close day of the 2026-09 bill.
    period = bill_period_for(date(2026, 9, 5), 5, 12)
    assert period.reference_month == date(2026, 10, 1)
    assert period.period_start == date(2026, 9, 5)
    assert bill_period_for(date(2026, 9, 4), 5, 12).reference_month == date(2026, 9, 1)


def test_independent_test_dates_land_in_expected_bills():
    # P1 Independent Test: 08-04 -> 2026-08; 08-05 and 09-04 -> 2026-09.
    assert bill_period_for(date(2026, 8, 4), 5, 12).reference_month == date(2026, 8, 1)
    assert bill_period_for(date(2026, 8, 5), 5, 12).reference_month == date(2026, 9, 1)
    assert bill_period_for(date(2026, 9, 4), 5, 12).reference_month == date(2026, 9, 1)


@pytest.mark.parametrize("close_day, due_day", [(5, 12), (28, 5)])
def test_nominal_due_matches_compute_effective_date_for_every_day_of_2026(close_day, due_day):
    d = date(2026, 1, 1)
    while d.year == 2026:
        period = bill_period_for(d, close_day, due_day)
        assert period.nominal_due_date == compute_effective_date(d, close_day, due_day), d
        assert period.period_start <= d <= period.period_end, d
        assert period == bill_period_for_month(period.reference_month, close_day, due_day), d
        d += timedelta(days=1)
