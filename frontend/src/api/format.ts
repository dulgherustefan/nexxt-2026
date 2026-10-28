import type { CaseStatus, Channel, DisputeType, Money, Question, Scenario, Verdict } from "./types";

/** Ora României, oricare ar fi fusul calculatorului de pe care rulează demo-ul. */
export const TZ = "Europe/Bucharest";

const nf0 = new Intl.NumberFormat("ro-RO", { maximumFractionDigits: 0 });
const nf2 = new Intl.NumberFormat("ro-RO", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function toMoney(v: number | Money | null | undefined, currency = "RON"): Money | null {
  if (v === null || v === undefined) return null;
  if (typeof v === "number") return { value: v, currency };
  if (typeof v === "object" && typeof v.value === "number") return { value: v.value, currency: v.currency ?? currency };
  return null;
}

/** 3200 → „3.200 lei"; 1249.9 → „1.249,90 lei". */
export function money(v: number | Money | null | undefined, opts: { decimals?: "auto" | 0 | 2 } = {}): string {
  const m = toMoney(v);
  if (!m) return "—";
  const decimals = opts.decimals ?? "auto";
  const useTwo = decimals === 2 || (decimals === "auto" && Math.round(m.value * 100) % 100 !== 0);
  const n = useTwo ? nf2.format(m.value) : nf0.format(m.value);
  const cur = (m.currency ?? "RON").toUpperCase();
  if (cur === "RON") return `${n} lei`;
  if (cur === "EUR") return `${n} €`;
  return `${n} ${cur}`;
}

export function num(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return new Intl.NumberFormat("ro-RO", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(v);
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

/** „29 oct., 23:59" */
export function dateTime(v: string | number | Date | null | undefined): string {
  if (!v || !isValidDate(v)) return "—";
  return new Intl.DateTimeFormat("ro-RO", {
    timeZone: TZ,
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d(v));
}

/** „29 octombrie 2026" */
export function dateLong(v: string | number | Date | null | undefined): string {
  if (!v || !isValidDate(v)) return "—";
  return new Intl.DateTimeFormat("ro-RO", { timeZone: TZ, day: "numeric", month: "long", year: "numeric" }).format(d(v));
}

/** „14:02:11" */
export function clock(v: string | number | Date | null | undefined, seconds = true): string {
  if (!v || !isValidDate(v)) return "—";
  return new Intl.DateTimeFormat("ro-RO", {
    timeZone: TZ,
    hour: "2-digit",
    minute: "2-digit",
    second: seconds ? "2-digit" : undefined,
    hour12: false,
  }).format(d(v));
}

/** „29.10 · 23:59:59" pentru linia conturată de sub ceas. */
export function deadlineStamp(v: string | number | Date | null | undefined): string {
  if (!v || !isValidDate(v)) return "—";
  const date = new Intl.DateTimeFormat("ro-RO", { timeZone: TZ, day: "2-digit", month: "2-digit" }).format(d(v));
  return `${date.replace(/\.$/, "")} ${clock(v)}`;
}

export function relative(v: string | number | Date | null | undefined, now = Date.now()): string {
  if (!v || !isValidDate(v)) return "—";
  const diff = Math.round((now - d(v).getTime()) / 1000);
  const abs = Math.abs(diff);
  const future = diff < 0;
  const wrap = (s: string) => (future ? `peste ${s}` : `acum ${s}`);
  if (abs < 45) return future ? "în câteva secunde" : "acum câteva secunde";
  if (abs < 3600) return wrap(`${Math.round(abs / 60)} min`);
  if (abs < 86400) return wrap(`${Math.round(abs / 3600)} h`);
  const days = Math.round(abs / 86400);
  return wrap(days === 1 ? "o zi" : `${days} zile`);
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

/** 81234 s → „22:33:54"; 31 h → „31:05:42"; peste 100 h → „4 zile 03 h". */
export function hms(totalSeconds: number): string {
  const c = countdownParts(totalSeconds);
  const hours = c.days * 24 + c.hours;
  if (hours >= 100) return `${c.days} zile ${pad(c.hours)} h`;
  return `${pad(hours)}:${pad(c.minutes)}:${pad(c.seconds)}`;
}

/** 92 → „1 min 32 s". */
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

// ------------------------------------------------------------------ texte în română

/** Normalizează cedila la virgulă (ş→ș, ţ→ț), cum cer regulile proiectului la intrare. */
export function normalizeRo(text: string): string {
  return text
    .replace(/ş/g, "ș")
    .replace(/Ş/g, "Ș")
    .replace(/ţ/g, "ț")
    .replace(/Ţ/g, "Ț")
    .normalize("NFC");
}

/** Pentru potriviri tolerante (ID-uri de pași, nume de agenți). */
export function slug(s: string | null | undefined): string {
  return (s ?? "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "");
}

const STATUS: Record<CaseStatus, string> = {
  NOU: "Nou",
  IN_ANALIZA: "În analiză",
  ASTEAPTA_APROBARE: "Așteaptă aprobare",
  RAMBURSAT: "Rambursat",
  EXCEPTIE: "Excepție",
  RESPINS: "Respins",
  TRASEU_APP: "Traseu APP",
  INCHIS: "Închis",
};

export function statusLabel(s: string | null | undefined): string {
  if (!s) return "—";
  return STATUS[s as CaseStatus] ?? s;
}

const VERDICT: Record<Verdict, string> = {
  RAMBURSEAZA: "Rambursează",
  RAMBURSEAZA_CU_APROBARE: "Rambursează cu aprobare",
  EXCEPTIE_FRAUDA_CLIENT: "Excepție: frauda clientului",
  RESPINGE_TARDIV: "Respinge: peste 13 luni",
  NU_SE_APLICA_T1: "T+1 nu se aplică",
  CHARGEBACK: "Chargeback",
  RECHEMARE: "Rechemare",
  RECUPERARE_PROPUSA: "Recuperare propusă",
  NU_RECOMANDAM_RECUPERARE: "Nu recomandăm recuperarea",
  INFORMATII_SUPLIMENTARE: "Cere informații",
  RTS_PROPUS: "RTS propus",
  MONITORIZARE: "Monitorizare",
  INCHIDE: "Închide",
};

export function verdictLabel(v: string | null | undefined): string {
  if (!v) return "Fără verdict";
  return VERDICT[v as Verdict] ?? v;
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
  rambursare_t1: "Rambursăm acum?",
  recuperare_client: "Cerem banii de la client?",
  recuperare_escroc: "Recuperăm de la escroc?",
  raspuns_reclamatie: "Răspunsul la reclamație",
  pista_aml: "Pistă AML",
  rts: "Raport de tranzacție suspectă",
};

export function questionLabel(q: string | null | undefined): string {
  if (!q) return "—";
  return QUESTION[q as Question] ?? q;
}

const SCENARIO: Record<Scenario, string> = {
  phishing_link: "Link fals (curier)",
  card_ecom_fara_3ds: "Card online fără 3DS",
  card_visa_secure: "Card cu Visa Secure",
  vishing_securitate: "Apel „de la securitate”",
  cont_sigur: "„Cont sigur”",
  sim_swap: "SIM swap",
  frauda_client: "Frauda clientului",
  reclamatie_tardiva: "Reclamație după 13 luni",
  plata_dubla: "Plată dublă",
  inel_carausi: "Inel de cărăuși",
  injectie_document: "Instrucțiuni ascunse",
  marfa_nelivrata: "Marfă nelivrată",
};

export function scenarioLabel(s: string | null | undefined): string {
  if (!s) return "—";
  return SCENARIO[s as Scenario] ?? s.replace(/_/g, " ");
}

const CHANNEL: Record<Channel, string> = {
  card: "Card",
  transfer: "Transfer",
  transfer_instant: "Transfer instant",
};

export function channelLabel(c: string | null | undefined): string {
  if (!c) return "—";
  return CHANNEL[c as Channel] ?? c;
}

const DISPUTE: Record<DisputeType, string> = {
  neautorizata: "Neautorizată",
  app: "Autorizată sub manipulare (APP)",
  disputa_comerciant: "Dispută cu comerciantul",
  eroare_procesare: "Eroare de procesare",
};

export function disputeLabel(t: string | null | undefined): string {
  if (!t) return "—";
  return DISPUTE[t as DisputeType] ?? t;
}

export function plural(n: number, one: string, many: string): string {
  return n === 1 ? `${n} ${one}` : `${num(n)} ${many}`;
}
