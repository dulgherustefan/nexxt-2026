"""Calendarul zilelor lucrătoare din România și ceasurile legale, în ora României (Europe/Bucharest).

- Sărbătorile legale vin din `holidays.Romania`: 1–2 ianuarie, 6–7 ianuarie, 24 ianuarie, Vinerea Mare,
  Paștele și Rusaliile ortodoxe (cu a doua zi), 1 mai, 1 iunie, 15 august, 30 noiembrie, 1 decembrie,
  25–26 decembrie. Lista oficială nu e în docs/context, deci sursa e marcată [U] și se verifică.
- Zilele în care banca e închisă suplimentar sunt parametrul [U] `bank_closure_days`.
- Datele fără fus orar se interpretează ca ora României. Rezultatele au mereu fus orar.
- Ziua de start nu se numără la adunarea zilelor lucrătoare (convenția din docs/context/11 §3).
"""

from __future__ import annotations

import calendar as _cal
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from typing import Literal, overload
from zoneinfo import ZoneInfo

import holidays

TZ = ZoneInfo("Europe/Bucharest")
END_OF_DAY = time(23, 59, 59)  # PARAM [U] `refund_end_of_day`: „sfârșitul zilei” nu e definit în note

BankingCalendarKind = Literal["ro", "target2"]


@lru_cache(maxsize=64)
def _ro_holidays(year: int) -> dict[date, str]:
    return dict(holidays.Romania(years=year, language="en_US"))     # numele sărbătorilor apar în engleză


@lru_cache(maxsize=64)
def _target2_holidays(year: int) -> frozenset[date]:
    """Zilele de închidere TARGET (calendarul ECB din `holidays`); opțiune [U] pentru rechemări SEPA."""
    return frozenset(holidays.financial_holidays("ECB", years=year).keys())


@dataclass(frozen=True)
class BusinessCalendar:
    """Calendarul zilelor lucrătoare: weekend, sărbători legale RO și zilele închise ale băncii."""

    closures: frozenset[date] = frozenset()
    kind: BankingCalendarKind = "ro"

    def is_holiday(self, d: date) -> bool:
        if self.kind == "target2":
            return d in _target2_holidays(d.year)
        return d in _ro_holidays(d.year) or d in self.closures

    def is_business_day(self, d: date) -> bool:
        return d.weekday() < 5 and not self.is_holiday(d)

    def next_business_day(self, d: date) -> date:
        """Prima zi lucrătoare STRICT după `d`."""
        d += timedelta(days=1)
        while not self.is_business_day(d):
            d += timedelta(days=1)
        return d

    def add_business_days(self, d: date, n: int) -> date:
        """`n` zile lucrătoare după `d`; ziua de start nu se numără."""
        if n < 0:
            raise ValueError("n must be >= 0")
        for _ in range(n):
            d = self.next_business_day(d)
        return d

    def business_days_between(self, start: date, end: date) -> int:
        """Câte zile lucrătoare sunt în intervalul (start, end]."""
        if end <= start:
            return 0
        count, d = 0, start
        while d < end:
            d += timedelta(days=1)
            count += self.is_business_day(d)
        return count


_closures: frozenset[date] = frozenset()


def set_bank_closure_days(days: Iterable[date | str]) -> None:
    """Configurează zilele închise ale băncii pentru calendarul implicit (parametrul [U])."""
    global _closures
    _closures = frozenset(d if isinstance(d, date) else date.fromisoformat(str(d)) for d in days)


def default_calendar() -> BusinessCalendar:
    return BusinessCalendar(closures=_closures)


def banking_calendar(kind: BankingCalendarKind = "ro", closures: Iterable[date] = ()) -> BusinessCalendar:
    """Calendarul pentru „zile bancare”: RO (implicit, [U]) sau TARGET (opțiune [U])."""
    return BusinessCalendar(closures=frozenset(closures) if kind == "ro" else frozenset(), kind=kind)


# ---------------------------------------------------------------- ora României


def to_local(dt: datetime) -> datetime:
    """Momentul în ora României; un datetime naiv e considerat deja ora României."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ)


def local_date(value: datetime | date) -> date:
    if isinstance(value, datetime):
        return to_local(value).date()
    return value


def end_of_day(d: date, eod: time = END_OF_DAY) -> datetime:
    return datetime.combine(d, eod, tzinfo=TZ)


def holiday_name(d: date) -> str | None:
    return _ro_holidays(d.year).get(d)


# ---------------------------------------------------------------- funcțiile publice (docs/06 §4.4)


def is_business_day(d: date | datetime, cal: BusinessCalendar | None = None) -> bool:
    return (cal or default_calendar()).is_business_day(local_date(d))


def next_business_day(d: date | datetime, cal: BusinessCalendar | None = None) -> date:
    """Prima zi lucrătoare STRICT după data (locală) a lui `d`."""
    return (cal or default_calendar()).next_business_day(local_date(d))


def end_of_next_business_day(dt: datetime, cal: BusinessCalendar | None = None, eod: time = END_OF_DAY) -> datetime:
    """23:59:59 ora României în ziua lucrătoare următoare datei locale a lui `dt`.

    Termenul T+1 din Legea 209/2019 art. 173 și CJUE C-70/25 („cel târziu până la sfârșitul zilei
    lucrătoare următoare”). O notificare de sâmbătă sau duminică are termenul luni (dacă e lucrătoare).
    """
    return end_of_day(next_business_day(dt, cal), eod)


@overload
def add_business_days(dt: datetime, n: int, cal: BusinessCalendar | None = None) -> datetime: ...
@overload
def add_business_days(dt: date, n: int, cal: BusinessCalendar | None = None) -> date: ...


def add_business_days(dt: datetime | date, n: int, cal: BusinessCalendar | None = None) -> datetime | date:
    """`n` zile lucrătoare după `dt` (ziua de start nu se numără).

    Pentru un datetime, rezultatul păstrează ora locală (ex. 15 zile lucrătoare de la primire, CMP-01).
    """
    c = cal or default_calendar()
    if isinstance(dt, datetime):
        local = to_local(dt)
        return datetime.combine(c.add_business_days(local.date(), n), local.time(), tzinfo=TZ)
    return c.add_business_days(dt, n)


@overload
def add_banking_days(dt: datetime, n: int, kind: BankingCalendarKind = "ro",
                     cal: BusinessCalendar | None = None) -> datetime: ...
@overload
def add_banking_days(dt: date, n: int, kind: BankingCalendarKind = "ro",
                     cal: BusinessCalendar | None = None) -> date: ...


def add_banking_days(dt: datetime | date, n: int, kind: BankingCalendarKind = "ro",
                     cal: BusinessCalendar | None = None) -> datetime | date:
    """`n` zile bancare după `dt`, pentru rechemarea SEPA (REC-02).

    docs/context nu conține calendarul TARGET2, deci implicit zilele bancare = zilele lucrătoare RO [U].
    Cu `kind="target2"` se folosesc zilele de închidere TARGET din `holidays` (tot [U]).
    """
    c = cal if cal is not None else (default_calendar() if kind == "ro" else banking_calendar(kind))
    return add_business_days(dt, n, c)


def business_days_between(start: date | datetime, end: date | datetime, cal: BusinessCalendar | None = None) -> int:
    return (cal or default_calendar()).business_days_between(local_date(start), local_date(end))


def roll_same_hour(dt: datetime, cal: BusinessCalendar | None = None) -> datetime:
    """L129 art. 8(10): un termen în ore care cade într-o zi nelucrătoare se mută la aceeași oră
    din prima zi lucrătoare."""
    c = cal or default_calendar()
    local = to_local(dt)
    d = local.date()
    while not c.is_business_day(d):
        d += timedelta(days=1)
    return datetime.combine(d, local.time(), tzinfo=TZ)


def add_months(d: date, months: int) -> date:
    """Convenția din docs/context/11 §3: ziua inexistentă devine ultima zi a lunii."""
    y, m0 = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m0 + 1
    return date(y, m, min(d.day, _cal.monthrange(y, m)[1]))


def months_between(start: date | datetime, end: date | datetime) -> int:
    """Lunile întregi scurse de la `start` la `end` (aceeași convenție ca `add_months`)."""
    a, b = local_date(start), local_date(end)
    if b < a:
        return -months_between(b, a)
    m = (b.year - a.year) * 12 + (b.month - a.month)
    while m > 0 and add_months(a, m) > b:
        m -= 1
    return m
