"""Descrierea serverului MCP pentru pagina /mcp din UI: tool-uri pe zone și configurări gata de copiat."""

from __future__ import annotations

import json

from versoml.config import ROOT

TOOLS = [
    ("versoml_rules_catalog", "ambele", "Catalogul regulilor cu temei și marcaj de încredere", "citire"),
    ("versoml_t1_deadline", "ambele", "Termenul T+1 și termenul de răspuns, pe calendarul RO", "calcul"),
    ("versoml_verify_dossier", "ambele", "Verifică un dosar de probe (SHA-256, Merkle, Ed25519)", "calcul"),
    ("versoml_list_scenarios", "client", "Scenariile sintetice de demo", "citire"),
    ("versoml_open_case", "client", "Deschide și pornește un caz", "creează caz"),
    ("versoml_case_status", "client", "Verdict, termen, decizii cu ID-uri de reguli", "citire"),
    ("versoml_case_evidence", "client", "Probele din registrul cazului", "citire"),
    ("versoml_approve", "client", "Semnătura umană pe o decizie", "acțiune umană"),
    ("versoml_counterfactual", "client", "Schimbă un fapt, vezi ce decizii se schimbă", "calcul"),
    ("versoml_check_letter", "client", "Filtrul zidului pe un text de scrisoare", "calcul"),
    ("versoml_evaluate_rules", "client", "Motorul de reguli pe un context JSON", "calcul"),
    ("versoml_domain_intel", "client", "Sosie, RDAP și CT pentru domeniul din SMS", "citire publică"),
    ("versoml_wall_status", "client", "Cele șase straturi ale zidului", "citire"),
    ("versoml_aml_leads", "aml", "Pistele AML din contestații", "citire"),
    ("versoml_aml_lead", "aml", "Graful banilor, ML, OSINT, ipoteze, ciorna RTS", "citire"),
    ("versoml_osint_investigate", "aml", "OSINT live pe un identificator public", "citire publică"),
    ("versoml_sanctions_screen", "aml", "Screening pe liste de sancțiuni", "citire publică"),
    ("versoml_company_lookup", "aml", "Firma după CUI (ANAF)", "citire publică"),
    ("versoml_aml_decide", "aml", "Decizia analistului: RTS, închidere, informații, HOLD", "acțiune umană"),
]


def mcp_info(client_url: str) -> dict:
    root = str(ROOT).replace("\\", "/")
    python = f"{root}/.venv/Scripts/python.exe"
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
        "zones": {"client": "tool-urile zonei client; AML nu apare", "aml": "tool-urile zonei AML; nimic nu ajunge la client"},
    }
