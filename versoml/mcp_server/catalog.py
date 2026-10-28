"""The MCP server's description for the website's /mcp page: tools by zone and ready-to-copy configurations."""

from __future__ import annotations

import json
import os

from versoml.config import ROOT

TOOLS = [
    ("versoml_rules_catalog", "both", "The rules catalog, with the legal basis and a confidence mark", "read"),
    ("versoml_t1_deadline", "both", "The refund deadline and the reply deadline, on the Romanian calendar", "compute"),
    ("versoml_verify_dossier", "both", "Verify an evidence file (SHA-256, Merkle, Ed25519)", "compute"),
    ("versoml_list_scenarios", "client", "The synthetic demo scenarios", "read"),
    ("versoml_open_case", "client", "Open and start a case", "creates a case"),
    ("versoml_case_status", "client", "Verdict, deadline, decisions with rule IDs", "read"),
    ("versoml_case_evidence", "client", "The evidence in the case ledger", "read"),
    ("versoml_approve", "client", "A person's signature on a decision", "human action"),
    ("versoml_counterfactual", "client", "Change one fact, see which decisions change", "compute"),
    ("versoml_check_letter", "client", "The wall's filter on a letter's text", "compute"),
    ("versoml_evaluate_rules", "client", "The rules engine on a JSON context", "compute"),
    ("versoml_domain_intel", "client", "Lookalike score, RDAP and CT for the domain in a text message", "public read"),
    ("versoml_wall_status", "client", "The wall's six layers", "read"),
    ("versoml_aml_leads", "aml", "AML leads from disputes", "read"),
    ("versoml_aml_lead", "aml", "The money graph, ML, OSINT, explanations, the draft STR", "read"),
    ("versoml_osint_investigate", "aml", "Live OSINT on a public identifier", "public read"),
    ("versoml_sanctions_screen", "aml", "Sanctions list screening", "public read"),
    ("versoml_company_lookup", "aml", "A company by CUI (ANAF)", "public read"),
    ("versoml_aml_decide", "aml", "The analyst's decision: STR, close, more information, HOLD", "human action"),
]


def mcp_info(client_url: str) -> dict:
    root = str(ROOT).replace("\\", "/")
    python = f"{root}/.venv/Scripts/python.exe" if os.name == "nt" else f"{root}/.venv/bin/python"
    desktop = {"mcpServers": {
        "versoml-client": {"command": python, "args": ["-m", "versoml.mcp_server", "--zone", "client"], "cwd": root},
        "versoml-aml": {"command": python, "args": ["-m", "versoml.mcp_server", "--zone", "aml"], "cwd": root},
    }}
    return {
        "tools": [{"name": n, "zone": z, "description": d, "effect": e} for n, z, d, e in TOOLS],
        "snippets": {
            "claude_desktop": json.dumps(desktop, indent=2),
            "cursor": json.dumps(desktop, indent=2),
            "http": "versoml mcp --zone client --transport http --port 8765",
        },
        "http_url": f"{client_url}/mcp/",
        "zones": {"client": "the client zone's tools; the AML tools are not listed",
                  "aml": "the AML zone's tools; nothing from them reaches the customer"},
    }
