/**
 * The simulation engine: turns a story into a run of the case graph, with AG-UI events
 * (STEP_*, TOOL_CALL_*, TEXT_MESSAGE_*, CUSTOM fact/rule_hit/decision/interrupt/ledger_seal/hold_signal).
 * The same timeline serves the pre-run inbox cases (on a fake clock) and live runs (on the real clock).
 */
import qrcode from "qrcode-generator";
import { disputeLabel, money, scenarioLabel, verdictLabel } from "../api/format";
import type { AgentEvent, CaseDetail, Decision, EventType, Fact, GroundingEntry, MatchResult, NodeStatus, RoutingEntry, RuleHit } from "../api/types";
import { matchNode, STAGES, STAGE_BY_ID, STAGE_EDGES, type StageSpec } from "../lib/pipeline";
import { fmtDay, fmtDayTime, isoRo } from "./calendar";
import { canonical, merkleRoot, sha256 } from "./sha256";
import { kbPassage } from "./kb";
import { plainReason, storyFor, type DecisionSeed, type FactSeed, type Story, type StoryCtx } from "./stories";

export interface Approval {
  action: "approve" | "reject";
  at: number;
  approver: string;
  note?: string;
}

export interface RunState {
  runId: string;
  startedAt: number;
  cursorA: number;
  cursorB1: number;
  cursorB2: number;
  approval: Approval | null;
  /** A person's answer to "which payment?": the run waits at Identification until it arrives. */
  pick?: { at: number; txId: string | null; approver: string } | null;
  done: boolean;
}

export interface SealState {
  root: string;
  signature: string;
  public_key: string;
  count: number;
  sealed_at: string;
  qr_svg: string;
}

export interface MockCase {
  caseId: string;
  customerRef: string;
  scenario: string;
  ctx: StoryCtx;
  detail: CaseDetail;
  events: AgentEvent[];
  keyToFact: Record<string, string>;
  run: RunState | null;
  seal: SealState | null;
  createdAt: number;
}

export interface EngineHooks {
  nextSeq: () => number;
  onDiode?: (c: MockCase, story: Story, at: number) => void;
  onRefund?: (c: MockCase, at: number) => void;
  /** Other open disputes in the same campaign (same payee and link). */
  linkedCases?: (c: MockCase) => string[];
}

interface Exec {
  c: MockCase;
  story: Story;
  at: number;
  hooks: EngineHooks;
}

type Apply = (x: Exec) => void;
interface Step {
  t: number;
  apply: Apply;
}

export interface Timeline {
  A: Step[];
  B1: Step[];
  B2: Step[];
  aEnd: number;
  needsApproval: boolean;
  /** The time of the "which payment?" interrupt, or null when the payment is already known. */
  gate: number | null;
}

// ------------------------------------------------------------------ helpers

export const PUBLIC_KEY = `ed25519:${sha256("versoml-demo-ledger-key").slice(0, 64)}`;

/**
 * The stories name their steps the short way ("reguli", "colector.tranzactie"); the canonical graph
 * uses the backend's node IDs ("motor_reguli", "colector_tranzactie"). Same loose match as the UI.
 */
function stageOf(step: string | null | undefined): StageSpec | undefined {
  if (!step) return undefined;
  const exact = STAGE_BY_ID[step];
  if (exact) return exact;
  const id = matchNode(STAGES, { step, agent: null });
  return id ? STAGE_BY_ID[id] : undefined;
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

function emit(x: Exec, type: EventType, fields: Partial<AgentEvent> = {}): AgentEvent {
  const step = fields.step ?? null;
  const ev: AgentEvent = {
    type,
    zone: "client",
    run_id: x.c.run?.runId ?? "run-0",
    case_id: x.c.caseId,
    seq: x.hooks.nextSeq(),
    ts: isoRo(x.at),
    step,
    agent: fields.agent ?? stageOf(step)?.agent ?? null,
    name: fields.name ?? null,
    message: fields.message ?? null,
    data: fields.data ?? {},
  };
  x.c.events.push(ev);
  return ev;
}

function setNode(x: Exec, id: string, status: NodeStatus, summary?: string) {
  const nodes = x.c.detail.pipeline?.nodes;
  const canonicalId = stageOf(id)?.id;
  const n = nodes?.find((k) => k.id === id) ?? (canonicalId ? nodes?.find((k) => k.id === canonicalId) : undefined);
  if (n) {
    n.status = status;
    if (summary) n.summary = summary;
  }
}

function start(x: Exec, step: string, message: string) {
  setNode(x, step, "running", message);
  emit(x, "STEP_STARTED", { step, message });
}

function finish(x: Exec, step: string, message: string, status: NodeStatus = "done", data: Record<string, unknown> = {}) {
  setNode(x, step, status, message);
  emit(x, "STEP_FINISHED", { step, message, data: { ...data, status } });
}

function addFact(x: Exec, seed: FactSeed): Fact {
  const facts = (x.c.detail.facts ??= []);
  const fact_id = `EV-${String(facts.length + 1).padStart(3, "0")}`;
  const prev = facts.length ? facts[facts.length - 1].sha256 : null;
  const content = seed.content ?? {};
  const payload = { fact_id, case_id: x.c.caseId, kind: seed.kind, source_tool: seed.tool, summary: seed.summary, content };
  const fact: Fact = {
    fact_id,
    case_id: x.c.caseId,
    zone: "client",
    kind: seed.kind,
    source_tool: seed.tool,
    args_hash: `sha256:${sha256(canonical({ tool: seed.tool, case_id: x.c.caseId }))}`,
    retrieved_at: isoRo(x.at),
    sha256: sha256((prev ?? "") + canonical(payload)),
    prev_hash: prev,
    labels: { conf: seed.conf ?? "client", trust: seed.trust ?? "trusted", sinks: seed.sinks ?? ["client"] },
    summary: seed.summary,
    content,
  };
  facts.push(fact);
  x.c.keyToFact[seed.key] = fact_id;
  if (x.c.detail.ledger) {
    x.c.detail.ledger.count = facts.length;
    if (x.c.seal) x.c.detail.ledger.sealed = false;
  }
  return fact;
}

function cite(x: Exec, keys: string[] | undefined): string[] {
  return (keys ?? []).map((k) => x.c.keyToFact[k]).filter((v): v is string => Boolean(v));
}

function factStep(x: Exec, seed: FactSeed) {
  emit(x, "TOOL_CALL_START", { step: seed.stage, message: seed.tool, data: { tool: seed.tool } });
  const f = addFact(x, seed);
  emit(x, "TOOL_CALL_END", { step: seed.stage, message: seed.tool, data: { tool: seed.tool, fact_id: f.fact_id } });
  emit(x, "CUSTOM", {
    step: seed.stage,
    name: "fact",
    message: `${f.fact_id} · ${seed.summary}`,
    data: { fact_id: f.fact_id, kind: f.kind, source_tool: f.source_tool, sha256: f.sha256, summary: f.summary },
  });
}

function toDecision(x: Exec, d: DecisionSeed): Decision {
  return {
    case_id: x.c.caseId,
    question: d.question,
    decision: d.decision,
    rule_ids: d.rule_ids,
    supporting_evidence: cite(x, d.supporting),
    contradicting_evidence: cite(x, d.contradicting),
    missing_evidence: d.missing ?? [],
    rationale: d.rationale.map((l) => ({ text: l.text, cites: cite(x, l.cites) })),
    unknowns: d.unknowns ?? [],
    next_actions: d.next_actions ?? [],
    requires_human: d.requires_human ?? false,
    deadline: d.deadline ?? null,
    amount: d.question === "rambursare_t1" ? { value: x.c.ctx.amount, currency: "RON" } : null,
    decided_by: "rules",
  };
}

function decisionStep(x: Exec, d: DecisionSeed) {
  const dec = toDecision(x, d);
  const list = (x.c.detail.decisions ??= []);
  const i = list.findIndex((k) => k.question === dec.question);
  if (i >= 0) list[i] = dec;
  else list.push(dec);
  if (x.c.detail.rules) x.c.detail.rules.decisions = list;
  const why = plainReason(d, x.c.ctx, x.story);
  const reasons = (x.c.detail.reasons ??= []).filter((r) => r.decision !== dec.decision);
  reasons.push({ rule_id: why.rule_id, decision: dec.decision, sentence: why.sentence });
  x.c.detail.reasons = reasons;
  emit(x, "CUSTOM", {
    step: d.stage,
    name: "decision",
    message: `${verdictLabel(dec.decision)} · ${dec.rule_ids?.join(", ")}`,
    data: { question: dec.question, decision: dec.decision, rule_ids: dec.rule_ids, requires_human: dec.requires_human },
  });
}

function hitStep(x: Exec, h: Story["hits"][number]) {
  const hit: RuleHit = {
    rule_id: h.rule_id,
    version: "1",
    title: h.title,
    basis: h.basis,
    confidence: h.confidence,
    outcome: h.outcome,
    explanation: h.explanation ?? "",
    inputs: cite(x, h.inputs),
    params: h.params ?? {},
  };
  x.c.detail.rules?.hits?.push(hit);
  emit(x, "CUSTOM", { step: "reguli", name: "rule_hit", message: `${hit.rule_id} · ${hit.outcome}`, data: { rule_id: hit.rule_id, outcome: hit.outcome, confidence: hit.confidence } });
}

function resolveLetter(x: Exec, body: string): { body: string; cites: string[] } {
  const cites: string[] = [];
  const out = body.replace(/\[\[([a-z0-9_]+)\]\]/gi, (_m, key: string) => {
    const id = x.c.keyToFact[key];
    if (!id) return "";
    cites.push(id);
    return `[${id}]`;
  });
  return { body: out.replace(/ +\n/g, "\n"), cites: Array.from(new Set(cites)) };
}

function chunks(text: string, n = 3): string[] {
  const words = text.split(" ");
  const size = Math.ceil(words.length / n);
  const out: string[] = [];
  for (let i = 0; i < words.length; i += size) out.push(words.slice(i, i + size).join(" ") + (i + size < words.length ? " " : ""));
  return out;
}

export function sealCase(c: MockCase, at: number): SealState {
  const facts = c.detail.facts ?? [];
  const root = merkleRoot(facts.map((f) => f.sha256));
  const signature = `${sha256(`ed25519-sim|${root}`)}${sha256(`ed25519-sim-2|${root}`)}`;
  const qr = qrcode(0, "M");
  qr.addData(`versoml:verify:${c.caseId}:${root}`);
  qr.make();
  const seal: SealState = {
    root,
    signature,
    public_key: PUBLIC_KEY,
    count: facts.length,
    sealed_at: isoRo(at),
    qr_svg: qr.createSvgTag({ cellSize: 4, margin: 2, scalable: true }),
  };
  c.seal = seal;
  c.detail.ledger = { count: facts.length, root, sealed: true };
  return seal;
}

// ------------------------------------------------------------------ identification, routing, grounding

const clone = <T>(v: T): T => JSON.parse(JSON.stringify(v)) as T;

/** The match for a case whose payment came with it (Demo Bank, the seeded inbox). */
function defaultMatch(c: MockCase, story: Story): MatchResult {
  const payee = story.beneficiary ? `Transfer to ${story.beneficiary.iban_masked}` : story.channel === "card" ? "Card payment" : "Transfer";
  return {
    customer_ref: c.customerRef,
    customer_match_reason: "Signed in to the Demo Bank app.",
    tx_id: c.ctx.txId,
    confidence: 0.99,
    needs_human: false,
    reason: "The customer picked the payment in the app.",
    candidates: [{ tx_id: c.ctx.txId, amount: c.ctx.amount, currency: "RON", ts: isoRo(c.ctx.executedAt), payee, channel: story.channel, direction: "out", score: 0.99, reasons: ["Picked by the customer in the app"] }],
  };
}

function matchOf(x: Exec): MatchResult {
  return x.c.ctx.intake?.match ?? defaultMatch(x.c, x.story);
}

function matchSummary(m: MatchResult, alias: string): string {
  if (!m.customer_ref) return "No customer found from the message.";
  const who = `${alias} (${m.customer_ref}): ${m.customer_match_reason ?? "identified"}`;
  if (m.tx_id) return `${who} Payment ${m.tx_id}: ${m.reason} Score ${m.confidence.toFixed(2)}.`;
  if (m.candidates.length && m.needs_human) return `${who} ${plural(m.candidates.length, "payment", "payments")} could match: a person picks one.`;
  return `${who} ${m.reason}`;
}

function identifyStep(x: Exec) {
  const m = matchOf(x);
  x.c.detail.match = clone(m);
  factStep(x, {
    key: "match",
    stage: "identificare",
    kind: "intake.match",
    tool: "bank-core.find_disputed_payment",
    summary: matchSummary(m, x.c.ctx.alias),
    content: { customer_ref: m.customer_ref, tx_id: m.tx_id, confidence: m.confidence, candidates: m.candidates.length, needs_human: m.needs_human },
  });
  emit(x, "CUSTOM", { step: "identificare", name: "match", message: m.reason, data: clone(m) as unknown as Record<string, unknown> });
}

function route(x: Exec, entry: RoutingEntry, step = "router") {
  const list = (x.c.detail.routing ??= []).filter((r) => r.node !== entry.node);
  list.push(entry);
  x.c.detail.routing = list;
  emit(x, "CUSTOM", { step, name: "routing", message: `${entry.run ? "Runs" : "Skipped"}: ${entry.node}. ${entry.reason}`, data: { ...entry } });
}

/** The router's plan for the evidence collectors: who runs on this case, and why. */
function collectorPlan(story: Story, ctx: StoryCtx): RoutingEntry[] {
  const noTx = Boolean(ctx.intake?.noTx);
  const has = (stage: string) => story.facts.some((f) => f.stage === stage);
  const none = "No payment identified yet, so there is nothing to check.";
  return [
    noTx
      ? { node: "colector_tranzactie", run: false, reason: none }
      : { node: "colector_tranzactie", run: true, reason: "The payment is identified: get it and the payee from core banking." },
    noTx ? { node: "colector_sca", run: false, reason: none }
      : has("colector.sca")
        ? { node: "colector_sca", run: true, reason: story.channel === "card" ? "A card payment: check how it was authenticated." : "Check what the approval screen showed the customer." }
        : { node: "colector_sca", run: false, reason: "How the payment was approved doesn't change this kind of claim." },
    noTx ? { node: "colector_dispozitiv", run: false, reason: none }
      : has("colector.dispozitiv")
        ? { node: "colector_dispozitiv", run: true, reason: "Check the device and the session behind the payment." }
        : { node: "colector_dispozitiv", run: false, reason: "Nothing in the claim points to a new device or a remote session." },
    has("colector.domeniu")
      ? { node: "colector_domeniu", run: true, reason: "The message has a link: check the website." }
      : { node: "colector_domeniu", run: false, reason: noTx ? none : "No link in the message." },
    story.beneficiary && !noTx
      ? { node: "colector_campanie", run: true, reason: "Fraud with a payee: look for other disputes with the same payee or link." }
      : { node: "colector_campanie", run: false, reason: "No payee or link to compare with other disputes." },
  ];
}

function campaignStep(x: Exec) {
  const b = x.story.beneficiary;
  const others = x.hooks.linkedCases?.(x.c) ?? [];
  if (b && others.length) {
    x.c.detail.campaign = {
      campaign_id: "CAMP-2026-07",
      case_ids: [x.c.caseId, ...others],
      shared_indicators: [
        { kind: "payee_account", value_masked: b.iban_masked },
        ...(b.domain ? [{ kind: "domain", value_masked: b.domain }] : []),
      ],
      similarity: 0.92,
    };
  }
  factStep(x, {
    key: "campaign",
    stage: "colector.campanie",
    kind: "case.campaign",
    tool: "cases.link_by_indicators",
    summary: others.length
      ? `${plural(others.length, "other dispute", "other disputes")} paid the same account ${b?.iban_masked ?? ""} after the same fake page.`
      : "No other dispute shares this payee or link yet.",
    content: { linked: others.length },
  });
}

function ground(x: Exec, usedIn: GroundingEntry["used_in"], ids: string[]) {
  const hits = ids.map((id, i) => kbPassage(id, i + 1)).filter((h): h is NonNullable<typeof h> => Boolean(h));
  const keep = (x.c.detail.grounding ?? []).filter((g) => g.used_in !== usedIn);
  x.c.detail.grounding = [...keep, ...hits.map((hit) => ({ used_in: usedIn, hit }))];
}

function letterSources(story: Story): string[] {
  const ids: string[] = [];
  if (story.verdict === "RAMBURSEAZA" || story.verdict === "RAMBURSEAZA_CU_APROBARE") ids.push("ctx:l209#art-173-174");
  if (story.verdict === "RESPINGE_TARDIV") ids.push("ctx:l209#art-169");
  if (story.verdict === "INFORMATII_SUPLIMENTARE") ids.push("rule:DSP-58");
  return [...ids, "ctx:l209#art-224", "ctx:l209#art-225"];
}

/** Every amount, date and time in the letter, checked against the evidence. One story shows a corrected number. */
function numericCheck(x: Exec) {
  const body = x.c.detail.letter?.body ?? "";
  const checked = (body.match(/RON [\d,.]+|\b\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w* \d{4}\b|\b\d{2}:\d{2}\b/g) ?? []).length;
  const fixed = x.story.scenario === "card_visa_secure";
  x.c.detail.numeric_check = {
    passed: true,
    checked: Math.max(checked, 1),
    mismatches: fixed ? [{ value: money(x.c.ctx.amount + 45), expected: money(x.c.ctx.amount), where: "letter" }] : [],
    rewritten: fixed,
  };
}

const PHRASES: Record<string, string> = {
  demo_t1: "Paid after a fake courier text",
  phishing_link: "Paid after a fake courier text",
  inel_carausi: "Paid the same account as other victims",
  injectie_document: "Fake courier text, PDF with hidden instructions",
  card_ecom_fara_3ds: "Online card payment the customer doesn't recognize",
  card_visa_secure: "Online card payment approved with Visa Secure",
  vishing_securitate: "Approved a payment during a fake bank call",
  cont_sigur: "Moved money to a “safe account”",
  marfa_nelivrata: "Paid for goods that never came",
  sim_swap: "Transfer after the phone lost signal",
  frauda_client: "Disputes a card payment made in person",
  reclamatie_tardiva: "Old card payment, reported after 13 months",
  plata_dubla: "Charged twice for one payment",
};

export function scenarioPhrase(scenario: string, ctx: StoryCtx): string {
  if (ctx.intake?.noTx) return "Payment not identified yet";
  if (ctx.intake?.pickNeeded && !ctx.intake.match.tx_id) return "Payment to be picked by a person";
  return PHRASES[scenario] ?? scenario.replace(/_/g, " ");
}

// ------------------------------------------------------------------ the timeline

export function buildTimeline(story: Story, ctx?: StoryCtx): Timeline {
  const A: Step[] = [];
  const B1: Step[] = [];
  const B2: Step[] = [];
  const at = (t: number, apply: Apply) => A.push({ t, apply });
  const byStage = (stage: string) => story.facts.filter((f) => f.stage === stage);

  at(0, (x) => {
    x.c.detail.summary.status = "IN_ANALIZA";
    for (const n of x.c.detail.pipeline?.nodes ?? []) {
      n.status = "idle";
      n.summary = undefined;
    }
    emit(x, "RUN_STARTED", { message: "Starting the case graph in the client zone." });
  });

  // Intake
  let t = 0.3;
  at(t, (x) => start(x, "receptor", "Reading the claim in the isolated model, which has no tools."));
  byStage("receptor").forEach((f, i) => at(0.8 + i * 0.5, (x) => factStep(x, f)));
  t = 0.8 + byStage("receptor").length * 0.5;
  at(t, (x) => {
    x.c.detail.complaint = { text: x.c.detail.complaint?.text || story.complaintText, attachments: x.c.detail.complaint?.attachments ?? story.attachments, received_at: isoRo(x.c.ctx.receivedAt) };
    x.c.detail.extracted = { ...story.extracted, ...(x.c.ctx.intake?.extracted ?? {}) };
    const inj = story.extracted.injection_suspected;
    if (inj) emit(x, "CUSTOM", { step: "receptor", name: "policy_denied", message: "Prompt injection in the document: treated as data and flagged.", data: { reason: "injection_suspected" } });
    finish(x, "receptor", inj ? "Typed fields extracted; the injection was flagged and ignored." : "Typed fields extracted from the untrusted text.");
  });

  // Identification: the customer and the payment. A person picks the payment when the match isn't sure.
  t += 0.2;
  at(t, (x) => start(x, "identificare", "Finding the customer and the disputed payment."));
  at(t + 0.45, (x) => identifyStep(x));
  t += 0.8;
  let gate: number | null = null;
  if (ctx?.intake?.pickNeeded) {
    gate = t;
    at(t, (x) => {
      const m = matchOf(x);
      x.c.detail.interrupt = { pending: true, kind: "pick_transaction", prompt: "Which payment does the customer dispute?", options: [], candidates: clone(m.candidates) };
      x.c.detail.summary.status = "ASTEAPTA_APROBARE";
      x.c.detail.summary.requires_human = true;
      // the refund clock runs from the customer's report (DSP-58), whether or not the payment is known yet
      x.c.detail.summary.deadline = x.c.ctx.t1;
      setNode(x, "identificare", "waiting", "Waiting for a person to pick the payment.");
      emit(x, "CUSTOM", {
        step: "identificare",
        name: "interrupt",
        message: "Which payment does the customer dispute? A person picks it.",
        data: { pending: true, kind: "pick_transaction", candidates: clone(m.candidates), payload: { kind: "pick_transaction", candidates: clone(m.candidates) } },
      });
    });
    t += 0.05;
    at(t, (x) => {
      const p = x.c.run?.pick;
      const m = matchOf(x);
      x.c.detail.interrupt = { pending: false, kind: "pick_transaction", options: [], answer: { action: "pick_transaction", approver: p?.approver, tx_id: p?.txId ?? null } };
      x.c.detail.match = clone(m);
      x.c.detail.summary.amount = { value: x.c.ctx.amount, currency: "RON" };
      x.c.detail.summary.status = "IN_ANALIZA";
      x.c.detail.summary.requires_human = false;
      x.c.detail.summary.scenario_phrase = scenarioPhrase(x.c.scenario, x.c.ctx);
      emit(x, "CUSTOM", { step: "identificare", name: "interrupt", message: p?.txId ? `${p.approver} picked ${p.txId}.` : `${p?.approver ?? "A person"}: none of these payments.`, data: { pending: false, kind: "pick_transaction", resolution: "pick_transaction", tx_id: p?.txId ?? null, approver: p?.approver } });
      emit(x, "CUSTOM", { step: "identificare", name: "match", message: m.reason, data: clone(m) as unknown as Record<string, unknown> });
      finish(x, "identificare", p?.txId ? `Payment ${p.txId}, picked by ${p.approver}.` : "No payment picked: VersoML asks the customer.");
    });
    t += 0.3;
  } else {
    at(t, (x) => {
      const m = matchOf(x);
      finish(x, "identificare", m.tx_id ? `${x.c.ctx.alias} · payment ${m.tx_id} · score ${m.confidence.toFixed(2)}` : m.customer_ref ? "Customer found, no payment matches." : "Customer not identified.");
    });
  }

  // Classifier
  t += 0.2;
  at(t, (x) => start(x, "clasificator", "Classifying the claim with the calibrated M1 model: channel, type, scam pattern."));
  byStage("clasificator").forEach((f, i) => at(t + 0.6 + i * 0.4, (x) => factStep(x, f)));
  t += 0.6 + byStage("clasificator").length * 0.4 + 0.2;
  at(t, (x) => {
    x.c.detail.classification = story.classification;
    const p = story.classification.probability ?? 0;
    finish(x, "clasificator", `${disputeLabel(story.classification.dispute_type)} · ${scenarioLabel(story.classification.scenario)} · p = ${p.toFixed(2)}`);
  });

  // Deadline clock
  t += 0.2;
  at(t, (x) => start(x, "ceasornicar", "Starting the legal clocks on the Romanian calendar."));
  story.deadlines.forEach((d, i) =>
    at(t + 0.35 + i * 0.15, (x) => {
      x.c.detail.rules?.deadlines?.push(d);
      if (d.rule_id === "PAY-03" || !x.c.detail.summary.deadline) x.c.detail.summary.deadline = d.due_at;
      emit(x, "CUSTOM", { step: "ceasornicar", name: "rule_hit", message: `${d.rule_id} · ${d.name}: ${fmtDayTime(d.due_at)}`, data: { rule_id: d.rule_id, deadline: d.due_at, name: d.name } });
    }),
  );
  t += 0.35 + story.deadlines.length * 0.15 + 0.2;
  at(t, (x) => {
    const refund = story.deadlines.find((d) => d.rule_id === "PAY-03");
    const due = x.c.detail.summary.deadline;
    finish(x, "ceasornicar", refund ? `Refund due by ${fmtDayTime(refund.due_at)}.` : due ? `Answer due by ${fmtDay(due)}.` : "Deadlines calculated.");
  });

  // The router picks the collectors this case needs
  const plan = ctx ? collectorPlan(story, ctx) : [];
  t += 0.2;
  at(t, (x) => start(x, "router", "Choosing the agents this case needs."));
  plan.forEach((r, i) => at(t + 0.25 + i * 0.1, (x) => route(x, r)));
  t += 0.25 + plan.length * 0.1 + 0.15;
  at(t, (x) => finish(x, "router", `${plan.filter((r) => r.run).length} of ${plan.length} evidence collectors needed.`));

  // The collectors, in parallel
  const collectors = ["colector.tranzactie", "colector.sca", "colector.dispozitiv", "colector.domeniu", "colector.campanie"];
  const cStart = t + 0.2;
  let collectorsEnd = cStart;
  collectors.forEach((cid, k) => {
    const s0 = cStart + k * 0.08;
    const planned = plan.find((r) => r.node === cid.replace(".", "_"));
    if (planned && !planned.run) {
      at(s0, (x) => finish(x, cid, planned.reason, "skipped", { skipped: true }));
      return;
    }
    if (cid === "colector.campanie") {
      at(s0, (x) => start(x, cid, stageOf(cid)?.hint ?? "Looking for linked cases."));
      at(s0 + 0.8, (x) => campaignStep(x));
      at(s0 + 1.3, (x) => finish(x, cid, x.c.detail.campaign ? `Linked to ${plural(x.c.detail.campaign.case_ids.length - 1, "other dispute", "other disputes")}.` : "No linked disputes."));
      collectorsEnd = Math.max(collectorsEnd, s0 + 1.3);
      return;
    }
    at(s0, (x) => start(x, cid, stageOf(cid)?.hint ?? "Collecting evidence."));
    const fs = byStage(cid);
    fs.forEach((f, j) => at(s0 + 0.6 + j * 0.95 + k * 0.22, (x) => factStep(x, f)));
    const end = fs.length ? s0 + 0.6 + (fs.length - 1) * 0.95 + k * 0.22 + 0.45 : s0 + 1.2;
    collectorsEnd = Math.max(collectorsEnd, end);
    at(end, (x) => finish(x, cid, fs.length ? `${plural(fs.length, "evidence item", "evidence items")} in the ledger.` : "Nothing relevant for this case."));
  });

  // The rules engine
  t = collectorsEnd + 0.3;
  const rStart = t;
  at(t, (x) => start(x, "reguli", "Running the rules on the facts, with no free text."));
  if (story.beneficiary) {
    at(t + 0.25, (x) => {
      emit(x, "TOOL_CALL_START", { step: "reguli", message: "dioda.send_facts", data: { tool: "dioda.send_facts" } });
      x.hooks.onDiode?.(x.c, story, x.at);
      emit(x, "TOOL_CALL_END", {
        step: "reguli",
        message: "DisputeFacts sent to the AML zone through the diode (HMAC-signed). Only a yes/no HOLD can come back.",
        data: { tool: "dioda.send_facts", victim_ref: x.c.ctx.victimRef },
      });
    });
  }
  story.hits.forEach((h, i) => at(rStart + 0.5 + i * 0.16, (x) => hitStep(x, h)));
  t = rStart + 0.5 + story.hits.length * 0.16;
  byStage("reguli").forEach((f, i) =>
    at(t + 0.15 + i * 0.35, (x) => {
      factStep(x, f);
      if (f.kind === "wall.hold_signal") {
        x.c.detail.hold = { received: true, approved_by: "ANALIST-07", authority_notified: true };
        emit(x, "CUSTOM", { step: "reguli", name: "hold_signal", message: "HOLD received through the diode: yes. No other details.", data: { hold: true } });
      }
    }),
  );
  t += 0.15 + byStage("reguli").length * 0.35 + 0.2;
  story.decisions.filter((d) => d.stage === "reguli").forEach((d, i) => at(t + i * 0.2, (x) => decisionStep(x, d)));
  t += story.decisions.filter((d) => d.stage === "reguli").length * 0.2 + 0.3;
  at(t, (x) => {
    x.c.detail.summary.verdict = story.verdict;
    finish(x, "reguli", `${verdictLabel(story.verdict)}`);
  });

  // The AML referral, a separate node as in the backend's graph
  t += 0.1;
  at(t, (x) => start(x, "outbox_aml", "Sending AML only facts about the attack and the payee, never the victim's identity."));
  at(t + 0.3, (x) => story.beneficiary
    ? finish(x, "outbox_aml", `Sent. The victim appears only as ${x.c.ctx.victimRef}.`)
    : finish(x, "outbox_aml", "Not a fraud case with a payee: nothing to send.", "skipped"));
  t += 0.3;

  // Refund
  t += 0.2;
  const rbStart = t;
  at(t, (x) => start(x, "rambursare", story.refund === "none" ? "Checking whether the next-business-day refund applies." : "Preparing the refund instruction (simulated)."));
  const needsApproval = story.refund === "approval" || story.refund === "exception";
  if (needsApproval) {
    at(t + 0.4, (x) => {
      const kind = story.refund === "approval" ? "aprobare_rambursare" : story.verdict === "RESPINGE_TARDIV" ? "aprobare_respingere" : "aprobare_exceptie";
      x.c.detail.interrupt = { pending: true, kind, prompt: story.approvalPrompt ?? "Confirm the decision.", options: ["approve", "reject"] };
      x.c.detail.summary.status = story.statusAfterRules;
      x.c.detail.summary.requires_human = true;
      setNode(x, "rambursare", "waiting", "Waiting for a person's signature.");
      emit(x, "CUSTOM", { step: "rambursare", name: "interrupt", message: story.approvalPrompt ?? "Waiting for approval.", data: { pending: true, kind } });
    });
  } else if (story.refund === "auto") {
    at(t + 0.5, (x) => {
      refundFact(x, "the rules engine (under the cap)");
      x.c.detail.summary.status = story.statusAfterRules;
      x.c.detail.summary.requires_human = false;
      finish(x, "rambursare", `Automatic refund: ${money(x.c.ctx.amount)}, under the cap.`);
    });
  } else {
    at(t + 0.4, (x) => {
      x.c.detail.summary.status = story.statusAfterRules;
      x.c.detail.summary.requires_human = story.decisions.some((d) => d.question === "rambursare_t1" && d.requires_human);
      finish(x, "rambursare", `${verdictLabel(story.verdict)}: no refund instruction.`, "skipped", { skipped: true });
    });
  }

  // Prosecutor and Defender (only on the recovery track)
  t = rbStart + 0.6;
  const cantPlanned = Boolean(story.debate) || story.decisions.some((d) => d.stage === "cantaritor");
  const noDebate = story.refund === "none" ? "No refund, so there is nothing to recover from the customer." : "Nothing points to negligence by the customer.";
  at(t - 0.05, (x) => {
    route(x, story.debate
      ? { node: "procuror", run: true, reason: "The customer may have been negligent: argue both sides before anyone asks them to repay." }
      : { node: "procuror", run: false, reason: noDebate });
    route(x, story.debate
      ? { node: "avocat", run: true, reason: "Argue for the customer, with a different model." }
      : { node: "avocat", run: false, reason: noDebate });
    route(x, cantPlanned
      ? { node: "cantaritor", run: true, reason: "Score both sides with the fixed rubric." }
      : { node: "cantaritor", run: false, reason: "Nothing to weigh." });
  });
  let debateEnd = t + 0.4;
  if (story.debate) {
    const runSide = (step: "procuror" | "avocat", lines: Array<{ text: string; cites?: string[] }>, offset: number) => {
      const s0 = t + offset;
      at(s0, (x) => start(x, step, step === "procuror" ? "Looking for evidence of gross negligence." : "Looking for evidence in the customer's favor."));
      let cur = s0 + 0.4;
      lines.forEach((line, i) => {
        const mid = `${step}-${i}`;
        at(cur, (x) => emit(x, "TEXT_MESSAGE_START", { step, data: { message_id: mid, role: step } }));
        chunks(line.text).forEach((ch, j) => at(cur + 0.25 + j * 0.25, (x) => emit(x, "TEXT_MESSAGE_CONTENT", { step, message: ch, data: { message_id: mid, delta: ch } })));
        cur += 0.25 + 3 * 0.25 + 0.1;
        at(cur, (x) => emit(x, "TEXT_MESSAGE_END", { step, data: { message_id: mid, cites: cite(x, line.cites) } }));
        cur += 0.2;
      });
      at(cur, (x) => finish(x, step, `${plural(lines.length, "argument", "arguments")}, each with citations.`));
      return cur;
    };
    const e1 = runSide("procuror", story.debate.prosecutor, 0);
    const e2 = runSide("avocat", story.debate.defender, 0.15);
    debateEnd = Math.max(e1, e2);
  } else {
    at(t, (x) => {
      finish(x, "procuror", "No debate: there is no recovery track against the customer.", "skipped", { skipped: true });
      finish(x, "avocat", "No debate.", "skipped", { skipped: true });
    });
  }

  // Weigher
  t = debateEnd + 0.2;
  const cantDecisions = story.decisions.filter((d) => d.stage === "cantaritor");
  if (story.debate || cantDecisions.length) {
    at(t, (x) => start(x, "cantaritor", "Weighing the arguments with the fixed rubric."));
    byStage("cantaritor").forEach((f, i) => at(t + 0.4 + i * 0.3, (x) => factStep(x, f)));
    t += 0.4 + byStage("cantaritor").length * 0.3;
    at(t, (x) => {
      if (story.debate) {
        x.c.detail.debate = {
          prosecutor: story.debate.prosecutor.map((l) => ({ text: l.text, cites: cite(x, l.cites) })),
          defender: story.debate.defender.map((l) => ({ text: l.text, cites: cite(x, l.cites) })),
          rubric: story.debate.rubric.map((r) => ({ indicator: r.indicator, value: r.value, weight: r.weight, cites: cite(x, r.cites) })),
          recommendation: story.debate.recommendation,
          ran: true,
        };
        ground(x, "debate", ["ctx:c-70-25#ruling", "ctx:l209#art-179-2", "ctx:l209#art-171-172", "ctx:l209#art-220"]);
      }
    });
    cantDecisions.forEach((d, i) => at(t + 0.2 + i * 0.2, (x) => decisionStep(x, d)));
    t += 0.2 + cantDecisions.length * 0.2 + 0.2;
    at(t, (x) => finish(x, "cantaritor", story.debate ? verdictLabel(story.debate.recommendation) : "Rubric applied."));
  } else {
    at(t, (x) => {
      x.c.detail.debate = { prosecutor: [], defender: [], rubric: [], recommendation: null, ran: false };
      finish(x, "cantaritor", "Nothing to weigh.", "skipped", { skipped: true });
    });
  }

  // Recovery
  t += 0.2;
  const noTx = Boolean(ctx?.intake?.noTx);
  at(t - 0.05, (x) => route(x, noTx
    ? { node: "recuperare", run: false, reason: "No payment identified yet." }
    : { node: "recuperare", run: true, reason: story.recovery?.chargeback?.eligible ? "A card payment: check what a chargeback can recover." : story.recovery?.recall ? "A transfer: prepare the recall to the payee's bank." : "Check whether the money can be recovered from the fraudster." }));
  if (noTx) at(t, (x) => finish(x, "recuperare", "No payment identified yet.", "skipped", { skipped: true }));
  else at(t, (x) => start(x, "recuperare", "Preparing the recovery drafts: recall, chargeback and the DNSC report."));
  byStage("recuperare").forEach((f, i) => at(t + 0.5 + i * 0.6, (x) => factStep(x, f)));
  t += 0.5 + byStage("recuperare").length * 0.6;
  story.decisions.filter((d) => d.stage === "recuperare").forEach((d, i) => at(t + i * 0.2, (x) => decisionStep(x, d)));
  t += story.decisions.filter((d) => d.stage === "recuperare").length * 0.2 + 0.2;
  at(t, (x) => {
    x.c.detail.recovery = story.recovery ?? { chargeback: null, recall: null, dnsc_report: null };
    if (noTx) return;
    const cb = story.recovery?.chargeback;
    finish(x, "recuperare", cb?.eligible ? `Chargeback ${cb.reason_code ?? ""} can recover the money.` : story.recovery?.recall ? "Recall draft ready." : "Nothing to recover from the fraudster.");
  });

  // Letter and letter check
  t += 0.2;
  at(t - 0.05, (x) => route(x, story.letter
    ? { node: "redactor", run: true, reason: "The customer gets a written answer to every point." }
    : { node: "redactor", run: false, reason: "A person writes the letter after the decision." }));
  if (story.letter) {
    const letter = story.letter;
    at(t, (x) => start(x, "redactor", "Drafting the reply: every point answered, with citations."));
    byStage("redactor").forEach((f, i) => at(t + 0.8 + i * 0.3, (x) => factStep(x, f)));
    t += 0.8 + byStage("redactor").length * 0.3 + 0.2;
    at(t, (x) => {
      const r = resolveLetter(x, letter.body);
      x.c.detail.letter = { case_id: x.c.caseId, subject: letter.subject, body: r.body, cites: r.cites, points_answered: letter.points, filter: null, status: "draft" };
      ground(x, "letter", letterSources(story));
      finish(x, "redactor", `Answers ${plural(letter.points.length, "point", "points")}, with ${plural(r.cites.length, "citation", "citations")}.`);
    });
    t += 0.2;
    at(t, (x) => start(x, "filtru_zid", "Checking the letter: banned terms, canary tokens, personal data."));
    byStage("filtru_zid").forEach((f, i) => at(t + 0.5 + i * 0.3, (x) => factStep(x, f)));
    t += 0.5 + byStage("filtru_zid").length * 0.3 + 0.2;
    at(t, (x) => {
      if (x.c.detail.letter) {
        x.c.detail.letter.filter = { passed: true, blocked_terms: [], canaries_found: 0, classifier_flag: false, pii_findings: [], reasons: [] };
        x.c.detail.letter.status = "approved";
      }
      numericCheck(x);
      finish(x, "filtru_zid", "Passed: 0 banned terms, 0 canary tokens.");
    });
  } else {
    at(t, (x) => {
      finish(x, "redactor", "A person writes the letter after the decision.", "skipped", { skipped: true });
      finish(x, "filtru_zid", "No letter to check yet.", "skipped", { skipped: true });
    });
  }
  const aEnd = t + 0.3;

  // B1: after a person signs
  B1.push({
    t: 0,
    apply: (x) => {
      const ap = x.c.run?.approval;
      if (!ap) return;
      const dec = x.c.detail.decisions?.find((d) => d.question === "rambursare_t1");
      x.c.detail.interrupt = { pending: false, kind: x.c.detail.interrupt?.kind, options: [] };
      x.c.detail.interrupt.answer = { action: ap.action, approver: ap.approver, note: ap.note };
      x.c.detail.summary.approved_by = ap.approver;
      x.c.detail.summary.approved_at = isoRo(ap.at);
      emit(x, "CUSTOM", { step: "rambursare", name: "interrupt", message: ap.action === "approve" ? `Approved by ${ap.approver}.` : `Rejected by ${ap.approver}.`, data: { pending: false, resolution: ap.action, approver: ap.approver } });
      const isRefund = story.refund === "approval";
      if ((isRefund && ap.action === "approve") || (!isRefund && ap.action === "reject" && story.verdict === "EXCEPTIE_FRAUDA_CLIENT")) {
        refundFact(x, ap.approver);
        if (dec) {
          dec.decided_by = "rules+human";
          dec.requires_human = false;
          if (!isRefund) {
            dec.decision = "RAMBURSEAZA";
            x.c.detail.reasons = [...(x.c.detail.reasons ?? []), { rule_id: "PAY-03", decision: "RAMBURSEAZA", sentence: `${ap.approver} didn't confirm the exception, so the bank refunds by the deadline.` }];
          }
          dec.next_actions = ["Refund issued (simulated instruction)"];
        }
        x.c.detail.summary.status = "RAMBURSAT";
        if (!isRefund) x.c.detail.summary.verdict = "RAMBURSEAZA";
        finish(x, "rambursare", `Refund approved by ${ap.approver}: ${money(x.c.ctx.amount)}.`);
      } else if (isRefund && ap.action === "reject") {
        if (dec) {
          dec.decided_by = "human";
          dec.requires_human = true;
          dec.next_actions = ["Give the reason for the rejection: a refusal needs a suspicion of fraud reported to the authority (DSP-05). The refund deadline still applies."];
        }
        x.c.detail.summary.status = "EXCEPTIE";
        finish(x, "rambursare", `Rejected by ${ap.approver}: the case becomes an exception, and the refund deadline still applies.`, "blocked", { blocked: true });
      } else {
        if (dec) {
          dec.decided_by = "rules+human";
          dec.requires_human = false;
        }
        x.c.detail.summary.status = story.statusFinal;
        finish(x, "rambursare", `${verdictLabel(story.verdict)}: confirmed by ${ap.approver}.`);
      }
      x.c.detail.summary.requires_human = false;
    },
  });

  // B2: the seal, once both lanes are done
  B2.push({ t: 0, apply: (x) => start(x, "sigiliu", "Sealing the case file: an Ed25519-signed Merkle root and a QR code.") });
  B2.push({
    t: 0.9,
    apply: (x) => {
      const s = sealCase(x.c, x.at);
      emit(x, "CUSTOM", { step: "sigiliu", name: "ledger_seal", message: `${plural(s.count, "evidence item", "evidence items")} sealed · root ${s.root.slice(0, 12)}…`, data: { root: s.root, count: s.count, signature: s.signature.slice(0, 32) } });
      finish(x, "sigiliu", `Sealed: ${plural(s.count, "evidence item", "evidence items")}, root ${s.root.slice(0, 10)}…`);
    },
  });
  B2.push({
    t: 1.2,
    apply: (x) => {
      if (x.c.run) x.c.run.done = true;
      emit(x, "RUN_FINISHED", { message: `Case closed in the client zone: ${verdictLabel(x.c.detail.summary.verdict)}.` });
    },
  });

  return { A: A.sort((a, b) => a.t - b.t), B1, B2, aEnd, needsApproval, gate };
}

function refundFact(x: Exec, approver: string) {
  factStep(x, {
    key: "refund",
    stage: "rambursare",
    kind: "refund.instruction",
    tool: "rules.refund_instruction",
    summary: `Refund instruction issued (simulated): ${money(x.c.ctx.amount)}, value date = debit date. Approved by: ${approver}.`,
    content: { amount: x.c.ctx.amount, currency: "RON", idempotency_key: `RF-${x.c.caseId}`, approved_by: approver, simulated: true },
  });
  x.hooks.onRefund?.(x.c, x.at);
}

// ------------------------------------------------------------------ creating and advancing a case

export function newCaseDetail(caseId: string, scenario: string, ctx: StoryCtx, story: Story): CaseDetail {
  return {
    summary: {
      case_id: caseId,
      customer_alias: ctx.alias,
      received_at: isoRo(ctx.receivedAt),
      channel: story.channel,
      scenario: story.scenario === "phishing_link" && scenario === "demo_t1" ? "phishing_link" : story.scenario,
      amount: { value: ctx.amount, currency: "RON" },
      status: "NOU",
      verdict: null,
      deadline: null,
      sla_seconds_left: null,
      requires_human: false,
      scenario_phrase: scenarioPhrase(scenario, ctx),
      approved_by: null,
      approved_at: null,
    },
    complaint: { text: story.complaintText, attachments: story.attachments, received_at: isoRo(ctx.receivedAt) },
    extracted: null,
    classification: null,
    facts: [],
    rules: { case_id: caseId, decisions: [], hits: [], deadlines: [], params_used: { plafon_aprobare_ron: 2000, prag_rubrica_recuperare: 4 }, engine_version: "1" },
    decisions: [],
    debate: null,
    recovery: null,
    letter: null,
    pipeline: {
      nodes: STAGES.map((s) => ({ id: s.id, label: s.label, agent: s.agent, model: s.model === "none" ? null : s.model, status: "idle" })),
      edges: STAGE_EDGES.map((e) => ({ source: e.source, target: e.target })),
    },
    interrupt: { pending: false },
    hold: { received: false },
    ledger: { count: 0, root: null, sealed: false },
    match: null,
    routing: [],
    grounding: [],
    numeric_check: null,
    campaign: null,
    reasons: [],
  };
}

export function storyOf(c: MockCase): Story {
  return storyFor(c.scenario, c.ctx);
}

/**
 * Advances the run up to `now`. Returns true when something changed.
 * Late steps apply at once, in order (for example after the tab running the demo was closed).
 */
export function advance(c: MockCase, now: number, hooks: EngineHooks): boolean {
  const run = c.run;
  if (!run || run.done) return false;
  // "none of these" switches the story to asking the customer; the steps up to the gate are the same in both
  const story = storyOf(c);
  const tl = buildTimeline(story, c.ctx);
  let changed = false;
  const exec = (stepAt: number): Exec => ({ c, story, at: Math.min(now, stepAt), hooks });
  // after a person picks the payment, the rest of the run follows from the moment they picked it
  const gate = tl.gate;
  const shift = () => (gate !== null && run.pick ? run.pick.at - (run.startedAt + gate * 1000) : 0);
  const timeOf = (t: number) => run.startedAt + t * 1000 + (gate !== null && t > gate ? shift() : 0);

  while (run.cursorA < tl.A.length) {
    const s = tl.A[run.cursorA];
    if (gate !== null && s.t > gate && !run.pick) break;
    if (timeOf(s.t) > now) break;
    s.apply(exec(timeOf(s.t)));
    run.cursorA += 1;
    changed = true;
  }
  const aDone = run.cursorA >= tl.A.length;

  if (tl.needsApproval) {
    if (!run.approval) return changed;
    while (run.cursorB1 < tl.B1.length && run.approval.at + tl.B1[run.cursorB1].t * 1000 <= now) {
      const s = tl.B1[run.cursorB1];
      s.apply(exec(run.approval.at + s.t * 1000));
      run.cursorB1 += 1;
      changed = true;
    }
  }
  if (!aDone) return changed;
  const aEndAt = timeOf(tl.aEnd);
  const b2Base = tl.needsApproval && run.approval ? Math.max(run.approval.at + 1200, aEndAt) : aEndAt;
  if (tl.needsApproval && run.cursorB1 < tl.B1.length) return changed;
  while (run.cursorB2 < tl.B2.length && b2Base + tl.B2[run.cursorB2].t * 1000 <= now) {
    const s = tl.B2[run.cursorB2];
    s.apply(exec(b2Base + s.t * 1000));
    run.cursorB2 += 1;
    changed = true;
  }
  return changed;
}

/** For the pre-run cases: runs at once on a fake clock, optionally with an approval. */
export function prerun(c: MockCase, startedAt: number, hooks: EngineHooks, approval: Omit<Approval, "at"> | null, approvalDelayS = 240) {
  c.run = { runId: `run-${c.caseId}-seed`, startedAt, cursorA: 0, cursorB1: 0, cursorB2: 0, approval: null, done: false };
  const tl = buildTimeline(storyOf(c), c.ctx);
  const aEndAt = startedAt + tl.aEnd * 1000;
  advance(c, aEndAt + 10, hooks);
  if (tl.needsApproval && approval) {
    c.run.approval = { ...approval, at: aEndAt + approvalDelayS * 1000 };
    advance(c, aEndAt + approvalDelayS * 1000 + 10_000, hooks);
  } else if (!tl.needsApproval) {
    advance(c, aEndAt + 10_000, hooks);
  }
}
