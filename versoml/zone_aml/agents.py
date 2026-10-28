"""Agenții Investigatorului (zona AML).

Pornesc dintr-o contestație (DisputeFacts venit prin diodă), leagă cazurile, scorează conturile cu ML pe graf,
verifică identificatorii publici prin OSINT, caută explicațiile nevinovate și redactează ciorna RTS. Decide omul.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Callable

from langgraph.types import interrupt

from versoml.contracts import AccountScore, HoldSignal, Labels, OsintFinding, RationaleLine, Sink, Trust, Verdict
from versoml.shared.events import Emitter, now
from versoml.shared.llm import Role
from versoml.zone_aml import prompts as P
from versoml.zone_aml.runtime import AmlRuntime, get_runtime

log = logging.getLogger("versoml.aml.agents")

AG = {
    "receptor_fapte": "Investigatorul/Receptor fapte",
    "graf_ml": "Investigatorul/Graf + ML",
    "osint": "Investigatorul/OSINT",
    "nevinovatie": "Investigatorul/Avocatul nevinovăției",
    "reguli_aml": "Motorul de reguli AML",
    "redactor_rts": "Investigatorul/Redactor RTS",
    "analist": "Analistul AML (om)",
    "sigiliu": "Registrul de probe AML",
}

PIPELINE_NODES = [
    {"id": "receptor_fapte", "label": "Receptor fapte", "model": "fără LLM", "hint": "citește DisputeFacts din diodă"},
    {"id": "graf_ml", "label": "Graf + ML", "model": "ml", "hint": "M5 GBDT pe trăsături de graf, Louvain, tipologii"},
    {"id": "osint", "label": "OSINT", "model": "sonnet", "hint": "ANAF, RDAP, CT, sancțiuni, presă; tool-uri în paralel"},
    {"id": "nevinovatie", "label": "Avocatul nevinovăției", "model": "opus", "hint": "ipoteze nevinovate, obligatoriu înainte de RTS"},
    {"id": "reguli_aml", "label": "Reguli AML", "model": "fără LLM", "hint": "Legea 129/2019 art. 6–8, ceasuri"},
    {"id": "redactor_rts", "label": "Ciornă RTS", "model": "opus", "hint": "fiecare frază cu sursă; canary plantat"},
    {"id": "analist", "label": "Analist (om)", "model": "om", "hint": "depune, închide, cere informații sau HOLD"},
    {"id": "sigiliu", "label": "Sigiliu", "model": "fără LLM", "hint": "Merkle + Ed25519"},
]
PIPELINE_EDGES = [("receptor_fapte", "graf_ml"), ("receptor_fapte", "osint"), ("graf_ml", "nevinovatie"),
                  ("osint", "nevinovatie"), ("nevinovatie", "reguli_aml"), ("reguli_aml", "redactor_rts"),
                  ("redactor_rts", "analist"), ("analist", "sigiliu")]


def g(d: dict | None, *keys: str, default: Any = None) -> Any:
    if not d:
        return default
    for key in keys:
        if key in d and d[key] is not None:
            return d[key]
    return default


def mask_iban(iban: str | None) -> str | None:
    return f"{iban[:4]} {iban[4:8]} •••• {iban[-4:]}" if iban and len(iban) > 12 else iban


class Ctx:
    def __init__(self, state: dict):
        self.rt: AmlRuntime = get_runtime()
        self.lead_id: str = state["lead_id"]
        self.run_id: str = state.get("run_id", "run")
        self.em = Emitter(self.rt.bus, self.lead_id, self.run_id, self.lead_id)

    def track(self, step: str, status: str, summary: str | None = None) -> None:
        doc = self.rt.leads.get(self.lead_id) or {}
        pipeline = doc.get("pipeline_status", {})
        entry = pipeline.get(step, {})
        entry["status"] = status
        entry["started_at" if status == "running" else "finished_at"] = now().isoformat()
        if summary:
            entry["summary"] = summary
        pipeline[step] = entry
        self.rt.leads.update(self.lead_id, {"pipeline_status": pipeline})

    async def start(self, step: str, message: str) -> None:
        self.track(step, "running")
        await self.em.step(step, AG[step], message)

    async def finish(self, step: str, message: str, data: dict | None = None, status: str = "done") -> None:
        self.track(step, status, message)
        await self.em.done(step, AG[step], message, {**(data or {}), "status": status})

    def save(self, patch: dict) -> None:
        self.rt.leads.update(self.lead_id, patch)

    async def fact(self, step: str, kind: str, source_tool: str, args: dict, content: dict, summary: str) -> str:
        fact = self.rt.ledger.append(self.lead_id, kind, source_tool, args, content, summary,
                                     Labels(conf="aml-only", trust=Trust.TRUSTED, sinks=[Sink.AML]))
        await self.em.custom("fact", summary, {"fact_id": fact.fact_id, "kind": kind, "source_tool": source_tool,
                                               "sha256": fact.sha256}, step=step, agent=AG.get(step))
        return fact.fact_id


# ---------------------------------------------------------------- 1. Receptorul de fapte


async def receptor_fapte(state: dict) -> dict:
    c = Ctx(state)
    await c.start("receptor_fapte", "Citesc faptele venite prin diodă (fără identitatea victimelor)")
    referrals = [r for r in c.rt.referrals.all() if r.get("lead_id") == c.lead_id]
    ids = []
    # la o rulare nouă a pistei (o victimă în plus), faptele deja primite nu se mai scriu a doua oară
    already = {f.content.get("case_id"): f.fact_id for f in c.rt.ledger.facts(c.lead_id) if f.kind == "diode.dispute_facts"}
    for ref in referrals:
        facts = ref["facts"]
        if facts["case_id"] in already:
            ids.append(already[facts["case_id"]])
            continue
        fid = await c.fact("receptor_fapte", "diode.dispute_facts", "diode.receive_facts", {"case_id": facts["case_id"]},
                           facts, f"Contestația {facts['case_id']}: {facts['amount']['value']:.0f} {facts['amount']['currency']} "
                                  f"spre {mask_iban(facts['beneficiary'].get('iban'))} ({facts.get('scenario') or facts['dispute_type']})")
        ids.append(fid)
    ibans = sorted({r["facts"]["beneficiary"].get("iban") for r in referrals if r["facts"]["beneficiary"].get("iban")})
    c.save({"case_ids": sorted({r["facts"]["case_id"] for r in referrals}), "ibans": ibans})
    await c.finish("receptor_fapte", f"{len(referrals)} contestații legate de {len(ibans)} cont(uri) beneficiar")
    return {"referrals": [r["facts"] for r in referrals], "ibans": ibans, "fact_ids": ids}


# ---------------------------------------------------------------- 2. Graful și ML-ul


def _ui_graph(graph: dict, scores: dict[str, AccountScore], comms: dict[str, int], referrals: list[dict]) -> dict:
    victims = {}
    for r in referrals:
        victims.setdefault(r["victim_ref"], {"amount": 0.0, "cases": []})
        victims[r["victim_ref"]]["amount"] += float(r["amount"]["value"])
        victims[r["victim_ref"]]["cases"].append(r["case_id"])
    nodes, edges = [], []
    raw_nodes = list(graph.get("nodes", []))
    if len(raw_nodes) > 60:
        # graful pentru ecran: conturile pistei, hub-urile, conturile semnalate și cele mai mari contrapărți
        volume: dict[str, float] = {}
        for edge in graph.get("edges", []):
            for end in (g(edge, "source", "src"), g(edge, "target", "dst")):
                volume[end] = volume.get(end, 0.0) + float(g(edge, "amount", default=0) or 0)
        must = [n for n in raw_nodes if n.get("is_seed") or n.get("hub") or n.get("flagged")
                or (scores.get(g(n, "id", "iban")) and scores[g(n, "id", "iban")].score >= 0.7)]
        rest = sorted((n for n in raw_nodes if n not in must), key=lambda n: -volume.get(g(n, "id", "iban"), 0))
        raw_nodes = must + rest[:max(0, 60 - len(must))]
    for node in raw_nodes:
        nid = g(node, "id", "iban", "account")
        kind_raw = f"{g(node, 'kind', 'type', default='cont')} {g(node, 'role_hint', 'role', default='')}".lower()
        kind = ("exchange" if "crypto" in kind_raw or "exchange" in kind_raw else
                "numerar" if "cash" in kind_raw or "atm" in kind_raw else
                "comerciant" if "merchant" in kind_raw else "cont")
        score = scores.get(nid)
        if score and score.score >= 0.7:
            kind = "carausi"
        nodes.append({"id": nid, "label": g(node, "label", "name", default=mask_iban(nid)), "kind": kind,
                      "score": round(score.score, 3) if score else None, "community": comms.get(nid),
                      "amount_in": float(g(node, "amount_in", "in_amount", default=0) or 0),
                      "amount_out": float(g(node, "amount_out", "out_amount", default=0) or 0),
                      "flagged": bool(score and score.score >= 0.7)})
    known = {n["id"] for n in nodes}
    by_id = {n["id"]: n for n in nodes}
    for i, edge in enumerate(graph.get("edges", [])):
        src, dst = g(edge, "source", "src", "from"), g(edge, "target", "dst", "to")
        if src not in known or dst not in known:
            continue
        amount = float(g(edge, "amount", default=0) or 0)
        edges.append({"id": g(edge, "id", default=f"e{i}"), "source": src, "target": dst,
                      "amount": amount, "ts": str(g(edge, "ts", "timestamp", default="")),
                      "kind": g(edge, "kind", "type", default="transfer"), "case_id": g(edge, "case_id")})
        if not g(by_id[src], "amount_out"):
            by_id[src]["_out"] = by_id[src].get("_out", 0.0) + amount
        if not g(by_id[dst], "amount_in"):
            by_id[dst]["_in"] = by_id[dst].get("_in", 0.0) + amount
    for n in nodes:  # sumele intrate și ieșite, din fluxurile vizibile (depozitul nu le dă pe nod)
        n["amount_in"] = round(n["amount_in"] or n.pop("_in", 0.0), 2)
        n["amount_out"] = round(n["amount_out"] or n.pop("_out", 0.0), 2)
        n.pop("_in", None)
        n.pop("_out", None)
    for victim, info in victims.items():
        nodes.append({"id": victim, "label": f"Victimă {victim}", "kind": "victima", "score": None, "community": None,
                      "amount_in": 0, "amount_out": info["amount"], "flagged": False})
        for r in referrals:
            if r["victim_ref"] == victim and r["beneficiary"].get("iban"):
                target = r["beneficiary"]["iban"]
                if target not in known:
                    nodes.append({"id": target, "label": mask_iban(target), "kind": "carausi", "score": None,
                                  "community": None, "amount_in": float(r["amount"]["value"]), "amount_out": 0, "flagged": True})
                    known.add(target)
                edges.append({"id": f"v-{r['case_id']}", "source": victim, "target": target,
                              "amount": float(r["amount"]["value"]), "ts": r["executed_at"], "kind": "frauda",
                              "case_id": r["case_id"]})
    return {"nodes": nodes, "edges": edges}


async def graf_ml(state: dict) -> dict:
    c = Ctx(state)
    await c.start("graf_ml", "Construiesc graful banilor și scorez conturile (GBDT pe trăsături de graf)")
    ibans = state.get("ibans") or []
    decision = c.rt.authorize("graf", "aml.graph.neighborhood")
    if not decision.allowed:
        await c.finish("graf_ml", "Refuzat de politică", status="blocked")
        return {}
    # vecinătatea directă a conturilor pistei: exchange-ul și numerarul intră, dar nu se expandează (hub-uri)
    graph = c.rt.repo.neighborhood(ibans, hops=1, days=30) if ibans else {"nodes": [], "edges": []}
    scores: dict[str, AccountScore] = {}
    comms: dict[str, int] = {}
    typologies: list[dict] = []
    try:
        from versoml.ml.m5_mule import communities, detect_typologies, score_accounts

        for s in score_accounts(graph):
            s = s if isinstance(s, AccountScore) else AccountScore.model_validate(s)
            scores[s.account] = s
        comms = communities(graph)
        found = detect_typologies(graph)
        # doar tiparele centrate pe conturile pistei sau pe conturile cu scor ridicat, câte unul pe (tip, cont)
        focus = set(ibans) | {a for a, s in scores.items() if s.score >= 0.9}
        seen: set[tuple] = set()
        for t in sorted(found, key=lambda t: (t.get("center") not in ibans, -(t.get("amount") or 0))):
            key = (t.get("typology") or t.get("name"), t.get("center"))
            if t.get("center") in focus and key not in seen:
                seen.add(key)
                typologies.append({k: v for k, v in t.items() if k not in ("edge_ids",)})
        typologies = typologies[:8]
    except Exception as exc:  # noqa: BLE001
        log.warning("M5 indisponibil: %s", exc)
    # întâi conturile pistei (beneficiarii din contestații), apoi celelalte conturi cu scor ridicat
    top = sorted(scores.values(), key=lambda s: (s.account not in ibans, -s.score))[:6]
    for s in top:
        s.community = comms.get(s.account)
    ui = _ui_graph(graph, scores, comms, state.get("referrals") or [])
    fid = await c.fact("graf_ml", "ml.m5_scores", "aml.graph.mule_score", {"ibans": len(ibans)},
                       {"top": [s.model_dump(mode="json") for s in top], "typologies": typologies,
                        "nodes": len(ui["nodes"]), "edges": len(ui["edges"])},
                       f"Graf: {len(ui['nodes'])} noduri, {len(ui['edges'])} fluxuri; scor maxim de cărăuș "
                       + (f"{top[0].score:.2f}" if top else "n/a") + (f"; tipologii: {', '.join(t.get('name', t.get('typology', '?')) for t in typologies[:3])}" if typologies else ""))
    for t in typologies[:5]:
        await c.em.custom("typology", f"Tipologie detectată: {t.get('name') or t.get('typology')}", t, step="graf_ml",
                          agent=AG["graf_ml"])
    c.save({"graph": ui, "accounts": [s.model_dump(mode="json") for s in top], "typologies": typologies})
    await c.finish("graf_ml", f"{len([s for s in scores.values() if s.score >= 0.7])} conturi cu scor ridicat")
    return {"accounts": [s.model_dump(mode="json") for s in top], "typologies": typologies, "graph_fact": fid}


# ---------------------------------------------------------------- 3. OSINT (LLM cu tool-uri, în paralel)

OSINT_TOOLS = {
    "web_search": ("Căutare web generală (Serper/Brave/Tavily/Exa/DuckDuckGo).", {"query": "string"}),
    "news_search": ("Presă și forumuri despre o entitate publică (firmă, domeniu, telefon).", {"entity": "string"}),
    "anaf_company": ("Datele unei firme după CUI (ANAF): denumire, stare, TVA.", {"cui": "string"}),
    "sanctions_screen": ("Verificare pe liste de sancțiuni pentru o firmă sau persoană beneficiară.", {"name": "string"}),
    "rdap_domain": ("Data înregistrării și registrarul unui domeniu (RDAP).", {"domain": "string"}),
    "ct_certificates": ("Certificatele TLS emise pentru un domeniu (crt.sh).", {"domain": "string"}),
    "dns_records": ("Înregistrările DNS ale unui domeniu.", {"domain": "string"}),
    "lookalike_score": ("Cât de mult imită un domeniu brandul băncii (0–1).", {"domain": "string"}),
    "fetch_page": ("Descarcă sigur o pagină (fără JS) și extrage formularele.", {"url": "string"}),
    "openphish_check": ("Verifică un URL sau domeniu în feedul OpenPhish.", {"url_or_domain": "string"}),
    "phone_intel": ("Informații publice despre un număr de telefon.", {"phone": "string"}),
    "validate_iban": ("Validează un IBAN și identifică banca.", {"iban": "string"}),
}


def _tool_specs() -> list[dict]:
    specs = []
    for name, (desc, props) in OSINT_TOOLS.items():
        specs.append({"name": name, "description": desc, "input_schema": {
            "type": "object", "properties": {k: {"type": v} for k, v in props.items()},
            "required": list(props), "additionalProperties": False}})
    return specs


def _resolve_tool(name: str) -> Callable | None:
    """Funcția din modulul OSINT; registrul e doar rezervă (un wrapper necunoscut nu trebuie să strice apelul)."""
    modules = {"web_search": "search", "news_search": "search", "anaf_company": "registry_ro", "validate_iban": "registry_ro",
               "sanctions_screen": "sanctions", "rdap_domain": "domain", "ct_certificates": "domain", "dns_records": "domain",
               "lookalike_score": "lookalike", "fetch_page": "crawl", "openphish_check": "threatintel", "phone_intel": "phone"}
    import importlib

    try:
        fn = getattr(importlib.import_module(f"versoml.osint.{modules[name]}"), name, None)
        if callable(fn):
            return fn
    except Exception:  # noqa: BLE001
        pass
    try:
        from versoml.osint import base

        tool = base.get_tool(name)
        for attr in ("fn", "func", "callable", "handler"):
            if callable(getattr(tool, attr, None)):
                return getattr(tool, attr)
        return tool if callable(tool) else None
    except Exception:  # noqa: BLE001
        return None


def _signal_of(data: dict) -> str:
    return data.get("signal") or "neutru"


async def osint(state: dict) -> dict:
    c = Ctx(state)
    await c.start("osint", "Investighez identificatorii publici: firma, domeniul, telefonul, presa")
    referrals = state.get("referrals") or []
    targets = {"ibans": sorted({r["beneficiary"].get("iban") for r in referrals if r["beneficiary"].get("iban")}),
               "companies": sorted({r["beneficiary"].get("name") for r in referrals if r["beneficiary"].get("name")}),
               "cuis": sorted({r["beneficiary"].get("cui") for r in referrals if r["beneficiary"].get("cui")}),
               "domains": sorted({r["attack"].get("domain") for r in referrals if r.get("attack", {}).get("domain")}),
               "urls": sorted({r["attack"].get("url") for r in referrals if r.get("attack", {}).get("url")}),
               "phones": sorted({r["attack"].get("phone") for r in referrals if r.get("attack", {}).get("phone")})}
    findings: list[dict] = []

    # Referințe în loc de valori (tiparul CaMeL): LLM-ul vede <IBAN_1>, tool-ul primește IBAN-ul real.
    # Pașaportul datelor (docs/05 §6.4): IBAN-ul și persoanele fizice ajung la model doar ca etichete.
    refs: dict[str, str] = {}
    for i, iban in enumerate(targets["ibans"], 1):
        refs[f"<IBAN_{i}>"] = iban
    for i, phone in enumerate(targets["phones"], 1):
        refs[f"<TELEFON_{i}>"] = phone
    for i, name in enumerate([n for n in targets["companies"] if not _is_company(n)], 1):
        refs[f"<PERSOANA_{i}>"] = name
    reverse = {real: token for token, real in refs.items()}
    masked_targets = {k: [reverse.get(v, v) for v in values] for k, values in targets.items()}

    def unmask(value: Any) -> Any:
        if isinstance(value, str):
            for token, real in refs.items():
                value = value.replace(token, real)
        return value

    def for_llm(payload: dict) -> dict:
        """Ce se întoarce la model: valorile cunoscute devin etichete, restul trece prin PrivacyProxy."""
        text = json.dumps(payload, ensure_ascii=False, default=str)
        for real, token in sorted(reverse.items(), key=lambda kv: -len(kv[0])):
            text = text.replace(real, token)
        text, _ = c.rt.privacy.pseudonymize(text, c.lead_id)
        try:
            return json.loads(text)
        except ValueError:
            return {"rezumat": text[:2000]}

    async def execute(name: str, args: dict) -> dict:
        decision = c.rt.authorize("osint", f"aml.osint.{name}")
        if not decision.allowed:
            await c.em.custom("policy_denied", f"Cedar a refuzat aml.osint.{name}", decision.model_dump(mode="json"),
                              step="osint", agent=AG["osint"])
            return {"ok": False, "error": "refuzat de politică"}
        fn = _resolve_tool(name)
        if fn is None:
            return {"ok": False, "error": f"tool necunoscut {name}"}
        args = {k: unmask(v) for k, v in args.items()}
        await c.em.tool("osint", AG["osint"], name, args)
        try:
            result = fn(**args)
            if asyncio.iscoroutine(result):
                result = await asyncio.wait_for(result, timeout=25)
            data = result.model_dump(mode="json") if hasattr(result, "model_dump") else dict(result)
        except Exception as exc:  # noqa: BLE001 - un tool căzut nu oprește investigația
            data = {"ok": False, "summary": f"{name} a eșuat: {type(exc).__name__}", "signal": "neutru", "mode": "offline"}
        target = next(iter(args.values()), "")
        fid = await c.fact("osint", f"osint.{name}", f"aml.osint.{name}", args,
                           {k: data.get(k) for k in ("ok", "summary", "signal", "source_url", "mode", "data")},
                           data.get("summary") or f"{name}({target})")
        finding = OsintFinding(tool=name, target=str(target), ok=bool(data.get("ok")), summary=data.get("summary") or "",
                               signal=_signal_of(data) if _signal_of(data) in ("rosu", "galben", "verde", "neutru") else "neutru",
                               fact_id=fid, source_url=data.get("source_url"),
                               mode=data.get("mode") if data.get("mode") in ("live", "fixture", "cache", "offline") else "fixture")
        findings.append(finding.model_dump(mode="json"))
        await c.em.tool("osint", AG["osint"], name, args, {"ok": finding.ok, "signal": finding.signal,
                                                           "summary": finding.summary, "fact_id": fid})
        compact = json.dumps(data.get("data") or {}, ensure_ascii=False, default=str)
        return for_llm({"ok": finding.ok, "fact_id": fid, "summary": finding.summary, "signal": finding.signal,
                        "data": compact[:2500]})

    def plan() -> list[tuple[str, dict]]:
        calls: list[tuple[str, dict]] = []
        for iban in targets["ibans"][:2]:
            calls.append(("validate_iban", {"iban": iban}))
        for cui in targets["cuis"][:2]:
            calls.append(("anaf_company", {"cui": cui}))
        for name in targets["companies"][:2]:
            calls += [("sanctions_screen", {"name": name}), ("news_search", {"entity": name})]
        for domain in targets["domains"][:2]:
            calls += [("rdap_domain", {"domain": domain}), ("ct_certificates", {"domain": domain}),
                      ("lookalike_score", {"domain": domain}), ("openphish_check", {"url_or_domain": domain})]
        for phone in targets["phones"][:2]:
            calls.append(("phone_intel", {"phone": phone}))
        return calls

    user = ("Identificatori de verificat (JSON). Etichetele precum <IBAN_1> sau <TELEFON_1> sunt referințe: "
            "le dai exact așa tool-urilor, iar sistemul le rezolvă.\n"
            + json.dumps(masked_targets, ensure_ascii=False, indent=1) + "\nVerifică tot ce e relevant, apoi rezumă.")
    summary, transcript, info = await c.rt.llm.tool_loop(
        role=Role.SONNET, agent=AG["osint"], system=P.OSINT_SYSTEM, user=user, tools=_tool_specs(),
        execute=execute, max_turns=4, effort="low", fallback_plan=plan)
    if not summary:
        reds = [f for f in findings if f["signal"] == "rosu"]
        summary = (f"{len(findings)} verificări OSINT; {len(reds)} semnale roșii: "
                   + "; ".join(f["summary"] for f in reds[:3]) if findings else "Nicio verificare OSINT posibilă.")
    order = {"rosu": 0, "galben": 1, "neutru": 2, "verde": 3}
    findings.sort(key=lambda f: order.get(f["signal"], 9))
    c.save({"osint": findings, "osint_summary": summary, "osint_mode": info.mode})
    await c.finish("osint", f"{len(findings)} verificări ({info.mode}); {sum(f['signal'] == 'rosu' for f in findings)} semnale roșii",
                   {"llm": info.as_dict(), "calls": len(transcript)})
    return {"osint": findings, "osint_summary": summary}


# ---------------------------------------------------------------- 4. Avocatul nevinovăției


RECOMPUTED = {"ml.m5_scores", "rules.aml", "aml.innocent_hypotheses", "aml.rts_draft"}


def _known_people(c: Ctx) -> dict[str, str]:
    """Numele persoanelor fizice beneficiare din pistă: la model ajung doar ca etichete."""
    names = {r["facts"]["beneficiary"].get("name") for r in c.rt.referrals.all() if r.get("lead_id") == c.lead_id}
    return {n: "PERSOANA" for n in names if n and not _is_company(n)}


def _aml_facts(c: Ctx, limit: int = 40) -> tuple[str, set[str], dict]:
    """Rezumatul probelor pentru LLM, pseudonimizat: nicio dată personală brută nu pleacă spre model.

    Recalculările (scor ML, reguli, ipoteze, ciornă) intră doar în ultima versiune; o reverificare cu
    aceeași sursă și același rezumat apare o singură dată.
    """
    facts = c.rt.ledger.facts(c.lead_id)
    latest: dict[tuple, object] = {}
    for f in facts:
        latest[(f.kind,) if f.kind in RECOMPUTED else (f.kind, f.summary)] = f
    brief = "\n".join(f"- {f.fact_id} [{f.kind}]: {f.summary}" for f in list(latest.values())[:limit])
    brief, vault = c.rt.privacy.pseudonymize(brief, c.lead_id, _known_people(c))
    return brief, {f.fact_id for f in facts}, vault


LEGAL_FORMS = (" SRL", " S.R.L", " SA", " S.A", " PFA", " II", " IF", " SNC", " SCS", " SCA", " RA", " ONG")


def _is_company(name: str) -> bool:
    """O firmă (formă juridică în denumire) e un identificator public; o persoană fizică nu."""
    upper = f" {name.upper()} "
    return any(form + " " in upper or form + "." in upper for form in LEGAL_FORMS)


async def nevinovatie(state: dict) -> dict:
    c = Ctx(state)
    await c.start("nevinovatie", "Caut explicațiile nevinovate înainte de orice raport (Opus)")
    brief, valid, vault = _aml_facts(c)
    restore = lambda s: c.rt.privacy.restore(s, vault) if s else s  # noqa: E731 - etichetele devin valori în zona AML

    def fallback() -> P.InnocenceOut:
        graph_fact = state.get("graph_fact")
        osint_ids = [f["fact_id"] for f in state.get("osint") or [] if f.get("fact_id")][:2]
        return P.InnocenceOut(hypotheses=[
            P.Hypothesis(hypothesis="Titularul contului e un cărăuș recrutat (de exemplu printr-un „job de acasă”), el însuși victimă.",
                         supports=[x for x in [graph_fact] if x], against=[],
                         check="Interviu cu titularul și verificarea anunțului de recrutare."),
            P.Hypothesis(hypothesis="Contul aparține unui comerciant nou și legitim cu încasări multe.",
                         supports=[], against=[x for x in [graph_fact, *osint_ids] if x],
                         check="Facturi și contracte pentru încasările de la plătitori diferiți."),
        ], verdict_hint="Tranzitul rapid spre exchange și plătitorii fără legătură între ei rămân indicii puternice.")

    out, info = await c.rt.llm.structured(role=Role.OPUS, agent=AG["nevinovatie"], system=P.INNOCENCE_SYSTEM,
                                          user="Probe din dosarul AML:\n" + brief, schema=P.InnocenceOut,
                                          effort="medium", max_tokens=3000, fallback=fallback)
    hyps = []
    for h in out.hypotheses:
        hyps.append({"hypothesis": restore(h.hypothesis), "supports": [x for x in h.supports if x in valid],
                     "against": [x for x in h.against if x in valid], "check": restore(h.check)})
    lines = [RationaleLine(text=h["hypothesis"], cites=h["supports"] + h["against"]).model_dump() for h in hyps]
    await c.fact("nevinovatie", "aml.innocent_hypotheses", "llm.innocence", {"model": info.model},
                 {"hypotheses": hyps, "verdict_hint": out.verdict_hint}, f"{len(hyps)} ipoteze nevinovate analizate")
    c.save({"innocent": lines, "innocent_detail": hyps, "innocent_hint": out.verdict_hint})
    await c.finish("nevinovatie", out.verdict_hint[:160], {"llm": info.as_dict()})
    return {"innocent": hyps}


# ---------------------------------------------------------------- 5. Regulile AML


async def reguli_aml(state: dict) -> dict:
    c = Ctx(state)
    await c.start("reguli_aml", "Aplic regulile AML: obligația de raportare și ceasurile")
    accounts = state.get("accounts") or []
    typologies = state.get("typologies") or []
    referrals = state.get("referrals") or []
    reds = sum(1 for f in state.get("osint") or [] if f.get("signal") == "rosu")
    top_score = max([a.get("score", 0) for a in accounts] or [0])
    outcome = None
    try:
        from versoml.shared import rules as R

        evaluate_aml = getattr(R, "evaluate_aml", None)
        context_cls = getattr(R, "AmlRuleContext", None)
        if evaluate_aml and context_cls:
            fields = context_cls.model_fields
            # bani rămași în contul semnalat = o plată de ieșire încă se poate suspenda (art. 8): ceasurile pornesc
            lead = c.rt.leads.get(c.lead_id) or {}
            flagged = [n for n in (lead.get("graph") or {}).get("nodes", []) if n.get("flagged")]
            funds_left = any((n.get("amount_in") or 0) > (n.get("amount_out") or 0) for n in flagged)
            features = sorted({name for a in accounts for name, _ in (a.get("top_features") or [])})
            payload = {"lead_id": c.lead_id, "now": now(), "victims": len({r["victim_ref"] for r in referrals}),
                       "cases": len(referrals), "top_mule_score": top_score, "typologies": [t.get("name") or t.get("typology") for t in typologies],
                       "osint_red_flags": reds, "amount_total": sum(float(r["amount"]["value"]) for r in referrals),
                       "transaction_executed": not funds_left, "features_used": features,
                       "suspension_start": now() if funds_left else None}
            outcome = evaluate_aml(context_cls(**{k: v for k, v in payload.items() if k in fields}))
    except Exception as exc:  # noqa: BLE001
        log.warning("evaluate_aml: %s", exc)
    if outcome is not None:
        data = outcome.model_dump(mode="json") if hasattr(outcome, "model_dump") else dict(outcome)
        decisions = data.get("decisions", [])
        recommendation = decisions[0]["decision"] if decisions else Verdict.MONITORIZARE.value
        clocks = data.get("deadlines", [])
        hits = data.get("hits", [])
    else:
        suspicious = top_score >= 0.7 or (len(referrals) >= 2 and typologies)
        recommendation = Verdict.RTS_PROPUS.value if suspicious else Verdict.MONITORIZARE.value
        start = now()
        from datetime import timedelta

        clocks = [{"rule_id": "AML-HOLD", "name": "Suspendare 24h înainte de executare (dacă tranzacția e în curs)",
                   "due_at": (start + timedelta(hours=24)).isoformat(), "basis": "Legea 129/2019 art. 8", "business_days": False},
                  {"rule_id": "AML-ONPCSB", "name": "Răspuns ONPCSB: 48h, prelungire 72h",
                   "due_at": (start + timedelta(hours=48)).isoformat(), "basis": "Legea 129/2019 art. 8", "business_days": False}]
        hits = []
    for hit in hits:
        await c.em.custom("rule_hit", f"{hit.get('rule_id')}: {hit.get('outcome')}", hit, step="reguli_aml",
                          agent=AG["reguli_aml"])
    fid = await c.fact("reguli_aml", "rules.aml", "rules.evaluate_aml", {"top_score": top_score},
                       {"recommendation": recommendation, "clocks": clocks, "rule_ids": [h.get("rule_id") for h in hits]},
                       f"Reguli AML: {recommendation}; {len(clocks)} ceasuri")
    c.save({"recommendation": recommendation, "clocks": clocks, "aml_rules": hits})
    await c.finish("reguli_aml", f"Recomandare: {recommendation}")
    return {"recommendation": recommendation, "clocks": clocks, "rules_fact": fid}


# ---------------------------------------------------------------- 6. Ciorna RTS (+ canary)


async def redactor_rts(state: dict) -> dict:
    c = Ctx(state)
    if state.get("recommendation") != Verdict.RTS_PROPUS.value:
        c.track("redactor_rts", "skipped", "Fără RTS: recomandarea e monitorizare")
        return {"rts": None}
    await c.start("redactor_rts", "Redactez ciorna RTS: fiecare frază cu sursă (Opus)")
    brief, valid, vault = _aml_facts(c)
    restore = lambda s: c.rt.privacy.restore(s, vault) if s else s  # noqa: E731
    canary = c.rt.canaries.mint(c.lead_id)

    def fallback() -> P.RtsOut:
        ids = sorted(valid)
        return P.RtsOut(
            title="Ciornă RTS: posibil cont de tranzit pentru fonduri obținute prin fraudă",
            suspicion_summary="Contul a primit în scurt timp plăți de la mai mulți plătitori fără legătură, contestate ca "
                              "fraudă, și a transferat rapid majoritatea sumelor spre un exchange crypto.",
            indicators=["plătitori multipli fără legătură", "tranzit sub 24h", "ieșiri spre crypto"],
            narrative=[P.RtsLine(text="Plățile au fost contestate de plătitori ca fraudă.", cites=ids[:2]),
                       P.RtsLine(text="Scorul de cont-cărăuș și tipologia de tranzit rapid susțin suspiciunea.", cites=ids[2:4] or ids[:1])],
            recommended_measures=["depunerea RTS la ONPCSB de către analist", "monitorizare sporită a contului"])

    out, info = await c.rt.llm.structured(role=Role.OPUS, agent=AG["redactor_rts"], system=P.RTS_SYSTEM,
                                          user="Probe din dosarul AML:\n" + brief, schema=P.RtsOut, effort="medium",
                                          max_tokens=3500, fallback=fallback)
    narrative, rejected = [], 0
    for line in out.narrative:
        cites = [x for x in line.cites if x in valid]
        if cites:
            narrative.append({"text": restore(line.text), "cites": cites})
        else:
            rejected += 1
    accounts = state.get("accounts") or []
    rts = {"status": "ciornă", "title": restore(out.title), "fields": {
        "raportor": "Banca Demo (sintetic)", "referinta_interna": f"{c.lead_id} · {canary}",
        "conturi": [mask_iban(a["account"]) for a in accounts[:3]],
        "tipologii": [t.get("name") or t.get("typology") for t in state.get("typologies") or []][:4],
        "rezumat": restore(out.suspicion_summary), "indicatori": [restore(x) for x in out.indicators],
        "masuri": [restore(x) for x in out.recommended_measures],
        "formular": "ONPCSB, portalul de raportări (depune un om)"},
        "narrative": narrative, "rejected_without_citation": rejected, "canary_planted": True}
    await c.fact("redactor_rts", "aml.rts_draft", "aml.str.draft", {"model": info.model},
                 {"title": out.title, "narrative": narrative, "canary_ref": "plantat"},
                 f"Ciornă RTS cu {len(narrative)} fraze cu sursă ({rejected} respinse)")
    c.save({"rts": rts, "canary": canary})
    await c.finish("redactor_rts", f"Ciornă RTS gata: {len(narrative)} fraze cu sursă", {"llm": info.as_dict()})
    return {"rts": rts}


# ---------------------------------------------------------------- 7. Analistul (om) și semnalul HOLD


async def analist(state: dict) -> dict:
    c = Ctx(state)
    doc = c.rt.leads.get(c.lead_id) or {}
    payload = {"kind": "decizie_analist", "prompt": "Decizia analistului AML: depui RTS, închizi, ceri informații "
                                                    "sau emiți HOLD spre zona client (doar dacă suspectezi chiar clientul)?",
               "options": ["file_rts", "close", "request_info", "hold_client"],
               "recommendation": state.get("recommendation")}
    pending = doc.get("interrupt") or {}
    if not (pending.get("pending") or pending.get("resuming")):
        c.track("analist", "waiting", "Așteaptă decizia analistului")
        c.save({"interrupt": {"pending": True, **payload}, "status": "ASTEAPTA_ANALIST"})
        await c.em.custom("interrupt", payload["prompt"], payload, step="analist", agent=AG["analist"])
    answer = interrupt(payload) or {}
    action = answer.get("action")
    analyst = answer.get("analyst") or "ANALIST-07"
    c.save({"interrupt": {**payload, "pending": False, "resuming": False, "answer": answer}})
    await c.fact("analist", "human.aml_decision", "consola.aml", {"analyst": analyst},
                 {"action": action, "note": answer.get("note")}, f"{analyst}: {action}")
    status = {"file_rts": "RTS_DEPUS", "close": "INCHIS", "request_info": "INFORMATII", "hold_client": "HOLD_EMIS"}.get(action, "DESCHIS")
    if action == "file_rts" and doc.get("rts"):
        rts = dict(doc["rts"])
        rts["status"] = "marcat pentru depunere (simulat)"
        c.save({"rts": rts})
    if action == "hold_client":
        for case_id in doc.get("case_ids", []):
            decision = c.rt.authorize("analist", "diode.send_hold")
            if not decision.allowed:
                continue
            signal = HoldSignal(case_id=case_id, hold=True, approved_by=analyst, approved_at=now(),
                                authority_notified=bool(answer.get("authority_notified", True)))
            try:
                result = c.rt.diode.send_hold(signal)
                if asyncio.iscoroutine(result):
                    await result
                await c.em.custom("hold_signal", f"HOLD trimis spre zona client pentru {case_id}",
                                  {"case_id": case_id}, step="analist", agent=AG["analist"])
            except Exception as exc:  # noqa: BLE001
                log.warning("send_hold: %s", exc)
    c.save({"status": status})
    await c.finish("analist", f"Decizie: {status}")
    return {"decision": action}


async def sigiliu(state: dict) -> dict:
    c = Ctx(state)
    await c.start("sigiliu", "Sigilez dosarul AML")
    seal = c.rt.ledger.seal(c.lead_id)
    c.save({"ledger": {"count": seal.get("count"), "root": seal.get("root"), "sealed": True}})
    await c.em.custom("ledger_seal", f"Dosar AML sigilat: {seal.get('count')} probe", {"root": seal.get("root")},
                      step="sigiliu", agent=AG["sigiliu"])
    await c.finish("sigiliu", f"Sigilat: {seal.get('count')} probe")
    return {}


def new_run_id() -> str:
    return "ARUN-" + uuid.uuid4().hex[:8]
