"""Teste live (rețea reală, surse fără cheie). Rulează doar cu VERSOML_LIVE_TESTS=1."""

from __future__ import annotations

import pytest

from versoml.osint import crawl, domain, registry_ro, threatintel

pytestmark = pytest.mark.live


async def test_live_rdap_example_com(settings_with):
    with settings_with(versoml_osint_mode="live"):
        result = await domain.rdap_domain("example.com")
    assert result.ok and result.mode == "live" and result.data["created"].startswith("1995")


async def test_live_dns_example_com(settings_with):
    with settings_with(versoml_osint_mode="live"):
        result = await domain.dns_records("example.com")
    assert result.ok and result.data["A"]


async def test_live_bnr_rates(settings_with):
    with settings_with(versoml_osint_mode="live"):
        result = await registry_ro.bnr_fx_rates(30)
    assert result.ok and result.data["eur_ron"] > 4


async def test_live_anaf_not_found_for_unused_cui(settings_with):
    with settings_with(versoml_osint_mode="live"):
        result = await registry_ro.anaf_company("9000000402")
    assert result.ok and result.data["found"] is False


async def test_live_openphish_feed(settings_with):
    with settings_with(versoml_osint_mode="live"):
        result = await threatintel.openphish_check("nu-apare-in-feed.invalid")
    assert result.ok and result.data["feed_size"] > 0


async def test_live_fetch_example_com(settings_with):
    with settings_with(versoml_osint_mode="live"):
        result = await crawl.fetch_page("https://example.com/")
    assert result.ok and result.data["status"] == 200 and result.data["title"]
