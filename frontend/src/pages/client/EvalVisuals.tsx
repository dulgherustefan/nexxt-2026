/** Evaluarea, ca imagine: inele pentru reguli, cifre mari pentru zid și confidențialitate, bare pentru ML. */
import type { ReactNode } from "react";
import { num } from "../../api/format";
import { cx } from "../../ui/kit";
import { Bar, Ring, type VizTone } from "../../ui/viz";
import { get, type Obj } from "./evalReport";

const n = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const p = (v: number | null) => (v === null ? "—" : `${num(v * 100, v >= 0.995 || v === 0 ? 0 : 1)}%`);

function Card({ title, children, sub, tone = "ink" }: { title: string; children: ReactNode; sub?: ReactNode; tone?: "ink" | "ok" | "danger" }) {
  return (
    <div className={cx("flex flex-col gap-2 rounded-xl border-2 bg-paper p-4", tone === "ok" ? "border-ok" : tone === "danger" ? "border-danger" : "border-ink")}>
      <p className="text-[0.8rem] font-bold tracking-wide text-muted">{title.toUpperCase()}</p>
      {children}
      {sub && <p className="text-[0.8667rem] text-ink-soft">{sub}</p>}
    </div>
  );
}

function RingStat({ value, label }: { value: number | null; label: string }) {
  const tone: VizTone = value === null ? "muted" : value >= 0.995 ? "ok" : value >= 0.9 ? "warn" : "danger";
  return (
    <div className="flex flex-col items-center gap-1">
      <Ring value={value ?? 0} size={92} stroke={10} tone={tone} label={label}>
        <span className="display text-[1.15rem] font-black tabular-nums">{p(value)}</span>
      </Ring>
      <span className="text-center text-[0.8rem] leading-tight font-semibold">{label}</span>
    </div>
  );
}

function Zero({ value, of, unit }: { value: number | null; of?: ReactNode; unit: string }) {
  return (
    <p className="flex items-baseline gap-2">
      <span className={cx("display text-[3rem] leading-none font-black tabular-nums", value === 0 ? "text-ok" : "text-danger")}>{value === null ? "—" : num(value)}</span>
      <span className="font-semibold">{unit}</span>
      {of && <span className="text-[0.8667rem] text-muted">{of}</span>}
    </p>
  );
}

export function EvalVisuals({ sections }: { sections: Obj }) {
  const g = (...path: string[]) => n(get(sections, ...path));
  const m5 = (k: string, m: string) => g("ml", "m5_mule", k, m);
  const bars = [
    { key: "rules_only", label: "Doar reguli (bază)", tone: "muted" as VizTone },
    { key: "gbdt_no_graph", label: "GBDT fără graf", tone: "ink" as VizTone },
    { key: "gbdt_graph", label: "GBDT pe graf (M5)", tone: "danger" as VizTone },
  ];
  const leaks = g("noninterference", "leaks");
  const pii = g("privacy", "raw_pii_to_llm");
  const changed = g("injection", "decision_changed_by_injection");
  return (
    <div className="mb-6 flex flex-col gap-4">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Card title="Reguli deterministe" tone={g("rules_golden", "verdict_accuracy") === 1 ? "ok" : "ink"}
          sub={`${g("rules_golden", "cases") ?? "—"} cazuri de aur + ${g("rules_generated", "cases") ?? "—"} generate; fiecare decizie are ID de regulă.`}>
          <div className="flex justify-around gap-2">
            <RingStat value={g("rules_golden", "verdict_accuracy")} label="verdict corect" />
            <RingStat value={g("rules_golden", "deadline_accuracy")} label="termen T+1 corect" />
            <RingStat value={g("rules_golden", "escalation_recall")} label="escaladări la om" />
          </div>
        </Card>
        <Card title="Zidul: neinterferență" tone={leaks === 0 ? "ok" : "danger"}
          sub={`${g("noninterference", "runs") ?? "—"} rulări cu zona AML goală vs plină; ${g("noninterference", "canaries_planted") ?? "—"} canary plantate, ${g("noninterference", "mismatches") ?? "—"} decizii schimbate.`}>
          <Zero value={leaks} unit="scurgeri peste zid" />
        </Card>
        <Card title="Confidențialitate" tone={pii === 0 ? "ok" : "danger"} sub={`${g("privacy", "complaints_checked") ?? "—"} reclamații verificate; ${g("privacy", "pseudonyms_created") ?? "—"} pseudonime create înainte de LLM.`}>
          <Zero value={pii} unit="date personale brute la LLM" />
        </Card>
        <Card title="Injecții și scrisori" tone={changed === 0 ? "ok" : "danger"}
          sub={`Injecții detectate ${p(g("injection", "detection_rate"))} din ${g("injection", "injection_cases") ?? "—"}; filtrul de scrisori a oprit ${g("letter_filter", "blocked") ?? "—"}/${g("letter_filter", "adversarial") ?? "—"} atacuri, ${g("letter_filter", "false_blocks") ?? "—"} blocări greșite.`}>
          <Zero value={changed} unit="decizii schimbate de injecții" />
        </Card>
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <Card title="M5 · contul-cărăuș: cât adaugă graful" sub={`${g("ml", "m5_mule", "n_accounts") ?? "—"} conturi sintetice, validare încrucișată pe grupuri (cărăușii aceluiași tipar stau în același fold).`}>
          <div className="grid gap-3 sm:grid-cols-2">
            {(["auc", "pr_auc"] as const).map((metric) => (
              <div key={metric}>
                <p className="mb-1.5 font-bold">{metric === "auc" ? "ROC-AUC" : "PR-AUC"}</p>
                <ul className="flex flex-col gap-2">
                  {bars.map((b) => {
                    const v = m5(b.key, metric);
                    return (
                      <li key={b.key}>
                        <div className="flex items-baseline justify-between text-[0.8667rem]"><span>{b.label}</span><span className="font-mono font-bold tabular-nums">{v === null ? "—" : v.toFixed(3).replace(".", ",")}</span></div>
                        <Bar value={v ?? 0} tone={b.tone} height={14} />
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
        </Card>
        <Card title="M1 · clasificarea reclamației și M2" sub="M1: TF-IDF + regresie logistică calibrată. M2: semnal pentru om, nu decizie.">
          <ul className="flex flex-col gap-2">
            {[
              ["M1 scenariu · macro-F1", g("ml", "m1_classifier", "scenario", "macro_f1"), "danger"],
              ["M1 tip de dispută · macro-F1", g("ml", "m1_classifier", "dispute_type", "macro_f1"), "ink"],
              ["M1 canal · macro-F1", g("ml", "m1_classifier", "channel", "macro_f1"), "ink"],
              ["M2 frauda clientului · AUC", g("ml", "m2_client_fraud", "held_out", "auc"), "ink"],
            ].map(([label, v, tone]) => (
              <li key={String(label)}>
                <div className="flex items-baseline justify-between text-[0.8667rem]"><span>{label as string}</span><span className="font-mono font-bold tabular-nums">{v === null ? "—" : (v as number).toFixed(3).replace(".", ",")}</span></div>
                <Bar value={(v as number | null) ?? 0} tone={tone as VizTone} height={10} />
              </li>
            ))}
          </ul>
          <p className="text-[0.8667rem]">Calibrare M1 (ECE pe scenariu): <span className="font-mono font-bold">{g("ml", "m1_classifier", "scenario", "ece")?.toFixed(3).replace(".", ",") ?? "—"}</span></p>
        </Card>
      </div>
    </div>
  );
}
