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
