"""Identificatori, normalizare și calendar (vectorii din docs/context/12 și 11)."""

from __future__ import annotations

import random
from datetime import date, datetime, timezone

import pytest

from versoml.data import artifacts as art
from versoml.data import ids
from versoml.data.calendar_ro import TZ, end_of_next_business_day, within_13_months
from versoml.data.text import fold, has_cedilla, normalize_ro, strip_diacritics


def test_cnp_vectors_from_docs():
    for ok in ["1630615123457", "6010315431239", "1900101401091"]:
        assert ids.validate_cnp(ok, allow_test_counties=False, today=date(2026, 10, 28)) == []
    assert ids.generate_cnp(date(2001, 3, 15), "F", 43, 123) == "6010315431239"
    assert ids.generate_cnp(date(1990, 1, 1), "M", 40, 109) == "1900101401091"   # rest 10 -> 1
    assert ids.validate_cnp("1630615123458", today=date(2026, 10, 28)) == ["wrong check digit"]


def test_generated_cnps_are_test_cnps():
    rng = random.Random(3)
    for _ in range(300):
        cnp = ids.generate_cnp(date(rng.randint(1950, 2005), rng.randint(1, 12), rng.randint(1, 28)), rng.choice("MF"),
                               rng.choice(ids.TEST_COUNTIES), rng.randint(1, 999))
        assert ids.cnp_checksum_ok(cnp) and ids.is_test_cnp(cnp)
        assert ids.validate_cnp(cnp, today=date(2026, 10, 28)) == []
        assert any("county" in e for e in ids.validate_cnp(cnp, allow_test_counties=False, today=date(2026, 10, 28)))


def test_stdnum_rejects_test_counties():
    from stdnum.ro import cnp as stdnum_cnp

    cnp = ids.generate_cnp(date(1985, 5, 5), "M", 75, 12)
    assert not stdnum_cnp.is_valid(cnp)


def test_cui_vectors_and_invalid_generation():
    for ok in ["18547290", "RO 185 472 90", "12345674", "RO12345674"]:
        assert ids.validate_cui(ok) == []
    assert ids.validate_cui("18547291") == ["wrong check digit"]
    rng = random.Random(5)
    for _ in range(500):
        cui = ids.generate_invalid_cui(rng, rng.randint(3, 10))
        assert ids.validate_cui(cui) == ["wrong check digit"]
    assert not ids.cui_checksum_ok(art.SHELL_COMPANY_CUI)
    assert not ids.cui_checksum_ok(art.CRYPTO_EXCHANGE_CUI)


def test_iban_vectors_and_fictive_banks():
    assert ids.validate_iban_ro("RO54RZBR0000060012345678") == []
    assert ids.validate_iban_ro("RO54 RZBR 0000 0600 1234 5678") == []
    assert ids.validate_iban_ro("RO55RZBR0000060012345678") == ["wrong check digits (mod 97)"]
    rng = random.Random(1)
    for bank in ids.FICTIVE_BANKS:
        for _ in range(100):
            iban = ids.generate_iban(rng, bank)
            assert ids.validate_iban_ro(iban) == [] and ids.iban_bank_code(iban) == bank
    assert ids.mask_iban("RO54RZBR0000060012345678").endswith("5678")


@pytest.mark.parametrize("value,expected", [
    ("https://livrare-bancademo.example/colet/RO4471", "livrare-bancademo.example"),
    ("plata.livrare-bancademo.example", "livrare-bancademo.example"),
    ("http://www.bancadem0-plati.test:8080/x?y=1", "bancadem0-plati.test"),
    ("magazin.com.ro", "magazin.com.ro"),
    ("a.b.magazin.com.ro", "magazin.com.ro"),
])
def test_registered_domain(value, expected):
    assert ids.registered_domain(value) == expected


def test_phone_and_ip_conventions():
    assert ids.normalize_phone("0700 000 111") == "+40700000111"
    assert ids.normalize_phone("0040700000222") == "+40700000222"
    assert ids.normalize_phone("+40 700 000 111") == art.SCAM_PHONE_SECURITATE
    assert ids.is_test_net_ip("203.0.113.7") and ids.is_test_net_ip("192.0.2.1") and ids.is_test_net_ip("198.51.100.9")
    assert not ids.is_test_net_ip("8.8.8.8")
    assert all(ids.is_reserved_domain(d) for d in art.SHARED_ARTIFACTS["scam_domains"].values())


def test_shared_artifact_names_are_exact():
    assert art.LEGIT_BRAND_DOMAIN == "bancademo.example" and art.LEGIT_COURIER_DOMAIN == "curierdemo.example"
    assert art.SHARED_ARTIFACTS["scam_domains"] == {
        "demo_t1": "livrare-bancademo.example", "card_visa_secure": "bancadem0-plati.test",
        "inel_carausi": "confirmare-colet-demo.example", "vishing_securitate": "securitate-bancademo.test"}
    assert art.SCAM_PHONE_SECURITATE == "+40700000111" and art.SCAM_PHONE_CONT_SIGUR == "+40700000222"
    assert art.SHELL_COMPANY_NAME == "EXPRES LIVRARE DEMO SRL"
    assert art.DEMO_SMS_TEXT == ("Your parcel could not be delivered. Confirm your address and pay the RON 2.99 delivery fee: "
                                 "https://livrare-bancademo.example/colet/RO4471")
    assert art.BANK_NAME == "Demo Bank" and art.DEMO_URL in art.DEMO_SMS_TEXT


def test_diacritics_normalization():
    assert normalize_ro("Ştefan Ţăranu, ţară") == "Ștefan Țăranu, țară"
    assert not has_cedilla(normalize_ro("şţŞŢ"))
    assert strip_diacritics("Ștefănescu-Țăranu îngână") == "Stefanescu-Taranu ingana"
    assert fold("Ştefan  ŢĂRANU") == fold("Ștefan Țăranu") == "stefan taranu"


@pytest.mark.parametrize("notified,deadline", [
    (datetime(2026, 10, 23, 9, 12, tzinfo=TZ), "2026-10-26T23:59:59+02:00"),   # DT-02: weekend + ora de iarnă
    (datetime(2026, 10, 28, 10, 0, tzinfo=TZ), "2026-10-29T23:59:59+02:00"),
    (datetime(2026, 11, 27, 12, 0, tzinfo=TZ), "2026-12-02T23:59:59+02:00"),   # 30.11 și 1.12 nelucrătoare
    (datetime(2026, 4, 9, 12, 0, tzinfo=TZ), "2026-04-14T23:59:59+03:00"),     # Paștele ortodox 2026
    (datetime(2026, 5, 29, 8, 30, tzinfo=TZ), "2026-06-02T23:59:59+03:00"),    # Rusalii + 1 iunie
    (datetime(2025, 12, 24, 9, 0, tzinfo=TZ), "2025-12-29T23:59:59+02:00"),    # Crăciun
    (datetime(2025, 12, 31, 11, 0, tzinfo=TZ), "2026-01-05T23:59:59+02:00"),   # Anul Nou
    (datetime(2026, 1, 5, 9, 30, tzinfo=TZ), "2026-01-08T23:59:59+02:00"),     # Boboteaza, Sf. Ioan
    (datetime(2026, 10, 25, 10, 0, tzinfo=TZ), "2026-10-26T23:59:59+02:00"),   # notificare duminică
    (datetime(2026, 10, 27, 22, 30, tzinfo=timezone.utc), "2026-10-29T23:59:59+02:00"),  # UTC -> 28.10 ora RO
])
def test_t1_deadline(notified, deadline):
    assert end_of_next_business_day(notified).isoformat() == deadline


def test_13_months_inclusive():
    ex = datetime(2025, 9, 15, 12, tzinfo=TZ)
    assert within_13_months(ex, datetime(2026, 10, 15, 23, tzinfo=TZ))
    assert not within_13_months(ex, datetime(2026, 10, 16, 0, 30, tzinfo=TZ))
