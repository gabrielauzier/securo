"""Brazilian banking business-day calendar (spec BDAY-01, P2 Matching AC 1-2)."""

from datetime import date

import pytest

from app.core.business_days import (
    br_national_holidays,
    easter_sunday,
    is_business_day,
    next_business_day,
)


@pytest.mark.parametrize(
    "year, expected",
    [
        (2026, date(2026, 4, 5)),
        (2027, date(2027, 3, 28)),
        (2028, date(2028, 4, 16)),
    ],
)
def test_easter_sunday_matches_spec_dates(year, expected):
    assert easter_sunday(year) == expected


# Every holiday listed in the spec Assumptions: 01/01, Carnival Monday and
# Tuesday, Good Friday, 21/04, 01/05, Corpus Christi, 07/09, 12/10, 02/11,
# 15/11, 20/11, 25/12.
EXPECTED_HOLIDAYS = {
    2026: {
        date(2026, 1, 1),
        date(2026, 2, 16),  # Carnival Monday (Easter - 48)
        date(2026, 2, 17),  # Carnival Tuesday (Easter - 47)
        date(2026, 4, 3),  # Good Friday (Easter - 2)
        date(2026, 4, 21),
        date(2026, 5, 1),
        date(2026, 6, 4),  # Corpus Christi (Easter + 60)
        date(2026, 9, 7),
        date(2026, 10, 12),
        date(2026, 11, 2),
        date(2026, 11, 15),
        date(2026, 11, 20),
        date(2026, 12, 25),
    },
    2027: {
        date(2027, 1, 1),
        date(2027, 2, 8),
        date(2027, 2, 9),
        date(2027, 3, 26),
        date(2027, 4, 21),
        date(2027, 5, 1),
        date(2027, 5, 27),
        date(2027, 9, 7),
        date(2027, 10, 12),
        date(2027, 11, 2),
        date(2027, 11, 15),
        date(2027, 11, 20),
        date(2027, 12, 25),
    },
    2028: {
        date(2028, 1, 1),
        date(2028, 2, 28),
        date(2028, 2, 29),
        date(2028, 4, 14),
        date(2028, 4, 21),
        date(2028, 5, 1),
        date(2028, 6, 15),
        date(2028, 9, 7),
        date(2028, 10, 12),
        date(2028, 11, 2),
        date(2028, 11, 15),
        date(2028, 11, 20),
        date(2028, 12, 25),
    },
}


@pytest.mark.parametrize("year", [2026, 2027, 2028])
def test_national_holidays_are_exactly_the_spec_list(year):
    assert br_national_holidays(year) == frozenset(EXPECTED_HOLIDAYS[year])


@pytest.mark.parametrize(
    "holiday", sorted(d for days in EXPECTED_HOLIDAYS.values() for d in days)
)
def test_every_holiday_is_not_a_business_day(holiday):
    assert is_business_day(holiday) is False


def test_weekend_is_not_a_business_day():
    assert is_business_day(date(2026, 9, 12)) is False  # Saturday
    assert is_business_day(date(2026, 9, 13)) is False  # Sunday


def test_next_business_day_rolls_saturday_to_monday():
    assert next_business_day(date(2026, 9, 12)) == date(2026, 9, 14)


def test_next_business_day_rolls_holiday_monday_to_tuesday():
    assert next_business_day(date(2026, 9, 7)) == date(2026, 9, 8)


def test_business_day_returns_itself():
    assert is_business_day(date(2026, 9, 14)) is True
    assert next_business_day(date(2026, 9, 14)) == date(2026, 9, 14)


def test_next_business_day_skips_carnival_after_weekend():
    # Saturday 2026-02-14 -> Sun, Carnival Mon 16, Carnival Tue 17 -> Wed 18.
    assert next_business_day(date(2026, 2, 14)) == date(2026, 2, 18)
