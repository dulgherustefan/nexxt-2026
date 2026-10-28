/** The groups the Rules page sorts the engine parameters into. */
export type ParamGroup = "refunds" | "deadlines" | "schemes" | "recovery" | "oversight" | "other";

/**
 * Labels for the parameter keys the demo data still uses. The backend keys are labeled in
 * pages/client/paramMeta.ts; any other key falls back to `humanizeParam`.
 */
export const PARAM_HELP: Record<string, { label: string; rule?: string; unit?: string; group?: ParamGroup }> = {
  plafon_aprobare_ron: { label: "Automatic refund cap", rule: "DSP-59", unit: "RON", group: "refunds" },
  prag_ore_risc_sla: { label: "At-risk alert", rule: "DSP-03", unit: "hours before the deadline", group: "deadlines" },
  autoritate_notificare_frauda: { label: "Authority notified of a fraud exception", rule: "DSP-05", group: "refunds" },
  prag_rubrica_recuperare: { label: "Recovery score threshold", rule: "DSP-06", unit: "points", group: "recovery" },
  dispute_count_scope: { label: "Disputes counted toward the limit of 35", rule: "DSP-26", group: "schemes" },
  curs_eur_ron: { label: "EUR to RON rate", rule: "PAY-05", unit: "RON per EUR", group: "refunds" },
};

/** "auto_refund_cap" → "Auto refund cap". */
export function humanizeParam(key: string): string {
  const s = key.replace(/[_.-]+/g, " ").trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}
