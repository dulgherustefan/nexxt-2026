/**
 * Tipurile UI-ului. Oglindesc `versoml/contracts.py` (Pydantic) și contractul API din
 * docs/06_implementare.md §6. Câmpurile cu valori implicite în Pydantic sunt opționale aici,
 * ca UI-ul să nu cadă dacă backend-ul le omite.
 */

export type ISODate = string;

// ------------------------------------------------------------------ etichete și probe

export type Zone = "client" | "aml";
export type Trust = "trusted" | "untrusted";
export type Sink = "client" | "aml" | "llm" | "osint" | "letter";
export type Conf = "client" | "aml" | "aml-only" | "public";

export interface Labels {
  conf: Conf;
  trust: Trust;
  sinks: Sink[];
}

export interface Fact {
  fact_id: string;
  case_id: string;
  zone: Zone;
  kind: string;
  source_tool: string;
  args_hash: string;
  retrieved_at: ISODate;
  sha256: string;
  prev_hash?: string | null;
  labels?: Labels;
  summary?: string;
  content?: Record<string, unknown>;
}

// ------------------------------------------------------------------ reclamația și clasificarea

export type Channel = "card" | "transfer" | "transfer_instant";
export type DisputeType = "neautorizata" | "app" | "disputa_comerciant" | "eroare_procesare";
export type Scenario =
  | "phishing_link"
  | "card_ecom_fara_3ds"
  | "card_visa_secure"
  | "vishing_securitate"
  | "cont_sigur"
  | "sim_swap"
  | "frauda_client"
  | "reclamatie_tardiva"
  | "plata_dubla"
  | "inel_carausi"
  | "injectie_document"
  | "marfa_nelivrata";

export interface Money {
  value: number;
  currency?: string;
}

export type AttachmentKind = "sms" | "email" | "pdf_text" | "screenshot_text" | "call_transcript" | "chat";

export interface Attachment {
  kind: AttachmentKind;
  content: string;
  name?: string | null;
}

export interface Complaint {
  case_id: string;
  customer_ref: string;
  received_at: ISODate;
  channel_hint?: Channel | null;
  transaction_refs?: string[];
  text: string;
  attachments?: Attachment[];
  source?: "app" | "email" | "branch" | "call_center" | "web_form";
  synthetic?: boolean;
}

export interface ClaimPoint {
  text: string;
  quote?: string;
}

export interface ExtractedClaim {
  claims_unauthorized?: boolean | null;
  client_admits_sharing_credentials?: boolean | null;
  client_admits_approving_in_app?: boolean | null;
  noticed_at?: ISODate | null;
  contacted_by?: "sms" | "apel" | "email" | "mesagerie" | "site" | "necunoscut" | null;
  impersonated_entity?: string | null;
  mentioned_urls?: string[];
  mentioned_phones?: string[];
  mentioned_amounts?: number[];
  requested_remedy?: string | null;
  points?: ClaimPoint[];
  injection_suspected?: boolean;
  language?: string;
}

export interface Classification {
  channel: Channel;
  dispute_type: DisputeType;
  scenario?: Scenario | null;
  probability?: number;
  proba?: Record<string, number>;
  ambiguous?: boolean;
  model_version?: string;
  method?: "ml" | "llm" | "ml+llm" | "rules";
}

// ------------------------------------------------------------------ reguli și decizii

export type Confidence = "P" | "S" | "U" | "V";

export interface Deadline {
  rule_id: string;
  name: string;
  due_at: ISODate;
  basis: string;
  business_days?: boolean;
}

export interface RuleHit {
  rule_id: string;
  version?: string;
  title: string;
  basis: string;
  confidence?: Confidence;
  outcome: string;
  explanation?: string;
  inputs?: string[];
  params?: Record<string, unknown>;
}

export type Question =
  | "rambursare_t1"
  | "recuperare_client"
  | "recuperare_escroc"
  | "raspuns_reclamatie"
  | "pista_aml"
  | "rts";

export type Verdict =
  | "RAMBURSEAZA"
  | "RAMBURSEAZA_CU_APROBARE"
  | "EXCEPTIE_FRAUDA_CLIENT"
  | "RESPINGE_TARDIV"
  | "NU_SE_APLICA_T1"
  | "CHARGEBACK"
  | "RECHEMARE"
  | "RECUPERARE_PROPUSA"
  | "NU_RECOMANDAM_RECUPERARE"
  | "INFORMATII_SUPLIMENTARE"
  | "RTS_PROPUS"
  | "MONITORIZARE"
  | "INCHIDE";

export interface RationaleLine {
  text: string;
  cites?: string[];
}

export interface Decision {
  case_id: string;
  question: Question;
  decision: Verdict;
  rule_ids?: string[];
  supporting_evidence?: string[];
  contradicting_evidence?: string[];
  missing_evidence?: string[];
  rationale?: RationaleLine[];
  unknowns?: string[];
  next_actions?: string[];
  requires_human?: boolean;
  deadline?: ISODate | null;
  amount?: Money | null;
  decided_by?: "rules" | "human" | "rules+human";
}

export interface RuleContext {
  case_id: string;
  now: ISODate;
  channel: Channel;
  dispute_type: DisputeType;
  scenario?: Scenario | null;
  amount: Money;
  executed_at: ISODate;
  notified_at: ISODate;
  sca_performed?: boolean | null;
  sca_method?: string | null;
  eci?: string | null;
  cavv_present?: boolean | null;
  screen_showed_amount_and_payee?: boolean | null;
  device_known?: boolean | null;
  seconds_after_click?: number | null;
  sim_swap_hours_before?: number | null;
  beneficiary_new?: boolean | null;
  merchant_mcc?: string | null;
  duplicate_of?: string | null;
  prior_disputes_12m?: number;
  client_fraud_score?: number | null;
  client_admits_sharing_credentials?: boolean | null;
  client_admits_approving_in_app?: boolean | null;
  hold_signal?: boolean;
  hold_authority_notified?: boolean;
  fact_ids?: Record<string, string>;
}

export interface RulesOutcome {
  case_id: string;
  decisions?: Decision[];
  hits?: RuleHit[];
  deadlines?: Deadline[];
  params_used?: Record<string, unknown>;
  engine_version?: string;
}

// ------------------------------------------------------------------ zidul

export interface BeneficiaryRef {
  iban?: string | null;
  name?: string | null;
  cui?: string | null;
  bank_bic?: string | null;
}

export interface AttackRef {
  domain?: string | null;
  url?: string | null;
  phone?: string | null;
  domain_age_hours?: number | null;
  lookalike_score?: number | null;
}

export interface DisputeFacts {
  case_id: string;
  victim_ref: string;
  channel: Channel;
  dispute_type: DisputeType;
  scenario?: Scenario | null;
  amount: Money;
  executed_at: ISODate;
  beneficiary: BeneficiaryRef;
  attack?: AttackRef;
  fact_ids?: string[];
}

export interface HoldSignal {
  case_id: string;
  hold: boolean;
  approved_by: string;
  approved_at: ISODate;
  authority_notified?: boolean;
}

export interface PolicyDecision {
  allowed: boolean;
  principal: string;
  action: string;
  resource: string;
  reason?: string;
  policy_ids?: string[];
  at?: ISODate | null;
  engine?: string | null;
  case_id?: string | null;
}

export interface FilterResult {
  passed: boolean;
  blocked_terms?: string[];
  canaries_found?: number;
  classifier_flag?: boolean;
  pii_findings?: string[];
  reasons?: string[];
  term_spans?: Array<{ start: number; end: number; label: string }>;
}

export interface LetterDraft {
  case_id: string;
  subject: string;
  body: string;
  cites?: string[];
  points_answered?: string[];
  filter?: FilterResult | null;
  status?: "draft" | "blocked" | "approved" | "sent";
  cmp_checks?: Array<{ rule_id: string; outcome: string; explanation?: string }>;
}

// ------------------------------------------------------------------ zona AML

export interface AccountScore {
  account: string;
  score: number;
  label?: "carausi_probabil" | "de_verificat" | "normal";
  /** Pydantic `list[tuple[str, float]]` ajunge în JSON ca listă de perechi. */
  top_features?: Array<[string, number]>;
  community?: number | null;
}

export type Signal = "rosu" | "galben" | "verde" | "neutru";
export type SourceMode = "live" | "fixture" | "cache" | "offline";

export interface OsintFinding {
  tool: string;
  target: string;
  ok: boolean;
  summary: string;
  signal?: Signal;
  fact_id?: string | null;
  source_url?: string | null;
  mode?: SourceMode;
  latency_ms?: number | null;
}

export interface AmlLead {
  lead_id: string;
  case_ids: string[];
  accounts?: AccountScore[];
  typologies?: string[];
  osint?: OsintFinding[];
  innocent_hypotheses?: RationaleLine[];
  recommendation?: Verdict;
  rts_draft_id?: string | null;
  canary?: string | null;
}

// ------------------------------------------------------------------ evenimente (AG-UI)

export type EventType =
  | "RUN_STARTED"
  | "RUN_FINISHED"
  | "RUN_ERROR"
  | "STEP_STARTED"
  | "STEP_FINISHED"
  | "TEXT_MESSAGE_START"
  | "TEXT_MESSAGE_CONTENT"
  | "TEXT_MESSAGE_END"
  | "TOOL_CALL_START"
  | "TOOL_CALL_END"
  | "STATE_DELTA"
  | "CUSTOM";

export type CustomEventName =
  | "fact"
  | "rule_hit"
  | "decision"
  | "policy_denied"
  | "wall_block"
  | "interrupt"
  | "ledger_seal"
  | "hold_signal"
  | "refund"
  | "clock"
  | "typology";

export interface AgentEvent {
  type: EventType;
  zone: Zone;
  run_id: string;
  case_id: string;
  seq?: number;
  ts: ISODate;
  step?: string | null;
  agent?: string | null;
  name?: CustomEventName | string | null;
  message?: string | null;
  data?: Record<string, unknown>;
}

// ================================================================== răspunsurile API (docs/06 §6)

export type CaseStatus =
  | "NOU"
  | "IN_ANALIZA"
  | "ASTEAPTA_APROBARE"
  | "RAMBURSAT"
  | "EXCEPTIE"
  | "RESPINS"
  | "TRASEU_APP"
  | "INCHIS";

export type ModelRole = "opus" | "sonnet" | "haiku";

export interface Meta {
  zone: Zone;
  version?: string;
  llm?: {
    mode?: string;
    region?: string;
    models?: Partial<Record<ModelRole, string>>;
    live_ok?: boolean;
  };
  osint_mode?: string;
  urls?: { client?: string; aml?: string };
}

export interface Stats {
  cases_total: number;
  open: number;
  refunded: number;
  awaiting_human: number;
  amount_refunded: number | Money;
  amount_recoverable: number | Money;
  avg_decision_seconds: number | null;
  deadlines_at_risk: number;
  by_status?: Record<string, number>;
  by_scenario?: Record<string, number>;
}

export interface ScenarioInfo {
  id: string;
  title: string;
  description: string;
  channel: Channel | string;
  expected_verdict: Verdict | string;
}

export interface NewComplaint {
  customer_ref: string;
  text: string;
  transaction_refs: string[];
  attachments: Attachment[];
}

export type CreateCaseBody = { scenario_id: string } | { complaint: NewComplaint };

export interface CaseSummary {
  case_id: string;
  customer_alias: string;
  received_at: ISODate;
  channel: Channel | string;
  scenario: Scenario | string | null;
  amount: Money;
  status: CaseStatus | string;
  verdict: Verdict | string | null;
  deadline: ISODate | null;
  sla_seconds_left: number | null;
  requires_human: boolean;
  dispute_type?: DisputeType | string | null;
}

export type StoryKind = "click" | "device" | "auth" | "payment" | "dispute" | "aml" | "refund" | "letter" | "seal";

/** Cronologia cazului, construită de backend din probele din registru (`ClientService._story`). */
export interface StoryItem {
  ts: ISODate;
  kind: StoryKind | string;
  title: string;
  detail?: string;
  fact_id?: string | null;
}

export interface DebateArgument {
  text: string;
  cites?: string[];
}

export interface RubricRow {
  indicator: string;
  value: boolean | null;
  weight: number;
  cites?: string[];
}

export interface Debate {
  prosecutor?: DebateArgument[];
  defender?: DebateArgument[];
  rubric?: RubricRow[];
  recommendation?: Verdict | string | null;
  ran?: boolean;
  score?: number;
  rubric_recommendation?: string | null;
  agree_with_rules?: boolean;
  rejected_without_citation?: number;
  missing_evidence?: string[];
  models?: { procuror?: string; avocat?: string };
}

export interface Recovery {
  chargeback?: { eligible: boolean | null; reason_code?: string | null; explanation?: string } | null;
  recall?: { kind?: string; xml?: string | null; note?: string; deadline?: ISODate | null } | null;
  dnsc_report?: { title?: string; text?: string; indicators?: string[]; channel?: string; status?: string } | null;
  decision?: string | null;
  rule_ids?: string[];
}

export type NodeStatus = "idle" | "running" | "done" | "blocked" | "waiting" | "skipped" | "error";

export interface PipelineNode {
  id: string;
  label: string;
  agent?: string;
  model?: string | null;
  status?: NodeStatus | string;
  summary?: string;
  hint?: string;
  lane?: string;
  started_at?: ISODate;
  finished_at?: ISODate;
}

export interface PipelineEdge {
  source: string;
  target: string;
}

export interface Interrupt {
  pending: boolean;
  resuming?: boolean;
  kind?: string;
  prompt?: string;
  options?: string[];
  verdict?: string;
  amount?: number;
  deadline?: ISODate | null;
  rule_ids?: string[];
  answer?: { action?: string; approver?: string; note?: string } | null;
  /** Zona AML: recomandarea regulilor (de ex. „RTS_PROPUS”) atașată întreruperii. */
  recommendation?: string | null;
}

export interface CaseDetail {
  summary: CaseSummary;
  complaint?: { text: string; attachments?: Attachment[]; received_at?: ISODate };
  extracted?: ExtractedClaim | null;
  classification?: Classification | null;
  facts?: Fact[];
  rules?: RulesOutcome | null;
  decisions?: Decision[];
  debate?: Debate | null;
  recovery?: Recovery | null;
  letter?: LetterDraft | null;
  pipeline?: { nodes: PipelineNode[]; edges: PipelineEdge[] } | null;
  interrupt?: Interrupt | null;
  hold?: { received: boolean; [k: string]: unknown } | null;
  ledger?: { count: number; root?: string | null; sealed: boolean } | null;
  rule_context?: Record<string, unknown> | null;
  clock?: { notified_at?: ISODate; t1_deadline?: ISODate; answer_deadline?: ISODate } | null;
  aml_referral?: { status?: string; victim_ref?: string } | null;
  decision_seconds?: number | null;
  llm_mode?: string | null;
  story?: StoryItem[];
}

export interface DecisionBrief {
  question: Question | string;
  decision: Verdict | string;
}

export interface CounterfactualResult {
  before: DecisionBrief[];
  after: DecisionBrief[];
  changed: string[];
  explanation: string;
}

export interface Seal {
  root: string;
  signature: string;
  public_key: string;
  count: number;
  sealed_at: ISODate;
  qr_svg?: string | null;
}

export interface VerifyCheck {
  name: string;
  ok: boolean;
  detail?: string;
}

export interface VerifyResult {
  valid: boolean;
  checks: VerifyCheck[];
}

export interface LedgerResponse {
  facts: Fact[];
  seal: Seal | null;
  verify: VerifyResult;
}

export interface RuleCatalogEntry {
  rule_id: string;
  title: string;
  basis: string;
  confidence: Confidence | string;
  pack: string;
  params?: Record<string, unknown> | string[] | null;
}

export type ParamValue = string | number | boolean | null;
export type RuleParams = Record<string, ParamValue | unknown>;

export interface WallLayer {
  id: string;
  name: string;
  status: "ok" | "alert" | string;
  detail?: string;
}

export interface WallBlock {
  at: ISODate;
  case_id: string;
  reasons: string[];
  terms: string[];
}

export interface WallState {
  layers: WallLayer[];
  denials: PolicyDecision[];
  blocks: WallBlock[];
  noninterference: { runs: number; leaks: number; at: ISODate | null } | null;
}

export type AttackKind = "read_aml_tool" | "letter_tipping_off" | "prompt_injection" | "diode_text_field";

export interface AttackResult {
  blocked: boolean;
  /** Backend-ul real trimite „3. Politici Cedar"; mock-ul „L3"; poate lipsi (null). */
  layer: string | number | null;
  /** Opțional: toate controalele care au participat la oprire (număr, nume sau {id, name}). */
  layers?: Array<string | number | { id?: string | number; name?: string }>;
  detail: string;
  evidence?: unknown;
}

export interface McpTool {
  name: string;
  /** „client", „aml" sau „ambele" (tool-ul e în ambele servere). */
  zone: Zone | string;
  description: string;
  effect: string;
}

export interface McpInfo {
  tools: McpTool[];
  snippets: { claude_desktop?: string; cursor?: string; http?: string } & Record<string, string | undefined>;
  http_url: string;
  zones?: Record<string, string>;
}

export interface BankTransaction {
  id: string;
  ts: ISODate;
  description: string;
  /** Mock: negativ la plăți; backend-ul real: pozitiv, cu `direction`. UI-ul folosește doar `direction`. */
  amount: number;
  direction: "in" | "out" | string;
  status: string;
  disputable: boolean;
  /** Backend-ul real: tranzacția e deja într-o contestație. */
  disputed?: boolean;
}

export interface BankNotification {
  ts: ISODate;
  text: string;
  kind: string;
}

export interface BankState {
  customer_ref?: string;
  customer_alias: string;
  balance: number;
  iban_masked: string;
  transactions: BankTransaction[];
  notifications: BankNotification[];
}

// ------------------------------------------------------------------ zona AML (§6.2)

export interface AmlStats {
  referrals: number;
  leads: number;
  rts_drafts: number;
  accounts_flagged: number;
  amount_at_risk: number | Money;
  communities: number;
}

export interface Referral {
  case_id: string;
  received_at: ISODate;
  amount: number | Money;
  beneficiary_iban_masked: string;
  scenario: Scenario | string | null;
  lead_id: string | null;
}

export interface LeadSummary {
  lead_id: string;
  case_ids: string[];
  top_score: number;
  typologies: string[];
  recommendation: Verdict | string;
  status: string;
  updated_at: ISODate;
}

export type GraphNodeKind = "victima" | "carausi" | "exchange" | "comerciant" | "cont" | "numerar";

export interface GraphNode {
  id: string;
  label: string;
  kind: GraphNodeKind | string;
  score: number | null;
  community: number | null;
  amount_in: number;
  amount_out: number;
  flagged: boolean;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  amount: number;
  ts: ISODate;
  case_id: string | null;
  kind: string;
}

export interface MoneyGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

/** O tipologie găsită de `detect_typologies` (versoml/ml/m5_mule.py), cu explicația în română. */
export interface TypologyHit {
  typology?: string;
  name?: string;
  rule_id?: string;
  center?: string | null;
  accounts?: string[];
  amount?: number | null;
  start?: ISODate | null;
  end?: ISODate | null;
  explanation?: string;
  [k: string]: unknown;
}

/** O ipoteză nevinovată a Avocatului nevinovăției, cu probele pentru și contra (stil ACH). */
export interface InnocentHypothesis {
  hypothesis: string;
  supports?: string[];
  against?: string[];
  check?: string | null;
}

export interface LeadDetail {
  lead: AmlLead;
  graph: MoneyGraph;
  osint: OsintFinding[];
  innocent: RationaleLine[];
  rts: {
    fields: Record<string, unknown>;
    narrative: RationaleLine[];
    status: string;
    title?: string;
    rejected_without_citation?: number;
    canary_planted?: boolean;
  } | null;
  clocks: Deadline[];
  timeline: AgentEvent[];
  // câmpuri trimise de backend-ul real (versoml/zone_aml/service.py → lead_detail); modul mock le poate omite
  status?: string | null;
  osint_summary?: string | null;
  innocent_detail?: InnocentHypothesis[];
  typologies_detail?: TypologyHit[];
  pipeline?: { nodes: PipelineNode[]; edges: PipelineEdge[] } | null;
  interrupt?: Interrupt | null;
  ledger?: { count?: number | null; root?: string | null; sealed?: boolean } | null;
  facts?: Fact[];
}

export type LeadAction = "file_rts" | "close" | "request_info" | "hold_client";

export type OsintKind = "auto" | "domain" | "url" | "phone" | "cui" | "iban" | "company";

export interface OsintResult {
  findings: OsintFinding[];
  raw?: Record<string, unknown>;
  artifacts?: Record<string, string[]>;
  /** Backend-ul real: politica a refuzat interogarea (findings e gol). */
  denied?: PolicyDecision | null;
}

export interface Campaign {
  campaign_id: string;
  cases: string[] | number;
  shared: { domains?: string[]; ibans?: string[]; phones?: string[] };
  amount_total: number | Money;
}
