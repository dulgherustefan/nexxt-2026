import { CheckCircle, X } from "@phosphor-icons/react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { dateTime, duration, money, scenarioLabel as baseScenarioLabel, verdictLabel } from "../../api/format";
import { useApi, useResource } from "../../api/runtime";
import type { AgentEvent, Decision, Money, PipelineNode, RoutingEntry, ScenarioInfo } from "../../api/types";
import { HIDDEN_STEPS, matchNode, normalizeStatus, STAGE_BY_ID } from "../../lib/pipeline";
import { Button, cx, Dot, ErrorNote, Skeleton, StepIcon, STEP_STATUS_LABEL, type Tone, useNowTick } from "../../ui/kit";

// ---------------------------------------------------------------- one set of case statuses across the app

export interface StatusView {
  label: string;
  tone: Tone;
  live?: boolean;
  group: "you" | "running" | "closed";
}

/**
 * `verdict` matters for a case the agents have finished without closing it: missing details wait on a person
 * (who asks the customer), and a dispute outside the refund rule goes the normal complaint route.
 */
export function caseStatus(status: string | null | undefined, requiresHuman = false, verdict?: string | null): StatusView {
  if (status === "IN_ANALIZA" && verdict === "INFORMATII_SUPLIMENTARE") return { label: "Missing details", tone: "now", group: "you" };
  if (status === "IN_ANALIZA" && verdict === "NU_SE_APLICA_T1") return { label: "Normal complaint route", tone: "neutral", group: "closed" };
  switch (status) {
    case "ASTEAPTA_APROBARE":
      return { label: "Needs approval", tone: "now", live: true, group: "you" };
    case "NOU":
      return { label: "New", tone: "neutral", group: "running" };
    case "IN_ANALIZA":
      return { label: "In progress", tone: "dark", live: true, group: "running" };
    case "RAMBURSAT":
      return { label: "Refunded", tone: "ok", group: "closed" };
    case "TRASEU_APP":
      return { label: "APP fraud review", tone: "neutral", group: requiresHuman ? "you" : "closed" };
    case "RESPINS":
      return { label: "Rejected", tone: "neutral", group: "closed" };
    case "EXCEPTIE":
      return { label: "Exception signed", tone: "danger", group: "closed" };
    case "INCHIS":
      return { label: "Closed", tone: "neutral", group: "closed" };
    case "EROARE":
      return { label: "Failed: restart the case", tone: "danger", group: "you" };
    default:
      return { label: status ?? "—", tone: "neutral", group: "running" };
  }
}

export function StatusLine({ status, requiresHuman, verdict }: { status?: string | null; requiresHuman?: boolean; verdict?: string | null }) {
  const s = caseStatus(status, requiresHuman, verdict);
  return (
    <span className={cx("inline-flex items-center gap-2 whitespace-nowrap", s.tone === "danger" ? "text-danger" : s.tone === "ok" ? "text-ok" : "text-ink-soft")}>
      <Dot tone={s.tone} live={s.live} />
      {s.label}
    </span>
  );
}

export function scenarioLabel(s: string | null | undefined): string {
  if (s === "demo_t1") return "Fake delivery link (demo)";
  if (s === "demo_t1_victima2") return "“Safe account” scam (demo)";
  return baseScenarioLabel(s);
}

export function exactTime(v: string | null | undefined): string {
  return dateTime(v);
}

// ---------------------------------------------------------------- the decision, in one sentence

/** `after` is what happened next (case status, the person's answer), so the sentence moves to the past tense. */
export function verdictSentence(
  d: Decision | undefined,
  amount: Money | null | undefined,
  after?: { status?: string; action?: string; approver?: string },
): { title: string; detail: string; tone: Tone } {
  const sum = money(amount ?? d?.amount ?? null);
  const until = d?.deadline ? exactTime(d.deadline) : "the deadline";
  const who = after?.approver ?? "a person";
  const Who = who.charAt(0).toUpperCase() + who.slice(1);
  if (d && after?.status === "RAMBURSAT") {
    return {
      title: `Refunded ${sum}.`,
      detail: d.decision === "RAMBURSEAZA" ? "Automatic: under the limit and no risk signals."
        : d.decision === "RAMBURSEAZA_CU_APROBARE" ? `Approved by ${who}, before the deadline.`
          : `${Who} didn’t confirm the decision against the customer, so the refund went out on time.`,
      tone: "ok",
    };
  }
  if (d?.decision === "RAMBURSEAZA_CU_APROBARE" && after?.action === "reject") {
    return { title: "The refund wasn’t approved.", detail: `${Who} declined it. The case stays open and the deadline keeps running.`, tone: "danger" };
  }
  if (d?.decision === "RESPINGE_TARDIV" && after?.status === "RESPINS") {
    return { title: "Claim rejected: reported more than 13 months after the payment.", detail: `The legal notice period had ended (art. 169). Signed by ${who}.`, tone: "neutral" };
  }
  if (d?.decision === "EXCEPTIE_FRAUDA_CLIENT" && after?.status === "EXCEPTIE") {
    return { title: "Exception confirmed: no refund for now.", detail: `Suspected customer fraud, reported to the authorities. Signed by ${who}.`, tone: "danger" };
  }
  switch (d?.decision) {
    case "RAMBURSEAZA":
      return { title: `Refund ${sum} by ${until}.`, detail: "Under the automatic refund limit with no risk signals, so the rules engine issues it without a signature.", tone: "ok" };
    case "RAMBURSEAZA_CU_APROBARE":
      return { title: `Refund ${sum} by ${until}, after your approval.`, detail: "The law requires the refund. A person confirms it because of the amount or a risk signal.", tone: "now" };
    case "NU_SE_APLICA_T1":
      return { title: "The customer authorized this payment, so the next-day refund rule doesn’t apply.", detail: "They were tricked into approving it themselves (APP fraud). VersoML starts a recall and helps them get the money back.", tone: "neutral" };
    case "RESPINGE_TARDIV":
      return { title: "Reported after 13 months: the claim will be rejected.", detail: "The legal notice period has ended (art. 169). A person signs any decision against the customer.", tone: "danger" };
    case "EXCEPTIE_FRAUDA_CLIENT":
      return { title: "Exception: suspected customer fraud, reported to the authorities.", detail: "The only exception to the next-day refund (CJEU C-70/25). A person signs it.", tone: "danger" };
    case "INFORMATII_SUPLIMENTARE":
      return { title: "Information is missing for a decision.", detail: "VersoML asks the customer for the missing details. The legal deadline keeps running.", tone: "neutral" };
    default:
      return { title: "Working on it", detail: "The decision appears here when the rules finish.", tone: "neutral" };
  }
}

// ---------------------------------------------------------------- agent steps

const PHASES: Array<{ id: string; label: string; doing: string; ids: string[] }> = [
  { id: "intake", label: "Intake", doing: "Reading the claim", ids: ["receptor", "identificare", "clasificator", "ceasornicar", "router"] },
  { id: "evidence", label: "Evidence", doing: "Collecting evidence", ids: ["colector_tranzactie", "colector_sca", "colector_dispozitiv", "colector_domeniu", "colector_campanie"] },
  { id: "decision", label: "Decision", doing: "Applying the rules", ids: ["motor_reguli", "rambursare"] },
  { id: "recovery", label: "Recovery", doing: "Preparing recovery", ids: ["procuror", "avocat", "cantaritor", "recuperare"] },
  { id: "reply", label: "Reply", doing: "Writing the reply", ids: ["redactor", "filtru_zid", "sigiliu"] },
];

export function modelName(m: string | null | undefined): string {
  const s = (m ?? "").toLowerCase();
  if (s.includes("opus")) return "Opus";
  if (s.includes("sonnet")) return "Sonnet";
  if (s.includes("haiku")) return "Haiku";
  if (s === "ml") return "ML";
  return "Rules";
}

export interface StepRow {
  id: string;
  label: string;
  model: string;
  status: string;
  summary?: string;
  hint?: string;
  start?: number;
  end?: number;
  /** The router's choice for this step, when it made one. */
  route?: RoutingEntry;
}

/** What a step is doing right now, when it says more than its phase. */
const STEP_DOING: Record<string, string> = {
  identificare: "Finding the customer and the payment",
  router: "Choosing the agents",
  colector_campanie: "Looking for linked cases",
};

/** The router's choices: what the case detail saved, then what the live events brought. */
export function useRouting(saved: RoutingEntry[] | undefined, events: AgentEvent[]): RoutingEntry[] {
  return useMemo(() => {
    const out = new Map<string, RoutingEntry>();
    for (const r of saved ?? []) if (r?.node) out.set(r.node, r);
    for (const e of events) {
      if (e.type !== "CUSTOM" || e.name !== "routing") continue;
      const d = e.data as Partial<RoutingEntry> | undefined;
      if (d?.node && typeof d.run === "boolean") out.set(d.node, { node: d.node, run: d.run, reason: String(d.reason ?? "") });
    }
    return [...out.values()];
  }, [saved, events]);
}

function ms(v: string | null | undefined): number | undefined {
  if (!v) return undefined;
  const t = new Date(v).getTime();
  return Number.isNaN(t) ? undefined : t;
}

/** Each step's state: first what the server saved, then what the live events brought. */
export function useStepRows(nodes: PipelineNode[] | undefined, events: AgentEvent[], routing: RoutingEntry[] = []): StepRow[] {
  return useMemo(() => {
    const rows = new Map<string, StepRow>();
    for (const n of nodes ?? []) {
      if (HIDDEN_STEPS.has(n.id)) continue;
      rows.set(n.id, {
        // the UI label wins: it is written for the operator, not for the graph
        id: n.id, label: STAGE_BY_ID[n.id]?.label ?? n.label, model: modelName(n.model), status: normalizeStatus(n.status),
        summary: n.summary, hint: STAGE_BY_ID[n.id]?.hint ?? n.hint, start: ms(n.started_at), end: ms(n.finished_at),
      });
    }
    for (const e of events) {
      if (e.type === "RUN_STARTED") {
        for (const r of rows.values()) Object.assign(r, { status: "idle", start: undefined, end: undefined, summary: undefined });
        continue;
      }
      const id = matchNode([...rows.values()].map((r) => ({ id: r.id, label: r.label, agent: undefined })), e);
      if (!id || HIDDEN_STEPS.has(id)) continue;
      const r = rows.get(id);
      if (!r) continue;
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
        if (e.data?.pending !== false) r.status = "waiting";
      } else if (e.type === "CUSTOM" && (e.name === "policy_denied" || e.name === "wall_block")) {
        r.status = "blocked";
      }
    }
    for (const route of routing) {
      const r = rows.get(route.node);
      if (r) r.route = route;
    }
    return [...rows.values()];
  }, [nodes, events, routing]);
}

function secondsText(ms0: number): string {
  const s = ms0 / 1000;
  return s < 10 ? `${s.toFixed(1)} s` : s < 90 ? `${Math.round(s)} s` : duration(s);
}

function timing(rows: StepRow[], now: number) {
  const starts = rows.map((r) => r.start).filter((x): x is number => typeof x === "number");
  const t0 = starts.length ? Math.min(...starts) : undefined;
  const ends = rows.map((r) => (r.status === "running" ? now : r.end)).filter((x): x is number => typeof x === "number");
  const t1 = ends.length ? Math.max(...ends) : undefined;
  return { t0, t1, total: t0 && t1 && t1 > t0 ? secondsText(t1 - t0) : null };
}

/**
 * The agents, in one line. While running: what they're doing now and five phase segments.
 * When done: a single sentence. The full step list opens on request.
 */
export function AgentStatus({ rows: input, settled, waiting, waitingLabel = "Waiting for your approval", onOpenTrace }: {
  rows: StepRow[]; settled: boolean; waiting: boolean; waitingLabel?: string; onOpenTrace: () => void;
}) {
  const rows = settled ? input.map((r) => (r.status === "idle" ? { ...r, status: "skipped" } : r)) : input;
  const now = useNowTick(250);
  const { total } = timing(rows, now);
  const byId = new Map(rows.map((r) => [r.id, r]));
  const phases = PHASES.map((p) => {
    const rs = p.ids.map((id) => byId.get(id)).filter(Boolean) as StepRow[];
    const state = !rs.length ? "todo"
      : rs.some((r) => r.status === "blocked" || r.status === "error") ? "stopped"
        : rs.some((r) => r.status === "waiting") ? "waiting"
          : rs.some((r) => r.status === "running") ? "running"
            : rs.every((r) => r.status === "done" || r.status === "skipped") ? "done"
              : rs.some((r) => r.status === "done") ? "running" : "todo";
    return { ...p, state };
  });
  const stopped = rows.filter((r) => r.status === "blocked" || r.status === "error");
  const doneCount = rows.filter((r) => r.status === "done" || r.status === "skipped").length;
  const runningPhase = phases.find((p) => p.state === "running");
  const runningStep = rows.find((r) => r.status === "running" && STEP_DOING[r.id]);
  const routed = rows.filter((r) => r.route);
  const skippedByRouter = routed.filter((r) => r.route && !r.route.run).length;
  const finished = rows.length > 0 && !runningPhase && !waiting && doneCount + stopped.length === rows.length;

  const headline = stopped.length
    ? { tone: "danger" as Tone, text: `${stopped[0].label} stopped` }
    : waiting
      ? { tone: "now" as Tone, text: waitingLabel }
      : finished
        ? { tone: "ok" as Tone, text: "Agents finished" }
        : runningPhase
          ? { tone: "dark" as Tone, text: runningStep ? STEP_DOING[runningStep.id] : runningPhase.doing }
          : { tone: "neutral" as Tone, text: "Starting" };

  return (
    <section aria-label="Agent progress" className="rounded-xl bg-paper px-4 py-3.5 shadow-[var(--shadow-card)]">
      <div className="flex items-center gap-3">
        {headline.tone === "ok" ? (
          <CheckCircle size={18} weight="fill" className="shrink-0 text-ok" />
        ) : (
          <span className="grid size-[18px] shrink-0 place-items-center"><Dot tone={headline.tone} live={headline.tone === "now" || headline.tone === "dark"} /></span>
        )}
        <p className="min-w-0 flex-1 leading-tight">
          <span className="block truncate text-[0.9333rem] font-medium">{headline.text}</span>
          <span className="tnum mt-0.5 block text-[0.8rem] text-muted">
            {finished ? `${rows.length} steps` : `${doneCount} of ${rows.length} steps`}
            {total ? ` · ${total}` : ""}
          </span>
        </p>
        <button type="button" onClick={onOpenTrace} className="shrink-0 rounded-full px-2.5 py-1 text-[0.8667rem] font-medium text-ink-soft transition-colors hover:bg-hover hover:text-ink">
          View trace
        </button>
      </div>
      <ol className="mt-3 grid grid-cols-5 gap-1.5" aria-label="Phases">
        {phases.map((p) => (
          <li key={p.id} className="min-w-0">
            <span
              aria-hidden
              className={cx(
                "block h-1 rounded-full transition-colors duration-300",
                p.state === "done" ? "bg-ink" : p.state === "waiting" ? "bg-yellow" : p.state === "running" ? "bg-ink/40" : p.state === "stopped" ? "bg-danger" : "bg-line",
              )}
            />
            <span className={cx("mt-1.5 block truncate text-[0.75rem]", p.state === "todo" ? "text-subtle" : "text-ink-soft")}>
              {p.label}
              <span className="sr-only">: {p.state === "todo" ? "not started" : p.state}</span>
            </span>
          </li>
        ))}
      </ol>
      {routed.length > 0 && (
        <p className="mt-2.5 border-t border-line pt-2.5 text-[0.8rem] text-muted">
          The router ran {routed.length - skippedByRouter} of {routed.length} optional agents.{" "}
          <button type="button" onClick={onOpenTrace} className="font-medium text-ink-soft underline decoration-line-strong underline-offset-2 hover:text-ink hover:decoration-ink">
            See why
          </button>
        </p>
      )}
    </section>
  );
}

/** The full trace: every step with its model, timing bar and summary. Lives in a side sheet. */
export function StepList({ rows: input, settled = false }: { rows: StepRow[]; settled?: boolean }) {
  const rows = settled ? input.map((r) => (r.status === "idle" ? { ...r, status: "skipped" } : r)) : input;
  const now = useNowTick(500);
  const { t0, t1, total } = timing(rows, now);
  const span = t0 && t1 && t1 > t0 ? t1 - t0 : 1;
  const byId = new Map(rows.map((r) => [r.id, r]));
  const phases = PHASES.map((p) => ({ ...p, rows: p.ids.map((id) => byId.get(id)).filter(Boolean) as StepRow[] })).filter((p) => p.rows.length);
  const known = new Set(PHASES.flatMap((p) => p.ids));
  const extra = rows.filter((r) => !known.has(r.id));
  if (extra.length) phases.push({ id: "other", label: "Other steps", doing: "", ids: extra.map((r) => r.id), rows: extra });

  return (
    <div>
      <p className="tnum text-[0.9333rem] text-muted">
        {rows.length} steps{total ? ` · ${total} end to end` : ""}
        {rows.some((r) => r.route) ? ` · the router skipped ${rows.filter((r) => r.route && !r.route.run).length}` : ""}
      </p>
      <ol className="mt-3">
        {phases.map((phase) => (
          <li key={phase.id} className="border-t border-line py-3 first:border-t-0">
            <p className="pb-1.5 text-[0.8rem] font-medium text-muted">{phase.label}</p>
            <ul className="flex flex-col gap-1">
              {phase.rows.map((r) => {
                const end = r.status === "running" ? now : r.end;
                const left = t0 && r.start ? ((r.start - t0) / span) * 100 : 0;
                const width = r.start && end ? Math.max(((end - r.start) / span) * 100, 1.5) : 0;
                return (
                  <li key={r.id} className="grid grid-cols-[1rem_minmax(0,1fr)_4rem] items-start gap-x-3 py-1.5" title={r.hint}>
                    <span className="mt-0.5"><StepIcon status={r.status} /></span>
                    <div className="min-w-0">
                      <p className="flex items-baseline gap-2">
                        <span className={cx("text-[0.9333rem] font-medium", r.status === "idle" && "text-muted")}>{r.label}</span>
                        <span className="text-[0.75rem] text-subtle">{r.model}</span>
                      </p>
                      <div className="mt-1.5 h-1 rounded-full bg-hover" aria-hidden>
                        {width > 0 && (
                          <div
                            className={cx("h-1 rounded-full", r.status === "running" || r.status === "waiting" ? "bg-yellow" : r.status === "blocked" || r.status === "error" ? "bg-danger" : "bg-ink/70")}
                            style={{ marginLeft: `${Math.min(left, 98)}%`, width: `${Math.min(width, 100 - Math.min(left, 98))}%` }}
                          />
                        )}
                      </div>
                      {r.summary && r.status !== "idle" && r.status !== "skipped" && <p className="mt-1.5 line-clamp-2 text-[0.8667rem] text-muted">{r.summary}</p>}
                      {r.route && (
                        <p className={cx("mt-1 text-[0.8rem]", r.route.run ? "text-ink-soft" : "text-subtle")}>
                          <span className="font-medium">{r.route.run ? "Why it ran:" : "Not needed:"}</span> {r.route.reason}
                        </p>
                      )}
                      {!r.route && r.status === "skipped" && r.summary && <p className="mt-1 text-[0.8rem] text-subtle">{r.summary}</p>}
                    </div>
                    <span className="tnum text-right text-[0.8rem] text-muted">
                      {r.start && end ? secondsText(end - r.start) : STEP_STATUS_LABEL[r.status] ?? ""}
                    </span>
                  </li>
                );
              })}
            </ul>
          </li>
        ))}
      </ol>
    </div>
  );
}

// ---------------------------------------------------------------- side sheet

export function Sheet({ title, onClose, children, footer, description }: {
  title: string; onClose: () => void; children: ReactNode; footer?: ReactNode; description?: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onCloseRef.current();
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      prev?.focus?.();
    };
  }, []);
  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label={title}>
      <button type="button" aria-label="Close" className="absolute inset-0 bg-ink/25 animate-[fade-in_200ms_var(--ease-out)]" onClick={onClose} />
      <div
        ref={ref}
        tabIndex={-1}
        className="absolute inset-y-2 right-2 flex w-[calc(100%-1rem)] max-w-[32rem] flex-col rounded-2xl bg-paper shadow-[var(--shadow-overlay)] outline-none animate-[sheet-in_300ms_var(--ease-drawer)]"
      >
        <header className="flex items-start justify-between gap-4 px-6 pt-5 pb-3">
          <div>
            <h2 className="text-[1.15rem] font-semibold">{title}</h2>
            {description && <p className="mt-0.5 text-[0.9333rem] text-muted">{description}</p>}
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="grid size-8 place-items-center rounded-full text-muted transition-colors hover:bg-hover hover:text-ink">
            <X size={16} />
          </button>
        </header>
        <div className="flex-1 overflow-y-auto px-6 pb-6">{children}</div>
        {footer && <footer className="flex justify-end gap-2 border-t border-line px-6 py-4">{footer}</footer>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- sample cases

/** Start a case from one of the prepared situations. The case starts right away. */
export function SampleCaseSheet({ onClose, onStart, busy }: { onClose: () => void; onStart: (id: string) => void; busy: boolean }) {
  const api = useApi();
  const scenarios = useResource(() => api.scenarios(), [api]);
  const [choice, setChoice] = useState<string>("demo_t1");
  return (
    <Sheet
      title="Start from a sample"
      description="Pick a prepared situation. The case starts right away."
      onClose={onClose}
      footer={<>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" busy={busy} disabled={!choice} onClick={() => onStart(choice)}>Start case</Button>
      </>}
    >
      {scenarios.error && !scenarios.data ? (
        <ErrorNote error={scenarios.error} what="the scenarios" onRetry={scenarios.reload} />
      ) : !scenarios.data ? (
        <div className="flex flex-col gap-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-16 rounded-xl" />)}</div>
      ) : (
        <fieldset className="flex flex-col gap-1.5">
          <legend className="sr-only">Situation</legend>
          {scenarios.data.map((s: ScenarioInfo) => (
            <label
              key={s.id}
              className={cx(
                "flex cursor-pointer gap-3 rounded-xl px-4 py-3 transition-colors",
                choice === s.id ? "bg-canvas ring-1 ring-inset ring-ink" : "ring-1 ring-inset ring-line hover:bg-canvas",
              )}
            >
              <input type="radio" name="scenario" value={s.id} checked={choice === s.id} onChange={() => setChoice(s.id)} className="mt-1 accent-ink" />
              <span className="min-w-0">
                <span className="block font-medium">{s.title || scenarioLabel(s.id)}</span>
                {s.description && <span className="mt-0.5 block text-[0.8667rem] text-muted">{s.description}</span>}
                {s.expected_verdict && <span className="mt-1 block text-[0.8rem] text-subtle">Expected outcome: {verdictLabel(String(s.expected_verdict))}</span>}
              </span>
            </label>
          ))}
        </fieldset>
      )}
    </Sheet>
  );
}
