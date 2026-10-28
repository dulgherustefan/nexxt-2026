/**
 * „Backend-ul" din browser pentru modul mock. Starea stă în localStorage, ca filele să o împartă:
 * consola de contestații, consola AML (?zone=aml) și Banca Demo văd aceleași cazuri, iar o rulare
 * pornită într-o filă continuă în alta (fila-lider avansează rulările).
 */
import type { AgentEvent, BankState, RuleParams, WallState } from "../api/types";
import { seedAml, advanceAml, ingestReferral, type AmlDb } from "./aml";
import { addBusinessDays, endOfNextBusinessDay, isoRo } from "./calendar";
import { advance, newCaseDetail, prerun, type EngineHooks, type MockCase } from "./engine";
import { ATTACKS, PARAMS, WALL_LAYERS, seedDenials } from "./fixtures";
import { sha256 } from "./sha256";
import { storyFor, type Story, type StoryCtx } from "./stories";

const KEY = "versoml.mock.db.v4";
const REV = "versoml.mock.rev.v4";
const LEADER = "versoml.mock.leader.v4";
const H = 3600_000;

export interface MockDb {
  v: 4;
  rev: number;
  seq: number;
  caseCounter: number;
  cases: Record<string, MockCase>;
  order: string[];
  bank: Record<string, BankState & { linked: Record<string, string> }>;
  params: RuleParams;
  wall: WallState;
  aml: AmlDb;
}

// ------------------------------------------------------------------ persistență

let memory: MockDb | null = null;
let localRev = -1;
const tabId = Math.random().toString(36).slice(2);

function storageOk(): boolean {
  try {
    const k = "versoml.mock.probe";
    localStorage.setItem(k, "1");
    localStorage.removeItem(k);
    return true;
  } catch {
    return false;
  }
}
const persistent = typeof window !== "undefined" && storageOk();

function readRev(): number {
  if (!persistent) return localRev;
  try {
    return Number(localStorage.getItem(REV) ?? "-1");
  } catch {
    return localRev;
  }
}

function load(): MockDb {
  if (persistent) {
    const rev = readRev();
    if (memory && rev === localRev) return memory;
    try {
      const raw = localStorage.getItem(KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as MockDb;
        if (parsed && parsed.v === 4) {
          memory = parsed;
          localRev = parsed.rev;
          return memory;
        }
      }
    } catch {
      /* stare coruptă: o regenerăm */
    }
  }
  if (!memory) {
    memory = seed(Date.now());
    save(memory);
  }
  return memory;
}

function save(db: MockDb) {
  db.rev += 1;
  localRev = db.rev;
  memory = db;
  if (!persistent) return;
  try {
    localStorage.setItem(KEY, JSON.stringify(db));
    localStorage.setItem(REV, String(db.rev));
  } catch {
    /* plin sau blocat: rămânem în memorie */
  }
}

type Listener = () => void;
const listeners = new Set<Listener>();
let lastNotifiedRev = -1;

function notify() {
  if (lastNotifiedRev === localRev) return;
  lastNotifiedRev = localRev;
  for (const l of Array.from(listeners)) l();
}

/** Citire consistentă (preia modificările făcute de alte file). */
export function read(): MockDb {
  return load();
}

/** Citire-modificare-scriere, sincronă, ca să nu pierdem scrierile altor file. */
export function transact<T>(fn: (db: MockDb, hooks: EngineHooks) => T): T {
  const db = load();
  const out = fn(db, hooksFor(db));
  save(db);
  notify();
  return out;
}

export function subscribe(l: Listener): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}

if (typeof window !== "undefined") {
  window.addEventListener("storage", (ev) => {
    if (ev.key === REV) {
      load();
      notify();
    }
  });
}

export function resetMock() {
  memory = seed(Date.now());
  save(memory);
  notify();
}

// ------------------------------------------------------------------ cârligele dintre zone și Banca Demo

function hooksFor(db: MockDb): EngineHooks {
  const nextSeq = () => ++db.seq;
  return {
    nextSeq,
    onDiode: (c: MockCase, story: Story, at: number) => {
      if (!story.beneficiary) return;
      ingestReferral(db.aml, { caseId: c.caseId, victimRef: c.ctx.victimRef, amount: c.ctx.amount, executedAt: c.ctx.executedAt, at, scenario: story.scenario }, nextSeq);
    },
    onRefund: (c: MockCase, at: number) => {
      const acct = db.bank[c.customerRef];
      if (!acct) return;
      const txId = Object.keys(acct.linked).find((tx) => acct.linked[tx] === c.caseId);
      if (!txId) return;
      const tx = acct.transactions.find((t) => t.id === txId);
      if (tx) {
        tx.status = "rambursată";
        tx.disputable = false;
      }
      acct.balance = Math.round((acct.balance + c.ctx.amount) * 100) / 100;
      acct.transactions.unshift({
        id: `RF-${c.caseId}`,
        ts: isoRo(at),
        description: `Rambursare contestație ${c.caseId}`,
        amount: c.ctx.amount,
        direction: "in",
        status: "executată",
        disputable: false,
      });
      acct.notifications.unshift({ ts: isoRo(at), text: `Ți-am returnat ${formatLei(c.ctx.amount)}`, kind: "refund" });
    },
  };
}

function formatLei(v: number): string {
  return `${new Intl.NumberFormat("ro-RO", { maximumFractionDigits: 2 }).format(v)} lei`;
}

// ------------------------------------------------------------------ cazuri

export function victimRefFor(caseId: string): string {
  return `VCT-${sha256(caseId).slice(0, 4)}`;
}

export function makeCtx(caseId: string, receivedAt: number, amount: number, alias: string, executedAgoMin = 6): StoryCtx {
  const received = new Date(receivedAt);
  return {
    caseId,
    receivedAt,
    executedAt: receivedAt - executedAgoMin * 60_000,
    amount,
    alias,
    t1: endOfNextBusinessDay(received),
    cmp15: addBusinessDays(received, 15),
    cmp35: addBusinessDays(received, 35),
    victimRef: victimRefFor(caseId),
    txId: `TX-${sha256(`tx-${caseId}`).slice(0, 8).toUpperCase()}`,
  };
}

export function createMockCase(db: MockDb, args: { scenario: string; customerRef: string; amount?: number; alias?: string; receivedAt?: number; txId?: string; complaintText?: string }): MockCase {
  db.caseCounter += 1;
  const caseId = `CT-2026-${String(db.caseCounter).padStart(6, "0")}`;
  const receivedAt = args.receivedAt ?? Date.now();
  const amount = args.amount ?? defaultAmount(args.scenario);
  const alias = args.alias ?? aliasFor(args.customerRef);
  const ctx = makeCtx(caseId, receivedAt, amount, alias);
  if (args.txId) ctx.txId = args.txId;
  const story = storyFor(args.scenario, ctx);
  const c: MockCase = {
    caseId,
    customerRef: args.customerRef,
    scenario: args.scenario,
    ctx,
    detail: newCaseDetail(caseId, args.scenario, ctx, story),
    events: [],
    keyToFact: {},
    run: null,
    seal: null,
    createdAt: receivedAt,
  };
  if (args.complaintText && c.detail.complaint) c.detail.complaint.text = args.complaintText;
  db.cases[caseId] = c;
  db.order.unshift(caseId);
  return c;
}

export function startRun(db: MockDb, caseId: string, now = Date.now()): string {
  const c = db.cases[caseId];
  const runId = `run-${caseId}-${Math.floor(now / 1000).toString(36)}`;
  c.events = [];
  c.keyToFact = {};
  c.seal = null;
  const story = storyFor(c.scenario, c.ctx);
  const fresh = newCaseDetail(caseId, c.scenario, c.ctx, story);
  fresh.complaint = c.detail.complaint ?? fresh.complaint;
  c.detail = fresh;
  c.run = { runId, startedAt: now, cursorA: 0, cursorB1: 0, cursorB2: 0, approval: null, done: false };
  return runId;
}

function defaultAmount(scenario: string): number {
  switch (scenario) {
    case "demo_t1":
      return 3200;
    case "inel_carausi":
      return 1850;
    case "card_ecom_fara_3ds":
      return 512.4;
    case "card_visa_secure":
      return 1249.9;
    case "vishing_securitate":
      return 8000;
    case "cont_sigur":
      return 15000;
    case "sim_swap":
      return 4750;
    case "frauda_client":
      return 2310;
    case "reclamatie_tardiva":
      return 640;
    case "plata_dubla":
      return 389;
    case "injectie_document":
      return 2900;
    default:
      return 1480;
  }
}

function aliasFor(ref: string): string {
  if (ref === "CUST-DEMO-01") return "Client 0042";
  if (ref === "CUST-DEMO-02") return "Client 0117";
  return `Client ${String(parseInt(sha256(ref).slice(0, 4), 16) % 1000).padStart(4, "0")}`;
}

// ------------------------------------------------------------------ starea inițială

function seed(now: number): MockDb {
  const db: MockDb = {
    v: 4,
    rev: 0,
    seq: 0,
    caseCounter: 114,
    cases: {},
    order: [],
    bank: seedBank(now),
    params: { ...PARAMS },
    wall: {
      layers: WALL_LAYERS.map((l) => ({ ...l })),
      denials: seedDenials(now),
      blocks: [{ at: isoRo(now - 2.6 * H), case_id: "CT-2026-000116", reasons: ["termen interzis în ciorna scrisorii"], terms: ["investigație"] }],
      noninterference: { runs: 200, leaks: 0, at: isoRo(now - 3 * H) },
    },
    aml: seedAml(now),
  };
  const hooks = hooksFor(db);
  const seeds: Array<{ scenario: string; ref: string; agoH: number; approval?: { action: "approve" | "reject"; approver: string } | null }> = [
    { scenario: "card_ecom_fara_3ds", ref: "CUST-0198", agoH: 26 },
    { scenario: "injectie_document", ref: "CUST-0750", agoH: 3, approval: null },
    { scenario: "plata_dubla", ref: "CUST-0561", agoH: 30 },
    { scenario: "card_visa_secure", ref: "CUST-0317", agoH: 20 },
    { scenario: "vishing_securitate", ref: "CUST-0105", agoH: 5 },
    { scenario: "sim_swap", ref: "CUST-0233", agoH: 8, approval: { action: "approve", approver: "OPERATOR-03" } },
    { scenario: "frauda_client", ref: "CUST-0412", agoH: 2, approval: null },
    { scenario: "reclamatie_tardiva", ref: "CUST-0089", agoH: 0.8, approval: null },
  ];
  for (const s of seeds) {
    const receivedAt = now - s.agoH * H;
    const c = createMockCase(db, { scenario: s.scenario, customerRef: s.ref, receivedAt, alias: `Client ${s.ref.slice(5)}` });
    prerun(c, receivedAt + 20_000, hooks, s.approval ?? null, 210);
  }
  return db;
}

function seedBank(now: number): MockDb["bank"] {
  const tx = (id: string, agoH: number, description: string, amount: number, direction: "in" | "out") => ({
    id,
    ts: isoRo(now - agoH * H),
    description,
    amount,
    direction,
    status: "executată",
    disputable: false,
  });
  return {
    "CUST-DEMO-01": {
      customer_alias: "Client 0042",
      balance: 12480.55,
      iban_masked: "RO49 BDEM •••• •••• •••• 0042",
      transactions: [
        tx("TX-D1-006", 5, "Supermarket Demo", -184.3, "out"),
        tx("TX-D1-005", 27, "Farmacia Demo", -62.15, "out"),
        tx("TX-D1-004", 50, "Factură energie (Furnizor Demo)", -231.4, "out"),
        tx("TX-D1-003", 74, "Abonament transport Demo", -80, "out"),
        tx("TX-D1-002", 120, "Restaurant Demo", -146, "out"),
        tx("TX-D1-001", 170, "Salariu (Angajator Demo SRL)", 6200, "in"),
      ],
      notifications: [],
      linked: {},
    },
    "CUST-DEMO-02": {
      customer_alias: "Client 0117",
      balance: 7930.1,
      iban_masked: "RO49 BDEM •••• •••• •••• 0117",
      transactions: [
        tx("TX-D2-003", 9, "Benzinărie Demo", -275.8, "out"),
        tx("TX-D2-002", 46, "Librăria Demo", -94.5, "out"),
        tx("TX-D2-001", 150, "Salariu (Angajator Demo SRL)", 5400, "in"),
      ],
      notifications: [],
      linked: {},
    },
  };
}

export { ATTACKS };

// ------------------------------------------------------------------ fila-lider avansează rulările

function hasActiveRuns(db: MockDb): boolean {
  if (Object.values(db.cases).some((c) => c.run && !c.run.done)) return true;
  return Object.values(db.aml.leads).some((l) => l.run && !l.run.done);
}

function amLeader(now: number): boolean {
  if (!persistent) return true;
  try {
    const raw = localStorage.getItem(LEADER);
    const cur = raw ? (JSON.parse(raw) as { id: string; ts: number }) : null;
    if (!cur || cur.id === tabId || now - cur.ts > 1500) {
      localStorage.setItem(LEADER, JSON.stringify({ id: tabId, ts: now }));
      return true;
    }
    return false;
  } catch {
    return true;
  }
}

let driver: ReturnType<typeof setInterval> | null = null;

export function startDriver() {
  if (driver) return;
  driver = setInterval(() => {
    const now = Date.now();
    const db = load();
    if (!hasActiveRuns(db)) return;
    if (!amLeader(now)) return;
    let changed = false;
    const hooks = hooksFor(db);
    for (const c of Object.values(db.cases)) {
      if (c.run && !c.run.done && advance(c, now, hooks)) changed = true;
    }
    for (const id of Object.keys(db.aml.leads)) {
      if (advanceAml(db.aml, id, now, hooks.nextSeq)) changed = true;
    }
    if (changed) {
      save(db);
      notify();
    }
  }, 200);
}

// ------------------------------------------------------------------ fluxurile de evenimente

export function caseEventSource(caseId: string) {
  return (onEvent: (e: AgentEvent) => void) => {
    let lastSeq = 0;
    const flush = () => {
      const c = read().cases[caseId];
      if (!c) return;
      for (const e of c.events) {
        if ((e.seq ?? 0) > lastSeq) {
          lastSeq = e.seq ?? lastSeq;
          onEvent(e);
        }
      }
    };
    flush();
    const unsub = subscribe(flush);
    return unsub;
  };
}

/** Activitatea agenților din toate cazurile (ca /api/ticker): ultimele 30, apoi ce apare nou. */
export function tickerSource() {
  return (onEvent: (e: AgentEvent) => void) => {
    const seen = new Set<string>();
    let first = true;
    const flush = () => {
      const all = Object.values(read().cases).flatMap((c) => c.events);
      const fresh = all.filter((e) => !seen.has(`${e.run_id}:${e.seq}`));
      fresh.forEach((e) => seen.add(`${e.run_id}:${e.seq}`));
      (first ? fresh.slice(-30) : fresh).forEach(onEvent);
      first = false;
    };
    flush();
    return subscribe(flush);
  };
}

export function leadEventSource(leadId: string) {
  return (onEvent: (e: AgentEvent) => void) => {
    let lastSeq = 0;
    const flush = () => {
      const l = read().aml.leads[leadId];
      if (!l) return;
      for (const e of l.events) {
        if ((e.seq ?? 0) > lastSeq) {
          lastSeq = e.seq ?? lastSeq;
          onEvent(e);
        }
      }
    };
    flush();
    return subscribe(flush);
  };
}

export const MOCK_NOW = () => Date.now();
