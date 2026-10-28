/**
 * Graful banilor, determinist: coloane fixe de la stânga la dreapta, fără layout de forțe.
 *   1. cine a trimis bani: victimele (sus), apoi alți plătitori (jos, grupați peste 4);
 *   2. contul urmărit (singurul punct galben);
 *   3. ieșirile: exchange, numerar, comercianți și alte conturi care au primit bani.
 * Așa fiecare săgeată merge spre dreapta. Aceleași date dau mereu același desen.
 */
import { money } from "../../api/format";
import type { AmlLead, GraphEdge, GraphNode, MoneyGraph } from "../../api/types";
import { compactAccount, isVictimRef, looksLikeAccount, maskAccount, roCount, toNumber, tsOf } from "./aml";

export type FlowRole = "victim" | "sender" | "subject" | "exit";

export const EXIT_KINDS = new Set(["exchange", "numerar", "comerciant"]);
/** Câte noduri încap într-un grup; restul se adună într-un nod „+n”. */
const CAPS: Record<FlowRole, number> = { victim: 4, sender: 5, subject: 4, exit: 6 };

export interface FlowNode {
  id: string;
  role: FlowRole;
  kind: string;
  label: string;
  short: string;
  mono: boolean;
  score: number | null;
  community: number | null;
  amountIn: number;
  amountOut: number;
  flagged: boolean;
  members: GraphNode[];
  isGroup: boolean;
}

export interface FlowLink {
  id: string;
  source: string;
  target: string;
  amount: number;
  count: number;
  firstTs: number | null;
  lastTs: number | null;
  caseIds: string[];
  kinds: string[];
}

export interface FlowSegment {
  role: FlowRole;
  title: string;
  nodes: FlowNode[];
}

export interface FlowColumn {
  key: "sources" | "subject" | "exits";
  segments: FlowSegment[];
}

export interface FlowModel {
  columns: FlowColumn[];
  links: FlowLink[];
  nodes: Map<string, FlowNode>;
  subjectIds: string[];
  /** Numărul de noduri și fluxuri trimise de server (înainte de comasări), ca în ciorna RTS. */
  nodeCount: number;
  edgeCount: number;
}

const kindOf = (n: GraphNode | undefined) => String(n?.kind ?? "").toLowerCase();

/**
 * Noduri unice, muchii cu capete cunoscute și sume numerice. Aceeași plată poate veni de două ori:
 * ca muchia victimei (pseudonim, prin diodă) și ca transferul din contul ei (din tranzacțiile băncii),
 * cu același caz. Păstrăm doar muchia victimei, iar contul rămas fără fluxuri iese din desen.
 */
export function cleanGraph(graph: MoneyGraph | null | undefined): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const uniq = new Map<string, GraphNode>();
  for (const n of Array.isArray(graph?.nodes) ? graph!.nodes : []) {
    if (n && typeof n.id === "string" && n.id && !uniq.has(n.id)) uniq.set(n.id, n);
  }
  let edges: GraphEdge[] = [];
  for (const e of Array.isArray(graph?.edges) ? graph!.edges : []) {
    if (!e || !uniq.has(e.source) || !uniq.has(e.target) || e.source === e.target) continue;
    edges.push({ ...e, amount: toNumber(e.amount) });
  }
  const isVictim = (id: string) => kindOf(uniq.get(id)) === "victima";
  const dup = new Set<GraphEdge>();
  for (const v of edges) {
    if (!isVictim(v.source) || !v.case_id) continue;
    for (const e of edges) {
      if (e === v || isVictim(e.source) || e.target !== v.target || e.case_id !== v.case_id) continue;
      if (Math.abs(e.amount - v.amount) <= Math.max(1, 0.01 * v.amount)) dup.add(e);
    }
  }
  if (dup.size) {
    const before = new Set(edges.flatMap((e) => [e.source, e.target]));
    edges = edges.filter((e) => !dup.has(e));
    const after = new Set(edges.flatMap((e) => [e.source, e.target]));
    for (const id of before) if (!after.has(id) && !isVictim(id)) uniq.delete(id);
  }
  return { nodes: Array.from(uniq.values()), edges };
}

/** Sumele intrate și ieșite: cele de pe nod, altfel din fluxurile vizibile. */
function volumes(edges: GraphEdge[]) {
  const inSum = new Map<string, number>();
  const outSum = new Map<string, number>();
  for (const e of edges) {
    inSum.set(e.target, (inSum.get(e.target) ?? 0) + e.amount);
    outSum.set(e.source, (outSum.get(e.source) ?? 0) + e.amount);
  }
  const amountIn = (n: GraphNode) => toNumber(n.amount_in) || inSum.get(n.id) || 0;
  const amountOut = (n: GraphNode) => toNumber(n.amount_out) || outSum.get(n.id) || 0;
  return { amountIn, amountOut };
}

/**
 * Contul urmărit: conturile-cărăuș (kind „carausi”), cele în care au plătit victimele și primul cont al pistei.
 * Dacă nu e niciunul, contul cu scorul cel mai mare. Cel mult 4, ca să rămână un singur punct fierbinte.
 */
export function subjectIdsOf(graph: MoneyGraph | null | undefined, lead?: AmlLead | null): string[] {
  const { nodes, edges } = cleanGraph(graph);
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const isVictim = (id: string) => kindOf(byId.get(id)) === "victima";
  const isExit = (id: string) => EXIT_KINDS.has(kindOf(byId.get(id)));
  const victimTargets = new Set(edges.filter((e) => isVictim(e.source) && !isVictim(e.target) && !isExit(e.target)).map((e) => e.target));
  const first = lead?.accounts?.[0]?.account;
  const firstMasked = first ? maskAccount(first) : null;
  const isFirst = (n: GraphNode) =>
    Boolean(first && (n.id === first || n.label === first || maskAccount(n.id) === firstMasked || maskAccount(n.label) === firstMasked));
  const { amountIn, amountOut } = volumes(edges);
  const vol = (n: GraphNode) => amountIn(n) + amountOut(n);
  const pool = nodes.filter((n) => !isVictim(n.id) && !isExit(n.id));
  let subs = pool.filter((n) => kindOf(n) === "carausi" || victimTargets.has(n.id) || isFirst(n));
  if (!subs.length) {
    const best = pool.slice().sort((a, b) => (b.score ?? -1) - (a.score ?? -1) || vol(b) - vol(a))[0];
    if (best) subs = [best];
  }
  subs.sort(
    (a, b) =>
      Number(isFirst(b)) - Number(isFirst(a)) ||
      Number(victimTargets.has(b.id)) - Number(victimTargets.has(a.id)) ||
      (b.score ?? 0) - (a.score ?? 0) ||
      vol(b) - vol(a),
  );
  return subs.slice(0, CAPS.subject).map((n) => n.id);
}

function shortLabel(n: GraphNode): { short: string; mono: boolean; label: string } {
  const raw = String(n.label || n.id);
  if (kindOf(n) === "victima") {
    const s = raw.replace(/^victim[ăa]\s+/i, "");
    return { short: s, mono: isVictimRef(s) || /^[A-Z]{2,}-[0-9a-z]+$/i.test(s), label: s };
  }
  const label = maskAccount(raw);
  if (looksLikeAccount(label)) return { short: compactAccount(label), mono: true, label };
  return { short: label, mono: false, label };
}

const GROUP_TITLE: Record<FlowRole, (n: number) => string> = {
  victim: (n) => `+${n} victime`,
  sender: (n) => `+${n} alți plătitori`,
  subject: (n) => `+${n} conturi`,
  exit: (n) => `+${n} alte ieșiri`,
};

export function buildFlowModel(graph: MoneyGraph | null | undefined, lead?: AmlLead | null): FlowModel {
  const { nodes, edges } = cleanGraph(graph);
  const subjectIds = subjectIdsOf(graph, lead);
  const S = new Set(subjectIds);
  const { amountIn, amountOut } = volumes(edges);
  const sum = (list: GraphEdge[]) => list.reduce((s, e) => s + e.amount, 0);
  const roleOf = (n: GraphNode): FlowRole => {
    if (kindOf(n) === "victima") return "victim";
    if (S.has(n.id)) return "subject";
    if (EXIT_KINDS.has(kindOf(n))) return "exit";
    // ceilalți: plătitori dacă au trimis spre contul urmărit mai mult decât au primit de la el
    const toS = sum(edges.filter((e) => e.source === n.id && S.has(e.target)));
    const fromS = sum(edges.filter((e) => S.has(e.source) && e.target === n.id));
    if (toS !== fromS) return toS > fromS ? "sender" : "exit";
    return sum(edges.filter((e) => e.source === n.id)) > sum(edges.filter((e) => e.target === n.id)) ? "sender" : "exit";
  };

  const byRole: Record<FlowRole, GraphNode[]> = { victim: [], sender: [], subject: [], exit: [] };
  for (const n of nodes) byRole[roleOf(n)].push(n);
  byRole.subject.sort((a, b) => subjectIds.indexOf(a.id) - subjectIds.indexOf(b.id));
  byRole.victim.sort((a, b) => amountOut(b) - amountOut(a));
  byRole.sender.sort((a, b) => Number(Boolean(b.flagged)) - Number(Boolean(a.flagged)) || amountOut(b) - amountOut(a));
  byRole.exit.sort((a, b) => amountIn(b) - amountIn(a));

  const flowNodes = new Map<string, FlowNode>();
  const rawToFlow = new Map<string, string>();
  const groups: Record<FlowRole, FlowNode[]> = { victim: [], sender: [], subject: [], exit: [] };
  for (const role of ["victim", "sender", "subject", "exit"] as FlowRole[]) {
    const list = byRole[role];
    const cap = CAPS[role];
    const keep = list.length > cap ? list.slice(0, cap - 1) : list;
    const rest = list.length > cap ? list.slice(cap - 1) : [];
    for (const n of keep) {
      const l = shortLabel(n);
      const f: FlowNode = {
        id: n.id,
        role,
        kind: kindOf(n) || "cont",
        label: l.label,
        short: l.short,
        mono: l.mono,
        score: typeof n.score === "number" ? n.score : null,
        community: typeof n.community === "number" ? n.community : null,
        amountIn: amountIn(n),
        amountOut: amountOut(n),
        flagged: Boolean(n.flagged),
        members: [n],
        isGroup: false,
      };
      flowNodes.set(f.id, f);
      rawToFlow.set(n.id, f.id);
      groups[role].push(f);
    }
    if (rest.length) {
      const id = `grup:${role}`;
      const g: FlowNode = {
        id,
        role,
        kind: "grup",
        label: GROUP_TITLE[role](rest.length),
        short: GROUP_TITLE[role](rest.length),
        mono: false,
        score: null,
        community: null,
        amountIn: rest.reduce((s, n) => s + amountIn(n), 0),
        amountOut: rest.reduce((s, n) => s + amountOut(n), 0),
        flagged: rest.some((n) => n.flagged),
        members: rest,
        isGroup: true,
      };
      flowNodes.set(id, g);
      for (const n of rest) rawToFlow.set(n.id, id);
      groups[role].push(g);
    }
  }

  const linkMap = new Map<string, FlowLink>();
  for (const e of edges) {
    const s = rawToFlow.get(e.source);
    const t = rawToFlow.get(e.target);
    if (!s || !t || s === t) continue;
    const id = `${s}→${t}`;
    const ts = tsOf(e.ts);
    const l = linkMap.get(id) ?? { id, source: s, target: t, amount: 0, count: 0, firstTs: null, lastTs: null, caseIds: [], kinds: [] };
    l.amount += e.amount;
    l.count += 1;
    if (ts !== null) {
      l.firstTs = l.firstTs === null ? ts : Math.min(l.firstTs, ts);
      l.lastTs = l.lastTs === null ? ts : Math.max(l.lastTs, ts);
    }
    if (e.case_id && !l.caseIds.includes(e.case_id)) l.caseIds.push(e.case_id);
    if (e.kind && !l.kinds.includes(e.kind)) l.kinds.push(e.kind);
    linkMap.set(id, l);
  }
  const links = Array.from(linkMap.values());

  // ordinea în grup: baricentrul vecinilor din contul urmărit, ca liniile să se încrucișeze cât mai puțin
  const pos = new Map<string, number>();
  groups.subject.forEach((n, i) => pos.set(n.id, (i + 0.5) / Math.max(1, groups.subject.length)));
  const bary = (n: FlowNode) => {
    const ys = links
      .filter((l) => l.source === n.id || l.target === n.id)
      .map((l) => pos.get(l.source === n.id ? l.target : l.source))
      .filter((y): y is number => y !== undefined);
    return ys.length ? ys.reduce((a, b) => a + b, 0) / ys.length : 2;
  };
  const sortByBary = (col: FlowNode[]) => {
    const order = new Map(col.map((n, i) => [n.id, i]));
    const plain = col.filter((n) => !n.isGroup).sort((a, b) => bary(a) - bary(b) || (order.get(a.id) ?? 0) - (order.get(b.id) ?? 0));
    return [...plain, ...col.filter((n) => n.isGroup)];
  };
  groups.victim = sortByBary(groups.victim);
  groups.sender = sortByBary(groups.sender);
  groups.exit = sortByBary(groups.exit);

  const columns: FlowColumn[] = [];
  const sources: FlowSegment[] = [];
  if (groups.victim.length) sources.push({ role: "victim", title: "Victime", nodes: groups.victim });
  if (groups.sender.length) sources.push({ role: "sender", title: groups.victim.length ? "Alți plătitori" : "Plătitori", nodes: groups.sender });
  if (sources.length) columns.push({ key: "sources", segments: sources });
  if (groups.subject.length) {
    columns.push({ key: "subject", segments: [{ role: "subject", title: groups.subject.length > 1 ? "Conturile urmărite" : "Contul urmărit", nodes: groups.subject }] });
  }
  if (groups.exit.length) columns.push({ key: "exits", segments: [{ role: "exit", title: "Ieșiri", nodes: groups.exit }] });

  const rawNodes = Array.isArray(graph?.nodes) ? graph!.nodes.filter(Boolean).length : 0;
  const rawEdges = Array.isArray(graph?.edges) ? graph!.edges.filter(Boolean).length : 0;
  return { columns, links, nodes: flowNodes, subjectIds, nodeCount: rawNodes, edgeCount: rawEdges };
}

// ------------------------------------------------------------------ așezarea în pagină

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
  col: number;
}

export interface LinkPath {
  link: FlowLink;
  d: string;
  width: number;
  mx: number;
  my: number;
}

export interface FlowLabel {
  x: number;
  y: number;
  w: number;
  text: string;
}

export interface FlowLayout {
  width: number;
  height: number;
  nodeW: number;
  boxes: Map<string, Box>;
  paths: LinkPath[];
  /** Titlul fiecărei coloane (sus) și al grupurilor următoare din aceeași coloană (între noduri). */
  labels: FlowLabel[];
}

export function layoutFlow(model: FlowModel, availWidth: number): FlowLayout {
  const k = Math.max(1, model.columns.length);
  const padX = 12;
  const headerH = 28;
  const subH = 24;
  const padY = 10;
  const minGap = 64;
  const minW = 120;
  const maxW = 190;

  const colHeight = (c: FlowColumn, nodeH: number, gapY: number) =>
    c.segments.reduce((h, s, i) => h + s.nodes.length * nodeH + Math.max(0, s.nodes.length - 1) * gapY + (i > 0 ? subH + gapY : 0), 0);
  let nodeH = 46;
  let gapY = 10;
  if (Math.max(0, ...model.columns.map((c) => colHeight(c, nodeH, gapY))) > 330) {
    nodeH = 40;
    gapY = 8;
  }
  const contentH = Math.max(nodeH, ...model.columns.map((c) => colHeight(c, nodeH, gapY)));
  const height = Math.max(280, headerH + padY * 2 + contentH);
  const extraY = (height - (headerH + padY * 2 + contentH)) / 2;

  const avail = Math.max(280, availWidth);
  let nodeW = k > 1 ? Math.floor((avail - 2 * padX - (k - 1) * minGap) / k) : Math.min(maxW, avail - 2 * padX);
  nodeW = Math.max(minW, Math.min(maxW, nodeW));
  const width = Math.max(avail, 2 * padX + k * nodeW + (k - 1) * minGap);
  const gap = k > 1 ? Math.min(260, (width - 2 * padX - k * nodeW) / (k - 1)) : 0;
  const totalW = k * nodeW + (k - 1) * gap;
  const offsetX = Math.max(padX, (width - totalW) / 2);
  const colX = model.columns.map((_, i) => offsetX + i * (nodeW + gap));

  const boxes = new Map<string, Box>();
  const labels: FlowLabel[] = [];
  model.columns.forEach((c, ci) => {
    let y = headerH + padY + extraY + (contentH - colHeight(c, nodeH, gapY)) / 2;
    labels.push({ x: colX[ci], y: 8, w: nodeW, text: c.segments[0]?.title ?? "" });
    c.segments.forEach((s, si) => {
      if (si > 0) {
        labels.push({ x: colX[ci], y: y + gapY + 2, w: nodeW, text: s.title });
        y += subH + gapY;
      }
      s.nodes.forEach((n, i) => {
        boxes.set(n.id, { x: colX[ci], y, w: nodeW, h: nodeH, col: ci });
        y += nodeH + (i < s.nodes.length - 1 ? gapY : 0);
      });
    });
  });

  // punctele de prindere: răspândite pe înălțimea nodului, în ordinea capătului celălalt
  type Side = "L" | "R";
  const attach = new Map<string, Array<{ linkId: string; otherY: number; end: "s" | "t" }>>();
  const sides = new Map<string, { s: Side; t: Side }>();
  const add = (nodeId: string, side: Side, item: { linkId: string; otherY: number; end: "s" | "t" }) => {
    const key = `${nodeId}\u0000${side}`;
    const list = attach.get(key) ?? [];
    list.push(item);
    attach.set(key, list);
  };
  for (const l of model.links) {
    const sb = boxes.get(l.source);
    const tb = boxes.get(l.target);
    if (!sb || !tb) continue;
    const side: { s: Side; t: Side } = sb.col < tb.col ? { s: "R", t: "L" } : sb.col > tb.col ? { s: "L", t: "R" } : { s: "R", t: "R" };
    sides.set(l.id, side);
    add(l.source, side.s, { linkId: l.id, otherY: tb.y + tb.h / 2, end: "s" });
    add(l.target, side.t, { linkId: l.id, otherY: sb.y + sb.h / 2, end: "t" });
  }
  const anchorY = new Map<string, number>();
  for (const [key, list] of attach) {
    const b = boxes.get(key.slice(0, key.indexOf("\u0000")));
    if (!b) continue;
    list.sort((a, c) => a.otherY - c.otherY);
    list.forEach((item, i) => {
      const y = b.y + (b.h * (i + 1)) / (list.length + 1);
      anchorY.set(`${item.linkId}:${item.end}`, Math.min(b.y + b.h - 5, Math.max(b.y + 5, y)));
    });
  }

  const maxAmount = Math.max(1, ...model.links.map((l) => l.amount));
  const paths: LinkPath[] = [];
  for (const l of model.links) {
    const sb = boxes.get(l.source);
    const tb = boxes.get(l.target);
    const side = sides.get(l.id);
    if (!sb || !tb || !side) continue;
    const sy = anchorY.get(`${l.id}:s`) ?? sb.y + sb.h / 2;
    const ty = anchorY.get(`${l.id}:t`) ?? tb.y + tb.h / 2;
    const sx = side.s === "R" ? sb.x + sb.w : sb.x;
    const tx = side.t === "R" ? tb.x + tb.w : tb.x;
    let c1x: number;
    let c2x: number;
    if (side.s === "R" && side.t === "L") {
      const c = Math.max(28, (tx - sx) * 0.5);
      c1x = sx + c;
      c2x = tx - c;
    } else if (side.s === "L" && side.t === "R") {
      const c = Math.max(28, (sx - tx) * 0.5);
      c1x = sx - c;
      c2x = tx + c;
    } else {
      c1x = sx + 40;
      c2x = tx + 40;
    }
    const d = `M ${sx} ${sy} C ${c1x} ${sy}, ${c2x} ${ty}, ${tx} ${ty}`;
    const width = Math.min(8, Math.max(1.5, 1.5 + 6.5 * Math.sqrt(l.amount / maxAmount)));
    paths.push({ link: l, d, width, mx: (sx + 3 * c1x + 3 * c2x + tx) / 8, my: (sy + ty) / 2 });
  }
  return { width, height, nodeW, boxes, paths, labels };
}

// ------------------------------------------------------------------ fraza în limbaj simplu

function windowPhrase(ms: number): string {
  const h = ms / 3_600_000;
  if (h < 1) return " în mai puțin de o oră";
  if (h <= 24) return ` în ${roCount(Math.ceil(h), "o oră", "ore")}`;
  const d = Math.ceil(h / 24);
  return d === 1 ? " într-o zi" : ` în ${roCount(d, "o zi", "zile")}`;
}

function speedPhrase(ms: number): string {
  const h = ms / 3_600_000;
  if (h < 1) return " în mai puțin de o oră";
  if (h <= 48) return ` în sub ${roCount(Math.ceil(h), "o oră", "ore")}`;
  return ` în ${roCount(Math.ceil(h / 24), "o zi", "zile")}`;
}

const DEST_WORDS: Record<string, (distinct: number) => string> = {
  exchange: (n) => (n > 1 ? "spre exchange-uri crypto" : "spre un exchange crypto"),
  numerar: () => "în numerar",
  comerciant: (n) => (n > 1 ? "la comercianți" : "la un comerciant"),
  cont: (n) => (n > 1 ? "spre alte conturi" : "spre alt cont"),
};

/**
 * O frază despre drumul banilor, calculată din graf (fără LLM): câți bani au venit de la victime și de la alții,
 * în cât timp, ce parte a plecat mai departe, încotro și cât de repede; plus, dacă e cazul,
 * că plata victimei încă nu a plecat (se mai poate opri).
 */
export function describeFlow(graph: MoneyGraph | null | undefined, subjectIds: string[]): string | null {
  const { nodes, edges } = cleanGraph(graph);
  if (!edges.length || !subjectIds.length) return null;
  const S = new Set(subjectIds);
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const kind = (id: string) => kindOf(byId.get(id));
  const inbound = edges.filter((e) => S.has(e.target) && !S.has(e.source));
  const victimIn = inbound.filter((e) => kind(e.source) === "victima");
  const otherIn = inbound.filter((e) => kind(e.source) !== "victima");
  const outbound = edges.filter((e) => S.has(e.source) && !S.has(e.target));
  if (!inbound.length && !outbound.length) return null;
  const plural = S.size > 1;
  const subj = plural ? "Conturile urmărite au" : "Contul a";
  const verb = plural ? "au" : "a";
  const total = (list: GraphEdge[]) => list.reduce((s, e) => s + e.amount, 0);
  const distinct = (list: GraphEdge[]) => new Set(list.map((e) => e.source)).size;
  const tsList = (list: GraphEdge[]) => list.map((e) => tsOf(e.ts)).filter((t): t is number => t !== null);

  const inTs = tsList(inbound);
  const span = inTs.length > 1 ? windowPhrase(Math.max(...inTs) - Math.min(...inTs)) : "";
  const nV = distinct(victimIn);
  const nO = distinct(otherIn);
  const others = nO === 1 ? "un alt plătitor" : `alți ${roCount(nO, "", "plătitori")}`;
  let first = "";
  if (victimIn.length && otherIn.length) first = `${subj} primit ${money(total(victimIn))} de la ${roCount(nV, "o victimă", "victime")} și încă ${money(total(otherIn))} de la ${others}${span}`;
  else if (victimIn.length) first = `${subj} primit ${money(total(victimIn))} de la ${roCount(nV, "o victimă", "victime")}${span}`;
  else if (otherIn.length) first = `${subj} primit ${money(total(otherIn))} de la ${roCount(nO, "un plătitor", "plătitori")}${span}`;

  // plata victimei încă în cont: nicio ieșire după ultima ei intrare
  let still = "";
  const vTs = tsList(victimIn);
  if (vTs.length && outbound.length) {
    const lastV = Math.max(...vTs);
    if (!tsList(outbound).some((t) => t >= lastV)) still = nV === 1 ? " Plata victimei nu a plecat încă mai departe." : " Ultima plată a unei victime nu a plecat încă mai departe.";
  }
  if (!outbound.length) return first ? `${first}. Banii nu au plecat încă mai departe.` : null;

  const outTotal = total(outbound);
  const byKind = new Map<string, { amount: number; targets: Set<string> }>();
  for (const e of outbound) {
    const k = EXIT_KINDS.has(kind(e.target)) ? kind(e.target) : "cont";
    const v = byKind.get(k) ?? { amount: 0, targets: new Set<string>() };
    v.amount += e.amount;
    v.targets.add(e.target);
    byKind.set(k, v);
  }
  const ranked = Array.from(byKind.entries()).sort((a, b) => b[1].amount - a[1].amount);
  const [topKind, top] = ranked[0];
  const second = ranked[1];
  let dest = DEST_WORDS[topKind]?.(top.targets.size) ?? "mai departe";
  if (second && second[1].amount >= 0.25 * outTotal) dest += ` și ${DEST_WORDS[second[0]]?.(second[1].targets.size) ?? ""}`.trimEnd();
  else if (top.amount < 0.9 * outTotal) dest = `mai ales ${dest}`;

  // viteza: pentru fiecare plată primită, cât a trecut până la prima ieșire de după ea
  const outTs = tsList(outbound).sort((a, b) => a - b);
  const delays: number[] = [];
  for (const t of inTs) {
    const next = outTs.find((o) => o >= t);
    if (next !== undefined) delays.push(next - t);
  }
  const speed = delays.length ? speedPhrase(Math.max(...delays)) : "";
  // „…spre un exchange crypto în sub 6 ore” sau „…, mai ales spre un exchange crypto, în sub 6 ore”
  const tail = dest.startsWith("mai ales") ? `, ${dest}${speed ? `,${speed}` : ""}` : ` ${dest}${speed}`;

  const inTotal = total(inbound);
  if (!first) return `${subj} trimis ${money(outTotal)}${tail}.`;
  const joiner = first.includes(" și încă ") ? `; ${verb}` : ` și ${verb}`;
  if (inTotal <= 0) return `${first}${joiner} trimis ${money(outTotal)}${tail}.${still}`;
  const share = Math.min(1, outTotal / inTotal);
  const part = share >= 0.995 ? "toți banii" : `${Math.round(share * 100)}%`;
  return `${first}${joiner} trimis ${part} mai departe${tail}.${still}`;
}
