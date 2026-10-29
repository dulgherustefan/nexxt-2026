import type { CaseStatus, Channel, DisputeType, Money, Question, Scenario, Verdict } from "./types";

/** Bucharest time, whatever time zone the demo laptop is set to. */
export const TZ = "Europe/Bucharest";
const LOCALE = "en-GB";

const nf0 = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 });

export function toMoney(v: number | Money | null | undefined, currency = "RON"): Money | null {
  if (v === null || v === undefined) return null;
  if (typeof v === "number") return { value: v, currency };
  if (typeof v === "object" && typeof v.value === "number") return { value: v.value, currency: v.currency ?? currency };
  return null;
}

/** 3200 → "RON 3,200.00"; with `{ decimals: 0 }` → "RON 3,200". The code goes first, as in EU style. */
/** False while the payment hasn't been loaded yet (the API sends a zero amount until then). */
export function hasAmount(v: number | Money | null | undefined): boolean {
  const m = toMoney(v);
  return Boolean(m && m.value > 0);
}

export function money(v: number | Money | null | undefined, opts: { decimals?: "auto" | 0 | 2 } = {}): string {
  const m = toMoney(v);
  if (!m) return "—";
  const decimals = opts.decimals ?? 2;
  const digits = decimals === "auto" ? (Math.round(m.value * 100) % 100 !== 0 ? 2 : 0) : decimals;
  const n = new Intl.NumberFormat(LOCALE, { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(m.value);
  return `${(m.currency ?? "RON").toUpperCase()} ${n}`;
}

export function num(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return digits === 0 ? nf0.format(v) : new Intl.NumberFormat(LOCALE, { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(v);
}

export function pct(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const x = v <= 1 ? v * 100 : v;
  return `${num(x, digits)}%`;
}

export function score(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return num(v, 2);
}

function d(v: string | number | Date): Date {
  return v instanceof Date ? v : new Date(v);
}

export function isValidDate(v: unknown): boolean {
  if (v === null || v === undefined || v === "") return false;
  const t = d(v as string).getTime();
  return !Number.isNaN(t);
}

/** "29 Oct, 23:59" */
export function dateTime(v: string | number | Date | null | undefined): string {
  if (!v || !isValidDate(v)) return "—";
  return new Intl.DateTimeFormat(LOCALE, { timeZone: TZ, day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false }).format(d(v));
}

/** "29 October 2026" */
export function dateLong(v: string | number | Date | null | undefined): string {
  if (!v || !isValidDate(v)) return "—";
  return new Intl.DateTimeFormat(LOCALE, { timeZone: TZ, day: "numeric", month: "long", year: "numeric" }).format(d(v));
}

/** "Thursday 29 October 2026, 23:59" for tooltips next to a countdown. */
export function dateFull(v: string | number | Date | null | undefined): string {
  if (!v || !isValidDate(v)) return "—";
  return new Intl.DateTimeFormat(LOCALE, {
    timeZone: TZ, weekday: "long", day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(d(v));
}

/** "14:02:11" */
export function clock(v: string | number | Date | null | undefined, seconds = true): string {
  if (!v || !isValidDate(v)) return "—";
  return new Intl.DateTimeFormat(LOCALE, {
    timeZone: TZ,
    hour: "2-digit",
    minute: "2-digit",
    second: seconds ? "2-digit" : undefined,
    hour12: false,
  }).format(d(v));
}

/** "29 Oct 23:59:59" */
export function deadlineStamp(v: string | number | Date | null | undefined): string {
  if (!v || !isValidDate(v)) return "—";
  const date = new Intl.DateTimeFormat(LOCALE, { timeZone: TZ, day: "numeric", month: "short" }).format(d(v));
  return `${date} ${clock(v)}`;
}

/** "Due tomorrow, 23:59" / "Due today, 18:00" / "Due 31 Oct, 23:59". */
export function dueLabel(v: string | number | Date | null | undefined, now = Date.now()): string {
  if (!v || !isValidDate(v)) return "—";
  const dayKey = (t: Date | number) => new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(t);
  const target = d(v);
  const today = dayKey(now);
  const tomorrow = dayKey(now + 86_400_000);
  const day = dayKey(target);
  const time = clock(target, false);
  if (day === today) return `Due today, ${time}`;
  if (day === tomorrow) return `Due tomorrow, ${time}`;
  return `Due ${dateTime(target)}`;
}

export function relative(v: string | number | Date | null | undefined, now = Date.now()): string {
  if (!v || !isValidDate(v)) return "—";
  const diff = Math.round((now - d(v).getTime()) / 1000);
  const abs = Math.abs(diff);
  const future = diff < 0;
  const wrap = (s: string) => (future ? `in ${s}` : `${s} ago`);
  if (abs < 45) return future ? "in a few seconds" : "just now";
  if (abs < 3600) return wrap(`${Math.round(abs / 60)} min`);
  if (abs < 86400) return wrap(`${Math.round(abs / 3600)} h`);
  const days = Math.round(abs / 86400);
  return wrap(days === 1 ? "1 day" : `${days} days`);
}

export interface Countdown {
  total: number;
  days: number;
  hours: number;
  minutes: number;
  seconds: number;
  expired: boolean;
}

export function countdownParts(totalSeconds: number): Countdown {
  const expired = totalSeconds <= 0;
  const t = Math.max(0, Math.floor(totalSeconds));
  return {
    total: t,
    days: Math.floor(t / 86400),
    hours: Math.floor((t % 86400) / 3600),
    minutes: Math.floor((t % 3600) / 60),
    seconds: t % 60,
    expired,
  };
}

const pad = (n: number) => String(n).padStart(2, "0");

/** 81234 s → "22:33:54"; over 100 h → "4 d 03 h". */
export function hms(totalSeconds: number): string {
  const c = countdownParts(totalSeconds);
  const hours = c.days * 24 + c.hours;
  if (hours >= 100) return `${c.days} d ${pad(c.hours)} h`;
  return `${pad(hours)}:${pad(c.minutes)}:${pad(c.seconds)}`;
}

/** 92 → "1 min 32 s". */
export function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return "—";
  const s = Math.round(seconds);
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  if (m < 60) return r ? `${m} min ${r} s` : `${m} min`;
  const h = Math.floor(m / 60);
  return `${h} h ${m % 60} min`;
}

export function shortHash(h: string | null | undefined, n = 10): string {
  if (!h) return "—";
  const clean = h.replace(/^sha256:/, "");
  return clean.length > n ? `${clean.slice(0, n)}…` : clean;
}

/** Customers may still write in Romanian: normalize cedilla letters to comma-below (ş→ș, ţ→ț). */
export function normalizeRo(text: string): string {
  return text
    .replace(/ş/g, "ș")
    .replace(/Ş/g, "Ș")
    .replace(/ţ/g, "ț")
    .replace(/Ţ/g, "Ț")
    .normalize("NFC");
}

/** Loose matching for step IDs and agent names. */
export function slug(s: string | null | undefined): string {
  return (s ?? "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "");
}

const STATUS: Record<CaseStatus, string> = {
  NOU: "New",
  IN_ANALIZA: "In progress",
  ASTEAPTA_APROBARE: "Needs approval",
  RAMBURSAT: "Refunded",
  EXCEPTIE: "Exception",
  RESPINS: "Rejected",
  TRASEU_APP: "APP fraud review",
  INCHIS: "Closed",
  REFUZAT: "Declined",
  COADA_MANUALA: "Manual queue",
};

export function statusLabel(s: string | null | undefined): string {
  if (!s) return "—";
  return STATUS[s as CaseStatus] ?? s;
}

const VERDICT: Record<Verdict, string> = {
  RAMBURSEAZA: "Refund",
  RAMBURSEAZA_CU_APROBARE: "Refund after approval",
  EXCEPTIE_FRAUDA_CLIENT: "Exception: customer fraud",
  RESPINGE_TARDIV: "Reject: reported after 13 months",
  NU_SE_APLICA_T1: "Next-day refund doesn't apply",
  CHARGEBACK: "Chargeback",
  RECHEMARE: "Recall",
  RECUPERARE_PROPUSA: "Recovery proposed",
  NU_RECOMANDAM_RECUPERARE: "Don't ask the customer to repay",
  INFORMATII_SUPLIMENTARE: "Ask for more information",
  RTS_PROPUS: "Report proposed",
  MONITORIZARE: "Monitor",
  INCHIDE: "Close",
};

// The engine reuses one code for both recovery questions; the words depend on who would repay.
const VERDICT_BY_QUESTION: Record<string, Record<string, string>> = {
  recuperare_escroc: { NU_RECOMANDAM_RECUPERARE: "No recovery to start" },
};

export function verdictLabel(v: string | null | undefined, question?: string): string {
  if (!v) return "No decision yet";
  return (question && VERDICT_BY_QUESTION[question]?.[v]) ?? VERDICT[v as Verdict] ?? v;
}

export type Tone = "ink" | "yellow" | "alert" | "fog" | "outline" | "paper" | "pink";

export function verdictTone(v: string | null | undefined): Tone {
  switch (v) {
    case "RAMBURSEAZA":
    case "RAMBURSEAZA_CU_APROBARE":
      return "ink";
    case "EXCEPTIE_FRAUDA_CLIENT":
    case "RESPINGE_TARDIV":
    case "RTS_PROPUS":
      return "alert";
    case "NU_SE_APLICA_T1":
    case "INFORMATII_SUPLIMENTARE":
    case "RECUPERARE_PROPUSA":
      return "yellow";
    default:
      return "outline";
  }
}

export function statusTone(s: string | null | undefined): Tone {
  switch (s) {
    case "RAMBURSAT":
      return "ink";
    case "ASTEAPTA_APROBARE":
    case "EXCEPTIE":
    case "COADA_MANUALA":
      return "alert";
    case "IN_ANALIZA":
      return "yellow";
    case "RESPINS":
    case "TRASEU_APP":
      return "outline";
    default:
      return "fog";
  }
}

const QUESTION: Record<Question, string> = {
  rambursare_t1: "Refund now?",
  recuperare_client: "Ask the customer to repay?",
  recuperare_escroc: "Recover from the fraudster?",
  raspuns_reclamatie: "Reply to the customer",
  pista_aml: "AML lead",
  rts: "Suspicious transaction report",
};

export function questionLabel(q: string | null | undefined): string {
  if (!q) return "—";
  return QUESTION[q as Question] ?? q;
}

const SCENARIO: Record<Scenario, string> = {
  phishing_link: "Fake delivery link",
  card_ecom_fara_3ds: "Card online, no 3-D Secure",
  card_visa_secure: "Card with Visa Secure",
  vishing_securitate: "Fake bank security call",
  cont_sigur: "“Safe account” scam",
  sim_swap: "SIM swap",
  frauda_client: "Customer fraud",
  reclamatie_tardiva: "Reported after 13 months",
  plata_dubla: "Duplicate charge",
  inel_carausi: "One scam, several victims",
  injectie_document: "Hidden instructions",
  marfa_nelivrata: "Goods not delivered",
};

export function scenarioLabel(s: string | null | undefined): string {
  if (!s) return "—";
  return SCENARIO[s as Scenario] ?? s.replace(/_/g, " ");
}

const CHANNEL: Record<Channel, string> = {
  card: "Card",
  transfer: "Transfer",
  transfer_instant: "Instant transfer",
};

export function channelLabel(c: string | null | undefined): string {
  if (!c) return "—";
  return CHANNEL[c as Channel] ?? c;
}

const DISPUTE: Record<DisputeType, string> = {
  neautorizata: "Unauthorized",
  app: "Authorized under manipulation (APP)",
  disputa_comerciant: "Merchant dispute",
  eroare_procesare: "Processing error",
};

export function disputeLabel(t: string | null | undefined): string {
  if (!t) return "—";
  return DISPUTE[t as DisputeType] ?? t;
}

export function plural(n: number, one: string, many: string): string {
  return n === 1 ? `${n} ${one}` : `${num(n)} ${many}`;
}
