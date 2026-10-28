/**
 * Logica fără UI a aplicației Banca Demo: clientul din URL, contestațiile urmărite pe acest
 * dispozitiv, pașii contestației în cuvintele clientului și datele „în clar”.
 */
import { clock, TZ } from "../../api/format";
import type { BankTransaction } from "../../api/types";

export const DEFAULT_CLIENT = "CUST-DEMO-01";
const CLIENT_RE = /^CUST-[A-Za-z0-9-]{1,40}$/;

export function clientFrom(search: URLSearchParams): string {
  const c = search.get("client");
  return c && CLIENT_RE.test(c) ? c : DEFAULT_CLIENT;
}

// ------------------------------------------------------------------ contestațiile urmărite (doar comoditate pe dispozitiv)

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
    /* fără stocare: contestația rămâne urmărită cât e pagina deschisă */
  }
}

// ------------------------------------------------------------------ tranzacții

export const isOut = (t: BankTransaction) => t.direction === "out" || t.direction === "debit";

export function isRefundTx(t: BankTransaction): boolean {
  return !isOut(t) && /rambursare|returnat/i.test(t.description ?? "");
}

export function isDisputed(t: BankTransaction, tracked: TrackedDispute[]): boolean {
  return Boolean(t.disputed) || /contest|rambursat/i.test(t.status ?? "") || tracked.some((d) => d.transaction_id === t.id);
}

export function canDispute(t: BankTransaction, tracked: TrackedDispute[]): boolean {
  return isOut(t) && t.disputable !== false && !isDisputed(t, tracked);
}

const RECENT_MS = 24 * 3600_000;

export function isRecent(t: BankTransaction, now: number): boolean {
  const ts = new Date(t.ts).getTime();
  return Number.isFinite(ts) && now - ts <= RECENT_MS && ts - now < 10 * 60_000;
}

const nf2 = new Intl.NumberFormat("ro-RO", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** „3.200,00" (fără semn și fără monedă). */
export function amount2(v: number): string {
  return nf2.format(Math.abs(v));
}

export function signedLei(t: BankTransaction): string {
  return `${isOut(t) ? "−" : "+"}${amount2(t.amount)} lei`;
}

// ------------------------------------------------------------------ date în clar

const dayKey = (d: Date) => new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(d);

/** „Azi", „Ieri" sau „luni, 26 octombrie". */
export function dayLabel(ts: string, now: number): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "Fără dată";
  const k = dayKey(d);
  if (k === dayKey(new Date(now))) return "Azi";
  if (k === dayKey(new Date(now - 86_400_000))) return "Ieri";
  const s = new Intl.DateTimeFormat("ro-RO", { timeZone: TZ, weekday: "long", day: "numeric", month: "long" }).format(d);
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** „mâine, joi 29 octombrie, la 23:59". */
export function plainWhen(iso: string | null | undefined, now: number): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const k = dayKey(d);
  const rel = k === dayKey(new Date(now)) ? "azi" : k === dayKey(new Date(now + 86_400_000)) ? "mâine" : null;
  const weekday = new Intl.DateTimeFormat("ro-RO", { timeZone: TZ, weekday: "long" }).format(d);
  const date = new Intl.DateTimeFormat("ro-RO", { timeZone: TZ, day: "numeric", month: "long" }).format(d);
  return `${rel ? `${rel}, ` : ""}${weekday} ${date}, la ${clock(d, false)}`;
}

/** „14:02" azi, altfel „26 oct., 14:02". */
export function shortWhen(ts: string, now: number): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "";
  if (dayKey(d) === dayKey(new Date(now))) return clock(d, false);
  return new Intl.DateTimeFormat("ro-RO", { timeZone: TZ, day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(d);
}

// ------------------------------------------------------------------ pașii contestației, în cuvintele clientului

export type StepState = "done" | "now" | "todo" | "ok" | "info";

export interface Step {
  label: string;
  state: StepState;
}

export const FINAL = new Set(["RAMBURSAT", "TRASEU_APP", "EXCEPTIE", "RESPINS", "INCHIS"]);

export function stepsFor(status: string, verdict: string | null | undefined): Step[] {
  const received: Step = { label: "Contestație primită", state: "done" };
  const analysed: Step = { label: "Analizăm", state: "done" };
  switch (status) {
    case "ASTEAPTA_APROBARE":
      return [received, analysed, { label: "Un specialist verifică", state: "now" }, { label: "Rambursat", state: "todo" }];
    case "RAMBURSAT":
      return [
        received,
        analysed,
        ...(verdict === "RAMBURSEAZA_CU_APROBARE" ? [{ label: "Un specialist a verificat", state: "done" as const }] : []),
        { label: "Rambursat", state: "ok" },
      ];
    case "TRASEU_APP":
      return [received, analysed, { label: "Plată autorizată de tine: te ajutăm să recuperezi banii", state: "info" }];
    case "EXCEPTIE":
      return [received, analysed, { label: "Avem nevoie de verificări suplimentare: îți răspundem în scris", state: "info" }];
    case "RESPINS":
      return [received, analysed, { label: "Nu am putut accepta contestația: îți explicăm în scris de ce", state: "info" }];
    case "INCHIS":
      return [received, analysed, { label: "Contestație închisă", state: "info" }];
    case "EROARE":
      return [received, { label: "Analiza automată s-a oprit; contestația rămâne înregistrată și termenul curge", state: "info" }];
    default:
      return [received, { label: "Analizăm", state: "now" }, { label: "Rambursat", state: "todo" }];
  }
}
