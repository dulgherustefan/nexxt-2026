/**
 * Etichete pentru parametrii motorului de reguli din backend (`versoml/shared/rules/params_default.yaml`).
 * Textele și opțiunile vin din descrierile de acolo; nu adaugă praguri noi. Cheile necunoscute
 * folosesc `PARAM_HELP` (lib/params.ts), apoi `humanizeParam`.
 */
import { humanizeParam, PARAM_HELP } from "../../lib/params";

export interface ParamMeta {
  label: string;
  unit?: string;
  help?: string;
  choices?: string[];
  choiceLabels?: Record<string, string>;
  nullable?: boolean;
  /** Tipul așteptat când valoarea curentă e `null` (nu se poate deduce). */
  type?: "number" | "text";
  /** Parametru blocat în backend: motivul, în cuvinte. */
  locked?: string;
  rule?: string;
}

export const PARAM_META: Record<string, ParamMeta> = {
  auto_refund_cap_ron: { label: "Plafon de rambursare automată", unit: "lei", help: "Peste plafon aprobă un om, tot în termenul T+1." },
  client_fraud_signal_threshold: { label: "Prag pentru semnalul de fraudă a clientului (M2)", unit: "scor 0–1", help: "Peste prag cazul merge la om; scorul nu reține și nu refuză rambursarea." },
  prior_disputes_signal_threshold: { label: "Contestații anterioare care trimit cazul la om", unit: "în 12 luni" },
  eur_ron_rate: { label: "Curs EUR/RON pentru plafoanele în euro", unit: "lei/EUR", help: "5,00 e valoarea fictivă de test din docs/context/11." },
  refund_end_of_day: { label: "Ora „sfârșitului zilei” pentru T+1", unit: "HH:MM:SS" },
  bank_closure_days: { label: "Zile în care banca e închisă suplimentar", unit: "date ISO, separate prin virgulă", help: "Pe lângă sărbătorile legale, ex. 2026-12-31." },
  refund_anchor_mode: {
    label: "De când curge termenul T+1",
    choices: ["cea_mai_devreme", "notificare"],
    choiceLabels: { cea_mai_devreme: "Prima: constatare sau notificare", notificare: "Notificarea clientului" },
  },
  refund_sla_alert_hours: { label: "Alertă de termen T+1, cu atâtea ore înainte", unit: "ore" },
  undue_delay_days: { label: "Prag pentru „fără întârziere nejustificată”", unit: "zile", nullable: true, type: "number", help: "Gol = neaplicat. Depășirea trimite cazul la om; nu amână rambursarea." },
  competent_authority: { label: "Autoritatea notificată la excepție", choices: ["BNR", "ANPC"], nullable: true },
  complaint_alert_lead_business_days: { label: "Alertă înainte de termenul de 15 zile", unit: "zile lucrătoare" },
  default_card_scheme: { label: "Schema de card presupusă", choices: ["visa", "mastercard"], choiceLabels: { visa: "Visa", mastercard: "Mastercard" } },
  visa_other_open_days: { label: "Termen de dispută Visa, alte condiții", unit: "zile" },
  visa_131_wait_anchor: {
    label: "Ancora așteptării de 15 zile la Visa 13.1",
    choices: ["processing_date", "transaction_date"],
    choiceLabels: { processing_date: "Data procesării", transaction_date: "Data tranzacției" },
  },
  fraud_report_deadline_mode: {
    label: "Lectura termenului de raport de fraudă Visa",
    choices: ["max", "after_day_60"],
    nullable: true,
    help: "Gol = se calculează ambele lecturi și se ia data mai devreme.",
  },
  dispute_count_scope: { label: "Ce dispute se numără la limita de 35", choices: ["toate", "frauda"], choiceLabels: { toate: "Toate disputele", frauda: "Doar cele de fraudă" } },
  scheme_alert_lead_days: { label: "Alertă înainte de un termen de schemă", unit: "zile" },
  mc_chargeback_open_days: { label: "Termen de chargeback Mastercard", unit: "zile" },
  sct_recall_answer_banking_days: { label: "Răspuns la rechemarea unui SCT", unit: "zile bancare" },
  ron_recall_answer_banking_days: { label: "Răspuns la o rechemare în lei", unit: "zile bancare", nullable: true, type: "number", help: "Procedura nu e publică; gol = fără termen." },
  recall_window_months: { label: "Fereastra pentru rechemare pe motiv de fraudă", unit: "luni" },
  banking_calendar: { label: "Calendarul zilelor bancare la rechemare", choices: ["ro", "target2"], choiceLabels: { ro: "Zile lucrătoare RO", target2: "TARGET2" } },
  same_bank_codes: { label: "Coduri de bancă tratate ca beneficiar intern", unit: "coduri din IBAN, separate prin virgulă" },
  aml_mule_score_threshold: { label: "Prag de cont-cărăuș (M5) pentru propunerea de RTS", unit: "scor 0–1", help: "Analistul decide; regula doar propune." },
  aml_min_linked_victims: { label: "Victime legate de același cont pentru propunerea de RTS", unit: "victime" },
  aml_prohibited_features: { label: "Trăsături personale interzise în scorurile AML", unit: "valori separate prin virgulă" },
  require_human_for_unfavourable: { label: "Semnătura unui om pe orice decizie defavorabilă", locked: "Blocat: nicio decizie defavorabilă exclusiv automată (DP-02, GDPR art. 22)." },
};

export function paramMeta(key: string): ParamMeta {
  const help = PARAM_HELP[key];
  const meta = PARAM_META[key];
  return {
    ...meta,
    label: help?.label ?? meta?.label ?? humanizeParam(key),
    unit: help?.unit ?? meta?.unit,
    rule: help?.rule ?? meta?.rule,
  };
}
