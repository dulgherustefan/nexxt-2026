"""Baza: contractul ToolResult, registrul pentru MCP, cache-ul, modurile și reîncercările."""

from __future__ import annotations

import json
import re
from datetime import timedelta

import httpx
import pytest

from versoml.osint import base
from versoml.osint.base import FIXTURE_NOW, FIXTURES_DIR, Interp, ToolResult, is_synthetic_target

SPEC_TOOLS = {
    "web_search", "fetch_page", "rdap_domain", "dns_records", "ct_certificates", "wayback_first_seen", "ip_geo",
    "openphish_check", "anaf_company", "sanctions_screen", "phone_intel", "lookalike_score", "page_similarity",
    "validate_iban", "investigate",
}
EXTRA_TOOLS = {"news_search", "urlhaus_check", "urlscan_search", "virustotal_domain", "safe_browsing_check",
               "bnr_fx_rates", "page_similarity_url", "extract_artifacts"}


def test_toolresult_fields_match_docs_06():
    assert set(ToolResult.model_fields) == {
        "tool", "args", "ok", "data", "summary", "signal", "source_url", "retrieved_at", "mode", "latency_ms", "error"}
    result = ToolResult(tool="x", ok=True)
    assert result.mode == "offline" and result.signal == "neutru" and result.retrieved_at.tzinfo is not None
    finding = ToolResult(tool="rdap_domain", args={"domain": "a.example"}, ok=True, summary="s", signal="rosu").as_finding()
    assert finding.target == "a.example" and finding.signal == "rosu"


def test_registry_lists_all_tools_with_schemas():
    tools = {t["name"]: t for t in base.list_tools()}
    assert SPEC_TOOLS | EXTRA_TOOLS <= set(tools)
    for spec in tools.values():
        assert spec["description"] and spec["input_schema"]["type"] == "object"
        assert spec["effect"] == "citire"
    assert tools["rdap_domain"]["input_schema"]["required"] == ["domain"]
    assert "artifacts" in tools["investigate"]["input_schema"]["properties"]
    assert tools["anaf_company"]["zones"] == ["aml"]
    assert base.get_tool("lookalike_score").is_async is False


async def test_call_tool_validates_and_never_raises():
    result = await base.call_tool("lookalike_score", {"domain": "livrare-bancademo.example"})
    assert result.ok and result.signal == "rosu"
    bad = await base.call_tool("rdap_domain", {"nu_exista": 1})
    assert bad.ok is False and "Argumente invalide" in bad.summary
    unknown = await base.call_tool("tool_inexistent", {})
    assert unknown.ok is False


def test_cache_ttl_and_stale(tmp_path):
    cache = base.Cache(tmp_path / "c.db")
    cache.put("t", "k", {"a": 1}, "https://sursa", ttl_s=60)
    hit = cache.get("t", "k")
    assert hit and hit.raw == {"a": 1} and not hit.stale
    cache.put("t", "old", {"b": 2}, None, ttl_s=-1)
    assert cache.get("t", "old") is None
    stale = cache.get("t", "old", allow_stale=True)
    assert stale and stale.stale and stale.raw == {"b": 2}


def _build(raw, ctx):
    return Interp({"value": raw["value"], "mode_seen": ctx.mode}, f"valoarea {raw['value']}", "galben")


async def test_run_source_fixture_mode_without_fixture_is_offline(settings_with):
    async def fetch():
        raise AssertionError("în modul fixture nu se apelează sursa")

    with settings_with(versoml_osint_mode="fixture"):
        result = await base.run_source("tool_test", {"x": 1}, key="nimic", fetch=fetch, build=_build, ttl_s=60,
                                       label="Test")
    assert result.ok is False and result.mode == "offline" and result.error == "fixture lipsă"


async def test_run_source_live_then_cache():
    calls = []

    async def fetch():
        calls.append(1)
        return {"value": 7}, "https://sursa.invalid"

    first = await base.run_source("tool_test", {}, key="k1", fetch=fetch, build=_build, ttl_s=60, label="Test")
    second = await base.run_source("tool_test", {}, key="k1", fetch=fetch, build=_build, ttl_s=60, label="Test")
    assert (first.mode, second.mode) == ("live", "cache")
    assert second.data["value"] == 7 and len(calls) == 1


async def test_run_source_auto_falls_back_to_stale_cache_then_fixture():
    base.get_cache().put("tool_test", "k2", {"value": 3}, None, ttl_s=-1)

    async def failing():
        raise httpx.ConnectError("jos")

    stale = await base.run_source("tool_test", {}, key="k2", fetch=failing, build=_build, ttl_s=60, label="Test")
    assert stale.ok and stale.mode == "cache" and stale.data["cache_stale"] is True
    # fără cache: cade pe înregistrarea locală (aici, RDAP-ul sintetic)
    from versoml.osint.domain import _build_rdap

    fixture = await base.run_source("rdap_domain", {"domain": "bancademo.example"}, key="bancademo.example",
                                    fetch=failing, build=_build_rdap, ttl_s=60, label="RDAP")
    assert fixture.ok and fixture.mode == "fixture" and fixture.data["live_error"]


async def test_run_source_live_mode_does_not_use_fixture(settings_with):
    async def failing():
        raise httpx.ConnectError("jos")

    from versoml.osint.domain import _build_rdap

    with settings_with(versoml_osint_mode="live"):
        result = await base.run_source("rdap_domain", {"domain": "bancademo.example"}, key="bancademo.example",
                                       fetch=failing, build=_build_rdap, ttl_s=60, label="RDAP")
    assert result.ok is False and result.mode == "live" and "nu a răspuns" in result.summary


async def test_missing_key_is_offline_with_romanian_summary():
    async def fetch():
        raise AssertionError("fără cheie nu se apelează sursa")

    result = await base.run_source("tool_test", {}, key="k", fetch=fetch, build=_build, ttl_s=60, label="Sursa X",
                                   missing_key="URLSCAN_API_KEY")
    assert result.ok is False and result.mode == "offline"
    assert "necesită cheie URLSCAN_API_KEY" in result.summary


async def test_http_request_retries_5xx_then_succeeds(mock_http):
    statuses = iter([503, 429, 200])
    calls = mock_http(lambda request: httpx.Response(next(statuses), json={"ok": True}))
    response = await base.http_request("GET", "https://api.invalid/x")
    assert response.status_code == 200 and len(calls) == 3
    assert calls[0].headers["user-agent"] == base.USER_AGENT


async def test_http_request_does_not_retry_4xx(mock_http):
    calls = mock_http(lambda request: httpx.Response(401))
    response = await base.http_request("GET", "https://api.invalid/y")
    assert response.status_code == 401 and len(calls) == 1


@pytest.mark.parametrize("value, expected", [
    ("livrare-bancademo.example", True),
    ("https://bancadem0-plati.test/plata", True),
    ("203.0.113.45", True),
    ("+40 700 000 111", True),
    ("0700000222", True),
    ("EXPRES LIVRARE DEMO SRL", True),
    ("9000000208", True),
    ("RO49BDEM0000000000000001", True),
    ("Caută „Banca Demo” phishing", True),
    ("raiffeisen.ro", False),
    ("8.8.8.8", False),
    ("+40 721 000 000", False),
    ("magazin online pantofi", False),
])
def test_is_synthetic_target(value, expected):
    assert is_synthetic_target(value) is expected


def test_fixture_clock_and_scam_domain_age():
    assert FIXTURE_NOW.isoformat() == "2026-10-28T12:00:00+02:00"
    raw = json.loads((FIXTURES_DIR / "rdap_domain" / "livrare-bancademo.example.json").read_text(encoding="utf-8"))
    created = base.parse_dt(raw["raw"]["events"][0]["eventDate"])
    assert FIXTURE_NOW - created == timedelta(hours=6)


def test_fixtures_are_synthetic_and_on_reserved_names():
    real_domain = re.compile(r"\b[a-z0-9-]+\.(?:ro|com|net|org|eu)\b")
    allowed = {"rdap.org", "crt.sh", "ip-api.com", "anaf.ro", "bnr.ro", "openphish.com", "cloudflare-dns.com",
               "archive.org"}
    for path in FIXTURES_DIR.rglob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if path.parent.name == "bnr_fx_rates":
            continue
        assert payload.get("synthetic") is True, path
        text = json.dumps(payload.get("raw", {}), ensure_ascii=False)
        for match in real_domain.findall(text.lower()):
            assert any(match.endswith(a) for a in allowed), (path, match)


def test_no_cedilla_in_osint_sources_and_fixtures():
    bad = re.compile("[şţŞŢ]")
    roots = [base.PACKAGE_DIR]
    for root in roots:
        for path in root.rglob("*"):
            if path.suffix in {".py", ".json", ".html", ".md"}:
                text = path.read_text(encoding="utf-8")
                assert not bad.search(text), f"sedilă în {path}"


def test_normalize_ro_and_formatting():
    from versoml.osint.util import normalize_ro

    assert normalize_ro("Ştefan plăteşte taxa") == "Ștefan plătește taxa"
    assert base.ro_count(1, "oră", "ore") == "1 oră"
    assert base.ro_count(6, "oră", "ore") == "6 ore"
    assert base.ro_count(20, "oră", "ore") == "20 de ore"
    assert base.fmt_age(6) == "6 ore" and base.fmt_age(24 * 44) == "44 de zile"
    assert base.ro_join(["a", "b", "c"]) == "a, b și c"
