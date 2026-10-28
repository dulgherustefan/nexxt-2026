"""Serverul MCP VersoML: VersoML ca tool în Claude Desktop, Cursor sau orice client MCP.

Câte un server pe zonă (`--zone client` sau `--zone aml`), ca zidul să existe și în MCP:
- tool-urile deterministe (reguli, termene, filtrul zidului, domain-intel, OSINT, verificarea dosarului) rulează local;
- tool-urile de caz vorbesc prin HTTP cu procesul zonei (`versoml up`), deci MCP și UI văd aceeași stare;
- fiecare apel trece prin Cedar cu principalul `Mcp::"client"` sau `Mcp::"aml"`; tool-urile altei zone nici nu apar.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from versoml.config import get_settings
from versoml.contracts import Zone
from versoml.secrets import install_log_redaction

log = logging.getLogger("versoml.mcp")

INSTRUCTIONS = {
    Zone.CLIENT: (
        "VersoML, zona client (Banca Demo, date sintetice). Rezolvă contestații de plată după CJUE C-70/25: "
        "rambursare până la sfârșitul zilei lucrătoare următoare, dosar de probe cu hash, recuperare. "
        "Regulile decid, LLM-ul doar extrage și redactează, omul semnează excepțiile. "
        "Zona client nu are acces la datele AML: nu cere și nu speculează despre investigații AML."
    ),
    Zone.AML: (
        "VersoML, zona AML (Banca Demo, date sintetice). Investighează conturile care au primit bani din fraude: "
        "graf + ML, OSINT pe identificatori publici, ipoteze nevinovate, ciorne RTS. Nicio informație de aici nu "
        "ajunge la client (tipping-off, Legea 129/2019 art. 38 alin. 2). Decizia o ia analistul uman."
    ),
}


def _authorize(zone: Zone, action: str) -> None:
    from versoml.shared.policy import authorize

    principal = "Mcp/client" if zone == Zone.CLIENT else "Mcp/aml"
    decision = authorize(principal, action, zone, {"via": "mcp"})
    if not decision.allowed:
        raise PermissionError(f"Refuzat de politica Cedar: {decision.reason}")


def _base(zone: Zone) -> str:
    s = get_settings()
    return s.client_url if zone == Zone.CLIENT else s.aml_url


async def _api(zone: Zone, method: str, path: str, body: dict | None = None) -> Any:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(method, _base(zone) + path, json=body)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Procesul zonei {zone.value} nu răspunde ({type(exc).__name__}). Pornește-l cu `versoml up`.") from exc
    if response.status_code >= 400:
        raise RuntimeError(f"{response.status_code}: {response.text[:300]}")
    return response.json()


def _dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_dump(v) for v in value]
    return value


def build_server(zone: Zone):
    from mcp.server.mcpserver import MCPServer

    install_log_redaction()
    name = "versoml-client" if zone == Zone.CLIENT else "versoml-aml"
    server = MCPServer(name=name, title=f"VersoML · zona {zone.value}", instructions=INSTRUCTIONS[zone],
                       version="0.1.0", log_level="WARNING")

    # ------------------------------------------------------------ comune (deterministe, locale)

    @server.tool(description="Catalogul regulilor VersoML (PAY, DSP, CMP, DP, REC, AML) cu temei și marcaj de încredere.")
    def versoml_rules_catalog(pack: str | None = None) -> list[dict]:
        _authorize(zone, "mcp.rules.catalog")
        from versoml.shared.rules import catalog

        rows = catalog()
        return [r for r in rows if not pack or str(r.get("pack", "")).upper() == pack.upper()]

    @server.tool(description="Termenul T+1 (sfârșitul zilei lucrătoare următoare, calendar RO) pentru o notificare ISO 8601.")
    def versoml_t1_deadline(notified_at: str) -> dict:
        _authorize(zone, "mcp.rules.deadline")
        from versoml.shared.rules.calendar_ro import add_business_days, end_of_next_business_day

        dt = datetime.fromisoformat(notified_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return {"notified_at": dt.isoformat(), "t1_deadline": end_of_next_business_day(dt).isoformat(),
                "complaint_answer_deadline": add_business_days(dt, 15).isoformat(),
                "basis": "Legea 209/2019 art. 173; CJUE C-70/25; art. 224–225 (15 zile lucrătoare)"}

    @server.tool(description="Verifică un dosar de probe exportat (lanț SHA-256, rădăcină Merkle, semnătură Ed25519).")
    def versoml_verify_dossier(dossier_json: str) -> dict:
        _authorize(zone, "mcp.ledger.verify")
        from versoml.shared.ledger import verify_dossier

        return verify_dossier(json.loads(dossier_json))

    if zone == Zone.CLIENT:
        _client_tools(server)
    else:
        _aml_tools(server)

    @server.resource("versoml://reguli/catalog", name="Catalogul regulilor", mime_type="application/json")
    def rules_resource() -> str:
        from versoml.shared.rules import catalog

        return json.dumps(catalog(), ensure_ascii=False, indent=1, default=str)

    @server.prompt(description="Investighează o contestație de plată cap-coadă, cu VersoML.")
    def investigheaza_contestatie(descriere: str) -> str:
        return ("Folosește tool-urile VersoML ca să deschizi un caz pentru contestația de mai jos, urmărește-i starea "
                "până la decizia de rambursare și rezumă: verdictul, regulile (ID-uri), termenul T+1, probele cheie "
                "(EV-…) și ce trebuie să semneze un om.\n\nContestația:\n" + descriere)

    return server


def _client_tools(server) -> None:
    zone = Zone.CLIENT

    @server.tool(description="Lista scenariilor sintetice de demo (phishing, Visa Secure, vishing, SIM swap etc.).")
    async def versoml_list_scenarios() -> list[dict]:
        _authorize(zone, "mcp.cases.read")
        return await _api(zone, "GET", "/api/scenarios")

    @server.tool(description="Deschide și pornește un caz: fie dintr-un scenariu (scenario_id), fie dintr-o reclamație "
                             "scrisă (complaint_text + customer_ref + transaction_id). Întoarce case_id.")
    async def versoml_open_case(scenario_id: str | None = None, complaint_text: str | None = None,
                             customer_ref: str | None = None, transaction_id: str | None = None) -> dict:
        _authorize(zone, "mcp.cases.create")
        body: dict = {"scenario_id": scenario_id} if scenario_id else {"complaint": {
            "customer_ref": customer_ref or "CUST-DEMO-01", "text": complaint_text or "",
            "transaction_refs": [transaction_id] if transaction_id else [], "attachments": []}}
        created = await _api(zone, "POST", "/api/cases", body)
        await _api(zone, "POST", f"/api/cases/{created['case_id']}/run")
        return {"case_id": created["case_id"], "ui": f"{_base(zone)}/cazuri/{created['case_id']}"}

    @server.tool(description="Starea unui caz: verdict, termen, decizii cu ID-uri de reguli, ce așteaptă semnătura umană.")
    async def versoml_case_status(case_id: str) -> dict:
        _authorize(zone, "mcp.cases.read")
        detail = await _api(zone, "GET", f"/api/cases/{case_id}")
        return {"summary": detail["summary"], "decisions": [
            {"question": d["question"], "decision": d["decision"], "rule_ids": d.get("rule_ids"),
             "deadline": d.get("deadline"), "requires_human": d.get("requires_human"),
             "rationale": [r.get("text") for r in d.get("rationale", [])][:3]} for d in detail.get("decisions", [])],
            "interrupt": detail.get("interrupt"), "letter_status": (detail.get("letter") or {}).get("status")}

    @server.tool(description="Probele din registrul cazului: ID, tip, sursă, rezumat, hash.")
    async def versoml_case_evidence(case_id: str) -> list[dict]:
        _authorize(zone, "mcp.cases.read")
        detail = await _api(zone, "GET", f"/api/ledger/{case_id}")
        return [{"fact_id": f["fact_id"], "kind": f["kind"], "source_tool": f["source_tool"], "summary": f["summary"],
                 "sha256": f["sha256"][:16]} for f in detail.get("facts", [])]

    @server.tool(description="Semnătura umană pe o decizie care o cere (approve sau reject). Clientul MCP trebuie să "
                             "confirme cu utilizatorul înainte de apel.")
    async def versoml_approve(case_id: str, action: str, note: str | None = None) -> dict:
        _authorize(zone, "mcp.cases.approve")
        return await _api(zone, "POST", f"/api/cases/{case_id}/approve",
                          {"action": action, "note": note, "approver": "OPERATOR-90"})

    @server.tool(description="Schimbă un fapt și arată ce decizii se schimbă (de exemplu screen_showed_amount_and_payee=true).")
    async def versoml_counterfactual(case_id: str, field: str, value: bool) -> dict:
        _authorize(zone, "mcp.cases.read")
        return await _api(zone, "POST", f"/api/cases/{case_id}/counterfactual", {"field": field, "value": value})

    @server.tool(description="Trece un text de scrisoare prin filtrul zidului: termeni interziși (tipping-off), canary, date personale.")
    def versoml_check_letter(text: str) -> dict:
        _authorize(zone, "letters.check_letter")
        from versoml.wall.letter_filter import check_letter

        return check_letter(text).model_dump(mode="json")

    @server.tool(description="Evaluează regulile VersoML pe un context JSON (contracts.RuleContext). Determinist.")
    def versoml_evaluate_rules(rule_context_json: str) -> dict:
        _authorize(zone, "mcp.rules.evaluate")
        from versoml.shared.rules import RuleContextExt, evaluate

        return evaluate(RuleContextExt.model_validate_json(rule_context_json)).model_dump(mode="json")

    @server.tool(description="Domain-intel pentru un domeniu sau URL din SMS: scor de sosie, vârsta (RDAP), certificate (CT).")
    async def versoml_domain_intel(domain_or_url: str) -> list[dict]:
        _authorize(zone, "domain-intel.lookalike_score")
        from versoml.osint import domain as osd
        from versoml.osint import lookalike as osl

        domain = domain_or_url.split("://")[-1].split("/")[0].lower()
        results = [osl.lookalike_score(domain), await osd.rdap_domain(domain), await osd.ct_certificates(domain)]
        return [_dump(r) for r in results]

    @server.tool(description="Starea zidului: cele șase straturi, refuzuri Cedar, scrisori blocate, neinterferență.")
    async def versoml_wall_status() -> dict:
        _authorize(zone, "mcp.wall.read")
        return await _api(zone, "GET", "/api/wall")


def _aml_tools(server) -> None:
    zone = Zone.AML

    @server.tool(description="Pistele AML deschise din contestații (conturi beneficiar, scor, tipologii, recomandare).")
    async def versoml_aml_leads() -> list[dict]:
        _authorize(zone, "aml.leads.read")
        return await _api(zone, "GET", "/api/aml/leads")

    @server.tool(description="Detaliul unei piste: graful banilor, scorurile ML, OSINT, ipoteze nevinovate, ciorna RTS, ceasuri.")
    async def versoml_aml_lead(lead_id: str) -> dict:
        _authorize(zone, "aml.leads.read")
        detail = await _api(zone, "GET", f"/api/aml/leads/{lead_id}")
        detail.pop("timeline", None)
        return detail

    @server.tool(description="Investigație OSINT live pe un identificator public (domeniu, URL, telefon, CUI, IBAN, firmă).")
    async def versoml_osint_investigate(target: str, kind: str = "auto") -> dict:
        _authorize(zone, "aml.osint.web_search")
        from versoml.osint.investigate import extract_artifacts, investigate

        artifacts = extract_artifacts(target) if kind == "auto" else {kind + "s": [target]}
        if not any(artifacts.values()):
            artifacts = {"companies": [target]}
        return {"artifacts": artifacts, "results": [_dump(r) for r in await investigate(artifacts)]}

    @server.tool(description="Screening pe liste de sancțiuni pentru o firmă sau persoană beneficiară.")
    async def versoml_sanctions_screen(name: str) -> dict:
        _authorize(zone, "aml.sanctions.screen")
        from versoml.osint.sanctions import sanctions_screen

        return _dump(await sanctions_screen(name))

    @server.tool(description="Datele publice ale unei firme după CUI (ANAF), cu validarea cifrei de control.")
    async def versoml_company_lookup(cui: str) -> dict:
        _authorize(zone, "aml.osint.anaf_company")
        from versoml.osint.registry_ro import anaf_company

        return _dump(await anaf_company(cui))

    @server.tool(description="Decizia analistului pe o pistă: file_rts, close, request_info sau hold_client. Cere confirmarea utilizatorului.")
    async def versoml_aml_decide(lead_id: str, action: str, note: str | None = None) -> dict:
        _authorize(zone, "aml.leads.decide")
        return await _api(zone, "POST", f"/api/aml/leads/{lead_id}/decide",
                          {"action": action, "note": note, "analyst": "ANALIST-90"})


def http_app(zone: Zone):
    """Aplicația Starlette pentru MCP prin HTTP (streamable), montată în procesul zonei la /mcp."""
    server = build_server(zone)
    return server.streamable_http_app(streamable_http_path="/", stateless_http=True, json_response=True)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Serverul MCP VersoML")
    parser.add_argument("--zone", choices=["client", "aml"], default="client")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()
    zone = Zone(args.zone)
    server = build_server(zone)
    if args.transport == "stdio":
        server.run("stdio")
    else:
        port = args.port or (8765 if zone == Zone.CLIENT else 8766)
        server.run("streamable-http", port=port, host="127.0.0.1")


if __name__ == "__main__":
    main()
