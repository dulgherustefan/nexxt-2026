/**
 * Motorul simulării: transformă o poveste într-o rulare a grafului Judecătorului, cu evenimente AG-UI
 * (STEP_*, TOOL_CALL_*, TEXT_MESSAGE_*, CUSTOM fact/rule_hit/decision/interrupt/ledger_seal/hold_signal).
 * Aceeași cronologie servește cazurile pre-rulate din inbox (ceas fals) și rulările live (ceas real).
 */
import qrcode from "qrcode-generator";
import { clock, dateLong, disputeLabel, money, scenarioLabel, verdictLabel } from "../api/format";
import type { AgentEvent, CaseDetail, Decision, EventType, Fact, NodeStatus, RuleHit } from "../api/types";
import { STAGES, STAGE_BY_ID, STAGE_EDGES } from "../lib/pipeline";
import { isoRo } from "./calendar";
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

// ------------------------------------------------------------------ utilitare

export const PUBLIC_KEY = `ed25519:${sha256("versoml-demo-ledger-key").slice(0, 64)}`;

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
    agent: fields.agent ?? (step ? STAGE_BY_ID[step]?.agent ?? null : null),
    name: fields.name ?? null,
    message: fields.message ?? null,
    data: fields.data ?? {},
  };
  x.c.events.push(ev);
  return ev;
}

function setNode(x: Exec, id: string, status: NodeStatus, summary?: string) {
  const nodes = x.c.detail.pipeline?.nodes;
  const n = nodes?.find((k) => k.id === id);
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

// ------------------------------------------------------------------ cronologia

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
    emit(x, "RUN_STARTED", { message: "Pornește graful Judecătorului pe zona client." });
  });

  // Receptor
  let t = 0.3;
  at(t, (x) => start(x, "receptor", "Citesc reclamația în LLM-ul izolat, fără tool-uri."));
  byStage("receptor").forEach((f, i) => at(0.8 + i * 0.5, (x) => factStep(x, f)));
  t = 0.8 + byStage("receptor").length * 0.5;
  at(t, (x) => {
    x.c.detail.complaint = { text: x.c.detail.complaint?.text || story.complaintText, attachments: story.attachments, received_at: isoRo(x.c.ctx.receivedAt) };
    x.c.detail.extracted = story.extracted;
    const inj = story.extracted.injection_suspected;
    if (inj) emit(x, "CUSTOM", { step: "receptor", name: "policy_denied", message: "Injecție de prompt în document: tratată ca dată și semnalată.", data: { reason: "injection_suspected" } });
    finish(x, "receptor", inj ? "Câmpuri tipizate; injecția a fost semnalată și ignorată." : "Câmpuri tipizate extrase din textul neîncrezut.");
  });

  // Clasificator
  t += 0.2;
  at(t, (x) => start(x, "clasificator", "M1 calibrat + Haiku: canal, tip, scenariu."));
  byStage("clasificator").forEach((f, i) => at(t + 0.6 + i * 0.4, (x) => factStep(x, f)));
  t += 0.6 + byStage("clasificator").length * 0.4 + 0.2;
  at(t, (x) => {
    x.c.detail.classification = story.classification;
    const p = story.classification.probability ?? 0;
    finish(x, "clasificator", `${disputeLabel(story.classification.dispute_type)} · ${scenarioLabel(story.classification.scenario)} · p = ${p.toFixed(2).replace(".", ",")}`);
  });

  // Ceasornicar
  t += 0.2;
  at(t, (x) => start(x, "ceasornicar", "Calculez termenele cu calendarul RO."));
  story.deadlines.forEach((d, i) =>
    at(t + 0.35 + i * 0.15, (x) => {
      x.c.detail.rules?.deadlines?.push(d);
      if (d.rule_id === "PAY-03" || !x.c.detail.summary.deadline) x.c.detail.summary.deadline = d.due_at;
      emit(x, "CUSTOM", { step: "ceasornicar", name: "rule_hit", message: `${d.rule_id} · ${d.name}: ${dateLong(d.due_at)}, ${clock(d.due_at, false)}`, data: { rule_id: d.rule_id, deadline: d.due_at, name: d.name } });
    }),
  );
  t += 0.35 + story.deadlines.length * 0.15 + 0.2;
  at(t, (x) => finish(x, "ceasornicar", x.c.detail.summary.deadline ? `T+1: ${dateLong(x.c.detail.summary.deadline)}, 23:59` : "Termene calculate."));

  // Colectorii, în paralel
  const collectors = ["colector.tranzactie", "colector.sca", "colector.dispozitiv", "colector.domeniu"];
  const cStart = t + 0.2;
  let collectorsEnd = cStart;
  collectors.forEach((cid, k) => {
    const s0 = cStart + k * 0.08;
    at(s0, (x) => start(x, cid, STAGE_BY_ID[cid]?.hint ?? "Colectez probe."));
    const fs = byStage(cid);
    fs.forEach((f, j) => at(s0 + 0.6 + j * 0.95 + k * 0.22, (x) => factStep(x, f)));
    const end = fs.length ? s0 + 0.6 + (fs.length - 1) * 0.95 + k * 0.22 + 0.45 : s0 + 1.2;
    collectorsEnd = Math.max(collectorsEnd, end);
    at(end, (x) => finish(x, cid, fs.length ? `${fs.length} ${fs.length === 1 ? "probă" : "probe"} în registru.` : "Nimic relevant pentru acest caz."));
  });

  // Motorul de reguli
  t = collectorsEnd + 0.3;
  const rStart = t;
  at(t, (x) => start(x, "reguli", "Evaluez regulile pe fapte, fără text liber."));
  if (story.beneficiary) {
    at(t + 0.25, (x) => {
      emit(x, "TOOL_CALL_START", { step: "reguli", message: "dioda.send_facts", data: { tool: "dioda.send_facts" } });
      x.hooks.onDiode?.(x.c, story, x.at);
      emit(x, "TOOL_CALL_END", {
        step: "reguli",
        message: "DisputeFacts trimis spre zona AML prin diodă (semnat HMAC). Înapoi poate veni doar un HOLD da/nu.",
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
        emit(x, "CUSTOM", { step: "reguli", name: "hold_signal", message: "HOLD primit prin diodă: da. Fără alte detalii.", data: { hold: true } });
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

  // Semnalul spre AML, nod separat ca în graful backend-ului
  t += 0.1;
  at(t, (x) => start(x, "outbox_aml", "Trimit spre AML doar fapte despre atac și beneficiar, fără identitatea victimei."));
  at(t + 0.3, (x) => story.beneficiary
    ? finish(x, "outbox_aml", `Trimis. Victima apare doar ca ${x.c.ctx.victimRef}.`)
    : finish(x, "outbox_aml", "Nu e fraudă cu beneficiar: nimic de trimis.", "skipped"));
  t += 0.3;

  // Rambursare
  t += 0.2;
  const rbStart = t;
  at(t, (x) => start(x, "rambursare", story.refund === "none" ? "Verific dacă T+1 se aplică." : "Pregătesc instrucțiunea de rambursare (simulată)."));
  const needsApproval = story.refund === "approval" || story.refund === "exception";
  if (needsApproval) {
    at(t + 0.4, (x) => {
      const kind = story.refund === "approval" ? "aprobare_rambursare" : story.verdict === "RESPINGE_TARDIV" ? "aprobare_respingere" : "aprobare_exceptie";
      x.c.detail.interrupt = { pending: true, kind, prompt: story.approvalPrompt ?? "Confirmă decizia.", options: ["approve", "reject"] };
      x.c.detail.summary.status = story.statusAfterRules;
      x.c.detail.summary.requires_human = true;
      setNode(x, "rambursare", "waiting", "Așteaptă semnătura unui om.");
      emit(x, "CUSTOM", { step: "rambursare", name: "interrupt", message: story.approvalPrompt ?? "Așteaptă aprobare.", data: { pending: true, kind } });
    });
  } else if (story.refund === "auto") {
    at(t + 0.5, (x) => {
      refundFact(x, "motorul de reguli (sub plafon)");
      x.c.detail.summary.status = story.statusAfterRules;
      x.c.detail.summary.requires_human = false;
      finish(x, "rambursare", `Rambursare automată: ${money(x.c.ctx.amount)}, sub plafon.`);
    });
  } else {
    at(t + 0.4, (x) => {
      x.c.detail.summary.status = story.statusAfterRules;
      x.c.detail.summary.requires_human = story.decisions.some((d) => d.question === "rambursare_t1" && d.requires_human);
      finish(x, "rambursare", `${verdictLabel(story.verdict)}: fără instrucțiune de rambursare.`, "skipped", { skipped: true });
    });
  }

  // Procuror ‖ Avocat (doar pe traseul de recuperare)
  t = rbStart + 0.6;
  let debateEnd = t + 0.4;
  if (story.debate) {
    const runSide = (step: "procuror" | "avocat", lines: Array<{ text: string; cites?: string[] }>, offset: number) => {
      const s0 = t + offset;
      at(s0, (x) => start(x, step, step === "procuror" ? "Caut probe pentru neglijență gravă." : "Caut probe în favoarea clientului."));
      let cur = s0 + 0.4;
      lines.forEach((line, i) => {
        const mid = `${step}-${i}`;
        at(cur, (x) => emit(x, "TEXT_MESSAGE_START", { step, data: { message_id: mid, role: step } }));
        chunks(line.text).forEach((ch, j) => at(cur + 0.25 + j * 0.25, (x) => emit(x, "TEXT_MESSAGE_CONTENT", { step, message: ch, data: { message_id: mid, delta: ch } })));
        cur += 0.25 + 3 * 0.25 + 0.1;
        at(cur, (x) => emit(x, "TEXT_MESSAGE_END", { step, data: { message_id: mid, cites: cite(x, line.cites) } }));
        cur += 0.2;
      });
      at(cur, (x) => finish(x, step, `${lines.length} ${lines.length === 1 ? "argument" : "argumente"}, fiecare cu citări.`));
      return cur;
    };
    const e1 = runSide("procuror", story.debate.prosecutor, 0);
    const e2 = runSide("avocat", story.debate.defender, 0.15);
    debateEnd = Math.max(e1, e2);
  } else {
    at(t, (x) => {
      finish(x, "procuror", "Nu se dezbate: nu există traseu de recuperare de la client.", "skipped", { skipped: true });
      finish(x, "avocat", "Nu se dezbate.", "skipped", { skipped: true });
    });
  }

  // Cântăritor
  t = debateEnd + 0.2;
  const cantDecisions = story.decisions.filter((d) => d.stage === "cantaritor");
  if (story.debate || cantDecisions.length) {
    at(t, (x) => start(x, "cantaritor", "Cântăresc argumentele cu rubrica deterministă."));
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
    at(t, (x) => finish(x, "cantaritor", story.debate ? verdictLabel(story.debate.recommendation) : "Rubrică aplicată."));
  } else {
    at(t, (x) => {
      x.c.detail.debate = { prosecutor: [], defender: [], rubric: [], recommendation: null, ran: false };
      finish(x, "cantaritor", "Nimic de cântărit.", "skipped", { skipped: true });
    });
  }

  // Recuperare
  t += 0.2;
  at(t, (x) => start(x, "recuperare", "Rechemare, chargeback, raport DNSC: doar ciorne."));
  byStage("recuperare").forEach((f, i) => at(t + 0.5 + i * 0.6, (x) => factStep(x, f)));
  t += 0.5 + byStage("recuperare").length * 0.6;
  story.decisions.filter((d) => d.stage === "recuperare").forEach((d, i) => at(t + i * 0.2, (x) => decisionStep(x, d)));
  t += story.decisions.filter((d) => d.stage === "recuperare").length * 0.2 + 0.2;
  at(t, (x) => {
    x.c.detail.recovery = story.recovery ?? { chargeback: null, recall: null, dnsc_report: null };
    const cb = story.recovery?.chargeback;
    finish(x, "recuperare", cb?.eligible ? `Chargeback ${cb.reason_code ?? ""} recuperabil.` : story.recovery?.recall ? "Ciornă de rechemare pregătită." : "Nimic de recuperat de la escroc.");
  });

  // Redactor + filtru
  t += 0.2;
  if (story.letter) {
    const letter = story.letter;
    at(t, (x) => start(x, "redactor", "Scriu răspunsul la fiecare punct, cu citări."));
    byStage("redactor").forEach((f, i) => at(t + 0.8 + i * 0.3, (x) => factStep(x, f)));
    t += 0.8 + byStage("redactor").length * 0.3 + 0.2;
    at(t, (x) => {
      const r = resolveLetter(x, letter.body);
      x.c.detail.letter = { case_id: x.c.caseId, subject: letter.subject, body: r.body, cites: r.cites, points_answered: letter.points, filter: null, status: "draft" };
      finish(x, "redactor", `Răspunde la ${letter.points.length} puncte, ${r.cites.length} citări.`);
    });
    t += 0.2;
    at(t, (x) => start(x, "filtru_zid", "Termeni interziși, canary, PII."));
    byStage("filtru_zid").forEach((f, i) => at(t + 0.5 + i * 0.3, (x) => factStep(x, f)));
    t += 0.5 + byStage("filtru_zid").length * 0.3 + 0.2;
    at(t, (x) => {
      if (x.c.detail.letter) {
        x.c.detail.letter.filter = { passed: true, blocked_terms: [], canaries_found: 0, classifier_flag: false, pii_findings: [], reasons: [] };
        x.c.detail.letter.status = "approved";
      }
      finish(x, "filtru_zid", "Trecut: 0 termeni interziși, 0 canary.");
    });
  } else {
    at(t, (x) => {
      finish(x, "redactor", "Scrisoarea o redactează omul, după decizie.", "skipped", { skipped: true });
      finish(x, "filtru_zid", "Nicio scrisoare de verificat încă.", "skipped", { skipped: true });
    });
  }
  const aEnd = t + 0.3;

  // B1: după semnătura omului
  B1.push({
    t: 0,
    apply: (x) => {
      const ap = x.c.run?.approval;
      if (!ap) return;
      const dec = x.c.detail.decisions?.find((d) => d.question === "rambursare_t1");
      x.c.detail.interrupt = { pending: false, kind: x.c.detail.interrupt?.kind, options: [] };
      emit(x, "CUSTOM", { step: "rambursare", name: "interrupt", message: ap.action === "approve" ? `Aprobat de ${ap.approver}.` : `Respins de ${ap.approver}.`, data: { pending: false, resolution: ap.action, approver: ap.approver } });
      const isRefund = story.refund === "approval";
      if ((isRefund && ap.action === "approve") || (!isRefund && ap.action === "reject" && story.verdict === "EXCEPTIE_FRAUDA_CLIENT")) {
        refundFact(x, ap.approver);
        if (dec) {
          dec.decided_by = "rules+human";
          dec.requires_human = false;
          if (!isRefund) dec.decision = "RAMBURSEAZA";
          dec.next_actions = ["Rambursare emisă (instrucțiune simulată)"];
        }
        x.c.detail.summary.status = "RAMBURSAT";
        if (!isRefund) x.c.detail.summary.verdict = "RAMBURSEAZA";
        finish(x, "rambursare", `Rambursare aprobată de ${ap.approver}: ${money(x.c.ctx.amount)}.`);
      } else if (isRefund && ap.action === "reject") {
        if (dec) {
          dec.decided_by = "human";
          dec.requires_human = true;
          dec.next_actions = ["Motivează respingerea: refuzul cere suspiciune de fraudă comunicată autorității (DSP-05). Termenul T+1 rămâne."];
        }
        x.c.detail.summary.status = "EXCEPTIE";
        finish(x, "rambursare", `Respinsă de ${ap.approver}: cazul devine excepție, termenul T+1 rămâne.`, "blocked", { blocked: true });
      } else {
        if (dec) {
          dec.decided_by = "rules+human";
          dec.requires_human = false;
        }
        x.c.detail.summary.status = story.statusFinal;
        finish(x, "rambursare", `${verdictLabel(story.verdict)}: confirmat de ${ap.approver}.`);
      }
      x.c.detail.summary.requires_human = false;
    },
  });

  // B2: sigiliul, după ce ambele benzi s-au încheiat
  B2.push({ t: 0, apply: (x) => start(x, "sigiliu", "Calculez rădăcina Merkle și semnez.") });
  B2.push({
    t: 0.9,
    apply: (x) => {
      const s = sealCase(x.c, x.at);
      emit(x, "CUSTOM", { step: "sigiliu", name: "ledger_seal", message: `${s.count} probe sigilate · rădăcina ${s.root.slice(0, 12)}…`, data: { root: s.root, count: s.count, signature: s.signature.slice(0, 32) } });
      finish(x, "sigiliu", `${s.count} probe, rădăcina ${s.root.slice(0, 10)}…`);
    },
  });
  B2.push({
    t: 1.2,
    apply: (x) => {
      if (x.c.run) x.c.run.done = true;
      emit(x, "RUN_FINISHED", { message: `Caz închis pe zona client: ${verdictLabel(x.c.detail.summary.verdict)}.` });
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
    summary: `Instrucțiune de rambursare emisă (simulat): ${money(x.c.ctx.amount)}, data valutei = data debitării. Aprobat de: ${approver}.`,
    content: { amount: x.c.ctx.amount, currency: "RON", idempotency_key: `RF-${x.c.caseId}`, approved_by: approver, simulated: true },
  });
  x.hooks.onRefund?.(x.c, x.at);
}

// ------------------------------------------------------------------ crearea și avansarea unui caz

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
 * Avansează rularea până la momentul `now`. Întoarce true dacă s-a schimbat ceva.
 * Pașii întârziați se aplică imediat, în ordine (de exemplu după ce s-a închis fila care rula demo-ul).
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

/** Pentru cazurile pre-rulate: rulează instant pe un ceas fals, opțional cu o aprobare. */
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
