/**
 * Zona AML în modul mock: o pistă despre contul-cărăuș în care au plătit victimele,
 * graful banilor, OSINT, Avocatul nevinovăției, ciorna RTS și ceasurile din Legea 129/2019.
 * Totul e sintetic: bănci fictive (XBNK, YBNK), domenii `.example`, pseudonime VCT-xxxx.
 */
import { money } from "../api/format";
import type {
  AgentEvent,
  AmlLead,
  Campaign,
  Deadline,
  EventType,
  GraphEdge,
  GraphNode,
  LeadDetail,
  OsintFinding,
  OsintKind,
  OsintResult,
  PolicyDecision,
  RationaleLine,
  Referral,
} from "../api/types";
import { isoRo } from "./calendar";
import { MULE_IBAN_SHORT, SCAM_DOMAIN } from "./stories";

export const LEAD_ID = "PST-2026-0007";
export const LEAD2_ID = "PST-2026-0006";
const MULE = "acc-7731";
const MULE2 = "acc-0918";
const EXCHANGE = "exc-01";

export interface AmlRun {
  runId: string;
  startedAt: number;
  cursor: number;
  done: boolean;
  decided: string | null;
}

export interface LeadState {
  detail: LeadDetail;
  status: string;
  updated_at: string;
  events: AgentEvent[];
  run: AmlRun | null;
}

export interface AmlDb {
  leads: Record<string, LeadState>;
  order: string[];
  referrals: Referral[];
  campaigns: Campaign[];
  wall: PolicyDecision[];
  axCounter: number;
}

const H = 3600_000;

function node(id: string, label: string, kind: string, score: number | null, community: number | null, flagged = false): GraphNode {
  return { id, label, kind, score, community, amount_in: 0, amount_out: 0, flagged };
}

function edge(id: string, source: string, target: string, amount: number, ts: number, case_id: string | null, kind = "transfer"): GraphEdge {
  return { id, source, target, amount, ts: isoRo(ts), case_id, kind };
}

export function recomputeAmounts(g: { nodes: GraphNode[]; edges: GraphEdge[] }) {
  for (const n of g.nodes) {
    n.amount_in = 0;
    n.amount_out = 0;
  }
  const byId = new Map(g.nodes.map((n) => [n.id, n]));
  for (const e of g.edges) {
    const s = byId.get(e.source);
    const t = byId.get(e.target);
    if (s) s.amount_out += e.amount;
    if (t) t.amount_in += e.amount;
  }
}

const ax = (n: number) => `AX-${String(n).padStart(3, "0")}`;

function osintSeed(): OsintFinding[] {
  return [
    { tool: "rdap_domain", target: SCAM_DOMAIN, ok: true, summary: "Înregistrat azi la 08:14, acum circa 6 ore. Date de contact ascunse.", signal: "rosu", fact_id: ax(4), source_url: "https://rdap.example/domain/" + SCAM_DOMAIN, mode: "fixture" },
    { tool: "ct_certificates", target: SCAM_DOMAIN, ok: true, summary: "Primul certificat emis azi la 08:20. Niciun istoric anterior.", signal: "rosu", fact_id: ax(5), source_url: null, mode: "fixture" },
    { tool: "lookalike_score", target: SCAM_DOMAIN, ok: true, summary: "Scor de sosie 0,93 față de bancademo.example (M3).", signal: "rosu", fact_id: ax(6), source_url: null, mode: "fixture" },
    { tool: "openphish_check", target: SCAM_DOMAIN, ok: true, summary: "Nu apare încă în feedul OpenPhish (actualizat la 6 ore).", signal: "galben", fact_id: ax(7), source_url: null, mode: "fixture" },
    { tool: "anaf_company", target: "CUI 4021837", ok: true, summary: "CUI-ul din detaliile plății nu trece cifra de control: firma nu există în registrul sintetic.", signal: "rosu", fact_id: ax(8), source_url: null, mode: "fixture" },
    { tool: "sanctions_screen", target: "titular T-7731", ok: true, summary: "Nicio potrivire în lista locală de sancțiuni (copie de demo).", signal: "verde", fact_id: ax(9), source_url: null, mode: "fixture" },
    { tool: "phone_intel", target: "+40 7•• ••• 214", ok: true, summary: "Numărul din SMS apare în 2 reclamații legate de același IBAN.", signal: "galben", fact_id: ax(10), source_url: null, mode: "fixture" },
    { tool: "validate_iban", target: MULE_IBAN_SHORT, ok: true, summary: "IBAN valid sintactic; banca XBNK e fictivă (nu există la BNR).", signal: "neutru", fact_id: ax(11), source_url: null, mode: "fixture" },
  ];
}

function innocentSeed(): RationaleLine[] {
  return [
    { text: "Cărăuș recrutat, posibil și el victimă: contul are 41 de zile și a primit salariu până luna trecută; tiparul seamănă cu recrutarea prin „job de acasă”.", cites: [ax(2), ax(12)] },
    { text: "Magazin online nou, legitim: puțin probabil. CUI-ul nu trece verificarea, iar contul nu are încasări de la clienți obișnuiți.", cites: [ax(8), ax(13)] },
    { text: "Cont comun sau de familie: exclus de date. Plățile vin de la victime fără legătură între ele, în mai puțin de o zi.", cites: [ax(1), ax(3)] },
  ];
}

function rtsSeed(detail: LeadDetail): LeadDetail["rts"] {
  const mule = detail.graph.nodes.find((n) => n.id === MULE);
  const victims = detail.graph.nodes.filter((n) => n.kind === "victima").length;
  return {
    status: "ciornă",
    fields: {
      "Entitate raportoare": "Banca Demo (fictivă)",
      "Tip raport": "RTS, art. 6 din Legea 129/2019",
      "Cont în cauză": `${MULE_IBAN_SHORT} (titular: pseudonim T-7731)`,
      "Sumă intrată": money(mule?.amount_in ?? 0),
      "Victime legate": String(victims),
      Tipologii: "fan-in, tranzit rapid, ieșiri spre exchange",
      "Tranzacție reținută": "3.100 lei spre Schimb Cripto Demo, reținută 24 h (AML-03)",
      "Scor M5 (doar suport)": "0,94",
    },
    narrative: [
      { text: `Contul ${MULE_IBAN_SHORT} a primit, în mai puțin de o zi, plăți de la ${victims} victime fără legătură între ele, după pagini false de livrare.`, cites: [ax(1), ax(2), ax(3)] },
      { text: "Banii au plecat în mai puțin de 24 de ore spre un exchange crypto și spre un al doilea cont, care a retras numerar.", cites: [ax(12), ax(14)] },
      { text: "Domeniul folosit în atac a fost înregistrat cu 6 ore înainte și imită pagina Banca Demo (scor 0,93).", cites: [ax(4), ax(6)] },
      { text: "Avocatul nevinovăției nu a găsit o explicație legitimă; ipoteza „cărăuș recrutat” rămâne deschisă și e trecută în raport.", cites: [ax(13)] },
    ],
  };
}

function clocksSeed(now: number): Deadline[] {
  return [
    { rule_id: "AML-03", name: "Reținere 24 h după înregistrarea RTS", due_at: isoRo(now + 24 * H), basis: "Legea 129/2019 art. 8 alin. (3)", business_days: false },
    { rule_id: "AML-04", name: "Suspendare ONPCSB: până la 48 h", due_at: isoRo(now + 72 * H), basis: "Legea 129/2019 art. 8 alin. (4)", business_days: false },
    { rule_id: "AML-04", name: "Prelungire o singură dată: până la 72 h", due_at: isoRo(now + 144 * H), basis: "Legea 129/2019 art. 8 alin. (6)", business_days: false },
  ];
}

export function seedAml(now: number): AmlDb {
  const nodes: GraphNode[] = [
    node("vct-0d77", "VCT-0d77", "victima", null, 1),
    node("vct-a9e4", "VCT-a9e4", "victima", null, 1),
    node(MULE, MULE_IBAN_SHORT, "carausi", 0.94, 1, true),
    node(MULE2, "RO12 YBNK •••• 0918", "cont", 0.71, 1, true),
    node(EXCHANGE, "Schimb Cripto Demo", "exchange", 0.35, 2),
    node("cash-01", "Numerar ATM", "numerar", null, 1),
    node("shop-01", "Electro Demo SRL", "comerciant", 0.08, 3),
  ];
  const edges: GraphEdge[] = [
    edge("e1", "vct-0d77", MULE2, 990, now - 50 * H, "CT-2026-000087"),
    edge("e2", "vct-a9e4", MULE, 2400, now - 20 * H, "CT-2026-000098"),
    edge("e3", MULE, MULE2, 2300, now - 19.2 * H, null),
    edge("e4", MULE2, "cash-01", 500, now - 18 * H, null, "numerar"),
    edge("e5", MULE2, EXCHANGE, 2700, now - 17.5 * H, null, "crypto"),
    edge("e6", MULE, "shop-01", 90, now - 30 * H, null, "card"),
  ];
  const graph = { nodes, edges };
  recomputeAmounts(graph);
  const lead: AmlLead = {
    lead_id: LEAD_ID,
    case_ids: ["CT-2026-000087", "CT-2026-000098"],
    accounts: [
      {
        account: MULE_IBAN_SHORT,
        score: 0.94,
        label: "carausi_probabil",
        top_features: [
          ["tranzit sub 24 h", 0.31],
          ["victime distincte (fan-in)", 0.27],
          ["ieșiri spre exchange crypto", 0.19],
          ["cont deschis acum 41 de zile", 0.12],
          ["sold mediu sub 50 lei", 0.05],
        ],
        community: 1,
      },
      {
        account: "RO12 YBNK •••• 0918",
        score: 0.71,
        label: "de_verificat",
        top_features: [
          ["primește din contul semnalat", 0.29],
          ["retrageri de numerar", 0.18],
          ["tranzit sub 24 h", 0.14],
        ],
        community: 1,
      },
      { account: "Schimb Cripto Demo", score: 0.35, label: "de_verificat", top_features: [["primește din 2 conturi semnalate", 0.21]], community: 2 },
    ],
    typologies: ["fan-in", "tranzit rapid", "fan-out"],
    osint: [],
    innocent_hypotheses: [],
    recommendation: "RTS_PROPUS",
    rts_draft_id: "RTS-DRAFT-0007",
    canary: "versoml-cn-5d1e9b2a",
  };
  const detail: LeadDetail = { lead, graph, osint: osintSeed(), innocent: innocentSeed(), rts: null, clocks: clocksSeed(now), timeline: [] };
  detail.lead.osint = detail.osint;
  detail.lead.innocent_hypotheses = detail.innocent;
  detail.rts = rtsSeed(detail);

  const g2nodes = [node("vct-5c10", "VCT-5c10", "victima", null, 4), node("acc-4410", "RO77 YBNK •••• 4410", "cont", 0.58, 4, true), node("exc-02", "Schimb Cripto Demo", "exchange", 0.35, 2)];
  const g2edges = [edge("f1", "vct-5c10", "acc-4410", 1200, now - 70 * H, "CT-2026-000071"), edge("f2", "acc-4410", "exc-02", 1150, now - 66 * H, null, "crypto")];
  const g2 = { nodes: g2nodes, edges: g2edges };
  recomputeAmounts(g2);
  const lead2: LeadDetail = {
    lead: {
      lead_id: LEAD2_ID,
      case_ids: ["CT-2026-000071"],
      accounts: [{ account: "RO77 YBNK •••• 4410", score: 0.58, label: "de_verificat", top_features: [["ieșiri spre exchange", 0.22], ["cont nou", 0.11]], community: 4 }],
      typologies: ["fan-out"],
      osint: [],
      innocent_hypotheses: [{ text: "Investitor începător în crypto: o singură intrare, o singură ieșire, nimic din tiparul unui inel.", cites: [] }],
      recommendation: "MONITORIZARE",
      rts_draft_id: null,
      canary: "versoml-cn-8a0c41f7",
    },
    graph: g2,
    osint: [],
    innocent: [{ text: "Investitor începător în crypto: o singură intrare, o singură ieșire, nimic din tiparul unui inel.", cites: [] }],
    rts: null,
    clocks: [],
    timeline: [],
  };

  return {
    leads: {
      [LEAD_ID]: { detail, status: "în lucru", updated_at: isoRo(now - 19 * H), events: [], run: null },
      [LEAD2_ID]: { detail: lead2, status: "monitorizare", updated_at: isoRo(now - 60 * H), events: [], run: null },
    },
    order: [LEAD_ID, LEAD2_ID],
    referrals: [
      { case_id: "CT-2026-000098", received_at: isoRo(now - 19.6 * H), amount: { value: 2400, currency: "RON" }, beneficiary_iban_masked: MULE_IBAN_SHORT, scenario: "phishing_link", lead_id: LEAD_ID },
      { case_id: "CT-2026-000087", received_at: isoRo(now - 49 * H), amount: { value: 990, currency: "RON" }, beneficiary_iban_masked: "RO12 YBNK •••• 0918", scenario: "phishing_link", lead_id: LEAD_ID },
      { case_id: "CT-2026-000071", received_at: isoRo(now - 69 * H), amount: { value: 1200, currency: "RON" }, beneficiary_iban_masked: "RO77 YBNK •••• 4410", scenario: "cont_sigur", lead_id: LEAD2_ID },
    ],
    campaigns: [
      {
        campaign_id: "CMP-LIVRARE-01",
        cases: ["CT-2026-000087", "CT-2026-000098"],
        shared: { domains: [SCAM_DOMAIN, "plata-curierdemo.example"], ibans: [MULE_IBAN_SHORT, "RO12 YBNK •••• 0918"], phones: ["+40 7•• ••• 214"] },
        amount_total: { value: 3390, currency: "RON" },
      },
    ],
    wall: [
      { allowed: false, principal: "Investigatorul/OSINT", action: "client.bank_core.get_customer", resource: "zone:client", reason: "zona AML nu citește datele victimei: primește doar DisputeFacts", policy_ids: ["zone-isolation"], at: isoRo(now - 2 * H) },
      { allowed: true, principal: "Investigatorul/Graf", action: "aml.graph.neighborhood", resource: "zone:aml", reason: "tool din zona proprie, doar citire", policy_ids: ["aml-read"], at: isoRo(now - 2 * H) },
      { allowed: false, principal: "Investigatorul/RTS", action: "str.submit", resource: "onpcsb", reason: "agentul nu depune nimic: doar analistul (om)", policy_ids: ["human-files-rts"], at: isoRo(now - 3 * H) },
    ],
    axCounter: 14,
  };
}

/** Un caz nou din zona client a trecut dioda: victima intră în graf, iar cărăușul mută banii în câteva minute. */
export function ingestReferral(aml: AmlDb, args: { caseId: string; victimRef: string; amount: number; executedAt: number; at: number; scenario: string }, nextSeq: () => number) {
  const st = aml.leads[LEAD_ID];
  if (!st) return;
  if (aml.referrals.some((r) => r.case_id === args.caseId)) return;
  const g = st.detail.graph;
  const vid = `vct-${args.victimRef.slice(4).toLowerCase()}`;
  if (!g.nodes.some((n) => n.id === vid)) g.nodes.push(node(vid, args.victimRef, "victima", null, 1));
  const n = g.edges.length + 1;
  g.edges.push(edge(`e${n}`, vid, MULE, args.amount, args.executedAt, args.caseId));
  g.edges.push(edge(`e${n + 1}`, MULE, EXCHANGE, Math.round(args.amount * 0.97), args.executedAt + 4 * 60_000, null, "crypto"));
  recomputeAmounts(g);
  st.detail.lead.case_ids = Array.from(new Set([...st.detail.lead.case_ids, args.caseId]));
  st.updated_at = isoRo(args.at);
  if (st.detail.rts) st.detail.rts = rtsSeed(st.detail);
  aml.referrals.unshift({
    case_id: args.caseId,
    received_at: isoRo(args.at),
    amount: { value: args.amount, currency: "RON" },
    beneficiary_iban_masked: MULE_IBAN_SHORT,
    scenario: args.scenario,
    lead_id: LEAD_ID,
  });
  const camp = aml.campaigns[0];
  if (camp && Array.isArray(camp.cases)) {
    camp.cases = Array.from(new Set([...camp.cases, args.caseId]));
    const total = typeof camp.amount_total === "number" ? camp.amount_total : camp.amount_total.value;
    camp.amount_total = { value: total + args.amount, currency: "RON" };
  }
  aml.axCounter += 1;
  pushLeadEvent(aml, LEAD_ID, nextSeq, args.at, "CUSTOM", {
    step: "receptor_fapte",
    agent: "Investigatorul/Receptor fapte",
    name: "fact",
    message: `${ax(aml.axCounter)} · DisputeFacts ${args.caseId}: ${money(args.amount)} spre ${MULE_IBAN_SHORT}. Victima intră în graf ca ${args.victimRef}.`,
    data: { fact_id: ax(aml.axCounter), case_id: args.caseId, node: vid, graph_update: true },
  });
}

export function pushLeadEvent(
  aml: AmlDb,
  leadId: string,
  nextSeq: () => number,
  at: number,
  type: EventType,
  fields: Partial<AgentEvent> = {},
): AgentEvent | null {
  const st = aml.leads[leadId];
  if (!st) return null;
  const ev: AgentEvent = {
    type,
    zone: "aml",
    run_id: st.run?.runId ?? "run-aml-0",
    case_id: leadId,
    seq: nextSeq(),
    ts: isoRo(at),
    step: fields.step ?? null,
    agent: fields.agent ?? null,
    name: fields.name ?? null,
    message: fields.message ?? null,
    data: fields.data ?? {},
  };
  st.events.push(ev);
  st.detail.timeline = st.events.slice(-80);
  return ev;
}

// ------------------------------------------------------------------ rularea Investigatorului

export const AML_STAGES = [
  { id: "receptor_fapte", label: "Receptor fapte", agent: "Investigatorul/Receptor fapte", model: "none" },
  { id: "osint", label: "OSINT entități", agent: "Investigatorul/OSINT", model: "sonnet" },
  { id: "graf_ml", label: "Graf + ML", agent: "Investigatorul/Graf", model: "none" },
  { id: "avocat_nevinovatie", label: "Avocatul nevinovăției", agent: "Investigatorul/Avocatul nevinovăției", model: "opus" },
  { id: "redactor_rts", label: "Redactor RTS", agent: "Investigatorul/Redactor RTS", model: "opus" },
  { id: "analist", label: "Analist (om)", agent: "Analist AML", model: "none" },
] as const;

interface AmlStep {
  t: number;
  apply: (aml: AmlDb, st: LeadState, at: number, nextSeq: () => number) => void;
}

function stepEvent(type: EventType, step: string, message: string, extra: Partial<AgentEvent> = {}): AmlStep["apply"] {
  return (aml, st, at, nextSeq) => {
    const agent = AML_STAGES.find((s) => s.id === step)?.agent ?? null;
    pushLeadEvent(aml, st.detail.lead.lead_id, nextSeq, at, type, { step, agent, message, ...extra });
  };
}

export function amlTimeline(): AmlStep[] {
  const steps: AmlStep[] = [];
  const at = (t: number, apply: AmlStep["apply"]) => steps.push({ t, apply });
  const osint = osintSeed();
  at(0, (aml, st, t, nextSeq) => {
    st.detail.osint = [];
    st.detail.innocent = [];
    st.detail.lead.osint = [];
    st.detail.lead.innocent_hypotheses = [];
    st.status = "în lucru";
    pushLeadEvent(aml, st.detail.lead.lead_id, nextSeq, t, "RUN_STARTED", { message: "Pornește graful Investigatorului pe zona AML." });
  });
  at(0.3, stepEvent("STEP_STARTED", "receptor_fapte", "Citesc DisputeFacts din outbox; verific semnătura HMAC."));
  at(1.1, stepEvent("CUSTOM", "receptor_fapte", "AX-001 · DisputeFacts verificate: semnătură validă, fără date de identificare ale victimelor.", { name: "fact", data: { fact_id: "AX-001" } }));
  at(1.5, stepEvent("STEP_FINISHED", "receptor_fapte", "Faptele despre atac și beneficiar sunt în registrul AML."));
  at(1.7, stepEvent("STEP_STARTED", "osint", "Interoghez surse publice doar cu identificatori publici ai beneficiarului."));
  osint.forEach((f, i) => {
    at(2.0 + i * 0.5, stepEvent("TOOL_CALL_START", "osint", f.tool, { data: { tool: f.tool, target: f.target } }));
    at(2.4 + i * 0.5, (aml, st, t, nextSeq) => {
      st.detail.osint.push(f);
      st.detail.lead.osint = st.detail.osint;
      pushLeadEvent(aml, st.detail.lead.lead_id, nextSeq, t, "CUSTOM", {
        step: "osint",
        agent: "Investigatorul/OSINT",
        name: "fact",
        message: `${f.fact_id} · ${f.tool}: ${f.summary}`,
        data: { fact_id: f.fact_id, signal: f.signal, tool: f.tool },
      });
    });
  });
  const osEnd = 2.4 + osint.length * 0.5;
  at(osEnd, stepEvent("STEP_FINISHED", "osint", `${osint.length} verificări, ${osint.filter((f) => f.signal === "rosu").length} semnale roșii.`));
  at(osEnd + 0.2, stepEvent("STEP_STARTED", "graf_ml", "Leg cazurile, caut comunitățile, calculez scorul M5."));
  at(osEnd + 0.7, stepEvent("TOOL_CALL_START", "graf_ml", "graph.link_cases", { data: { tool: "graph.link_cases" } }));
  at(osEnd + 1.4, (aml, st, t, nextSeq) => {
    const victims = st.detail.graph.nodes.filter((n) => n.kind === "victima").length;
    pushLeadEvent(aml, st.detail.lead.lead_id, nextSeq, t, "CUSTOM", { step: "graf_ml", agent: "Investigatorul/Graf", name: "fact", message: `AX-012 · ${victims} victime legate prin același IBAN; tranzit median 31 de minute.`, data: { fact_id: "AX-012", graph_update: true } });
  });
  at(osEnd + 1.9, stepEvent("TOOL_CALL_START", "graf_ml", "graph.communities", { data: { tool: "graph.communities" } }));
  at(osEnd + 2.4, stepEvent("CUSTOM", "graf_ml", "AX-014 · Leiden: comunitatea 1 are 4 conturi; ieșirile duc spre același exchange.", { name: "fact", data: { fact_id: "AX-014" } }));
  at(osEnd + 2.9, stepEvent("TOOL_CALL_START", "graf_ml", "graph.mule_score", { data: { tool: "graph.mule_score" } }));
  at(osEnd + 3.5, stepEvent("STEP_FINISHED", "graf_ml", `M5: ${MULE_IBAN_SHORT} are scorul 0,94 (cărăuș probabil). Fapte obiective, fără date demografice.`, { data: { graph_update: true } }));
  const gEnd = osEnd + 3.5;
  at(gEnd + 0.2, stepEvent("STEP_STARTED", "avocat_nevinovatie", "Caut explicații nevinovate înainte de orice RTS."));
  innocentSeed().forEach((h, i) => {
    at(gEnd + 0.8 + i * 1.0, (aml, st, t, nextSeq) => {
      st.detail.innocent.push(h);
      st.detail.lead.innocent_hypotheses = st.detail.innocent;
      pushLeadEvent(aml, st.detail.lead.lead_id, nextSeq, t, "TEXT_MESSAGE_CONTENT", { step: "avocat_nevinovatie", agent: "Investigatorul/Avocatul nevinovăției", message: h.text, data: { delta: h.text, cites: h.cites } });
    });
  });
  const aEnd = gEnd + 0.8 + 3 * 1.0;
  at(aEnd, stepEvent("STEP_FINISHED", "avocat_nevinovatie", "3 ipoteze; „cărăuș recrutat” rămâne deschisă."));
  at(aEnd + 0.2, stepEvent("STEP_STARTED", "redactor_rts", "Redactez ciorna RTS; fiecare frază citează un AX."));
  at(aEnd + 2.2, (aml, st, t, nextSeq) => {
    st.detail.rts = rtsSeed(st.detail);
    pushLeadEvent(aml, st.detail.lead.lead_id, nextSeq, t, "STEP_FINISHED", { step: "redactor_rts", agent: "Investigatorul/Redactor RTS", message: "Ciornă RTS cu 4 fraze, toate cu sursă. Nu se depune nimic automat." });
  });
  at(aEnd + 2.5, (aml, st, t, nextSeq) => {
    st.status = "așteaptă analistul";
    pushLeadEvent(aml, st.detail.lead.lead_id, nextSeq, t, "CUSTOM", {
      step: "analist",
      agent: "Analist AML",
      name: "interrupt",
      message: "Analistul decide: depune RTS, închide, cere informații sau emite HOLD spre zona client.",
      data: { pending: true, options: ["file_rts", "close", "request_info", "hold_client"] },
    });
  });
  return steps;
}

export function advanceAml(aml: AmlDb, leadId: string, now: number, nextSeq: () => number): boolean {
  const st = aml.leads[leadId];
  const run = st?.run;
  if (!st || !run || run.done) return false;
  const tl = amlTimeline();
  let changed = false;
  while (run.cursor < tl.length && run.startedAt + tl[run.cursor].t * 1000 <= now) {
    const s = tl[run.cursor];
    s.apply(aml, st, Math.min(now, run.startedAt + s.t * 1000), nextSeq);
    run.cursor += 1;
    changed = true;
  }
  if (run.cursor >= tl.length && !run.decided) {
    // așteaptă decizia analistului; rularea rămâne deschisă
  }
  return changed;
}

// ------------------------------------------------------------------ OSINT la cerere

function cuiValid(cui: string): boolean {
  const digits = cui.replace(/\D/g, "");
  if (digits.length < 2 || digits.length > 10) return false;
  const key = "753217532";
  const body = digits.slice(0, -1).padStart(9, "0");
  const control = Number(digits.slice(-1));
  let sum = 0;
  for (let i = 0; i < 9; i++) sum += Number(body[i]) * Number(key[i]);
  let c = (sum * 10) % 11;
  if (c === 10) c = 0;
  return c === control;
}

function ibanValid(iban: string): boolean {
  const s = iban.replace(/\s|•/g, "").toUpperCase();
  if (!/^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$/.test(s)) return false;
  const re = s.slice(4) + s.slice(0, 4);
  const num = re.replace(/[A-Z]/g, (ch) => String(ch.charCodeAt(0) - 55));
  let rem = 0;
  for (const ch of num) rem = (rem * 10 + Number(ch)) % 97;
  return rem === 1;
}

export function detectKind(target: string): Exclude<OsintKind, "auto"> {
  const t = target.trim();
  if (/^https?:\/\//i.test(t)) return "url";
  if (/^(\+?40|0)\s?7/.test(t.replace(/[\s.-]/g, "")) || /^\+?\d[\d\s]{8,}$/.test(t)) return "phone";
  if (/^RO\d{2}\s?[A-Z]{4}/i.test(t.replace(/\s/g, ""))) return "iban";
  if (/^(RO)?\s?\d{2,10}$/i.test(t.replace(/\s/g, "")) || /^cui/i.test(t)) return "cui";
  if (/^[a-z0-9-]+(\.[a-z0-9-]+)+$/i.test(t)) return "domain";
  return "company";
}

export function osintLookup(target: string, kindIn: OsintKind = "auto"): OsintResult {
  const kind = kindIn === "auto" ? detectKind(target) : kindIn;
  const clean = target.trim();
  const isScam = /bancademo|curierdemo|livrare/i.test(clean);
  const f = (tool: string, summary: string, signal: OsintFinding["signal"], source_url: string | null = null): OsintFinding => ({ tool, target: clean, ok: true, summary, signal, fact_id: null, source_url, mode: "fixture" });
  const findings: OsintFinding[] = [];
  if (kind === "domain" || kind === "url") {
    const host = kind === "url" ? clean.replace(/^https?:\/\//i, "").split("/")[0] : clean;
    if (isScam) {
      findings.push(f("rdap_domain", `${host}: înregistrat acum circa 6 ore, date de contact ascunse.`, "rosu"));
      findings.push(f("ct_certificates", "Primul certificat TLS: azi, 08:20. Niciun istoric anterior.", "rosu"));
      findings.push(f("lookalike_score", "Scor de sosie 0,93 față de bancademo.example (M3).", "rosu"));
      findings.push(f("wayback_first_seen", "Nicio captură în arhivă: domeniul e nou.", "galben"));
      findings.push(f("openphish_check", "Nu apare încă în feedul OpenPhish.", "galben"));
      if (kind === "url") findings.push(f("page_similarity", "Pagina seamănă 0,91 cu pagina de login Banca Demo (M4).", "rosu"));
    } else {
      findings.push(f("rdap_domain", `${host}: înregistrat acum peste 6 ani, registrar cunoscut.`, "verde"));
      findings.push(f("lookalike_score", "Scor de sosie 0,08: nu seamănă cu domeniul băncii.", "verde"));
      findings.push(f("openphish_check", "Nu apare în feedul OpenPhish.", "verde"));
      findings.push(f("dns_records", "MX și SPF configurate, ca la un domeniu folosit de mult.", "neutru"));
    }
  } else if (kind === "phone") {
    findings.push(f("phone_intel", isScam || clean.endsWith("214") ? "Numărul apare în 2 reclamații legate de același IBAN." : "Număr mobil RO, fără apariții în reclamațiile din zona AML.", clean.endsWith("214") ? "galben" : "neutru"));
  } else if (kind === "iban") {
    const ok = ibanValid(clean);
    const bank = clean.replace(/\s/g, "").slice(4, 8).toUpperCase();
    const fictive = ["BDEM", "XBNK", "YBNK", "ZBNK"].includes(bank);
    findings.push(f("validate_iban", ok ? `IBAN valid (cifre de control corecte)${fictive ? `; banca ${bank} e fictivă (date sintetice)` : ""}.` : "IBAN invalid: cifrele de control nu se potrivesc.", ok ? "neutru" : "galben"));
    if (clean.replace(/\s|•/g, "").endsWith("7731")) findings.push(f("graph.link_cases", "Contul e în pista PST-2026-0007, cu scorul M5 0,94.", "rosu"));
  } else if (kind === "cui") {
    const ok = cuiValid(clean);
    findings.push(f("anaf_company", ok ? "CUI valid ca format; firma nu apare în registrul sintetic al demo-ului." : "CUI-ul nu trece cifra de control: nu poate fi o firmă reală.", ok ? "neutru" : "rosu"));
  } else {
    findings.push(f("sanctions_screen", "Nicio potrivire în lista locală de sancțiuni (copie de demo).", "verde"));
    findings.push(f("news_search", "Nicio știre negativă găsită (sursă de căutare neconfigurată în modul mock).", "neutru"));
  }
  return { findings, raw: { kind, target: clean, mode: "fixture", tools: findings.map((x) => x.tool) } };
}
