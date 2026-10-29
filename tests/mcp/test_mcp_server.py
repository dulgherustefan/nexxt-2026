"""Serverul MCP: tool-urile sunt separate pe zone (zidul există și în MCP)."""

import asyncio

from versoml.contracts import Zone
from versoml.mcp_server.server import build_server


def _names(zone: Zone) -> set[str]:
    server = build_server(zone)
    tools = asyncio.run(server.list_tools())
    return {t.name for t in tools}


def test_client_server_has_no_aml_tools():
    names = _names(Zone.CLIENT)
    assert "versoml_open_case" in names and "versoml_check_letter" in names
    assert not any("aml" in n or n in ("versoml_osint_investigate", "versoml_sanctions_screen") for n in names)


def test_aml_server_has_no_case_tools():
    names = _names(Zone.AML)
    assert "versoml_aml_leads" in names and "versoml_osint_investigate" in names
    assert "versoml_open_case" not in names and "versoml_approve" not in names


def test_common_tools_in_both():
    for zone in (Zone.CLIENT, Zone.AML):
        assert {"versoml_rules_catalog", "versoml_t1_deadline", "versoml_verify_dossier"} <= _names(zone)


def test_new_intake_and_knowledge_tools_are_registered_per_zone():
    client = _names(Zone.CLIENT)
    assert {"versoml_intake", "versoml_kb_search", "versoml_kb_ask", "versoml_precedents"} <= client
    aml = _names(Zone.AML)
    assert "versoml_kb_search" in aml and not {"versoml_intake", "versoml_precedents", "versoml_kb_ask"} & aml


def test_catalog_lists_the_new_tools():
    from versoml.mcp_server.catalog import mcp_info

    tools = {t["name"]: t["zone"] for t in mcp_info("http://127.0.0.1:8000")["tools"]}
    assert tools["versoml_intake"] == "client" and tools["versoml_kb_search"] == "both"
    assert tools["versoml_precedents"] == "client"


def test_mcp_approve_only_proposes_and_cedar_denies_the_signature(monkeypatch):
    import json

    from versoml.mcp_server import server as mcp_server
    from versoml.shared.policy import clear_decisions, recent_decisions

    calls = []

    async def fake_api(zone, method, path, body=None):
        calls.append((method, path, body))
        if path.endswith("/proposals"):
            return {"ok": True, "signed": False, "proposal": {"action": body["action"], "fact_id": "EV-031"},
                    "detail": "Recorded as proposal EV-031."}
        return {"summary": {}, "interrupt": {"pending": True, "approval_token": "secret-ish"}, "facts": [
            {"fact_id": "EV-001", "kind": "bank.transaction", "source_tool": "bank-core", "summary": "s", "sha256": "ab" * 32,
             "content": {"payee_iban": "RO49AAAA1B31007593840000"}}]}

    monkeypatch.setattr(mcp_server, "_api", fake_api)
    clear_decisions()
    server = build_server(Zone.CLIENT)
    result = asyncio.run(server.call_tool("versoml_approve", {"case_id": "CT-2026-123456", "action": "approve"}))
    out = json.loads(result.content[0].text)
    assert out["signed"] is False and out["proposal"]["fact_id"] == "EV-031"
    assert "only-a-person-signs" in out["why_not_signed"]
    assert [c[1] for c in calls] == ["/api/cases/CT-2026-123456/proposals"]         # never the approve endpoint
    denied = [d for d in recent_decisions(10) if d.action == "mcp.cases.approve"]
    assert denied and not denied[0].allowed                                         # the wall page shows the denial

    status = json.loads(asyncio.run(server.call_tool("versoml_case_status", {"case_id": "CT-2026-123456"})).content[0].text)
    assert "approval_token" not in status["interrupt"]
    listed = asyncio.run(server.call_tool("versoml_case_evidence", {"case_id": "CT-2026-123456"}))
    evidence = [json.loads(c.text) for c in listed.content]
    assert evidence == [{"fact_id": "EV-001", "kind": "bank.transaction", "source_tool": "bank-core", "summary": "s",
                         "sha256": "ab" * 8}]


def test_catalog_says_mcp_approve_only_proposes():
    from versoml.mcp_server.catalog import mcp_info

    tools = {t["name"]: t for t in mcp_info("http://127.0.0.1:8000")["tools"]}
    assert tools["versoml_approve"]["effect"] == "proposes only"
