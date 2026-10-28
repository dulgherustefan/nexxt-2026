import { DeviceMobile, Play, Plus } from "@phosphor-icons/react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { dateTime, duration, hasAmount, money, verdictLabel } from "../../api/format";
import { useApi, useResource } from "../../api/runtime";
import type { CaseSummary, Stats } from "../../api/types";
import { Button, cx, DeadlineText, EmptyState, ErrorNote, PageHeader, Skeleton, Tabs } from "../../ui/kit";
import { caseStatus, scenarioLabel, StatusLine } from "./caseUi";

type Filter = "you" | "running" | "today" | "closed" | "all";

// one source for the groups: the same function that gives the status label
const group = (c: CaseSummary) => caseStatus(String(c.status), c.requires_human).group;
const needsYou = (c: CaseSummary) => group(c) === "you";
const isClosed = (c: CaseSummary) => group(c) === "closed";

function dueSoon(c: CaseSummary): boolean {
  if (!c.deadline || isClosed(c)) return false;
  return new Date(c.deadline).getTime() - Date.now() < 24 * 3600 * 1000;
}

function byUrgency(a: CaseSummary, b: CaseSummary): number {
  const rank = (c: CaseSummary) => (needsYou(c) ? 0 : isClosed(c) ? 2 : 1);
  const r = rank(a) - rank(b);
  if (r) return r;
  const da = a.deadline ? new Date(a.deadline).getTime() : Infinity;
  const db = b.deadline ? new Date(b.deadline).getTime() : Infinity;
  return da - db;
}

const caseHref = (id: string) => `/cases/${encodeURIComponent(id)}`;

export default function CasesPage() {
  const api = useApi();
  const navigate = useNavigate();
  const cases = useResource(() => api.cases(), [api], { pollMs: 3000 });
  const stats = useResource(() => api.stats(), [api], { pollMs: 5000 });
  const [filter, setFilter] = useState<Filter>("all");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const list = useMemo(() => [...(cases.data ?? [])].sort(byUrgency), [cases.data]);
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
        description="Most urgent first. You only approve the exceptions."
        actions={
          <>
            <Button icon={<Play size={14} weight="fill" />} busy={starting} onClick={() => startCase("demo_t1")}>Run demo case</Button>
            <Button variant="primary" icon={<Plus size={14} weight="bold" />} onClick={() => navigate("/cases/new")}>New case</Button>
          </>
        }
      />
      {startError && <div className="mb-5"><ErrorNote error={startError} what="the new case" onRetry={() => startCase("demo_t1")} /></div>}

      <Summary stats={stats.data} counts={counts} />

      <div className="mt-8">
        <Tabs<Filter>
          label="Filter cases"
          value={filter}
          onChange={setFilter}
          tabs={[
            { id: "all", label: "All", count: counts.all },
            { id: "you", label: "Needs approval", count: counts.you },
            { id: "running", label: "In progress", count: counts.running },
            { id: "today", label: "Due within 24 h", count: counts.today },
            { id: "closed", label: "Closed", count: counts.closed },
          ]}
        />
      </div>

      <div className="mt-4">
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
          <CaseList cases={visible} onOpen={(id) => navigate(caseHref(id))} />
        )}
      </div>
      {cases.error && cases.data && (
        <p className="mt-3 text-[0.8667rem] text-danger">Updates from the server stopped. Showing the last list received.</p>
      )}

    </>
  );
}

// ---------------------------------------------------------------- summary card

function Summary({ stats, counts }: { stats?: Stats; counts: Record<Filter, number> }) {
  const refunded = stats ? money(stats.amount_refunded) : null;
  const parts = [
    counts.you ? `${counts.you} need${counts.you === 1 ? "s" : ""} approval` : null,
    counts.running ? `${counts.running} in progress` : null,
    stats?.deadlines_at_risk ? `${stats.deadlines_at_risk} at risk of missing the deadline` : null,
  ].filter(Boolean);
  return (
    <section aria-label="Summary" className="grid gap-6 rounded-2xl bg-paper px-6 py-5 shadow-[var(--shadow-card)] md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
      <div>
        <p className="text-[0.9333rem] text-muted">Refunded so far</p>
        {refunded ? (
          <p className="mt-1 text-[2.2rem] leading-none font-semibold tracking-[-0.03em]">{refunded}</p>
        ) : (
          <Skeleton className="mt-2 h-9 w-56" />
        )}
        <p className="mt-2.5 text-[0.9333rem] text-muted">
          {stats ? `${stats.refunded} of ${stats.cases_total} case${stats.cases_total === 1 ? "" : "s"} refunded` : " "}
          {stats?.avg_decision_seconds ? ` · average time to a decision ${duration(stats.avg_decision_seconds)}` : ""}
        </p>
      </div>
      <p className="text-[0.9333rem] text-ink-soft md:text-right">
        {parts.length ? parts.join(" · ") : counts.all ? "Nothing waiting on you." : ""}
      </p>
    </section>
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
          const s = caseStatus(String(c.status), c.requires_human);
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
                    "grid size-9 shrink-0 place-items-center rounded-full text-[0.75rem] font-semibold",
                    s.group === "you" ? "bg-yellow-tint text-ink ring-1 ring-inset ring-[#f1dc5c]" : "bg-hover text-ink-soft",
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
                <span className="text-[0.8667rem] md:text-[0.9333rem]" title={statusTitle(c)}>
                  <StatusLine status={String(c.status)} requiresHuman={c.requires_human} />
                </span>
                <span className="text-right text-[0.8667rem] md:text-left md:text-[0.9333rem]">
                  <DeadlineText deadline={c.deadline} done={isClosed(c)} />
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

/** The verdict and who signed it, for the status tooltip. */
function statusTitle(c: CaseSummary): string | undefined {
  const parts = [c.verdict ? verdictLabel(c.verdict) : null, c.approved_by ? `Signed by ${c.approved_by}${c.approved_at ? `, ${dateTime(c.approved_at)}` : ""}` : null];
  return parts.filter(Boolean).join(" · ") || undefined;
}
