/**
 * Așezarea grafului de agenți. Graful Judecătorului (zona client) are o grilă scrisă de mână, pe rânduri
 * care spun povestea: intrare → probe în paralel → decizie → recuperare → răspuns. Orice alt graf
 * (Investigatorul AML, noduri noi) primește o așezare pe straturi, calculată din muchii.
 */
import type { PipelineEdge } from "../api/types";

export const NODE_W = 148;
export const NODE_H = 58;
const COL = 168;
const ROW = 96;

/** [coloană, rând] pentru nodurile cunoscute ale Judecătorului (versoml/zone_client/agents.py, PIPELINE_NODES). */
const CLIENT_GRID: Record<string, [number, number]> = {
  receptor: [0.5, 0],
  clasificator: [1.5, 0],
  ceasornicar: [2.5, 0],
  colector_tranzactie: [0, 1],
  colector_sca: [1, 1],
  colector_dispozitiv: [2, 1],
  colector_domeniu: [3, 1],
  motor_reguli: [0.5, 2],
  outbox_aml: [1.5, 2],
  rambursare: [2.5, 2],
  procuror: [0.5, 3],
  avocat: [1.5, 3],
  recuperare: [2.75, 3.5],
  cantaritor: [1, 4],
  redactor: [0.5, 5],
  filtru_zid: [1.5, 5],
  sigiliu: [2.5, 5],
};

/** Etapele, ca etichete de rând în stânga grafului. */
export const CLIENT_ROWS: Array<{ row: number; label: string }> = [
  { row: 0, label: "Intrare" },
  { row: 1, label: "Probe în paralel" },
  { row: 2, label: "Decizie" },
  { row: 3, label: "Recuperare" },
  { row: 5, label: "Răspuns" },
];

export interface Placed {
  x: number;
  y: number;
  row: number;
}

/** Straturi după cel mai lung drum; un lanț liniar se pliază pe rânduri de câte `wrap`. */
function layered(ids: string[], edges: PipelineEdge[], wrap = 3, dir: "TB" | "LR" = "TB"): Record<string, Placed> {
  const incoming = new Map<string, string[]>();
  ids.forEach((id) => incoming.set(id, []));
  edges.forEach((e) => incoming.get(e.target)?.push(e.source));
  const depth = new Map<string, number>();
  const visit = (id: string, stack: Set<string>): number => {
    if (depth.has(id)) return depth.get(id)!;
    if (stack.has(id)) return 0;
    stack.add(id);
    const preds = (incoming.get(id) ?? []).filter((p) => ids.includes(p));
    const d = preds.length ? Math.max(...preds.map((p) => visit(p, stack) + 1)) : 0;
    stack.delete(id);
    depth.set(id, d);
    return d;
  };
  ids.forEach((id) => visit(id, new Set()));
  const layers: string[][] = [];
  ids.forEach((id) => {
    const d = depth.get(id) ?? 0;
    (layers[d] ??= []).push(id);
  });
  const out: Record<string, Placed> = {};
  const linear = layers.every((l) => l.length <= 1);
  if (linear) {
    const order = layers.flat();
    order.forEach((id, i) => {
      const row = Math.floor(i / wrap);
      const col = i % wrap;
      out[id] = { x: col * COL, y: row * ROW, row };
    });
    return out;
  }
  const widest = Math.max(...layers.map((l) => l.length));
  layers.forEach((layer, row) => {
    const offset = (widest - layer.length) / 2;
    layer.forEach((id, i) => {
      out[id] = dir === "LR" ? { x: row * (NODE_W + 44), y: (offset + i) * (NODE_H + 26), row: 0 } : { x: (offset + i) * COL, y: row * ROW, row };
    });
  });
  return out;
}

export function layoutPipeline(ids: string[], edges: PipelineEdge[], dir: "TB" | "LR" = "TB"): { pos: Record<string, Placed>; rows: Array<{ row: number; label: string; y: number }>; mode: "grid" | "TB" | "LR" } {
  const known = ids.filter((id) => CLIENT_GRID[id]);
  if (known.length >= Math.max(3, ids.length - 2)) {
    const pos: Record<string, Placed> = {};
    known.forEach((id) => {
      const [c, r] = CLIENT_GRID[id];
      pos[id] = { x: c * COL, y: r * ROW, row: r };
    });
    // noduri noi, necunoscute: un rând suplimentar jos
    ids.filter((id) => !CLIENT_GRID[id]).forEach((id, i) => {
      pos[id] = { x: (i % 4) * COL, y: (6 + Math.floor(i / 4)) * ROW, row: 6 };
    });
    return { pos, rows: CLIENT_ROWS.map((r) => ({ ...r, y: r.row * ROW })), mode: "grid" };
  }
  return { pos: layered(ids, edges, 3, dir), rows: [], mode: dir };
}

/** Pe ce laturi intră și iese o muchie, după pozițiile capetelor. */
export function handlesFor(a: Placed, b: Placed, mode: "grid" | "TB" | "LR" = "grid"): { sourceHandle: string; targetHandle: string } {
  if (mode === "LR" || Math.abs(a.y - b.y) < ROW * 0.4) {
    return b.x >= a.x ? { sourceHandle: "s-right", targetHandle: "t-left" } : { sourceHandle: "s-left", targetHandle: "t-right" };
  }
  return b.y > a.y ? { sourceHandle: "s-bottom", targetHandle: "t-top" } : { sourceHandle: "s-top", targetHandle: "t-bottom" };
}
