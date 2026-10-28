/**
 * Implementarea mock a `Api`. Aceleași forme ca backend-ul (docs/06 §6); zona se alege cu `?zone=aml`.
 * Ca în producție, zona client nu „vede" endpoint-urile AML și invers (răspund 404).
 */
import { ApiError, type Api } from "../api/client";
import type {
  AgentEvent,
  AmlStats,
  AttackKind,
  CaseDetail,
  CaseSummary,
  CounterfactualResult,
  DecisionBrief,
  FilterResult,
  LeadSummary,
  LedgerResponse,
  Meta,
  MoneyGraph,
  PolicyDecision,
  Stats,
  VerifyResult,
  Zone,
} from "../api/types";
import { LEAD_ID, osintLookup } from "./aml";
import { isoRo } from "./calendar";
import { advance, PUBLIC_KEY, type MockCase } from "./engine";
import { MCP, RULES, SCENARIOS, evalReport } from "./fixtures";
import { canonical, merkleRoot, sha256 } from "./sha256";
import { ATTACKS, caseEventSource, createMockCase, leadEventSource, read, startDriver, startRun, transact } from "./store";
import { MULE_IBAN_SHORT } from "./stories";
import type { StreamSource } from "../api/sse";

const ZONE_KEY = "versoml.mock.zone";

export function mockZoneFromUrl(): Zone {
  try {
    const q = new URLSearchParams(window.location.search).get("zone");
    if (q === "aml" || q === "client") {
      sessionStorage.setItem(ZONE_KEY, q);
      return q;
    }
    const s = sessionStorage.getItem(ZONE_KEY);
    if (s === "aml" || s === "client") return s;
  } catch {
    /* fără sessionStorage */
  }
  return "client";
}

const clone = <T>(v: T): T => (v === undefined ? v : (JSON.parse(JSON.stringify(v)) as T));
const delay = <T>(v: T, ms = 120): Promise<T> => new Promise((res) => setTimeout(() => res(clone(v)), ms));
const notFound = (what: string, path: string) => new ApiError(`${what} nu există.`, 404, path);

function slaLeft(deadline: string | null | undefined): number | null {
  if (!deadline) return null;
  return Math.round((new Date(deadline).getTime() - Date.now()) / 1000);
}

function summaryOf(c: MockCase): CaseSummary {
  const s = c.detail.summary;
  return { ...s, sla_seconds_left: slaLeft(s.deadline) };
}

function detailOf(c: MockCase): CaseDetail {
  const d = clone(c.detail);
  d.summary.sla_seconds_left = slaLeft(d.summary.deadline);
  return d;
}

const FORBIDDEN: Array<[RegExp, string]> = [
  [/\bONPCSB\b/gi, "ONPCSB"],
  [/\bRTS\b/g, "RTS"],
  [/\braport\p{L}*/giu, "raport"],
  [/\bsp[ăa]l\p{L}*/giu, "spălare"],
  [/\bsuspec\p{L}*/giu, "suspect"],
  [/\binvestig\p{L}*/giu, "investigație"],
  [/\bAML\b/gi, "AML"],
];

export function filterLetter(body: string): FilterResult {
  const blocked = new Set<string>();
  for (const [re, label] of FORBIDDEN) {
    const m = body.match(re);
    if (m) m.forEach((hit) => blocked.add(hit.trim() || label));
  }
  const canaries = body.match(/versoml-cn-[0-9a-f]{6,}/gi)?.length ?? 0;
  const pii: string[] = [];
  if (/\bRO\d{2}\s?[A-Z]{4}(\s?[0-9A-Z]{4}){4}\b/.test(body)) pii.push("IBAN complet");
  if (/\b[1-8]\d{12}\b/.test(body)) pii.push("CNP");
  if (/\b(?:\d[ -]?){15,18}\d\b/.test(body)) pii.push("număr de card");
  const classifier = /\b(urmărit|monitoriz\p{L}*|dosar penal|poliți\p{L}*|blocat pentru verificări)\b/iu.test(body);
  const reasons: string[] = [];
  if (blocked.size) reasons.push("termeni interziși: scrisoarea ar putea avertiza beneficiarul (tipping-off)");
  if (canaries) reasons.push("token canary din dosarul AML: o scurgere peste zid");
  if (pii.length) reasons.push("date personale care nu aparțin scrisorii");
  if (classifier) reasons.push("clasificatorul Haiku a semnalat o aluzie la verificări asupra beneficiarului");
  return {
    passed: !blocked.size && !canaries && !pii.length && !classifier,
    blocked_terms: Array.from(blocked),
    canaries_found: canaries,
    classifier_flag: classifier,
    pii_findings: pii,
    reasons,
  };
}

function verifyDossier(d: unknown): VerifyResult {
  const obj = (d && typeof d === "object" ? d : {}) as { facts?: Array<Record<string, unknown>>; seal?: Record<string, unknown> | null; case_id?: string };
  const facts = Array.isArray(obj.facts) ? obj.facts : [];
  const checks: VerifyResult["checks"] = [];
  let chainOk = facts.length > 0;
  let hashOk = facts.length > 0;
  let prev: string | null = null;
  for (const f of facts) {
    const payload = { fact_id: f.fact_id, case_id: f.case_id, kind: f.kind, source_tool: f.source_tool, summary: f.summary, content: f.content ?? {} };
    const expected = sha256((prev ?? "") + canonical(payload));
    if (f.sha256 !== expected) hashOk = false;
    if ((f.prev_hash ?? null) !== prev) chainOk = false;
    prev = typeof f.sha256 === "string" ? f.sha256 : null;
  }
  checks.push({ name: "Hash-ul fiecărei probe", ok: hashOk, detail: hashOk ? `${facts.length} probe recalculate, toate potrivite` : "conținutul unei probe nu se potrivește cu hash-ul ei" });
  checks.push({ name: "Lanțul de hash-uri", ok: chainOk, detail: chainOk ? "fiecare probă trimite la cea dinainte" : "lanțul e rupt" });
  const seal = obj.seal;
  if (!seal) {
    checks.push({ name: "Sigiliul", ok: false, detail: "dosarul nu e sigilat încă" });
  } else {
    const root = merkleRoot(facts.map((f) => String(f.sha256)));
    const rootOk = root === seal.root;
    checks.push({ name: "Rădăcina Merkle", ok: rootOk, detail: rootOk ? `rădăcina ${root.slice(0, 16)}… se potrivește` : "rădăcina recalculată diferă de cea sigilată" });
    const sigOk = seal.signature === `${sha256(`ed25519-sim|${String(seal.root)}`)}${sha256(`ed25519-sim-2|${String(seal.root)}`)}` && seal.public_key === PUBLIC_KEY;
    checks.push({ name: "Semnătura Ed25519", ok: sigOk, detail: sigOk ? "semnătură simulată validă (modul demo)" : "semnătura nu corespunde rădăcinii" });
    const countOk = Number(seal.count) === facts.length;
    checks.push({ name: "Numărul de probe", ok: countOk, detail: `${facts.length} în dosar, ${String(seal.count)} la sigilare` });
  }
  return { valid: checks.every((c) => c.ok), checks };
}

function briefs(c: MockCase): DecisionBrief[] {
  return (c.detail.decisions ?? []).map((d) => ({ question: d.question, decision: d.decision }));
}

export function createMockApi(zone: Zone): Api {
  startDriver();
  const clientOnly = (path: string) => {
    if (zone !== "client") throw new ApiError("Endpoint inexistent în zona AML (proces separat).", 404, path);
  };
  const amlOnly = (path: string) => {
    if (zone !== "aml") throw new ApiError("Endpoint inexistent în zona client (proces separat).", 404, path);
  };
  const getCase = (id: string, path: string) => {
    const c = read().cases[id];
    if (!c) throw notFound(`Cazul ${id}`, path);
    return c;
  };

  const api: Api = {
    mode: "mock",
    async meta(): Promise<Meta> {
      const origin = window.location.origin;
      return delay({
        zone,
        version: "mock-1",
        llm: { mode: "replay (mock)", region: "us-east-1", models: { opus: "anthropic.claude-opus-5-5", sonnet: "anthropic.claude-sonnet-5", haiku: "anthropic.claude-haiku-4-5" }, live_ok: false },
        osint_mode: "fixture",
        urls: { client: `${origin}/?zone=client`, aml: `${origin}/?zone=aml` },
      }, 20);
    },
    async stats(): Promise<Stats> {
      clientOnly("/api/stats");
      const cases = Object.values(read().cases);
      const by_status: Record<string, number> = {};
      const by_scenario: Record<string, number> = {};
      let refunded = 0;
      let amountRefunded = 0;
      let recoverable = 0;
      let awaiting = 0;
      let atRisk = 0;
      const decisionTimes: number[] = [];
      for (const c of cases) {
        const s = c.detail.summary;
        by_status[s.status] = (by_status[s.status] ?? 0) + 1;
        if (s.scenario) by_scenario[String(s.scenario)] = (by_scenario[String(s.scenario)] ?? 0) + 1;
        if (s.status === "RAMBURSAT") {
          refunded += 1;
          amountRefunded += s.amount.value;
        }
        if (s.requires_human) awaiting += 1;
        const rec = c.detail.decisions?.find((d) => d.question === "recuperare_escroc");
        if (rec && ["RECHEMARE", "CHARGEBACK"].includes(rec.decision)) recoverable += s.amount.value;
        const left = slaLeft(s.deadline);
        if (left !== null && left > 0 && left < 6 * 3600 && !["RAMBURSAT", "INCHIS", "RESPINS"].includes(s.status)) atRisk += 1;
        const firstDecision = c.events.find((e) => e.name === "decision");
        if (firstDecision) decisionTimes.push((new Date(firstDecision.ts).getTime() - c.ctx.receivedAt) / 1000);
      }
      const open = cases.filter((c) => !["RAMBURSAT", "INCHIS", "RESPINS"].includes(c.detail.summary.status)).length;
      return delay({
        cases_total: cases.length,
        open,
        refunded,
        awaiting_human: awaiting,
        amount_refunded: { value: amountRefunded, currency: "RON" },
        amount_recoverable: { value: recoverable, currency: "RON" },
        avg_decision_seconds: decisionTimes.length ? decisionTimes.reduce((a, b) => a + b, 0) / decisionTimes.length : null,
        deadlines_at_risk: atRisk,
        by_status,
        by_scenario,
      });
    },
    async scenarios() {
      clientOnly("/api/scenarios");
      return delay(SCENARIOS);
    },
    async createCase(body) {
      clientOnly("/api/cases");
      const id = transact((db) => {
        if ("scenario_id" in body) {
          return createMockCase(db, { scenario: body.scenario_id, customerRef: body.scenario_id === "demo_t1" ? "CUST-DEMO-01" : `CUST-${Math.floor(Math.random() * 900 + 100)}` }).caseId;
        }
        const text = body.complaint.text;
        const scenario = /apel|sunat|securitate/i.test(text) ? "vishing_securitate" : /sim|semnal/i.test(text) ? "sim_swap" : /de două ori|dublă/i.test(text) ? "plata_dubla" : "phishing_link";
        return createMockCase(db, { scenario, customerRef: body.complaint.customer_ref || "CUST-NOU", complaintText: text }).caseId;
      });
      return delay({ case_id: id });
    },
    async cases() {
      clientOnly("/api/cases");
      const db = read();
      return delay(db.order.map((id) => summaryOf(db.cases[id])).filter(Boolean));
    },
    async caseDetail(id) {
      clientOnly(`/api/cases/${id}`);
      return delay(detailOf(getCase(id, `/api/cases/${id}`)), 60);
    },
    async runCase(id) {
      clientOnly(`/api/cases/${id}/run`);
      getCase(id, `/api/cases/${id}/run`);
      const runId = transact((db) => startRun(db, id));
      return delay({ run_id: runId });
    },
    caseEvents(id): StreamSource {
      return (h) => {
        h.onStatus?.("open");
        const unsub = caseEventSource(id)(h.onEvent);
        return () => {
          unsub();
          h.onStatus?.("closed");
        };
      };
    },
    async approve(id, body) {
      clientOnly(`/api/cases/${id}/approve`);
      const status = transact((db, hooks) => {
        const c = db.cases[id];
        if (!c) throw notFound(`Cazul ${id}`, `/api/cases/${id}/approve`);
        if (!c.detail.interrupt?.pending || !c.run) throw new ApiError("Nu există nicio aprobare în așteptare.", 409, `/api/cases/${id}/approve`);
        const now = Date.now();
        c.run.approval = { action: body.action, at: now, approver: body.approver || "OPERATOR-DEMO", note: body.note };
        advance(c, now, hooks);
        return c.detail.summary.status;
      });
      return delay({ ok: true, status });
    },
    async counterfactual(id, body): Promise<CounterfactualResult> {
      clientOnly(`/api/cases/${id}/counterfactual`);
      const c = getCase(id, `/api/cases/${id}/counterfactual`);
      const before = briefs(c);
      const after = before.map((b) => ({ ...b }));
      const changed: string[] = [];
      let explanation = "Faptul schimbat nu atinge nicio regulă care decide acest caz: deciziile rămân aceleași.";
      const rubric = c.detail.debate?.rubric ?? [];
      const threshold = Number(read().params.prag_rubrica_recuperare ?? 4);
      const value = body.value === true || body.value === "true";
      if (rubric.length && (body.field === "screen_showed_amount_and_payee" || body.field === "client_admits_sharing_credentials")) {
        const label = body.field === "screen_showed_amount_and_payee" ? "Ecranul a afișat suma și beneficiarul" : "Clientul a dat codul sau parola altcuiva";
        const scoreBefore = rubric.reduce((s, r) => s + (r.value ? r.weight : 0), 0);
        const scoreAfter = rubric.reduce((s, r) => s + ((r.indicator === label ? value : r.value) ? r.weight : 0), 0);
        const rec = after.find((b) => b.question === "recuperare_client");
        if (rec) {
          const next = scoreAfter >= threshold ? "RECUPERARE_PROPUSA" : "NU_RECOMANDAM_RECUPERARE";
          if (next !== rec.decision) {
            rec.decision = next;
            changed.push("recuperare_client");
          }
        }
        explanation =
          body.field === "screen_showed_amount_and_payee"
            ? `Cu legarea dinamică (DSP-10), aprobarea din aplicație arată că clientul a văzut suma și beneficiarul. Rubrica urcă de la ${scoreBefore} la ${scoreAfter} puncte (pragul e ${threshold}), deci recuperarea de la client devine o propunere pe care o semnează un om (DSP-06, PAY-06). Rambursarea rămâne: neglijența gravă nu permite refuzul sau amânarea (PAY-15, C-70/25).`
            : `Dacă clientul ar fi dat codul altcuiva, rubrica urcă de la ${scoreBefore} la ${scoreAfter} puncte (pragul e ${threshold}). Rambursarea rămâne în termen (PAY-15); recuperarea o decide un om.`;
      }
      return delay({ before, after, changed, explanation }, 400);
    },
    async letterCheck(id, body) {
      clientOnly(`/api/cases/${id}/letter/check`);
      const result = filterLetter(body.body);
      if (!result.passed) {
        transact((db) => {
          db.wall.blocks.unshift({ at: isoRo(Date.now()), case_id: id, reasons: result.reasons ?? [], terms: result.blocked_terms ?? [] });
          db.wall.blocks = db.wall.blocks.slice(0, 30);
        });
      }
      return delay(result, 350);
    },
    async ledger(caseId): Promise<LedgerResponse> {
      clientOnly(`/api/ledger/${caseId}`);
      const c = getCase(caseId, `/api/ledger/${caseId}`);
      const dossier = { case_id: caseId, facts: c.detail.facts ?? [], seal: c.seal };
      return delay({ facts: clone(dossier.facts), seal: clone(c.seal), verify: verifyDossier(dossier) });
    },
    async verify(dossier) {
      clientOnly("/api/verify");
      return delay(verifyDossier(dossier), 500);
    },
    async rules() {
      clientOnly("/api/rules");
      const params = read().params;
      return delay(
        RULES.map((r) => ({
          ...r,
          params: r.params && !Array.isArray(r.params) ? Object.fromEntries(Object.keys(r.params).map((k) => [k, params[k] ?? null])) : r.params,
        })),
      );
    },
    async ruleParams() {
      clientOnly("/api/rules/params");
      return delay(read().params);
    },
    async putRuleParams(p) {
      clientOnly("/api/rules/params");
      const out = transact((db) => {
        db.params = { ...db.params, ...p };
        return db.params;
      });
      return delay(out, 250);
    },
    async wall() {
      clientOnly("/api/wall");
      return delay(read().wall);
    },
    async wallAttack(body) {
      clientOnly("/api/wall/attack");
      const kind = body.kind as AttackKind;
      const a = ATTACKS[kind];
      if (!a) throw new ApiError("Tip de atac necunoscut.", 422, "/api/wall/attack");
      const now = Date.now();
      transact((db) => {
        if (kind === "read_aml_tool" || kind === "prompt_injection") {
          const ev = a.result.evidence as Partial<PolicyDecision>;
          db.wall.denials.unshift({
            allowed: false,
            principal: ev.principal ?? "LLM izolat (Receptor)",
            action: ev.action ?? "letter.include_aml_value",
            resource: ev.resource ?? "sink:letter",
            reason: a.result.detail,
            policy_ids: ev.policy_ids ?? ["label-sinks"],
            at: isoRo(now),
          });
        }
        if (kind === "letter_tipping_off") {
          db.wall.blocks.unshift({ at: isoRo(now), case_id: "CT-ATAC-DEMO", reasons: ["termeni interziși"], terms: ["ONPCSB", "raportat", "investigat", "AML"] });
        }
        if (kind === "diode_text_field") {
          db.wall.denials.unshift({ allowed: false, principal: "dioda/hold", action: "diode.receive_hold", resource: "zone:client", reason: "HoldSignal cu câmp necunoscut „note”: respins (extra=forbid)", policy_ids: ["diode-schema"], at: isoRo(now) });
        }
        db.wall.denials = db.wall.denials.slice(0, 40);
        db.wall.blocks = db.wall.blocks.slice(0, 40);
      });
      return delay({ ...a.result, evidence: a.result.evidence }, 700);
    },
    async evalReport() {
      clientOnly("/api/eval");
      return delay(evalReport(Date.now()));
    },
    async mcp() {
      clientOnly("/api/mcp");
      return delay(MCP);
    },
    async bank(ref) {
      clientOnly(`/api/bank/${ref}`);
      const acct = read().bank[ref];
      if (!acct) throw notFound(`Clientul ${ref}`, `/api/bank/${ref}`);
      const { linked: _linked, ...state } = acct;
      void _linked;
      return delay(state, 60);
    },
    async bankDispute(ref, body) {
      clientOnly(`/api/bank/${ref}/dispute`);
      const caseId = transact((db) => {
        const acct = db.bank[ref];
        if (!acct) throw notFound(`Clientul ${ref}`, `/api/bank/${ref}/dispute`);
        const tx = acct.transactions.find((t) => t.id === body.transaction_id);
        if (!tx) throw notFound(`Tranzacția ${body.transaction_id}`, `/api/bank/${ref}/dispute`);
        if (acct.linked[tx.id]) return acct.linked[tx.id];
        const c = createMockCase(db, {
          scenario: ref === "CUST-DEMO-02" ? "inel_carausi" : "demo_t1",
          customerRef: ref,
          amount: Math.abs(tx.amount),
          alias: acct.customer_alias,
          txId: tx.id,
          complaintText: body.text,
        });
        c.ctx.executedAt = new Date(tx.ts).getTime();
        acct.linked[tx.id] = c.caseId;
        tx.status = "contestată";
        tx.disputable = false;
        startRun(db, c.caseId);
        acct.notifications.unshift({ ts: isoRo(Date.now()), text: `Am primit contestația ${c.caseId}. Îți răspundem până la termenul legal.`, kind: "info" });
        return c.caseId;
      });
      return delay({ case_id: caseId }, 300);
    },
    async demoScam(body) {
      clientOnly("/api/demo/scam");
      const out = transact((db) => {
        const acct = db.bank[body.customer_ref];
        if (!acct) throw notFound(`Clientul ${body.customer_ref}`, "/api/demo/scam");
        const amount = body.customer_ref === "CUST-DEMO-02" ? 1850 : 3200;
        const id = `TX-SCAM-${Date.now().toString(36).toUpperCase()}`;
        acct.transactions.unshift({ id, ts: isoRo(Date.now()), description: `Transfer către ${MULE_IBAN_SHORT}`, amount: -amount, direction: "out", status: "executată", disputable: true });
        acct.balance = Math.round((acct.balance - amount) * 100) / 100;
        acct.notifications.unshift({ ts: isoRo(Date.now()), text: `Ai trimis ${new Intl.NumberFormat("ro-RO").format(amount)} lei către ${MULE_IBAN_SHORT}.`, kind: "debit" });
        return { transaction_id: id, amount };
      });
      return delay(out, 500);
    },
    // ---------------------------------------------------------------- AML
    async amlStats(): Promise<AmlStats> {
      amlOnly("/api/aml/stats");
      const aml = read().aml;
      const leads = Object.values(aml.leads);
      const flagged = new Set<string>();
      const communities = new Set<number>();
      let atRisk = 0;
      for (const l of leads) {
        for (const n of l.detail.graph.nodes) {
          if (n.flagged) {
            flagged.add(n.id);
            atRisk += n.amount_in;
          }
          if (n.community !== null) communities.add(n.community);
        }
      }
      return delay({
        referrals: aml.referrals.length,
        leads: leads.length,
        rts_drafts: leads.filter((l) => l.detail.rts).length,
        accounts_flagged: flagged.size,
        amount_at_risk: { value: atRisk, currency: "RON" },
        communities: communities.size,
      });
    },
    async amlReferrals() {
      amlOnly("/api/aml/referrals");
      return delay(read().aml.referrals);
    },
    async amlLeads(): Promise<LeadSummary[]> {
      amlOnly("/api/aml/leads");
      const aml = read().aml;
      return delay(
        aml.order.map((id) => {
          const l = aml.leads[id];
          return {
            lead_id: id,
            case_ids: l.detail.lead.case_ids,
            top_score: Math.max(0, ...(l.detail.lead.accounts ?? []).map((a) => a.score)),
            typologies: l.detail.lead.typologies ?? [],
            recommendation: l.detail.lead.recommendation ?? "MONITORIZARE",
            status: l.status,
            updated_at: l.updated_at,
          };
        }),
      );
    },
    async amlLead(id) {
      amlOnly(`/api/aml/leads/${id}`);
      const l = read().aml.leads[id];
      if (!l) throw notFound(`Pista ${id}`, `/api/aml/leads/${id}`);
      const d = clone(l.detail);
      d.lead.osint = d.osint;
      d.lead.innocent_hypotheses = d.innocent;
      d.timeline = clone(l.events.slice(-80));
      return delay(d, 60);
    },
    async amlRunLead(id) {
      amlOnly(`/api/aml/leads/${id}/run`);
      const runId = transact((db) => {
        const l = db.aml.leads[id];
        if (!l) throw notFound(`Pista ${id}`, `/api/aml/leads/${id}/run`);
        const rid = `run-${id}-${Math.floor(Date.now() / 1000).toString(36)}`;
        l.run = { runId: rid, startedAt: Date.now(), cursor: 0, done: false, decided: null };
        return rid;
      });
      return delay({ run_id: runId });
    },
    leadEvents(id): StreamSource {
      return (h) => {
        h.onStatus?.("open");
        const unsub = leadEventSource(id)(h.onEvent);
        return () => {
          unsub();
          h.onStatus?.("closed");
        };
      };
    },
    async amlDecide(id, body) {
      amlOnly(`/api/aml/leads/${id}/decide`);
      transact((db, hooks) => {
        const l = db.aml.leads[id];
        if (!l) throw notFound(`Pista ${id}`, `/api/aml/leads/${id}/decide`);
        const now = Date.now();
        const analyst = body.analyst || "ANALIST-07";
        const labels: Record<string, string> = {
          file_rts: "RTS depus (simulat): ceasul de 24 h al tranzacției reținute a pornit.",
          close: "Pistă închisă de analist, cu motivare.",
          request_info: "Informații suplimentare cerute; pista rămâne deschisă.",
          hold_client: "HOLD emis spre zona client prin diodă: un boolean, fără detalii.",
        };
        l.status = { file_rts: "RTS depus", close: "închisă", request_info: "informații cerute", hold_client: "HOLD emis" }[body.action];
        l.updated_at = isoRo(now);
        if (body.action === "file_rts" && l.detail.rts) l.detail.rts.status = "depus (simulat)";
        if (body.action === "close") l.detail.lead.recommendation = "INCHIDE";
        if (l.run) {
          l.run.decided = body.action;
          l.run.done = true;
        }
        const push = (type: AgentEvent["type"], fields: Partial<AgentEvent>) => {
          const ev: AgentEvent = { type, zone: "aml", run_id: l.run?.runId ?? "run-aml-0", case_id: id, seq: hooks.nextSeq(), ts: isoRo(now), step: "analist", agent: "Analist AML", name: null, message: null, data: {}, ...fields };
          l.events.push(ev);
        };
        push("CUSTOM", { name: "decision", message: `${analyst}: ${labels[body.action]}`, data: { action: body.action, analyst, note: body.note ?? null } });
        if (body.action === "hold_client") {
          push("CUSTOM", { name: "hold_signal", message: "HoldSignal {hold: true, approved_by} trimis prin diodă.", data: { hold: true, approved_by: analyst } });
          db.aml.wall.unshift({ allowed: true, principal: analyst, action: "diode.send_hold", resource: "zone:client", reason: "HoldSignal aprobat de om: un boolean, fără text liber", policy_ids: ["diode-schema", "human-only-hold"], at: isoRo(now) });
          for (const cid of l.detail.lead.case_ids) {
            const c = db.cases[cid];
            if (!c) continue;
            c.detail.hold = { received: true, approved_by: analyst, approved_at: isoRo(now), authority_notified: false };
            c.events.push({ type: "CUSTOM", zone: "client", run_id: c.run?.runId ?? "run-0", case_id: cid, seq: hooks.nextSeq(), ts: isoRo(now), step: "reguli", agent: "Dioda", name: "hold_signal", message: "HOLD primit prin diodă: da. Fără motiv, fără detalii. Rambursarea rămâne în termen.", data: { hold: true } });
          }
        }
        push("RUN_FINISHED", { message: "Rularea Investigatorului s-a încheiat cu decizia analistului." });
        l.detail.timeline = l.events.slice(-80);
      });
      return delay({ ok: true });
    },
    async amlOsint(body) {
      amlOnly("/api/aml/osint");
      return delay(osintLookup(body.target, body.kind ?? "auto"), 900);
    },
    async amlCampaigns() {
      amlOnly("/api/aml/campaigns");
      return delay(read().aml.campaigns);
    },
    async amlGraph(): Promise<MoneyGraph> {
      amlOnly("/api/aml/graph");
      const aml = read().aml;
      const nodes = new Map<string, MoneyGraph["nodes"][number]>();
      const edges: MoneyGraph["edges"] = [];
      for (const l of Object.values(aml.leads)) {
        for (const n of l.detail.graph.nodes) if (!nodes.has(n.id)) nodes.set(n.id, n);
        edges.push(...l.detail.graph.edges.map((e) => ({ ...e, id: `${l.detail.lead.lead_id}:${e.id}` })));
      }
      return delay({ nodes: Array.from(nodes.values()), edges });
    },
    async amlWall() {
      amlOnly("/api/aml/wall");
      return delay(read().aml.wall);
    },
  };
  return api;
}

export { LEAD_ID };
