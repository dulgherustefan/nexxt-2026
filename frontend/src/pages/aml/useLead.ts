import { useCallback, useEffect, useMemo, useRef } from "react";
import { useApi, useResource } from "../../api/runtime";
import { useEventStream, type StreamStatus } from "../../api/sse";
import type { AgentEvent, Interrupt, LeadDetail } from "../../api/types";
import {
  collectFacts,
  deriveInterrupt,
  deriveStatus,
  lastDecision,
  lastRunError,
  latestRunId,
  leadStatus,
  mergeEvents,
  resolveSteps,
  type DecisionInfo,
  type FactRow,
  type LeadStatusInfo,
  type StepView,
} from "./aml";

const EMPTY: AgentEvent[] = [];
const RELOAD_TYPES = new Set(["RUN_STARTED", "STEP_FINISHED", "RUN_FINISHED", "RUN_ERROR"]);
const RELOAD_CUSTOM = new Set(["interrupt", "decision", "hold_signal", "ledger_seal", "fact", "typology"]);

export interface LeadLive {
  detail: LeadDetail | undefined;
  error: Error | undefined;
  loading: boolean;
  reload: () => Promise<void>;
  events: AgentEvent[];
  streamStatus: StreamStatus;
  resetStream: () => void;
  steps: StepView[];
  status: LeadStatusInfo | null;
  interrupt: Interrupt | null;
  decision: DecisionInfo | null;
  runError: string | null;
  facts: FactRow[];
  running: boolean;
  hasRun: boolean;
}

/**
 * Pista, vie: detaliul sondat la 3 s (rezerva sigură) plus evenimentele SSE (pașii bifați pe loc).
 * Un eveniment care schimbă datele (pas terminat, probă, întrerupere) cere imediat o reîncărcare.
 * Dacă SSE cade, polling-ul și `timeline` din detaliu țin pagina la zi.
 */
export function useLead(id: string): LeadLive {
  const api = useApi();
  const res = useResource(() => api.amlLead(id), [api, id], { pollMs: 3000 });
  const detail = res.data;
  const timeline = Array.isArray(detail?.timeline) ? detail!.timeline : EMPTY;
  const runId = latestRunId(timeline);

  // Modul mock nu pune starea în detaliu; o luăm din listă doar dacă lipsește și din evenimente.
  const needList = Boolean(detail) && !detail?.status;
  const list = useResource(needList ? () => api.amlLeads() : null, [api, needList], { pollMs: needList ? 5000 : undefined });

  const reloadRef = useRef(res.reload);
  reloadRef.current = res.reload;
  const timer = useRef<number | null>(null);
  const reloadSoon = useCallback(() => {
    if (timer.current !== null) return;
    timer.current = window.setTimeout(() => {
      timer.current = null;
      void reloadRef.current();
    }, 350);
  }, []);
  useEffect(
    () => () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
    },
    [],
  );

  const source = useMemo(() => api.leadEvents(id), [api, id]);
  // cheia include rularea: la o rulare nouă ne reconectăm, iar serverul retrimite istoricul ei
  const stream = useEventStream(detail ? source : null, detail ? `${id}:${runId ?? "-"}` : null, (e, isReplay) => {
    if (isReplay) return;
    if (RELOAD_TYPES.has(e.type) || (e.type === "CUSTOM" && typeof e.name === "string" && RELOAD_CUSTOM.has(e.name))) reloadSoon();
  });

  const events = useMemo(() => mergeEvents(timeline, stream.events), [timeline, stream.events]);
  const steps = useMemo(() => resolveSteps(detail?.pipeline?.nodes, events), [detail?.pipeline?.nodes, events]);
  const facts = useMemo(() => collectFacts(detail?.facts, events, Array.isArray(detail?.osint) ? detail!.osint : []), [detail?.facts, detail?.osint, events]);

  const listStatus = needList && Array.isArray(list.data) ? list.data.find((l) => l?.lead_id === id)?.status ?? null : null;
  const status = leadStatus(detail?.status ?? null) ?? leadStatus(deriveStatus(events)) ?? leadStatus(listStatus);
  const interrupt = detail?.interrupt ?? deriveInterrupt(events);
  const running = steps.some((s) => s.status === "running") || status?.key === "IN_ANALIZA";
  const hasRun = events.some((e) => e.type === "RUN_STARTED") || steps.some((s) => s.status !== "idle");

  return {
    detail,
    error: res.error,
    loading: res.loading,
    reload: res.reload,
    events,
    streamStatus: stream.status,
    resetStream: stream.reset,
    steps,
    status,
    interrupt,
    decision: lastDecision(events, interrupt),
    runError: lastRunError(events),
    facts,
    running,
    hasRun,
  };
}
