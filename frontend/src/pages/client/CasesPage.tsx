import { CheckCircle, DeviceMobile, Hourglass, Play, Plus, Signature, Siren, Spinner } from "@phosphor-icons/react";
import { useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router";
import { dateTime, duration, hasAmount, money, verdictLabel } from "../../api/format";
import { useApi, useResource } from "../../api/runtime";
import type { CaseEscalation, CaseSummary, Stats } from "../../api/types";
import { Button, cx, DeadlineText, EmptyState, ErrorNote, PageHeader, Skeleton } from "../../ui/kit";
import { caseStatus, FlagMarkers, scenarioLabel, StatusLine } from "./caseUi";

type Filter = "you" | "running" | "today" | "closed" | "all";

// one source for the groups: the same function that gives the status label
const group = (c: CaseSummary) => caseStatus(String(c.status), c.requires_human, c.verdict).group;
const needsYou = (c: CaseSummary) => group(c) === "you";
const isClosed = (c: CaseSummary) => group(c) === "closed";

function dueSoon(c: CaseSummary): boolean {
  if (!c.deadline || isClosed(c)) return false;
  return new Date(c.deadline).getTime() - Date.now() < 24 * 3600 * 1000;
}

type Sort = "deadline" | "newest";

/** The deadline that counts: the escalation's (refund or written answer), else the refund deadline. */
const dueAt = (c: CaseSummary) => {
  const at = c.escalation?.deadline ?? c.deadline;
  const t = at ? new Date(at).getTime() : NaN;
  return Number.isNaN(t) ? Infinity : t;
};

/** Open cases by deadline, soonest first, so the overdue ones lead; closed cases after them. */
function byDeadline(a: CaseSummary, b: CaseSummary): number {
  const r = Number(isClosed(a)) - Number(isClosed(b));
  if (r) return r;
  return dueAt(a) - dueAt(b) || (needsYou(b) ? 1 : 0) - (needsYou(a) ? 1 : 0);
}

function byNewest(a: CaseSummary, b: CaseSummary): number {
  return new Date(b.received_at).getTime() - new Date(a.received_at).getTime();
}

const caseHref = (id: string) => `/cases/${encodeURIComponent(id)}`;

export default function CasesPage() {
  const api = useApi();
  const navigate = useNavigate();
  const cases = useResource(() => api.cases(), [api], { pollMs: 3000 });
  const stats = useResource(() => api.stats(), [api], { pollMs: 5000 });
  const [filter, setFilter] = useState<Filter>("all");
  const [sort, setSort] = useState<Sort>("deadline");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const list = useMemo(() => [...(cases.data ?? [])].sort(sort === "deadline" ? byDeadline : byNewest), [cases.data, sort]);
  const counts = useMemo(() => ({
    you: list.filter(needsYou).length,
    running: list.filter((c) => group(c) === "running").length,
    today: list.filter(dueSoon).length,
    closed: list.filter(isClosed).length,
    all: list.length,
  }), [list]);
  const visible = list.filter((c) =>
    filter === "all" ? true
      : filter === "you" ? needsYou(c)
        : filter === "running" ? group(c) === "running"
          : filter === "today" ? dueSoon(c)
            : isClosed(c));

  async function startCase(scenarioId: string) {
    setStarting(true);
    setStartError(null);
    try {
      const { case_id } = await api.createCase({ scenario_id: scenarioId });
      await api.runCase(case_id);
      navigate(caseHref(case_id));
    } catch (e) {
      setStartError(e instanceof Error ? e.message : "The case didn't start");
      setStarting(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Cases"
        description={<>Soonest deadline first. You only approve the exceptions{stats.data?.avg_decision_seconds ? <>; a decision takes <span className="tnum">{duration(stats.data.avg_decision_seconds)}</span> on average</> : null}.</>}
        actions={
          <>
            <Button icon={<Play size={14} weight="fill" />} busy={starting} onClick={() => startCase("demo_t1")}>Run demo case</Button>
            <Button variant="primary" icon={<Plus size={14} weight="bold" />} onClick={() => navigate("/cases/new")}>New case</Button>
          </>
        }
      />
      {startError && <div className="mb-5"><ErrorNote error={startError} what="the new case" onRetry={() => startCase("demo_t1")} /></div>}

      <Lanes stats={stats.data} counts={counts} value={filter} onChange={setFilter} loading={!cases.data} />

      <div className="mt-8 mb-3 flex items-baseline justify-between gap-4">
        <h2 className="text-[1.1rem] font-semibold tracking-[-0.015em]">
          {LANE_TITLE[filter]} <span className="tnum font-normal text-muted">{filter === "all" ? counts.all : visible.length}</span>
        </h2>
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          {filter !== "all" && (
            <button type="button" onClick={() => setFilter("all")} className="text-[0.9333rem] font-medium text-ink-soft underline decoration-line-strong underline-offset-2 transition-colors hover:text-ink hover:decoration-ink">
              Show all cases
            </button>
          )}
          <div role="group" aria-label="Sort cases" className="flex items-center gap-0.5 rounded-full bg-hover p-0.5 text-[0.8667rem]">
            {(["deadline", "newest"] as const).map((v) => (
              <button
                key={v}
                type="button"
                aria-pressed={sort === v}
                onClick={() => setSort(v)}
                className={cx("h-7 rounded-full px-3 font-medium transition-colors", sort === v ? "bg-paper text-ink shadow-[var(--shadow-card)]" : "text-muted hover:text-ink")}
              >
                {v === "deadline" ? "Deadline" : "Newest"}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div>
        {cases.error && !cases.data ? (
          <ErrorNote error={cases.error} what="the cases" onRetry={cases.reload} />
        ) : !cases.data ? (
          <div className="flex flex-col gap-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-14 rounded-xl" />)}</div>
        ) : list.length === 0 ? (
          <EmptyState
            icon={<DeviceMobile size={20} />}
            title="No cases yet"
            action={
              <div className="flex flex-wrap justify-center gap-2">
                <Button variant="primary" icon={<Play size={14} weight="fill" />} busy={starting} onClick={() => startCase("demo_t1")}>Run demo case</Button>
                <a className="press inline-flex h-9 items-center rounded-full bg-paper px-4 text-[0.9333rem] font-medium shadow-[var(--shadow-card)] hover:bg-hover" href="/bank" target="_blank" rel="noreferrer">
                  Open Demo Bank
                </a>
              </div>
            }
          >
            Run the demo case, or report a payment from Demo Bank.
          </EmptyState>
        ) : visible.length === 0 ? (
          <EmptyState title="Nothing in this view">Pick another filter, or go back to All.</EmptyState>
        ) : (
          <div key={filter} className="animate-enter"><CaseList cases={visible} onOpen={(id) => navigate(caseHref(id))} /></div>
        )}
      </div>
      {cases.error && cases.data && (
        <p className="mt-3 text-[0.8667rem] text-danger">Updates from the server stopped. Showing the last list received.</p>
      )}

    </>
  );
}

// ---------------------------------------------------------------- the four lanes: what needs a person, what is urgent, what runs, what is done

const LANE_TITLE: Record<Filter, string> = {
  all: "All cases",
  you: "Waiting for you",
  today: "Due within 24 hours",
  running: "In progress",
  closed: "Closed",
};

function Lanes({ stats, counts, value, onChange, loading }: {
  stats?: Stats; counts: Record<Filter, number>; value: Filter; onChange: (f: Filter) => void; loading: boolean;
}) {
  const lanes: Array<{ id: Filter; icon: ReactNode; title: string; note: string; strong?: boolean }> = [
    {
      id: "you", icon: <Signature size={18} />, title: "Waiting for you",
      note: counts.you ? "Approve a refund or pick a payment" : "Nothing to sign", strong: counts.you > 0,
    },
    {
      id: "today", icon: <Hourglass size={18} />, title: "Due within 24 h",
      note: stats?.deadlines_at_risk ? `${stats.deadlines_at_risk} with under 6 hours left` : "Under 24 hours left to refund",
    },
    { id: "running", icon: <Spinner size={18} />, title: "In progress", note: "The agents are working on them" },
    {
      id: "closed", icon: <CheckCircle size={18} />, title: "Closed",
      note: stats ? `${money(stats.amount_refunded)} refunded` : "Refunded, rejected or signed",
    },
  ];
  return (
    <div role="group" aria-label="Filter cases" className="grid grid-cols-2 gap-2.5 sm:gap-3 xl:grid-cols-4">
      {lanes.map((l) => {
        const on = value === l.id;
        return (
          <button
            key={l.id}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(on ? "all" : l.id)}
            className={cx(
              "press group flex min-w-0 flex-col gap-2 rounded-xl px-3.5 py-3 text-left sm:gap-3 sm:px-4 sm:py-3.5 transition-[background-color,box-shadow] duration-150",
              l.strong
                ? "bg-yellow text-on-yellow hover:bg-yellow-hover"
                : "bg-paper shadow-[var(--shadow-card)] hover:bg-hover",
              on && (l.strong ? "ring-2 ring-on-yellow ring-offset-2 ring-offset-paper" : "ring-2 ring-ink"),
            )}
          >
            <span className="flex items-center justify-between gap-3">
              <span className={cx("truncate text-[0.8667rem] font-medium sm:text-[0.9333rem]", !l.strong && "text-ink-soft")}>{l.title}</span>
              <span className={cx(l.strong ? "text-on-yellow" : "text-subtle")}>{l.icon}</span>
            </span>
            <span className="flex items-baseline gap-2">
              {loading
                ? <span aria-hidden className="h-8 w-10 animate-pulse rounded-md bg-hover" />
                : <span className="tnum text-[1.9rem] leading-none font-semibold tracking-[-0.03em]">{counts[l.id]}</span>}
            </span>
            <span className={cx("hidden truncate text-[0.8rem] sm:block", l.strong ? "text-on-yellow-muted" : "text-muted")}>{l.note}</span>
          </button>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------- the list

function initials(name: string): string {
  const words = name.replace(/[^A-Za-z0-9 ]/g, " ").split(/\s+/).filter(Boolean);
  const letters = words.filter((w) => /[A-Za-z]/.test(w[0])).map((w) => w[0].toUpperCase());
  return (letters.slice(0, 2).join("") || "#");
}

function CaseList({ cases, onOpen }: { cases: CaseSummary[]; onOpen: (id: string) => void }) {
  return (
    <div className="overflow-hidden rounded-2xl bg-paper shadow-[var(--shadow-card)]">
      <div className="hidden grid-cols-[minmax(0,2.2fr)_minmax(0,1.2fr)_minmax(0,1.1fr)_minmax(0,1fr)] gap-4 border-b border-line px-5 py-2.5 text-[0.8rem] text-subtle md:grid">
        <span>Customer</span>
        <span>Status</span>
        <span>Deadline</span>
        <span className="text-right">Amount</span>
      </div>
      <ul className="divide-y divide-line">
        {cases.map((c) => {
          const s = caseStatus(String(c.status), c.requires_human, c.verdict);
          return (
            <li key={c.case_id}>
              <button
                type="button"
                onClick={() => onOpen(c.case_id)}
                aria-label={`Open case ${c.case_id}, ${c.customer_alias}${hasAmount(c.amount) ? `, ${money(c.amount)}` : ""}`}
                onKeyDown={(e) => {
                  const li = e.currentTarget.parentElement;
                  if (e.key === "ArrowDown") (li?.nextElementSibling?.querySelector("button") as HTMLElement | null)?.focus();
                  if (e.key === "ArrowUp") (li?.previousElementSibling?.querySelector("button") as HTMLElement | null)?.focus();
                }}
                className={cx(
                  "grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-2 px-5 py-3.5 text-left transition-colors hover:bg-canvas focus-visible:bg-canvas",
                  "md:grid-cols-[minmax(0,2.2fr)_minmax(0,1.2fr)_minmax(0,1.1fr)_minmax(0,1fr)]",
                )}
              >
                <span className="flex min-w-0 items-center gap-3">
                  <span className={cx(
                    "hidden size-9 shrink-0 place-items-center rounded-full text-[0.75rem] font-semibold md:grid",
                    s.group === "you" ? "bg-yellow-tint text-ink ring-1 ring-inset ring-yellow-line" : "bg-hover text-ink-soft",
                  )}>
                    {initials(c.customer_alias)}
                  </span>
                  <span className="min-w-0 leading-tight">
                    <span className="block truncate font-medium">{c.customer_alias}</span>
                    <span className="mt-0.5 block truncate text-[0.8rem] text-muted">
                      {c.scenario_phrase || scenarioLabel(c.scenario)} · <span className="id-text text-[0.8rem] text-subtle">{c.case_id}</span>
                    </span>
                  </span>
                </span>
                <span className="tnum text-right font-medium md:hidden">{hasAmount(c.amount) ? money(c.amount) : "—"}</span>
                <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-[0.8667rem] md:text-[0.9333rem]" title={statusTitle(c)}>
                  <StatusLine status={String(c.status)} requiresHuman={c.requires_human} verdict={c.verdict} />
                  <FlagMarkers flags={c.review_flags} />
                </span>
                <span className="flex flex-col items-end gap-0.5 text-right text-[0.8667rem] md:items-start md:text-left md:text-[0.9333rem]">
                  <DeadlineText deadline={c.escalation?.deadline ?? c.deadline} done={isClosed(c) && c.status !== "REFUZAT"} />
                  {c.escalation && <Escalation e={c.escalation} />}
                </span>
                <span className="tnum hidden text-right font-medium md:block">{hasAmount(c.amount) ? money(c.amount) : "—"}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** Escalated by the server: close to or past the deadline on a case nobody has settled. */
function Escalation({ e }: { e: CaseEscalation }) {
  const breached = e.level === "breached";
  return (
    <span title={e.message} className={cx("inline-flex items-center gap-1 text-[0.8rem] font-medium", breached ? "text-danger" : "text-warn")}>
      <Siren aria-hidden size={13} weight="fill" />
      {breached ? "Escalated: overdue" : "Escalated: at risk"}
      <span className="sr-only">. {e.message}</span>
    </span>
  );
}

/** The verdict and who signed it, for the status tooltip. */
function statusTitle(c: CaseSummary): string | undefined {
  const parts = [c.verdict ? verdictLabel(c.verdict) : null, c.approved_by ? `Signed by ${c.approved_by}${c.approved_at ? `, ${dateTime(c.approved_at)}` : ""}` : null];
  return parts.filter(Boolean).join(" · ") || undefined;
}
