"""M3: scorul de domeniu-sosie."""

from __future__ import annotations

import re

import pytest

from versoml.osint import lookalike
from versoml.osint.lookalike import lookalike_score, permutations, skeleton

CEDILLA = re.compile("[şţŞŢ]")


def test_scam_domain_scores_high_with_permutation_match():
    result = lookalike_score("livrare-bancademo.example")
    assert result.ok and result.data["score"] >= 0.85 and result.signal == "rosu"
    assert result.data["closest_brand"] == "bancademo.example"
    assert result.data["permutation_match"] == {"brand": "bancademo.example", "fuzzer": "dictionary"}
    reasons = [e["reason"] for e in result.data["explanations"]]
    assert any("combosquatting" in r for r in reasons) and any("livrare" in r for r in reasons)
    assert all(isinstance(e["weight"], float) for e in result.data["explanations"])
    assert result.data["weights"]["bias"] == lookalike.WEIGHTS["bias"]


@pytest.mark.parametrize("value", ["bancademo.example", "www.bancademo.example", "login.bancademo.example",
                                   "https://bancademo.example/autentificare", "curierdemo.example", "raiffeisen.ro"])
def test_protected_domains_are_legit(value):
    result = lookalike_score(value)
    assert result.data["legit"] is True and result.data["score"] <= 0.05 and result.signal == "verde"


@pytest.mark.parametrize("value", [
    "bancadem0-plati.test",          # 0 în loc de o + cuvânt de plată
    "securitate-bancademo.test",     # combosquatting
    "xn--bncademo-16g.example",      # „а” chirilic (punycode)
    "bаncademo.example",             # același domeniu, scris direct în Unicode
    "bancaderno.example",            # rn → m
    "banca-demo.example",            # cratimă
    "bancademo.test",                # alt TLD
    "bancademo-login.example",       # dicționar
])
def test_lookalikes_are_red(value):
    result = lookalike_score(value)
    assert result.data["score"] >= 0.85, (value, result.data["explanations"])
    assert result.signal == "rosu"


def test_punycode_is_decoded_and_explained():
    result = lookalike_score("xn--bncademo-16g.example")
    assert result.data["unicode_domain"] == "bаncademo.example"
    features = {e["feature"] for e in result.data["explanations"]}
    assert {"skeleton_equal", "idn"} <= features


def test_skeleton_collapses_confusables():
    assert skeleton("bаncademo") == skeleton("bancademo")      # chirilic
    assert skeleton("bancadern0") == skeleton("bancademo")      # rn→m, 0→o
    assert skeleton("ra1ffe1sen") == skeleton("raiffeisen")     # 1/i/l
    assert skeleton("banca-demo") == "bancademo"
    assert skeleton("vvebsite") == skeleton("website")


def test_unrelated_domains_are_low():
    for value in ("magazin-exemplu.example", "google.com", "stiri-demo.example"):
        result = lookalike_score(value)
        assert result.data["score"] < 0.5, value
        assert result.signal in ("verde", "neutru"), value


def test_keyword_domain_without_brand_is_yellow_not_red():
    result = lookalike_score("confirmare-colet-demo.example")
    assert result.data["score"] < 0.5 and result.signal == "galben"
    assert "Nu imită direct un domeniu protejat" in result.summary


def test_brand_in_subdomain_is_flagged():
    result = lookalike_score("bancademo.example.verificare-cont.test")
    assert result.data["score"] >= 0.5
    assert "brand_in_subdomain" in {e["feature"] for e in result.data["explanations"]}


def test_age_and_cert_raise_score():
    base_score = lookalike_score("securitate-bancademo.test").data["score"]
    aged = lookalike_score("securitate-bancademo.test", age_hours=6, cert_age_hours=5)
    assert aged.data["score"] > base_score
    features = {e["feature"] for e in aged.data["explanations"]}
    assert {"young_domain", "young_cert"} <= features


def test_custom_protected_list():
    result = lookalike_score("raiffeisen-plati.ro", protected=["raiffeisen.ro"])
    assert result.data["score"] >= 0.85 and result.data["closest_brand"] == "raiffeisen.ro"


def test_permutation_generator_covers_all_fuzzers():
    perms = permutations("bancademo.example")
    fuzzers = set(perms.values())
    assert {"addition", "bitsquatting", "homoglyph", "hyphenation", "insertion", "omission", "repetition",
            "replacement", "transposition", "vowel-swap", "subdomain", "tld-swap", "dictionary", "plural"} <= fuzzers
    for candidate, fuzzer in {"bancadem0.example": "homoglyph", "bancademo.test": "tld-swap",
                              "banca-demo.example": "hyphenation", "bancdemo.example": "omission",
                              "bnacademo.example": "transposition", "livrare-bancademo.example": "dictionary",
                              "xn--bncademo-16g.example": "homoglyph", "banca.demo.example": "subdomain"}.items():
        assert perms.get(candidate) == fuzzer, candidate
    assert "bancademo.example" not in perms


def test_explanations_are_romanian_without_cedilla():
    for value in ("livrare-bancademo.example", "xn--bncademo-16g.example", "bancadem0-plati.test"):
        result = lookalike_score(value, age_hours=30, cert_age_hours=20)
        assert not CEDILLA.search(result.summary)
        assert all(not CEDILLA.search(e["reason"]) for e in result.data["explanations"])
        assert "," in result.summary  # zecimale cu virgulă


def test_invalid_domain_fails_soft():
    result = lookalike_score("nu e un domeniu")
    assert result.ok is False and result.error
