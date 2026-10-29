"""Pachetul DSP: dispute card, scheme Visa/Mastercard și procesul emitentului (docs/context/14).

Valorile [P] din Visa Core Rules (18.04.2026) sunt constante aici, cu sursa lângă ele. Valorile [U] și
termenele Mastercard (în conflict între surse) sunt parametri. Ordinea regulilor contează doar pentru lista
de hit-uri: DSP-52 (flagul de recuperabilitate) apare înaintea celorlalte reguli de schemă.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from pydantic import BaseModel, Field

from versoml.contracts import Confidence, Deadline, DisputeType, Question

from ..calendar_ro import end_of_day, local_date, to_local
from ..context import GuardResult, RuleContextExt
from ..facts import (
    Env, card_present, card_scheme, fmt_d, fmt_dt, fmt_money, fmt_num, is_card, is_unauthorised, processing_date,
    refund_anchor, refund_due, refund_track, refund_withheld, risk_signals, to_ron, visa_condition,
)
from ..registry import Finding, rule

P, S, U = Confidence.P, Confidence.S, Confidence.U
SRC = "docs/context/14"
Q_T1, Q_CLIENT, Q_ESCROC, Q_ANSWER = (Question.RAMBURSARE_T1, Question.RECUPERARE_CLIENT,
                                      Question.RECUPERARE_ESCROC, Question.RASPUNS_RECLAMATIE)

# ---------------------------------------------------------------- constante Visa (Core Rules 18.04.2026) [P]

VISA_CONDITIONS: dict[str, str] = {          # docs/context/14 §5.1, denumirile din Core Rules
    "10.1": "EMV Liability Shift Counterfeit", "10.2": "EMV Liability Shift Non-Counterfeit",
    "10.3": "Other Fraud – Card-Present", "10.4": "Other Fraud – Card-Absent",
    "10.5": "Visa Fraud Monitoring Program",
    "11.1": "Card Recovery Bulletin", "11.2": "Declined Authorization", "11.3": "No Authorization/Late Presentment",
    "12.2": "Incorrect Transaction Code", "12.3": "Incorrect Currency", "12.4": "Incorrect Account Number",
    "12.5": "Incorrect Amount", "12.6": "Duplicate Processing/Paid by Other Means", "12.7": "Invalid Data",
    "13.1": "Merchandise/Services Not Received", "13.2": "Cancelled Recurring", "13.3": "Not as Described/Defective",
    "13.4": "Counterfeit Merchandise", "13.5": "Misrepresentation", "13.6": "Credit Not Processed",
    "13.7": "Cancelled Merchandise/Services", "13.8": "Original Credit Transaction Not Accepted",
    "13.9": "Non-Receipt of Cash at an ATM",
}
# Subcodurile 12.6.x nu sunt în docs/context: cerute de produs, marcate [U] (de verificat în Core Rules).
VISA_SUBCONDITIONS: dict[str, tuple[str, str]] = {"12.6.1": ("12.6", "Duplicate Processing"),
                                                   "12.6.2": ("12.6", "Paid by Other Means")}
VISA_104_OPEN_DAYS = 120          # Table 11-29 [P]
VISA_131_OPEN_DAYS = 120          # Table 11-92 [P]
VISA_131_CAP_DAYS = 540           # Table 11-92 [P]
VISA_131_WAIT_DAYS = 15           # Table 11-92 [P]; ancora [U]
VISA_104_DISPUTE_CAP = 35         # Table 11-28 [P]; ce se numără [U]
VISA_FRAUD_RPT_TXN_DAYS = 60      # §1.9.4.3 [P]
VISA_FRAUD_RPT_NOTICE_DAYS = 30   # §1.9.4.3 [P]; lectura [U]
CE3_V2026_FROM = date(2026, 10, 24)   # CE3.0 cu mai mulți comercianți; device ID + fingerprint = un element
MC_CODES = {DisputeType.NEAUTORIZATA: "4837", DisputeType.DISPUTA_COMERCIANT: "4853",
            DisputeType.EROARE_PROCESARE: "4834"}   # DSP-40 [S]

# Etapele Visa: (zile, ancora, marcaj). Table 11-1 (alocare, 10–11) și 11-2 (colaborare, 12–13).
VISA_STAGES: dict[str, dict[str, tuple[int, str, Confidence]]] = {
    "alocare": {
        "prearbitraj_acquirer": (30, "dispute processing date", P),
        "raspuns_emitent_prearbitraj": (30, "pre-arbitration (unit not stated)", U),
        "arbitraj_acquirer": (10, "pre-arbitration response", P),
    },
    "colaborare": {
        "raspuns_disputa_acquirer": (30, "dispute (unit not stated)", U),
        "prearbitraj_emitent": (30, "Dispute Response (unit not stated)", U),
        "raspuns_acquirer_prearbitraj": (30, "pre-arbitration (unit not stated)", U),
        "arbitraj_emitent": (10, "acquirer response (unit not stated)", U),
    },
}


def is_valid_condition(code: str) -> bool:
    return code in VISA_CONDITIONS or code in VISA_SUBCONDITIONS


def condition_name(code: str) -> str:
    if code in VISA_SUBCONDITIONS:
        return VISA_SUBCONDITIONS[code][1]
    return VISA_CONDITIONS.get(code, "?")


def _eci(x: RuleContextExt) -> str | None:
    return x.eci.strip().zfill(2) if x.eci else None


def classification_ambiguous(x: RuleContextExt, env: Env) -> bool:
    return bool(x.classification_ambiguous or env.flags.get("classification_ambiguous"))


# ---------------------------------------------------------------- calculatoare de schemă


@rule("DSP-22", title="The processing day of the previous event does not count", basis="Visa Core Rules §11.2.1",
      confidence=P, pack="DSP", source=f"{SRC} §5.2", kind="calculator", tests=("DT-01", "DT-09", "DT-13"))
def visa_due(anchor: date, days: int) -> date:
    """Visa deadline: the anchor plus n calendar days (the anchor day does not count)."""
    return anchor + timedelta(days=days)


@rule("DSP-23", title="No action by the deadline closes the cycle; alert before the deadline",
      basis="Visa Core Rules §11.2.1", confidence=P, pack="DSP", source=f"{SRC} §5.2", kind="calculator",
      params=("scheme_alert_lead_days",), exceptions=("DSP_SCHEME_DEADLINE_AT_RISK",), tests=("DT-14",))
def scheme_deadline_status(due: date, as_of: datetime | date, lead_days: int) -> tuple[str, int]:
    """Status of a scheme deadline: (code, days left). Missing the deadline means an automatic loss."""
    left = (due - local_date(as_of)).days
    if left < 0:
        return "termen_expirat", left
    if left <= lead_days:
        return "DSP_SCHEME_DEADLINE_AT_RISK", left
    return "in_termen", left


@rule("DSP-33", title="Categories 10–11: acquirer pre-arbitration, issuer response, arbitration",
      basis="Visa Core Rules Table 11-1", confidence=P, pack="DSP", source=f"{SRC} §5.2", kind="calculator",
      exceptions=("DSP_SCHEME_DEADLINE_AT_RISK",), tests=("DT-13", "DT-14"))
def visa_allocation_stage_due(stage: str, anchor: date) -> tuple[date, Confidence]:
    """Deadline for a stage of the allocation flow (fraud, authorization). One unit is not stated [U]."""
    days, _, conf = VISA_STAGES["alocare"][stage]
    return visa_due(anchor, days), conf


@rule("DSP-34", title="Categories 12–13: Dispute Response, issuer pre-arbitration, response, arbitration",
      basis="Visa Core Rules Table 11-2", confidence=P, pack="DSP", source=f"{SRC} §5.2", kind="calculator",
      exceptions=("DSP_SCHEME_DEADLINE_AT_RISK",), tests=("DT-09",))
def visa_collaboration_stage_due(stage: str, anchor: date) -> tuple[date, Confidence]:
    """Deadline for a stage of the collaboration flow (processing errors, consumer disputes). Units are [U]."""
    days, _, conf = VISA_STAGES["colaborare"][stage]
    return visa_due(anchor, days), conf


def visa_fraud_report_due(txn_on: date, notified_on: date, mode: str | None) -> tuple[date, bool]:
    """DSP-25: (termen, lecturi concordante). 60 de zile de la tranzacție / 30 de la notificare, dacă vine
    mai târziu; lectura e [U]. Fără mod setat: dacă lecturile diferă, data mai devreme."""
    d60 = txn_on + timedelta(days=VISA_FRAUD_RPT_TXN_DAYS)
    d30 = notified_on + timedelta(days=VISA_FRAUD_RPT_NOTICE_DAYS)
    by_max = max(d60, d30)
    by_after = d30 if notified_on > d60 else d60
    if mode == "max":
        return by_max, True
    if mode == "after_day_60":
        return by_after, True
    return (by_max, True) if by_max == by_after else (min(by_max, by_after), False)


@dataclass(frozen=True)
class DisputeWindow:
    condition: str
    due: date
    earliest: date | None
    verified: bool
    anchor_known: bool
    expired: bool


def visa_dispute_window(x: RuleContextExt, env: Env) -> DisputeWindow | None:
    """Termenul emitentului pentru condiția Visa a cazului (DSP-24, §5.4)."""
    cond = visa_condition(x)
    if cond is None or not is_valid_condition(cond):
        return None
    proc, known = processing_date(x)
    earliest = None
    if cond == "10.4":
        due, verified = visa_due(proc, VISA_104_OPEN_DAYS), True
    elif cond == "13.1":
        base = max(proc, x.expected_delivery_date) if x.expected_delivery_date else proc
        due, verified = min(visa_due(base, VISA_131_OPEN_DAYS), visa_due(proc, VISA_131_CAP_DAYS)), True
        if x.expected_delivery_date is None:
            anchor = proc if env.p("visa_131_wait_anchor") == "processing_date" else local_date(x.executed_at)
            earliest = visa_due(anchor, VISA_131_WAIT_DAYS)
    else:
        due, verified = visa_due(proc, env.p("visa_other_open_days")), False
    return DisputeWindow(cond, due, earliest, verified, known, local_date(x.now) > due)


def chargeback_recoverable(x: RuleContextExt, env: Env) -> tuple[str, list[str], str | None]:
    """Flagul DSP-52 (docs/context/14 §6.1): (DA / NU / INCERT, regulile care au decis, codul de motiv).
    Ordinea testelor e fixă; fiecare NU sau INCERT citează regula care a decis."""
    if x.existing_dispute_for_txn:
        return "NU", ["DSP-21"], None
    if x.purchase_type == "crypto_nft" and x.cardholder_participated:
        return "NU", ["DSP-29"], None
    if x.dispute_type == DisputeType.APP:
        return "NU", ["PAY-12"], None
    if x.preauth_release_late:
        return "NU", ["PAY-09"], None
    if card_scheme(x, env) == "mastercard":
        return "INCERT", ["DSP-42", "DSP-43"], MC_CODES.get(x.dispute_type)
    cond = visa_condition(x)
    if cond is not None and not is_valid_condition(cond):
        return "INCERT", ["DSP-20"], cond
    if is_unauthorised(x):
        if card_present(x) is not False:
            return "INCERT", ["DSP-52"], None
        window = visa_dispute_window(x, env)
        if window and window.expired:
            return "NU", ["DSP-24"], "10.4"
        if x.prior_disputes_120d is not None and x.prior_disputes_120d > VISA_104_DISPUTE_CAP:
            return "NU", ["DSP-26"], "10.4"
        if x.prior_disputes_120d is None and x.prior_disputes_12m > VISA_104_DISPUTE_CAP:
            return "INCERT", ["DSP-26"], "10.4"
        if _eci(x) == "05" and x.cavv_present is True and x.visa_secure_auth_confirmation is not False:
            return "NU", ["DSP-27"], "10.4"
        if x.wallet_token and x.tavv_present and x.cvm_approved:
            return "NU", ["DSP-28"], "10.4"
        if x.ce3_met:
            return "NU", ["DSP-30"], "10.4"
        if _eci(x) == "06":
            return "INCERT", ["DSP-31"], "10.4"
        return "DA", [], "10.4"
    if cond is None:
        return "INCERT", ["DSP-20"], None
    window = visa_dispute_window(x, env)
    if window and window.expired:
        return "NU", ["DSP-24"], cond
    blocking = []
    if window and not window.verified:
        blocking.append("DSP-24")
    if cond.startswith("13.") and cond != "13.9" and x.merchant_contact_proof is not True:
        blocking.append("DSP-53")
    return ("INCERT" if blocking else "DA"), blocking, cond


# ---------------------------------------------------------------- pista A: rambursarea (proces)


@rule("DSP-58", title="The refund deadline runs from the earlier of the bank noting the fraud and the customer reporting it",
      basis="Law 209/2019, art. 173 (“after noting or being notified”); inference from the notes", confidence=U,
      pack="DSP", source=f"{SRC} §7.4", questions=(Q_T1,), params=("refund_anchor_mode",), tests=("DT-19",))
def dsp_58_refund_anchor(x: RuleContextExt, env: Env) -> Finding | None:
    """The refund clock starts at the earlier of the fraud team's confirmation (not an alert) and the customer's
    report. This reading is an inference [U], so the anchor mode is a parameter."""
    if x.bank_noted_at is None or not refund_track(x):
        return None
    anchor, source = refund_anchor(x, env.p("refund_anchor_mode"))
    if source == "constatare":
        text = (f"The refund clock starts when the bank noted the fraud ({fmt_dt(anchor)}), before the customer "
                f"reported it ({fmt_dt(x.notified_at)}).")
    else:
        text = f"The refund clock starts when the customer reported the payment ({fmt_dt(anchor)})."
    return Finding("DSP-58", f"ancora_{source}", text, ("bank_noted_at", "notified_at"),
                   data={"anchor": anchor, "source": source})


@rule("DSP-03", title="Refund clock: at-risk alert and breach",
      basis="Law 209/2019, art. 173–174; CJEU ruling C-70/25", confidence=P, pack="DSP", source=f"{SRC} §3",
      questions=(Q_T1,), params=("refund_sla_alert_hours", "refund_end_of_day"),
      exceptions=("DSP_REFUND_SLA_AT_RISK", "DSP_REFUND_SLA_BREACHED"), tests=("DT-07", "DT-19"))
def dsp_03_refund_sla(x: RuleContextExt, env: Env) -> Finding | None:
    """The refund deadline is tracked from the DSP-58 anchor. If it has already passed at intake (for example, a
    paper letter registered late), the bank refunds immediately and escalates. The alert threshold in hours is
    a [U] parameter."""
    if not refund_track(x) or refund_withheld(x):
        return None
    due, now = refund_due(x, env), to_local(x.now)
    if now > due:
        return Finding("DSP-03", "DSP_REFUND_SLA_BREACHED",
                       f"The refund deadline ({fmt_dt(due)}) had already passed when the case was reviewed "
                       f"({fmt_dt(now)}). The bank refunds now and escalates.", ("notified_at",), data={"due": due})
    hours = (due - now).total_seconds() / 3600
    if hours <= env.p("refund_sla_alert_hours"):
        return Finding("DSP-03", "DSP_REFUND_SLA_AT_RISK",
                       f"The refund deadline ({fmt_dt(due)}) is {fmt_num(hours, 1)} hours away. The case has priority.",
                       ("notified_at",), data={"due": due})
    return None


@rule("DSP-50", title="Who completed the SCA step: authentication signals and ambiguity go to a human",
      basis="Law 209/2019, art. 171–172; inference from the notes", confidence=U, pack="DSP", source=f"{SRC} §7.4",
      questions=(Q_T1,), exceptions=("DSP_AUTH_AMBIGUOUS",), tests=("DT-02", "DT-03"))
def dsp_50_auth_signals(x: RuleContextExt, env: Env) -> Finding | None:
    """The engine records who completed the SCA step and how. A new device, a SIM swap and a payment right
    after a link click suggest the customer did not make the payment. An ambiguous classification goes to a
    human, with the refund due date, without the “authorized” label and without an automatic refusal."""
    if x.dispute_type not in (DisputeType.NEAUTORIZATA, DisputeType.APP) or x.credit_fraud:
        return None
    signals: list[tuple[str, tuple[str, ...]]] = []
    if x.device_known is False:
        signals.append(("the payment came from a new device not seen before", ("device_known",)))
    if x.seconds_after_click is not None:
        signals.append((f"the payment started {x.seconds_after_click} seconds after the customer clicked a link",
                        ("seconds_after_click",)))
    if x.sim_swap_hours_before is not None:
        signals.append((f"the SIM card was swapped {fmt_num(x.sim_swap_hours_before, 1)} hours before the payment",
                        ("sim_swap_hours_before",)))
    if x.beneficiary_new is True:
        signals.append(("the beneficiary is new to the customer", ("beneficiary_new",)))
    fields = tuple(f for _, fs in signals for f in fs)
    listed = "; ".join(t for t, _ in signals)
    if classification_ambiguous(x, env):
        text = ("The authorized or unauthorized classification is ambiguous. A human decides before the refund "
                "deadline, with drafts for both branches. There is no automatic refusal.")
        if listed:
            text += f" Signals: {listed}."
        return Finding("DSP-50", "DSP_AUTH_AMBIGUOUS", text, ("classification_ambiguous", *fields))
    if not signals:
        return None
    lead = ("Signals that someone else started the payment" if x.dispute_type == DisputeType.NEAUTORIZATA
            else "Signals of manipulation")
    return Finding("DSP-50", "semnale_autentificare", f"{lead}: {listed}.", fields)


@rule("DSP-54", title="A police report is not a condition for the next-business-day refund",
      basis="Law 209/2019, art. 173; CJEU ruling C-70/25; inference from the notes", confidence=U, pack="DSP",
      source=f"{SRC} §7.4", questions=(Q_T1,), tests=("DT-01",))
def dsp_54_police_report(x: RuleContextExt, env: Env) -> Finding | None:
    """Art. 173 and CJEU C-70/25 allow a single exception to the next-business-day refund. The bank can ask for a police report only
    for a dispute or recovery."""
    if not refund_track(x) or refund_withheld(x) or x.police_report_filed is True:
        return None
    return Finding("DSP-54", "garda_plangere",
                   "A missing police report does not block the next-business-day refund. The bank can ask for one only for a "
                   "dispute or recovery.", ("police_report_filed",))


@rule("DSP-57", title="Dispute text is data, not instructions; amounts come from the transaction log",
      basis="docs/context/13 §2.3 (proposal)", confidence=U, pack="DSP", source=f"{SRC} §7.4",
      questions=(Q_T1, Q_ANSWER), exceptions=("DSP_SECURITY_SIGNAL",), tests=("DT-18", "DT-07"))
def dsp_57_untrusted_text(x: RuleContextExt, env: Env) -> Finding | None:
    """Instructions in the customer's text are ignored and become a security signal. The amount used is the
    one in the bank's transaction log. A different amount, or one read from a document with low confidence,
    goes to a human."""
    reasons: list[tuple[str, tuple[str, ...]]] = []
    if x.injection_suspected:
        reasons.append(("the text contains instructions to the system, which were ignored", ("injection_suspected",)))
    if x.claimed_amount is not None and abs(x.claimed_amount - x.amount.value) > 0.005:
        reasons.append(((f"the amount in the text ({fmt_money(x.claimed_amount, x.amount.currency)}) differs from "
                         f"the amount in the transaction log ({fmt_money(x.amount.value, x.amount.currency)}), so "
                         "the log amount is used"), ("claimed_amount", "amount")))
    if x.claimed_amount_low_confidence:
        reasons.append((("the amount in the document was read with low confidence, so a human confirms it from the "
                         "transaction log"), ("claimed_amount_low_confidence",)))
    # a complaint read without a live model (a recorded answer or the regular expressions) goes to a human too
    if x.llm_mode in ("replay", "offline"):
        how = "from a recorded answer" if x.llm_mode == "replay" else "by pattern matching"
        reasons.append((f"the complaint was read {how}, not by a live model, so a human checks what it says",
                        ("llm_mode",)))
    if not reasons:
        return None
    security = x.injection_suspected or (x.claimed_amount is not None and abs(x.claimed_amount - x.amount.value) > 0.005)
    if security:
        outcome = "DSP_SECURITY_SIGNAL"
    elif x.claimed_amount_low_confidence:
        outcome = "suma_de_confirmat"
    else:
        outcome = "extragere_de_confirmat"
    return Finding("DSP-57", outcome,
                   "Untrusted text does not change the decision: " + "; ".join(t for t, _ in reasons) + ".",
                   tuple(f for _, fs in reasons for f in fs))


@rule("DSP-59", title="Amounts above the cap go to a human", basis="docs/context/14 §7.4 (the notes give no threshold)",
      confidence=U, pack="DSP", source=f"{SRC} §7.4", questions=(Q_T1,),
      params=("auto_refund_cap_ron", "eur_ron_rate"), exceptions=("DSP_AMOUNT_REVIEW",), tests=("scenarii",))
def dsp_59_amount_cap(x: RuleContextExt, env: Env) -> Finding | None:
    """Automatic refunds have a configurable cap [U]. Above the cap, a human approves, still within the refund
    deadline. The cap never delays or refuses anything."""
    if not refund_track(x) or refund_withheld(x):
        return None
    cap, rate = env.p("auto_refund_cap_ron"), env.p("eur_ron_rate")
    ron = to_ron(x.amount, rate)
    amount = fmt_money(x.amount.value, x.amount.currency)
    if ron is None:
        return Finding("DSP-59", "DSP_AMOUNT_REVIEW",
                       f"The currency {x.amount.currency} cannot be compared with the RON cap. A human approves the "
                       "refund, still within the refund deadline.", ("amount",), data={"amount_ron": None})
    if ron <= cap:
        return Finding("DSP-59", "sub_plafon",
                       f"The amount of {amount} is under the automatic refund cap ({fmt_money(cap, 'RON')}, "
                       "a bank setting).", ("amount",), data={"amount_ron": ron})
    return Finding("DSP-59", "DSP_AMOUNT_REVIEW",
                   f"The amount of {amount} is above the automatic refund cap ({fmt_money(cap, 'RON')}, "
                   "a bank setting). A human approves it, still within the refund deadline.", ("amount",),
                   data={"amount_ron": ron})


@rule("DSP-16", title="A loan or credit card in the victim's name is a credit complaint",
      basis="GEO 50/2010, art. 42", confidence=S, pack="DSP", source=f"{SRC} §3", questions=(Q_T1, Q_ANSWER),
      exceptions=("DSP_ROUTE_CREDIT_FRAUD",), tests=("DT-17",))
def dsp_16_credit_fraud(x: RuleContextExt, env: Env) -> Finding | None:
    """A loan or credit card issued in the customer's name without their request is a credit complaint
    (30-day deadline, CMP-04), with a request to the Credit Bureau to suspend reporting. It is not rejected as
    “not a card dispute”."""
    if not x.credit_fraud:
        return None
    return Finding("DSP-16", "DSP_ROUTE_CREDIT_FRAUD",
                   "A loan or credit card was issued in the customer's name without their request. This is a credit "
                   "complaint (30 days, CMP-04), with a request to the Credit Bureau to suspend reporting.",
                   ("credit_fraud",))


@rule("DSP-51", title="APP: support route, not the card dispute queue", basis="inference from the notes",
      confidence=U, pack="DSP", source=f"{SRC} §7.4", questions=(Q_ESCROC, Q_ANSWER),
      exceptions=("PAY_APP_SCAM",), tests=("DT-04",))
def dsp_51_support_route(x: RuleContextExt, env: Env) -> Finding | None:
    """An authorized push payment (APP) scam goes to the support route: investigation, a recommendation to
    file a police report, possibly rescheduling and the Credit Bureau, and an explanatory letter."""
    if x.dispute_type != DisputeType.APP:
        return None
    return Finding("DSP-51", "traseu_sprijin",
                   "Support route for an authorized push payment scam: investigation, a recommendation to file a "
                   "police report, and an explanatory letter. It does not go to the card dispute queue.",
                   ("dispute_type",))


# ---------------------------------------------------------------- pista C: chargeback


@rule("DSP-52", title="The “recoverable by chargeback” flag", basis="Visa rules (docs/context/14 §6.1); inference",
      confidence=U, pack="DSP", source=f"{SRC} §6.1", questions=(Q_ESCROC,), params=("default_card_scheme",),
      tests=("DT-01", "DT-02", "DT-06", "DT-08", "DT-11", "DT-16"))
def dsp_52_chargeback_flag(x: RuleContextExt, env: Env) -> Finding | None:
    """The flag is calculated at intake from the ECI, CAVV, token, channel, merchant and history, in the fixed
    order of §6.1: yes (DA), no (NU) or uncertain (INCERT), with the rules that decided it. It does not change
    the refund (DSP-37)."""
    if not is_card(x) or x.credit_fraud:
        return None
    value, blocking, code = chargeback_recoverable(x, env)
    scheme = card_scheme(x, env)
    label = (f"Visa {code}" if scheme == "visa" else f"Mastercard {code}") if code else "condition to be determined"
    if value == "DA":
        text = f"Recoverable by chargeback: yes ({label})."
    elif value == "NU":
        text = f"Recoverable by chargeback: no (rule {', '.join(blocking)})."
    else:
        text = (f"Recoverable by chargeback: uncertain ({label}; {', '.join(blocking)}). A human chooses the scheme "
                "route.")
    fields = ("eci", "cavv_present", "dispute_type", "duplicate_of")
    return Finding("DSP-52", f"recuperabil_{value}", text, fields,
                   data={"value": value, "blocking_rules": blocking, "reason_code": code, "scheme": scheme,
                         "hit_params": {"recuperabil": value, "reason_code": code, "blocking_rules": blocking,
                                        "scheme": scheme}})


@rule("DSP-20", title="The condition comes from Visa's closed list", basis="Visa Core Rules ch. 11", confidence=P,
      pack="DSP", source=f"{SRC} §5.2", questions=(Q_ESCROC,), exceptions=("DSP_UNKNOWN_CONDITION",),
      tests=("DT-10",))
def dsp_20_condition(x: RuleContextExt, env: Env) -> Finding | None:
    """The dispute condition comes from the closed list (§5.1), with the Core Rules names. Any other value goes
    to a human. Subcodes 12.6.1 and 12.6.2 are not in docs/context [U]."""
    if not is_card(x) or card_scheme(x, env) != "visa":
        return None
    cond = visa_condition(x)
    if cond is None:
        return None
    if not is_valid_condition(cond):
        return Finding("DSP-20", "DSP_UNKNOWN_CONDITION",
                       f"The proposed condition “{cond}” is not on Visa's closed list (Core Rules, ch. 11). A human "
                       "decides.", ("visa_condition",), data={"condition": cond})
    note = " (subcode [U], to be checked in the Core Rules)" if cond in VISA_SUBCONDITIONS else ""
    return Finding("DSP-20", "conditie_valida", f"Visa condition {cond}: {condition_name(cond)}{note}.",
                   ("visa_condition", "dispute_type", "duplicate_of"), data={"condition": cond})


@rule("DSP-21", title="Each transaction is disputed separately and only once", basis="Visa Core Rules §11.2.1",
      confidence=P, pack="DSP", source=f"{SRC} §5.2", questions=(Q_ESCROC,), exceptions=("DSP_DUPLICATE_DISPUTE",),
      tests=("DT-16",))
def dsp_21_single_dispute(x: RuleContextExt, env: Env) -> Finding | None:
    """N transactions mean N disputes. An existing dispute on a transaction blocks a second one (exception:
    10.5)."""
    if not is_card(x) or not x.existing_dispute_for_txn:
        return None
    return Finding("DSP-21", "DSP_DUPLICATE_DISPUTE",
                   "A dispute already exists for this transaction. A transaction can be disputed only once.",
                   ("existing_dispute_for_txn",))


@rule("DSP-24", title="The issuer's dispute deadline depends on the condition",
      basis="Visa Core Rules Tables 11-29 and 11-92", confidence=P, pack="DSP", source=f"{SRC} §5.4",
      questions=(Q_ESCROC,), params=("visa_other_open_days", "visa_131_wait_anchor"),
      exceptions=("PAY_CHARGEBACK_WINDOW", "DSP_DEADLINE_UNVERIFIED"), tests=("DT-01", "DT-05", "DT-09", "DT-10"))
def dsp_24_dispute_window(x: RuleContextExt, env: Env) -> Finding | None:
    """10.4: 120 days from processing. 13.1: 120 days from processing or from the last expected delivery, at
    most 540, after a 15-day wait when there is no delivery date ([U] anchor). Other conditions: “120 days for
    most” [U], so `DSP_DEADLINE_UNVERIFIED` and a human decides."""
    if not is_card(x) or card_scheme(x, env) != "visa" or x.dispute_type == DisputeType.APP:
        return None
    w = visa_dispute_window(x, env)
    if w is None:
        return None
    basis = "Visa Core Rules Table 11-29" if w.condition == "10.4" else (
        "Visa Core Rules Table 11-92" if w.condition == "13.1" else "Visa Core Rules ch. 11 [U]")
    deadlines = [Deadline(rule_id="DSP-24", name=f"Visa {w.condition} dispute deadline (issuer)",
                          due_at=end_of_day(w.due), basis=basis, business_days=False)]
    fields = ["processing_date" if w.anchor_known else "executed_at"]
    if x.expected_delivery_date:
        fields.append("expected_delivery_date")
    anchor = "" if w.anchor_known else " (no processing date, so the payment date is the conservative anchor)"
    if w.earliest:
        deadlines.append(Deadline(rule_id="DSP-24", name=f"Earliest Visa {w.condition} dispute date "
                                  "(after the 15-day wait)", due_at=end_of_day(w.earliest), basis=basis,
                                  business_days=False))
    data = {"condition": w.condition, "due": w.due, "earliest": w.earliest}
    if w.expired:
        return Finding("DSP-24", "PAY_CHARGEBACK_WINDOW",
                       f"The Visa {w.condition} dispute deadline expired on {fmt_d(w.due)}{anchor}. A chargeback is "
                       "no longer possible.", tuple(fields), data=data, deadlines=tuple(deadlines))
    if not w.verified:
        return Finding("DSP-24", "DSP_DEADLINE_UNVERIFIED",
                       f"The deadline for condition {w.condition} was not read in the Core Rules. The engine uses "
                       f"{env.p('visa_other_open_days')} days [U], until {fmt_d(w.due)}{anchor}. A human confirms "
                       "the deadline.", tuple(fields), data=data, deadlines=tuple(deadlines))
    text = f"The Visa {w.condition} dispute can be opened until {fmt_d(w.due)}{anchor}."
    if w.earliest:
        text += f" With no delivery date, the earliest date is {fmt_d(w.earliest)} (15-day wait, [U] anchor)."
    return Finding("DSP-24", "in_termen", text, tuple(fields), data=data, deadlines=tuple(deadlines))


@rule("DSP-25", title="Fraud is reported to Visa even when a dispute is not possible",
      basis="Visa Core Rules Table 11-27; §1.9.4.3", confidence=P, pack="DSP", source=f"{SRC} §5.2",
      questions=(Q_ESCROC,), params=("fraud_report_deadline_mode",), exceptions=("DSP_FRAUD_REPORT_DUE",),
      tests=("DT-01", "DT-02"))
def dsp_25_fraud_report(x: RuleContextExt, env: Env) -> Finding | None:
    """Fraud is reported through VisaNet when detected, whatever the transaction status: 60 days from the
    transaction, or 30 days from the cardholder's report if that comes later (the reading is a [U]
    parameter)."""
    if not (is_card(x) and card_scheme(x, env) == "visa" and refund_track(x)) or refund_withheld(x):
        return None
    due, agree = visa_fraud_report_due(local_date(x.executed_at), local_date(x.notified_at),
                                       env.p("fraud_report_deadline_mode"))
    text = f"The bank reports the fraud to Visa by {fmt_d(due)}, even if a dispute is not possible."
    if not agree:
        text += (" The two readings of the deadline differ. The engine picked the earlier date, and a human "
                 "confirms it (DSP_RULE_UNVERIFIED).")
    return Finding("DSP-25", "DSP_FRAUD_REPORT_DUE", text, ("executed_at", "notified_at"), data={"due": due},
                   deadlines=(Deadline(rule_id="DSP-25", name="Fraud report to Visa", due_at=end_of_day(due),
                                       basis="Visa Core Rules §1.9.4.3", business_days=False),))


def _visa_fraud_claim(x: RuleContextExt, env: Env) -> bool:
    return is_card(x) and card_scheme(x, env) == "visa" and is_unauthorised(x)


_COUNT_SCOPE_LABELS = {"toate": "all disputes", "frauda": "fraud disputes only"}


@rule("DSP-26", title="10.4 is invalid above 35 disputes in the last 120 days",
      basis="Visa Core Rules Table 11-28", confidence=P, pack="DSP", source=f"{SRC} §5.2", questions=(Q_ESCROC,),
      params=("dispute_count_scope",), exceptions=("DSP_DISPUTE_LIMIT_EXCEEDED",), tests=("DT-06",))
def dsp_26_dispute_cap(x: RuleContextExt, env: Env) -> Finding | None:
    """Above 35 disputes opened by the issuer on the account in 120 days, 10.4 is not valid. What counts is
    [U] (the `dispute_count_scope` parameter). The legal duty to refund still applies."""
    if not _visa_fraud_claim(x, env):
        return None
    scope = env.p("dispute_count_scope")
    n = x.prior_disputes_120d
    if n is None:
        if x.prior_disputes_12m > VISA_104_DISPUTE_CAP:
            return Finding("DSP-26", "DSP_RULE_UNVERIFIED",
                           f"The account has {x.prior_disputes_12m} disputes in 12 months, but the 120-day count is "
                           "missing. A human checks the limit of 35.", ("prior_disputes_12m",))
        return None
    if n > VISA_104_DISPUTE_CAP:
        return Finding("DSP-26", "DSP_DISPUTE_LIMIT_EXCEEDED",
                       f"The account has {n} disputes in the last 120 days (scope: "
                       f"{_COUNT_SCOPE_LABELS.get(scope, scope)}), above the limit of 35. Condition 10.4 is not "
                       "valid. The legal refund still applies, and the account is flagged to the fraud team.",
                       ("prior_disputes_120d",), data={"count": n})
    return Finding("DSP-26", "sub_limita",
                   f"The account has {n} disputes in the last 120 days, under the limit of 35 for 10.4.",
                   ("prior_disputes_120d",), data={"count": n})


@rule("DSP-27", title="10.4 is invalid for e-commerce authenticated with Visa Secure (ECI 05 + CAVV)",
      basis="Visa Core Rules Table 11-28", confidence=P, pack="DSP", source=f"{SRC} §5.2", questions=(Q_ESCROC,),
      exceptions=("DSP_NOT_CHARGEABLE",), tests=("DT-02", "DT-03"))
def dsp_27_visa_secure(x: RuleContextExt, env: Env) -> Finding | None:
    """E-commerce with ECI 5, Visa Secure (EMV 3DS) authentication confirmation and a CAVV in the
    authorization: 10.4 is not valid (liability shift). The next-business-day refund is still due."""
    if not _visa_fraud_claim(x, env):
        return None
    if _eci(x) == "05" and x.cavv_present is True and x.visa_secure_auth_confirmation is not False:
        return Finding("DSP-27", "DSP_NOT_CHARGEABLE",
                       "The e-commerce payment was authenticated with Visa Secure (ECI 05, CAVV in the "
                       "authorization). Condition 10.4 is not valid, so the bank bears the loss if recovery from the "
                       "customer fails. The next-business-day refund is still due.", ("eci", "cavv_present"))
    return None


@rule("DSP-28", title="10.4 is invalid for an authenticated tokenized transaction", basis="Visa Core Rules Table 11-28",
      confidence=P, pack="DSP", source=f"{SRC} §5.2", questions=(Q_ESCROC,), exceptions=("DSP_NOT_CHARGEABLE",))
def dsp_28_token(x: RuleContextExt, env: Env) -> Finding | None:
    """A token with a TAVV and an approved verification method: 10.4 is not valid."""
    if _visa_fraud_claim(x, env) and x.wallet_token and x.tavv_present and x.cvm_approved:
        return Finding("DSP-28", "DSP_NOT_CHARGEABLE",
                       "The tokenized transaction was authenticated (TAVV and an approved verification method). "
                       "Condition 10.4 is not valid.", ("wallet_token", "tavv_present", "cvm_approved"))
    return None


@rule("DSP-29", title="10.4 is invalid for crypto or NFTs bought by the cardholder",
      basis="Visa Core Rules Table 11-28", confidence=P, pack="DSP", source=f"{SRC} §5.2", questions=(Q_ESCROC, Q_T1),
      exceptions=("PAY_APP_SCAM",), tests=("DT-04",))
def dsp_29_crypto(x: RuleContextExt, env: Env) -> Finding | None:
    """The cardholder took part in buying crypto or NFTs and later says they were scammed: 10.4 is not valid,
    and the case is APP (DSP-13, DSP-51). The notes do not map MCCs to crypto [U]."""
    if is_card(x) and x.purchase_type == "crypto_nft" and x.cardholder_participated is True:
        return Finding("DSP-29", "PAY_APP_SCAM",
                       "The cardholder bought the crypto or NFT and later says they were scammed. Condition 10.4 is "
                       "not valid. The case goes to the support route.", ("purchase_type", "cardholder_participated"))
    return None


@rule("DSP-30", title="CE3.0: two earlier undisputed transactions with matching data elements",
      basis="Visa Core Rules Table 11-28; Visa guide, pp. 22–23, 78–79", confidence=P, pack="DSP",
      source=f"{SRC} §5.2", questions=(Q_ESCROC, Q_T1), exceptions=("DSP_CE3_MET", "DSP_CE3_NOT_MET"),
      tests=("DT-12", "DT-13"))
def dsp_30_ce3(x: RuleContextExt, env: Env) -> Finding | None:
    """The result of `ce3_check` on the bank's data. When CE3.0 is met, 10.4 is not valid, and the case becomes
    a possible sign of customer fraud (DSP-05): a proposed hold and a notice to the authority, with
    four-eyes."""
    if not is_card(x) or x.ce3_met is None:
        return None
    if x.ce3_met:
        return Finding("DSP-30", "DSP_CE3_MET",
                       "The CE3.0 evidence is met (two earlier undisputed transactions with matching data elements). "
                       "Condition 10.4 is not valid, and the case is a possible sign of customer fraud. A human "
                       "decides on withholding and notifying the authority (four-eyes).", ("ce3_met",))
    return Finding("DSP-30", "DSP_CE3_NOT_MET", "The CE3.0 conditions are not met.", ("ce3_met",))


@rule("DSP-31", title="ECI 06 (“attempted”): conditions not fully read", basis="Visa Core Rules Table 11-28",
      confidence=U, pack="DSP", source=f"{SRC} §5.2", questions=(Q_ESCROC,), exceptions=("DSP_RULE_UNVERIFIED",),
      tests=("DT-08",))
def dsp_31_eci06(x: RuleContextExt, env: Env) -> Finding | None:
    """ECI 6 can make 10.4 invalid, under conditions that were not fully read. The result is uncertain
    (INCERT) and a human decides."""
    if _visa_fraud_claim(x, env) and _eci(x) == "06":
        return Finding("DSP-31", "DSP_RULE_UNVERIFIED",
                       "ECI 06 (“attempted”): the rule for 10.4 was not fully read, so recoverability is uncertain "
                       "and a human decides. The refund does not change.", ("eci",))
    return None


@rule("DSP-32", title="Certifying on the cardholder's behalf only on an authenticated channel",
      basis="Visa Core Rules §11.7.1, §11.10.1", confidence=P, pack="DSP", source=f"{SRC} §5.2",
      questions=(Q_ESCROC, Q_ANSWER), exceptions=("DSP_CARDHOLDER_PROOF_MISSING",), tests=("DT-01", "DT-07"))
def dsp_32_cardholder_certification(x: RuleContextExt, env: Env) -> Finding | None:
    """The issuer certifies on the cardholder's behalf (categories 10 and 13) only if the request came through
    a channel equivalent to a signature. Otherwise it asks for a signed letter with the card, the merchants and
    the amounts."""
    if not is_card(x) or x.dispute_type not in (DisputeType.NEAUTORIZATA, DisputeType.DISPUTA_COMERCIANT):
        return None
    if x.intake_authenticated is True:
        return Finding("DSP-32", "certificare_permisa",
                       "The request came through an authenticated channel. The issuer can certify on the cardholder's "
                       "behalf.", ("intake_authenticated",))
    if x.intake_authenticated is False and x.signed_letter is not True:
        return Finding("DSP-32", "DSP_CARDHOLDER_PROOF_MISSING",
                       "The request did not come through an authenticated channel and is not signed. Before the "
                       "dispute, the bank asks for a signed letter with the card (masked), the merchants and the "
                       "amounts.", ("intake_authenticated", "signed_letter"))
    return None


@rule("DSP-37", title="The issuer does not process invalid disputes and does due diligence on each one",
      basis="Visa Core Rules §11.1.2", confidence=P, pack="DSP", source=f"{SRC} §5.2", questions=(Q_ESCROC,),
      tests=("frauda_client",))
def dsp_37_due_diligence(x: RuleContextExt, env: Env) -> Finding | None:
    """Invalidity is checked before any dispute draft. With signs of customer fraud, no fraud dispute is
    proposed until a human clears them. The customer's legal protections still apply."""
    if not (is_card(x) and is_unauthorised(x)):
        return None
    signals = risk_signals(x, env)
    reasons = [t for t, _ in signals]
    fields = [f for _, fs in signals for f in fs]
    if x.hold_signal:
        reasons.append("a human confirmed a suspicion of customer fraud")
        fields.append("hold_signal")
    if x.ce3_met:
        reasons.append("the CE3.0 evidence is met")
        fields.append("ce3_met")
    if not reasons:
        return None
    return Finding("DSP-37", "due_diligence",
                   "No fraud dispute is proposed until a human clears the signals: " + "; ".join(reasons) + ".",
                   tuple(fields))


@rule("DSP-40", title="Mastercard reason codes (4837 fraud, 4853 dispute, 4834 error)",
      basis="Valitor/Rapyd specifications; aggregators", confidence=S, pack="DSP", source=f"{SRC} §5.3",
      questions=(Q_ESCROC,), exceptions=("DSP_RULE_UNVERIFIED",), tests=("DT-11",))
def dsp_40_mastercard_codes(x: RuleContextExt, env: Env) -> Finding | None:
    """The Mastercard reason codes come from secondary sources: 4837 No Cardholder Authorization, 4853
    Cardholder Dispute, 4834 Point-of-Interaction Error. The code is only a candidate."""
    if not is_card(x) or card_scheme(x, env) != "mastercard":
        return None
    code = MC_CODES.get(x.dispute_type)
    if code is None:
        return None
    return Finding("DSP-40", "cod_candidat", f"Candidate Mastercard reason code: {code} (secondary source).",
                   ("dispute_type",), data={"reason_code": code})


@rule("DSP-42", title="Sources conflict on Mastercard deadlines", basis="aggregators (Chargeback Gurus, "
      "ChargebackStop, Chargeflow)", confidence=U, pack="DSP", source=f"{SRC} §5.3", questions=(Q_ESCROC,),
      params=("mc_chargeback_open_days",), exceptions=("DSP_RULE_UNVERIFIED",), tests=("DT-11",))
def dsp_42_mastercard_deadlines(x: RuleContextExt, env: Env) -> Finding | None:
    """Mastercard deadlines live in the configuration, with no automatic block. A human chooses the route."""
    if not is_card(x) or card_scheme(x, env) != "mastercard" or x.dispute_type == DisputeType.APP:
        return None
    days = env.p("mc_chargeback_open_days")
    proc, _ = processing_date(x)
    due = visa_due(proc, days)
    return Finding("DSP-42", "DSP_RULE_UNVERIFIED",
                   f"Sources conflict on Mastercard deadlines (chargeback in about {days} days, by {fmt_d(due)} "
                   "[S]). Nothing is blocked automatically. A human decides.", ("executed_at",),
                   deadlines=(Deadline(rule_id="DSP-42", name="Mastercard chargeback deadline (estimated, [S])",
                                       due_at=end_of_day(due), basis="aggregators; sources conflict",
                                       business_days=False),))


@rule("DSP-43", title="4837 preconditions and the per-account cap are not verified", basis="gap in the notes",
      confidence=U, pack="DSP", source=f"{SRC} §5.3", questions=(Q_ESCROC,), exceptions=("DSP_RULE_UNVERIFIED",),
      tests=("DT-11",))
def dsp_43_mastercard_4837(x: RuleContextExt, env: Env) -> Finding | None:
    """The Mastercard fraud route goes to a human: the notes do not cover the 4837 preconditions."""
    if is_card(x) and card_scheme(x, env) == "mastercard" and is_unauthorised(x):
        return Finding("DSP-43", "DSP_RULE_UNVERIFIED",
                       "The preconditions for reason code 4837 (for example, reporting to the fraud database) are not "
                       "verified. A human chooses the Mastercard fraud route.", ("dispute_type",))
    return None


@rule("DSP-53", title="Evidence checklist; each gap becomes a request to the customer",
      basis="BCR form (proxy) [P at BCR]; Raiffeisen practice [U]", confidence=U, pack="DSP",
      source=f"{SRC} §7.4", questions=(Q_T1, Q_ESCROC, Q_ANSWER),
      params=("match_auto_min_points", "match_auto_min_margin", "match_candidate_min_points"),
      exceptions=("DSP_EVIDENCE_MISSING",), tests=("DT-09", "freeform"))
def dsp_53_evidence(x: RuleContextExt, env: Env) -> Finding | None:
    """Each gap in the evidence becomes a request to the customer. The first gap is the payment itself: when a
    free-form complaint cannot be matched to the customer or to a payment in the bank's records, the case rests on
    the customer's statements only, so a person identifies the payment and the bank asks the customer for the
    missing details. Consumer disputes (13.x) also need proof that the customer contacted the merchant, canceled or
    returned the purchase. If it is missing, the bank asks the customer for it before the dispute."""
    gaps: list[str] = []
    if not x.customer_identified:
        gaps.append("the customer's identification (the phone number or IBAN registered with the bank)")
    if not x.transaction_identified:
        gaps.append("the payment details (date, amount and payee)")
    if gaps:
        who = "" if x.customer_identified else " and the customer could not be identified"
        return Finding("DSP-53", "DSP_EVIDENCE_MISSING",
                       f"The payment could not be found in the bank's records{who}, so the case rests on the "
                       f"customer's statements only. A person identifies the payment, and the bank asks the customer "
                       f"for {' and '.join(gaps)}.",
                       ("transaction_identified", "customer_identified"), data={"missing": gaps, "gap": "identification"})
    if not is_card(x):
        return None
    cond = visa_condition(x)
    if not cond or not cond.startswith("13.") or cond == "13.9" or x.merchant_contact_proof is True:
        return None
    return Finding("DSP-53", "DSP_EVIDENCE_MISSING",
                   "Proof that the customer contacted the merchant (or canceled or returned the purchase) is missing. "
                   "The bank asks the customer for it before the dispute.", ("merchant_contact_proof",),
                   data={"missing": ["proof of merchant contact"]})


# ---------------------------------------------------------------- gărzi și calculatoare de proces


_REVERSAL_ALLOWED = {"comerciant_a_rambursat": "the merchant already refunded the same transaction",
                     "disputa_13x_pierduta": "the consumer dispute (13.x) was lost, under the contract clause [U]"}


@rule("DSP-55", title="Reverse a provisional credit only in permitted cases",
      basis="BCR clause (proxy) [P]; CJEU ruling C-70/25; AG opinion", confidence=U, pack="DSP", source=f"{SRC} §7.4",
      kind="garda", questions=(Q_CLIENT,), exceptions=("DSP_REVERSAL_BLOCKED",), tests=("DT-15",))
def validate_reversal(reason: str) -> GuardResult:
    """A reversal is proposed only if (a) the merchant already refunded, or (b) a 13.x consumer dispute was
    lost. After a refund under art. 173, gross negligence does not justify a reversal. The case goes to
    track B."""
    key = reason.strip().lower()
    if key in _REVERSAL_ALLOWED:
        return GuardResult(allowed=True, rule_id="DSP-55", code="propune_reversare",
                           explanation=f"A reversal can be proposed: {_REVERSAL_ALLOWED[key]}.",
                           next_actions=["Propose the reversal for human sign-off", "Notify the customer first"])
    return GuardResult(allowed=False, rule_id="DSP-55", code="DSP_REVERSAL_BLOCKED",
                       explanation="Reversing the credit is blocked. After a refund under Law 209/2019, art. 173, "
                                   "gross negligence or any other reason does not justify a one-sided reversal.",
                       next_actions=["Draft the repayment request on the recovery track (PAY-06)",
                                     "If the customer refuses, the bank goes to court (AG opinion)"])


class Ce3Txn(BaseModel):
    """O tranzacție pentru CE3.0 (date sintetice): elementele care se compară."""

    txn_id: str
    processed_on: date
    merchant_id: str | None = None
    device_id: str | None = None
    fingerprint: str | None = None
    ip: str | None = None
    login_id: str | None = None
    shipping_address: str | None = None      # adresa completă sau hash-ul ei
    reported_fraud: bool = False
    disputed: bool = False


class Ce3Result(BaseModel):
    met: bool
    code: str
    qualifying: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


def _ce3_elements(a: Ce3Txn, b: Ce3Txn, v2026: bool) -> set[str]:
    out: set[str] = set()
    device = bool(a.device_id and a.device_id == b.device_id and len(a.device_id) >= 15)
    fingerprint = bool(a.fingerprint and a.fingerprint == b.fingerprint and len(a.fingerprint) >= 20)
    if v2026:
        if device or fingerprint:
            out.add("device")            # din 24.10.2026: device ID și fingerprint = un singur element
    else:
        if device:
            out.add("device")
        if fingerprint:
            out.add("fingerprint")
    if a.ip and a.ip == b.ip:
        out.add("ip")
    if a.login_id and a.login_id == b.login_id:
        out.add("login")
    if a.shipping_address and a.shipping_address == b.shipping_address:
        out.add("address")
    return out


def ce3_check(disputed: Ce3Txn, priors: list[Ce3Txn], dispute_on: date, as_of: date | None = None) -> Ce3Result:
    """DSP-30: CE3.0 e îndeplinit cu două tranzacții anterioare pe aceeași credențială, neraportate ca fraudă,
    procesate cu peste 120 de zile înainte de dispută și în cele 365 de zile dinaintea tranzacției contestate,
    fiecare cu cel puțin două elemente potrivite, dintre care unul IP sau dispozitiv. Din 24.10.2026 contează și
    alți comercianți, iar device ID și fingerprint sunt un singur element. Versiunea regulii se alege după
    `as_of` (momentul evaluării, ex. pre-arbitrajul; implicit data disputei): data de referință e [U]."""
    v2026 = (as_of or dispute_on) >= CE3_V2026_FROM
    qualifying: list[str] = []
    reasons: list[str] = []
    for t in priors:
        if t.reported_fraud:
            reasons.append(f"{t.txn_id}: reported by the bank as fraud")
            continue
        if t.disputed:
            reasons.append(f"{t.txn_id}: disputed")
            continue
        if (dispute_on - t.processed_on).days <= 120:
            reasons.append(f"{t.txn_id}: processed 120 days or less before the dispute")
            continue
        age = (disputed.processed_on - t.processed_on).days
        if age < 0 or age > 365:
            reasons.append(f"{t.txn_id}: outside the 365 days before the disputed transaction")
            continue
        if not v2026 and t.merchant_id != disputed.merchant_id:
            reasons.append(f"{t.txn_id}: different merchant (before 24 Oct 2026, it had to be the same one)")
            continue
        elements = _ce3_elements(disputed, t, v2026)
        if len(elements) >= 2 and elements & {"device", "fingerprint", "ip"}:
            qualifying.append(t.txn_id)
        else:
            reasons.append(f"{t.txn_id}: matching elements: {', '.join(sorted(elements)) or 'none'} (two needed, one "
                           "of them IP or device)")
    met = len(qualifying) >= 2
    return Ce3Result(met=met, code="DSP_CE3_MET" if met else "DSP_CE3_NOT_MET", qualifying=qualifying,
                     reasons=reasons)


__all__ = ["Ce3Result", "Ce3Txn", "DisputeWindow", "MC_CODES", "VISA_CONDITIONS", "VISA_STAGES",
           "VISA_SUBCONDITIONS", "ce3_check", "chargeback_recoverable", "classification_ambiguous",
           "condition_name", "is_valid_condition", "scheme_deadline_status", "validate_reversal",
           "visa_allocation_stage_due", "visa_collaboration_stage_due", "visa_dispute_window", "visa_due",
           "visa_fraud_report_due"]
