"""Orchestrarea: extragerea artefactelor din SMS și investigația în paralel, fără rețea pe țintele sintetice."""

from __future__ import annotations

import asyncio
import sys

from versoml.osint import base, domain
from versoml.osint.base import SIGNAL_ORDER
from versoml.osint.investigate import extract_artifacts, investigate, plan

inv = sys.modules["versoml.osint.investigate"]  # numele pachetului `investigate` e funcția publică

from .conftest import DEMO_T1_SMS


def test_extract_artifacts_from_demo_sms():
    found = extract_artifacts(DEMO_T1_SMS)
    assert found["urls"] == ["https://livrare-bancademo.example/confirmare?id=7731"]
    assert found["domains"] == ["livrare-bancademo.example"]
    assert found["phones"] == ["+40700000111"]
    assert found["cuis"] == ["44712025"]
    assert found["companies"] == ["EXPRES LIVRARE DEMO SRL"]
    assert found["ibans"] == []


def test_extract_artifacts_more_formats():
    text = ("Plătește în RO49 AAAA 1B31 0075 9384 0000 (S.C. TRANZIT RAPID DEMO S.R.L., CIF RO9000000208). "
            "Sună la +40 700 000 222 sau intră pe bancadem0-plati.test/plata ori www.securitate-bancademo.test; "
            "suma 3.200 lei, data 28.10.2026, ora 14:02.")
    found = extract_artifacts(text)
    assert found["ibans"] == ["RO49AAAA1B31007593840000"]
    assert found["cuis"] == ["9000000208"]
    assert found["phones"] == ["+40700000222"]
    assert "https://bancadem0-plati.test/plata" in found["urls"]
    assert {"bancadem0-plati.test", "www.securitate-bancademo.test"} <= set(found["domains"])
    assert found["companies"] == ["TRANZIT RAPID DEMO S.R.L."]


def test_extract_artifacts_excludes_victim_identifiers():
    text = "Clientul are IBAN RO54RZBR0000060012345678 și telefon 0721 000 111; escrocul: 0700 000 111"
    found = extract_artifacts(text, exclude={"RO54RZBR0000060012345678", "+40721000111"})
    assert found["ibans"] == [] and found["phones"] == ["+40700000111"]


async def test_investigate_demo_sms_red_without_network(no_network):
    results = await investigate(extract_artifacts(DEMO_T1_SMS))
    assert not no_network.calls, no_network.calls
    red = {r.tool for r in results if r.signal == "rosu"}
    assert {"rdap_domain", "ct_certificates", "lookalike_score", "fetch_page", "page_similarity", "phone_intel",
            "anaf_company", "news_search"} <= red
    order = [SIGNAL_ORDER[r.signal] for r in results]
    assert order == sorted(order) and results[0].signal == "rosu"
    assert all(isinstance(r, base.ToolResult) for r in results)
    lookalike = next(r for r in results if r.tool == "lookalike_score")
    assert lookalike.data["score"] >= 0.85 and {"young_domain", "young_cert"} <= {
        e["feature"] for e in lookalike.data["explanations"]}
    ip = next(r for r in results if r.tool == "ip_geo")
    assert ip.args["ip"] == "203.0.113.45" and ip.signal == "galben"
    similarity = next(r for r in results if r.tool == "page_similarity")
    assert similarity.data["score"] >= 0.7
    assert sum(1 for r in results if r.tool == "openphish_check") == 1


async def test_investigate_per_tool_timeout(monkeypatch, no_network):
    async def slow(domain_name):
        await asyncio.sleep(5)

    monkeypatch.setattr(domain, "rdap_domain", slow)
    results = await investigate({"domains": ["livrare-bancademo.example"]}, timeout_s=0.2)
    rdap = next(r for r in results if r.tool == "rdap_domain")
    assert rdap.ok is False and rdap.error == "timeout"
    assert any(r.tool == "dns_records" and r.ok for r in results)


async def test_investigate_never_raises_on_bad_input(no_network):
    results = await investigate({"domains": ["%%%", ""], "urls": ["nu-e-url"], "phones": ["abc"], "cuis": ["x"],
                                 "ibans": ["123"], "companies": [""]})
    assert isinstance(results, list) and all(isinstance(r, base.ToolResult) for r in results)
    assert await investigate(None) == []


def test_plan_is_fixed_and_keyed_tools_only_with_keys(settings_with):
    artifacts = {"urls": ["https://livrare-bancademo.example/x"], "phones": ["0700 000 111"], "cuis": ["44712025"]}
    steps = plan(artifacts)
    tools = {s["tool"] for s in steps}
    assert {"rdap_domain", "fetch_page", "page_similarity", "lookalike_score", "phone_intel", "anaf_company"} <= tools
    assert "urlscan_search" not in tools and "virustotal_domain" not in tools
    with settings_with(urlscan_api_key="test", virustotal_api_key="test"):
        keyed = {s["tool"] for s in plan(artifacts)}
    assert {"urlscan_search", "virustotal_domain"} <= keyed


async def test_call_tool_investigate_and_extract(no_network):
    found = await base.call_tool("extract_artifacts", {"text": DEMO_T1_SMS})
    assert found.ok and found.data["phones"] == ["+40700000111"]
    results = await base.call_tool("investigate", {"artifacts": {"phones": ["+40700000111"]}})
    assert [r.tool for r in results] == ["phone_intel"] and results[0].signal == "rosu"


async def test_singular_artifact_keys_are_accepted(no_network):
    results = await investigate({"company": "EXPRES LIVRARE DEMO SRL", "cuis": ["44712025"]})
    assert {r.tool for r in results} == {"sanctions_screen", "news_search", "anaf_company"}
    assert inv._normalize_artifacts({"companys": ["X SRL"]})["companies"] == ["X SRL"]


def test_artifact_limits():
    many = {"domains": [f"d{i}.example" for i in range(20)]}
    normalized = inv._normalize_artifacts(many)
    assert len(normalized["domains"]) <= inv.MAX_PER_KIND * 2
