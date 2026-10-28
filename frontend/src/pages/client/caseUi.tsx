import { ChevronDown, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { money, scenarioLabel as baseScenarioLabel } from "../../api/format";
import type { AgentEvent, Decision, Money, PipelineNode } from "../../api/types";
import { matchNode, normalizeStatus, STAGE_BY_ID } from "../../lib/pipeline";
import { Button, cx, Dot, StepIcon, STEP_STATUS_LABEL, type Tone, useNowTick } from "../../ui/kit";

// ---------------------------------------------------------------- un singur set de stări, în toată aplicația

export interface StatusView {
  label: string;
  tone: Tone;
  live?: boolean;
  group: "you" | "running" | "closed";
}

export function caseStatus(status: string | null | undefined, requiresHuman = false): StatusView {
  switch (status) {
    case "ASTEAPTA_APROBARE":
      return { label: "Așteaptă semnătura ta", tone: "now", group: "you" };
    case "NOU":
      return { label: "Nou", tone: "neutral", group: "running" };
    case "IN_ANALIZA":
      return { label: "În analiză", tone: "now", live: true, group: "running" };
    case "RAMBURSAT":
      return { label: "Rambursat", tone: "ok", group: "closed" };
    case "TRASEU_APP":
      return { label: "Recuperare (plată autorizată)", tone: "neutral", group: requiresHuman ? "you" : "closed" };
    case "RESPINS":
      return { label: "Respins", tone: "neutral", group: "closed" };
    case "EXCEPTIE":
      return { label: "Excepție semnată", tone: "danger", group: "closed" };
    case "INCHIS":
      return { label: "Închis", tone: "neutral", group: "closed" };
    case "EROARE":
      return { label: "Eroare: repornește cazul", tone: "danger", group: "you" };
    default:
      return { label: status ?? "—", tone: "neutral", group: "running" };
  }
}

export function StatusLine({ status, requiresHuman }: { status?: string | null; requiresHuman?: boolean }) {
  const s = caseStatus(status, requiresHuman);
  return (
    <span className="inline-flex items-center gap-2 whitespace-nowrap">
      <Dot tone={s.tone} live={s.live} />
      {s.label}
    </span>
  );
}

export function scenarioLabel(s: string | null | undefined): string {
  if (s === "demo_t1") return "Link fals de curier (demo)";
  if (s === "demo_t1_victima2") return "„Cont sigur” (demo)";
  return baseScenarioLabel(s);
}

export function exactTime(v: string | null | undefined): string {
  if (!v) return "—";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return "—";
  return new Intl.DateTimeFormat("ro-RO", { timeZone: "Europe/Bucharest", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }).format(d);
}

// ---------------------------------------------------------------- decizia, într-o propoziție

/** `after` = ce s-a întâmplat după decizie (starea cazului, răspunsul omului), ca propoziția să treacă la trecut. */
export function verdictSentence(
  d: Decision | undefined,
  amount: Money | null | undefined,
  after?: { status?: string; action?: string; approver?: string },
): { title: string; detail: string; tone: Tone } {
  const sum = money(amount ?? d?.amount ?? null);
  const until = d?.deadline ? `până pe ${exactTime(d.deadline)}` : "în termen";
  const who = after?.approver ?? "un om";
  const Who = who.charAt(0).toUpperCase() + who.slice(1);
  if (d && after?.status === "RAMBURSAT") {
    return {
      title: `Rambursarea de ${sum} a fost emisă.`,
      detail: d.decision === "RAMBURSEAZA" ? "Automat: sub plafon și fără semnale de risc."
        : d.decision === "RAMBURSEAZA_CU_APROBARE" ? `Instrucțiunea a fost aprobată de ${who}, în termen.`
          : `${Who} nu a confirmat decizia defavorabilă, așa că rambursăm în termen.`,
      tone: "ok",
    };
  }
  if (d?.decision === "RAMBURSEAZA_CU_APROBARE" && after?.action === "reject") {
    return { title: "Rambursarea nu a fost aprobată.", detail: `${Who} a refuzat instrucțiunea. Cazul rămâne în analiză, iar termenul T+1 curge în continuare.`, tone: "danger" };
  }
  if (d?.decision === "RESPINGE_TARDIV" && after?.status === "RESPINS") {
    return { title: "Contestația a fost respinsă: a venit după 13 luni.", detail: `Termenul legal de notificare a expirat (art. 169). A semnat ${who}.`, tone: "neutral" };
  }
  if (d?.decision === "EXCEPTIE_FRAUDA_CLIENT" && after?.status === "EXCEPTIE") {
    return { title: "Excepția a fost confirmată: nu rambursăm acum.", detail: `Suspiciune de fraudă a clientului, comunicată autorității. A semnat ${who}.`, tone: "danger" };
  }
  switch (d?.decision) {
    case "RAMBURSEAZA":
      return { title: `Rambursăm ${sum} ${until}.`, detail: "Sub plafonul de rambursare automată, fără semnale de risc: motorul de reguli emite instrucțiunea fără semnătură.", tone: "ok" };
    case "RAMBURSEAZA_CU_APROBARE":
      return { title: `Rambursăm ${sum} ${until}, cu semnătura ta.`, detail: "Legea cere rambursarea; suma sau un semnal de risc cer ca un om să confirme instrucțiunea.", tone: "now" };
    case "NU_SE_APLICA_T1":
      return { title: "Plata a fost autorizată de client: nu se rambursează la T+1.", detail: "Clientul a fost păcălit să aprobe singur plata (APP). Pornim rechemarea și îl ajutăm să recupereze banii.", tone: "neutral" };
    case "RESPINGE_TARDIV":
      return { title: "Contestația a venit după 13 luni: o respingem.", detail: "Termenul legal de notificare a expirat (art. 169). O decizie defavorabilă se semnează de un om.", tone: "danger" };
    case "EXCEPTIE_FRAUDA_CLIENT":
      return { title: "Excepție: suspiciune de fraudă a clientului, comunicată autorității.", detail: "Singura excepție de la rambursarea la T+1 (C-70/25). Se semnează de un om.", tone: "danger" };
    case "INFORMATII_SUPLIMENTARE":
      return { title: "Ne lipsesc informații pentru o decizie.", detail: "Cerem clientului datele care lipsesc; termenul legal curge în continuare.", tone: "neutral" };
    default:
      return { title: "Agenții lucrează.", detail: "Decizia apare aici imediat ce motorul de reguli termină.", tone: "neutral" };
  }
}

// ---------------------------------------------------------------- lista de pași, cu bare pe axa de timp comună

const PHASES: Array<{ label: string; ids: string[] }> = [
  { label: "Intrare", ids: ["receptor", "clasificator", "ceasornicar"] },
  { label: "Probe, în paralel", ids: ["colector_tranzactie", "colector_sca", "colector_dispozitiv", "colector_domeniu"] },
  { label: "Decizie", ids: ["motor_reguli", "outbox_aml", "rambursare"] },
  { label: "Recuperare, în paralel", ids: ["procuror", "avocat", "cantaritor", "recuperare"] },
  { label: "Răspuns", ids: ["redactor", "filtru_zid", "sigiliu"] },
];

export function modelName(m: string | null | undefined): string {
  const s = (m ?? "").toLowerCase();
  if (s.includes("opus")) return "Opus";
  if (s.includes("sonnet")) return "Sonnet";
  if (s.includes("haiku")) return "Haiku";
  if (s === "ml") return "ML";
  return "Reguli";
}

interface StepRow {
  id: string;
  label: string;
  model: string;
  status: string;
  summary?: string;
  hint?: string;
  start?: number;
  end?: number;
}

function ms(v: string | null | undefined): number | undefined {
  if (!v) return undefined;
  const t = new Date(v).getTime();
  return Number.isNaN(t) ? undefined : t;
}

/** Starea fiecărui pas: întâi ce a salvat serverul, apoi ce au adus evenimentele live. */
export function useStepRows(nodes: PipelineNode[] | undefined, events: AgentEvent[]): StepRow[] {
  return useMemo(() => {
    const rows = new Map<string, StepRow>();
    for (const n of nodes ?? []) {
      rows.set(n.id, {
        // eticheta din interfață are prioritate: e scrisă pentru operator, nu pentru graf
        id: n.id, label: STAGE_BY_ID[n.id]?.label ?? n.label, model: modelName(n.model), status: normalizeStatus(n.status),
        summary: n.summary, hint: n.hint, start: ms(n.started_at), end: ms(n.finished_at),
      });
    }
    let runStarted = false;
    for (const e of events) {
      if (e.type === "RUN_STARTED") {
        runStarted = true;
        for (const r of rows.values()) Object.assign(r, { status: "idle", start: undefined, end: undefined, summary: undefined });
        continue;
      }
      const id = matchNode([...rows.values()].map((r) => ({ id: r.id, label: r.label, agent: undefined })), e);
      if (!id) continue;
      const r = rows.get(id)!;
      const t = ms(e.ts);
      if (e.type === "STEP_STARTED") {
        r.status = r.status === "done" ? r.status : "running";
        r.start = r.start ?? t;
      } else if (e.type === "STEP_FINISHED") {
        const declared = typeof e.data?.status === "string" ? normalizeStatus(e.data.status as string) : "done";
        r.status = declared === "idle" ? "done" : declared;
        r.end = t;
        if (e.message) r.summary = e.message;
      } else if (e.type === "CUSTOM" && e.name === "interrupt") {
        r.status = "waiting";
      } else if (e.type === "CUSTOM" && (e.name === "policy_denied" || e.name === "wall_block")) {
        r.status = "blocked";
      }
    }
    void runStarted;
    return [...rows.values()];
  }, [nodes, events]);
}

function secondsText(ms0: number): string {
  const s = ms0 / 1000;
  return s < 10 ? `${s.toFixed(1).replace(".", ",")} s` : `${Math.round(s)} s`;
}

/** `settled`: rularea s-a încheiat, deci pașii care n-au pornit deloc nu se mai aplică acestui caz. */
export function StepList({ rows: input, title = "Agenții", settled = false }: { rows: StepRow[]; title?: string; settled?: boolean }) {
  const rows = settled ? input.map((r) => (r.status === "idle" ? { ...r, status: "skipped" } : r)) : input;
  const now = useNowTick(500);
  const [open, setOpen] = useState(true);
  const starts = rows.map((r) => r.start).filter((x): x is number => typeof x === "number");
  const t0 = starts.length ? Math.min(...starts) : undefined;
  const ends = rows.map((r) => (r.status === "running" ? now : r.end)).filter((x): x is number => typeof x === "number");
  const t1 = ends.length ? Math.max(...ends) : undefined;
  const span = t0 && t1 && t1 > t0 ? t1 - t0 : 1;
  const done = rows.filter((r) => ["done", "skipped"].includes(r.status)).length;
  const running = rows.some((r) => r.status === "running");
  const waiting = rows.find((r) => r.status === "waiting");
  const stopped = rows.filter((r) => r.status === "blocked" || r.status === "error");
  const total = t0 && t1 ? secondsText(t1 - t0) : null;
  // un pas blocat sau eșuat încheie și el rularea, dar lista rămâne deschisă ca să se vadă care
  const finished = rows.length > 0 && !running && !waiting && done + stopped.length === rows.length;
  const byId = new Map(rows.map((r) => [r.id, r]));
  const phases = PHASES.map((p) => ({ ...p, rows: p.ids.map((id) => byId.get(id)).filter(Boolean) as StepRow[] }))
    .filter((p) => p.rows.length);
  const known = new Set(PHASES.flatMap((p) => p.ids));
  const extra = rows.filter((r) => !known.has(r.id));
  if (extra.length) phases.push({ label: "Alți pași", ids: extra.map((r) => r.id), rows: extra });

  useEffect(() => {
    if (finished && !stopped.length) setOpen(false);
  }, [finished, stopped.length]);

  return (
    <section className="rounded-lg border border-line bg-paper" aria-label="Progresul agenților">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 border-b border-line px-4 py-3 text-left">
        <span>
          <span className="font-semibold">{title}</span>
          <span className="ml-2 tabular-nums text-muted">
            {finished ? `${rows.length} pași${total ? ` în ${total}` : ""}` : `${done}/${rows.length} gata${total ? ` · ${total}` : ""}`}
          </span>
        </span>
        <span className="flex items-center gap-2 text-[0.8667rem] text-muted">
          {waiting ? <><Dot tone="now" /> așteaptă semnătura</>
            : running ? <><Dot tone="now" live /> lucrează</>
              : stopped.length ? <><Dot tone="danger" /> {stopped.length === 1 ? `${stopped[0].label}: ${STEP_STATUS_LABEL[stopped[0].status] ?? "oprit"}` : `${stopped.length} pași opriți`}</>
                : null}
          <ChevronDown aria-hidden className={cx("size-4 transition-transform", open && "rotate-180")} />
        </span>
      </button>
      {open && (
        <ol className="px-4 py-2">
          {phases.map((phase) => (
            <li key={phase.label} className="py-2">
              <p className="pb-1 text-[0.8rem] font-semibold text-muted">{phase.label}</p>
              <ul className="flex flex-col">
                {phase.rows.map((r) => {
                  const end = r.status === "running" ? now : r.end;
                  const left = t0 && r.start ? ((r.start - t0) / span) * 100 : 0;
                  const width = r.start && end ? Math.max(((end - r.start) / span) * 100, 1.5) : 0;
                  return (
                    <li key={r.id} className="grid grid-cols-[1rem_minmax(0,1fr)_4.5rem] items-start gap-x-2.5 py-1.5" title={r.hint}>
                      <span className="mt-0.5"><StepIcon status={r.status} /></span>
                      <div className="min-w-0">
                        <p className="flex items-baseline gap-2">
                          <span className={cx("font-medium", r.status === "idle" && "text-muted")}>{r.label}</span>
                          <span className="text-[0.8rem] text-subtle">{r.model}</span>
                        </p>
                        <div className="mt-1 h-1.5 rounded-full bg-hover" aria-hidden>
                          {width > 0 && (
                            <div className={cx("h-1.5 rounded-full", r.status === "running" ? "bg-yellow ring-1 ring-ink/30" : r.status === "waiting" ? "bg-yellow" : r.status === "blocked" || r.status === "error" ? "bg-danger" : "bg-ink")}
                              style={{ marginLeft: `${Math.min(left, 98)}%`, width: `${Math.min(width, 100 - Math.min(left, 98))}%` }} />
                          )}
                        </div>
                        {r.summary && r.status !== "idle" && (
                          <p className="mt-1 line-clamp-2 text-[0.8667rem] text-ink-soft">{r.summary}</p>
                        )}
                      </div>
                      <span className="text-right text-[0.8rem] tabular-nums text-muted">
                        {r.start && end ? secondsText(end - r.start) : STEP_STATUS_LABEL[r.status] ?? ""}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- panou lateral (contestație nouă)

export function Sheet({ title, onClose, children, footer }: { title: string; onClose: () => void; children: ReactNode; footer?: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      prev?.focus?.();
    };
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label={title}>
      <button type="button" aria-label="Închide" className="absolute inset-0 bg-ink/35" onClick={onClose} />
      <div ref={ref} tabIndex={-1} className="absolute inset-y-0 right-0 flex w-full max-w-[34rem] flex-col bg-paper shadow-[var(--shadow-overlay)] outline-none animate-enter">
        <header className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 className="text-[1.15rem] font-bold">{title}</h2>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Închide"><X className="size-4" /></Button>
        </header>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && <footer className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</footer>}
      </div>
    </div>
  );
}
