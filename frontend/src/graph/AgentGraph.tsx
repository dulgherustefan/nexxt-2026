import "@xyflow/react/dist/style.css";
import {
  Handle,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { Check, CircleSlash, Hand, Pause, Play, RotateCcw, Wrench, X } from "lucide-react";
import { memo, useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { clock } from "../api/format";
import type { AgentEvent, PipelineEdge, PipelineNode } from "../api/types";
import { reduceNodeStates, type LiveNodeState } from "../lib/pipeline";
import { Button, cx, Dot, STEP_STATUS_LABEL } from "../ui/kit";
import { ModelBadge } from "../ui/viz";
import { handlesFor, layoutPipeline, NODE_H, NODE_W } from "./layout";

// ------------------------------------------------------------------ nodul

interface AgentData extends Record<string, unknown> {
  label: string;
  model?: string | null;
  status: string;
  tools: number;
  summary?: string;
  hint?: string;
  selected: boolean;
}

const SIDES: Array<[Position, string]> = [
  [Position.Top, "top"],
  [Position.Bottom, "bottom"],
  [Position.Left, "left"],
  [Position.Right, "right"],
];

function StatusGlyph({ status }: { status: string }) {
  switch (status) {
    case "done":
      return <span className="grid size-4 place-items-center rounded-full bg-ink text-paper"><Check className="size-2.5" strokeWidth={3.5} /></span>;
    case "running":
      return <Dot tone="now" live />;
    case "waiting":
      return <span className="grid size-4 place-items-center rounded-full border border-ink bg-yellow"><Hand className="size-2.5" strokeWidth={2.5} /></span>;
    case "blocked":
    case "error":
      return <span className="grid size-4 place-items-center rounded-full bg-danger text-paper"><X className="size-2.5" strokeWidth={3.5} /></span>;
    case "skipped":
      return <span className="grid size-4 place-items-center rounded-full border border-dashed border-line-strong text-subtle"><CircleSlash className="size-2.5" /></span>;
    default:
      return <span className="block size-4 rounded-full border border-line-strong bg-paper" />;
  }
}

const AgentNode = memo(function AgentNode({ data }: NodeProps<Node<AgentData>>) {
  const s = data.status;
  return (
    <div
      title={[data.hint, data.summary].filter(Boolean).join("\n")}
      className={cx(
        "relative flex flex-col justify-between rounded-md border px-2.5 py-1.5 transition-colors duration-300",
        s === "running" && "animate-glow border-yellow-line bg-yellow",
        s === "waiting" && "animate-glow border-yellow-line bg-yellow-soft",
        s === "done" && "border-line-strong bg-paper",
        (s === "blocked" || s === "error") && "border-danger bg-danger-soft",
        s === "skipped" && "border-dashed border-line bg-canvas opacity-60",
        s === "idle" && "border-dashed border-line-strong bg-paper/70",
        data.selected && "ring-2 ring-ink ring-offset-1",
      )}
      style={{ width: NODE_W, height: NODE_H }}
    >
      {SIDES.map(([pos, id]) => (
        <span key={id}>
          <Handle type="target" position={pos} id={`t-${id}`} className="!size-1 !min-h-0 !min-w-0 !border-0 !bg-transparent" isConnectable={false} />
          <Handle type="source" position={pos} id={`s-${id}`} className="!size-1 !min-h-0 !min-w-0 !border-0 !bg-transparent" isConnectable={false} />
        </span>
      ))}
      <div className="flex items-center justify-between gap-1.5">
        <span className={cx("truncate text-[0.8rem] font-semibold leading-tight", s === "idle" && "text-muted")}>{data.label}</span>
        <StatusGlyph status={s} />
      </div>
      <div className="flex items-center justify-between gap-1">
        <ModelBadge model={data.model} />
        {data.tools > 0 && (
          <span className="inline-flex items-center gap-0.5 text-[0.7rem] text-muted tabular-nums" title={`${data.tools} apeluri de tool`}>
            <Wrench className="size-2.5" /> {data.tools}
          </span>
        )}
      </div>
    </div>
  );
});

const nodeTypes = { agent: AgentNode };

// ------------------------------------------------------------------ rejucarea

const MAX_GAP_MS = 2200;
const REPLAY_MS = 14_000;

function virtualTimes(events: AgentEvent[]): number[] {
  const out: number[] = [];
  let prev: number | null = null;
  let acc = 0;
  for (const e of events) {
    const t = new Date(e.ts).getTime();
    if (prev !== null && Number.isFinite(t)) acc += Math.min(Math.max(t - prev, 0), MAX_GAP_MS);
    if (Number.isFinite(t)) prev = t;
    out.push(acc);
  }
  return out;
}

/** Ultima rulare: de la ultimul RUN_STARTED încolo (reluările după semnătură rămân în aceeași rulare). */
function lastRunEvents(events: AgentEvent[]): AgentEvent[] {
  let i = events.length - 1;
  while (i >= 0 && events[i].type !== "RUN_STARTED") i--;
  return i >= 0 ? events.slice(i) : events;
}

function useReplay(events: AgentEvent[]) {
  const [state, setState] = useState<{ on: boolean; paused: boolean; elapsed: number }>({ on: false, paused: false, elapsed: 0 });
  const run = useMemo(() => lastRunEvents(events), [events]);
  const vt = useMemo(() => virtualTimes(run), [run]);
  const total = vt.length ? vt[vt.length - 1] : 0;
  const factor = Math.max(1, total / REPLAY_MS);
  useEffect(() => {
    if (!state.on || state.paused) return;
    const t = window.setInterval(() => {
      setState((s) => {
        const elapsed = s.elapsed + 100;
        if (elapsed * factor >= total + 400) return { on: false, paused: false, elapsed: 0 };
        return { ...s, elapsed };
      });
    }, 100);
    return () => window.clearInterval(t);
  }, [state.on, state.paused, factor, total]);
  const visible = useMemo(() => {
    if (!state.on) return null;
    const limit = state.elapsed * factor;
    const n = vt.findIndex((v) => v > limit);
    return run.slice(0, n === -1 ? run.length : n);
  }, [state.on, state.elapsed, factor, run, vt]);
  return {
    active: state.on,
    paused: state.paused,
    progress: state.on && total ? Math.min(1, (state.elapsed * factor) / total) : 0,
    visible,
    canReplay: run.length > 3,
    start: () => setState({ on: true, paused: false, elapsed: 0 }),
    toggle: () => setState((s) => ({ ...s, paused: !s.paused })),
    stop: () => setState({ on: false, paused: false, elapsed: 0 }),
  };
}

// ------------------------------------------------------------------ graful

function FitOnResize({ boxRef, deps }: { boxRef: RefObject<HTMLDivElement | null>; deps: unknown }) {
  const rf = useReactFlow();
  useEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    let raf = 0;
    const ro = new ResizeObserver(() => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => void rf.fitView({ padding: 0.08, duration: 200 }));
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [rf, boxRef, deps]);
  return null;
}

export interface AgentGraphProps {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  events: AgentEvent[];
  title?: string;
  height?: number;
  /** Rularea e încheiată: nodurile care n-au pornit nu se aplică acestui caz. */
  settled?: boolean;
  /** Afișează etichetele etapelor în stânga (graful Judecătorului). */
  rowLabels?: boolean;
  /** Pentru grafurile fără grilă proprie: straturi de sus în jos sau de la stânga la dreapta. */
  direction?: "TB" | "LR";
}

function edgeState(a: LiveNodeState | undefined, b: LiveNodeState | undefined): "flow" | "done" | "blocked" | "idle" {
  if (!a || !b) return "idle";
  if (b.status === "blocked" || b.status === "error") return "blocked";
  if ((b.status === "running" || b.status === "waiting") && (a.status === "done" || a.status === "running")) return "flow";
  if (a.status === "running" && b.status === "idle") return "flow";
  if (a.status === "done" && (b.status === "done" || b.status === "skipped")) return "done";
  return "idle";
}

function Inner({ nodes, edges, events, title = "Agenții, live", height = 520, settled = false, rowLabels = true, direction = "TB" }: AgentGraphProps) {
  const box = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const replay = useReplay(events);
  const shownEvents = replay.visible ?? events;
  const baseNodes = useMemo(() => (replay.active ? nodes.map((n) => ({ ...n, status: "idle" })) : nodes), [nodes, replay.active]);
  const states = useMemo(() => reduceNodeStates(baseNodes, shownEvents), [baseNodes, shownEvents]);
  const ids = useMemo(() => nodes.map((n) => n.id), [nodes]);
  const { pos, rows, mode } = useMemo(() => layoutPipeline(ids, edges, direction), [ids, edges, direction]);

  const effective = (id: string) => {
    const st = states[id]?.status ?? "idle";
    return settled && !replay.active && st === "idle" ? "skipped" : st;
  };

  const rfNodes: Node<AgentData>[] = useMemo(
    () =>
      nodes.map((n) => {
        const st = states[n.id];
        const server = n.summary;
        return {
          id: n.id,
          type: "agent",
          position: { x: pos[n.id]?.x ?? 0, y: pos[n.id]?.y ?? 0 },
          draggable: false,
          selectable: true,
          data: {
            label: n.label,
            model: n.model,
            status: effective(n.id),
            tools: st?.tools ?? 0,
            summary: replay.active ? st?.live : st?.live ?? server,
            hint: n.hint,
            selected: selected === n.id,
          },
        };
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [nodes, states, pos, selected, settled, replay.active],
  );

  const rfEdges: Edge[] = useMemo(
    () =>
      edges
        .filter((e) => pos[e.source] && pos[e.target])
        .map((e) => {
          const kind = edgeState(states[e.source], states[e.target]);
          const h = handlesFor(pos[e.source], pos[e.target], mode);
          const stroke = kind === "blocked" ? "var(--color-danger)" : kind === "idle" ? "var(--color-line-strong)" : kind === "flow" ? "var(--color-ink)" : "var(--color-ink-soft)";
          return {
            id: `${e.source}->${e.target}`,
            source: e.source,
            target: e.target,
            ...h,
            type: "smoothstep",
            animated: kind === "flow",
            style: { stroke, strokeWidth: kind === "flow" ? 2.5 : kind === "done" ? 1.5 : 1.25, strokeDasharray: kind === "idle" ? "4 5" : undefined },
          };
        }),
    [edges, states, pos, mode],
  );

  const all = nodes.map((n) => effective(n.id));
  const done = all.filter((s) => s === "done" || s === "skipped").length;
  const running = nodes.filter((n) => effective(n.id) === "running");
  const waiting = nodes.find((n) => effective(n.id) === "waiting");
  const lastMsg = [...shownEvents].reverse().find((e) => e.message && e.type !== "RUN_FINISHED");
  const sel = selected ? nodes.find((n) => n.id === selected) : null;
  const selState = selected ? states[selected] : undefined;

  return (
    <section aria-label="Graful agenților" className="flex flex-col overflow-hidden rounded-lg border border-line bg-paper">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2.5">
        <div className="flex items-center gap-2.5">
          <h2 className="font-semibold">{title}</h2>
          <span className="text-[0.8667rem] tabular-nums text-muted">{done}/{nodes.length} pași</span>
          {waiting ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-yellow-soft px-2 text-[0.8rem] font-medium"><Hand className="size-3" /> așteaptă un om</span>
          ) : running.length ? (
            <span className="inline-flex items-center gap-1.5 text-[0.8667rem] font-semibold"><Dot tone="now" live /> {running.length === 1 ? "un agent lucrează" : `${running.length} agenți lucrează`}</span>
          ) : null}
        </div>
        <div className="flex items-center gap-1.5">
          {replay.active && (
            <Button size="sm" variant="ghost" onClick={replay.toggle} icon={replay.paused ? <Play className="size-3.5" /> : <Pause className="size-3.5" />}>
              {replay.paused ? "Continuă" : "Pauză"}
            </Button>
          )}
          <Button
            size="sm"
            variant="secondary"
            disabled={!replay.canReplay}
            onClick={replay.active ? replay.stop : replay.start}
            icon={<RotateCcw className="size-3.5" />}
            title={replay.canReplay ? "Rulează din nou animația, din evenimentele salvate" : "Nu există încă o rulare de rejucat"}
          >
            {replay.active ? "Oprește" : "Rejoacă"}
          </Button>
        </div>
      </header>
      {replay.active && (
        <div className="h-1 bg-hover" aria-hidden>
          <div className="h-1 bg-ink transition-[width] duration-100" style={{ width: `${replay.progress * 100}%` }} />
        </div>
      )}
      <div ref={box} className="relative bg-canvas/40" style={{ height }}>
        {rowLabels && rows.length > 0 && (
          <div className="pointer-events-none absolute top-2 left-3 z-10 hidden flex-col gap-1 text-[0.75rem] font-semibold text-subtle 2xl:flex">
            {rows.map((r) => <span key={r.row}>{r.row + 1}. {r.label}</span>)}
          </div>
        )}
        <ReactFlow
          nodes={rfNodes}
          edges={rfEdges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.08 }}
          minZoom={0.3}
          maxZoom={1.6}
          zoomOnScroll={false}
          preventScrolling={false}
          panOnScroll={false}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable
          onNodeClick={(_, n) => setSelected((s) => (s === n.id ? null : n.id))}
          onPaneClick={() => setSelected(null)}
          proOptions={{ hideAttribution: true }}
        >
          <FitOnResize boxRef={box} deps={nodes.length} />
        </ReactFlow>
      </div>
      <footer className="border-t border-line px-4 py-2.5 text-[0.9333rem]">
        {sel ? (
          <div>
            <p className="flex flex-wrap items-center gap-2 font-semibold">
              {sel.label} <ModelBadge model={sel.model} />
              <span className="text-[0.8667rem] font-normal text-muted">{STEP_STATUS_LABEL[effective(sel.id)] ?? effective(sel.id)}</span>
              {selState?.tools ? <span className="text-[0.8667rem] font-normal text-muted">· {selState.tools} tool-uri{selState.lastTool ? `, ultimul ${selState.lastTool}` : ""}</span> : null}
            </p>
            {sel.hint && <p className="text-[0.8667rem] text-muted">{sel.hint}</p>}
            {(selState?.live ?? sel.summary) && <p className="mt-0.5 text-ink-soft">{selState?.live ?? sel.summary}</p>}
          </div>
        ) : lastMsg ? (
          <p className="flex min-w-0 items-baseline gap-2" aria-live="polite">
            <span className="shrink-0 font-mono text-[0.8rem] text-muted tabular-nums">{clock(lastMsg.ts)}</span>
            <span className="shrink-0 font-semibold">{(lastMsg.agent ?? "").split("/").pop() || "Sistem"}</span>
            <span className="min-w-0 truncate text-ink-soft">{lastMsg.message}</span>
          </p>
        ) : (
          <p className="text-muted">Apasă pe un agent ca să vezi ce face. Graful se aprinde pe măsură ce agenții lucrează.</p>
        )}
      </footer>
    </section>
  );
}

export default function AgentGraph(props: AgentGraphProps) {
  return (
    <ReactFlowProvider>
      <Inner {...props} />
    </ReactFlowProvider>
  );
}
