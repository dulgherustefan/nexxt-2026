"""Registre RO: CUI și ANAF, IBAN, cursul BNR."""

from __future__ import annotations

import json

import httpx
import pytest

from versoml.osint import registry_ro
from versoml.osint.base import fixture_text
from versoml.osint.registry_ro import anaf_company, bnr_fx_rates, iban_check_digits, validate_cui, validate_iban


# vectorii din docs/context/12 §2.2
@pytest.mark.parametrize("value, errors", [
    ("18547290", []),
    ("RO 185 472 90", []),
    ("12345674", []),
    ("RO12345674", []),
    ("18547291", ["cifra de control greșită"]),
    ("01234567", ["începe cu 0"]),
    ("1", ["lungime în afara intervalului 2-10"]),
    ("RO1854729A", ["format: doar cifre (după eliminarea prefixului RO)"]),
])
def test_cui_checksum_vectors(value, errors):
    assert validate_cui(value) == errors


async def test_invalid_cui_is_red_without_calling_anaf(no_network):
    result = await anaf_company("44712025")  # EXPRES LIVRARE DEMO SRL (sintetic)
    assert result.ok and result.signal == "rosu" and result.mode == "offline"
    assert result.data["anaf_called"] is False and result.data["errors"] == ["cifra de control greșită"]
    assert "ANAF nu a fost interogat" in result.summary
    assert not no_network.calls


@pytest.mark.parametrize("cui, signal, name", [
    ("9000000100", "verde", "CURIER DEMO SA"),
    ("RO9000000208", "galben", "TRANZIT RAPID DEMO SRL"),
    ("9000000305", "rosu", "CASA DE SCHIMB EXEMPLU SRL"),
])
async def test_synthetic_registry_never_goes_live(cui, signal, name, no_network):
    result = await anaf_company(cui)
    assert result.mode == "fixture" and result.signal == signal and result.data["denumire"] == name
    assert not no_network.calls


async def test_anaf_live_parsing_found_and_not_found(mock_http):
    record = json.loads(fixture_text("anaf_company/9000000305.json"))["raw"]["found"][0]
    record["date_generale"]["cui"] = 9000000402
    record["date_generale"]["denumire"] = "FIRMA MOCK RADIATĂ SRL"

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body[0]["cui"] == 9000000402:
            return httpx.Response(200, json={"found": [record], "notFound": []})
        return httpx.Response(404, json={"found": [], "notFound": [body[0]["cui"]]})

    calls = mock_http(handler)
    found = await anaf_company("9000000402")
    assert found.mode == "live" and found.signal == "rosu" and found.data["radiat"] is True
    sent = json.loads(calls[0].content)
    assert str(calls[0].url) == registry_ro.ANAF_URL and sent[0]["cui"] == 9000000402 and len(sent[0]["data"]) == 10
    missing = await anaf_company("9000000500")
    assert missing.signal == "galben" and missing.data["found"] is False


def test_anaf_record_normalizes_cedilla():
    record = {"date_generale": {"cui": 1, "denumire": "FIRMA COŞBUC SRL", "stare_inregistrare": "INREGISTRAT",
                                "organFiscalCompetent": "Administraţia Fiscală"}}
    data = registry_ro.parse_anaf_record(record, now=None)
    assert data["denumire"] == "FIRMA COȘBUC SRL" and data["organ_fiscal"] == "Administrația Fiscală"


def test_iban_valid_known_bank():
    result = validate_iban("ro54 rzbr 0000 0600 1234 5678")
    assert result.data["valid"] and result.data["bank_name"] == "Raiffeisen Bank" and result.data["bank_confidence"] == "S"
    assert result.data["formatted"] == "RO54 RZBR 0000 0600 1234 5678"


def test_iban_synthetic_bank_codes():
    for code in ("BDEM", "XBNK", "YBNK", "ZBNK"):
        account = "0000000000007731"
        iban = "RO" + iban_check_digits("RO", code + account) + code + account
        result = validate_iban(iban)
        assert result.data["valid"] and result.data["synthetic"] is True, iban


@pytest.mark.parametrize("iban, bank", [
    ("RO61BDEM1777286093723598", "Banca Demo (sintetic)"),   # contul cărăușului din demo (versoml/data)
    ("RO65ZBNK9000000000777000", "Banca Z (sintetic)"),      # exchange-ul crypto sintetic
])
def test_demo_ibans_from_data_module(iban, bank):
    result = validate_iban(iban)
    assert result.data["valid"] and result.data["bank_name"] == bank and result.data["synthetic"] is True
    assert result.signal == "neutru" and "fictiv" in result.summary


@pytest.mark.parametrize("iban, valid, signal", [
    ("RO55RZBR0000060012345678", False, "galben"),       # mod 97
    ("RO54RZBR000006001234567", False, "galben"),        # 23 de caractere
    ("RO49AAAA1B31007593840000", True, "galben"),        # cod de bancă necunoscut
    ("DE89370400440532013000", True, "neutru"),          # IBAN de exemplu (DE)
    ("nu e iban", False, "galben"),
])
def test_iban_edge_cases(iban, valid, signal):
    result = validate_iban(iban)
    assert result.data["valid"] is valid and result.signal == signal


async def test_bnr_fixture_and_conversion(settings_with):
    with settings_with(versoml_osint_mode="fixture"):
        result = await bnr_fx_rates(30)
    assert result.mode == "fixture" and result.data["date"] == "2026-10-28"
    assert result.data["eur_ron"] == pytest.approx(5.3495)
    assert result.data["amount_ron"] == pytest.approx(160.48, abs=0.01)
    assert "1 EUR = 5,3495 lei" in result.summary


async def test_bnr_live_parse_and_ecb_fallback(mock_http):
    xml = fixture_text("bnr_fx_rates/nbrfxrates_2026-10-28.xml")
    state = {"bnr_ok": True}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "curs.bnr.ro":
            return httpx.Response(200, text=xml) if state["bnr_ok"] else httpx.Response(200, text="<html>prima pagină</html>")
        return httpx.Response(200, json={"amount": 1.0, "base": "EUR", "date": "2026-10-27", "rates": {"RON": 5.3488}})

    mock_http(handler)
    live = await bnr_fx_rates()
    assert live.mode == "live" and live.data["provider"] == "bnr" and live.data["rates"]["HUF"] == pytest.approx(0.014569)
    registry_ro_cache_clear()
    state["bnr_ok"] = False
    fallback = await bnr_fx_rates()
    assert fallback.data["provider"] == "ecb" and "BCE" in fallback.summary


def registry_ro_cache_clear():
    from versoml.osint.base import get_cache

    get_cache().clear()
