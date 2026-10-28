/**
 * Demo Bank logic without UI: the customer from the URL, the disputes this phone tracks,
 * the dispute steps in the customer's words, and amounts and dates in plain English.
 */
import { useEffect } from "react";
import { clock, money, TZ } from "../../api/format";
import type { BankNotification, BankTransaction } from "../../api/types";

export const DEFAULT_CLIENT = "CUST-DEMO-01";
/** The two jurors' accounts; the second one opens with `?client=CUST-DEMO-02`. */
export const DEMO_CLIENTS = ["CUST-DEMO-01", "CUST-DEMO-02"] as const;
const CLIENT_RE = /^CUST-[A-Za-z0-9-]{1,40}$/;

export function clientFrom(search: URLSearchParams): string {
  const c = search.get("client");
  return c && CLIENT_RE.test(c) ? c : DEFAULT_CLIENT;
}

export function bankPath(ref: string): string {
  return `/bank?client=${encodeURIComponent(ref)}`;
}

// ------------------------------------------------------------------ disputes tracked on this phone (a convenience only)

export interface TrackedDispute {
  case_id: string;
  transaction_id: string;
  at: number;
}

const key = (ref: string) => `versoml.bank.disputes.${ref}`;

export function loadTracked(ref: string): TrackedDispute[] {
  try {
    const raw = localStorage.getItem(key(ref));
    const list = raw ? (JSON.parse(raw) as TrackedDispute[]) : [];
    return Array.isArray(list) ? list.filter((d) => d && typeof d.case_id === "string").slice(0, 5) : [];
  } catch {
    return [];
  }
}

export function saveTracked(ref: string, list: TrackedDispute[]) {
  try {
    localStorage.setItem(key(ref), JSON.stringify(list.slice(0, 5)));
  } catch {
    /* no storage: the dispute stays tracked while the page is open */
  }
}

// ------------------------------------------------------------------ transactions

export const isOut = (t: BankTransaction) => t.direction === "out" || t.direction === "debit";

/** The backend writes "Refund for dispute CT-…"; older data says "Rambursare contestație CT-…". */
export function isRefundTx(t: BankTransaction): boolean {
  return !isOut(t) && /\brefund|rambursare|returnat/i.test(t.description ?? "");
}

export function isRefunded(t: BankTransaction): boolean {
  return /refunded|rambursat/i.test(t.status ?? "");
}

export function isDisputed(t: BankTransaction, tracked: TrackedDispute[]): boolean {
  return Boolean(t.disputed) || /disput|contest|refunded|rambursat/i.test(t.status ?? "") || tracked.some((d) => d.transaction_id === t.id);
}

export function canDispute(t: BankTransaction, tracked: TrackedDispute[]): boolean {
  return isOut(t) && t.disputable !== false && !isDisputed(t, tracked);
}

const RECENT_MS = 24 * 3600_000;

export function isRecent(t: BankTransaction, now: number): boolean {
  const ts = new Date(t.ts).getTime();
  return Number.isFinite(ts) && now - ts <= RECENT_MS && ts - now < 10 * 60_000;
}

/** "RON 3,200.00", without a sign. */
export function amountText(v: number): string {
  return money(Math.abs(v));
}

/** "−RON 3,200.00" for money out, "+RON 6,200.00" for money in. */
export function signedAmount(t: BankTransaction): string {
  return `${isOut(t) ? "−" : "+"}${amountText(t.amount)}`;
}

export type TxCategory =
  | "refund"
  | "income"
  | "groceries"
  | "health"
  | "energy"
  | "water"
  | "telecom"
  | "transit"
  | "taxi"
  | "food"
  | "coffee"
  | "fuel"
  | "books"
  | "cinema"
  | "cash"
  | "transfer_out"
  | "transfer_in"
  | "card";

const CATEGORY_RULES: Array<[RegExp, TxCategory]> = [
  [/salar|salary|pension|pensie|invoice payment/i, "income"],
  [/supermarket|market|grocer|magazin|pia[tț]a/i, "groceries"],
  [/pharm|farmac/i, "health"],
  [/energ|electric|curent/i, "energy"],
  [/\bwater\b|\bap[aă](?!\p{L})/iu, "water"],
  [/internet|telco|mobile|phone|abonament telefon/i, "telecom"],
  [/transit|transport|metro|\bbus\b|tram/i, "transit"],
  [/taxi|\bride\b/i, "taxi"],
  [/caf[eé]|cafenea|coffee/i, "coffee"],
  [/restaurant|bistro|food|m[aâ]ncare|pizza/i, "food"],
  [/gas station|fuel|benzin|petrol/i, "fuel"],
  [/\bbook|libr[aă]ri/i, "books"],
  [/cinema|movie|film/i, "cinema"],
  [/\batm\b|withdrawal|retragere/i, "cash"],
];

/** A category for the row's icon, guessed from the description (backend and mock data alike). */
export function txCategory(t: BankTransaction): TxCategory {
  if (isRefundTx(t)) return "refund";
  const d = t.description ?? "";
  for (const [re, cat] of CATEGORY_RULES) if (re.test(d)) return cat;
  if (/transfer|către|catre/i.test(d)) return isOut(t) ? "transfer_out" : "transfer_in";
  return isOut(t) ? "card" : "transfer_in";
}

// ------------------------------------------------------------------ notifications

export type NoteKind = "refund" | "money" | "security" | "info";

export function noteKind(n: BankNotification): NoteKind {
  const k = String(n.kind ?? "").toLowerCase();
  if (k === "refund" || k === "rambursare" || /\brefunded|\breturnat|rambursa/i.test(n.text ?? "")) return "refund";
  if (k === "debit" || k === "credit" || k === "tranzactie" || k === "transaction") return "money";
  if (k === "securitate" || k === "security") return "security";
  return "info";
}

// ------------------------------------------------------------------ dates in plain words

/** Fixed abbreviations, so September stays "Sep" whatever the browser's locale data says. */
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function parts(d: Date) {
  const p = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(d);
  const get = (t: string) => Number(p.find((x) => x.type === t)?.value);
  return { y: get("year"), m: get("month"), d: get("day") };
}

const dayKey = (d: Date) => {
  const { y, m, d: day } = parts(d);
  return `${y}-${m}-${day}`;
};

const weekday = (d: Date) => new Intl.DateTimeFormat("en-GB", { timeZone: TZ, weekday: "long" }).format(d);

/** "26 Oct", or "26 Oct 2025" outside the current year. */
export function dayMonth(d: Date, now = Date.now()): string {
  const { y, m, d: day } = parts(d);
  return y === parts(new Date(now)).y ? `${day} ${MONTHS[m - 1]}` : `${day} ${MONTHS[m - 1]} ${y}`;
}

/** "29 Oct 2026, 23:59": the house format, for a payment's exact time. */
export function fullWhen(ts: string): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "—";
  const { y, m, d: day } = parts(d);
  return `${day} ${MONTHS[m - 1]} ${y}, ${clock(d, false)}`;
}

/** "Today", "Yesterday" or "Monday, 26 Oct". */
export function dayLabel(ts: string, now: number): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "No date";
  const k = dayKey(d);
  if (k === dayKey(new Date(now))) return "Today";
  if (k === dayKey(new Date(now - 86_400_000))) return "Yesterday";
  return `${weekday(d)}, ${dayMonth(d, now)}`;
}

/** "19:39" today, otherwise "26 Oct, 14:02". */
export function shortWhen(ts: string, now: number): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "";
  if (dayKey(d) === dayKey(new Date(now))) return clock(d, false);
  return `${dayMonth(d, now)}, ${clock(d, false)}`;
}

/** For sentences: "at 19:39" today, otherwise "on 26 Oct at 14:02". */
export function atWhen(ts: string, now: number): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "";
  if (dayKey(d) === dayKey(new Date(now))) return `at ${clock(d, false)}`;
  return `on ${dayMonth(d, now)} at ${clock(d, false)}`;
}

/**
 * The refund deadline for a customer: "the end of tomorrow, 29 Oct". The deadline is the end of a
 * business day (23:59:59); any other time is written out: "17:00 on Monday, 2 Nov".
 */
export function refundBy(iso: string | null | undefined, now: number): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const k = dayKey(d);
  const rel = k === dayKey(new Date(now)) ? "today" : k === dayKey(new Date(now + 86_400_000)) ? "tomorrow" : null;
  const day = rel === "today" ? "today" : rel === "tomorrow" ? `tomorrow, ${dayMonth(d, now)}` : `${weekday(d)}, ${dayMonth(d, now)}`;
  const time = clock(d, false);
  if (time === "23:59") return `the end of ${day}`;
  return rel ? `${time} ${day}` : `${time} on ${day}`;
}

/** The written answer's date: "18 Nov 2026". */
export function answerBy(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const { y, m, d: day } = parts(d);
  return `${day} ${MONTHS[m - 1]} ${y}`;
}

// ------------------------------------------------------------------ the dispute's steps, in the customer's words

export type StepState = "done" | "now" | "todo" | "ok" | "info";

export interface Step {
  label: string;
  state: StepState;
  /** One line under the tracker, for the step that needs explaining. */
  note?: string;
  /** The icon of an "info" step: the outcome that is not a refund. */
  mark?: "recover" | "wait" | "stop" | "closed" | "pause";
}

export const FINAL = new Set(["RAMBURSAT", "TRASEU_APP", "EXCEPTIE", "RESPINS", "INCHIS"]);

/** Always three steps: Received → Under review → Refunded (or the outcome that replaces the refund). */
export function stepsFor(status: string, verdict: string | null | undefined): Step[] {
  const received: Step = { label: "Received", state: "done" };
  const reviewed: Step = { label: "Under review", state: "done" };
  const refunded: Step = { label: "Refunded", state: "todo" };
  switch (status) {
    case "ASTEAPTA_APROBARE":
      return [received, { label: "Under review", state: "now", note: "A specialist is checking it now." }, refunded];
    case "RAMBURSAT":
      return [
        received,
        verdict === "RAMBURSEAZA_CU_APROBARE" ? { ...reviewed, note: "A specialist approved it." } : reviewed,
        { label: "Refunded", state: "ok" },
      ];
    case "TRASEU_APP":
      return [received, reviewed, { label: "Recovery", state: "info", mark: "recover", note: "You approved this payment yourself, so we're helping you get the money back." }];
    case "EXCEPTIE":
      return [received, reviewed, { label: "More checks", state: "info", mark: "wait", note: "We need to run more checks. We'll write to you." }];
    case "RESPINS":
      return [received, reviewed, { label: "Not accepted", state: "info", mark: "stop", note: "We couldn't accept your claim. We'll explain why in writing." }];
    case "INCHIS":
      return [received, reviewed, { label: "Closed", state: "info", mark: "closed", note: "Your claim is closed." }];
    case "EROARE":
      return [
        received,
        { label: "Under review", state: "info", mark: "pause", note: "The automatic review stopped. Your claim is still on record, and the deadline still applies." },
        refunded,
      ];
    default:
      return [received, { label: "Under review", state: "now" }, refunded];
  }
}

// ------------------------------------------------------------------ the browser's top bar

/** Colors the phone's browser bar to match the page while it is open. */
export function useThemeColor(color: string) {
  useEffect(() => {
    const meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
    if (!meta) return;
    const prev = meta.content;
    meta.content = color;
    return () => {
      meta.content = prev;
    };
  }, [color]);
}
