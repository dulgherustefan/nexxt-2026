import { slug } from "../api/format";
import type { AgentEvent, NodeStatus, PipelineEdge, PipelineNode } from "../api/types";

export type ModelBadge = "opus" | "sonnet" | "haiku" | "none";

export interface StageSpec {
  id: string;
  label: string;
  agent: string;
  model: ModelBadge;
  hint: string;
  x: number;
  y: number;
}

/**
 * Graful Judecătorului (docs/05 §7.1), în ordinea din demo:
 * Receptor → Clasificator → Ceasornicar → 4 colectori în paralel → Motor de reguli → Rambursare
 * și, pe traseul de recuperare: Procuror ‖ Avocat → Cântăritor → Recuperare → Redactor → Filtru zid → Sigiliu.
 * Pozițiile sunt o grilă pe două benzi; backend-ul poate trimite alt graf în CaseDetail.pipeline.
 */
const W = 162;
// ID-urile sunt cele ale nodurilor din graful LangGraph (versoml/zone_client/agents.py, PIPELINE_NODES)
export const STAGES: StageSpec[] = [
  { id: "receptor", label: "Receptor", agent: "Judecătorul/Receptor", model: "haiku", hint: "LLM izolat, fără tool-uri: textul clientului devine câmpuri tipizate", x: 0, y: 74 },
  { id: "clasificator", label: "Clasificator", agent: "Judecătorul/Clasificator", model: "none", hint: "M1 calibrat: canal, tip de dispută, scenariu", x: W, y: 74 },
  { id: "ceasornicar", label: "Ceasornicar", agent: "Judecătorul/Ceasornicar", model: "none", hint: "Termene cu calendarul RO: T+1, 15/35 zile, 13 luni", x: W * 2, y: 74 },
  { id: "colector_tranzactie", label: "Tranzacție", agent: "Judecătorul/Colector tranzacție", model: "none", hint: "bank-core: plata și beneficiarul", x: W * 3, y: -40 },
  { id: "colector_sca", label: "Autentificare SCA", agent: "Judecătorul/Colector SCA", model: "none", hint: "sca-logs: ce a afișat ecranul de autentificare", x: W * 3, y: 36 },
  { id: "colector_dispozitiv", label: "Dispozitiv", agent: "Judecătorul/Colector dispozitiv", model: "none", hint: "device: dispozitivul, sesiunea, momentul click-ului", x: W * 3, y: 112 },
  { id: "colector_domeniu", label: "Domeniu fals", agent: "Judecătorul/Colector domeniu", model: "none", hint: "domain-intel: RDAP, CT, sosie M3, asemănare M4", x: W * 3, y: 188 },
  { id: "motor_reguli", label: "Motor de reguli", agent: "Motorul de reguli", model: "none", hint: "Decide determinist, cu ID de regulă pe fiecare decizie", x: W * 4, y: 74 },
  { id: "outbox_aml", label: "Semnal spre AML", agent: "Zidul/Diodă", model: "none", hint: "Doar DisputeFacts, semnat HMAC; victima apare ca pseudonim", x: W * 5, y: -10 },
  { id: "rambursare", label: "Rambursare T+1", agent: "Judecătorul/Rambursare", model: "none", hint: "Doar motorul de reguli emite instrucțiunea; peste plafon semnează un om", x: W * 5, y: 150 },
  { id: "procuror", label: "Procuror", agent: "Judecătorul/Procuror", model: "opus", hint: "Argumente pentru neglijență gravă, cu citări", x: 0, y: 292 },
  { id: "avocat", label: "Avocat", agent: "Judecătorul/Avocat", model: "sonnet", hint: "Argumente pentru client, alt model decât Procurorul", x: 0, y: 368 },
  { id: "cantaritor", label: "Cântăritor", agent: "Judecătorul/Cântăritor", model: "none", hint: "Rubrică deterministă; recomandarea o semnează omul", x: W, y: 330 },
  { id: "recuperare", label: "Recuperare", agent: "Judecătorul/Recuperare", model: "sonnet", hint: "Rechemare camt.056, chargeback, raport DNSC: ciorne", x: W, y: 444 },
  { id: "redactor", label: "Scrisoare", agent: "Judecătorul/Redactor", model: "sonnet", hint: "Răspunde la fiecare punct, cu termene și căile de sesizare", x: W * 2, y: 380 },
  { id: "filtru_zid", label: "Filtru zid", agent: "Zidul/Filtru scrisori", model: "none", hint: "Termeni interziși, canary, date personale: blochează și trimite la om", x: W * 3, y: 380 },
  { id: "sigiliu", label: "Sigiliu", agent: "Registrul de probe", model: "none", hint: "Rădăcină Merkle semnată Ed25519 + QR", x: W * 4, y: 380 },
];

export interface FlowEdgeSpec extends PipelineEdge {
  /** Muchiile care trec de pe banda de sus pe cea de jos coboară la această înălțime. */
  wrapY?: number;
}

export const STAGE_EDGES: FlowEdgeSpec[] = [
  { source: "receptor", target: "clasificator" },
  { source: "clasificator", target: "ceasornicar" },
  { source: "ceasornicar", target: "colector_tranzactie" },
  { source: "ceasornicar", target: "colector_sca" },
  { source: "ceasornicar", target: "colector_dispozitiv" },
  { source: "ceasornicar", target: "colector_domeniu" },
  { source: "colector_tranzactie", target: "motor_reguli" },
  { source: "colector_sca", target: "motor_reguli" },
  { source: "colector_dispozitiv", target: "motor_reguli" },
  { source: "colector_domeniu", target: "motor_reguli" },
  { source: "motor_reguli", target: "outbox_aml" },
  { source: "outbox_aml", target: "rambursare" },
  { source: "rambursare", target: "procuror", wrapY: 273 },
  { source: "rambursare", target: "avocat", wrapY: 273 },
  { source: "rambursare", target: "recuperare", wrapY: 273 },
  { source: "procuror", target: "cantaritor" },
  { source: "avocat", target: "cantaritor" },
  { source: "cantaritor", target: "redactor" },
  { source: "recuperare", target: "redactor" },
  { source: "redactor", target: "filtru_zid" },
  { source: "filtru_zid", target: "sigiliu" },
];

export const STAGE_BY_ID: Record<string, StageSpec> = Object.fromEntries(STAGES.map((s) => [s.id, s]));

export function normalizeModel(m: string | null | undefined): ModelBadge {
  const s = slug(m);
  if (s.includes("opus")) return "opus";
  if (s.includes("sonnet")) return "sonnet";
  if (s.includes("haiku")) return "haiku";
  return "none";
}

export function normalizeStatus(s: string | null | undefined): NodeStatus {
  switch (slug(s)) {
    case "running":
    case "inlucru":
    case "started":
      return "running";
    case "done":
    case "finished":
    case "ok":
    case "completed":
      return "done";
    case "blocked":
    case "denied":
      return "blocked";
    case "waiting":
    case "interrupt":
    case "pending":
      return "waiting";
    case "skipped":
      return "skipped";
    case "error":
    case "failed":
      return "error";
    default:
      return "idle";
  }
}

/** Găsește nodul unui eveniment: întâi după `step`, apoi tolerant (fără diacritice, fără punctuație), apoi după agent. */
export function matchNode(nodes: Pick<PipelineNode, "id" | "label" | "agent">[], e: Pick<AgentEvent, "step" | "agent">): string | null {
  if (e.step) {
    const exact = nodes.find((n) => n.id === e.step);
    if (exact) return exact.id;
    const s = slug(e.step);
    const loose = nodes.find((n) => slug(n.id) === s || slug(n.label) === s);
    if (loose) return loose.id;
    const tail = s.replace(/^(colector|collector|judecatorul|investigatorul|zid)/, "");
    const partial = nodes.find((n) => tail.length > 2 && (slug(n.id).endsWith(tail) || slug(n.label) === tail));
    if (partial) return partial.id;
  }
  if (e.agent) {
    const a = slug(e.agent);
    const byAgent = nodes.find((n) => slug(n.agent) === a || (n.label && a.endsWith(slug(n.label))));
    if (byAgent) return byAgent.id;
  }
  return null;
}

export interface LiveNodeState {
  status: NodeStatus;
  live?: string;
  tools: number;
  lastTool?: string;
}

/** Reduce fluxul de evenimente la starea fiecărui nod. */
export function reduceNodeStates(nodes: Pick<PipelineNode, "id" | "label" | "agent" | "status">[], events: AgentEvent[]): Record<string, LiveNodeState> {
  const out: Record<string, LiveNodeState> = {};
  for (const n of nodes) out[n.id] = { status: normalizeStatus(n.status), tools: 0 };
  for (const e of events) {
    if (e.type === "RUN_STARTED") {
      for (const n of nodes) out[n.id] = { status: "idle", tools: 0 };
      continue;
    }
    const id = matchNode(nodes, e);
    if (!id) continue;
    const st = out[id];
    switch (e.type) {
      case "STEP_STARTED":
        if (st.status !== "done") st.status = "running";
        break;
      case "STEP_FINISHED": {
        const declared = normalizeStatus(typeof e.data?.status === "string" ? e.data.status : null);
        st.status = e.data?.skipped ? "skipped" : e.data?.blocked ? "blocked" : declared !== "idle" ? declared : "done";
        if (e.message) st.live = e.message;
        break;
      }
      case "TOOL_CALL_START":
        st.tools += 1;
        st.lastTool = (e.data?.tool as string | undefined) ?? e.message ?? undefined;
        if (st.status === "idle") st.status = "running";
        break;
      case "RUN_ERROR":
        st.status = "error";
        break;
      case "CUSTOM":
        if (e.name === "policy_denied" || e.name === "wall_block") st.status = "blocked";
        if (e.name === "interrupt") {
          const pending = e.data?.pending !== false;
          st.status = pending ? "waiting" : "done";
        }
        if (e.message) st.live = e.message;
        break;
      default:
        if (e.message && st.status === "running") st.live = e.message;
    }
  }
  return out;
}

/** Nodurile de afișat: graful trimis de backend sau, dacă lipsește, graful canonic. */
export function resolvePipeline(p: { nodes: PipelineNode[]; edges: PipelineEdge[] } | null | undefined): {
  nodes: Array<PipelineNode & { x: number; y: number; hint?: string }>;
  edges: FlowEdgeSpec[];
} {
  if (!p || !p.nodes?.length) {
    return {
      nodes: STAGES.map((s) => ({ id: s.id, label: s.label, agent: s.agent, model: s.model, status: "idle", x: s.x, y: s.y, hint: s.hint })),
      edges: STAGE_EDGES,
    };
  }
  // Nodurile cunoscute își păstrează locul din grilă; cele noi se așază pe un rând suplimentar.
  let extra = 0;
  const nodes = p.nodes.map((n) => {
    const known = STAGE_BY_ID[n.id] ?? STAGES.find((s) => slug(s.label) === slug(n.label));
    if (known) return { ...n, x: known.x, y: known.y, hint: known.hint };
    const pos = { x: (extra % 6) * W, y: 476 + Math.floor(extra / 6) * 84 };
    extra += 1;
    return { ...n, ...pos };
  });
  const edges: FlowEdgeSpec[] = (p.edges?.length ? p.edges : STAGE_EDGES).map((e) => {
    const known = STAGE_EDGES.find((k) => k.source === e.source && k.target === e.target);
    return known ? { ...e, wrapY: known.wrapY } : e;
  });
  return { nodes, edges };
}
