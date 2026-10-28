"""Liste de amenințări: OpenPhish (fără cheie, cache 6 h) și sursele cu cheie (URLhaus, urlscan, VirusTotal, GSB)."""

from __future__ import annotations

import json

import httpx
import pytest

from versoml.osint import threatintel


async def test_openphish_synthetic_feed(no_network):
    listed = await threatintel.openphish_check("https://bancadem0-plati.test/plata")
    assert listed.signal == "rosu" and listed.data["match"] == "url"
    by_domain = await threatintel.openphish_check("confirmare-colet-demo.example")
    assert by_domain.signal == "rosu" and by_domain.data["listed"]
    fresh = await threatintel.openphish_check("https://livrare-bancademo.example/confirmare?id=7731")
    assert fresh.signal == "neutru" and fresh.data["listed"] is False
    assert "absența nu dovedește" in fresh.summary
    assert not no_network.calls


async def test_openphish_live_feed_is_cached(mock_http):
    feed = "https://phish-exemplu.invalid/login\nhttps://alt-phish.invalid/x\n"
    calls = mock_http(lambda request: httpx.Response(200, text=feed))
    first = await threatintel.openphish_check("https://phish-exemplu.invalid/login")
    second = await threatintel.openphish_check("curat.invalid")
    assert first.mode == "live" and first.signal == "rosu" and first.data["match"] == "url"
    assert second.mode == "cache" and second.signal == "neutru"
    assert len(calls) == 1 and str(calls[0].url) == threatintel.OPENPHISH_FEEDS[0]


async def test_openphish_falls_back_to_github_mirror(mock_http):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "openphish.com":
            return httpx.Response(503)
        return httpx.Response(200, text="https://oglinda.invalid/p\n")

    mock_http(handler)
    result = await threatintel.openphish_check("oglinda.invalid")
    assert result.signal == "rosu" and result.source_url == threatintel.OPENPHISH_FEEDS[1]


@pytest.mark.parametrize("call, key_name", [
    (lambda: threatintel.urlhaus_check("phish-exemplu.invalid"), "URLHAUS_AUTH_KEY"),
    (lambda: threatintel.urlscan_search("phish-exemplu.invalid"), "URLSCAN_API_KEY"),
    (lambda: threatintel.virustotal_domain("phish-exemplu.invalid"), "VIRUSTOTAL_API_KEY"),
    (lambda: threatintel.safe_browsing_check("https://phish-exemplu.invalid/x"), "GOOGLE_SAFE_BROWSING_KEY"),
])
async def test_missing_keys_are_offline(call, key_name, no_network):
    result = await call()
    assert result.ok is False and result.mode == "offline"
    assert f"necesită cheie {key_name}" in result.summary
    assert not no_network.calls


async def test_urlhaus_with_key(mock_http, settings_with):
    body = {"query_status": "ok", "url_count": 2, "firstseen": "2026-10-27 10:00:00 UTC",
            "urls": [{"url": "https://phish-exemplu.invalid/a", "url_status": "online", "threat": "malware_download"},
                     {"url": "https://phish-exemplu.invalid/b", "url_status": "offline", "threat": "malware_download"}]}
    calls = mock_http(lambda request: httpx.Response(200, json=body))
    with settings_with(urlhaus_auth_key="cheie-test-urlhaus"):
        result = await threatintel.urlhaus_check("phish-exemplu.invalid")
    assert result.mode == "live" and result.signal == "rosu" and result.data["online"] == 1
    assert calls[0].headers["auth-key"] == "cheie-test-urlhaus"
    assert str(calls[0].url).endswith("/v1/host/") and b"host=phish-exemplu.invalid" in calls[0].content


async def test_urlscan_with_key(mock_http, settings_with):
    body = {"total": 1, "results": [{"task": {"url": "https://phish-exemplu.invalid/", "time": "2026-10-28T08:00:00Z"},
                                     "page": {"url": "https://phish-exemplu.invalid/", "ip": "198.51.100.1", "asn": "AS64500"},
                                     "verdicts": {"overall": {"malicious": True}}, "result": "https://urlscan.invalid/r/1"}]}
    calls = mock_http(lambda request: httpx.Response(200, json=body))
    with settings_with(urlscan_api_key="cheie-test-urlscan"):
        result = await threatintel.urlscan_search("phish-exemplu.invalid")
    assert result.signal == "rosu" and result.data["malicious"] is True
    assert calls[0].headers["api-key"] == "cheie-test-urlscan" and calls[0].url.params["q"] == "domain:phish-exemplu.invalid"


async def test_virustotal_with_key(mock_http, settings_with):
    body = {"data": {"attributes": {"last_analysis_stats": {"malicious": 5, "suspicious": 1, "harmless": 60}}}}
    calls = mock_http(lambda request: httpx.Response(200, json=body))
    with settings_with(virustotal_api_key="cheie-test-vt"):
        result = await threatintel.virustotal_domain("https://sub.phish-exemplu.invalid/x")
    assert result.args == {"domain": "phish-exemplu.invalid"}
    assert result.signal == "rosu" and calls[0].headers["x-apikey"] == "cheie-test-vt"


async def test_safe_browsing_key_goes_in_header_not_url(mock_http, settings_with):
    calls = mock_http(lambda request: httpx.Response(200, json={"matches": [{"threatType": "SOCIAL_ENGINEERING"}]}))
    with settings_with(google_safe_browsing_key="cheie-test-gsb"):
        result = await threatintel.safe_browsing_check("https://phish-exemplu.invalid/x")
    assert result.signal == "rosu" and "SOCIAL_ENGINEERING" in result.summary
    assert calls[0].headers["x-goog-api-key"] == "cheie-test-gsb"
    assert "cheie-test-gsb" not in str(calls[0].url)
    sent = json.loads(calls[0].content)
    assert sent["threatInfo"]["threatEntries"] == [{"url": "https://phish-exemplu.invalid/x"}]
