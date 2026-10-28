/**
 * Zona AML: etichete în română, normalizări și derivări din evenimente.
 * Totul e tolerant: backend-ul real (versoml/zone_aml) și modul mock trimit forme ușor diferite,
 * iar un câmp lipsă nu trebuie să dărâme pagina.
 */
import { eventKey } from "../../api/sse";
import { num, slug } from "../../api/format";
import type {
  AgentEvent,
  Fact,
  Interrupt,
  LeadAction,
  NodeStatus,
  OsintFinding,
  OsintKind,
  PipelineNode,
  Signal,
} from "../../api/types";
import { normalizeStatus, reduceNodeStates } from "../../lib/pipeline";
import type { Tone } from "../../ui/kit";

// ------------------------------------------------------------------ texte mici

export function capitalize(s: string): string {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

/** Numerale în română: „o victimă”, „2 victime”, „20 de victime”. */
export function roCount(n: number, one: string, many: string): string {
  if (n === 1) return one;
  const r = Math.abs(n) % 100;
  const de = n !== 0 && (r === 0 || r >= 20);
  return `${num(n)}${de ? " de" : ""} ${many}`;
}

export function toNumber(v: unknown): number {
  const n = typeof v === "number" ? v : typeof v === "string" ? Number(v) : NaN;
  return Number.isFinite(n) ? n : 0;
}

export function tsOf(v: string | null | undefined): number | null {
  if (!v) return null;
  const t = Date.parse(v);
  return Number.isNaN(t) ? null : t;
}

/** „2.400”, „12,4 mii”, „1,2 mil.”: pentru nodurile grafului, unde locul e puțin. */
export function compactAmount(v: number): string {
  const a = Math.abs(v);
  if (a < 10_000) return num(v);
  if (a < 1_000_000) return `${num(v / 1000, 1)} mii`;
  return `${num(v / 1_000_000, 1)} mil.`;
}

// ------------------------------------------------------------------ conturi

/**
 * La fel ca `mask_iban` din backend: „RO49 XBNK •••• 7731”. Acceptă și IBAN-uri deja mascate,
 * cu „•” sau cu „*” (graful real trimite „RO61 BDEM **** **** **** 3598”), și le aduce la aceeași formă.
 */
export function maskAccount(v: string | null | undefined): string {
  if (!v) return "—";
  const s = String(v).trim();
  if (!s) return "—";
  if (/[•*]/.test(s)) {
    const m = s.match(/^([A-Z]{2}\d{2})\s*([A-Z0-9]{4})[\s•*]+([A-Z0-9]{4})$/i);
    return m ? `${m[1].toUpperCase()} ${m[2].toUpperCase()} •••• ${m[3].toUpperCase()}` : s.replace(/\*/g, "•");
  }
  const compact = s.replace(/\s+/g, "");
  if (/^[A-Z]{2}\d{2}[A-Z0-9]{9,30}$/i.test(compact)) {
    const up = compact.toUpperCase();
    return `${up.slice(0, 4)} ${up.slice(4, 8)} •••• ${up.slice(-4)}`;
  }
  return s;
}

export function looksLikeAccount(v: string | null | undefined): boolean {
  if (!v) return false;
  const s = v.replace(/\s+/g, "");
  return /^[A-Z]{2}\d{2}[A-Z0-9•*]{6,}$/i.test(s);
}

/** „RO49 XBNK •••• 7731” → „XBNK •• 7731”, ca să încapă într-un nod. */
export function compactAccount(label: string): string {
  const m = maskAccount(label).match(/^([A-Z]{2}\d{2})\s*([A-Z0-9]{4})[\s•]+([A-Z0-9]{4})$/i);
  return m ? `${m[2]} •• ${m[3]}` : label;
}

export function isVictimRef(v: string | null | undefined): boolean {
  return Boolean(v && /\bVCT-[0-9a-z]{2,}\b/i.test(v));
}

// ------------------------------------------------------------------ starea pistei

export type LeadStatusKey = "NOU" | "IN_ANALIZA" | "ASTEAPTA_ANALIST" | "INFORMATII" | "RTS_DEPUS" | "HOLD_EMIS" | "INCHIS" | "EROARE";
export type LeadGroup = "waiting" | "active" | "closed";

export interface LeadStatusInfo {
  key: LeadStatusKey | null;
  label: string;
  tone: Tone;
  live: boolean;
  group: LeadGroup;
}

const STATUS: Record<LeadStatusKey, Omit<LeadStatusInfo, "key">> = {
  NOU: { label: "Nouă", tone: "neutral", live: false, group: "active" },
  IN_ANALIZA: { label: "În analiză", tone: "neutral", live: true, group: "active" },
  ASTEAPTA_ANALIST: { label: "Te așteaptă", tone: "now", live: false, group: "waiting" },
  INFORMATII: { label: "Informații cerute", tone: "neutral", live: false, group: "active" },
  RTS_DEPUS: { label: "RTS depus", tone: "dark", live: false, group: "closed" },
  HOLD_EMIS: { label: "HOLD emis", tone: "dark", live: false, group: "closed" },
  INCHIS: { label: "Închisă", tone: "neutral", live: false, group: "closed" },
  EROARE: { label: "Eroare", tone: "danger", live: false, group: "active" },
};

/** Stările reale (enum) și cele în cuvinte ale modului mock („în lucru”, „așteaptă analistul”). */
const STATUS_ALIASES: Record<string, LeadStatusKey> = {
  nou: "NOU",
  noua: "NOU",
  new: "NOU",
  inanaliza: "IN_ANALIZA",
  inlucru: "IN_ANALIZA",
  running: "IN_ANALIZA",
  asteaptaanalist: "ASTEAPTA_ANALIST",
  asteaptaanalistul: "ASTEAPTA_ANALIST",
  asteaptadecizia: "ASTEAPTA_ANALIST",
  teasteapta: "ASTEAPTA_ANALIST",
  informatii: "INFORMATII",
  informatiicerute: "INFORMATII",
  rtsdepus: "RTS_DEPUS",
  holdemis: "HOLD_EMIS",
  inchis: "INCHIS",
  inchisa: "INCHIS",
  closed: "INCHIS",
  eroare: "EROARE",
  error: "EROARE",
};

export function leadStatus(raw: string | null | undefined): LeadStatusInfo | null {
  if (!raw || typeof raw !== "string") return null;
  const key = STATUS_ALIASES[slug(raw)];
  if (key) return { key, ...STATUS[key] };
  return { key: null, label: capitalize(raw.replace(/_/g, " ").toLowerCase()), tone: "neutral", live: false, group: "active" };
}

export const GROUP_ORDER: Record<LeadGroup, number> = { waiting: 0, active: 1, closed: 2 };

// ------------------------------------------------------------------ scorul M5

/**
 * Pragurile etichetelor M5, oglindă a `LABEL_HIGH` / `LABEL_MID` din versoml/ml/m5_mule.py (PARAM [U]).
 * Se folosesc doar când backend-ul nu trimite eticheta (`label`), de exemplu în lista de piste.
 */
export const M5_HIGH = 0.7;
export const M5_MID = 0.3;

export interface ScoreLevel {
  level: "high" | "mid" | "low";
  word: string;
  label: string;
}

const LEVELS: Record<ScoreLevel["level"], ScoreLevel> = {
  high: { level: "high", word: "ridicat", label: "cărăuș probabil" },
  mid: { level: "mid", word: "mediu", label: "de verificat" },
  low: { level: "low", word: "scăzut", label: "fără semne de cărăuș" },
};

export function scoreLevel(score: number | null | undefined, label?: string | null): ScoreLevel | null {
  if (label === "carausi_probabil") return LEVELS.high;
  if (label === "de_verificat") return LEVELS.mid;
  if (label === "normal") return LEVELS.low;
  if (score === null || score === undefined || Number.isNaN(score)) return null;
  return score >= M5_HIGH ? LEVELS.high : score >= M5_MID ? LEVELS.mid : LEVELS.low;
}

/** Oglindă a `FEATURE_LABELS_RO` (versoml/data/features.py) și a `explain_feature` (versoml/ml/m5_mule.py). */
const FEATURE_RO: Record<string, string> = {
  in_count: "număr de intrări",
  out_count: "număr de ieșiri",
  in_amount: "total intrări (lei)",
  out_amount: "total ieșiri (lei)",
  distinct_senders: "plătitori distincți",
  distinct_receivers: "beneficiari distincți",
  degree_total: "contrapartide distincte",
  pass_through_ratio: "raport ieșiri / intrări",
  median_dwell_hours: "timp median între intrare și următoarea ieșire (ore)",
  share_fwd_24h: "ponderea intrărilor urmate de o ieșire în 24 de ore",
  frac_out_crypto: "ponderea ieșirilor spre exchange cripto",
  frac_out_cash: "ponderea ieșirilor în numerar",
  frac_in_exchange: "ponderea intrărilor de la exchange",
  frac_in_cash: "ponderea depunerilor de numerar",
  victim_reports: "intrări raportate ca fraudă (dispută sau rechemare)",
  night_share: "activitate între 00:00 și 05:00",
  burstiness: "activitate în rafale",
  max_in_24h: "intrări maxime în 24 de ore",
  near_threshold_share: "intrări chiar sub un prag rotund",
  in_amount_cv: "variația sumelor primite",
  days_active: "zile active / fereastră",
  account_age_days: "vechimea contului (zile)",
  is_internal: "cont la Banca Demo",
  is_business: "cont de persoană juridică",
  pr_ego: "PageRank în subgraful-ego",
  ego_size: "mărimea subgrafului-ego",
  deg_in_graph: "vecini de intrare în graf",
  deg_out_graph: "vecini de ieșire în graf",
  n_hub_neighbors: "vecini hub (exchange, numerar, comercianți mari)",
  frac_in_external: "ponderea plătitorilor de la alte bănci",
  frac_out_to_hubs: "ponderea ieșirilor spre hub-uri",
};

const FEATURE_PREFIX: Array<[string, string]> = [
  ["in1_", "media vecinilor de intrare: "],
  ["out1_", "media vecinilor de ieșire: "],
  ["n2_", "media vecinilor la 2 pași: "],
];

/** Numele trăsăturii în cuvinte; un cod necunoscut rămâne cod (afișat mono). */
export function featureLabel(name: string): { text: string; code: boolean } {
  const n = String(name ?? "").trim();
  if (FEATURE_RO[n]) return { text: capitalize(FEATURE_RO[n]), code: false };
  for (const [prefix, label] of FEATURE_PREFIX) {
    const rest = n.slice(prefix.length);
    if (n.startsWith(prefix) && FEATURE_RO[rest]) return { text: capitalize(label + FEATURE_RO[rest]), code: false };
  }
  if (/^[a-z0-9_.]+$/i.test(n)) return { text: n, code: true };
  return { text: capitalize(n), code: false };
}

// ------------------------------------------------------------------ tipologii

/** Cheile din `detect_typologies` (versoml/ml/m5_mule.py); etichetele deja în română rămân neschimbate. */
const TYPOLOGY: Record<string, string> = {
  fan_in: "fan-in",
  fan_out: "fan-out",
  rapid_pass_through: "tranzit rapid",
  crypto_cash_out: "ieșire spre cripto sau numerar",
  structuring: "structurare",
  gather_scatter: "strânge și împrăștie",
  scatter_gather: "împrăștie și strânge",
  cycle: "ciclu",
};

export function typologyLabel(key: string | null | undefined): string {
  if (!key) return "—";
  const k = String(key).trim().toLowerCase().replace(/[\s-]+/g, "_");
  return TYPOLOGY[k] ?? String(key);
}

// ------------------------------------------------------------------ OSINT

export const SIGNAL_ORDER: Signal[] = ["rosu", "galben", "neutru", "verde"];

export const SIGNAL_INFO: Record<Signal, { label: string; hint: string }> = {
  rosu: { label: "Roșu", hint: "risc" },
  galben: { label: "Galben", hint: "de verificat" },
  neutru: { label: "Neutru", hint: "informativ" },
  verde: { label: "Verde", hint: "liniștitor" },
};

export function signalOf(f: Pick<OsintFinding, "signal">): Signal {
  return f.signal && SIGNAL_ORDER.includes(f.signal) ? f.signal : "neutru";
}

const TOOLS: Record<string, string> = {
  web_search: "Căutare web",
  news_search: "Presă și forumuri",
  anaf_company: "Registrul firmelor (ANAF)",
  sanctions_screen: "Liste de sancțiuni",
  rdap_domain: "Înregistrarea domeniului (RDAP)",
  ct_certificates: "Certificate TLS emise",
  dns_records: "Înregistrări DNS",
  lookalike_score: "Asemănare cu domeniul băncii",
  fetch_page: "Pagina web",
  page_similarity: "Asemănare cu paginile Banca Demo",
  openphish_check: "Feed de phishing (OpenPhish)",
  phone_intel: "Numărul de telefon",
  validate_iban: "Validare IBAN",
  wayback_first_seen: "Arhiva web",
  ip_geo: "Localizarea serverului",
  urlhaus_check: "Feed URLhaus",
  urlscan_search: "Scanări urlscan",
  virustotal_domain: "VirusTotal",
  safe_browsing_check: "Safe Browsing",
  "graph.link_cases": "Graful AML: cazuri legate",
  investigate: "Investigație OSINT",
};

export function toolLabel(tool: string | null | undefined): string | null {
  if (!tool) return null;
  return TOOLS[tool] ?? null;
}

export function modeInfo(mode: string | null | undefined): { label: string; title: string } | null {
  switch (mode) {
    case "live":
      return { label: "live", title: "Interogare live a sursei" };
    case "fixture":
      return { label: "înregistrare", title: "Răspuns înregistrat dinainte (fixture), fără rețea" };
    case "cache":
      return { label: "din cache", title: "Răspuns păstrat dintr-o interogare recentă" };
    case "offline":
      return { label: "offline", title: "Sursa nu a putut fi contactată" };
    default:
      return null;
  }
}

export const OSINT_KINDS: Array<{ id: OsintKind; label: string }> = [
  { id: "auto", label: "Auto" },
  { id: "domain", label: "Domeniu" },
  { id: "url", label: "URL" },
  { id: "phone", label: "Telefon" },
  { id: "cui", label: "CUI" },
  { id: "iban", label: "IBAN" },
  { id: "company", label: "Firmă" },
];

export function isOsintKind(v: unknown): v is OsintKind {
  return typeof v === "string" && OSINT_KINDS.some((k) => k.id === v);
}

/** Ghicitul tipului, doar pentru mesajul de încărcare; serverul își face propria detecție. */
export function detectOsintKind(target: string): Exclude<OsintKind, "auto"> | null {
  const s = target.trim();
  if (!s) return null;
  if (/^https?:\/\//i.test(s)) return "url";
  const flat = s.replace(/\s+/g, "");
  if (/^[A-Z]{2}\d{2}[A-Z0-9•]{8,}$/i.test(flat)) return "iban";
  const digits = s.replace(/[\s.()-]/g, "");
  if (/^(\+?40|0)7\d{8}$/.test(digits) || /^\+\d{9,14}$/.test(digits)) return "phone";
  if (/^(RO)?\d{2,10}$/i.test(digits) || /^cui\b/i.test(s)) return "cui";
  if (/^[a-z0-9-]+(\.[a-z0-9-]+)+$/i.test(s)) return "domain";
  return "company";
}

/** Câte tool-uri rulează serverul pentru fiecare tip (planul fix din versoml/osint/investigate.py, fără cheile opționale). */
const SOURCES_BY_KIND: Record<Exclude<OsintKind, "auto">, number> = { domain: 9, url: 9, phone: 1, cui: 1, iban: 1, company: 2 };

export function osintLoadingLabel(target: string, kind: OsintKind): string {
  const k = kind === "auto" ? detectOsintKind(target) : kind;
  const n = k ? SOURCES_BY_KIND[k] : null;
  if (!n) return "Interoghez sursele publice…";
  return n === 1 ? "Interoghez sursa publică potrivită…" : `Interoghez ${n} surse publice în paralel…`;
}

/** Datele victimelor și datele personale nu pleacă spre surse publice. */
export function privacyGuard(target: string): string | null {
  const s = target.trim();
  if (isVictimRef(s)) return "VCT-… e pseudonimul unei victime. Datele victimelor nu se caută în surse publice.";
  if (/(^|\D)[1-8]\d{12}(\D|$)/.test(s.replace(/\s+/g, ""))) return "Arată ca un CNP. Datele personale nu se trimit spre surse publice.";
  return null;
}

// ------------------------------------------------------------------ deciziile analistului

export interface ActionInfo {
  label: string;
  confirm: string;
  consequence: string;
  placeholder: string;
  danger?: boolean;
}

export const ACTION_ORDER: LeadAction[] = ["file_rts", "close", "request_info", "hold_client"];

export const ACTIONS: Record<LeadAction, ActionInfo> = {
  file_rts: {
    label: "Depune RTS",
    confirm: "Confirmă depunerea",
    consequence:
      "Ciorna se marchează pentru depunere la ONPCSB (AML-01). În demo depunerea e simulată: raportul îl trimite un om, pe canalele ONPCSB, nu agentul.",
    placeholder: "De ce depui raportul (de exemplu: tranzit rapid spre crypto, 2 victime)",
  },
  close: {
    label: "Închide pista",
    confirm: "Confirmă închiderea",
    consequence: "Pista se închide fără raport. Nota ta rămâne în jurnalul de audit ca motivare.",
    placeholder: "De ce închizi pista",
  },
  request_info: {
    label: "Cere informații",
    confirm: "Confirmă cererea",
    consequence: "Pista rămâne deschisă, cu starea „Informații cerute”. Nimic nu ajunge în zona client.",
    placeholder: "Ce informații ceri și de la cine",
  },
  hold_client: {
    label: "Emite HOLD",
    confirm: "Confirmă HOLD",
    consequence: "Trimite spre zona client doar un semnal da/nu, fără detalii. Folosește-l doar dacă suspectezi chiar clientul.",
    placeholder: "De ce suspectezi chiar clientul",
    danger: true,
  },
};

export function isLeadAction(v: unknown): v is LeadAction {
  return typeof v === "string" && (ACTION_ORDER as string[]).includes(v);
}

/** Butonul principal urmează recomandarea regulilor; HOLD nu e niciodată principal. */
export function recommendedAction(rec: string | null | undefined): LeadAction | null {
  switch (rec) {
    case "RTS_PROPUS":
      return "file_rts";
    case "INCHIDE":
      return "close";
    case "INFORMATII_SUPLIMENTARE":
      return "request_info";
    default:
      return null;
  }
}

export const ACTION_STATUS: Record<LeadAction, LeadStatusKey> = {
  file_rts: "RTS_DEPUS",
  close: "INCHIS",
  request_info: "INFORMATII",
  hold_client: "HOLD_EMIS",
};

// ------------------------------------------------------------------ evenimente

/** Uniune fără dubluri (SSE + `timeline` din polling), în ordinea rulărilor și apoi a `seq`. */
export function mergeEvents(...lists: Array<AgentEvent[] | null | undefined>): AgentEvent[] {
  const map = new Map<string, AgentEvent>();
  for (const list of lists) {
    if (!Array.isArray(list)) continue;
    for (const e of list) {
      if (!e || typeof e.type !== "string") continue;
      const k = eventKey(e);
      if (!map.has(k)) map.set(k, e);
    }
  }
  const all = Array.from(map.values());
  const start = new Map<string, number>();
  for (const e of all) {
    const t = tsOf(e.ts) ?? 0;
    const s = start.get(e.run_id);
    if (s === undefined || t < s) start.set(e.run_id, t);
  }
  return all.sort((a, b) => {
    const r = (start.get(a.run_id) ?? 0) - (start.get(b.run_id) ?? 0);
    if (r) return r;
    if (a.run_id !== b.run_id) return a.run_id < b.run_id ? -1 : 1;
    const sa = a.seq ?? 0;
    const sb = b.seq ?? 0;
    if (sa > 0 && sb > 0) return sa - sb;
    return (tsOf(a.ts) ?? 0) - (tsOf(b.ts) ?? 0);
  });
}

/** Evenimentele ultimei rulări (de la ultimul RUN_STARTED). */
export function lastRun(events: AgentEvent[]): AgentEvent[] {
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i].type === "RUN_STARTED") return events.slice(i);
  }
  return events;
}

export function latestRunId(events: AgentEvent[] | null | undefined): string | null {
  if (!events?.length) return null;
  for (let i = events.length - 1; i >= 0; i--) if (events[i].type === "RUN_STARTED") return events[i].run_id;
  return events[events.length - 1].run_id ?? null;
}

function dataString(e: AgentEvent, key: string): string | undefined {
  const v = e.data?.[key];
  return typeof v === "string" ? v : undefined;
}

/** Rezerva pentru modul mock, unde detaliul pistei nu are `interrupt`. */
export function deriveInterrupt(events: AgentEvent[]): Interrupt | null {
  let pending: Interrupt | null = null;
  for (const e of lastRun(events)) {
    if (e.type === "CUSTOM" && e.name === "interrupt") {
      if (e.data?.pending === false) {
        pending = null;
        continue;
      }
      const options = Array.isArray(e.data?.options) ? (e.data?.options as unknown[]).filter((x): x is string => typeof x === "string") : undefined;
      pending = { pending: true, prompt: e.message ?? undefined, options, recommendation: dataString(e, "recommendation") ?? null };
    } else if (
      (e.type === "CUSTOM" && e.name === "decision") ||
      e.type === "RUN_FINISHED" ||
      e.type === "RUN_ERROR" ||
      (e.type === "STEP_FINISHED" && e.step === "analist")
    ) {
      pending = null;
    }
  }
  return pending;
}

/** Starea pistei citită din evenimente, când detaliul nu o are. */
export function deriveStatus(events: AgentEvent[]): LeadStatusKey | null {
  const run = lastRun(events);
  let status: LeadStatusKey | null = null;
  for (const e of run) {
    if (e.type === "RUN_STARTED") status = "IN_ANALIZA";
    else if (e.type === "CUSTOM" && e.name === "interrupt" && e.data?.pending !== false) status = "ASTEAPTA_ANALIST";
    else if (e.type === "CUSTOM" && e.name === "decision") {
      const a = e.data?.action;
      if (isLeadAction(a)) status = ACTION_STATUS[a];
    } else if (e.type === "RUN_ERROR") status = "EROARE";
  }
  return status;
}

export interface DecisionInfo {
  action: LeadAction | null;
  note: string | null;
  analyst: string | null;
  at: string | null;
  message: string | null;
}

export function lastDecision(events: AgentEvent[], interrupt: Interrupt | null | undefined): DecisionInfo | null {
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i];
    if (e.type === "CUSTOM" && e.name === "decision") {
      const a = e.data?.action;
      return {
        action: isLeadAction(a) ? a : null,
        note: dataString(e, "note") ?? null,
        analyst: dataString(e, "analyst") ?? null,
        at: e.ts ?? null,
        message: e.message ?? null,
      };
    }
  }
  const answer = interrupt?.answer as Record<string, unknown> | null | undefined;
  if (answer && typeof answer === "object") {
    const a = answer.action;
    return {
      action: isLeadAction(a) ? a : null,
      note: typeof answer.note === "string" ? answer.note : null,
      analyst: typeof answer.analyst === "string" ? answer.analyst : typeof answer.approver === "string" ? answer.approver : null,
      at: null,
      message: null,
    };
  }
  return null;
}

export function lastRunError(events: AgentEvent[]): string | null {
  const run = lastRun(events);
  for (let i = run.length - 1; i >= 0; i--) if (run[i].type === "RUN_ERROR") return run[i].message ?? null;
  return null;
}

// ------------------------------------------------------------------ probe

export interface FactRow {
  fact_id: string;
  kind?: string;
  summary?: string;
  sha256?: string;
  source_tool?: string;
  retrieved_at?: string;
}

const FACT_KIND: Record<string, string> = {
  "diode.dispute_facts": "Fapte primite prin diodă",
  "ml.m5_scores": "Graful și scorul M5",
  "rules.aml": "Regulile AML",
  "aml.innocent_hypotheses": "Ipoteze nevinovate",
  "aml.rts_draft": "Ciorna RTS",
  "human.aml_decision": "Decizia analistului",
};

export function factKindLabel(kind: string | null | undefined): string | null {
  if (!kind) return null;
  if (FACT_KIND[kind]) return FACT_KIND[kind];
  if (kind.startsWith("osint.")) return `OSINT · ${toolLabel(kind.slice(6)) ?? kind.slice(6)}`;
  return null;
}

/** Probele: întâi registrul din detaliu, apoi faptele anunțate în evenimente, apoi ID-urile din OSINT. */
export function collectFacts(facts: Fact[] | null | undefined, events: AgentEvent[], osint: OsintFinding[]): FactRow[] {
  const out = new Map<string, FactRow>();
  for (const f of facts ?? []) {
    if (!f || typeof f.fact_id !== "string") continue;
    out.set(f.fact_id, { fact_id: f.fact_id, kind: f.kind, summary: f.summary, sha256: f.sha256, source_tool: f.source_tool, retrieved_at: f.retrieved_at });
  }
  for (const e of events) {
    if (e.type !== "CUSTOM" || e.name !== "fact") continue;
    const id = dataString(e, "fact_id");
    if (!id || out.has(id)) continue;
    const msg = (e.message ?? "").replace(new RegExp(`^${id.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*·\\s*`), "");
    out.set(id, { fact_id: id, kind: dataString(e, "kind"), summary: msg || undefined, sha256: dataString(e, "sha256"), source_tool: dataString(e, "source_tool"), retrieved_at: e.ts });
  }
  for (const f of osint) {
    if (!f?.fact_id || out.has(f.fact_id)) continue;
    out.set(f.fact_id, { fact_id: f.fact_id, kind: `osint.${f.tool}`, summary: f.summary, source_tool: f.tool });
  }
  return Array.from(out.values()).sort((a, b) => {
    const ta = tsOf(a.retrieved_at);
    const tb = tsOf(b.retrieved_at);
    if (ta !== null && tb !== null && ta !== tb) return ta - tb;
    return a.fact_id.localeCompare(b.fact_id, "ro", { numeric: true });
  });
}

// ------------------------------------------------------------------ pașii agenților

/** Graful Investigatorului (PIPELINE_NODES din versoml/zone_aml/agents.py): rezerva când detaliul nu are `pipeline`. */
export const AML_STEPS: PipelineNode[] = [
  { id: "receptor_fapte", label: "Receptor fapte", agent: "Investigatorul/Receptor fapte", hint: "Citește faptele venite prin diodă" },
  { id: "graf_ml", label: "Graf + ML", agent: "Investigatorul/Graf + ML", hint: "Graful banilor, scorul M5, tipologii" },
  { id: "osint", label: "OSINT", agent: "Investigatorul/OSINT", hint: "Surse publice despre beneficiar" },
  { id: "nevinovatie", label: "Avocatul nevinovăției", agent: "Investigatorul/Avocatul nevinovăției", hint: "Explicații nevinovate, înainte de orice raport" },
  { id: "reguli_aml", label: "Reguli AML", agent: "Motorul de reguli AML", hint: "Obligația de raportare și ceasurile" },
  { id: "redactor_rts", label: "Ciornă RTS", agent: "Investigatorul/Redactor RTS", hint: "Fiecare frază cu sursă" },
  { id: "analist", label: "Analist (om)", agent: "Analistul AML (om)", hint: "Decizia ta" },
  { id: "sigiliu", label: "Sigiliu", agent: "Registrul de probe AML", hint: "Dosarul AML sigilat" },
];

const STEP_ALIAS: Record<string, string> = {
  avocat_nevinovatie: "nevinovatie",
  avocatul_nevinovatiei: "nevinovatie",
  graf: "graf_ml",
  rts: "redactor_rts",
};

const RANK: Record<NodeStatus, number> = { idle: 0, running: 1, waiting: 2, blocked: 3, error: 3, skipped: 3, done: 3 };

export interface StepView {
  id: string;
  label: string;
  status: NodeStatus;
  summary?: string;
  hint?: string;
  model?: string | null;
  startedAt: number | null;
  finishedAt: number | null;
}

/**
 * Starea fiecărui pas: cea salvată de backend (`pipeline.nodes`) combinată cu cea citită din evenimente;
 * câștigă starea mai avansată. Pașii rămași „în așteptare” după încheierea rulării devin „nu e cazul”.
 */
export function resolveSteps(nodes: PipelineNode[] | null | undefined, events: AgentEvent[]): StepView[] {
  const base = (Array.isArray(nodes) && nodes.length ? nodes : AML_STEPS).filter((n) => n && typeof n.id === "string");
  const agentOf = new Map(AML_STEPS.map((s) => [s.id, s.agent]));
  const evs = events.map((e) => (e.step && STEP_ALIAS[e.step] ? { ...e, step: STEP_ALIAS[e.step] } : e));
  const live = reduceNodeStates(
    base.map((n) => ({ id: n.id, label: n.label ?? n.id, agent: n.agent ?? agentOf.get(n.id), status: n.status })),
    evs,
  );
  const run = lastRun(evs);
  const finished = run.some((e) => e.type === "RUN_FINISHED");
  const started = new Map<string, number>();
  const ended = new Map<string, number>();
  const lastMsg = new Map<string, string>();
  for (const e of run) {
    if (!e.step) continue;
    const t = tsOf(e.ts);
    if (t !== null && (e.type === "STEP_STARTED" || e.type === "TOOL_CALL_START") && !started.has(e.step)) started.set(e.step, t);
    if (t !== null && e.type === "STEP_FINISHED") ended.set(e.step, t);
    if (e.type === "STEP_FINISHED" && e.message) lastMsg.set(e.step, e.message);
  }
  return base.map((n) => {
    const persisted = normalizeStatus(n.status);
    const fromEvents = live[n.id]?.status ?? "idle";
    let status = RANK[fromEvents] > RANK[persisted] ? fromEvents : persisted;
    if (status === "idle" && finished) status = "skipped";
    const liveMsg = live[n.id]?.live;
    const summary =
      status === "running" ? liveMsg ?? n.summary : status === "idle" ? undefined : n.summary ?? lastMsg.get(n.id) ?? liveMsg;
    return {
      id: n.id,
      label: n.label ?? n.id,
      status,
      summary: summary || undefined,
      hint: n.hint ?? AML_STEPS.find((s) => s.id === n.id)?.hint,
      model: n.model ?? null,
      startedAt: tsOf(n.started_at) ?? started.get(n.id) ?? null,
      finishedAt: tsOf(n.finished_at) ?? ended.get(n.id) ?? null,
    };
  });
}

// ------------------------------------------------------------------ ciorna RTS

export const RTS_FIELD_LABELS: Record<string, string> = {
  raportor: "Entitate raportoare",
  referinta_interna: "Referință internă",
  conturi: "Conturi",
  tipologii: "Tipologii",
  rezumat: "Rezumatul suspiciunii",
  indicatori: "Indicatori",
  masuri: "Măsuri propuse",
  formular: "Formular",
};

export function humanizeKey(key: string): string {
  if (RTS_FIELD_LABELS[key]) return RTS_FIELD_LABELS[key];
  return capitalize(key.replace(/[_]+/g, " ").trim());
}
