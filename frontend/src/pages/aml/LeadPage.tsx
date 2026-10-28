import { Play, RotateCw, TriangleAlert, Waypoints } from "lucide-react";
import { useCallback, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router";
import { ApiError } from "../../api/client";
import { dateTime, relative, verdictLabel } from "../../api/format";
import { useApi, usePrefersReducedMotion } from "../../api/runtime";
import { Badge, Button, Dot, EmptyState, ErrorNote, IdTag, SectionBoundary, Skeleton, useNowTick } from "../../ui/kit";
import { maskAccount, roCount, tsOf } from "./aml";
import { DecisionArea } from "./DecisionPanel";
import FlowGraph from "./FlowGraph";
import { describeFlow, subjectIdsOf } from "./flow";
import { AchPanel, ClocksPanel, ScorePanel, StepsPanel } from "./LeadPanels";
import { LeadTabs, type LeadTab } from "./LeadTabs";
import { LeadStatusBadge, StaleNote } from "./ui";
import { useLead } from "./useLead";

function Breadcrumb({ id }: { id: string }) {
  return (
    <nav aria-label="Firul paginii" className="mb-3 flex items-center gap-1.5 text-[0.8667rem] text-muted">
      <Link to="/" className="font-semibold text-ink-soft hover:underline">
        Piste
      </Link>
      <span aria-hidden>/</span>
      <span aria-current="page" className="font-mono text-ink">
        {id || "—"}
      </span>
    </nav>
  );
}

function LeadSkeleton({ id }: { id: string }) {
  return (
    <div role="status" aria-label="Se încarcă pista">
      <Breadcrumb id={id} />
      <Skeleton className="h-9 w-80" />
      <Skeleton className="mt-3 h-5 w-full max-w-[60ch]" />
      <Skeleton className="mt-2 h-4 w-64" />
      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Skeleton className="h-[22rem] w-full rounded-lg" />
          <Skeleton className="h-48 w-full rounded-lg" />
        </div>
        <div className="space-y-6">
          <Skeleton className="h-44 w-full rounded-lg" />
          <Skeleton className="h-56 w-full rounded-lg" />
          <Skeleton className="h-64 w-full rounded-lg" />
        </div>
      </div>
    </div>
  );
}

export default function LeadPage() {
  const { leadId = "" } = useParams<{ leadId: string }>();
  const id = leadId;
  const api = useApi();
  const live = useLead(id);
  const { detail } = live;
  const now = useNowTick(30_000);
  const reduced = usePrefersReducedMotion();

  const [tab, setTab] = useState<LeadTab>("rts");
  const [highlight, setHighlight] = useState<{ id: string; n: number } | null>(null);
  const tabsRef = useRef<HTMLDivElement>(null);
  const onCite = useCallback(
    (factId: string) => {
      setTab("probe");
      setHighlight((h) => ({ id: factId, n: (h?.n ?? 0) + 1 }));
      window.requestAnimationFrame(() => {
        const el = tabsRef.current;
        if (!el) return;
        const r = el.getBoundingClientRect();
        if (r.top < 0 || r.top > window.innerHeight - 160) el.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
      });
    },
    [reduced],
  );
  const factMap = useMemo(() => new Map(live.facts.map((f) => [f.fact_id, f.summary])), [live.facts]);
  const factTitle = useCallback((fid: string) => factMap.get(fid) ?? undefined, [factMap]);

  const graphKey = useMemo(() => {
    try {
      return JSON.stringify(detail?.graph ?? null);
    } catch {
      return "x";
    }
  }, [detail?.graph]);
  const firstAccount = detail?.lead?.accounts?.[0]?.account ?? "";
  const subjectIds = useMemo(
    () => subjectIdsOf(detail?.graph, detail?.lead),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [graphKey, firstAccount],
  );
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const sentence = useMemo(() => describeFlow(detail?.graph, subjectIds), [graphKey, subjectIds]);

  const [rerun, setRerun] = useState<{ busy: boolean; error: string | null }>({ busy: false, error: null });
  const doRerun = async () => {
    setRerun({ busy: true, error: null });
    try {
      await api.amlRunLead(id);
      live.resetStream();
      await live.reload();
      setRerun({ busy: false, error: null });
    } catch (e) {
      setRerun({ busy: false, error: e instanceof Error ? e.message : String(e) });
    }
  };

  if (!detail) {
    if (live.error) {
      if (live.error instanceof ApiError && live.error.status === 404) {
        return (
          <div>
            <Breadcrumb id={id} />
            <EmptyState
              icon={<Waypoints aria-hidden className="size-5" />}
              title={`Pista ${id} nu există.`}
              action={
                <Link to="/" className="font-semibold underline">
                  Înapoi la piste
                </Link>
              }
            >
              Poate a fost ștearsă la o resetare a demo-ului sau linkul e greșit.
            </EmptyState>
          </div>
        );
      }
      return (
        <div>
          <Breadcrumb id={id} />
          <ErrorNote error={live.error} what="pista" onRetry={() => void live.reload()} />
        </div>
      );
    }
    return <LeadSkeleton id={id} />;
  }

  const lead = detail.lead ?? { lead_id: id, case_ids: [] };
  const cases = Array.isArray(lead.case_ids) ? lead.case_ids : [];
  const subjectNode = (detail.graph?.nodes ?? []).find((n) => n?.id === subjectIds[0]);
  const account = firstAccount || subjectNode?.label || subjectNode?.id || null;
  const extraSubjects = Math.max(0, subjectIds.length - 1);
  const recommendation = typeof lead.recommendation === "string" ? lead.recommendation : null;
  const lastTs = live.events.length ? tsOf(live.events[live.events.length - 1].ts) : null;
  const runningSteps = live.steps.filter((s) => s.status === "running").map((s) => s.label);
  const graphBuilding = live.steps.some((s) => s.id === "graf_ml" && s.status === "running");
  const pending = Boolean(live.interrupt?.pending);

  const fallbackSentence = graphBuilding
    ? "Agenții construiesc graful banilor; rezumatul apare imediat după."
    : cases.length
      ? `${roCount(cases.length, "O contestație e legată", "contestații sunt legate")} de această pistă; graful banilor nu are încă fluxuri.`
      : "Pista nu are încă fapte primite prin diodă.";

  return (
    <div>
      <Breadcrumb id={id} />

      <header className="mb-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
              <h1 className="text-[1.6rem] leading-tight font-bold">
                {account ? (
                  <span className="font-mono tracking-tight">{maskAccount(account)}</span>
                ) : (
                  <>
                    Pista <span className="font-mono">{id}</span>
                  </>
                )}
                {extraSubjects > 0 && <span className="ml-2 text-[1rem] font-semibold text-muted">+{roCount(extraSubjects, "un cont", "conturi")}</span>}
              </h1>
              <LeadStatusBadge status={live.status?.key ?? live.status?.label ?? null} />
              {recommendation && <Badge tone="neutral">Recomandare: {verdictLabel(recommendation)}</Badge>}
            </div>
            <p className="mt-2 max-w-[90ch] text-[1.0667rem]">{sentence ?? fallbackSentence}</p>
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2 text-[0.8667rem] text-muted">
              <span>{roCount(cases.length, "o contestație", "contestații")}</span>
              {cases.slice(0, 4).map((c) => (
                <IdTag key={c}>{c}</IdTag>
              ))}
              {cases.length > 4 && <span>+{cases.length - 4}</span>}
              {lastTs !== null && <span title={dateTime(lastTs)}>ultima activitate {relative(lastTs, now)}</span>}
              {runningSteps.length > 0 && (
                <span className="inline-flex items-center gap-1.5 font-semibold text-ink">
                  <Dot tone="now" live />
                  Agenții lucrează: {runningSteps.join(", ")}
                </span>
              )}
            </div>
          </div>
          {!pending && live.status?.key !== "EROARE" && (
            <div className="flex flex-col items-end gap-1">
              <Button
                size="sm"
                icon={live.hasRun ? <RotateCw aria-hidden className="size-3.5" /> : <Play aria-hidden className="size-3.5" />}
                busy={rerun.busy}
                disabled={live.running}
                onClick={() => void doRerun()}
                title={live.running ? "Agenții lucrează deja pe această pistă" : undefined}
              >
                {live.hasRun ? "Rulează din nou" : "Pornește investigația"}
              </Button>
              {rerun.error && (
                <p role="alert" className="flex items-center gap-1 text-[0.8667rem] font-semibold text-danger">
                  <TriangleAlert aria-hidden className="size-3.5" />
                  Nu a pornit: {rerun.error}
                </p>
              )}
            </div>
          )}
        </div>
      </header>

      <StaleNote error={live.error} every="3 s" />

      <SectionBoundary label="Decizia ta">
        <DecisionArea
          leadId={id}
          interrupt={live.interrupt}
          status={live.status}
          recommendation={recommendation}
          decision={live.decision}
          runError={live.runError}
          onChanged={() => void live.reload()}
          onRerun={() => void doRerun()}
          rerunBusy={rerun.busy}
        />
      </SectionBoundary>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="min-w-0 space-y-6 lg:col-span-2">
          <SectionBoundary label="Drumul banilor">
            <FlowGraph graph={detail.graph} lead={lead} building={graphBuilding} />
          </SectionBoundary>
          <div ref={tabsRef} className="scroll-mt-4">
            <SectionBoundary label="Ciornă RTS, OSINT și probe">
              <LeadTabs
                tab={tab}
                onTab={setTab}
                detail={detail}
                facts={live.facts}
                highlight={highlight}
                onCite={onCite}
                factTitle={factTitle}
                running={live.running}
              />
            </SectionBoundary>
          </div>
        </div>

        <div className="min-w-0 space-y-6">
          <SectionBoundary label="Scor M5">
            <ScorePanel accounts={lead.accounts} />
          </SectionBoundary>
          <SectionBoundary label="Pentru și contra">
            <AchPanel
              innocentDetail={detail.innocent_detail}
              innocent={Array.isArray(detail.innocent) && detail.innocent.length ? detail.innocent : lead.innocent_hypotheses}
              typologyDetail={detail.typologies_detail}
              typologyNames={lead.typologies}
              onCite={onCite}
              factTitle={factTitle}
            />
          </SectionBoundary>
          <SectionBoundary label="Ceasuri">
            <ClocksPanel clocks={detail.clocks} />
          </SectionBoundary>
          <SectionBoundary label="Pașii agenților">
            <StepsPanel steps={live.steps} streamStatus={live.streamStatus} hasRun={live.hasRun} />
          </SectionBoundary>
        </div>
      </div>
    </div>
  );
}
