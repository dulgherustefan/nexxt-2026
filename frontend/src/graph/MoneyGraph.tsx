/**
 * Graful banilor (React Flow), de la stânga la dreapta: victime și plătitori → contul urmărit → ieșiri.
 * Grosimea muchiei = suma; culoarea nodului = scorul M5 de cont-cărăuș. „Rejoacă banii” aprinde
 * transferurile în ordinea în care s-au întâmplat.
 */
import "@xyflow/react/dist/style.css";
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  Handle,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { Banknote, Bitcoin, Landmark, Pause, Play, RotateCcw, Store, User, Users } from "lucide-react";
import { memo, useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { dateTime, money } from "../api/format";
import type { AmlLead, MoneyGraph as MoneyGraphData } from "../api/types";
import { buildFlowModel, cleanGraph, type FlowNode, type FlowRole } from "../pages/aml/flow";
import { compactAmount, M5_HIGH, M5_MID, tsOf } from "../pages/aml/aml";
import { Button, cx, EmptyState } from "../ui/kit";

// ------------------------------------------------------------------ nodurile

interface AccData extends Record<string, unknown> {
  n: FlowNode;
  lit: boolean;
  pulse: boolean;
  subject: boolean;
}

const KIND_ICON: Record<string, typeof User> = { victima: User, exchange: Bitcoin, numerar: Banknote, comerciant: Store, grup: Users };

function scoreCls(score: number | null): string {
  if (score === null) return "border-line-strong bg-paper";
  if (score >= M5_HIGH) return "border-danger bg-danger-soft";
  if (score >= M5_MID) return "border-warn bg-warn-soft";
  return "border-ok bg-ok-soft";
}

const KIND_WORD: Record<string, string> = { victima: "victimă", exchange: "exchange cripto", numerar: "numerar", comerciant: "comerciant", cont: "cont", carausi: "cont urmărit", grup: "grup" };

const AccountNode = memo(function AccountNode({ data }: NodeProps<Node<AccData>>) {
  const { n, subject, pulse, lit } = data;
  const Icon = KIND_ICON[n.kind] ?? Landmark;
  const handles = (
    <>
      <Handle type="target" position={Position.Left} className="!size-1 !min-h-0 !min-w-0 !border-0 !bg-transparent" isConnectable={false} />
      <Handle type="source" position={Position.Right} className="!size-1 !min-h-0 !min-w-0 !border-0 !bg-transparent" isConnectable={false} />
    </>
  );
  if (subject) {
    return (
      <div className={cx("flex w-[220px] flex-col rounded-lg border border-yellow-line bg-yellow px-3 py-2.5", pulse && "animate-glow")}>
        {handles}
        <p className="text-[0.75rem] font-medium">Contul urmărit</p>
        <p className="mt-0.5 font-mono text-[0.9333rem] font-semibold">{n.short}</p>
        <p className="mt-1.5 flex items-baseline justify-between gap-2 text-[0.8rem] tabular-nums">
          <span>scor <span className="font-semibold">{n.score === null ? "—" : n.score.toFixed(2).replace(".", ",")}</span></span>
          <span>{compactAmount(n.amountIn)} → {compactAmount(n.amountOut)} lei</span>
        </p>
      </div>
    );
  }
  const victim = n.kind === "victima";
  return (
    <div title={`${n.label} · ${KIND_WORD[n.kind] ?? n.kind}`}
      className={cx("flex w-[188px] items-center gap-2 rounded-lg border px-2.5 py-1.5 transition-opacity duration-300",
        victim ? "border-danger-line bg-paper" : n.kind === "exchange" || n.kind === "numerar" ? "border-ink bg-ink text-paper" : scoreCls(n.score),
        !lit && "opacity-35", pulse && "animate-glow")}>
      {handles}
      <span className={cx("grid size-7 shrink-0 place-items-center rounded-full", victim ? "bg-danger-soft text-danger" : n.kind === "exchange" || n.kind === "numerar" ? "bg-white/15 text-paper" : "bg-paper/80")}>
        <Icon className="size-4" />
      </span>
      <span className="min-w-0 leading-tight">
        <span className={cx("block truncate text-[0.8rem] font-semibold", n.mono && "font-mono")}>{n.short}</span>
        <span className={cx("block truncate text-[0.7rem]", n.kind === "exchange" || n.kind === "numerar" ? "text-white/70" : "text-muted")}>
          {KIND_WORD[n.kind] ?? n.kind}{n.score !== null ? ` · ${n.score.toFixed(2).replace(".", ",")}` : ""}
        </span>
      </span>
    </div>
  );
});

// ------------------------------------------------------------------ muchiile

interface MoneyEdgeData extends Record<string, unknown> {
  amount: number;
  count: number;
  width: number;
  tone: "victim" | "exit" | "plain";
  lit: boolean;
  active: boolean;
  label: string | null;
}

function MoneyEdge({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data }: EdgeProps<Edge<MoneyEdgeData>>) {
  const [path, lx, ly] = getBezierPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition });
  const d = data!;
  const color = d.active ? "var(--color-ink)" : d.tone === "victim" ? "var(--color-danger)" : d.tone === "exit" ? "var(--color-ink)" : "var(--color-line-strong)";
  return (
    <>
      {d.active && <BaseEdge id={`${id}-halo`} path={path} style={{ stroke: "var(--color-yellow)", strokeWidth: d.width + 8, opacity: 0.9 }} />}
      <BaseEdge id={id} path={path} style={{ stroke: color, strokeWidth: d.width, opacity: d.lit ? 0.9 : 0.15, transition: "opacity 300ms" }} />
      {d.active && (
        <circle r={Math.max(5, d.width / 2 + 2)} fill="var(--color-yellow)" stroke="var(--color-ink)" strokeWidth={2}>
          <animateMotion dur="0.9s" repeatCount="indefinite" path={path} />
        </circle>
      )}
      {d.label && d.lit && (
        <EdgeLabelRenderer>
          <div className={cx("nodrag nopan pointer-events-none absolute rounded-sm px-1 text-[0.7rem] font-bold tabular-nums", d.active ? "bg-yellow text-ink" : "bg-paper/90 text-ink-soft")}
            style={{ transform: `translate(-50%, -50%) translate(${lx}px, ${ly}px)` }}>
            {d.label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

const nodeTypes = { acc: AccountNode };
const edgeTypes = { money: MoneyEdge };

// ------------------------------------------------------------------ așezarea

const COL_X: Record<FlowRole, number> = { victim: 0, sender: 0, subject: 320, exit: 660 };
const ROW_H = 64;

function FitOnResize({ boxRef, n }: { boxRef: RefObject<HTMLDivElement | null>; n: number }) {
  const rf = useReactFlow();
  useEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    let raf = 0;
    const ro = new ResizeObserver(() => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => void rf.fitView({ padding: 0.06, duration: 200 }));
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [rf, boxRef, n]);
  return null;
}

export interface MoneyGraphProps {
  graph: MoneyGraphData | null | undefined;
  lead?: AmlLead | null;
  building?: boolean;
  title?: string;
  height?: number;
}

function Inner({ graph, lead, building = false, title = "Drumul banilor", height }: MoneyGraphProps) {
  const box = useRef<HTMLDivElement>(null);
  const model = useMemo(() => buildFlowModel(graph, lead), [graph, lead]);
  const raw = useMemo(() => cleanGraph(graph).edges, [graph]);

  // transferurile individuale, în ordinea timpului, legate de muchia (agregată) din desen
  const flowIdOf = useMemo(() => {
    const m = new Map<string, string>();
    for (const n of model.nodes.values()) for (const mem of n.members) m.set(mem.id, n.id);
    return m;
  }, [model]);
  const steps = useMemo(
    () =>
      raw
        .map((e) => ({ e, link: `${flowIdOf.get(e.source)}→${flowIdOf.get(e.target)}`, t: tsOf(e.ts) ?? 0 }))
        .filter((s) => model.links.some((l) => l.id === s.link))
        .sort((a, b) => a.t - b.t),
    [raw, flowIdOf, model.links],
  );

  const [replay, setReplay] = useState<{ on: boolean; i: number; paused: boolean }>({ on: false, i: 0, paused: false });
  useEffect(() => {
    if (!replay.on || replay.paused) return;
    const t = window.setTimeout(() => {
      setReplay((r) => (r.i + 1 >= steps.length ? { on: false, i: 0, paused: false } : { ...r, i: r.i + 1 }));
    }, replay.i === 0 ? 500 : 750);
    return () => window.clearTimeout(t);
  }, [replay, steps.length]);

  const current = replay.on ? steps[replay.i] : null;
  const litLinks = useMemo(() => {
    if (!replay.on) return null;
    return new Set(steps.slice(0, replay.i + 1).map((s) => s.link));
  }, [replay, steps]);
  const litNodes = useMemo(() => {
    if (!litLinks) return null;
    const s = new Set<string>(model.subjectIds);
    for (const l of model.links) if (litLinks.has(l.id)) {
      s.add(l.source);
      s.add(l.target);
    }
    return s;
  }, [litLinks, model]);

  const maxAmount = Math.max(1, ...model.links.map((l) => l.amount));

  const nodes: Node<AccData>[] = useMemo(() => {
    const out: Node<AccData>[] = [];
    const subjectIds = new Set(model.subjectIds);
    const columns = { left: [] as FlowNode[], mid: [] as FlowNode[], right: [] as FlowNode[] };
    for (const col of model.columns) for (const seg of col.segments) for (const n of seg.nodes) {
      (col.key === "sources" ? columns.left : col.key === "subject" ? columns.mid : columns.right).push(n);
    }
    const SUBJ_H = 120;
    const tallest = Math.max(columns.left.length * ROW_H, columns.right.length * ROW_H, columns.mid.length * SUBJ_H, ROW_H);
    const place = (list: FlowNode[], x: number, h: number, nodeH: number) => {
      const start = (tallest - list.length * h) / 2 + (h - nodeH) / 2;
      list.forEach((n, i) => {
        const subject = subjectIds.has(n.id);
        out.push({
          id: n.id,
          type: "acc",
          position: { x, y: start + i * h },
          draggable: false,
          data: { n, subject, lit: !litNodes || litNodes.has(n.id), pulse: Boolean(current && (flowIdOf.get(current.e.target) === n.id)) },
        });
      });
    };
    place(columns.left, COL_X.victim, ROW_H, 48);
    place(columns.mid, COL_X.subject, SUBJ_H, 84);
    place(columns.right, COL_X.exit, ROW_H, 48);
    return out;
  }, [model, litNodes, current, flowIdOf]);

  const edges: Edge<MoneyEdgeData>[] = useMemo(
    () =>
      model.links.map((l) => {
        const src = model.nodes.get(l.source);
        const tgt = model.nodes.get(l.target);
        const tone: MoneyEdgeData["tone"] = src?.kind === "victima" ? "victim" : tgt && (tgt.kind === "exchange" || tgt.kind === "numerar") ? "exit" : "plain";
        const active = Boolean(current && current.link === l.id);
        const label = active && current
          ? `${dateTime(current.e.ts)} · ${money(current.e.amount)}`
          : l.amount >= maxAmount * 0.12 ? `${l.count > 1 ? `${l.count}× · ` : ""}${compactAmount(l.amount)} lei` : null;
        return {
          id: l.id,
          source: l.source,
          target: l.target,
          type: "money",
          data: { amount: l.amount, count: l.count, width: 1.5 + 12 * Math.sqrt(l.amount / maxAmount), tone, lit: !litLinks || litLinks.has(l.id), active, label },
        };
      }),
    [model, maxAmount, litLinks, current],
  );

  if (!model.links.length) {
    return (
      <section className="rounded-lg border border-line bg-paper p-4">
        <h2 className="mb-3 font-semibold">{title}</h2>
        <EmptyState title={building ? "Agenții construiesc graful banilor…" : "Graful nu are încă fluxuri."}>
          Graful apare după ce Investigatorul citește faptele venite prin diodă și tranzacțiile contului.
        </EmptyState>
      </section>
    );
  }
  const rows = Math.max(...model.columns.map((c) => c.segments.reduce((s, g) => s + g.nodes.length * (c.key === "subject" ? 2 : 1), 0)), 4);
  const h = height ?? Math.min(560, Math.max(320, rows * ROW_H + 40));
  const total = steps.reduce((s, x) => s + x.e.amount, 0);
  const shown = replay.on ? steps.slice(0, replay.i + 1).reduce((s, x) => s + x.e.amount, 0) : total;

  return (
    <section aria-label="Graful banilor" className="flex flex-col overflow-hidden rounded-lg border border-line bg-paper">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2.5">
        <div>
          <h2 className="font-semibold">{title}</h2>
          <p className="text-[0.8667rem] text-muted">{steps.length} transferuri · linia mai groasă înseamnă mai mulți bani</p>
        </div>
        <div className="flex items-center gap-1.5">
          {replay.on && (
            <Button size="sm" variant="ghost" onClick={() => setReplay((r) => ({ ...r, paused: !r.paused }))} icon={replay.paused ? <Play className="size-3.5" /> : <Pause className="size-3.5" />}>
              {replay.paused ? "Continuă" : "Pauză"}
            </Button>
          )}
          <Button size="sm" variant="secondary" disabled={steps.length < 2}
            onClick={() => setReplay(replay.on ? { on: false, i: 0, paused: false } : { on: true, i: 0, paused: false })} icon={<RotateCcw className="size-3.5" />}>
            {replay.on ? "Oprește" : "Rejoacă banii"}
          </Button>
        </div>
      </header>
      {replay.on && current && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-line bg-yellow-tint px-4 py-1.5 text-[0.9333rem]" aria-live="polite">
          <span className="font-mono font-semibold tabular-nums">{replay.i + 1}/{steps.length}</span>
          <span className="font-semibold">{dateTime(current.e.ts)}</span>
          <span>{money(current.e.amount)} · {model.nodes.get(flowIdOf.get(current.e.source) ?? "")?.short} → {model.nodes.get(flowIdOf.get(current.e.target) ?? "")?.short}</span>
          <span className="ml-auto font-semibold tabular-nums">cumulat {money(shown)}</span>
        </div>
      )}
      <div className="grid grid-cols-3 border-b border-line px-4 py-1.5 text-[0.8rem] text-muted" aria-hidden>
        <span>Victime</span><span className="text-center">Contul urmărit</span><span className="text-right">Unde pleacă banii</span>
      </div>
      <div ref={box} className="relative bg-canvas/40" style={{ height: h }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
          fitViewOptions={{ padding: 0.06 }}
          minZoom={0.3}
          maxZoom={1.5}
          zoomOnScroll={false}
          preventScrolling={false}
          nodesDraggable={false}
          nodesConnectable={false}
          proOptions={{ hideAttribution: true }}
        >
          <FitOnResize boxRef={box} n={nodes.length} />
        </ReactFlow>
      </div>
      <footer className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line px-4 py-2 text-[0.8rem] text-muted">
        <span className="inline-flex items-center gap-1.5"><span className="size-2.5 rounded-sm border border-danger bg-danger-soft" /> scor peste 0,70</span>
        <span className="inline-flex items-center gap-1.5"><span className="size-2.5 rounded-sm border border-warn bg-warn-soft" /> 0,30–0,70</span>
        <span className="inline-flex items-center gap-1.5"><span className="size-2.5 rounded-sm border border-ok bg-ok-soft" /> sub 0,30</span>
        <span className="ml-auto">Victimele apar ca pseudonim (VCT-…).</span>
      </footer>
    </section>
  );
}

export default function MoneyGraph(props: MoneyGraphProps) {
  return (
    <ReactFlowProvider>
      <Inner {...props} />
    </ReactFlowProvider>
  );
}
