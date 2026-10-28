/**
 * Pagina unei piste: antetul (contul, scorul, recomandarea), bara de decizie, graful banilor
 * și, la cerere, tiparele, OSINT, ipotezele nevinovate, ciorna RTS, ceasurile și agenții.
 */
import { Play, RotateCw, TriangleAlert, Waypoints } from "lucide-react";
import { lazy, Suspense, useCallback, useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { ApiError } from "../../api/client";
import { dateTime, relative, verdictLabel } from "../../api/format";
import { useApi } from "../../api/runtime";
import { Badge, Breadcrumb, Button, Collapsible, Dot, EmptyState, ErrorNote, SectionBoundary, Skeleton, useNowTick } from "../../ui/kit";
import { Gauge } from "../../ui/viz";
import { maskAccount, roCount, tsOf, typologyLabel } from "./aml";
import { DecisionArea } from "./DecisionPanel";
import { describeFlow, subjectIdsOf } from "./flow";
import { AchPanel, ScorePanel } from "./LeadPanels";
import { OsintTab, ProbeTab, RtsTab } from "./LeadTabs";
import { ClockBars, TypologyChips } from "./LeadVisuals";
import { LeadStatusBadge, StaleNote } from "./ui";
import { useLead } from "./useLead";

const MoneyGraph = lazy(() => import("../../graph/MoneyGraph"));
const AgentGraph = lazy(() => import("../../graph/AgentGraph"));

type SectionId = "tipare" | "osint" | "ipoteze" | "rts" | "ceasuri" | "agenti" | "probe";

function LeadSkeleton({ id }: { id: string }) {
  return (
    <div role="status" aria-label="Se încarcă pista">
      <Breadcrumb items={[{ label: "Piste", to: "/aml" }, { label: id || "—" }]} />
      <Skeleton className="h-9 w-80" />
      <Skeleton className="mt-3 h-5 w-full max-w-[60ch]" />
      <Skeleton className="mt-6 h-20 w-full rounded-lg" />
      <Skeleton className="mt-6 h-[26rem] w-full rounded-lg" />
    </div>
  );
}

export default function LeadPage() {
  const { leadId = "" } = useParams<{ leadId: string }>();
  return <LeadRoom leadId={leadId} />;
}

export function LeadRoom({ leadId, compact = false }: { leadId: string; compact?: boolean }) {
  const id = leadId;
  const api = useApi();
  const live = useLead(id);
  const { detail } = live;
  const now = useNowTick(30_000);
  const [open, setOpen] = useState<Partial<Record<SectionId, boolean>>>({});
  const [highlight, setHighlight] = useState<{ id: string; n: number } | null>(null);

  const onCite = useCallback((factId: string) => {
    setOpen((o) => ({ ...o, probe: true }));
    setHighlight((h) => ({ id: factId, n: (h?.n ?? 0) + 1 }));
    window.setTimeout(() => document.getElementById("lead-probe")?.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
  }, []);
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
            {!compact && <Breadcrumb items={[{ label: "Piste", to: "/aml" }, { label: id || "—" }]} />}
            <EmptyState icon={<Waypoints aria-hidden className="size-5" />} title={`Pista ${id} nu există.`}
              action={<Link to="/aml" className="font-semibold underline">Înapoi la piste</Link>}>
              Poate a dispărut la o resetare a demo-ului sau linkul e greșit.
            </EmptyState>
          </div>
        );
      }
      return (
        <div>
          {!compact && <Breadcrumb items={[{ label: "Piste", to: "/aml" }, { label: id || "—" }]} />}
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
  const topScore = lead.accounts?.[0]?.score ?? null;
  const typNames = (Array.isArray(detail.typologies_detail) && detail.typologies_detail.length
    ? detail.typologies_detail.map((t) => String(t.typology ?? t.name ?? ""))
    : lead.typologies ?? []).filter(Boolean);
  const osint = Array.isArray(detail.osint) ? detail.osint.filter(Boolean) : [];
  const innocent = Array.isArray(detail.innocent_detail) && detail.innocent_detail.length ? detail.innocent_detail.length : (Array.isArray(detail.innocent) ? detail.innocent.length : 0);
  const done = live.steps.filter((s) => s.status === "done" || s.status === "skipped").length;
  const toggle = (k: SectionId) => (v: boolean) => setOpen((o) => ({ ...o, [k]: v }));

  const fallbackSentence = graphBuilding
    ? "Agenții construiesc graful banilor."
    : cases.length
      ? `${roCount(cases.length, "O contestație e legată", "contestații sunt legate")} de pistă. Graful nu are încă fluxuri.`
      : "Pista nu are încă fapte primite din zona client.";

  return (
    <div className="mx-auto w-full max-w-[1100px]">
      {!compact && <Breadcrumb items={[{ label: "Piste", to: "/aml" }, { label: id }]} />}

      <header className="mb-6 flex flex-wrap items-start justify-between gap-x-6 gap-y-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-[1.5rem] leading-tight font-semibold">
              {account ? <span className="font-mono tracking-tight">{maskAccount(account)}</span> : <>Pista <span className="font-mono">{id}</span></>}
              {extraSubjects > 0 && <span className="ml-2 text-[0.9333rem] font-normal text-muted">+{roCount(extraSubjects, "un cont", "conturi")}</span>}
            </h1>
            <LeadStatusBadge status={live.status?.key ?? live.status?.label ?? null} />
            {recommendation && <Badge tone="neutral">Regulile recomandă: {verdictLabel(recommendation)}</Badge>}
          </div>
          <p className="mt-2 max-w-[80ch] text-[0.9333rem] text-ink-soft">{sentence ?? fallbackSentence}</p>
          <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.8667rem] text-muted">
            <span>{roCount(cases.length, "o contestație", "contestații")}{cases.length ? `: ${cases.slice(0, 3).join(", ")}${cases.length > 3 ? ` +${cases.length - 3}` : ""}` : ""}</span>
            {lastTs !== null && <span title={dateTime(lastTs)}>· activ {relative(lastTs, now)}</span>}
            {runningSteps.length > 0 && <span className="inline-flex items-center gap-1.5 font-medium text-ink"><Dot tone="now" live /> Agenții lucrează: {runningSteps.join(", ")}</span>}
          </p>
        </div>
        <div className="flex items-start gap-4">
          <Gauge value={topScore} size={96} label="scor cărăuș" />
          {!pending && live.status?.key !== "EROARE" && (
            <div className="flex flex-col items-end gap-1 pt-1">
              <Button size="sm" icon={live.hasRun ? <RotateCw aria-hidden className="size-3.5" /> : <Play aria-hidden className="size-3.5" />}
                busy={rerun.busy} disabled={live.running} onClick={() => void doRerun()} title={live.running ? "Agenții lucrează deja pe această pistă" : undefined}>
                {live.hasRun ? "Rulează din nou" : "Pornește investigația"}
              </Button>
              {rerun.error && (
                <p role="alert" className="flex items-center gap-1 text-[0.8667rem] font-medium text-danger">
                  <TriangleAlert aria-hidden className="size-3.5" /> {rerun.error}
                </p>
              )}
            </div>
          )}
        </div>
      </header>

      <StaleNote error={live.error} every="3 s" />

      <SectionBoundary label="Decizia ta">
        <DecisionArea leadId={id} interrupt={live.interrupt} status={live.status} recommendation={recommendation} decision={live.decision}
          runError={live.runError} onChanged={() => void live.reload()} onRerun={() => void doRerun()} rerunBusy={rerun.busy} />
      </SectionBoundary>

      <SectionBoundary label="Drumul banilor">
        <Suspense fallback={<Skeleton className="h-[28rem] w-full rounded-lg" />}>
          <MoneyGraph graph={detail.graph} lead={lead} building={graphBuilding} />
        </Suspense>
      </SectionBoundary>

      <div className="mt-8 border-y border-line">
        <Collapsible title="Tipare găsite" meta={typNames.length ? typNames.map(typologyLabel).join(", ") : "niciunul încă"} open={Boolean(open.tipare)} onToggle={toggle("tipare")}>
          <div className="flex flex-col gap-6">
            <SectionBoundary label="Tipologii"><TypologyChips detail={detail.typologies_detail} names={lead.typologies} /></SectionBoundary>
            <div>
              <p className="mb-2 text-[0.8667rem] font-semibold text-muted">De unde vine scorul</p>
              <SectionBoundary label="Scor"><ScorePanel accounts={lead.accounts} /></SectionBoundary>
            </div>
          </div>
        </Collapsible>
        <Collapsible title="Verificări OSINT" meta={osint.length ? roCount(osint.length, "un rezultat", "rezultate") : "niciuna încă"} open={Boolean(open.osint)} onToggle={toggle("osint")}>
          <SectionBoundary label="OSINT"><OsintTab findings={osint} summary={detail.osint_summary} onCite={onCite} factTitle={factTitle} running={live.running} /></SectionBoundary>
        </Collapsible>
        <Collapsible title="Ipoteze nevinovate" meta={innocent ? roCount(innocent, "o ipoteză", "ipoteze") : "nu a rulat"} open={Boolean(open.ipoteze)} onToggle={toggle("ipoteze")}>
          <SectionBoundary label="Ipoteze">
            <AchPanel showTypologies={false} innocentDetail={detail.innocent_detail}
              innocent={Array.isArray(detail.innocent) && detail.innocent.length ? detail.innocent : lead.innocent_hypotheses}
              typologyDetail={detail.typologies_detail} typologyNames={lead.typologies} onCite={onCite} factTitle={factTitle} />
          </SectionBoundary>
        </Collapsible>
        <Collapsible title="Ciornă RTS" meta={detail.rts?.status ?? "nu există"} open={Boolean(open.rts)} onToggle={toggle("rts")}>
          <SectionBoundary label="Ciornă RTS"><RtsTab rts={detail.rts} onCite={onCite} factTitle={factTitle} running={live.running} /></SectionBoundary>
        </Collapsible>
        <Collapsible title="Ceasuri legale" meta={detail.clocks?.length ? roCount(detail.clocks.length, "un ceas", "ceasuri") : "nepornite"} open={Boolean(open.ceasuri)} onToggle={toggle("ceasuri")}>
          <SectionBoundary label="Ceasuri"><ClockBars clocks={detail.clocks} events={live.events} /></SectionBoundary>
        </Collapsible>
        <Collapsible title="Cum a lucrat Investigatorul" meta={live.steps.length ? `${done}/${live.steps.length} pași` : undefined} open={Boolean(open.agenti)} onToggle={toggle("agenti")}>
          <SectionBoundary label="Agenții Investigatorului">
            <Suspense fallback={<Skeleton className="h-64 w-full rounded-lg" />}>
              <AgentGraph nodes={detail.pipeline?.nodes ?? []} edges={detail.pipeline?.edges ?? []} events={live.events} direction="LR" height={260}
                rowLabels={false} settled={!live.running && !pending && live.hasRun} title="Agenții Investigatorului, live" />
            </Suspense>
          </SectionBoundary>
        </Collapsible>
        <Collapsible id="lead-probe" title="Probe" meta={roCount(live.facts.length, "o probă", "probe")} open={Boolean(open.probe)} onToggle={toggle("probe")}>
          <SectionBoundary label="Probe"><ProbeTab facts={live.facts} highlight={highlight} ledger={detail.ledger} /></SectionBoundary>
        </Collapsible>
      </div>
    </div>
  );
}
