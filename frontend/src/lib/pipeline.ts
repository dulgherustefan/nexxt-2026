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
 * The client-zone graph, in demo order:
 * Intake → Classifier → Deadline clock → 4 evidence collectors in parallel → Rules engine → Refund,
 * then on the recovery path: Prosecutor ‖ Defender → Weigher → Recovery → Letter → Letter check → Seal.
 * Positions are a two-lane grid; the backend may send a different graph in CaseDetail.pipeline.
 */
const W = 162;
// IDs are the LangGraph node IDs (versoml/zone_client/agents.py); they never change with the language.
export const STAGES: StageSpec[] = [
  { id: "receptor", label: "Intake", agent: "Intake", model: "haiku", hint: "An isolated model with no tools turns the customer’s message into typed fields", x: 0, y: 74 },
  { id: "clasificator", label: "Classifier", agent: "Classifier", model: "none", hint: "Calibrated ML model: channel, dispute type, scam pattern", x: W, y: 74 },
  { id: "ceasornicar", label: "Deadline clock", agent: "Deadline clock", model: "none", hint: "Deadlines on the Romanian calendar: next business day, 15/35 business days, 13 months", x: W * 2, y: 74 },
  { id: "colector_tranzactie", label: "Transaction", agent: "Transaction collector", model: "none", hint: "Core banking: the payment and the payee", x: W * 3, y: -40 },
  { id: "colector_sca", label: "Authentication (SCA)", agent: "SCA collector", model: "none", hint: "What the approval screen showed the customer", x: W * 3, y: 36 },
  { id: "colector_dispozitiv", label: "Device", agent: "Device collector", model: "none", hint: "Device, session and the time of the click", x: W * 3, y: 112 },
  { id: "colector_domeniu", label: "Fake website", agent: "Domain collector", model: "none", hint: "Domain age, certificate logs, look-alike score, page similarity", x: W * 3, y: 188 },
  { id: "motor_reguli", label: "Rules engine", agent: "Rules engine", model: "none", hint: "Decides deterministically, with a rule ID on every decision", x: W * 4, y: 74 },
  { id: "outbox_aml", label: "AML referral", agent: "Diode", model: "none", hint: "Signed dispute facts only", x: W * 5, y: -10 },
  { id: "rambursare", label: "Refund", agent: "Refund", model: "none", hint: "Only the rules engine issues the refund; a person signs above the limit", x: W * 5, y: 150 },
  { id: "procuror", label: "Prosecutor", agent: "Prosecutor", model: "opus", hint: "Arguments for gross negligence, each with a citation", x: 0, y: 292 },
  { id: "avocat", label: "Defender", agent: "Defender", model: "sonnet", hint: "Arguments for the customer, from a different model", x: 0, y: 368 },
  { id: "cantaritor", label: "Weigher", agent: "Weigher", model: "none", hint: "A fixed rubric; a person signs the recommendation", x: W, y: 330 },
  { id: "recuperare", label: "Recovery", agent: "Recovery", model: "sonnet", hint: "Chargeback, camt.056 recall, phishing report: all drafts", x: W, y: 444 },
  { id: "redactor", label: "Letter", agent: "Letter writer", model: "sonnet", hint: "Answers every point, with deadlines and where to complain", x: W * 2, y: 380 },
  { id: "filtru_zid", label: "Letter check", agent: "Letter check", model: "none", hint: "Blocks banned terms and personal data, then sends the letter to a person", x: W * 3, y: 380 },
  { id: "sigiliu", label: "Seal", agent: "Evidence ledger", model: "none", hint: "Merkle root signed with Ed25519, plus a QR code", x: W * 4, y: 380 },
];

/** Steps that exist in the graph but are not part of the product any more (the AML referral). */
export const HIDDEN_STEPS = new Set(["outbox_aml"]);

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
    const tail = s.replace(/^(colector|collector|judecatorul|investigatorul|zid|judge)/, "");
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
