/**
 * The evaluation report (`versoml eval` writes var/eval/report.json), reduced to what the dispute
 * console shows. Real shape: {at, llm_mode, sections: {...}, summary: {rows}}. The demo data uses an
 * older shape, mapped onto the same sections without inventing numbers.
 *
 * The metric list is built here from `sections`, with its own names and the backend's targets.
 * The wall, tipping-off and money-mule sections stay in the raw JSON but aren't listed: AML is out
 * of the product.
 */
import { num } from "../../api/format";

export type Obj = Record<string, unknown>;

export const isObj = (v: unknown): v is Obj => Boolean(v) && typeof v === "object" && !Array.isArray(v);
export const get = (o: unknown, ...path: string[]): unknown => path.reduce<unknown>((cur, k) => (isObj(cur) ? cur[k] : undefined), o);
const n = (v: unknown): number | undefined => (typeof v === "number" && Number.isFinite(v) ? v : undefined);
const str = (v: unknown): string | null => (typeof v === "string" && v.trim() !== "" ? v : null);

// ---------------------------------------------------------------- metrics

export type GroupId = "decisions" | "safety" | "classifier" | "runs";

export const METRIC_GROUPS: Array<{ id: GroupId; title: string }> = [
  { id: "decisions", title: "Rules engine vs oracle" },
  { id: "safety", title: "Privacy and prompt safety" },
  { id: "classifier", title: "Claim classifier" },
  { id: "runs", title: "Measured run times" },
];

export type Format = "pct" | "count" | "score" | "seconds";
/** `measured`: a number reported as it is, with no target to pass (run times). */
export type Outcome = "pass" | "fail" | "none" | "measured";

export interface Target {
  op: ">=" | "<=";
  x: number;
}

export interface Metric {
  id: string;
  group: GroupId;
  name: string;
  /** Context under the name: how many cases, what the number means. */
  detail: string | null;
  /** Why there is no value: a section that failed, didn't run or isn't in the report. */
  problem: string | null;
  value: number | null;
  outcome: Outcome;
  valueText: string;
  targetText: string;
}

interface Spec {
  id: string;
  group: GroupId;
  name: string;
  section: string;
  path: string[];
  format: Format;
  /** None for a measurement reported as it is. */
  target?: Target;
  detail?: (s: Obj) => string | null;
}

const count = (v: unknown, one: string, many: string): string | null => {
  const x = n(v);
  return x === undefined ? null : `${num(x)} ${x === 1 ? one : many}`;
};

/** Targets match `_rows_summary` in versoml/eval/run.py. "≈ 0" for false alarms is read as at most 1%. */
const SPECS: Spec[] = [
  {
    id: "golden", group: "decisions", name: "Rules engine vs oracle: refund verdict on the golden set",
    section: "rules_golden", path: ["verdict_accuracy"], format: "pct", target: { op: ">=", x: 1 },
    detail: (s) => count(get(s, "rules_golden", "cases"), "hand-checked case", "hand-checked cases"),
  },
  {
    id: "generated", group: "decisions", name: "Rules engine vs oracle: verdict on generated cases",
    section: "rules_generated", path: ["verdict_accuracy"], format: "pct", target: { op: ">=", x: 1 },
    detail: (s) => count(get(s, "rules_generated", "cases"), "generated case", "generated cases"),
  },
  {
    id: "typologies", group: "decisions", name: "Rules engine vs oracle: verdict on the typology cases",
    section: "rules_typologies", path: ["verdict_accuracy"], format: "pct", target: { op: ">=", x: 1 },
    detail: (s) => count(get(s, "rules_typologies", "cases"), "typology case", "typology cases"),
  },
  {
    id: "deadlines", group: "decisions", name: "Rules engine vs oracle: refund deadlines",
    section: "rules_golden", path: ["deadline_accuracy"], format: "pct", target: { op: ">=", x: 1 },
    detail: () => "End of the next business day, with Romanian public holidays. The oracle reads the same decision table, so this checks the code follows it",
  },
  {
    id: "escalation", group: "decisions", name: "Rules engine vs oracle: escalations to a person",
    section: "rules_golden", path: ["escalation_recall"], format: "pct", target: { op: ">=", x: 0.95 },
    detail: () => "Escalation recall on the golden set",
  },
  {
    id: "pii", group: "safety", name: "Raw personal data after pseudonymization (independent check)",
    section: "privacy", path: ["raw_pii_to_llm"], format: "count", target: { op: "<=", x: 0 },
    detail: (s) => {
      const c = count(get(s, "privacy", "complaints_checked"), "claim", "claims");
      const by = str(get(s, "privacy", "checker")) ? "a separate detector, not the one that masks" : null;
      return c ? `${c} checked${by ? ` by ${by}` : " after pseudonymization"}` : null;
    },
  },
  {
    id: "injection", group: "safety", name: "Prompt injections caught",
    section: "injection", path: ["detection_rate"], format: "pct", target: { op: ">=", x: 1 },
    detail: (s) => {
      const caught = n(get(s, "injection", "detected"));
      const total = n(get(s, "injection", "injection_cases"));
      if (total === undefined) return null;
      return caught === undefined ? `${num(total)} claims with hidden instructions` : `${num(caught)} of ${num(total)} claims with hidden instructions`;
    },
  },
  {
    id: "injection_effect", group: "safety", name: "Injections that moved a decision their way",
    section: "injection", path: ["decision_moved_toward_injection"], format: "count", target: { op: "<=", x: 0 },
    detail: (s) => {
      const twins = n(get(s, "injection", "twins_compared"));
      const changed = n(get(s, "injection", "decision_changed_by_injection"));
      const signed = n(get(s, "injection", "sign_off_added_by_injection"));
      if (twins === undefined) return null;
      const base = `Measured on ${num(twins)} claims, each run with and without the hidden instructions`;
      if (changed === undefined) return base;
      return `${base}: ${num(changed)} changed${signed !== undefined && changed ? `, ${num(signed)} of them by adding a sign-off` : ""}`;
    },
  },
  {
    id: "false_alarms", group: "safety", name: "False alarms on clean claims",
    section: "injection", path: ["false_positive_rate"], format: "pct", target: { op: "<=", x: 0.01 },
    detail: () => "Clean claims flagged as prompt injections",
  },
  {
    id: "f1", group: "classifier", name: "Scenario accuracy (macro-F1)",
    section: "ml", path: ["m1_classifier", "scenario", "macro_f1"], format: "score", target: { op: ">=", x: 0.9 },
    detail: (s) => {
      const c = count(get(s, "ml", "m1_classifier", "n_test"), "test claim", "test claims");
      return c ? `M1 classifier, ${c}` : "M1 classifier";
    },
  },
  {
    id: "ece", group: "classifier", name: "Calibration error (ECE)",
    section: "ml", path: ["m1_classifier", "scenario", "ece"], format: "score", target: { op: "<=", x: 0.05 },
    detail: () => "M1 classifier, lower is better",
  },
  {
    id: "time_decision", group: "runs", name: "Seconds to the refund decision (live runs, median)",
    section: "case_runs", path: ["by_llm_mode", "live", "to_refund_decision", "median_s"], format: "seconds",
    detail: (s) => spread(get(s, "case_runs", "by_llm_mode", "live", "to_refund_decision")),
  },
  {
    id: "time_sealed", group: "runs", name: "Seconds to the sealed file, without the wait for a person (live runs, median)",
    section: "case_runs", path: ["by_llm_mode", "live", "to_sealed_file_without_wait", "median_s"], format: "seconds",
    detail: (s) => spread(get(s, "case_runs", "by_llm_mode", "live", "to_sealed_file_without_wait")),
  },
];

function spread(v: unknown): string | null {
  const p90 = n(get(v, "p90_s"));
  const runs = n(get(v, "runs"));
  if (p90 === undefined && runs === undefined) return null;
  return [p90 !== undefined ? `p90 ${num(p90, 1)} s` : null, runs !== undefined ? `${num(runs)} stored runs` : null].filter(Boolean).join(" · ");
}

const meets = (v: number, t: Target) => (t.op === ">=" ? v >= t.x - 1e-9 : v <= t.x + 1e-9);

/**
 * Rates as percentages, scores with two decimals. Extra decimals when rounding would mislead:
 * 99.96% never shows as 100%, a small rate never shows as 0, and a miss never rounds onto its target.
 */
function valueText(v: number, format: Format, t?: Target): string {
  if (format === "seconds") return `${num(v, 1)} s`;
  if (!t) return num(v, 2);
  if (format === "count") return num(v, Number.isInteger(v) ? 0 : 2);
  const scale = format === "pct" ? 100 : 1;
  const x = v * scale;
  const pass = meets(v, t);
  const fmt = (d: number) =>
    new Intl.NumberFormat("en-US", { minimumFractionDigits: format === "score" ? Math.min(2, d) : 0, maximumFractionDigits: d, useGrouping: false }).format(x);
  const misleading = (s: string) => {
    const shown = Number(s);
    return (!pass && Math.abs(shown - t.x * scale) < 1e-9) || (format === "pct" && x < 100 && shown >= 100) || (x > 0 && shown === 0);
  };
  let d = format === "score" ? 2 : Math.abs(x - Math.round(x)) < 1e-9 ? 0 : 1;
  while (d < 4 && misleading(fmt(d))) d++;
  return format === "pct" ? `${fmt(d)}%` : fmt(d);
}

function targetText(t: Target | undefined, format: Format): string {
  if (!t) return "Measured";
  const v = format === "pct"
    ? `${new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(t.x * 100)}%`
    : format === "score" ? t.x.toFixed(2) : num(t.x);
  if ((t.op === ">=" && format === "pct" && t.x === 1) || (t.op === "<=" && t.x === 0)) return v;
  return `${t.op === ">=" ? "≥" : "≤"} ${v}`;
}

const clip = (s: string, max: number) => (s.length > max ? `${s.slice(0, max - 1).trimEnd()}…` : s);

/** Sections carry `{status, error}` when they failed ("eroare") or when the models aren't trained ("neantrenat"). */
function sectionProblem(section: unknown, key: string): string | null {
  if (!isObj(section)) return "Not in this report.";
  const status = typeof section.status === "string" ? section.status.toLowerCase() : null;
  if (!status) return null;
  if (key === "ml" && /neantrenat|untrained|not.?trained/.test(status)) {
    return "The models aren’t trained yet. Run uv run versoml train, then the evaluation.";
  }
  const error = str(section.error);
  return error ? `This part of the run failed: ${clip(error, 140)}` : "This part of the run failed.";
}

function buildMetric(spec: Spec, sections: Obj): Metric {
  const section = sections[spec.section];
  const value = n(get(section, ...spec.path)) ?? null;
  const problem = value === null ? sectionProblem(section, spec.section) ?? "No value in this report." : null;
  return {
    id: spec.id,
    group: spec.group,
    name: spec.name,
    detail: spec.detail?.(sections) ?? null,
    problem,
    value,
    outcome: value === null ? "none" : !spec.target ? "measured" : meets(value, spec.target) ? "pass" : "fail",
    valueText: value === null ? "" : valueText(value, spec.format, spec.target),
    targetText: targetText(spec.target, spec.format),
  };
}

// ---------------------------------------------------------------- failures

export interface Failure {
  id: string;
  set: "golden" | "generated";
  scenario: string | null;
  expected: string | null;
  got: string | null;
}

function failuresOf(sections: Obj): Failure[] {
  const out: Failure[] = [];
  for (const [key, set] of [["rules_golden", "golden"], ["rules_generated", "generated"]] as const) {
    const list = get(sections, key, "failures");
    if (!Array.isArray(list)) continue;
    for (const f of list) {
      if (isObj(f)) out.push({ id: str(f.id) ?? "", set, scenario: str(f.scenario), expected: str(f.expected), got: str(f.got) });
    }
  }
  return out;
}

// ---------------------------------------------------------------- the report

export type EvalModel =
  | { kind: "missing"; message: string | null }
  | {
    kind: "report";
    at: string | null;
    llmMode: string | null;
    simulated: boolean;
    metrics: Metric[];
    failures: Failure[];
    /** Golden set plus generated cases, when the report says. */
    cases: number | null;
    raw: unknown;
  };

/** The demo data's older shape, put onto the real sections. */
function fromLegacy(raw: Obj): Obj {
  const attacks = n(get(raw, "injection", "attacks"));
  const sections: Obj = {
    rules_golden: {
      cases: get(raw, "golden_set", "cases"),
      verdict_accuracy: get(raw, "rules", "consistency"),
      deadline_accuracy: get(raw, "rules", "deadlines_correct"),
      escalation_recall: get(raw, "escalation", "recall"),
    },
    rules_generated: { cases: get(raw, "golden_set", "generated_cases") },
    privacy: isObj(raw.privacy) ? { complaints_checked: raw.privacy.requests_scanned, raw_pii_to_llm: raw.privacy.raw_pii_to_llm } : undefined,
    // "succeeded" counts injections that changed something, not the ones detected: no detection rate is derived from it
    injection: attacks !== undefined ? { injection_cases: attacks, decision_changed_by_injection: get(raw, "injection", "succeeded") } : undefined,
    ml: isObj(raw.ml) && isObj(raw.ml.m1_classifier) ? { m1_classifier: { scenario: raw.ml.m1_classifier } } : undefined,
  };
  return Object.fromEntries(Object.entries(sections).filter(([, v]) => v !== undefined));
}

export function normalizeEval(raw: unknown): EvalModel {
  if (!isObj(raw)) return { kind: "missing", message: null };
  if (raw.status === "missing") return { kind: "missing", message: str(raw.message) };
  const real = isObj(raw.sections);
  const sections = real ? (raw.sections as Obj) : fromLegacy(raw);
  const golden = n(get(sections, "rules_golden", "cases"));
  const generated = n(get(sections, "rules_generated", "cases"));
  const source = str(raw.source) ?? "";
  return {
    kind: "report",
    at: str(raw.at) ?? str(raw.generated_at),
    llmMode: str(raw.llm_mode),
    simulated: !real || /mock|simulat|demo/i.test(source),
    metrics: SPECS.map((s) => buildMetric(s, sections)),
    failures: failuresOf(sections),
    cases: golden === undefined && generated === undefined ? null : (golden ?? 0) + (generated ?? 0),
    raw,
  };
}
