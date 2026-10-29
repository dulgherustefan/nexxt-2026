"""The standard formats the agent normalizes its inputs to."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from versoml.contracts import Money
from versoml.shared import canonical as K


@pytest.mark.parametrize("raw, value, cur", [
    ("3.200,00", 3200.0, "RON"), ("3,200.00", 3200.0, "RON"), ("3200", 3200.0, "RON"), ("2,99", 2.99, "RON"),
    (650, 650.0, "EUR"),
])
def test_money_reads_both_decimal_conventions(raw, value, cur):
    assert K.money(raw, "€" if cur == "EUR" else "lei") == Money(value=value, currency=cur)


def test_currency_words_become_iso_codes():
    assert [K.currency(w) for w in ("lei", "RON", "€", "euro", "usd", "")] == ["RON", "RON", "EUR", "EUR", "USD", "RON"]
    assert K.currency("doubloons", default=None) is None


def test_the_claimed_amount_is_in_the_payment_currency_then_nearest():
    mentions = [Money(value=2.99, currency="RON"), Money(value=3200, currency="RON"), Money(value=650, currency="EUR")]
    assert K.closest_amount(mentions, Money(value=3200, currency="RON")).value == 3200
    # a EUR payment picks the EUR amount, even though 2.99 is nearer in value
    assert K.closest_amount(mentions, Money(value=640, currency="EUR")) == Money(value=650, currency="EUR")
    assert K.closest_amount([], Money(value=1, currency="RON")) is None


@pytest.mark.parametrize("raw, out", [
    ("0712 345 678", "+40712345678"), ("+40 712-345-678", "+40712345678"), ("0040712345678", "+40712345678"),
    ("40712345678", "+40712345678"), ("+44 20 7946 0958", "+442079460958"), ("<TELEFON_1>", None), ("12345", None),
])
def test_phones_become_e164(raw, out):
    assert K.e164(raw) == out


def test_phone_mask_keeps_country_and_last_digits():
    assert K.mask_phone("0712345678") == "+40 7•• ••• 678"


@pytest.mark.parametrize("raw, out", [
    ("https://WWW.Livrare-BancaDemo.example/colet/RO4471?x=1", "livrare-bancademo.example"),
    ("livrare-bancademo.example.", "livrare-bancademo.example"),
    ("bancă-demo.ro", "xn--banc-demo-tcb.ro"),
    ("<URL_1>", None), ("not a host", None),
])
def test_hosts_are_canonical(raw, out):
    assert K.host(raw) == out


def test_iban_check_digits_and_one_mask():
    good = "RO49AAAA1B31007593840000"
    assert K.iban("ro49 aaaa 1b31 0075 9384 0000") == good
    assert K.iban("RO48AAAA1B31007593840000") is None  # one digit off: the mod-97 check fails
    assert K.mask_iban(good) == "RO49 AAAA •••• 0000"


@pytest.mark.parametrize("eci, scheme, out", [
    ("05", "visa", "authenticated"), ("5", "visa", "authenticated"), ("06", "visa", "attempted"),
    ("07", "visa", "not_authenticated"), ("02", "mastercard", "authenticated"), ("01", "mastercard", "attempted"),
    ("00", "mastercard", "not_authenticated"),
    ("05", "mastercard", None),  # a Visa code on a Mastercard is not read as anything
    (None, "visa", None), ("05", None, None),
])
def test_eci_is_read_against_the_card_scheme(eci, scheme, out):
    assert K.three_ds(eci, scheme) == out


def test_local_time_follows_summer_time():
    assert K.local_noon(date(2026, 1, 15)).utcoffset().total_seconds() == 2 * 3600
    assert K.local_noon(date(2026, 7, 15)).utcoffset().total_seconds() == 3 * 3600
    # a time without an offset is Bucharest time already
    assert K.local(datetime(2026, 7, 15, 9, 0)).isoformat() == "2026-07-15T09:00:00+03:00"  # noqa: DTZ001


@pytest.mark.parametrize("channel, kind, scenario, pos, out", [
    ("transfer", "app", "cont_sigur", None, "manipulation_of_payer"),
    ("transfer", "neautorizata", "phishing_link", None, "payment_order_issued_by_fraudster"),
    ("card", "neautorizata", "card_ecom_fara_3ds", "ecommerce", "card_details_theft"),
    ("card", "neautorizata", None, "contactless", "card_lost_or_stolen"),
    ("card", "disputa_comerciant", "marfa_nelivrata", "ecommerce", None),
    ("transfer", "eroare_procesare", "plata_dubla", None, None),
])
def test_eba_fraud_type(channel, kind, scenario, pos, out):
    assert K.eba_fraud_type(channel, kind, scenario, pos) == out
