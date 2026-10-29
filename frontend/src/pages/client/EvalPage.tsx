import { ArrowClockwise, CaretRight, ChartLineUp } from "@phosphor-icons/react";
import { useMemo, useState } from "react";
import { clock, num, relative, scenarioLabel, verdictLabel } from "../../api/format";
import { useApi, useResource } from "../../api/runtime";
import { Badge, Button, cx, Dot, EmptyState, ErrorNote, IdTag, PageHeader, SectionBoundary, Skeleton, Status, useNowTick, type Tone } from "../../ui/kit";
import { METRIC_GROUPS, normalizeEval, type EvalModel, type Failure, type Metric } from "./evalReport";
import { CommandLine, CopyButton, dateTimeYear } from "./trustUi";

type Report = Extract<EvalModel, { kind: "report" }>;

const COMMAND = "uv run versoml eval --fast";

const LLM_MODE: Record<string, string> = {
  live: "Live model on Amazon Bedrock",
  replay: "Recorded model answers",
  offline: "No model, rules and templates only",
};

const OUTCOME: Record<Metric["outcome"], { word: string; tone: Tone }> = {
  pass: { word: "Pass", tone: "ok" },
  fail: { word: "Fail", tone: "danger" },
  none: { word: "No data", tone: "neutral" },
  measured: { word: "Measured", tone: "neutral" },
};

const lowerFirst = (s: string) => s.charAt(0).toLowerCase() + s.slice(1);

/** "a", "a and b", "a, b, and c". */
function listOf(items: string[]): string {
  if (items.length <= 1) return items.join("");
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(", ")}, and ${items[items.length - 1]}`;
}

export default function EvalPage() {
  const api = useApi();
  const res = useResource(() => api.evalReport(), [api]);
  const model = useMemo(() => (res.data ? normalizeEval(res.data) : null), [res.data]);
  const [checking, setChecking] = useState(false);
  const [checkedAt, setCheckedAt] = useState<number | null>(null);

  async function check() {
    setChecking(true);
    await res.reload();
    setChecking(false);
    setCheckedAt(Date.now());
  }

  return (
    <>
      <PageHeader
        title="Evaluation"
        description="Scores on synthetic cases, measured before anyone relies on them."
        actions={
          model?.kind === "report" ? (
            <Button icon={<ArrowClockwise aria-hidden size={16} />} busy={checking} onClick={check}>Reload report</Button>
          ) : undefined
        }
      />

      {res.error && !res.data ? (
        <ErrorNote error={res.error} what="the evaluation report" onRetry={check} />
      ) : !model ? (
        <ResultsSkeleton />
      ) : model.kind === "missing" ? (
        <Missing onCheck={check} checking={checking} checkedAt={checkedAt} failed={Boolean(res.error)} />
      ) : (
        <>
          {res.error && (
            <p role="alert" className="mb-3 text-[0.8667rem] text-danger">Couldn’t reload the report. Showing the last one received.</p>
          )}
          <SectionBoundary label="Results">
            <Results model={model} />
          </SectionBoundary>
          {model.failures.length > 0 && (
            <SectionBoundary label="Wrong decisions">
              <Failures items={model.failures} />
            </SectionBoundary>
          )}
          <RawReport raw={model.raw} />
        </>
      )}
    </>
  );
}

// ---------------------------------------------------------------- no report yet

function Missing({ onCheck, checking, checkedAt, failed }: { onCheck: () => void; checking: boolean; checkedAt: number | null; failed: boolean }) {
  return (
    <EmptyState
      icon={<ChartLineUp aria-hidden size={20} />}
      title="No evaluation report yet"
      action={
        <div className="mt-1 flex w-full max-w-md flex-col items-center gap-3">
          <CommandLine command={COMMAND} />
          <Button icon={<ArrowClockwise aria-hidden size={16} />} busy={checking} onClick={onCheck}>Check again</Button>
          <p role="status" className="min-h-5 text-[0.8667rem] text-muted">
            {checking
              ? ""
              : failed
                ? <span className="text-danger">Couldn’t reach the server. Check that it’s running, then try again.</span>
                : checkedAt
                  ? <>Checked at <span className="tnum">{clock(checkedAt, false)}</span>. Still no report.</>
                  : ""}
          </p>
        </div>
      }
    >
      Run this in the project folder. It checks the rules and the claim classifier on synthetic cases, then saves the report this page reads.
    </EmptyState>
  );
}

// ---------------------------------------------------------------- results

const METRIC_GRID = "md:grid-cols-[minmax(0,1fr)_7rem_6.5rem_7rem]";

function Results({ model }: { model: Report }) {
  const now = useNowTick(60_000);
  // measured rows (run times) have no target: they are not checks
  const checks = model.metrics.filter((m) => m.outcome !== "measured");
  const total = checks.length;
  const passed = checks.filter((m) => m.outcome === "pass").length;
  const failed = checks.filter((m) => m.outcome === "fail");
  const noData = total - passed - failed.length;

  const title = passed + failed.length === 0
    ? "No results in this report"
    : failed.length === 0 && noData === 0
      ? `All ${total} checks passed`
      : `${passed} of ${total} checks passed`;
  const notes = [
    failed.length > 0 ? `Below target: ${listOf(failed.map((m) => lowerFirst(m.name)))}.` : null,
    noData > 0 ? (noData === 1 ? "1 check has no data in this report." : `${noData} checks have no data in this report.`) : null,
  ].filter(Boolean);
  const tone: Tone = failed.length > 0 ? "danger" : passed === 0 || noData > 0 ? "neutral" : "ok";

  const at = dateTimeYear(model.at);
  const mode = model.llmMode ? LLM_MODE[model.llmMode] ?? `Model mode: ${model.llmMode}` : "Model mode not recorded";

  return (
    <section aria-labelledby="eval-title" className="overflow-clip rounded-2xl bg-paper shadow-[var(--shadow-card)]">
      <header className="flex items-start gap-3 px-5 py-4">
        <span className="flex h-[1.6rem] shrink-0 items-center"><Dot tone={tone} /></span>
        <div className="min-w-0">
          <h2 id="eval-title" className="text-[1.0667rem] leading-[1.6rem] font-semibold">{title}</h2>
          {notes.length > 0 && <p className="text-[0.9333rem] text-ink-soft">{notes.join(" ")}</p>}
          <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[0.8667rem] text-muted">
            <span>
              {at && model.at ? (
                <>Generated <span className="tnum">{at}</span> · {relative(model.at, now)}</>
              ) : (
                "Generation time not recorded"
              )}
            </span>
            <span aria-hidden className="text-subtle">·</span>
            <span>{mode}</span>
            {model.cases ? (
              <>
                <span aria-hidden className="text-subtle">·</span>
                <span className="tnum">{num(model.cases)} synthetic cases</span>
              </>
            ) : null}
            {model.simulated && (
              <Badge className="ml-1" title="This report comes from demo data, not from a run of the evaluation.">Demo data</Badge>
            )}
          </p>
        </div>
      </header>

      <div aria-hidden className={cx("hidden gap-x-4 border-t border-line px-5 py-2 text-[0.8rem] text-subtle md:grid", METRIC_GRID)}>
        <span>Check</span>
        <span className="text-right">Result</span>
        <span className="text-right">Target</span>
        <span className="pl-2">Status</span>
      </div>

      {METRIC_GROUPS.map((g) => {
        const rows = model.metrics.filter((m) => m.group === g.id);
        if (rows.length === 0) return null;
        return (
          <div key={g.id} role="group" aria-labelledby={`eval-group-${g.id}`}>
            <h3 id={`eval-group-${g.id}`} className="border-y border-line bg-canvas px-5 py-2 text-[0.8rem] font-medium text-muted">
              {g.title}
            </h3>
            <ul className="divide-y divide-line">
              {rows.map((m) => <MetricRow key={m.id} m={m} />)}
            </ul>
          </div>
        );
      })}
    </section>
  );
}

function MetricRow({ m }: { m: Metric }) {
  const o = OUTCOME[m.outcome];
  const sub = m.problem ?? m.detail;
  return (
    <li className={cx("grid grid-cols-[minmax(0,1fr)_auto] items-start gap-x-4 px-5 py-3 md:items-center", METRIC_GRID)}>
      <div className="min-w-0">
        <p className="font-medium">{m.name}</p>
        {sub && <p className={cx("mt-0.5 text-[0.8rem] leading-snug", m.problem ? "text-warn" : "text-muted")}>{sub}</p>}
        <p className="mt-0.5 text-[0.8rem] text-muted md:hidden">
          Target <span className="tnum">{m.targetText}</span>
        </p>
      </div>
      <div className="flex flex-col items-end gap-1 md:contents">
        <p className="tnum text-right font-medium">
          {m.value === null ? <span className="sr-only">No result</span> : <><span className="sr-only">Result </span>{m.valueText}</>}
        </p>
        <p className="tnum hidden text-right text-[0.9333rem] text-muted md:block">
          <span className="sr-only">Target </span>
          {m.targetText}
        </p>
        <span className="md:pl-2">
          <Status tone={o.tone}>{o.word}</Status>
        </span>
      </div>
    </li>
  );
}

function Failures({ items }: { items: Failure[] }) {
  return (
    <section aria-labelledby="eval-failures" className="mt-6 overflow-clip rounded-2xl bg-paper shadow-[var(--shadow-card)]">
      <header className="px-5 py-4">
        <h2 id="eval-failures" className="text-[0.9333rem] font-semibold">Wrong decisions</h2>
        <p className="mt-0.5 text-[0.8667rem] text-muted">Cases where the rules missed the expected decision (up to 12 per set).</p>
      </header>
      <ul className="divide-y divide-line border-t border-line">
        {items.map((f, i) => (
          <li key={`${f.set}-${f.id}-${i}`} className="grid gap-x-4 gap-y-1 px-5 py-3 sm:grid-cols-[minmax(0,13rem)_minmax(0,1fr)] sm:items-center">
            <span className="flex min-w-0 items-center gap-2.5">
              <IdTag>{f.id || "No ID"}</IdTag>
              <span className="truncate text-[0.8rem] text-muted">{f.set === "golden" ? "Golden set" : "Generated"}</span>
            </span>
            <p className="text-[0.9333rem]">
              <span className="text-muted">{f.scenario ? scenarioLabel(f.scenario) : "Unknown scenario"}:</span>{" "}
              expected <span className="font-medium">{f.expected ? verdictLabel(f.expected) : "no decision"}</span>,
              got <span className="font-medium">{f.got ? verdictLabel(f.got) : "no decision"}</span>
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

function RawReport({ raw }: { raw: unknown }) {
  const json = useMemo(() => JSON.stringify(raw, null, 2) ?? "", [raw]);
  return (
    <details className="group mt-6 rounded-2xl bg-paper shadow-[var(--shadow-card)]">
      <summary
        className={cx(
          "flex cursor-pointer list-none items-center gap-2 rounded-2xl px-5 py-3.5 text-[0.9333rem] font-medium transition-colors select-none",
          "hover:bg-canvas group-open:rounded-b-none [&::-webkit-details-marker]:hidden",
        )}
      >
        <CaretRight aria-hidden size={14} className="text-subtle transition-transform duration-150 group-open:rotate-90" />
        Raw report
        <span className="font-normal text-muted">JSON</span>
      </summary>
      <div className="border-t border-line">
        <div className="flex items-center justify-between gap-3 py-1.5 pr-1.5 pl-5">
          <span className="text-[0.8rem] text-muted">The full file the server sent, including sections this page doesn’t list.</span>
          <CopyButton text={json} label="Copy JSON" />
        </div>
        <pre
          tabIndex={0}
          className="max-h-[32rem] overflow-auto rounded-b-2xl border-t border-line bg-canvas px-5 py-4 font-mono text-[0.8rem] leading-relaxed text-ink-soft"
        >
          {json}
        </pre>
      </div>
    </details>
  );
}

function ResultsSkeleton() {
  return (
    <div className="overflow-hidden rounded-2xl bg-paper shadow-[var(--shadow-card)]" aria-busy="true">
      <div className="flex flex-col gap-2 px-5 py-4">
        <Skeleton className="h-5 w-56" />
        <Skeleton className="h-4 w-80 max-w-full" />
      </div>
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <div key={i} className="flex items-center gap-6 border-t border-line px-5 py-3.5">
          <Skeleton className="h-4 flex-1" />
          <Skeleton className="h-4 w-14" />
          <Skeleton className="hidden h-4 w-12 md:block" />
          <Skeleton className="h-4 w-16" />
        </div>
      ))}
    </div>
  );
}
