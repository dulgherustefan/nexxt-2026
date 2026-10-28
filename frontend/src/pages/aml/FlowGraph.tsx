import { ArrowDownLeft, ArrowUpRight, Banknote, Bitcoin, Landmark, Layers, Play, Square, Store, TriangleAlert, UserRound, X } from "lucide-react";
import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from "react";
import { dateTime, money } from "../../api/format";
import { usePrefersReducedMotion } from "../../api/runtime";
import type { AmlLead, MoneyGraph } from "../../api/types";
import { Button, cx, EmptyState, IdTag, KeyValues, Panel } from "../../ui/kit";
import { compactAmount, roCount } from "./aml";
import { buildFlowModel, layoutFlow, type FlowLink, type FlowModel, type FlowNode } from "./flow";
import { ScoreText } from "./ui";

const KIND_WORDS: Record<string, string> = {
  victima: "Victimă (pseudonim)",
  carausi: "Cont-cărăuș probabil",
  cont: "Cont bancar",
  exchange: "Exchange crypto",
  numerar: "Retragere de numerar",
  comerciant: "Comerciant",
  grup: "Grup de conturi",
};

const ROLE_WORDS: Record<FlowNode["role"], string> = {
  victim: "Victimă",
  sender: "Alt plătitor",
  subject: "Contul urmărit",
  exit: "Ieșire",
};

function kindWords(n: FlowNode): string {
  return KIND_WORDS[n.kind] ?? (n.kind ? n.kind : "Cont");
}

function KindIcon({ n, className }: { n: FlowNode; className?: string }) {
  const cls = cx("size-3.5 shrink-0", className);
  if (n.isGroup) return <Layers aria-hidden className={cls} />;
  switch (n.kind) {
    case "victima":
      return <UserRound aria-hidden className={cls} />;
    case "exchange":
      return <Bitcoin aria-hidden className={cls} />;
    case "numerar":
      return <Banknote aria-hidden className={cls} />;
    case "comerciant":
      return <Store aria-hidden className={cls} />;
    default:
      return <Landmark aria-hidden className={cls} />;
  }
}

const ROLE_CLS: Record<FlowNode["role"], string> = {
  victim: "border-line-strong bg-paper hover:bg-hover",
  sender: "border-line-strong bg-paper hover:bg-hover",
  subject: "border-ink bg-yellow text-ink hover:bg-yellow-hover",
  exit: "border-line bg-canvas hover:bg-hover",
};

function nodeAria(n: FlowNode): string {
  const parts = [`${n.role === "subject" ? "Contul urmărit, " : ""}${kindWords(n)}: ${n.label}.`];
  if (n.amountIn > 0) parts.push(`Intrat ${money(n.amountIn)}.`);
  if (n.amountOut > 0) parts.push(`Ieșit ${money(n.amountOut)}.`);
  if (n.flagged) parts.push("Scor M5 ridicat.");
  return parts.join(" ");
}

function linkLabel(l: FlowLink): string {
  if (l.count > 1) return `${money(l.amount)} · ${roCount(l.count, "o plată", "plăți")}`;
  return l.firstTs ? `${money(l.amount)} · ${dateTime(l.firstTs)}` : money(l.amount);
}

function Amounts({ n, subject }: { n: FlowNode; subject: boolean }) {
  const cls = cx("flex items-center gap-2 text-[0.8667rem] tabular-nums", subject ? "text-ink-soft" : "text-muted");
  const showIn = n.amountIn > 0 && n.role !== "victim";
  const showOut = n.amountOut > 0 && n.role !== "exit";
  if (!showIn && !showOut) return <span className={cls}>—</span>;
  return (
    <span className={cls}>
      {showIn && (
        <span className="inline-flex items-center gap-0.5">
          <ArrowDownLeft aria-hidden className="size-3.5" />
          {compactAmount(n.amountIn)}
        </span>
      )}
      {showOut && (
        <span className="inline-flex items-center gap-0.5">
          <ArrowUpRight aria-hidden className="size-3.5" />
          {compactAmount(n.amountOut)}
        </span>
      )}
    </span>
  );
}

function NodeDetails({ n, model, id, side, onClose, panelRef }: {
  n: FlowNode;
  model: FlowModel;
  id: string;
  side: "left" | "right";
  onClose: () => void;
  panelRef: RefObject<HTMLElement | null>;
}) {
  const links = model.links.filter((l) => l.source === n.id || l.target === n.id).sort((a, b) => b.amount - a.amount);
  const caseIds = Array.from(new Set(links.flatMap((l) => l.caseIds)));
  return (
    <aside
      id={id}
      ref={panelRef}
      tabIndex={-1}
      aria-label={`Detalii: ${n.label}`}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.stopPropagation();
          onClose();
        }
      }}
      className={cx(
        "absolute top-2 z-20 max-h-[calc(100%-1rem)] w-[18.5rem] max-w-[calc(100%-1rem)] animate-enter overflow-y-auto rounded-lg border border-line-strong bg-paper p-4 shadow-[var(--shadow-raise)] outline-none",
        side === "right" ? "right-2" : "left-2",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[0.8667rem] text-muted">{ROLE_WORDS[n.role]}</p>
          <p className={cx("font-semibold break-all", n.mono && "font-mono")}>{n.label}</p>
        </div>
        <button type="button" aria-label="Închide detaliile" onClick={onClose} className="grid size-8 shrink-0 place-items-center rounded-md hover:bg-hover">
          <X aria-hidden className="size-4" />
        </button>
      </div>
      <div className="mt-3 text-[0.9333rem]">
        <KeyValues
          rows={[
            ["Ce este", kindWords(n)],
            n.score !== null && ["Scor M5", <ScoreText key="s" score={n.score} />],
            n.role !== "victim" && ["Intrat", <span key="i" className="tabular-nums">{money(n.amountIn)}</span>],
            n.role !== "exit" && ["Ieșit", <span key="o" className="tabular-nums">{money(n.amountOut)}</span>],
            n.community !== null && ["Comunitate", `nr. ${n.community}`],
            n.role !== "victim" &&
              !n.isGroup && [
                "Semnalat",
                n.flagged ? (
                  <span key="f" className="inline-flex items-center gap-1 font-semibold text-danger">
                    <TriangleAlert aria-hidden className="size-3.5" />
                    da, scor M5 ridicat
                  </span>
                ) : (
                  "nu"
                ),
              ],
          ]}
        />
      </div>
      {links.length > 0 && (
        <div className="mt-4">
          <p className="mb-1.5 text-[0.8667rem] font-semibold">Fluxuri ({links.length})</p>
          <ul className="space-y-1.5 text-[0.8667rem]">
            {links.slice(0, 6).map((l) => {
              const incoming = l.target === n.id;
              const other = model.nodes.get(incoming ? l.source : l.target);
              return (
                <li key={l.id} className="flex items-center justify-between gap-2">
                  <span className="flex min-w-0 items-center gap-1">
                    {incoming ? <ArrowDownLeft aria-label="de la" className="size-3.5 shrink-0" /> : <ArrowUpRight aria-label="spre" className="size-3.5 shrink-0" />}
                    <span className={cx("truncate", other?.mono && "font-mono")}>{other?.short ?? "—"}</span>
                  </span>
                  <span className="shrink-0 tabular-nums">{money(l.amount)}</span>
                </li>
              );
            })}
          </ul>
          {links.length > 6 && <p className="mt-1 text-[0.8667rem] text-muted">și încă {links.length - 6}</p>}
        </div>
      )}
      {caseIds.length > 0 && (
        <div className="mt-4">
          <p className="mb-1.5 text-[0.8667rem] font-semibold">Contestații</p>
          <div className="flex flex-wrap gap-1.5">
            {caseIds.map((c) => (
              <IdTag key={c}>{c}</IdTag>
            ))}
          </div>
        </div>
      )}
      {n.isGroup && (
        <div className="mt-4">
          <p className="mb-1.5 text-[0.8667rem] font-semibold">În grup</p>
          <ul className="space-y-1 text-[0.8667rem]">
            {n.members.slice(0, 12).map((m) => (
              <li key={m.id} className="truncate font-mono">{m.label || m.id}</li>
            ))}
          </ul>
          {n.members.length > 12 && <p className="mt-1 text-[0.8667rem] text-muted">și încă {n.members.length - 12}</p>}
        </div>
      )}
    </aside>
  );
}

function LegendSwatch({ cls, children, icon }: { cls: string; children: ReactNode; icon: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span aria-hidden className={cx("grid size-5 place-items-center rounded-sm border", cls)}>{icon}</span>
      {children}
    </span>
  );
}

/**
 * Graful banilor ca diagramă de flux: coloane fixe, linii cu grosimea după sumă,
 * sumele la survolare sau focus, detalii la clic. Nodurile sunt butoane (tastatura merge).
 */
export default function FlowGraph({ graph, lead, building = false }: { graph?: MoneyGraph | null; lead?: AmlLead | null; building?: boolean }) {
  const graphKey = useMemo(() => {
    try {
      return JSON.stringify(graph ?? null);
    } catch {
      return "x";
    }
  }, [graph]);
  const leadFirst = lead?.accounts?.[0]?.account ?? "";
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const model = useMemo(() => buildFlowModel(graph, lead), [graphKey, leadFirst]);
  const hasLinks = model.links.length > 0;

  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  useLayoutEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const measure = () => setWidth(Math.max(280, Math.floor(el.clientWidth)));
    measure();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", measure);
      return () => window.removeEventListener("resize", measure);
    }
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [hasLinks]);
  const layout = useMemo(() => layoutFlow(model, width), [model, width]);

  const [hover, setHover] = useState<string | null>(null);
  const [focused, setFocused] = useState<string | null>(null);
  const [hoverLink, setHoverLink] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const nodeRefs = useRef(new Map<string, HTMLButtonElement>());
  const panelRef = useRef<HTMLElement | null>(null);
  const rawId = useId();
  const uid = rawId.replace(/[^a-zA-Z0-9_-]/g, "");
  const panelId = `${uid}-detalii`;

  useEffect(() => {
    if (selected && !model.nodes.has(selected)) setSelected(null);
  }, [model, selected]);

  // ---------------------------------------------------------------- reluarea în ordinea timpului
  const reduced = usePrefersReducedMotion();
  const order = useMemo(
    () =>
      layout.paths
        .slice()
        .sort((a, b) => (a.link.firstTs ?? Number.MAX_SAFE_INTEGER) - (b.link.firstTs ?? Number.MAX_SAFE_INTEGER))
        .map((p) => p.link.id),
    [layout],
  );
  const [replay, setReplay] = useState<{ k: number; playing: boolean } | null>(null);
  const [motionNote, setMotionNote] = useState(false);
  useEffect(() => {
    if (!replay) return;
    if (!replay.playing) {
      let inner = 0;
      const outer = requestAnimationFrame(() => {
        inner = requestAnimationFrame(() => setReplay((p) => (p ? { ...p, playing: true } : p)));
      });
      return () => {
        cancelAnimationFrame(outer);
        cancelAnimationFrame(inner);
      };
    }
    if (replay.k >= order.length) {
      const t = window.setTimeout(() => setReplay(null), 1600);
      return () => window.clearTimeout(t);
    }
    const step = Math.max(320, Math.min(700, 5600 / Math.max(1, order.length)));
    const t = window.setTimeout(() => setReplay((p) => (p ? { ...p, k: p.k + 1 } : p)), replay.k === 0 ? 250 : step);
    return () => window.clearTimeout(t);
  }, [replay, order.length]);
  useEffect(() => {
    if (!motionNote) return;
    const t = window.setTimeout(() => setMotionNote(false), 5000);
    return () => window.clearTimeout(t);
  }, [motionNote]);

  const startReplay = () => {
    if (!order.length) return;
    if (reduced) {
      setReplay(null);
      setMotionNote(true);
      return;
    }
    setSelected(null);
    setReplay({ k: 0, playing: false });
  };

  const revealed = replay ? new Set(order.slice(0, replay.k)) : null;
  const latest = replay && replay.k > 0 ? model.links.find((l) => l.id === order[replay.k - 1]) ?? null : null;
  const reached = new Set<string>();
  if (revealed) for (const l of model.links) if (revealed.has(l.id)) reached.add(l.source).add(l.target);

  // ---------------------------------------------------------------- ce e evidențiat
  const activeNode = hover ?? focused ?? selected;
  const activeLinks = new Set<string>();
  if (hoverLink) {
    activeLinks.add(hoverLink);
  } else if (activeNode) {
    for (const l of model.links) {
      if (l.source === activeNode || l.target === activeNode) activeLinks.add(l.id);
    }
  } else if (latest) {
    activeLinks.add(latest.id);
  }
  const labelPaths = layout.paths
    .filter((p) => activeLinks.has(p.link.id) && (!revealed || revealed.has(p.link.id)))
    .sort((a, b) => b.link.amount - a.link.amount)
    .slice(0, 6);
  const neighborsOfSelected = new Set<string>();
  if (selected) {
    neighborsOfSelected.add(selected);
    for (const l of model.links) if (l.source === selected || l.target === selected) neighborsOfSelected.add(l.source).add(l.target);
  }

  const select = (id: string, viaKeyboard: boolean) => {
    if (selected === id) {
      setSelected(null);
      return;
    }
    setSelected(id);
    if (viaKeyboard) window.setTimeout(() => panelRef.current?.focus(), 0);
  };
  const close = () => {
    const id = selected;
    setSelected(null);
    if (id) nodeRefs.current.get(id)?.focus();
  };

  const selectedNode = selected ? model.nodes.get(selected) ?? null : null;
  const selectedBox = selected ? layout.boxes.get(selected) : undefined;
  const side: "left" | "right" = selectedBox && selectedBox.col >= model.columns.length / 2 ? "left" : "right";

  const title = (
    <span className="flex flex-wrap items-baseline gap-x-2">
      Drumul banilor
      {model.nodeCount > 0 && (
        <span className="text-[0.8667rem] font-normal text-muted">
          {roCount(model.nodeCount, "un cont", "conturi")} · {roCount(model.edgeCount, "un flux", "fluxuri")}
        </span>
      )}
    </span>
  );
  const replayButton = (
    <Button
      size="sm"
      icon={replay ? <Square aria-hidden className="size-3.5" /> : <Play aria-hidden className="size-3.5" />}
      onClick={() => (replay ? setReplay(null) : startReplay())}
      disabled={!hasLinks}
    >
      {replay ? "Oprește" : "Rejoacă banii"}
    </Button>
  );

  if (!model.nodeCount || !hasLinks) {
    return (
      <Panel title={title} actions={replayButton}>
        <EmptyState
          icon={<Layers aria-hidden className="size-5" />}
          title={!model.nodeCount ? (building ? "Agenții construiesc graful banilor." : "Graful banilor e gol deocamdată.") : "Niciun flux de bani între conturile pistei."}
        >
          {!model.nodeCount
            ? "Apare după pasul „Graf + ML”, din contestațiile legate de această pistă."
            : `${roCount(model.nodeCount, "Un cont cunoscut", "conturi cunoscute")}, fără transferuri între ele în fereastra analizată.`}
        </EmptyState>
      </Panel>
    );
  }

  const caption = latest
    ? `${replay ? `${Math.min(replay.k, order.length)} din ${order.length} · ` : ""}${latest.firstTs ? `${dateTime(latest.firstTs)} · ` : ""}${model.nodes.get(latest.source)?.short ?? ""} → ${model.nodes.get(latest.target)?.short ?? ""} · ${money(latest.amount)}`
    : motionNote
      ? "Mișcarea redusă e activă: graful rămâne direct în starea finală."
      : replay
        ? "Pornesc de la primul transfer…"
        : null;

  return (
    <Panel title={title} actions={replayButton} bodyClassName="p-0">
      <div
        className="relative"
        onKeyDown={(e) => {
          if (e.key === "Escape" && selected) close();
        }}
      >
        <div ref={wrapRef} className="overflow-x-auto overflow-y-hidden">
          <div className="relative" style={{ width: layout.width, height: layout.height }}>
            {layout.labels.map((lb, i) => (
              <p key={`${lb.text}-${i}`} className="absolute truncate text-[0.8667rem] font-semibold text-muted" style={{ left: lb.x, top: lb.y, width: lb.w }}>
                {lb.text}
              </p>
            ))}

            <svg width={layout.width} height={layout.height} className="absolute inset-0 overflow-visible" aria-hidden>
              <defs>
                <marker id={`${uid}-arrow`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" markerUnits="userSpaceOnUse" orient="auto">
                  <path d="M0,0 L10,5 L0,10 z" className="fill-ink" />
                </marker>
              </defs>
              {layout.paths.map((p) => {
                const isActive = activeLinks.has(p.link.id);
                const hidden = revealed ? !revealed.has(p.link.id) : false;
                const dim = (activeLinks.size > 0 && !isActive) || (selected !== null && !isActive);
                const opacity = hidden ? 0.07 : isActive ? 0.9 : dim ? 0.12 : 0.34;
                return (
                  <g key={p.link.id} opacity={opacity} style={{ transition: "opacity 160ms" }}>
                    <path
                      d={p.d}
                      fill="none"
                      className="stroke-ink"
                      strokeWidth={p.width}
                      strokeLinecap="round"
                      markerEnd={hidden ? undefined : `url(#${uid}-arrow)`}
                      pathLength={replay ? 1 : undefined}
                      style={
                        replay
                          ? {
                              strokeDasharray: 1,
                              strokeDashoffset: hidden ? 1 : 0,
                              transition: replay.playing ? "stroke-dashoffset 560ms cubic-bezier(0.22, 1, 0.36, 1)" : "none",
                            }
                          : undefined
                      }
                    />
                    <path
                      d={p.d}
                      fill="none"
                      stroke="transparent"
                      strokeWidth={Math.max(12, p.width + 8)}
                      style={{ pointerEvents: "stroke" }}
                      onMouseEnter={() => setHoverLink(p.link.id)}
                      onMouseLeave={() => setHoverLink((h) => (h === p.link.id ? null : h))}
                    />
                  </g>
                );
              })}
            </svg>

            {labelPaths.map((p) => (
              <span
                key={`lbl-${p.link.id}`}
                className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-1/2 whitespace-nowrap rounded-sm border border-line-strong bg-paper px-1.5 py-px text-[0.8667rem] font-semibold tabular-nums"
                style={{ left: p.mx, top: p.my }}
              >
                {linkLabel(p.link)}
              </span>
            ))}

            {model.columns.map((c) =>
              c.segments.flatMap((sg) => sg.nodes).map((n) => {
                const b = layout.boxes.get(n.id);
                if (!b) return null;
                const isSel = selected === n.id;
                const faded = (revealed !== null && !reached.has(n.id)) || (selected !== null && !neighborsOfSelected.has(n.id));
                return (
                  <button
                    key={n.id}
                    ref={(el) => {
                      if (el) nodeRefs.current.set(n.id, el);
                      else nodeRefs.current.delete(n.id);
                    }}
                    type="button"
                    aria-label={nodeAria(n)}
                    aria-expanded={isSel}
                    aria-controls={isSel ? panelId : undefined}
                    onClick={(e) => select(n.id, e.detail === 0)}
                    onMouseEnter={() => setHover(n.id)}
                    onMouseLeave={() => setHover((h) => (h === n.id ? null : h))}
                    onFocus={() => setFocused(n.id)}
                    onBlur={() => setFocused((f) => (f === n.id ? null : f))}
                    className={cx(
                      "absolute z-[5] flex flex-col justify-center gap-0.5 rounded-md border px-2.5 text-left transition-opacity duration-200",
                      ROLE_CLS[n.role],
                      n.isGroup && "border-dashed",
                      isSel && "ring-2 ring-ink ring-offset-2",
                      faded && "opacity-40",
                    )}
                    style={{ left: b.x, top: b.y, width: b.w, height: b.h }}
                  >
                    <span className="flex min-w-0 items-center gap-1.5">
                      <KindIcon n={n} />
                      <span className={cx("truncate text-[0.8667rem] font-semibold", n.mono && "font-mono")}>{n.short}</span>
                      {n.flagged && n.role !== "subject" && <TriangleAlert aria-hidden className="size-3.5 shrink-0 text-danger" />}
                    </span>
                    <Amounts n={n} subject={n.role === "subject"} />
                  </button>
                );
              }),
            )}
          </div>
        </div>

        {selectedNode && (
          <NodeDetails n={selectedNode} model={model} id={panelId} side={side} onClose={close} panelRef={panelRef} />
        )}
      </div>

      {caption && (
        <p aria-live="polite" className="border-t border-line bg-canvas px-4 py-2 text-[0.8667rem] font-semibold tabular-nums">
          {caption}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-line px-4 py-2.5 text-[0.8667rem] text-muted">
        <LegendSwatch cls="border-line-strong bg-paper" icon={<UserRound className="size-3" />}>Victimă</LegendSwatch>
        <LegendSwatch cls="border-ink bg-yellow text-ink" icon={<Landmark className="size-3" />}>Contul urmărit</LegendSwatch>
        <LegendSwatch cls="border-line-strong bg-paper" icon={<Landmark className="size-3" />}>Alt cont</LegendSwatch>
        <LegendSwatch cls="border-line bg-canvas" icon={<Bitcoin className="size-3" />}>Ieșire: exchange, numerar, comerciant</LegendSwatch>
        <span className="inline-flex items-center gap-1">
          <TriangleAlert aria-hidden className="size-3.5 text-danger" />
          scor M5 ridicat
        </span>
        <span className="inline-flex items-center gap-1">
          <ArrowDownLeft aria-hidden className="size-3.5" /> intrat
          <ArrowUpRight aria-hidden className="ml-1 size-3.5" /> ieșit · sume în lei · linie groasă = sumă mare
        </span>
      </div>
    </Panel>
  );
}
