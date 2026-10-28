"""Contractele de date comune (docs/05 §7.3 și §16).

Reguli:
- `DisputeFacts` e singurul obiect care trece zidul dinspre client spre AML.
- `HoldSignal` e singurul obiect dinspre AML spre client și nu are câmpuri de text liber.
- Toate valorile din date și teste sunt sintetice.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    """Model care respinge câmpurile necunoscute (folosit pe contractele care trec zidul)."""

    model_config = ConfigDict(extra="forbid", frozen=True)


# ---------------------------------------------------------------- etichete și probe


class Zone(str, Enum):
    CLIENT = "client"
    AML = "aml"


class Trust(str, Enum):
    TRUSTED = "trusted"      # sisteme interne ale băncii, motorul de reguli
    UNTRUSTED = "untrusted"  # textul clientului, SMS-ul escrocului, pagini web, rezultate OSINT


class Sink(str, Enum):
    """Destinațiile în care o valoare are voie să ajungă (pașaportul datelor)."""

    CLIENT = "client"        # zona client (consola de contestații)
    AML = "aml"              # zona AML
    LLM = "llm"              # un apel spre model (doar pseudonimizat)
    OSINT = "osint"          # o interogare spre surse publice (doar identificatori publici)
    LETTER = "letter"        # scrisoarea către client


class Labels(BaseModel):
    conf: Literal["client", "aml", "aml-only", "public"] = "client"
    trust: Trust = Trust.TRUSTED
    sinks: list[Sink] = Field(default_factory=lambda: [Sink.CLIENT])


class Fact(BaseModel):
    """O intrare în registrul de probe."""

    fact_id: str                      # EV-001 (zona client) sau AX-001 (zona AML)
    case_id: str
    zone: Zone
    kind: str                         # ex. "sca.auth_event", "domain.rdap", "rule.hit"
    source_tool: str                  # ex. "sca-logs.get_auth_events"
    args_hash: str                    # sha256 al argumentelor canonice
    retrieved_at: datetime
    sha256: str                       # sha256 al conținutului canonic
    prev_hash: str | None = None      # lanțul registrului
    entry_hash: str | None = None     # hash-ul intrării în lanț
    labels: Labels = Field(default_factory=Labels)
    summary: str = ""                 # o propoziție în română, pentru UI și citări
    content: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------- reclamația și clasificarea


class Channel(str, Enum):
    CARD = "card"
    TRANSFER = "transfer"
    TRANSFER_INSTANT = "transfer_instant"


class DisputeType(str, Enum):
    NEAUTORIZATA = "neautorizata"            # plată pe care clientul n-a autorizat-o (art. 173)
    APP = "app"                              # clientul a autorizat-o, păcălit (authorised push payment)
    DISPUTA_COMERCIANT = "disputa_comerciant"
    EROARE_PROCESARE = "eroare_procesare"    # ex. plată dublă


class Scenario(str, Enum):
    PHISHING_LINK = "phishing_link"                  # transfer după link fals (curier/OLX)
    CARD_ECOM_FARA_3DS = "card_ecom_fara_3ds"        # ECI 7
    CARD_VISA_SECURE = "card_visa_secure"            # ECI 5 + CAVV, aprobat în aplicație
    VISHING_SECURITATE = "vishing_securitate"        # „departamentul de securitate”, clientul aprobă
    CONT_SIGUR = "cont_sigur"                        # „mută banii într-un cont sigur”
    SIM_SWAP = "sim_swap"
    FRAUDA_CLIENT = "frauda_client"                  # clientul contestă o plată proprie
    RECLAMATIE_TARDIVA = "reclamatie_tardiva"        # după 13 luni
    PLATA_DUBLA = "plata_dubla"
    INEL_CARAUSI = "inel_carausi"                    # mai multe victime, același IBAN
    INJECTIE_DOCUMENT = "injectie_document"          # instrucțiuni ascunse în reclamație
    MARFA_NELIVRATA = "marfa_nelivrata"              # dispută comerciant


class Money(BaseModel):
    value: float
    currency: str = "RON"


class Attachment(BaseModel):
    kind: Literal["sms", "email", "pdf_text", "screenshot_text", "call_transcript", "chat"]
    content: str
    name: str | None = None


class Complaint(BaseModel):
    """Contestația, așa cum intră în bancă (text neîncrezut).

    `customer_ref` și `transaction_refs` pot lipsi (reclamație liberă, de exemplu pe e-mail): nodul `identificare`
    caută clientul și plata în evidențele băncii.
    """

    case_id: str
    customer_ref: str | None = None
    received_at: datetime
    channel_hint: Channel | None = None
    transaction_refs: list[str] = Field(default_factory=list)
    text: str
    attachments: list[Attachment] = Field(default_factory=list)
    source: Literal["app", "email", "branch", "call_center", "web_form"] = "app"
    synthetic: bool = True


class MatchCandidate(BaseModel):
    """O plată din evidențele clientului care s-ar putea potrivi cu reclamația (scor determinist, 0–1)."""

    tx_id: str
    amount: float
    currency: str = "RON"
    ts: datetime | str
    payee: str | None = None
    channel: str | None = None
    direction: str = "out"
    score: float = 0.0
    points: int = 0                   # punctajul brut din care vine scorul (transparent)
    reasons: list[str] = Field(default_factory=list)


class MatchResult(BaseModel):
    """Rezultatul identificării: clientul, plata contestată și de ce (sau de ce e nevoie de un om)."""

    customer_ref: str | None = None
    customer_match_reason: str | None = None
    customer_confidence: float = 0.0
    tx_id: str | None = None
    confidence: float = 0.0
    needs_human: bool = True
    reason: str = ""
    method: Literal["given", "matched", "picked", "none"] = "none"
    candidates: list[MatchCandidate] = Field(default_factory=list)


class ClaimPoint(BaseModel):
    """Un punct din reclamație la care scrisoarea trebuie să răspundă (CMP)."""

    text: str
    quote: str = ""          # citatul exact din reclamație


class ExtractedClaim(BaseModel):
    """Ce scoate LLM-ul izolat din textul neîncrezut. Doar câmpuri tipizate."""

    claims_unauthorized: bool | None = None
    client_admits_sharing_credentials: bool | None = None
    client_admits_approving_in_app: bool | None = None
    noticed_at: datetime | None = None
    contacted_by: Literal["sms", "apel", "email", "mesagerie", "site", "necunoscut"] | None = None
    impersonated_entity: str | None = None        # ex. „curier”, „banca”, „poliția”
    mentioned_urls: list[str] = Field(default_factory=list)
    mentioned_phones: list[str] = Field(default_factory=list)
    mentioned_amounts: list[float] = Field(default_factory=list)
    requested_remedy: str | None = None
    points: list[ClaimPoint] = Field(default_factory=list)
    injection_suspected: bool = False             # textul conține instrucțiuni către sistem
    language: str = "ro"


class Classification(BaseModel):
    channel: Channel
    dispute_type: DisputeType
    scenario: Scenario | None = None
    probability: float = 0.0
    proba: dict[str, float] = Field(default_factory=dict)
    ambiguous: bool = False
    model_version: str = ""
    method: Literal["ml", "llm", "ml+llm", "rules"] = "ml"


# ---------------------------------------------------------------- reguli și decizii


class Confidence(str, Enum):
    P = "P"   # citit în textul oficial
    S = "S"   # sursă secundară
    U = "U"   # neverificat: parametru configurabil
    V = "V"   # verificat în sesiunea de research


class Deadline(BaseModel):
    rule_id: str
    name: str
    due_at: datetime
    basis: str
    business_days: bool = True


class RuleHit(BaseModel):
    rule_id: str
    version: str = "1"
    title: str
    basis: str                     # temeiul legal sau contractual
    confidence: Confidence = Confidence.P
    outcome: str                   # ce a decis regula
    explanation: str = ""          # în română, pentru scrisoare și UI
    inputs: list[str] = Field(default_factory=list)     # fact_id-urile folosite
    params: dict[str, Any] = Field(default_factory=dict)


class Question(str, Enum):
    RAMBURSARE_T1 = "rambursare_t1"
    RECUPERARE_CLIENT = "recuperare_client"     # dosar de neglijență gravă
    RECUPERARE_ESCROC = "recuperare_escroc"     # rechemare, chargeback, DNSC
    RASPUNS_RECLAMATIE = "raspuns_reclamatie"
    PISTA_AML = "pista_aml"
    RTS = "rts"


class Verdict(str, Enum):
    RAMBURSEAZA = "RAMBURSEAZA"                         # sub plafon, fără semnale: motorul emite instrucțiunea
    RAMBURSEAZA_CU_APROBARE = "RAMBURSEAZA_CU_APROBARE"  # peste plafon sau cu semnale: un om confirmă, tot în termen
    EXCEPTIE_FRAUDA_CLIENT = "EXCEPTIE_FRAUDA_CLIENT"   # doar cu HoldSignal aprobat și autoritatea notificată
    RESPINGE_TARDIV = "RESPINGE_TARDIV"                 # peste 13 luni (art. 169)
    NU_SE_APLICA_T1 = "NU_SE_APLICA_T1"                 # APP sau dispută comerciant: alt traseu
    CHARGEBACK = "CHARGEBACK"
    RECHEMARE = "RECHEMARE"
    RECUPERARE_PROPUSA = "RECUPERARE_PROPUSA"
    NU_RECOMANDAM_RECUPERARE = "NU_RECOMANDAM_RECUPERARE"
    INFORMATII_SUPLIMENTARE = "INFORMATII_SUPLIMENTARE"
    RTS_PROPUS = "RTS_PROPUS"
    MONITORIZARE = "MONITORIZARE"
    INCHIDE = "INCHIDE"


class RationaleLine(BaseModel):
    text: str
    cites: list[str] = Field(default_factory=list)


class Decision(BaseModel):
    """Contractul de ieșire al oricărei decizii (docs/05 §7.3)."""

    case_id: str
    question: Question
    decision: Verdict
    rule_ids: list[str] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    rationale: list[RationaleLine] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    requires_human: bool = False
    deadline: datetime | None = None
    amount: Money | None = None
    decided_by: Literal["rules", "human", "rules+human"] = "rules"


class RuleContext(BaseModel):
    """Intrarea deterministă a motorului de reguli: doar fapte, fără text liber."""

    case_id: str
    now: datetime
    channel: Channel
    dispute_type: DisputeType
    scenario: Scenario | None = None
    amount: Money
    executed_at: datetime
    notified_at: datetime                         # când a anunțat clientul banca
    # autentificare și context tehnic (din jurnalele băncii, nu din reclamație)
    sca_performed: bool | None = None
    sca_method: str | None = None                 # ex. "app_push", "sms_otp", "none"
    eci: str | None = None                        # card: "05", "07" etc.
    cavv_present: bool | None = None
    screen_showed_amount_and_payee: bool | None = None   # dynamic linking afișat
    device_known: bool | None = None
    seconds_after_click: int | None = None
    sim_swap_hours_before: float | None = None
    beneficiary_new: bool | None = None
    merchant_mcc: str | None = None
    duplicate_of: str | None = None               # tranzacția identică, la plata dublă
    prior_disputes_12m: int = 0
    client_fraud_score: float | None = None       # M2: doar semnal pentru om
    client_admits_sharing_credentials: bool | None = None
    client_admits_approving_in_app: bool | None = None
    # semnalul din zona AML (singurul canal permis)
    hold_signal: bool = False
    hold_authority_notified: bool = False
    fact_ids: dict[str, str] = Field(default_factory=dict)   # câmp -> fact_id, pentru citări


class RulesOutcome(BaseModel):
    case_id: str
    decisions: list[Decision] = Field(default_factory=list)
    hits: list[RuleHit] = Field(default_factory=list)
    deadlines: list[Deadline] = Field(default_factory=list)
    params_used: dict[str, Any] = Field(default_factory=dict)
    engine_version: str = "1"


# ---------------------------------------------------------------- zidul


class BeneficiaryRef(Strict):
    iban: str | None = None
    name: str | None = None
    cui: str | None = None
    bank_bic: str | None = None


class AttackRef(Strict):
    domain: str | None = None
    url: str | None = None
    phone: str | None = None
    domain_age_hours: float | None = None
    lookalike_score: float | None = None


class DisputeFacts(Strict):
    """Singurul obiect care trece zidul spre AML. Fără date de identificare ale victimei."""

    case_id: str
    victim_ref: str                 # pseudonim (VCT-xxxx), nu ID-ul de client
    channel: Channel
    dispute_type: DisputeType
    scenario: Scenario | None = None
    amount: Money
    executed_at: datetime
    beneficiary: BeneficiaryRef
    attack: AttackRef = AttackRef()
    fact_ids: list[str] = Field(default_factory=list)


class HoldSignal(Strict):
    """Singurul obiect dinspre AML spre client. Un boolean, fără text liber."""

    case_id: str
    hold: bool
    approved_by: str                # ID-ul analistului (ex. ANALIST-07)
    approved_at: datetime
    authority_notified: bool = False


class PolicyDecision(BaseModel):
    allowed: bool
    principal: str
    action: str
    resource: str
    reason: str = ""
    policy_ids: list[str] = Field(default_factory=list)
    at: datetime | None = None
    engine: str | None = None        # "cedar" sau rezerva Python
    case_id: str | None = None


class FilterResult(BaseModel):
    passed: bool
    blocked_terms: list[str] = Field(default_factory=list)
    canaries_found: int = 0
    classifier_flag: bool = False
    pii_findings: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    term_spans: list[dict[str, Any]] = Field(default_factory=list)   # {start, end, label}, pentru evidențiere în UI


class LetterDraft(BaseModel):
    case_id: str
    subject: str
    body: str
    cites: list[str] = Field(default_factory=list)
    points_answered: list[str] = Field(default_factory=list)
    filter: FilterResult | None = None
    status: Literal["draft", "blocked", "approved", "sent"] = "draft"


# ---------------------------------------------------------------- zona AML


class AccountScore(BaseModel):
    account: str                     # IBAN sintetic sau referință internă
    score: float
    label: Literal["carausi_probabil", "de_verificat", "normal"] = "de_verificat"
    top_features: list[tuple[str, float]] = Field(default_factory=list)
    community: int | None = None


class OsintFinding(BaseModel):
    tool: str
    target: str
    ok: bool
    summary: str
    signal: Literal["rosu", "galben", "verde", "neutru"] = "neutru"
    fact_id: str | None = None
    source_url: str | None = None
    mode: Literal["live", "fixture", "cache", "offline"] = "fixture"


class AmlLead(BaseModel):
    lead_id: str
    case_ids: list[str]
    accounts: list[AccountScore] = Field(default_factory=list)
    typologies: list[str] = Field(default_factory=list)
    osint: list[OsintFinding] = Field(default_factory=list)
    innocent_hypotheses: list[RationaleLine] = Field(default_factory=list)
    recommendation: Verdict = Verdict.MONITORIZARE
    rts_draft_id: str | None = None
    canary: str | None = None        # tokenul plantat în dosar (pentru testul zidului)


# ---------------------------------------------------------------- evenimente (format AG-UI)


class EventType(str, Enum):
    RUN_STARTED = "RUN_STARTED"
    RUN_FINISHED = "RUN_FINISHED"
    RUN_ERROR = "RUN_ERROR"
    STEP_STARTED = "STEP_STARTED"
    STEP_FINISHED = "STEP_FINISHED"
    TEXT_MESSAGE_START = "TEXT_MESSAGE_START"
    TEXT_MESSAGE_CONTENT = "TEXT_MESSAGE_CONTENT"
    TEXT_MESSAGE_END = "TEXT_MESSAGE_END"
    TOOL_CALL_START = "TOOL_CALL_START"
    TOOL_CALL_END = "TOOL_CALL_END"
    STATE_DELTA = "STATE_DELTA"
    CUSTOM = "CUSTOM"                 # name: fact | rule_hit | decision | policy_denied | wall_block | interrupt | ledger_seal | hold_signal


class AgentEvent(BaseModel):
    type: EventType
    zone: Zone
    run_id: str
    case_id: str
    seq: int = 0
    ts: datetime
    step: str | None = None           # nodul din graf, ex. "colector.sca"
    agent: str | None = None          # ex. "Judecătorul/Receptor"
    name: str | None = None           # pentru CUSTOM
    message: str | None = None        # o propoziție în română, pentru trace
    data: dict[str, Any] = Field(default_factory=dict)
