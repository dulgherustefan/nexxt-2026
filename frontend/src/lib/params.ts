/** Etichete pentru parametrii [U] cunoscuți. Cheile necunoscute se afișează „umanizat". */
export const PARAM_HELP: Record<string, { label: string; rule?: string; unit?: string }> = {
  plafon_aprobare_ron: { label: "Plafon de rambursare automată", rule: "DSP-59", unit: "lei" },
  prag_ore_risc_sla: { label: "Alertă de termen, cu atâtea ore înainte", rule: "DSP-03", unit: "ore" },
  autoritate_notificare_frauda: { label: "Autoritatea notificată la excepție", rule: "DSP-05" },
  prag_rubrica_recuperare: { label: "Pragul rubricii pentru recuperare", rule: "DSP-06", unit: "puncte" },
  dispute_count_scope: { label: "Ce dispute se numără la limita de 35", rule: "DSP-26" },
  curs_eur_ron: { label: "Curs EUR/RON pentru plafonul de 30 EUR", rule: "PAY-05", unit: "lei/EUR" },
};

export function humanizeParam(key: string): string {
  const s = key.replace(/[_.-]+/g, " ").trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}
