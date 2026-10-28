/** Piesele vizuale ale camerei de pistă: tipologiile ca jetoane cu explicație și ceasurile AML ca bare. */
import { useState } from "react";
import { money } from "../../api/format";
import type { AgentEvent, Deadline, TypologyHit } from "../../api/types";
import { cx, IdTag, useNowTick } from "../../ui/kit";
import { Bar, slaTone, TONE_STROKE } from "../../ui/viz";
import { typologyLabel } from "./aml";

const TYPOLOGY_PLAIN: Record<string, string> = {
  fan_in: "Mulți plătitori diferiți trimit bani în același cont, în puține zile.",
  fan_out: "Banii dintr-un cont pleacă rapid spre mulți beneficiari.",
  rapid_pass_through: "Banii intră și pleacă mai departe în câteva ore: contul e doar un tranzit.",
  crypto_cash_out: "Ieșirile merg spre exchange-uri cripto sau numerar, greu de urmărit.",
  structuring: "Sume ținute chiar sub praguri rotunde, ca să nu declanșeze raportarea.",
  cycle: "Banii se întorc în cerc la contul de plecare.",
};

export function TypologyChips({ detail, names }: { detail?: TypologyHit[] | null; names?: string[] | null }) {
  const list: TypologyHit[] = Array.isArray(detail) && detail.length ? detail : (names ?? []).map((n) => ({ typology: n }));
  const [open, setOpen] = useState<string | null>(list[0]?.typology ?? list[0]?.name ?? null);
  if (!list.length) return null;
  const cur = list.find((t) => (t.typology ?? t.name) === open) ?? null;
  return (
    <section aria-label="Tipologii">
      <div className="flex flex-wrap gap-1.5">
        {list.map((t) => {
          const k = String(t.typology ?? t.name ?? "");
          return (
            <button key={k} type="button" onClick={() => setOpen(k)} aria-pressed={open === k}
              className={cx("inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-[0.8667rem] font-medium transition-colors", open === k ? "border-ink bg-ink text-paper" : "border-line-strong bg-paper hover:bg-hover")}>
              {typologyLabel(k)}
              {t.rule_id && <span className="font-mono text-[0.7rem] opacity-70">{t.rule_id}</span>}
            </button>
          );
        })}
      </div>
      {cur && (
        <div className="mt-3 max-w-[72ch] rounded-md bg-canvas px-4 py-3 text-[0.9333rem] animate-enter">
          <p className="font-semibold">{TYPOLOGY_PLAIN[String(cur.typology ?? cur.name)] ?? typologyLabel(String(cur.typology ?? cur.name))}</p>
          {cur.explanation && <p className="mt-1 text-ink-soft">{cur.explanation}</p>}
          <p className="mt-1.5 flex flex-wrap items-center gap-2 text-[0.8rem] text-muted">
            {typeof cur.amount === "number" && <span className="font-semibold text-ink tabular-nums">{money(cur.amount)}</span>}
            {Array.isArray(cur.accounts) && <span>{cur.accounts.length} conturi implicate</span>}
            {cur.rule_id && <IdTag>{cur.rule_id}</IdTag>}
          </p>
        </div>
      )}
    </section>
  );
}

function hoursOf(name: string): number | null {
  const m = name.match(/(\d+)\s*h/);
  return m ? Number(m[1]) : null;
}

/** Ceasurile AML (24 h / 48 h / 72 h) ca bare care se golesc. Începutul ferestrei: prima activitate a pistei. */
export function ClockBars({ clocks, events }: { clocks: Deadline[] | null | undefined; events: AgentEvent[] }) {
  const now = useNowTick(1000);
  const list = (Array.isArray(clocks) ? clocks : []).filter((c) => c?.due_at).slice().sort((a, b) => Date.parse(a.due_at) - Date.parse(b.due_at));
  const startTs = events.map((e) => Date.parse(e.ts)).filter(Number.isFinite).sort((a, b) => a - b)[0];
  return (
    <section aria-label="Ceasurile AML" className="max-w-[40rem]">
      {!list.length ? (
        <p className="text-[0.9333rem] text-muted">Pornesc când regulile AML propun un raport (RTS).</p>
      ) : (
        <ul className="flex flex-col gap-4">
          {list.map((c, i) => {
            const end = Date.parse(c.due_at);
            const begin = Number.isFinite(startTs) && startTs < end ? startTs : end - (hoursOf(c.name) ?? 24) * 3_600_000;
            const left = end - now;
            const frac = Math.max(0, Math.min(1, left / (end - begin)));
            const tone = slaTone(frac);
            const h = Math.floor(Math.max(0, left) / 3_600_000);
            const m = Math.floor((Math.max(0, left) % 3_600_000) / 60_000);
            return (
              <li key={`${c.rule_id}-${i}`}>
                <div className="flex items-baseline justify-between gap-3">
                  <span className="min-w-0 text-[0.9333rem] font-semibold">{c.name}</span>
                  <span className="shrink-0 text-[0.9333rem] font-semibold tabular-nums" style={{ color: TONE_STROKE[tone] }}>
                    {left <= 0 ? "expirat" : h >= 48 ? `${Math.floor(h / 24)} z ${h % 24} h` : `${h} h ${String(m).padStart(2, "0")}`}
                  </span>
                </div>
                <Bar value={frac} tone={tone} height={6} className="mt-1.5" />
                <p className="mt-1 flex flex-wrap items-center gap-2 text-[0.8rem] text-muted"><IdTag>{c.rule_id}</IdTag>{c.basis}</p>
              </li>
            );
          })}
        </ul>
      )}
      <p className="mt-3 text-[0.8rem] text-muted">Termenele sunt estimate de regulile AML; ce se întâmplă cu contul decide analistul.</p>
    </section>
  );
}
