/**
 * Labels for the rules engine parameters (backend: versoml/shared/rules/params_default.yaml).
 * The wording follows the descriptions there and adds no thresholds of its own. Keys not listed
 * here fall back to the demo-data labels in lib/params.ts, then to `humanizeParam`.
 */
import { humanizeParam, PARAM_HELP, type ParamGroup } from "../../lib/params";

export type { ParamGroup };

export const PARAM_GROUPS: Array<{ id: ParamGroup; title: string }> = [
  { id: "refunds", title: "Refunds" },
  { id: "deadlines", title: "Deadlines and alerts" },
  { id: "schemes", title: "Card schemes" },
  { id: "recovery", title: "Recalls and recovery" },
  { id: "oversight", title: "Human review" },
  { id: "other", title: "Other" },
];

export interface ParamMeta {
  label: string;
  group?: ParamGroup;
  /** Shown after a number input ("hours"), or before it when `unitBefore` is set ("RON"). */
  unit?: string;
  unitBefore?: boolean;
  /** A format hint under text and list inputs. */
  format?: string;
  help?: string;
  choices?: string[];
  choiceLabels?: Record<string, string>;
  nullable?: boolean;
  /** What an empty value means, in words ("Off", "Not set"). */
  emptyLabel?: string;
  /** The expected type when the current value is `null` and can't tell us. */
  type?: "number" | "text";
  /** Locked in the backend: why, in words. */
  locked?: string;
  /** A rule that uses the key, for keys the catalog doesn't list. */
  rule?: string;
}

export const PARAM_META: Record<string, ParamMeta> = {
  // refunds
  auto_refund_cap_ron: {
    group: "refunds", label: "Automatic refund cap", unit: "RON", unitBefore: true,
    help: "Above this amount, a person approves the refund. It still goes out by the end of the next business day.",
  },
  client_fraud_signal_threshold: {
    group: "refunds", label: "Customer fraud signal threshold",
    help: "An M2 score from 0 to 1. At or above it, a person reviews the case. The score never holds back or refuses a refund.",
  },
  prior_disputes_signal_threshold: {
    group: "refunds", label: "Repeat disputes that need a person", unit: "in 12 months",
    help: "Customers with this many disputes in the last 12 months go to a person.",
  },
  eur_ron_rate: {
    group: "refunds", label: "EUR to RON rate", unit: "RON per EUR",
    help: "Converts the EUR 30 liability cap into lei. 5.00 is a test value.",
  },
  competent_authority: {
    group: "refunds", label: "Authority notified of a fraud exception",
    choices: ["BNR", "ANPC"], choiceLabels: { BNR: "BNR, National Bank of Romania", ANPC: "ANPC, consumer protection" },
    nullable: true, emptyLabel: "Not set",
    help: "When the bank suspects the customer of fraud and holds the refund, it tells this authority in writing (art. 173).",
  },
  undue_delay_days: {
    group: "refunds", label: "Late report threshold", unit: "days", nullable: true, type: "number", emptyLabel: "Off",
    help: "Reports made later than this go to a person (“without undue delay”, art. 169). The refund isn’t delayed. Leave it empty to turn it off.",
  },
  // deadlines and alerts
  refund_end_of_day: {
    group: "deadlines", label: "End of the business day", format: "HH:MM:SS, for example 23:59:59",
    help: "The refund is due by this time on the next business day.",
  },
  refund_anchor_mode: {
    group: "deadlines", label: "Refund deadline starts from",
    choices: ["cea_mai_devreme", "notificare"],
    choiceLabels: { cea_mai_devreme: "Earlier of detection or report", notificare: "The customer’s report" },
    help: "Detection means the bank noticed the fraud before the customer reported it.",
  },
  refund_sla_alert_hours: {
    group: "deadlines", label: "At-risk alert", unit: "hours before the deadline",
    help: "A case is marked at risk this long before its refund deadline.",
  },
  bank_closure_days: {
    group: "deadlines", label: "Extra bank closure days", format: "Dates as YYYY-MM-DD, separated by commas",
    help: "Days the bank is closed on top of public holidays, for example 2026-12-31.",
  },
  complaint_alert_lead_business_days: {
    group: "deadlines", label: "Holding reply alert", unit: "business days before day 15",
    help: "Complaints get an answer within 15 business days. The alert for a holding reply appears this early.",
  },
  // card schemes
  default_card_scheme: {
    group: "schemes", label: "Card scheme when the data doesn’t say",
    choices: ["visa", "mastercard"], choiceLabels: { visa: "Visa", mastercard: "Mastercard" },
    help: "Demo Bank cards are Visa.",
  },
  visa_other_open_days: {
    group: "schemes", label: "Visa dispute window, other conditions", unit: "days",
    help: "For Visa conditions whose own deadline isn’t in the notes.",
  },
  visa_131_wait_anchor: {
    group: "schemes", label: "Visa 13.1 wait starts from",
    choices: ["processing_date", "transaction_date"],
    choiceLabels: { processing_date: "Processing date", transaction_date: "Transaction date" },
    help: "The start of the 15-day wait before a Visa 13.1 dispute.",
  },
  fraud_report_deadline_mode: {
    group: "schemes", label: "Visa fraud report deadline",
    choices: ["max", "after_day_60"],
    choiceLabels: { max: "The later of the two dates", after_day_60: "30 days from the report, if after day 60" },
    nullable: true, emptyLabel: "Not set: earlier date, flagged",
    help: "Visa gives 60 days from the transaction or 30 days from the report. When this isn’t set, the rules work out both, use the earlier date and flag the case to a person.",
  },
  dispute_count_scope: {
    group: "schemes", label: "Disputes counted toward the limit of 35",
    choices: ["toate", "frauda"], choiceLabels: { toate: "All disputes", frauda: "Fraud disputes only" },
    help: "Visa 10.4 is invalid above 35 disputes in 120 days.",
  },
  scheme_alert_lead_days: {
    group: "schemes", label: "Scheme deadline alert", unit: "days before the deadline",
  },
  mc_chargeback_open_days: {
    group: "schemes", label: "Mastercard chargeback window", unit: "days",
    help: "About 120 days. Sources disagree.",
  },
  // recalls and recovery
  sct_recall_answer_banking_days: {
    group: "recovery", label: "Answer time for a SEPA recall", unit: "banking days",
    help: "How long the receiving bank has to answer a recall of a SEPA transfer.",
  },
  ron_recall_answer_banking_days: {
    group: "recovery", label: "Answer time for a RON recall", unit: "banking days",
    nullable: true, type: "number", emptyLabel: "No deadline",
    help: "The procedure isn’t public. Leave it empty for no deadline.",
  },
  recall_window_months: {
    group: "recovery", label: "Fraud recall window", unit: "months after the payment",
    help: "After this, the rules stop proposing a fraud recall.",
  },
  banking_calendar: {
    group: "recovery", label: "Banking days for recalls",
    choices: ["ro", "target2"], choiceLabels: { ro: "Romanian business days", target2: "TARGET2 calendar" },
  },
  same_bank_codes: {
    group: "recovery", label: "Bank codes treated as internal", format: "IBAN bank codes, separated by commas",
    help: "Payees at these banks get an internal block and a return request. BDEM is Demo Bank.",
  },
  // human review
  require_human_for_unfavourable: {
    group: "oversight", label: "A person signs every adverse decision",
    locked: "Locked. No adverse decision can be fully automated (GDPR art. 22, rule DP-02).",
  },
};

const ORDER = Object.keys(PARAM_META);

/** Position of a key in the list above; unknown keys go last. */
export function paramOrder(key: string): number {
  const i = ORDER.indexOf(key);
  return i === -1 ? ORDER.length : i;
}

export function paramMeta(key: string): ParamMeta {
  const meta = PARAM_META[key];
  if (meta) return meta;
  const legacy = PARAM_HELP[key];
  return {
    label: legacy?.label ?? humanizeParam(key),
    unit: legacy?.unit,
    unitBefore: legacy?.unit === "RON",
    rule: legacy?.rule,
    group: legacy?.group ?? "other",
  };
}
