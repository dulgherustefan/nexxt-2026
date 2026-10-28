/**
 * The knowledge base in mock mode: a small synthetic corpus, hybrid search (BM25 + a "dense" score
 * on concept groups, fused with RRF, k = 60) and grounded answers with [n] markers.
 *
 * The passages paraphrase the rule texts in docs/context/11 and 14 and the explanations the mock
 * stories already use. Nothing here is a new rule, article or threshold. The precedents are
 * synthetic closed cases.
 */
import type { KbAnswer, KbHit, KbKind, KbStats } from "../api/types";
import { isoRo } from "./calendar";
import { RULES } from "./fixtures";

interface Passage {
  id: string;
  kind: KbKind;
  title: string;
  text: string;
  source: string;
  confidence: "P" | "S" | "U" | null;
  rule_ids: string[];
  meta?: Record<string, unknown>;
}

// ------------------------------------------------------------------ the client corpus

const LAW: Passage[] = [
  {
    id: "ctx:l209#art-169",
    kind: "law",
    title: "Notice within 13 months of the debit",
    source: "Law 209/2019, art. 169",
    confidence: "P",
    rule_ids: ["PAY-01"],
    text: "The customer reports an unauthorized payment without undue delay, and no later than 13 months after the debit. The limit does not apply if the bank did not give the required information about the payment. The Advocate General's opinion in C-70/25 confirms that after 13 months there is no duty to refund right away.",
  },
  {
    id: "ctx:l209#art-171-172",
    kind: "law",
    title: "The bank carries the burden of proof",
    source: "Law 209/2019, art. 171–172",
    confidence: "P",
    rule_ids: ["PAY-02", "DSP-02"],
    text: "When the customer denies authorizing a payment, the bank proves that it was authenticated, recorded correctly, booked and not affected by a technical failure. Use of the payment instrument alone is not necessarily enough. The burden of proof for fraud or gross negligence is on the bank.",
  },
  {
    id: "ctx:l209#art-173-174",
    kind: "law",
    title: "Refund by the end of the next business day",
    source: "Law 209/2019, art. 173–174",
    confidence: "P",
    rule_ids: ["PAY-03", "DSP-03"],
    text: "For an unauthorized payment, the bank refunds the amount immediately, and in any case by the end of the next business day after it notes the payment or is told about it. It restores the account to its earlier state, with a value date no later than the debit date. The only exception: reasonable grounds to suspect fraud by the payer, reported in writing to the national authority.",
  },
  {
    id: "ctx:c-70-25#ruling",
    kind: "law",
    title: "Gross negligence does not block the refund",
    source: "CJEU C-70/25, ruling of 15 Oct 2026",
    confidence: "P",
    rule_ids: ["PAY-15", "PAY-03"],
    text: "Gross negligence by the customer, such as entering details on a fake bank website, does not allow the bank to refuse or delay the next-business-day refund. The refund and the final allocation of the loss are separate: afterwards, the bank can ask for the money back if it proves intent or gross negligence, and the burden of proof is on the bank.",
  },
  {
    id: "ctx:l209#art-177",
    kind: "law",
    title: "When the customer bears no loss",
    source: "Law 209/2019, art. 177",
    confidence: "P",
    rule_ids: ["PAY-04"],
    text: "A payer who did not act fraudulently bears no loss if: the loss, theft or misappropriation could not be detected before the payment; the loss was caused by the bank's staff, agents, branches or outsourcers; it happened after the customer reported the loss or theft; the bank did not require strong customer authentication; or the bank offered no permanent way to report it.",
  },
  {
    id: "ctx:l209#art-179-1",
    kind: "law",
    title: "At most EUR 30 for a lost or stolen instrument",
    source: "Law 209/2019, art. 179(1)",
    confidence: "P",
    rule_ids: ["PAY-05"],
    text: "The payer bears at most EUR 30, or the equivalent in lei, for a lost, stolen or misappropriated payment instrument, if they did not act fraudulently and did not intentionally breach their obligations under art. 166.",
  },
  {
    id: "ctx:l209#art-179-2",
    kind: "law",
    title: "Full loss only for fraud or gross negligence",
    source: "Law 209/2019, art. 179(2)–(3)",
    confidence: "P",
    rule_ids: ["PAY-06"],
    text: "The payer bears all losses caused by fraud, or by breaching their obligations under art. 166 intentionally or through gross negligence: using the instrument under its terms, reporting without delay and keeping the security details safe. The nature of the security details and the circumstances are taken into account.",
  },
  {
    id: "ctx:l209#art-220",
    kind: "law",
    title: "Strong authentication and dynamic linking",
    source: "Law 209/2019, art. 220",
    confidence: "P",
    rule_ids: ["PAY-08", "DSP-10"],
    text: "Strong customer authentication applies when the customer accesses the account online, starts an electronic payment, or takes any remote action with a risk of fraud. Remote electronic payments need dynamic linking to the amount and the payee. Strong authentication uses at least two independent elements: knowledge, possession and inherence.",
  },
  {
    id: "ctx:l209#art-224",
    kind: "law",
    title: "Answer a complaint within 15 business days",
    source: "Law 209/2019, art. 224",
    confidence: "P",
    rule_ids: ["CMP-01", "CMP-02", "DSP-14"],
    text: "Complaints about payment services get an answer on paper or another agreed durable medium, covering every point, no later than 15 business days after the complaint is received. In exceptional situations outside the bank's control, a holding reply gives the reasons and the date of the final answer, which cannot be more than 35 business days after receipt.",
  },
  {
    id: "ctx:l209#art-225",
    kind: "law",
    title: "Tell the customer where else to complain",
    source: "Law 209/2019, art. 225, 185(2)",
    confidence: "P",
    rule_ids: ["CMP-03"],
    text: "The bank tells customers clearly, on its website, in its branches and in its general terms, about their right to complain to ANPC, ANAF, BNR and the competent alternative dispute resolution entity.",
  },
  {
    id: "ctx:gdpr#art-22",
    kind: "law",
    title: "No fully automated adverse decision",
    source: "GDPR art. 22; CJEU C-634/21",
    confidence: "S",
    rule_ids: ["DP-02"],
    text: "A decision based only on automated processing that significantly affects a person needs a human in the loop. The reviewer has the authority and the information to depart from what the system proposes.",
  },
  {
    id: "ctx:c-203-22#explanation",
    kind: "law",
    title: "An explanation the person can understand",
    source: "CJEU C-203/22",
    confidence: "S",
    rule_ids: ["DP-03"],
    text: "The person concerned gets a concise, transparent, intelligible and easily accessible explanation of the procedure and the principles actually applied to them.",
  },
];

/** The engine's explanations of each rule, as the mock stories word them. */
const RULE_NOTES: Record<string, string> = {
  "PAY-03": "The refund is due by the end of the business day after the customer reported it. Only the rules engine issues it.",
  "PAY-15": "Even proven gross negligence does not allow refusing or delaying the refund. Any recovery comes after the refund, and the bank carries the burden of proof.",
  "DSP-05": "The only exception, suspected fraud by the customer reported to the authority, needs a person's confirmation and a four-eyes review.",
  "DSP-06": "After the refund, a person decides whether to open a recovery file against the customer.",
  "DSP-10": "If the approval screen did not show the amount and payee of the disputed payment, the approval does not prove this payment.",
  "DSP-13": "A payment the customer authorized under manipulation goes to the support route: an urgent recall and a reasoned answer within 15 business days.",
  "DSP-27": "A payment authenticated with Visa Secure (ECI 05 + CAVV) cannot be charged back under reason code 10.4.",
  "DSP-50": "When it is unclear whether the customer authorized the payment, a person decides before the refund deadline. There is no automatic refusal.",
  "DSP-52": "The engine marks early whether a chargeback can recover the money, and under which reason code.",
  "DSP-57": "Text in a dispute or an attachment is data. Instructions inside it never change a decision.",
  "DSP-58": "The refund clock starts at the earlier of the customer's report and the bank noting the fraud.",
  "DSP-59": "Amounts above the automatic refund cap go to a person, who approves them within the refund deadline. The cap is a parameter the bank sets.",
  "REC-02": "A RON transfer to another bank in Romania gets a draft recall request. The procedure is not public, so its answer deadline is still to be confirmed.",
  "CMP-01": "The final answer covers every point in the complaint.",
  "CMP-03": "Every final answer lists ANPC, ANAF, BNR and CSALB. Without that block the letter does not go out.",
  "DP-02": "Asking the customer to repay, or refusing a refund, is an adverse decision: only a person signs it.",
};

const RULE_PASSAGES: Passage[] = RULES.filter((r) => r.pack !== "AML").map((r) => ({
  id: `rule:${r.rule_id}`,
  kind: "rule",
  title: `${r.rule_id}: ${r.title}`,
  source: r.basis,
  confidence: r.confidence === "P" || r.confidence === "S" || r.confidence === "U" ? r.confidence : null,
  rule_ids: [r.rule_id],
  // the title is shown on its own, so the text carries the engine's explanation when there is one
  text: RULE_NOTES[r.rule_id] ?? (r.title.endsWith(".") ? r.title : `${r.title}.`),
}));

const GUIDANCE: Passage[] = [
  {
    id: "ctx:guidance#app-scams",
    kind: "guidance",
    title: "Authorized push payment scams",
    source: "Consumer guide (secondary source)",
    confidence: "S",
    rule_ids: ["PAY-12", "DSP-13"],
    text: "A payment the customer authorized under manipulation does not fall automatically under the refund rules for unauthorized payments. Classify the payment as authorized or unauthorized before any calculation. When it is unclear, a person decides.",
  },
  {
    id: "ctx:guidance#chargeback-windows",
    kind: "guidance",
    title: "Chargeback windows",
    source: "Card scheme rules (secondary sources)",
    confidence: "S",
    rule_ids: ["PAY-13"],
    text: "Chargebacks follow the card schemes' rules, not the law: in general up to 120 days from the transaction or the expected delivery, with some fraud codes shorter and some Visa codes up to 540 days. The merchant answers within 30 days (Visa) or 45 days (Mastercard).",
  },
  {
    id: "ctx:guidance#csalb",
    kind: "guidance",
    title: "CSALB, the banking dispute resolution center",
    source: "CSALB reports (secondary source)",
    confidence: "S",
    rule_ids: ["CMP-06"],
    text: "Going to CSALB is free. Negotiation lasts under three months, at most 90 days, with a conciliator both sides accept. An agreement has the force of a court ruling.",
  },
];

const TYPOLOGIES: Passage[] = [
  {
    id: "typ:phishing_link",
    kind: "typology",
    title: "Fake delivery link",
    source: "VersoML scenario catalog",
    confidence: null,
    rule_ids: ["PAY-03", "PAY-15", "DSP-10"],
    text: "A text message from a fake courier asks for a small fee. The link opens a page that copies the bank's login. Minutes later, a new device approves a transfer to a new payee. Signals: a domain registered the same day, a high look-alike score, a payment within minutes of the click.",
  },
  {
    id: "typ:vishing_securitate",
    kind: "typology",
    title: "Fake bank security call",
    source: "VersoML scenario catalog",
    confidence: null,
    rule_ids: ["PAY-12", "DSP-13", "DSP-50"],
    text: "A caller says they are from the bank's security team and asks the customer to approve a notification to protect their money. The customer approves the payment themselves, so it is an authorized push payment: no automatic next-day refund, and a person decides when it is unclear.",
  },
  {
    id: "typ:cont_sigur",
    kind: "typology",
    title: "“Move your money to a safe account”",
    source: "VersoML scenario catalog",
    confidence: null,
    rule_ids: ["PAY-12"],
    text: "The customer is told their account is at risk and moves the money to a “safe account” the fraudster controls, often by instant transfer. Authorized under manipulation; the bank starts an urgent recall.",
  },
  {
    id: "typ:sim_swap",
    kind: "typology",
    title: "SIM swap",
    source: "VersoML scenario catalog",
    confidence: null,
    rule_ids: ["PAY-02", "PAY-03"],
    text: "The fraudster moves the customer's number to a new SIM and receives the one-time codes. The customer's phone loses signal shortly before the payment. A code sent to the new SIM does not prove authorization on its own.",
  },
  {
    id: "typ:card_ecom_fara_3ds",
    kind: "typology",
    title: "Online card payment without 3-D Secure",
    source: "VersoML scenario catalog",
    confidence: null,
    rule_ids: ["PAY-04", "DSP-52"],
    text: "An e-commerce payment with ECI 07, so no strong authentication. The customer bears no loss (art. 177), and a 10.4 chargeback is possible.",
  },
];

const CASE_STUDIES: Passage[] = [
  {
    id: "case:edge-cases#ex-25",
    kind: "case_study",
    title: "Phishing that an operator wants to close as gross negligence",
    source: "VersoML edge cases, EX-25",
    confidence: "P",
    rule_ids: ["PAY-03", "PAY-06", "PAY-15"],
    text: "The customer entered their details on a fake bank website and approved the authentication. The operator wants to close the case as gross negligence. The refusal is blocked: the refund is due by the end of the next business day unless a suspicion of fraud was reported to the authority, and a recovery review opens with an evidence pack.",
  },
  {
    id: "case:edge-cases#ex-19",
    kind: "case_study",
    title: "Gross negligence claimed without authentication logs",
    source: "VersoML edge cases, EX-19",
    confidence: "P",
    rule_ids: ["PAY-02", "PAY-04", "PAY-06", "PAY-15"],
    text: "The refund goes out by the next business day anyway. On the recovery track the burden of proof is on the bank. If strong authentication was not required, the customer's liability is zero, and without logs recovery is blocked.",
  },
  {
    id: "case:edge-cases#ex-20",
    kind: "case_study",
    title: "A payment approved after a call “from the bank”",
    source: "VersoML edge cases, EX-20",
    confidence: "S",
    rule_ids: ["PAY-12"],
    text: "Treat it as an authorized push payment scam. Do not promise an automatic refund. Open a fraud case and a complaint.",
  },
  {
    id: "case:edge-cases#ex-18",
    kind: "case_study",
    title: "A refund asked for after 13 months",
    source: "VersoML edge cases, EX-18",
    confidence: "P",
    rule_ids: ["PAY-01", "CMP-01"],
    text: "If the bank gave the customer the payment information, the claim is late and gets a reasoned answer within the complaint deadline. If it did not, the 13-month limit does not apply.",
  },
];

// ------------------------------------------------------------------ precedents: synthetic closed cases

export interface PrecedentSeed {
  case_id: string;
  scenario: string;
  title: string;
  text: string;
  closed: string;
  rule_ids: string[];
  outcome: Record<string, unknown>;
}

const PRECEDENT_SEEDS: PrecedentSeed[] = [
  {
    case_id: "CT-2026-000071",
    scenario: "phishing_link",
    title: "Fake delivery link, transfer of RON 2,750.00",
    text: "The customer paid after a courier text message: new device, payment 3 minutes after the click, a domain registered that morning. A person approved the refund above the cap. The recall to the payee's bank brought back part of the money.",
    closed: "12 Aug 2026",
    rule_ids: ["PAY-03", "PAY-15", "DSP-59", "REC-02"],
    outcome: { decision: "RAMBURSEAZA_CU_APROBARE", status: "RAMBURSAT", refund_days: 1, recovered: { value: 1900, currency: "RON" }, amount: { value: 2750, currency: "RON" } },
  },
  {
    case_id: "CT-2026-000088",
    scenario: "phishing_link",
    title: "Fake delivery link, transfer of RON 1,240.00",
    text: "Same pattern: a fee of a few lei, a look-alike login page, a transfer to a new payee. Under the cap, so the refund was automatic. The recall came back empty: the money had left the payee's account.",
    closed: "2 Sep 2026",
    rule_ids: ["PAY-03", "PAY-15", "REC-02"],
    outcome: { decision: "RAMBURSEAZA", status: "RAMBURSAT", refund_days: 1, recovered: { value: 0, currency: "RON" }, amount: { value: 1240, currency: "RON" } },
  },
  {
    case_id: "CT-2026-000093",
    scenario: "phishing_link",
    title: "Fake bank login page, customer approved in the app",
    text: "The approval screen showed the amount and the payee. The refund went out on time. The rubric reached the threshold and a person signed a recovery file against the customer, which the customer accepted.",
    closed: "19 Sep 2026",
    rule_ids: ["PAY-03", "PAY-06", "PAY-15", "DSP-06"],
    outcome: { decision: "RAMBURSEAZA", status: "RAMBURSAT", refund_days: 1, note: "Recovery file signed by a person; the customer repaid." },
  },
  {
    case_id: "CT-2026-000064",
    scenario: "vishing_securitate",
    title: "Call “from the security department”, RON 6,500.00",
    text: "The customer approved the transfer on a screen that showed the amount and the payee. Treated as an authorized push payment: no automatic refund. The urgent recall recovered the full amount.",
    closed: "28 Jul 2026",
    rule_ids: ["DSP-13", "DSP-50", "REC-02"],
    outcome: { decision: "NU_SE_APLICA_T1", status: "TRASEU_APP", recovered: { value: 6500, currency: "RON" }, amount: { value: 6500, currency: "RON" } },
  },
  {
    case_id: "CT-2026-000052",
    scenario: "sim_swap",
    title: "SIM swap, transfer of RON 3,900.00",
    text: "The SIM was swapped an hour before the payment and the code went to the new SIM. A person approved the refund above the cap, on time.",
    closed: "6 Jul 2026",
    rule_ids: ["PAY-02", "PAY-03", "DSP-59"],
    outcome: { decision: "RAMBURSEAZA_CU_APROBARE", status: "RAMBURSAT", refund_days: 1, amount: { value: 3900, currency: "RON" } },
  },
  {
    case_id: "CT-2026-000079",
    scenario: "card_ecom_fara_3ds",
    title: "Online card payment without 3-D Secure, RON 430.00",
    text: "ECI 07, no strong authentication: zero liability for the customer and an automatic refund. The 10.4 chargeback recovered the amount from the merchant's bank.",
    closed: "21 Aug 2026",
    rule_ids: ["PAY-03", "PAY-04", "DSP-52"],
    outcome: { decision: "RAMBURSEAZA", status: "RAMBURSAT", refund_days: 1, recovered: { value: 430, currency: "RON" }, amount: { value: 430, currency: "RON" } },
  },
  {
    case_id: "CT-2026-000047",
    scenario: "plata_dubla",
    title: "Charged twice at a gas station",
    text: "Two identical card transactions a few seconds apart. A processing error, not an unauthorized payment: the 12.6 chargeback returned the duplicate.",
    closed: "30 Jun 2026",
    rule_ids: ["DSP-52", "PAY-13"],
    outcome: { decision: "CHARGEBACK", status: "INCHIS", recovered: { value: 215, currency: "RON" }, amount: { value: 215, currency: "RON" } },
  },
  {
    case_id: "CT-2026-000039",
    scenario: "reclamatie_tardiva",
    title: "A card payment reported after 15 months",
    text: "The statements were available every month, so the 13-month limit applied. A person signed the reasoned rejection, which named the external complaint routes.",
    closed: "11 Jun 2026",
    rule_ids: ["PAY-01", "DP-02", "CMP-03"],
    outcome: { decision: "RESPINGE_TARDIV", status: "RESPINS" },
  },
];

export const PRECEDENTS: Passage[] = PRECEDENT_SEEDS.map((p) => ({
  id: `prec:${p.case_id}`,
  kind: "precedent",
  title: p.title,
  source: `Closed case, ${p.closed}`,
  confidence: null,
  rule_ids: p.rule_ids,
  text: p.text,
  meta: { outcome: p.outcome, scenario: p.scenario, case_id: maskCaseId(p.case_id) },
}));

export function maskCaseId(id: string): string {
  return id.replace(/(\d{3})(\d{3})$/, "•••$2");
}

const CLIENT_CORPUS: Passage[] = [...LAW, ...RULE_PASSAGES, ...GUIDANCE, ...TYPOLOGIES, ...CASE_STUDIES, ...PRECEDENTS];

// ------------------------------------------------------------------ the AML corpus (served only by the AML zone)

const AML_CORPUS: Passage[] = [
  {
    id: "ctx:l129#art-6",
    kind: "law",
    title: "Report a suspicious transaction to ONPCSB",
    source: "Law 129/2019, art. 6(1), 6(3)",
    confidence: "P",
    rule_ids: ["AML-01"],
    text: "A suspicious transaction report goes only to ONPCSB when the bank knows, suspects or has reasonable grounds to suspect that the funds come from crime or are linked to terrorist financing, or that the information may help law enforcement; and when ONPCSB asks that a future transaction be treated as suspicious.",
  },
  {
    id: "ctx:l129#art-8-1",
    kind: "law",
    title: "Report without delay, before the transaction runs",
    source: "Law 129/2019, art. 8(1)–(2)",
    confidence: "P",
    rule_ids: ["AML-02"],
    text: "The report goes out without delay and before any of the customer's transactions linked to the suspicion is executed. ONPCSB confirms it right away with a registration number.",
  },
  {
    id: "ctx:l129#art-8-3",
    kind: "law",
    title: "The 24-hour hold after a report",
    source: "Law 129/2019, art. 8(3)",
    confidence: "P",
    rule_ids: ["AML-03"],
    text: "The transaction is held: it is not executed for 24 hours after the report is registered. After that it can run, unless ONPCSB ordered a suspension.",
  },
  {
    id: "ctx:l129#art-8-4",
    kind: "law",
    title: "Suspension by ONPCSB",
    source: "Law 129/2019, art. 8(4), 8(6), 8(9)",
    confidence: "P",
    rule_ids: ["AML-04"],
    text: "ONPCSB can suspend the transaction for up to 48 hours, and can ask the prosecutor's office once for an extension of up to 72 hours. If the extension is not communicated before the suspension ends, the bank can execute the transaction.",
  },
  {
    id: "ctx:l129#art-8-10",
    kind: "law",
    title: "Hour deadlines on non-business days",
    source: "Law 129/2019, art. 8(10)",
    confidence: "P",
    rule_ids: ["AML-05"],
    text: "A deadline counted in hours that ends on a non-business day moves to the same hour on the next business day.",
  },
  {
    id: "ctx:l129#art-8-12",
    kind: "law",
    title: "Electronic reports and corrections",
    source: "Law 129/2019, art. 8(12)–(14)",
    confidence: "P",
    rule_ids: ["AML-06"],
    text: "Reports go only electronically, through ONPCSB's channels. A report that does not comply comes back and is corrected within 2 business days, and the 24 hours start again when the corrected report is confirmed.",
  },
  ...RULES.filter((r) => r.pack === "AML").map((r): Passage => ({
    id: `rule:${r.rule_id}`,
    kind: "rule",
    title: `${r.rule_id}: ${r.title}`,
    source: r.basis,
    confidence: r.confidence === "P" || r.confidence === "S" || r.confidence === "U" ? r.confidence : null,
    rule_ids: [r.rule_id],
    text: `${r.title}.`,
  })),
  {
    id: "typ:mule_account",
    kind: "typology",
    title: "Money mule account",
    source: "VersoML typology catalog",
    confidence: null,
    rule_ids: ["AML-01"],
    text: "An account receives transfers from several unrelated senders within hours, then moves the money on in smaller amounts or withdraws it in cash. Signals: a recently opened account, many first-time senders, money leaving within minutes.",
  },
  {
    id: "typ:fan_out",
    kind: "typology",
    title: "Fan-out after a fraud payment",
    source: "VersoML typology catalog",
    confidence: null,
    rule_ids: ["AML-01", "AML-02"],
    text: "A fraud payment lands in one account and leaves at once in several transfers to other new accounts, often at other banks, so a recall finds the first account empty.",
  },
  {
    id: "case:aml#one-scam-several-victims",
    kind: "case_study",
    title: "One scam, several victims",
    source: "VersoML scenario catalog",
    confidence: null,
    rule_ids: ["AML-01", "AML-03"],
    text: "Three customers paid the same account after the same fake page. The disputes reach the AML zone only as signed facts about the attack and the payee, never the victims' identities. An analyst decides whether to file a report.",
  },
];

// ------------------------------------------------------------------ search: BM25 + concept groups, fused with RRF

const STOP = new Set(
  ("a an and are as at be by can do does for from has have how i if in into is it its may must my no not of on or our so " +
    "than that the their them then there they this to was we what when where which who why will with you your " +
    "si sa se la de din pe cu un o ce cum ca care este sunt nu mai al ale lui le ne va")
    .split(" "),
);

function fold(s: string): string {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

function tokens(s: string): string[] {
  return fold(s)
    .split(/[^a-z0-9]+/)
    .filter((t) => t.length > 1 && !STOP.has(t));
}

/** Concept groups stand in for embeddings: they match across English and Romanian wording. */
const CONCEPTS: Array<[string, string[]]> = [
  ["refund", ["refund", "refunds", "refunded", "rambursare", "rambursa", "rambursam", "rambursati", "ramburseaza", "rambursarea", "reimburse", "back", "inapoi", "banii", "money"]],
  ["negligence", ["negligence", "negligent", "neglijenta", "neglijent", "careless"]],
  ["deadline", ["deadline", "termen", "termenul", "business", "lucratoare", "day", "days", "zi", "zile", "next", "until", "hours", "ore", "when"]],
  ["fraud", ["fraud", "frauda", "fraudster", "escroc", "scam", "suspicion", "suspiciune", "suspect"]],
  ["authorization", ["authorized", "authorize", "unauthorized", "autorizat", "autorizare", "neautorizata", "approved", "approve", "aprobat", "sca", "authentication", "autentificare"]],
  ["complaint", ["complaint", "complaints", "reclamatie", "reclamatia", "answer", "raspuns", "letter", "scrisoare", "reply"]],
  ["phishing", ["phishing", "link", "sms", "text", "courier", "curier", "fake", "fals", "website", "site", "page", "domain"]],
  ["call", ["call", "called", "apel", "sunat", "telefon", "phoned", "vishing", "security", "securitate", "caller"]],
  ["chargeback", ["chargeback", "card", "visa", "mastercard", "scheme", "merchant", "comerciant"]],
  ["recall", ["recall", "rechemare", "camt", "return", "payee"]],
  ["late", ["13", "months", "luni", "late", "tardiv", "old", "limit"]],
  ["liability", ["liability", "raspundere", "loss", "losses", "pierdere", "bears", "eur", "30"]],
  ["human", ["person", "human", "om", "signature", "sign", "signs", "semnatura", "automated", "automat", "decision"]],
  ["exception", ["exception", "exceptie", "withhold", "refuse", "refusal", "delay", "amana", "refuza"]],
  ["sim", ["sim", "swap", "signal", "semnal", "code", "otp", "cod"]],
  ["report", ["report", "str", "onpcsb", "raport", "suspend", "suspension", "hold", "held"]],
  ["mule", ["mule", "carausi", "mules", "account", "accounts", "cont", "conturi", "cash", "numerar"]],
  ["instructions", ["instructions", "ignore", "system", "injection", "prompt", "instructiuni"]],
];

const CONCEPT_OF = new Map<string, string[]>();
for (const [concept, words] of CONCEPTS) {
  for (const w of words) CONCEPT_OF.set(w, [...(CONCEPT_OF.get(w) ?? []), concept]);
}

function concepts(toks: string[]): Set<string> {
  const out = new Set<string>();
  for (const t of toks) for (const c of CONCEPT_OF.get(t) ?? []) out.add(c);
  return out;
}

interface Indexed {
  p: Passage;
  toks: string[];
  tf: Map<string, number>;
  concepts: Set<string>;
}

function index(corpus: Passage[]): { docs: Indexed[]; df: Map<string, number>; avg: number } {
  const docs = corpus.map((p) => {
    // the title counts twice, like a boosted field
    const toks = tokens(`${p.title} ${p.title} ${p.text} ${p.source} ${p.rule_ids.join(" ")}`);
    const tf = new Map<string, number>();
    for (const t of toks) tf.set(t, (tf.get(t) ?? 0) + 1);
    return { p, toks, tf, concepts: concepts(toks) };
  });
  const df = new Map<string, number>();
  for (const d of docs) for (const t of new Set(d.toks)) df.set(t, (df.get(t) ?? 0) + 1);
  const avg = docs.reduce((s, d) => s + d.toks.length, 0) / Math.max(1, docs.length);
  return { docs, df, avg };
}

const CLIENT_INDEX = index(CLIENT_CORPUS);
const AML_INDEX = index(AML_CORPUS);
const RRF_K = 60;

function rank(ix: ReturnType<typeof index>, q: string, opts: { kind?: string; k?: number } = {}): KbHit[] {
  const qt = tokens(q);
  const qRuleIds = (q.match(/\b[A-Z]{2,3}-\d{2}\b/gi) ?? []).map((s) => s.toUpperCase());
  const qc = concepts(qt);
  const docs = opts.kind ? ix.docs.filter((d) => d.p.kind === opts.kind) : ix.docs;
  const N = ix.docs.length;
  const k1 = 1.2;
  const b = 0.75;

  const bm25 = docs.map((d) => {
    let s = 0;
    for (const t of new Set(qt)) {
      const f = d.tf.get(t);
      if (!f) continue;
      const n = ix.df.get(t) ?? 0;
      const idf = Math.log(1 + (N - n + 0.5) / (n + 0.5));
      s += idf * ((f * (k1 + 1)) / (f + k1 * (1 - b + (b * d.toks.length) / ix.avg)));
    }
    if (qRuleIds.some((id) => d.p.rule_ids.includes(id))) s += 6;
    return { d, s };
  });
  const dense = docs.map((d) => {
    const shared = [...qc].filter((c) => d.concepts.has(c)).length;
    let s = qc.size && d.concepts.size ? shared / Math.sqrt(qc.size * d.concepts.size) : 0;
    if (qRuleIds.some((id) => d.p.rule_ids.includes(id))) s += 0.5;
    return { d, s };
  });
  const bmRank = new Map<Indexed, number>();
  bm25.filter((x) => x.s > 0).sort((a, b2) => b2.s - a.s).forEach((x, i) => bmRank.set(x.d, i + 1));
  const deRank = new Map<Indexed, number>();
  dense.filter((x) => x.s > 0.2).sort((a, b2) => b2.s - a.s).forEach((x, i) => deRank.set(x.d, i + 1));

  const fused = docs
    .map((d) => {
      const r1 = bmRank.get(d);
      const r2 = deRank.get(d);
      const rrf = (r1 ? 1 / (RRF_K + r1) : 0) + (r2 ? 1 / (RRF_K + r2) : 0);
      return { d, r1, r2, rrf };
    })
    .filter((x) => x.rrf > 0)
    .sort((a, b2) => b2.rrf - a.rrf)
    .slice(0, opts.k ?? 6);

  return fused.map((x) => toHit(x.d.p, { bm25_rank: x.r1 ?? null, dense_rank: x.r2 ?? null, rrf: Math.round(x.rrf * 10_000) / 10_000, dense: true }));
}

function toHit(p: Passage, why: KbHit["why"]): KbHit {
  return {
    id: p.id,
    kind: p.kind,
    title: p.title,
    text: p.text,
    source: p.source,
    confidence: p.confidence,
    rule_ids: p.rule_ids,
    score: why.rrf ?? 0,
    why,
    meta: p.meta ?? {},
  };
}

export function kbSearch(q: string, opts: { kind?: string; k?: number } = {}): KbHit[] {
  if (!q.trim()) return [];
  return rank(CLIENT_INDEX, q, opts);
}

export function amlKbSearch(q: string, k = 6): KbHit[] {
  if (!q.trim()) return [];
  return rank(AML_INDEX, q, { k });
}

/** One passage by ID, with a plausible "why" (for the grounding a case carries). */
export function kbPassage(id: string, position = 1): KbHit | null {
  const p = CLIENT_CORPUS.find((x) => x.id === id);
  if (!p) return null;
  const bm = position;
  const de = position === 1 ? 2 : position === 2 ? 1 : position + 1;
  return toHit(p, { bm25_rank: bm, dense_rank: de, rrf: Math.round((1 / (RRF_K + bm) + 1 / (RRF_K + de)) * 10_000) / 10_000, dense: true });
}

// ------------------------------------------------------------------ grounded answers

interface Canned {
  when: (c: Set<string>, t: string[]) => boolean;
  answer: string;
  ids: string[];
}

/** Recorded answers for the questions the demo asks, in the voice of the live model. */
const CANNED: Canned[] = [
  {
    when: (c) => c.has("negligence"),
    answer:
      "No. Gross negligence does not allow the bank to refuse or delay the refund [1]. The bank refunds an unauthorized payment by the end of the next business day [2]. " +
      "Afterwards it can ask the customer to repay only if it proves intent or gross negligence, and the burden of proof is on the bank [3].",
    ids: ["ctx:c-70-25#ruling", "ctx:l209#art-173-174", "ctx:l209#art-179-2"],
  },
  {
    when: (c) => c.has("call") || (c.has("authorization") && c.has("fraud") && !c.has("refund")),
    answer:
      "A payment the customer approved under manipulation does not fall automatically under the next-business-day refund [1]. " +
      "VersoML classifies the payment first, and a person decides when it is unclear [2]. The bank starts an urgent recall to the payee's bank [3].",
    ids: ["ctx:guidance#app-scams", "rule:DSP-50", "rule:REC-02"],
  },
  {
    when: (c) => c.has("complaint"),
    answer:
      "The answer covers every point and goes out within 15 business days of receiving the complaint [1]. " +
      "It names ANPC, ANAF, BNR and CSALB as other places to complain [2]. In exceptional cases, a holding reply can extend the deadline to 35 business days [1].",
    ids: ["ctx:l209#art-224", "ctx:l209#art-225"],
  },
  {
    when: (c) => c.has("refund") && (c.has("deadline") || c.has("authorization")),
    answer:
      "By the end of the next business day after the customer reports the payment [1]. The clock starts at the earlier of the customer's report and the bank noting the fraud [2]. " +
      "The only exception is a suspicion of customer fraud reported to the authority [1].",
    ids: ["ctx:l209#art-173-174", "rule:DSP-58"],
  },
];

function firstSentence(s: string): string {
  const m = s.match(/^.*?[.!?](\s|$)/);
  return (m ? m[0] : s).trim();
}

export function kbAsk(question: string, k = 4): KbAnswer {
  const q = question.trim();
  const qc = concepts(tokens(q));
  const canned = CANNED.find((c) => c.when(qc, tokens(q)));
  if (canned) {
    const citations = canned.ids.map((id, i) => kbPassage(id, i + 1)).filter((h): h is KbHit => Boolean(h));
    return { question: q, answer: canned.answer, citations, grounded: true, mode: "replay" };
  }
  const hits = kbSearch(q, { k }).filter((h) => h.kind !== "precedent");
  if (!hits.length) {
    return {
      question: q,
      answer: "No passage in the knowledge base answers this. Try other words, or search the passages.",
      citations: [],
      grounded: false,
      mode: "offline",
    };
  }
  const used = hits.slice(0, 3);
  const answer = used.map((h, i) => `${firstSentence(h.text).replace(/[.!?]$/, "")} [${i + 1}].`).join(" ");
  // the extractive fallback only quotes the passages, so it is grounded when the best match is a real match
  return { question: q, answer, citations: used, grounded: (used[0].why.bm25_rank ?? 99) <= 3, mode: "offline" };
}

export function kbStats(): KbStats {
  const chunks: Record<string, number> = {};
  for (const p of CLIENT_CORPUS) chunks[p.kind] = (chunks[p.kind] ?? 0) + 1;
  return { chunks, embedding_model: "cohere.embed-multilingual-v3", dense: true, built_at: isoRo(BUILT_AT) };
}

const BUILT_AT = Date.now() - 2.4 * 3600_000;

// ------------------------------------------------------------------ precedents for a case

const FAMILY: Record<string, string> = {
  demo_t1: "phishing_link",
  inel_carausi: "phishing_link",
  injectie_document: "phishing_link",
  cont_sigur: "vishing_securitate",
  marfa_nelivrata: "vishing_securitate",
  card_visa_secure: "phishing_link",
  frauda_client: "card_ecom_fara_3ds",
};

/** The closest closed cases: same scenario first, then the rest by a search on the claim. */
export function precedentsFor(scenario: string | null | undefined, claim: string) {
  const family = FAMILY[String(scenario)] ?? String(scenario ?? "");
  const searched = rank(CLIENT_INDEX, `${claim} ${family.replace(/_/g, " ")}`, { kind: "precedent", k: 8 });
  const same = PRECEDENT_SEEDS.filter((p) => p.scenario === family).map((p) => p.case_id);
  const order = [...same, ...searched.map((h) => String(h.id).replace(/^prec:/, ""))];
  const unique = Array.from(new Set(order)).slice(0, 3);
  return unique.map((caseId, i) => {
    const seed = PRECEDENT_SEEDS.find((p) => p.case_id === caseId)!;
    const hit = kbPassage(`prec:${caseId}`, i + 1)!;
    const similarity = Math.max(0.42, (same.includes(caseId) ? 0.91 : 0.66) - i * 0.07);
    return { hit: { ...hit, score: Math.round(similarity * 100) / 100 }, outcome: seed.outcome, case_id_masked: maskCaseId(caseId) };
  });
}
