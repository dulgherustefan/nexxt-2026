"""Calendarul zilelor lucrătoare din România și termenul T+1 (L209 art. 173, CJUE C-70/25).

Oglinda calculatorului din motorul de reguli (docs/06 §4.4: `end_of_next_business_day`), folosită aici
doar ca să calculăm termenele așteptate din setul de aur. Sărbătorile legale vin din pachetul `holidays`
(RO: 1–2 ian., 6–7 ian., 24 ian., Vinerea Mare, Paștele și a doua zi (ortodox), 1 mai, 1 iunie, Rusaliile
și a doua zi, 15 aug., 30 nov., 1 dec., 25–26 dec.). Zilele în care banca e închisă suplimentar sunt PARAM [U].
"""

from __future__ import annotations

import calendar as _cal
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

import holidays

TZ = ZoneInfo("Europe/Bucharest")
END_OF_DAY = time(23, 59, 59)          # PARAM: „sfârșitul zilei" nu e definit în note (docs/context/11 §3)


@lru_cache(maxsize=64)
def ro_holidays(year: int) -> frozenset[date]:
    return frozenset(holidays.country_holidays("RO", years=year).keys())


def is_business_day(d: date) -> bool:
    return d.weekday() < 5 and d not in ro_holidays(d.year)


def next_business_day(d: date) -> date:
    """Prima zi lucrătoare STRICT după `d`."""
    d += timedelta(days=1)
    while not is_business_day(d):
        d += timedelta(days=1)
    return d


def add_business_days(d: date, n: int) -> date:
    for _ in range(n):
        d = next_business_day(d)
    return d


def to_local(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ)


def end_of_next_business_day(dt: datetime) -> datetime:
    """23:59:59 ora României în următoarea zi lucrătoare după data (locală) a lui `dt`."""
    local = to_local(dt)
    return datetime.combine(next_business_day(local.date()), END_OF_DAY, tzinfo=TZ)


def add_months(d: date, months: int) -> date:
    """Convenție (docs/context/11 §3): ziua inexistentă -> ultima zi a lunii."""
    y, m0 = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m0 + 1
    return date(y, m, min(d.day, _cal.monthrange(y, m)[1]))


def within_13_months(executed_at: datetime, notified_at: datetime) -> bool:
    """L209 art. 169 (DSP-01), pe date locale, inclusiv: notificarea <= debitare + 13 luni."""
    return to_local(notified_at).date() <= add_months(to_local(executed_at).date(), 13)


def iso(dt: datetime | None) -> str | None:
    """ISO 8601 cu offset, în ora României (convenția depozitelor)."""
    if dt is None:
        return None
    return to_local(dt).isoformat()


def parse_ts(value: str | datetime | None) -> datetime | None:
    """Șir ISO (cu sau fără offset) sau datetime -> datetime cu fus orar (ora României dacă lipsește)."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return to_local(value)
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return to_local(dt)
