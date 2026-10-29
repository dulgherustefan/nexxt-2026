"""The VersoML MCP server: VersoML as a tool in Claude Desktop, Cursor or any MCP client.

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
        "VersoML, client zone (Demo Bank, synthetic data). It resolves payment disputes under CJEU C-70/25: "
        "a refund by the end of the next business day, an evidence file with hashes, and recovery. "
        "Rules decide, the LLM only extracts and drafts, and a person signs off the exceptions. "
        "You cannot sign: versoml_approve records a proposal, and a person signs it in the console. "
        "The client zone has no access to AML data: do not ask about AML investigations or speculate about them."
    ),
    Zone.AML: (
        "VersoML, AML zone (Demo Bank, synthetic data). It investigates the accounts that received money from "
        "fraud: graph + ML, OSINT on public identifiers, innocent explanations, draft STRs. Nothing from here "
        "reaches the customer (tipping-off, Law 129/2019 art. 38(2)). A human analyst makes the decision."
    ),
}
ZONE_TITLES = {Zone.CLIENT: "client zone", Zone.AML: "AML zone"}


def _authorize(zone: Zone, action: str) -> None:
    from versoml.shared.policy import authorize

    principal = "Mcp/client" if zone == Zone.CLIENT else "Mcp/aml"
    decision = authorize(principal, action, zone, {"via": "mcp"})
    if not decision.allowed:
        raise PermissionError(f"Denied by the Cedar policy: {decision.reason}")


def _base(zone: Zone) -> str:
    s = get_settings()
    return s.client_url if zone == Zone.CLIENT else s.aml_url


async def _api(zone: Zone, method: str, path: str, body: dict | None = None) -> Any:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(method, _base(zone) + path, json=body)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"The {ZONE_TITLES[zone]} process is not responding ({type(exc).__name__}). "
                           "Start it with `versoml up`.") from exc
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
    server = MCPServer(name=name, title=f"VersoML · {ZONE_TITLES[zone]}", instructions=INSTRUCTIONS[zone],
                       version="0.1.0", log_level="WARNING")

    # ------------------------------------------------------------ shared (deterministic, local)

    @server.tool(description="The VersoML rules catalog (PAY, DSP, CMP, DP, REC, AML), with each rule's legal basis "
                             "and confidence mark.")
    def versoml_rules_catalog(pack: str | None = None) -> list[dict]:
        _authorize(zone, "mcp.rules.catalog")
        from versoml.shared.rules import catalog

        rows = catalog()
        return [r for r in rows if not pack or str(r.get("pack", "")).upper() == pack.upper()]

    @server.tool(description="The refund deadline (end of the next business day, Romanian calendar) for a notification "
                             "time in ISO 8601.")
    def versoml_t1_deadline(notified_at: str) -> dict:
        _authorize(zone, "mcp.rules.deadline")
        from versoml.shared.rules.calendar_ro import add_business_days, end_of_next_business_day

        dt = datetime.fromisoformat(notified_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return {"notified_at": dt.isoformat(), "t1_deadline": end_of_next_business_day(dt).isoformat(),
                "complaint_answer_deadline": add_business_days(dt, 15).isoformat(),
                "basis": "Law 209/2019 art. 173; CJEU C-70/25; art. 224–225 (15 business days)"}

    @server.tool(description="Verify an exported evidence file (SHA-256 chain, Merkle root, Ed25519 signature).")
    def versoml_verify_dossier(dossier_json: str) -> dict:
        _authorize(zone, "mcp.ledger.verify")
        from versoml.shared.ledger import verify_dossier

        return verify_dossier(json.loads(dossier_json))

    if zone == Zone.CLIENT:
        _client_tools(server)
    else:
        _aml_tools(server)

    @server.resource("versoml://reguli/catalog", name="Rules catalog", mime_type="application/json")
    def rules_resource() -> str:
        from versoml.shared.rules import catalog

        return json.dumps(catalog(), ensure_ascii=False, indent=1, default=str)

    @server.prompt(description="Investigate a payment dispute end to end with VersoML.")
    def investigheaza_contestatie(descriere: str) -> str:
        return ("Use the VersoML tools to open a case for the dispute below, follow its status until the refund "
                "decision, then summarize: the verdict, the rules (IDs), the refund deadline, the key evidence (EV-…) "
                "and what a person has to sign.\n\nThe dispute:\n" + descriere)

    return server


def _client_tools(server) -> None:
    zone = Zone.CLIENT

    @server.tool(description="The synthetic demo scenarios (phishing, Visa Secure, vishing, SIM swap and more).")
    async def versoml_list_scenarios() -> list[dict]:
        _authorize(zone, "mcp.cases.read")
        return await _api(zone, "GET", "/api/scenarios")

    @server.tool(description="Open and start a case, either from a scenario (scenario_id) or from a written complaint "
                             "(complaint_text + customer_ref + transaction_id). Returns the case_id and the case page link.")
    async def versoml_open_case(scenario_id: str | None = None, complaint_text: str | None = None,
                             customer_ref: str | None = None, transaction_id: str | None = None) -> dict:
        _authorize(zone, "mcp.cases.create")
        body: dict = {"scenario_id": scenario_id} if scenario_id else {"complaint": {
            "customer_ref": customer_ref or "CUST-DEMO-01", "text": complaint_text or "",
            "transaction_refs": [transaction_id] if transaction_id else [], "attachments": []}}
        created = await _api(zone, "POST", "/api/cases", body)
        await _api(zone, "POST", f"/api/cases/{created['case_id']}/run")
        return {"case_id": created["case_id"], "ui": f"{_base(zone)}/cases/{created['case_id']}"}

    @server.tool(description="A case's status: verdict, deadline, decisions with rule IDs, what waits for a "
                             "person's signature, and the case in standard codes (EBA fraud type, ISO 4217, E.164).")
    async def versoml_case_status(case_id: str) -> dict:
        _authorize(zone, "mcp.cases.read")
        detail = await _api(zone, "GET", f"/api/cases/{case_id}")
        interrupt = {k: v for k, v in (detail.get("interrupt") or {}).items() if k != "approval_token"}
        return {"summary": detail["summary"], "decisions": [
            {"question": d["question"], "decision": d["decision"], "rule_ids": d.get("rule_ids"),
             "deadline": d.get("deadline"), "requires_human": d.get("requires_human"),
             "rationale": [r.get("text") for r in d.get("rationale", [])][:3]} for d in detail.get("decisions", [])],
            "interrupt": interrupt, "proposals": detail.get("proposals") or [],
            "letter_status": (detail.get("letter") or {}).get("status"),
            # the case in published codes (EBA fraud type, ISO 4217, ISO 13616, E.164), schema versoml.case.v1
            "standard": detail.get("standard")}

    @server.tool(description="The evidence in the case ledger: ID, kind, source, summary, hash.")
    async def versoml_case_evidence(case_id: str) -> list[dict]:
        _authorize(zone, "mcp.cases.read")
        # the full ledger needs an operator session; the case view lists the same entries, and only these fields
        # leave this tool
        detail = await _api(zone, "GET", f"/api/cases/{case_id}")
        return [{"fact_id": f["fact_id"], "kind": f["kind"], "source_tool": f["source_tool"], "summary": f["summary"],
                 "sha256": f["sha256"][:16]} for f in detail.get("facts", [])]

    @server.tool(description="Propose approve or reject on a decision that waits for a person's signature. It does "
                             "not sign and moves no money: an MCP client may not approve (a Cedar forbid), so the "
                             "proposal goes into the case's evidence ledger and a person signs in the console.")
    async def versoml_approve(case_id: str, action: str, note: str | None = None) -> dict:
        _authorize(zone, "mcp.cases.propose")
        from versoml.shared.policy import authorize

        # the signature itself is a person's: always denied here, and the denial shows on the wall page
        signature = authorize("Mcp/client", "mcp.cases.approve", zone, {"via": "mcp", "case_id": case_id})
        proposed = await _api(zone, "POST", f"/api/cases/{case_id}/proposals", {"action": action, "note": note})
        return {"signed": False, "proposal": proposed.get("proposal"), "detail": proposed.get("detail"),
                "why_not_signed": signature.reason}

    @server.tool(description="Change one fact and show which decisions change (for example "
                             "screen_showed_amount_and_payee=true).")
    async def versoml_counterfactual(case_id: str, field: str, value: bool) -> dict:
        _authorize(zone, "mcp.cases.read")
        return await _api(zone, "POST", f"/api/cases/{case_id}/counterfactual", {"field": field, "value": value})

    @server.tool(description="Run a letter's text through the wall's filter: banned terms (tipping-off), canaries, "
                             "personal data.")
    def versoml_check_letter(text: str) -> dict:
        _authorize(zone, "letters.check_letter")
        from versoml.wall.letter_filter import check_letter

        return check_letter(text).model_dump(mode="json")

    @server.tool(description="Evaluate the VersoML rules on a JSON context (contracts.RuleContext). Deterministic.")
    def versoml_evaluate_rules(rule_context_json: str) -> dict:
        _authorize(zone, "mcp.rules.evaluate")
        from versoml.shared.rules import RuleContextExt, evaluate

        return evaluate(RuleContextExt.model_validate_json(rule_context_json)).model_dump(mode="json")

    @server.tool(description="Domain intelligence for a domain or URL from a text message: lookalike score, age (RDAP), "
                             "certificates (CT).")
    async def versoml_domain_intel(domain_or_url: str) -> list[dict]:
        _authorize(zone, "domain-intel.lookalike_score")
        from versoml.osint import domain as osd
        from versoml.osint import lookalike as osl

        domain = domain_or_url.split("://")[-1].split("/")[0].lower()
        results = [osl.lookalike_score(domain), await osd.rdap_domain(domain), await osd.ct_certificates(domain)]
        return [_dump(r) for r in results]

    @server.tool(description="The wall's status: its six layers, Cedar denials, blocked letters, non-interference.")
    async def versoml_wall_status() -> dict:
        _authorize(zone, "mcp.wall.read")
        return await _api(zone, "GET", "/api/wall")

    @server.tool(description="Free-form intake: open and start a case from a complaint as the customer wrote it (an email, "
                             "a call note). The customer reference and the transaction are optional: VersoML finds the "
                             "customer and the payment in the bank's records and says how sure it is. Returns the case_id "
                             "and the match preview.")
    async def versoml_intake(text: str, customer_ref: str | None = None, source: str = "email",
                             channel_hint: str | None = None) -> dict:
        _authorize(zone, "mcp.cases.create")
        body = {"text": text, "customer_ref": customer_ref, "source": source, "channel_hint": channel_hint}
        preview = await _api(zone, "POST", "/api/intake/preview", {k: v for k, v in body.items() if v})
        created = await _api(zone, "POST", "/api/cases", {"complaint": {k: v for k, v in body.items() if v}})
        await _api(zone, "POST", f"/api/cases/{created['case_id']}/run")
        return {"case_id": created["case_id"], "ui": f"{_base(zone)}/cases/{created['case_id']}",
                "customer": preview.get("customer"), "match": preview.get("match")}

    @server.tool(description="Search the client zone's knowledge base (rules, laws, guidance, case studies): passages "
                             "with their source and confidence mark (P official text, S secondary, U unverified).")
    def versoml_kb_search(query: str, k: int = 6, kind: str | None = None) -> list[dict]:
        _authorize(zone, "mcp.rules.catalog")
        from versoml.zone_client import grounding as G

        return G.search(query, k=max(1, min(k, 20)), kinds=[kind] if kind else None)

    @server.tool(description="Ask the client zone's knowledge base a question: a short answer with [n] citations to "
                             "the passages it used. Information, never a decision.")
    async def versoml_kb_ask(question: str, k: int = 6) -> dict:
        _authorize(zone, "mcp.rules.catalog")
        from versoml.zone_client import grounding as G

        return await G.ask(question, k=max(1, min(k, 20)))

    @server.tool(description="Closed cases like a given case (precedents): their outcome and why they look alike. "
                             "Information for a person; the rules never read it.")
    async def versoml_precedents(case_id: str, k: int = 3) -> list[dict]:
        _authorize(zone, "mcp.cases.read")
        return await _api(zone, "GET", f"/api/cases/{case_id}/precedents?k={max(1, min(k, 10))}")


def _aml_tools(server) -> None:
    zone = Zone.AML

    @server.tool(description="AML leads opened from disputes (payee accounts, score, typologies, recommendation).")
    async def versoml_aml_leads() -> list[dict]:
        _authorize(zone, "aml.leads.read")
        return await _api(zone, "GET", "/api/aml/leads")

    @server.tool(description="One lead in detail: the money graph, ML scores, OSINT, innocent explanations, the draft "
                             "STR, the clocks.")
    async def versoml_aml_lead(lead_id: str) -> dict:
        _authorize(zone, "aml.leads.read")
        detail = await _api(zone, "GET", f"/api/aml/leads/{lead_id}")
        detail.pop("timeline", None)
        return detail

    @server.tool(description="A live OSINT check on a public identifier (domain, URL, phone, CUI, IBAN, company).")
    async def versoml_osint_investigate(target: str, kind: str = "auto") -> dict:
        _authorize(zone, "aml.osint.web_search")
        from versoml.osint.investigate import extract_artifacts, investigate

        artifacts = extract_artifacts(target) if kind == "auto" else {kind + "s": [target]}
        if not any(artifacts.values()):
            artifacts = {"companies": [target]}
        return {"artifacts": artifacts, "results": [_dump(r) for r in await investigate(artifacts)]}

    @server.tool(description="Sanctions list screening for a payee company or person.")
    async def versoml_sanctions_screen(name: str) -> dict:
        _authorize(zone, "aml.sanctions.screen")
        from versoml.osint.sanctions import sanctions_screen

        return _dump(await sanctions_screen(name))

    @server.tool(description="A company's public data by CUI (ANAF), with the check digit validated.")
    async def versoml_company_lookup(cui: str) -> dict:
        _authorize(zone, "aml.osint.anaf_company")
        from versoml.osint.registry_ro import anaf_company

        return _dump(await anaf_company(cui))

    @server.tool(description="Search the AML zone's knowledge base (AML law, typologies, guidance). No client-zone "
                             "precedents are in it.")
    def versoml_kb_search(query: str, k: int = 6, kind: str | None = None) -> list[dict]:
        _authorize(zone, "mcp.rules.catalog")
        from versoml.zone_aml.agents import kb_search_aml

        return kb_search_aml(query, k=max(1, min(k, 20)), kinds=[kind] if kind else None)

    @server.tool(description="The analyst's decision on a lead: file_rts, close, request_info or hold_client. Ask the "
                             "user to confirm first.")
    async def versoml_aml_decide(lead_id: str, action: str, note: str | None = None) -> dict:
        _authorize(zone, "aml.leads.decide")
        return await _api(zone, "POST", f"/api/aml/leads/{lead_id}/decide",
                          {"action": action, "note": note, "analyst": "ANALIST-90"})


# Tools that cost Bedrock calls (or outside lookups), and the limit each one counts against.
COSTLY_TOOLS = {"versoml_open_case": "case_run", "versoml_intake": "case_run",
                "versoml_kb_ask": "kb_ask", "versoml_domain_intel": "web_lookup"}
MAX_BODY = 64_000


class PublicLimits:
    """ASGI wrapper for MCP over HTTP: a size cap, a per-caller request rate, and per-caller limits on the costly
    tools. Case tools then go through the API, which also applies the shared limits; `versoml_kb_ask` runs in this
    process, so its shared limit is counted here."""

    def __init__(self, app) -> None:
        self.app = app
        self.router = app.router  # the zone app runs the MCP session manager through this router's lifespan

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return
        from versoml.shared import ratelimit

        body, more = b"", True
        while more:
            message = await receive()
            body += message.get("body", b"")
            more = message.get("more_body", False)
            if len(body) > MAX_BODY:
                await _refuse(send, 413, None, "The request is too large for this demo.")
                return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        caller = ratelimit.caller_of(headers)
        refusal = ratelimit.check("mcp_call", caller) if caller else None
        if refusal is None:
            for name, rpc_id in _tool_calls(body):
                policy = COSTLY_TOOLS.get(name)
                if policy == "kb_ask" or (policy and caller):
                    refusal = ratelimit.check(policy, caller)
                if refusal:
                    break
        if refusal:
            log.info("MCP limit %s reached", refusal.policy)
            await _refuse(send, 429, refusal.retry_after, refusal.text(), _first_id(body))
            return
        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


def _messages(body: bytes) -> list[dict]:
    try:
        data = json.loads(body or b"null")
    except ValueError:
        return []
    return [m for m in (data if isinstance(data, list) else [data]) if isinstance(m, dict)]


def _tool_calls(body: bytes) -> list[tuple[str, Any]]:
    return [(str((m.get("params") or {}).get("name") or ""), m.get("id"))
            for m in _messages(body) if m.get("method") == "tools/call"]


def _first_id(body: bytes) -> Any:
    ids = [m.get("id") for m in _messages(body) if "id" in m]
    return ids[0] if ids else None


async def _refuse(send, status: int, retry_after: int | None, text: str, rpc_id: Any = None) -> None:
    """A JSON-RPC error the MCP client can show, with the HTTP status and Retry-After for anything in between."""
    payload = json.dumps({"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32000, "message": text}}).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode())]
    if retry_after:
        headers.append((b"retry-after", str(retry_after).encode()))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": payload})


def http_app(zone: Zone):
    """The Starlette app for MCP over HTTP (streamable), mounted at /mcp in the zone's process.

    Reachable on this machine and on the demo's public hosts (`VERSOML_PUBLIC_HOSTS`); any other Host header is
    refused (DNS rebinding protection), and every request passes the public limits first."""
    from mcp.server.transport_security import TransportSecuritySettings

    server = build_server(zone)
    public = [h.strip() for h in get_settings().versoml_public_hosts.split(",") if h.strip()]
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*", *public],
        allowed_origins=["http://127.0.0.1:*", "http://localhost:*", *[f"https://{h}" for h in public]],
    )
    app = server.streamable_http_app(streamable_http_path="/", stateless_http=True, json_response=True,
                                     transport_security=security, max_request_body_size=MAX_BODY)
    return PublicLimits(app)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="The VersoML MCP server")
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
