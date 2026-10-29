import { openEventStream, TUNNEL_HEADERS, type StreamSource } from "./sse";

export { TUNNEL_HEADERS };
import type {
  AmlStats,
  ApproveBody,
  AttackKind,
  AttackResult,
  BankState,
  Campaign,
  CaseDetail,
  CaseSummary,
  CounterfactualResult,
  CreateCaseBody,
  CustomerHit,
  FilterResult,
  IntakePreview,
  IntakePreviewBody,
  KbAnswer,
  KbHit,
  KbStats,
  LeadAction,
  LeadDetail,
  LeadSummary,
  LedgerResponse,
  McpInfo,
  Meta,
  MoneyGraph,
  OperatorInfo,
  OsintKind,
  OsintResult,
  PolicyDecision,
  Precedent,
  Referral,
  RuleCatalogEntry,
  RuleParams,
  ScenarioInfo,
  SealCheck,
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
  approve(id: string, body: ApproveBody): Promise<{ ok: boolean; status: string }>; // POST /api/cases/{id}/approve (operator session)
  precedents(id: string): Promise<Precedent[]>; // GET /api/cases/{id}/precedents
  intakePreview(body: IntakePreviewBody): Promise<IntakePreview>; // POST /api/intake/preview
  customers(q: string): Promise<CustomerHit[]>; // GET /api/customers?q=
  kbSearch(params: { q: string; k?: number; kind?: string }): Promise<KbHit[]>; // GET /api/kb/search
  kbAsk(body: { question: string; k?: number }): Promise<KbAnswer>; // POST /api/kb/ask
  kbStats(): Promise<KbStats>; // GET /api/kb/stats
  counterfactual(id: string, body: { field: string; value: unknown }): Promise<CounterfactualResult>; // POST /api/cases/{id}/counterfactual
  letterCheck(id: string, body: { body: string }): Promise<FilterResult>; // POST /api/cases/{id}/letter/check
  ledger(caseId: string): Promise<LedgerResponse>; // GET /api/ledger/{case_id} (operator session)
  verify(dossier: unknown): Promise<VerifyResult>; // POST /api/verify
  verifySeal(caseId: string, root: string): Promise<SealCheck>; // POST /api/verify/seal (public, needs the QR root)
  rules(): Promise<RuleCatalogEntry[]>; // GET /api/rules
  ruleParams(): Promise<RuleParams>; // GET /api/rules/params
  putRuleParams(params: RuleParams): Promise<RuleParams>; // PUT /api/rules/params (operator session, rules role)
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
  amlKbSearch(params: { q: string; k?: number }): Promise<KbHit[]>; // GET /api/aml/kb/search
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
      headers: { Accept: "application/json", ...TUNNEL_HEADERS, ...(init.body ? { "Content-Type": "application/json" } : {}), ...init.headers },
    });
    const text = await res.text();
    let body: unknown = null;
    if (text) {
      try {
        body = JSON.parse(text);
      } catch {
        if (!res.ok) throw new ApiError(`${res.status} ${res.statusText}`, res.status, path);
        throw new ApiError("The server sent a response that isn’t JSON.", res.status, path);
      }
    }
    if (!res.ok) throw new ApiError(detailMessage(body, `${res.status} ${res.statusText}`), res.status, path);
    return body as T;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError("The server didn’t answer in time.", 0, path);
    }
    throw new ApiError("Can’t reach the server.", 0, path);
  } finally {
    clearTimeout(timeout);
  }
}

const enc = encodeURIComponent;
const post = <T>(path: string, body?: unknown, timeoutMs?: number) =>
  fetchJson<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body), timeoutMs });
const get = <T>(path: string) => fetchJson<T>(path);

/** "?q=refund&k=6": empty values are left out. */
function query(params: Record<string, string | number | undefined | null>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
}

// The intake preview and the grounded answer may call a model: give them longer than the default 20 s.
const MODEL_TIMEOUT_MS = 60_000;

// ---------------------------------------------------------------- the operator session

/**
 * Who signs in this console. Signatures, rule changes and the evidence file need a signed session from the server,
 * sent as a bearer token; the signer is never taken from the request body. In demo mode the server names a demo
 * operator for each console tab, and every signature made with it says it came from a demo session.
 */
interface SessionGrant {
  token: string;
  operator: OperatorInfo;
}

const SESSION_KEY = "versoml.operator.session";
let grant: SessionGrant | null = null;
let asking: Promise<SessionGrant> | null = null;

function keep(next: SessionGrant | null): void {
  grant = next;
  try {
    if (next) sessionStorage.setItem(SESSION_KEY, JSON.stringify(next));
    else sessionStorage.removeItem(SESSION_KEY);
  } catch {
    /* no sessionStorage: the session lives in memory for this page */
  }
}

function stored(): SessionGrant | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as SessionGrant) : null;
  } catch {
    return null;
  }
}

/** The console's operator session; a new demo one when there is none or it is about to expire. */
export async function operatorSession(): Promise<SessionGrant> {
  grant ??= stored();
  if (grant && Date.parse(grant.operator.expires_at) - Date.now() > 60_000) return grant;
  asking ??= fetchJson<SessionGrant>("/api/session/demo", { method: "POST" })
    .then((next) => {
      keep(next);
      return next;
    })
    .finally(() => {
      asking = null;
    });
  return asking;
}

/** A call made as the signed-in operator. A 401 (a restarted server, an expired session) gets one fresh session
 * and one retry. */
async function asOperator<T>(path: string, init: RequestInit & { timeoutMs?: number } = {}): Promise<T> {
  const call = async () =>
    fetchJson<T>(path, { ...init, headers: { ...init.headers, Authorization: `Bearer ${(await operatorSession()).token}` } });
  try {
    return await call();
  } catch (err) {
    if (!(err instanceof ApiError) || err.status !== 401) throw err;
    keep(null);
    return call();
  }
}

const opGet = <T>(path: string) => asOperator<T>(path);
const opPost = <T>(path: string, body: unknown) => asOperator<T>(path, { method: "POST", body: JSON.stringify(body) });
const opPut = <T>(path: string, body: unknown) => asOperator<T>(path, { method: "PUT", body: JSON.stringify(body) });

export function createHttpApi(): Api {
  return {
    mode: "live",
    meta: () => get("/api/meta"),
    stats: () => get("/api/stats"),
    scenarios: () => get("/api/scenarios"),
    createCase: (body) => post("/api/cases", body),
    cases: () => get("/api/cases"),
    caseDetail: (id) => opGet(`/api/cases/${enc(id)}`),
    runCase: (id) => post(`/api/cases/${enc(id)}/run`),
    caseEvents: (id) => (h) =>
      openEventStream(`/api/cases/${enc(id)}/events`, h, async () => ({ Authorization: `Bearer ${(await operatorSession()).token}` })),
    approve: (id, body) => opPost(`/api/cases/${enc(id)}/approve`, body),
    precedents: (id) => get(`/api/cases/${enc(id)}/precedents`),
    intakePreview: (body) => post("/api/intake/preview", body, MODEL_TIMEOUT_MS),
    customers: (q) => opGet(`/api/customers${query({ q })}`),
    kbSearch: ({ q, k, kind }) => get(`/api/kb/search${query({ q, k, kind })}`),
    kbAsk: (body) => post("/api/kb/ask", body, MODEL_TIMEOUT_MS),
    kbStats: () => get("/api/kb/stats"),
    counterfactual: (id, body) => post(`/api/cases/${enc(id)}/counterfactual`, body),
    letterCheck: (id, body) => post(`/api/cases/${enc(id)}/letter/check`, body),
    ledger: (caseId) => opGet(`/api/ledger/${enc(caseId)}`),
    verify: (dossier) => opPost("/api/verify", dossier),
    verifySeal: (caseId, root) => post("/api/verify/seal", { case_id: caseId, root }),
    rules: () => get("/api/rules"),
    ruleParams: () => get("/api/rules/params"),
    putRuleParams: (params) => opPut("/api/rules/params", params),
    wall: () => get("/api/wall"),
    wallAttack: (body) => post("/api/wall/attack", body),
    evalReport: () => get("/api/eval"),
    mcp: () => get("/api/mcp"),
    bank: (ref) => get(`/api/bank/${enc(ref)}`),
    bankDispute: (ref, body) => post(`/api/bank/${enc(ref)}/dispute`, body),
    demoScam: (body) => opPost("/api/demo/scam", body),
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
    amlKbSearch: ({ q, k }) => get(`/api/aml/kb/search${query({ q, k })}`),
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
