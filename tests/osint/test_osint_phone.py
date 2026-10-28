"""Telefoane: E.164, tipul numărului, raportările publice."""

from __future__ import annotations

import pytest

from versoml.osint.phone import classify, phone_intel, search_query
from versoml.osint.util import normalize_phone


@pytest.mark.parametrize("raw", ["0700 000 111", "+40 700 000 111", "0040700000111", "40700000111", "(0700) 000-111"])
def test_e164_normalization(raw):
    assert normalize_phone(raw) == "+40700000111"


@pytest.mark.parametrize("raw", ["12345", "721123456", "", "3.200"])
def test_unparseable_numbers(raw):
    assert normalize_phone(raw) is None


@pytest.mark.parametrize("e164, kind", [
    ("+40721123456", "mobil"),
    ("+40211234567", "fix (București)"),
    ("+40264123456", "fix (geografic)"),
    ("+40800123456", "apel gratuit"),
    ("+40900123456", "tarif special"),
    ("+442071234567", "internațional"),
])
def test_number_type(e164, kind):
    info = classify(e164)
    assert info["type"] == kind and info["operator"] is None


def test_search_query_uses_all_formats():
    assert search_query("+40700000111") == '"0700000111" OR "+40700000111" OR "0700 000 111"'


async def test_scam_phone_reports(no_network):
    result = await phone_intel("0700 000 111")
    assert result.ok and result.mode == "fixture" and result.signal == "rosu"
    assert result.data["synthetic"] is True and result.data["fraud_reports"] == 2
    assert result.data["national"] == "0700 000 111"
    assert all(r["mentions_entity"] for r in result.data["reports"])
    assert not no_network.calls


async def test_second_scam_phone(no_network):
    result = await phone_intel("+40700000222")
    assert result.signal == "rosu" and result.data["report_count"] == 2


async def test_invalid_phone_fails_soft(no_network):
    result = await phone_intel("nu e telefon")
    assert result.ok is False
