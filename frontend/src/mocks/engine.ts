/**
 * The simulation engine: turns a story into a run of the case graph, with AG-UI events
 * (STEP_*, TOOL_CALL_*, TEXT_MESSAGE_*, CUSTOM fact/rule_hit/decision/interrupt/ledger_seal/hold_signal).
 * The same timeline serves the pre-run inbox cases (on a fake clock) and live runs (on the real clock).
 */
import qrcode from "qrcode-generator";
import { disputeLabel, money, scenarioLabel, verdictLabel } from "../api/format";
import type { AgentEvent, CaseDetail, Decision, EventType, Fact, NodeStatus, RuleHit } from "../api/types";
import { matchNode, STAGES, STAGE_BY_ID, STAGE_EDGES, type StageSpec } from "../lib/pipeline";
import { fmtDay, fmtDayTime, isoRo } from "./calendar";
import { canonical, merkleRoot, sha256 } from "./sha256";
import { storyFor, type DecisionSeed, type FactSeed, type Story, type StoryCtx } from "./stories";

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

// ------------------------------------------------------------------ the timeline

export function buildTimeline(story: Story): Timeline {
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
    x.c.detail.complaint = { text: x.c.detail.complaint?.text || story.complaintText, attachments: story.attachments, received_at: isoRo(x.c.ctx.receivedAt) };
    x.c.detail.extracted = story.extracted;
    const inj = story.extracted.injection_suspected;
    if (inj) emit(x, "CUSTOM", { step: "receptor", name: "policy_denied", message: "Prompt injection in the document: treated as data and flagged.", data: { reason: "injection_suspected" } });
    finish(x, "receptor", inj ? "Typed fields extracted; the injection was flagged and ignored." : "Typed fields extracted from the untrusted text.");
  });

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

  // The collectors, in parallel
  const collectors = ["colector.tranzactie", "colector.sca", "colector.dispozitiv", "colector.domeniu"];
  const cStart = t + 0.2;
  let collectorsEnd = cStart;
  collectors.forEach((cid, k) => {
    const s0 = cStart + k * 0.08;
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
  at(t, (x) => start(x, "recuperare", "Preparing the recovery drafts: recall, chargeback and the DNSC report."));
  byStage("recuperare").forEach((f, i) => at(t + 0.5 + i * 0.6, (x) => factStep(x, f)));
  t += 0.5 + byStage("recuperare").length * 0.6;
  story.decisions.filter((d) => d.stage === "recuperare").forEach((d, i) => at(t + i * 0.2, (x) => decisionStep(x, d)));
  t += story.decisions.filter((d) => d.stage === "recuperare").length * 0.2 + 0.2;
  at(t, (x) => {
    x.c.detail.recovery = story.recovery ?? { chargeback: null, recall: null, dnsc_report: null };
    const cb = story.recovery?.chargeback;
    finish(x, "recuperare", cb?.eligible ? `Chargeback ${cb.reason_code ?? ""} can recover the money.` : story.recovery?.recall ? "Recall draft ready." : "Nothing to recover from the fraudster.");
  });

  // Letter and letter check
  t += 0.2;
  if (story.letter) {
    const letter = story.letter;
    at(t, (x) => start(x, "redactor", "Drafting the reply: every point answered, with citations."));
    byStage("redactor").forEach((f, i) => at(t + 0.8 + i * 0.3, (x) => factStep(x, f)));
    t += 0.8 + byStage("redactor").length * 0.3 + 0.2;
    at(t, (x) => {
      const r = resolveLetter(x, letter.body);
      x.c.detail.letter = { case_id: x.c.caseId, subject: letter.subject, body: r.body, cites: r.cites, points_answered: letter.points, filter: null, status: "draft" };
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
      emit(x, "CUSTOM", { step: "rambursare", name: "interrupt", message: ap.action === "approve" ? `Approved by ${ap.approver}.` : `Rejected by ${ap.approver}.`, data: { pending: false, resolution: ap.action, approver: ap.approver } });
      const isRefund = story.refund === "approval";
      if ((isRefund && ap.action === "approve") || (!isRefund && ap.action === "reject" && story.verdict === "EXCEPTIE_FRAUDA_CLIENT")) {
        refundFact(x, ap.approver);
        if (dec) {
          dec.decided_by = "rules+human";
          dec.requires_human = false;
          if (!isRefund) dec.decision = "RAMBURSEAZA";
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

  return { A: A.sort((a, b) => a.t - b.t), B1, B2, aEnd, needsApproval };
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
  const story = storyOf(c);
  const tl = buildTimeline(story);
  let changed = false;
  const exec = (stepAt: number): Exec => ({ c, story, at: Math.min(now, stepAt), hooks });

  while (run.cursorA < tl.A.length && run.startedAt + tl.A[run.cursorA].t * 1000 <= now) {
    const s = tl.A[run.cursorA];
    s.apply(exec(run.startedAt + s.t * 1000));
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
  const b2Base = tl.needsApproval && run.approval ? Math.max(run.approval.at + 1200, run.startedAt + tl.aEnd * 1000) : run.startedAt + tl.aEnd * 1000;
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
  const tl = buildTimeline(storyOf(c));
  const aEndAt = startedAt + tl.aEnd * 1000;
  advance(c, aEndAt + 10, hooks);
  if (tl.needsApproval && approval) {
    c.run.approval = { ...approval, at: aEndAt + approvalDelayS * 1000 };
    advance(c, aEndAt + approvalDelayS * 1000 + 10_000, hooks);
  } else if (!tl.needsApproval) {
    advance(c, aEndAt + 10_000, hooks);
  }
}
