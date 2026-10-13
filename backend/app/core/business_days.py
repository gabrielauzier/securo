"""Brazilian banking business days.

A business day is a weekday that is not a Brazilian national holiday. These
are the days banks process payments (FEBRABAN calendar); state and municipal
holidays are out of scope. A bill whose due date is not a business day can be
paid on the next one without penalty, which is what `next_business_day`
answers.
"""

from datetime import date, timedelta
from functools import lru_cache

# (month, day) of the fixed national holidays.
_FIXED_HOLIDAYS = (
    (1, 1),  # Confraternização Universal
    (4, 21),  # Tiradentes
    (5, 1),  # Dia do Trabalho
    (9, 7),  # Independência
    (10, 12),  # Nossa Senhora Aparecida
    (11, 2),  # Finados
    (11, 15),  # Proclamação da República
    (12, 25),  # Natal
)

# Dia Nacional de Zumbi e da Consciência Negra became a national holiday by
# Law 14.759/2023, first observed in 2024.
_CONSCIENCIA_NEGRA_SINCE = 2024


def easter_sunday(year: int) -> date:
    """Easter Sunday of a Gregorian year (anonymous Gregorian algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


@lru_cache(maxsize=64)
def br_national_holidays(year: int) -> frozenset[date]:
    """Brazilian national banking holidays of a year."""
    easter = easter_sunday(year)
    days = {date(year, month, day) for month, day in _FIXED_HOLIDAYS}
    if year >= _CONSCIENCIA_NEGRA_SINCE:
        days.add(date(year, 11, 20))
    days.update(
        {
            easter - timedelta(days=48),  # Carnival Monday
            easter - timedelta(days=47),  # Carnival Tuesday
            easter - timedelta(days=2),  # Good Friday
            easter + timedelta(days=60),  # Corpus Christi
        }
    )
    return frozenset(days)


def is_business_day(d: date) -> bool:
    return d.weekday() < 5 and d not in br_national_holidays(d.year)


def next_business_day(d: date) -> date:
    """`d` when it is a business day, else the first business day after it."""
    while not is_business_day(d):
        d += timedelta(days=1)
    return d
