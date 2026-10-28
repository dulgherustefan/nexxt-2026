"""Serviciul zonei AML: primirea faptelor prin diodă, pistele, rulările și decizia analistului."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime
from typing import Any

from langgraph.types import Command

from versoml.contracts import DisputeFacts
from versoml.shared.events import Emitter, now
from versoml.zone_aml import agents as A
from versoml.zone_aml.graph import build_graph
from versoml.zone_aml.runtime import AmlRuntime, get_runtime

log = logging.getLogger("versoml.aml.service")


class AmlService:
    def __init__(self, runtime: AmlRuntime | None = None):
        self.rt = runtime or get_runtime()
        self._graph = None
        self._conn = None
        self._tasks: set[asyncio.Task] = set()
        self._running: set[str] = set()

    async def graph(self):
        if self._graph is None:
            try:
                import aiosqlite
                from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

                self._conn = await aiosqlite.connect(str(self.rt.settings.var_dir / "aml_checkpoints.db"))
                saver = AsyncSqliteSaver(self._conn)
            except Exception as exc:  # noqa: BLE001
                log.warning("checkpointer SQLite indisponibil (%s); folosesc memoria", exc)
                from langgraph.checkpoint.memory import InMemorySaver

                saver = InMemorySaver()
            self._graph = build_graph(saver)
        return self._graph

    async def close(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            self._graph = None

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # ------------------------------------------------------------ dioda

    def _lead_for(self, facts: DisputeFacts) -> str:
        """Leagă contestația de o pistă: același IBAN beneficiar, aceeași firmă sau același domeniu (M6)."""
        existing = [r for r in self.rt.referrals.all() if r.get("facts")]
        try:
            from versoml.ml.m6_entity_resolution import link_cases

            rows = [r["facts"] for r in existing] + [facts.model_dump(mode="json")]
            clusters = link_cases(rows)
            for cluster in clusters:
                ids = cluster.get("case_ids") or cluster.get("cases") or []
                if facts.case_id in ids:
                    for r in existing:
                        if r["facts"]["case_id"] in ids and r.get("lead_id"):
                            return r["lead_id"]
        except Exception as exc:  # noqa: BLE001
            log.info("M6 indisponibil (%s); leg după IBAN și domeniu", exc)
        keys = {facts.beneficiary.iban, facts.attack.domain} - {None}
        for r in existing:
            other = {r["facts"]["beneficiary"].get("iban"), (r["facts"].get("attack") or {}).get("domain")} - {None}
            if keys & other and r.get("lead_id"):
                return r["lead_id"]
        basis = facts.beneficiary.iban or facts.attack.domain or facts.case_id
        return "PL-" + hashlib.sha256(basis.encode()).hexdigest()[:6].upper()

    def receive(self, facts: DisputeFacts) -> dict:
        lead_id = self._lead_for(facts)
        self.rt.referrals.put(facts.case_id, {"id": facts.case_id, "lead_id": lead_id, "facts": facts.model_dump(mode="json"),
                                              "received_at": now().isoformat()})
        try:
            self.rt.repo.save_referral(facts)
        except Exception as exc:  # noqa: BLE001
            log.info("save_referral: %s", exc)
        lead = self.rt.leads.get(lead_id) or {"lead_id": lead_id, "created_at": now().isoformat(), "status": "NOU"}
        lead["updated_at"] = now().isoformat()
        lead["case_ids"] = sorted(set(lead.get("case_ids", [])) | {facts.case_id})
        self.rt.leads.put(lead_id, lead)
        self._spawn(self.run(lead_id))
        return {"ok": True, "lead_id": lead_id}

    def ingest_core_tx(self, payload: dict) -> None:
        try:
            ts = datetime.fromisoformat(payload["ts"]) if payload.get("ts") else now()
            self.rt.repo.ingest_demo_payment(payload.get("from_ref"), payload.get("to_iban"), float(payload.get("amount", 0)), ts)
        except Exception as exc:  # noqa: BLE001
            log.info("ingest_demo_payment: %s", exc)

    # ------------------------------------------------------------ rulări

    async def run(self, lead_id: str) -> str:
        if lead_id in self._running:
            await asyncio.sleep(1.5)
        run_id = A.new_run_id()
        self.rt.bus.reset(lead_id)
        self.rt.leads.update(lead_id, {"run_id": run_id, "status": "IN_ANALIZA", "pipeline_status": {},
                                       "interrupt": {"pending": False}, "started_at": now().isoformat()})
        self._spawn(self._drive(lead_id, run_id, {"lead_id": lead_id, "run_id": run_id}))
        return run_id

    async def _drive(self, lead_id: str, run_id: str, payload: Any) -> None:
        em = Emitter(self.rt.bus, lead_id, run_id, lead_id)
        config = {"configurable": {"thread_id": f"{lead_id}:{run_id}"}, "recursion_limit": 40}
        self._running.add(lead_id)
        try:
            if not isinstance(payload, Command):
                await em.run_started("Investigatorul a preluat pista")
            graph = await self.graph()
            result = await graph.ainvoke(payload, config)
            if isinstance(result, dict) and result.get("__interrupt__"):
                return
            await em.run_finished("Pistă închisă de analist", {"status": (self.rt.leads.get(lead_id) or {}).get("status")})
        except Exception as exc:  # noqa: BLE001
            log.exception("pista %s a eșuat", lead_id)
            self.rt.leads.update(lead_id, {"status": "EROARE", "error": str(exc)[:300]})
            await em.run_error(f"Eroare: {str(exc)[:200]}")
        finally:
            self._running.discard(lead_id)

    async def decide(self, lead_id: str, action: str, note: str | None, analyst: str | None) -> dict:
        lead = self.rt.leads.get(lead_id) or {}
        pending = lead.get("interrupt") or {}
        if not pending.get("pending") or pending.get("resuming"):
            return {"ok": False, "detail": "Nicio decizie nu așteaptă analistul."}
        self.rt.leads.update(lead_id, {"interrupt": {**pending, "resuming": True}})
        resume = Command(resume={"action": action, "note": note, "analyst": analyst or "ANALIST-07",
                                 "authority_notified": action == "hold_client"})
        run_id = lead.get("run_id", "run")
        em_config_id = f"{lead_id}:{run_id}"
        self._spawn(self._resume(lead_id, run_id, em_config_id, resume))
        return {"ok": True}

    async def _resume(self, lead_id: str, run_id: str, thread_id: str, resume: Command) -> None:
        em = Emitter(self.rt.bus, lead_id, run_id, lead_id)
        try:
            graph = await self.graph()
            await graph.ainvoke(resume, {"configurable": {"thread_id": thread_id}, "recursion_limit": 40})
            await em.run_finished("Decizia analistului a fost aplicată", {"status": (self.rt.leads.get(lead_id) or {}).get("status")})
        except Exception as exc:  # noqa: BLE001
            log.exception("decizia pe %s a eșuat", lead_id)
            await em.run_error(f"Eroare: {str(exc)[:200]}")

    # ------------------------------------------------------------ citire

    def stats(self) -> dict:
        leads = self.rt.leads.all()
        refs = self.rt.referrals.all()
        flagged = {a["account"] for l in leads for a in l.get("accounts", []) if a.get("score", 0) >= 0.7}
        return {"referrals": len(refs), "leads": len(leads),
                "rts_drafts": sum(1 for l in leads if l.get("rts")), "accounts_flagged": len(flagged),
                "amount_at_risk": round(sum(float(r["facts"]["amount"]["value"]) for r in refs), 2),
                "communities": len({a.get("community") for l in leads for a in l.get("accounts", []) if a.get("community") is not None})}

    def list_referrals(self) -> list[dict]:
        out = []
        for r in self.rt.referrals.all():
            f = r["facts"]
            out.append({"case_id": f["case_id"], "received_at": r.get("received_at"), "amount": f["amount"],
                        "beneficiary_iban_masked": A.mask_iban(f["beneficiary"].get("iban")),
                        "scenario": f.get("scenario"), "lead_id": r.get("lead_id")})
        return out

    def list_leads(self) -> list[dict]:
        out = []
        for l in self.rt.leads.all():
            out.append({"lead_id": l["lead_id"], "case_ids": l.get("case_ids", []),
                        "top_score": max([a.get("score", 0) for a in l.get("accounts", [])] or [0]),
                        "typologies": [t.get("name") or t.get("typology") for t in l.get("typologies", [])],
                        "recommendation": l.get("recommendation"), "status": l.get("status"),
                        "updated_at": l.get("updated_at")})
        return out

    def lead_detail(self, lead_id: str) -> dict | None:
        l = self.rt.leads.get(lead_id)
        if not l:
            return None
        status_map = l.get("pipeline_status", {})
        nodes = [{**n, "agent": A.AG.get(n["id"]), **status_map.get(n["id"], {"status": "idle"})} for n in A.PIPELINE_NODES]
        lead = {"lead_id": lead_id, "case_ids": l.get("case_ids", []), "accounts": l.get("accounts", []),
                "typologies": [t.get("name") or t.get("typology") for t in l.get("typologies", [])],
                "osint": l.get("osint", []), "innocent_hypotheses": l.get("innocent", []),
                "recommendation": l.get("recommendation") or "MONITORIZARE", "rts_draft_id": lead_id if l.get("rts") else None,
                "canary": None}
        return {"lead": lead, "status": l.get("status"), "graph": l.get("graph") or {"nodes": [], "edges": []},
                "osint": l.get("osint", []), "osint_summary": l.get("osint_summary"), "innocent": l.get("innocent", []),
                "innocent_detail": l.get("innocent_detail", []), "typologies_detail": l.get("typologies", []),
                "rts": l.get("rts") or {"status": "nepregătit"}, "clocks": l.get("clocks", []),
                "pipeline": {"nodes": nodes, "edges": [{"source": s, "target": t} for s, t in A.PIPELINE_EDGES]},
                "interrupt": l.get("interrupt") or {"pending": False}, "ledger": l.get("ledger"),
                "facts": [f.model_dump(mode="json") for f in self.rt.ledger.facts(lead_id)],
                "timeline": [e.model_dump(mode="json") for e in self.rt.bus.history(lead_id)][-80:]}

    def campaigns(self) -> list[dict]:
        groups: dict[str, dict] = {}
        for r in self.rt.referrals.all():
            f = r["facts"]
            key = (f.get("attack") or {}).get("domain") or f["beneficiary"].get("iban") or f["case_id"]
            grp = groups.setdefault(key, {"campaign_id": "CMP-" + hashlib.sha256(key.encode()).hexdigest()[:5].upper(),
                                          "cases": [], "shared": {"domains": set(), "ibans": set(), "phones": set()},
                                          "amount_total": 0.0})
            grp["cases"].append(f["case_id"])
            grp["amount_total"] += float(f["amount"]["value"])
            if (f.get("attack") or {}).get("domain"):
                grp["shared"]["domains"].add(f["attack"]["domain"])
            if f["beneficiary"].get("iban"):
                grp["shared"]["ibans"].add(A.mask_iban(f["beneficiary"]["iban"]))
            if (f.get("attack") or {}).get("phone"):
                grp["shared"]["phones"].add(f["attack"]["phone"])
        return [{**g, "shared": {k: sorted(v) for k, v in g["shared"].items()}, "amount_total": round(g["amount_total"], 2)}
                for g in groups.values()]

    def network(self) -> dict:
        nodes, edges, seen = [], [], set()
        for l in self.rt.leads.all():
            for n in (l.get("graph") or {}).get("nodes", []):
                if n["id"] not in seen:
                    seen.add(n["id"])
                    nodes.append(n)
            edges += (l.get("graph") or {}).get("edges", [])
        return {"nodes": nodes, "edges": edges}

    async def osint_lookup(self, target: str, kind: str = "auto") -> dict:
        from versoml.osint.investigate import extract_artifacts, investigate

        artifacts = extract_artifacts(target) if kind == "auto" else {f"{kind}s" if not kind.endswith("s") else kind: [target]}
        if kind == "company":
            artifacts = {"companies": [target]}
        if not any(artifacts.values()):
            artifacts = {"companies": [target]}
        decision = self.rt.authorize("osint", "aml.osint.web_search")
        if not decision.allowed:
            return {"findings": [], "raw": {}, "denied": decision.model_dump(mode="json")}
        results = await investigate(artifacts)
        findings, raw = [], {}
        for r in results:
            data = r.model_dump(mode="json") if hasattr(r, "model_dump") else dict(r)
            raw[f"{data.get('tool')}:{list((data.get('args') or {}).values())[:1]}"] = data
            findings.append({"tool": data.get("tool"), "target": str(next(iter((data.get("args") or {}).values()), target)),
                             "ok": data.get("ok"), "summary": data.get("summary"), "signal": data.get("signal", "neutru"),
                             "source_url": data.get("source_url"), "mode": data.get("mode", "live"), "fact_id": None,
                             "latency_ms": data.get("latency_ms")})
        return {"findings": findings, "raw": raw, "artifacts": artifacts}


_service: AmlService | None = None


def get_service() -> AmlService:
    global _service
    if _service is None:
        _service = AmlService()
    return _service
