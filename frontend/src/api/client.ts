import { openEventStream, type StreamSource } from "./sse";
import type {
  AmlStats,
  AttackKind,
  AttackResult,
  BankState,
  Campaign,
  CaseDetail,
  CaseSummary,
  CounterfactualResult,
  CreateCaseBody,
  FilterResult,
  LeadAction,
  LeadDetail,
  LeadSummary,
  LedgerResponse,
  McpInfo,
  Meta,
  MoneyGraph,
  OsintKind,
  OsintResult,
  PolicyDecision,
  Referral,
  RuleCatalogEntry,
  RuleParams,
  ScenarioInfo,
  Stats,
  VerifyResult,
  WallState,
} from "./types";

/**
 * Interfața comună pentru backend-ul real (docs/06 §6) și pentru modul mock.
 * Fiecare metodă corespunde exact unui endpoint; numele căii e în comentariu.
 */
export interface Api {
  readonly mode: "live" | "mock";
  // ---------------------------------------------------------------- zona client
  meta(): Promise<Meta>; // GET /api/meta
  stats(): Promise<Stats>; // GET /api/stats
  scenarios(): Promise<ScenarioInfo[]>; // GET /api/scenarios
  createCase(body: CreateCaseBody): Promise<{ case_id: string }>; // POST /api/cases
  cases(): Promise<CaseSummary[]>; // GET /api/cases
  caseDetail(id: string): Promise<CaseDetail>; // GET /api/cases/{id}
  runCase(id: string): Promise<{ run_id: string }>; // POST /api/cases/{id}/run
  caseEvents(id: string): StreamSource; // GET /api/cases/{id}/events (SSE)
  approve(id: string, body: { action: "approve" | "reject"; note?: string; approver?: string }): Promise<{ ok: boolean; status: string }>; // POST /api/cases/{id}/approve
  counterfactual(id: string, body: { field: string; value: unknown }): Promise<CounterfactualResult>; // POST /api/cases/{id}/counterfactual
  letterCheck(id: string, body: { body: string }): Promise<FilterResult>; // POST /api/cases/{id}/letter/check
  ledger(caseId: string): Promise<LedgerResponse>; // GET /api/ledger/{case_id}
  verify(dossier: unknown): Promise<VerifyResult>; // POST /api/verify
  rules(): Promise<RuleCatalogEntry[]>; // GET /api/rules
  ruleParams(): Promise<RuleParams>; // GET /api/rules/params
  putRuleParams(params: RuleParams): Promise<RuleParams>; // PUT /api/rules/params
  wall(): Promise<WallState>; // GET /api/wall
  wallAttack(body: { kind: AttackKind; payload?: unknown }): Promise<AttackResult>; // POST /api/wall/attack
  evalReport(): Promise<Record<string, unknown>>; // GET /api/eval
  mcp(): Promise<McpInfo>; // GET /api/mcp
  bank(customerRef: string): Promise<BankState>; // GET /api/bank/{customer_ref}
  bankDispute(customerRef: string, body: { transaction_id: string; text: string }): Promise<{ case_id: string }>; // POST /api/bank/{customer_ref}/dispute
  demoScam(body: { customer_ref: string; card_last4?: string }): Promise<{ transaction_id: string; amount: number }>; // POST /api/demo/scam
  // ---------------------------------------------------------------- zona AML
  amlStats(): Promise<AmlStats>; // GET /api/aml/stats
  amlReferrals(): Promise<Referral[]>; // GET /api/aml/referrals
  amlLeads(): Promise<LeadSummary[]>; // GET /api/aml/leads
  amlLead(id: string): Promise<LeadDetail>; // GET /api/aml/leads/{lead_id}
  amlRunLead(id: string): Promise<{ run_id: string }>; // POST /api/aml/leads/{lead_id}/run
  leadEvents(id: string): StreamSource; // GET /api/aml/leads/{lead_id}/events (SSE)
  amlDecide(id: string, body: { action: LeadAction; note?: string; analyst?: string }): Promise<{ ok: boolean }>; // POST /api/aml/leads/{lead_id}/decide
  amlOsint(body: { target: string; kind?: OsintKind }): Promise<OsintResult>; // POST /api/aml/osint
  amlCampaigns(): Promise<Campaign[]>; // GET /api/aml/campaigns
  amlGraph(): Promise<MoneyGraph>; // GET /api/aml/graph
  amlWall(): Promise<PolicyDecision[] | Record<string, unknown>>; // GET /api/aml/wall
}

export class ApiError extends Error {
  readonly status: number;
  readonly path: string;
  constructor(message: string, status: number, path: string) {
    super(message);
    this.status = status;
    this.path = path;
  }
}

function detailMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const det = (body as { detail: unknown }).detail;
    if (typeof det === "string") return det;
    if (Array.isArray(det)) {
      return det
        .map((x) => (x && typeof x === "object" && "msg" in x ? String((x as { msg: unknown }).msg) : JSON.stringify(x)))
        .join("; ");
    }
  }
  return fallback;
}

export async function fetchJson<T>(path: string, init: RequestInit & { timeoutMs?: number } = {}): Promise<T> {
  const ctrl = new AbortController();
  const timeout = setTimeout(() => ctrl.abort(), init.timeoutMs ?? 20_000);
  try {
    const res = await fetch(path, {
      ...init,
      signal: init.signal ?? ctrl.signal,
      headers: { Accept: "application/json", ...(init.body ? { "Content-Type": "application/json" } : {}), ...init.headers },
    });
    const text = await res.text();
    let body: unknown = null;
    if (text) {
      try {
        body = JSON.parse(text);
      } catch {
        if (!res.ok) throw new ApiError(`${res.status} ${res.statusText}`, res.status, path);
        throw new ApiError("Răspunsul serverului nu e JSON.", res.status, path);
      }
    }
    if (!res.ok) throw new ApiError(detailMessage(body, `${res.status} ${res.statusText}`), res.status, path);
    return body as T;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError("Serverul nu a răspuns la timp.", 0, path);
    }
    throw new ApiError("Serverul nu poate fi contactat.", 0, path);
  } finally {
    clearTimeout(timeout);
  }
}

const enc = encodeURIComponent;
const post = <T>(path: string, body?: unknown) =>
  fetchJson<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
const put = <T>(path: string, body: unknown) => fetchJson<T>(path, { method: "PUT", body: JSON.stringify(body) });
const get = <T>(path: string) => fetchJson<T>(path);

export function createHttpApi(): Api {
  return {
    mode: "live",
    meta: () => get("/api/meta"),
    stats: () => get("/api/stats"),
    scenarios: () => get("/api/scenarios"),
    createCase: (body) => post("/api/cases", body),
    cases: () => get("/api/cases"),
    caseDetail: (id) => get(`/api/cases/${enc(id)}`),
    runCase: (id) => post(`/api/cases/${enc(id)}/run`),
    caseEvents: (id) => (h) => openEventStream(`/api/cases/${enc(id)}/events`, h),
    approve: (id, body) => post(`/api/cases/${enc(id)}/approve`, body),
    counterfactual: (id, body) => post(`/api/cases/${enc(id)}/counterfactual`, body),
    letterCheck: (id, body) => post(`/api/cases/${enc(id)}/letter/check`, body),
    ledger: (caseId) => get(`/api/ledger/${enc(caseId)}`),
    verify: (dossier) => post("/api/verify", dossier),
    rules: () => get("/api/rules"),
    ruleParams: () => get("/api/rules/params"),
    putRuleParams: (params) => put("/api/rules/params", params),
    wall: () => get("/api/wall"),
    wallAttack: (body) => post("/api/wall/attack", body),
    evalReport: () => get("/api/eval"),
    mcp: () => get("/api/mcp"),
    bank: (ref) => get(`/api/bank/${enc(ref)}`),
    bankDispute: (ref, body) => post(`/api/bank/${enc(ref)}/dispute`, body),
    demoScam: (body) => post("/api/demo/scam", body),
    amlStats: () => get("/api/aml/stats"),
    amlReferrals: () => get("/api/aml/referrals"),
    amlLeads: () => get("/api/aml/leads"),
    amlLead: (id) => get(`/api/aml/leads/${enc(id)}`),
    amlRunLead: (id) => post(`/api/aml/leads/${enc(id)}/run`),
    leadEvents: (id) => (h) => openEventStream(`/api/aml/leads/${enc(id)}/events`, h),
    amlDecide: (id, body) => post(`/api/aml/leads/${enc(id)}/decide`, body),
    amlOsint: (body) => post("/api/aml/osint", body),
    amlCampaigns: () => get("/api/aml/campaigns"),
    amlGraph: () => get("/api/aml/graph"),
    amlWall: () => get("/api/aml/wall"),
  };
}

/** Sondează /api/meta. Eșecul (rețea, 404, HTML în loc de JSON) trimite UI-ul în modul mock. */
export async function probeMeta(timeoutMs = 2500): Promise<Meta | null> {
  try {
    const m = await fetchJson<Meta>("/api/meta", { timeoutMs });
    if (m && (m.zone === "client" || m.zone === "aml")) return m;
    return null;
  } catch {
    return null;
  }
}
