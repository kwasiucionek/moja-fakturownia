"""Terminy płatności z przesunięciem na najbliższy dzień roboczy.

Ordynacja podatkowa (art. 12 § 5) i przepisy o ZUS: jeżeli ostatni dzień terminu
przypada na sobotę lub dzień ustawowo wolny od pracy, termin upływa następnego
dnia roboczego.
"""

from datetime import date, timedelta
from functools import lru_cache


def easter_sunday(year: int) -> date:
    # Algorytm Meeusa/Jonesa/Butchera (kalendarz gregoriański)
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


@lru_cache(maxsize=32)
def public_holidays(year: int) -> frozenset[date]:
    easter = easter_sunday(year)
    days = {
        date(year, 1, 1),
        date(year, 1, 6),
        easter,
        easter + timedelta(days=1),  # Poniedziałek Wielkanocny
        date(year, 5, 1),
        date(year, 5, 3),
        easter + timedelta(days=49),  # Zielone Świątki
        easter + timedelta(days=60),  # Boże Ciało
        date(year, 8, 15),
        date(year, 11, 1),
        date(year, 11, 11),
        date(year, 12, 25),
        date(year, 12, 26),
    }
    if year >= 2025:
        days.add(date(year, 12, 24))  # Wigilia — dzień wolny od 2025 r.
    return frozenset(days)


def is_working_day(day: date) -> bool:
    return day.weekday() < 5 and day not in public_holidays(day.year)


def shift_to_working_day(day: date) -> date:
    while not is_working_day(day):
        day += timedelta(days=1)
    return day


def next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def previous_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def zus_deadline(year: int, month: int) -> date:
    """Składki ZUS za dany miesiąc (osoba prowadząca JDG): do 20. dnia następnego miesiąca."""
    y, m = next_month(year, month)
    return shift_to_working_day(date(y, m, 20))


def lump_sum_deadline(year: int, month: int) -> date:
    """Ryczałt za miesiąc: do 20. dnia następnego miesiąca, za grudzień — w terminie PIT-28."""
    if month == 12:
        return annual_return_deadline(year)
    y, m = next_month(year, month)
    return shift_to_working_day(date(y, m, 20))


def annual_return_deadline(year: int) -> date:
    """Zeznanie roczne PIT-28 za dany rok: do 30 kwietnia roku następnego."""
    return shift_to_working_day(date(year + 1, 4, 30))


def annual_health_deadline(year: int) -> date:
    """Roczne rozliczenie składki zdrowotnej: w deklaracji za kwiecień, do 20 maja."""
    return shift_to_working_day(date(year + 1, 5, 20))
