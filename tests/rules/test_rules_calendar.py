"""Calendarul RO și ceasurile: weekenduri, sărbători legale, fusul orar, zilele închise ale băncii."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from rules_testkit import TZ, eod, ts
from versoml.shared.rules import calendar_ro as cal
from versoml.shared.rules.calendar_ro import (
    BusinessCalendar, add_banking_days, add_business_days, add_months, business_days_between,
    end_of_next_business_day, is_business_day, months_between, next_business_day, roll_same_hour,
)
from versoml.shared.rules.facts import fmt_d, fmt_dt, fmt_money, fmt_num

RO_HOLIDAYS_2026 = [
    date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 6), date(2026, 1, 7), date(2026, 1, 24),
    date(2026, 4, 10), date(2026, 4, 12), date(2026, 4, 13), date(2026, 5, 1), date(2026, 5, 31), date(2026, 6, 1),
    date(2026, 8, 15), date(2026, 11, 30), date(2026, 12, 1), date(2026, 12, 25), date(2026, 12, 26),
]


@pytest.mark.parametrize("d", RO_HOLIDAYS_2026)
def test_sarbatorile_legale_2026_nu_sunt_zile_lucratoare(d):
    assert not is_business_day(d)
    assert cal.holiday_name(d)


def test_numele_sarbatorilor_sunt_in_engleza():
    assert cal.holiday_name(date(2026, 12, 1)) == "National Day"
    assert cal.holiday_name(date(2026, 12, 25)) == "Christmas Day"
    assert cal.holiday_name(date(2026, 10, 28)) is None


def test_paste_si_rusalii_ortodoxe_2027():
    for d in (date(2027, 4, 30), date(2027, 5, 2), date(2027, 5, 3), date(2027, 6, 20), date(2027, 6, 21)):
        assert not is_business_day(d), d
    assert is_business_day(date(2027, 3, 29))          # Lunea Paștelui catolic nu e sărbătoare în RO


def test_zile_obisnuite_sunt_lucratoare():
    assert is_business_day(date(2026, 10, 28))
    assert not is_business_day(date(2026, 10, 31))     # sâmbătă
    assert not is_business_day(date(2026, 11, 1))      # duminică


# ---------------------------------------------------------------- T+1 (art. 173, C-70/25)


def test_t1_notificare_vineri_seara_termen_luni():
    # 25.10.2026 se trece la ora de iarnă: termenul e luni, cu offset +02:00
    due = end_of_next_business_day(ts(2026, 10, 23, 21, 30))
    assert due == eod(2026, 10, 26)
    assert due.utcoffset() == timedelta(hours=2)


def test_t1_29_noiembrie_sare_peste_30_noiembrie_si_1_decembrie():
    assert end_of_next_business_day(ts(2026, 11, 29, 12)) == eod(2026, 12, 2)


def test_t1_vineri_27_noiembrie_exemplul_din_docs_11():
    assert end_of_next_business_day(ts(2026, 11, 27, 9)) == eod(2026, 12, 2)


def test_t1_pastele_ortodox_2027():
    # joi 29.04.2027 → Vinerea Mare 30.04, 1 mai (sâmbătă), Paștele 2–3.05 → marți 4.05
    assert end_of_next_business_day(ts(2027, 4, 29, 18)) == eod(2027, 5, 4)
    assert end_of_next_business_day(ts(2027, 4, 29, 18)).utcoffset() == timedelta(hours=3)


def test_t1_rusalii_2027():
    assert end_of_next_business_day(ts(2027, 6, 18, 15)) == eod(2027, 6, 22)


def test_t1_craciun_si_anul_nou():
    assert end_of_next_business_day(ts(2026, 12, 24, 11)) == eod(2026, 12, 28)
    assert end_of_next_business_day(ts(2026, 12, 31, 11)) == eod(2027, 1, 4)
    assert end_of_next_business_day(ts(2027, 1, 5, 11)) == eod(2027, 1, 8)      # Boboteaza și Sf. Ioan


def test_t1_notificare_in_weekend_termen_luni():
    assert end_of_next_business_day(ts(2026, 10, 25, 9)) == eod(2026, 10, 26)


def test_t1_foloseste_data_locala_nu_data_utc():
    # 26.10.2026 22:30 UTC = marți 27.10, 00:30 ora României → termenul e miercuri
    utc = datetime(2026, 10, 26, 22, 30, tzinfo=timezone.utc)
    assert end_of_next_business_day(utc) == eod(2026, 10, 28)


def test_t1_data_naiva_e_ora_romaniei():
    assert end_of_next_business_day(datetime(2026, 10, 23, 23, 0)) == eod(2026, 10, 26)


def test_t1_vara_are_offset_plus_trei():
    due = end_of_next_business_day(ts(2026, 6, 15, 10))
    assert due == datetime(2026, 6, 16, 23, 59, 59, tzinfo=TZ)
    assert due.utcoffset() == timedelta(hours=3)


def test_zi_inchisa_a_bancii_parametru():
    closed = BusinessCalendar(closures=frozenset({date(2026, 12, 31)}))
    assert end_of_next_business_day(ts(2026, 12, 30), closed) == eod(2027, 1, 4)
    assert end_of_next_business_day(ts(2026, 12, 30)) == eod(2026, 12, 31)


def test_calendarul_implicit_preia_zilele_inchise():
    cal.set_bank_closure_days(["2026-12-31"])
    assert not is_business_day(date(2026, 12, 31))
    cal.set_bank_closure_days([])
    assert is_business_day(date(2026, 12, 31))


# ---------------------------------------------------------------- zile lucrătoare și bancare


def test_15_si_35_de_zile_lucratoare_din_docs_11():
    assert add_business_days(date(2026, 10, 28), 15) == date(2026, 11, 18)
    assert add_business_days(date(2026, 10, 28), 35) == date(2026, 12, 18)
    assert add_business_days(date(2026, 11, 26), 3) == date(2026, 12, 3)


def test_add_business_days_pastreaza_ora_pentru_datetime():
    out = add_business_days(ts(2026, 10, 23, 9, 12), 15)
    assert out == ts(2026, 11, 13, 9, 12)


def test_add_business_days_zero_si_negativ():
    assert add_business_days(date(2026, 10, 31), 0) == date(2026, 10, 31)
    with pytest.raises(ValueError):
        add_business_days(date(2026, 10, 31), -1)


def test_zile_bancare_implicit_ro_si_optiunea_target2():
    assert add_banking_days(date(2026, 11, 27), 2) == date(2026, 12, 3)
    assert add_banking_days(date(2026, 11, 27), 2, kind="target2") == date(2026, 12, 1)
    assert add_banking_days(date(2026, 4, 3), 1, kind="target2") == date(2026, 4, 7)   # Good Friday + Easter Monday


def test_business_days_between():
    assert business_days_between(date(2026, 11, 17), date(2026, 11, 18)) == 1
    assert business_days_between(date(2026, 11, 27), date(2026, 12, 2)) == 1
    assert business_days_between(date(2026, 12, 2), date(2026, 11, 27)) == 0


def test_roll_same_hour_art_8_alin_10():
    assert roll_same_hour(ts(2026, 11, 28, 16)) == ts(2026, 12, 2, 16)
    assert roll_same_hour(ts(2026, 11, 27, 16)) == ts(2026, 11, 27, 16)


def test_add_months_conventia_ultima_zi():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2027, 1, 31), 13) == date(2028, 2, 29)
    assert add_months(date(2025, 9, 15), 13) == date(2026, 10, 15)


def test_months_between():
    assert months_between(date(2025, 9, 15), date(2026, 10, 15)) == 13
    assert months_between(date(2025, 9, 15), date(2026, 10, 14)) == 12
    assert months_between(date(2026, 10, 15), date(2025, 9, 15)) == -13
    assert months_between(date(2026, 1, 31), date(2026, 2, 28)) == 1


# ---------------------------------------------------------------- formatarea textelor (engleză)


def test_sumele_au_codul_monedei_intai_virgula_la_mii_si_punct_la_zecimale():
    assert fmt_money(3200, "RON") == "RON 3,200.00"
    assert fmt_money(1234567.891, "EUR") == "EUR 1,234,567.89"
    assert fmt_money(0.5, "RON") == "RON 0.50"
    assert fmt_num(0.7) == "0.70" and fmt_num(1.5, 1) == "1.5" and fmt_num(12000, 0) == "12,000"


def test_datele_sunt_zi_luna_an_si_ora_romaniei_pe_24h():
    assert fmt_d(date(2026, 10, 29)) == "29 Oct 2026"
    assert fmt_d(date(2026, 12, 2)) == "2 Dec 2026"                     # ziua fără zero în față
    assert fmt_dt(ts(2026, 10, 29, 23, 59, 59)) == "29 Oct 2026, 23:59"
    assert fmt_dt(ts(2027, 1, 4, 9, 5, 0)) == "4 Jan 2027, 09:05"
    # 26.10.2026 22:30 UTC = 27.10.2026 00:30 ora României
    utc = datetime(2026, 10, 26, 22, 30, tzinfo=UTC)
    assert fmt_dt(utc) == "27 Oct 2026, 00:30" and fmt_d(utc) == "27 Oct 2026"
    assert fmt_dt(datetime(2026, 6, 15, 21, 0, tzinfo=UTC)) == "16 Jun 2026, 00:00"   # ora de vară, +3


# ---------------------------------------------------------------- proprietăți


moments = st.datetimes(min_value=datetime(2025, 1, 1), max_value=datetime(2028, 12, 31), timezones=st.just(TZ))


@settings(max_examples=300, deadline=None)
@given(moments)
def test_proprietate_t1_e_mereu_sfarsitul_primei_zile_lucratoare(dt):
    due = end_of_next_business_day(dt)
    start = cal.to_local(dt).date()
    assert due.tzinfo is not None and due.time().isoformat() == "23:59:59"
    assert due.date() > start and is_business_day(due.date())
    d = start + timedelta(days=1)
    while d < due.date():
        assert not is_business_day(d)
        d += timedelta(days=1)
    assert next_business_day(dt) == due.date()


@settings(max_examples=200, deadline=None)
@given(st.dates(min_value=date(2025, 1, 1), max_value=date(2028, 6, 30)), st.integers(min_value=0, max_value=40))
def test_proprietate_add_business_days_numara_exact_n_zile(d, n):
    out = add_business_days(d, n)
    assert business_days_between(d, out) == n
    assert n == 0 or is_business_day(out)
