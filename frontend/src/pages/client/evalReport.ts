/**
 * Raportul de evaluare (`versoml eval` → var/eval/report.json) adus la o singură formă.
 * Forma reală: {at, llm_mode, sections:{…}, summary:{rows:[{name, value, target}]}}.
 * Raportul simulat din modul mock are altă formă; îl traducem pe aceleași secțiuni, fără cifre noi.
 */
import { num } from "../../api/format";

export type Obj = Record<string, unknown>;

export interface EvalRow {
  name: string;
  value: unknown;
  target: string | null;
}

export type EvalModel =
  | { kind: "missing"; message: string | null }
  | { kind: "report"; at: string | null; llmMode: string | null; source: string | null; rows: EvalRow[]; sections: Obj; simulated: boolean; raw: unknown };

export const isObj = (v: unknown): v is Obj => Boolean(v) && typeof v === "object" && !Array.isArray(v);
export const get = (o: unknown, ...path: string[]): unknown => path.reduce<unknown>((cur, k) => (isObj(cur) ? cur[k] : undefined), o);
const n = (v: unknown): number | undefined => (typeof v === "number" && Number.isFinite(v) ? v : undefined);

/** Aceleași rânduri ca `_rows_summary` din backend (nume și ținte de acolo), pentru rapoartele fără sinteză. */
function rowsFromSections(s: Obj): EvalRow[] {
  const m5 = get(s, "ml", "m5_mule");
  return [
    { name: "Reguli: verdict T+1 pe setul de aur (40)", value: get(s, "rules_golden", "verdict_accuracy"), target: "100%" },
    { name: "Reguli: verdict pe 300 de cazuri generate", value: get(s, "rules_generated", "verdict_accuracy"), target: "100%" },
    { name: "Termene T+1 corecte", value: get(s, "rules_golden", "deadline_accuracy"), target: "100%" },
    { name: "Recall escaladări spre om", value: get(s, "rules_golden", "escalation_recall"), target: "≥ 0,95" },
    { name: "Neinterferență: scurgeri peste zid", value: get(s, "noninterference", "leaks"), target: "0" },
    { name: "Neinterferență: decizii schimbate de zona AML", value: get(s, "noninterference", "mismatches"), target: "0" },
    { name: "Date personale brute trimise LLM-ului", value: get(s, "privacy", "raw_pii_to_llm"), target: "0" },
    { name: "Injecții detectate", value: get(s, "injection", "detection_rate"), target: "100%" },
    { name: "Filtrul zidului: recall tipping-off", value: get(s, "letter_filter", "tipping_off_recall"), target: "100%" },
    { name: "M1 clasificare scenariu: macro-F1", value: get(s, "ml", "m1_classifier", "scenario", "macro_f1"), target: "≥ 0,90" },
    { name: "M1 calibrare scenariu: ECE", value: get(s, "ml", "m1_classifier", "scenario", "ece"), target: "≤ 0,05" },
    { name: "M5 cărăuși: AUC (GBDT pe graf)", value: get(m5, "gbdt_graph", "auc"), target: "≥ 0,85" },
    { name: "M5 cărăuși: AUC doar reguli (bază)", value: get(m5, "rules_only", "auc"), target: "comparație" },
  ].filter((r) => r.value !== undefined);
}

/** Raportul simulat (mock): aceleași cifre, puse pe secțiunile reale. */
function fromLegacy(raw: Obj): Obj {
  const injection = get(raw, "injection");
  const attacks = n(get(injection, "attacks"));
  const succeeded = n(get(injection, "succeeded"));
  const sections: Obj = {
    rules_golden: {
      cases: get(raw, "golden_set", "cases"),
      verdict_accuracy: get(raw, "rules", "consistency"),
      deadline_accuracy: get(raw, "rules", "deadlines_correct"),
      escalation_recall: get(raw, "escalation", "recall"),
    },
    rules_generated: { cases: get(raw, "golden_set", "generated_cases") },
    noninterference: get(raw, "noninterference"),
    privacy: isObj(raw.privacy) ? { complaints_checked: raw.privacy.requests_scanned, raw_pii_to_llm: raw.privacy.raw_pii_to_llm } : undefined,
    // „succeeded" spune câte injecții au schimbat ceva, nu câte au fost detectate: nu deducem rata de detecție
    injection: attacks !== undefined ? { injection_cases: attacks, decision_changed_by_injection: succeeded } : undefined,
    ml: isObj(raw.ml)
      ? {
          m1_classifier: isObj(raw.ml.m1_classifier) ? { scenario: raw.ml.m1_classifier } : undefined,
          m5_mule: isObj(raw.ml.m5_mule) ? { gbdt_graph: raw.ml.m5_mule } : undefined,
        }
      : undefined,
  };
  return Object.fromEntries(Object.entries(sections).filter(([, v]) => v !== undefined));
}

export function normalizeEval(raw: unknown): EvalModel {
  if (!isObj(raw)) return { kind: "missing", message: null };
  if (raw.status === "missing") return { kind: "missing", message: typeof raw.message === "string" ? raw.message : null };
  const real = isObj(raw.sections);
  const sections = real ? (raw.sections as Obj) : fromLegacy(raw);
  const given = get(raw, "summary", "rows");
  const rows = Array.isArray(given)
    ? given.filter(isObj).map((r) => ({ name: String(r.name ?? "—"), value: r.value, target: r.target === undefined || r.target === null ? null : String(r.target) }))
    : rowsFromSections(sections);
  const source = typeof raw.source === "string" ? raw.source : null;
  return {
    kind: "report",
    at: typeof raw.at === "string" ? raw.at : typeof raw.generated_at === "string" ? raw.generated_at : null,
    llmMode: typeof raw.llm_mode === "string" ? raw.llm_mode : null,
    source,
    rows,
    sections,
    simulated: !real || /mock|simulat/i.test(source ?? ""),
    raw,
  };
}

// ------------------------------------------------------------------ ținte și valori

export type Outcome = "met" | "below" | "na";

interface Target {
  op: ">=" | "<=" | ">" | "<" | "=" | "~";
  x: number;
}

/** „≈ 0" e atins sub această toleranță (1 punct procentual); o spunem pe pagină. */
export const APPROX_TOLERANCE = 0.01;

export function parseTarget(t: string | null): Target | null {
  if (!t) return null;
  const s = t.trim();
  const m = s.match(/^(≥|>=|≤|<=|≈|~|>|<|=)?\s*(-?\d+(?:[.,]\d+)?)\s*(%)?/);
  if (!m) return null;
  const opRaw = m[1] ?? "=";
  const op = ({ "≥": ">=", ">=": ">=", "≤": "<=", "<=": "<=", "≈": "~", "~": "~", ">": ">", "<": "<", "=": "=" } as const)[opRaw] ?? "=";
  let x = Number(m[2].replace(",", "."));
  if (m[3]) x /= 100;
  // „100%" fără operator = cel puțin 100%
  return { op: m[3] && op === "=" ? ">=" : op, x };
}

export function outcome(value: unknown, target: string | null): Outcome {
  const t = parseTarget(target);
  const v = typeof value === "number" ? value : typeof value === "string" && value.trim() !== "" ? Number(value.replace(",", ".")) : NaN;
  if (!t || !Number.isFinite(v)) return "na";
  const eps = 1e-9;
  switch (t.op) {
    case ">=": return v >= t.x - eps ? "met" : "below";
    case "<=": return v <= t.x + eps ? "met" : "below";
    case ">": return v > t.x ? "met" : "below";
    case "<": return v < t.x ? "met" : "below";
    case "=": return Math.abs(v - t.x) <= eps ? "met" : "below";
    case "~": return Math.abs(v - t.x) <= APPROX_TOLERANCE ? "met" : "below";
  }
}

const fractional = (t: string | null) => Boolean(t && (/%/.test(t) || /\d[.,]\d/.test(t)));

/** 0,9927 → „99,3%"; 1 → „100%"; 0,9996 → „99,96%" (nu rotunjim la 100% ce nu e 100%). */
export function pct(v: number): string {
  const x = v * 100;
  const round1 = Math.round(x * 10) / 10;
  const digits = Number.isInteger(x) ? 0 : (round1 >= 100 && x < 100) || (round1 === 0 && x !== 0) ? 2 : 1;
  return `${new Intl.NumberFormat("ro-RO", { maximumFractionDigits: digits }).format(x)}%`;
}

/** Fracțiile ≤ 1 devin procente; 0 și 1 doar când ținta e procent sau zecimală (altfel sunt numărători). */
export function showValue(v: unknown, target: string | null = null): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "da" : "nu";
  if (typeof v === "number") {
    if (!Number.isFinite(v)) return "—";
    const asPct = (!Number.isInteger(v) && Math.abs(v) <= 1) || (Number.isInteger(v) && (v === 0 || v === 1) && fractional(target));
    return asPct ? pct(v) : num(v, Number.isInteger(v) ? 0 : 2);
  }
  if (Array.isArray(v)) return v.map((x) => showValue(x)).join(", ");
  if (isObj(v)) return JSON.stringify(v);
  return String(v);
}

/** Ținta în aceeași unitate ca valoarea: „≥ 0,95" lângă „100%" devine „≥ 95%". */
export function showTarget(target: string | null, value: unknown): string {
  if (!target) return "—";
  const shownAsPct = /%$/.test(showValue(value, target));
  if (!shownAsPct || /%/.test(target)) return target;
  const t = parseTarget(target);
  if (!t || !/\d[.,]\d/.test(target)) return target;
  const sym = { ">=": "≥", "<=": "≤", ">": ">", "<": "<", "=": "", "~": "≈" }[t.op];
  return `${sym ? `${sym} ` : ""}${pct(t.x)}`;
}

/** Valori din secțiuni: rate ca procente, milisecunde, octeți. */
export function showMetric(key: string, v: unknown): string {
  if (typeof v === "number" && Number.isFinite(v)) {
    if (/^ms_|_ms$/.test(key)) return `${num(v, v < 10 ? 1 : 0)} ms`;
    if (/bytes/.test(key)) return v >= 1e6 ? `${num(v / 1e6, 1)} MB` : v >= 1e3 ? `${num(v / 1e3, 1)} kB` : `${num(v)} B`;
    if (/^seconds|_s$|seconds_total/.test(key)) return `${num(v, 1)} s`;
    const rate = /accuracy|recall|precision|rate|auc|f1|ece|consistency|validity|correct/.test(key);
    if (rate && Math.abs(v) <= 1) return pct(v);
    return num(v, Number.isInteger(v) ? 0 : 2);
  }
  return showValue(v);
}
