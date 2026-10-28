"""Contractul cu modulul de date: aceleași domenii, telefoane, CUI și IBAN-uri, fără rețea."""

from __future__ import annotations

import pytest

from versoml.osint import base
from versoml.osint.investigate import extract_artifacts, investigate
from versoml.osint.lookalike import lookalike_score
from versoml.osint.phone import phone_intel
from versoml.osint.registry_ro import anaf_company, validate_iban
from versoml.osint.sanctions import sanctions_screen

artifacts = pytest.importorskip("versoml.data.artifacts")


async def test_demo_sms_from_data_module_is_red_without_network(no_network):
    found = extract_artifacts(artifacts.DEMO_SMS_TEXT)
    assert found["urls"] == [artifacts.DEMO_URL]
    assert found["domains"] == [artifacts.SCAM_DOMAIN_DEMO]
    results = await investigate(found)
    red = {r.tool for r in results if r.signal == "rosu"}
    assert {"rdap_domain", "ct_certificates", "lookalike_score", "fetch_page", "page_similarity"} <= red
    assert not no_network.calls


@pytest.mark.parametrize("name", ["SCAM_DOMAIN_DEMO", "SCAM_DOMAIN_CARD", "SCAM_DOMAIN_INEL", "SCAM_DOMAIN_VISHING",
                                  "LEGIT_BRAND_DOMAIN", "LEGIT_COURIER_DOMAIN"])
def test_every_data_domain_has_fixtures(name):
    domain = getattr(artifacts, name)
    for tool in ("rdap_domain", "dns_records", "ct_certificates", "wayback_first_seen", "fetch_page", "news_search"):
        assert base.load_fixture(tool, [domain]) is not None, (tool, domain)
    legit = name.startswith("LEGIT")
    assert lookalike_score(domain).data["legit"] is legit


async def test_shell_company_and_exchange(no_network):
    shell = await anaf_company(artifacts.SHELL_COMPANY_CUI)
    assert artifacts.SHELL_COMPANY_CUI == "44712025"
    assert shell.signal == "rosu" and shell.data["anaf_called"] is False
    assert (await sanctions_screen(artifacts.SHELL_COMPANY_NAME)).signal == "verde"
    exchange = validate_iban(artifacts.CRYPTO_EXCHANGE_IBAN)
    assert exchange.data["bank_name"] == "Banca Z (sintetic)"
    assert validate_iban("RO61BDEM1777286093723598").data["bank_name"] == "Banca Demo (sintetic)"
    assert not no_network.calls


@pytest.mark.parametrize("name, signal", [("SCAM_PHONE_SECURITATE", "rosu"), ("SCAM_PHONE_CONT_SIGUR", "rosu"),
                                          ("BANK_OFFICIAL_PHONE", "neutru")])
async def test_data_phones(name, signal, no_network):
    result = await phone_intel(getattr(artifacts, name))
    assert result.ok and result.mode == "fixture" and result.signal == signal
    assert not no_network.calls
