"""Motorul de reguli VersoML: fapte → reguli → decizii, determinist, fără I/O în afară de citirea parametrilor.

Regulile (pachetele din `packs/`) constată; motorul compune deciziile pe cele patru întrebări în ordinea fixă
a arborilor din docs/context/11 §4.2 și 14 §4: întâi tipul cererii (APP, dispută, eroare), apoi cele 13 luni,
apoi singura excepție (suspiciunea de fraudă comunicată autorității), apoi rambursarea; recuperarea (de la
client sau de la escroc) nu schimbă niciodată rambursarea. Fiecare decizie are ID-urile regulilor, rânduri de
motivare cu citări din `ctx.fact_ids` și termenul ei.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from versoml.contracts import (
    Channel, Decision, Deadline, DisputeType, Money, Question, RationaleLine, RuleContext, RuleHit, RulesOutcome,
    Verdict, Zone,
)

from . import packs  # noqa: F401  (înregistrează regulile)
from .calendar_ro import local_date
from .context import AmlRuleContext, AmlRulesOutcome, RuleContextExt, extend
from .facts import (
    GN_FIELDS, Env, cite, fmt_d, fmt_dt, fmt_money, gn_indicator_fields, is_card, is_unauthorised, make_env,
    refund_due,
)
from .packs.dp import apply_human_review, explanation_complete
from .packs.rec import recall_applicable
from .params import get_params as _get_params
from .params import param_specs, resolve
from .params import set_params as _set_params
from .registry import (
    PACK_ORDER, PACK_TITLES, RULES_VERSION, Finding, RuleSpec, all_rules, engine_rules, get_rule, resolve_id,
)

ENGINE_VERSION = RULES_VERSION
QUESTIONS = (Question.RAMBURSARE_T1, Question.RECUPERARE_CLIENT, Question.RECUPERARE_ESCROC,
             Question.RASPUNS_RECLAMATIE)
Findings = Mapping[str, Finding]
# Declared facts only (DSP-53): the rules that read the bank's records (13 months, the cap, SCA, schemes, risk) do not
# run on the customer's statements. These need only the complaint's receipt and the text itself.
DECLARED_RULES = frozenset({"DSP-53", "DSP-57", "DSP-58", "DSP-03", "CMP-01", "CMP-02", "CMP-03"})


# ---------------------------------------------------------------- construirea unei decizii


class _Draft:
    """Acumulează o decizie: reguli, motivare cu citări, probe și pașii următori."""

    def __init__(self, x: RuleContextExt, question: Question, findings: Findings):
        self.x, self.q, self.f = x, question, findings
        self.rule_ids: list[str] = []
        self.rationale: list[RationaleLine] = []
        self.support: list[str] = []
        self.contra: list[str] = []
        self.missing: list[str] = []
        self.unknowns: list[str] = []
        self.next: list[str] = []

    def rule(self, rule_id: str) -> None:
        if rule_id not in self.rule_ids:
            self.rule_ids.append(rule_id)

    def use(self, rule_id: str, *, line: bool = True) -> Finding | None:
        """Adaugă regula și, dacă a constatat ceva, explicația ei ca rând de motivare."""
        found = self.f.get(rule_id)
        self.rule(rule_id)
        if found is not None and line:
            cites = cite(self.x, found.fields)
            self.rationale.append(RationaleLine(text=found.explanation, cites=cites))
            self.support.extend(c for c in cites if c not in self.support)
        return found

    def line(self, text: str, fields: Iterable[str] = ()) -> None:
        self.rationale.append(RationaleLine(text=text, cites=cite(self.x, fields)))

    def against(self, fields: Iterable[str]) -> None:
        self.contra.extend(c for c in cite(self.x, fields) if c not in self.contra)

    def build(self, verdict: Verdict, *, human: bool, deadline: datetime | None = None,
              amount: Money | None = None) -> Decision:
        return Decision(
            case_id=self.x.case_id, question=self.q, decision=verdict, rule_ids=list(self.rule_ids),
            supporting_evidence=[c for c in self.support if c not in self.contra],
            contradicting_evidence=list(self.contra), missing_evidence=list(dict.fromkeys(self.missing)),
            rationale=list(self.rationale), unknowns=list(dict.fromkeys(self.unknowns)),
            next_actions=list(dict.fromkeys(self.next)), requires_human=human, deadline=deadline, amount=amount,
            decided_by="rules+human" if human else "rules")


def _money(x: RuleContextExt) -> str:
    return fmt_money(x.amount.value, x.amount.currency)


def _evidence_gaps(d: _Draft, x: RuleContextExt) -> None:
    if x.sca_performed is None and x.screen_showed_amount_and_payee is None:
        d.missing.append("SCA log for the payment: method, device and what the screen showed")
    if x.screen_showed_amount_and_payee is None:
        d.unknowns.append("Whether the authentication screen showed the amount and beneficiary")


# ---------------------------------------------------------------- 1. rambursare_t1


def _decide_declared_refund(d: _Draft, x: RuleContextExt, env: Env, F: Findings) -> Decision:
    """Declared facts only (DSP-53): no payment in the bank's records matches the complaint. Nothing is refunded or
    refused on the customer's statements; a person identifies the payment, and the refund clock keeps running."""
    found = d.use("DSP-53")
    d.missing.extend(found.data["missing"] if found is not None else [])
    due = None
    if x.dispute_type == DisputeType.NEAUTORIZATA and not x.credit_fraud:
        due = refund_due(x, env)
        d.rule("PAY-03")
        d.line(f"If the payment turns out to be unauthorized, the refund deadline still runs from the customer's "
               f"report: {fmt_dt(due)}.", ["notified_at"])
    if "DSP-57" in F:
        d.use("DSP-57")
    d.next += ["Identify the customer and the payment in the bank's records" + (f" before {fmt_dt(due)}" if due else ""),
               "Ask the customer for the missing details (DSP-53)"]
    return d.build(Verdict.INFORMATII_SUPLIMENTARE, human=True, deadline=due,
                   amount=x.amount if x.amount.value > 0 else None)


def _decide_refund(x: RuleContextExt, env: Env, F: Findings) -> Decision:
    d = _Draft(x, Question.RAMBURSARE_T1, F)
    if not x.transaction_identified:
        return _decide_declared_refund(d, x, env, F)
    if "DSP-16" in F:
        d.use("DSP-16")
        d.use("CMP-04", line=False)
        d.next += ["Route to credit fraud (credit complaint, 30 days)",
                   "Ask the Credit Bureau to suspend reporting"]
        return d.build(Verdict.NU_SE_APLICA_T1, human=True, amount=x.amount)

    if x.dispute_type == DisputeType.APP:
        d.use("PAY-12")
        for rid in ("DSP-29", "DSP-51", "DSP-50"):
            if rid in F:
                d.use(rid)
        d.next += ["Recall the funds urgently (see fraudster recovery)", "Recommend a police report",
                   "Send an explanatory letter within 15 business days (CMP-01)"]
        return d.build(Verdict.NU_SE_APLICA_T1, human=True, amount=x.amount)

    if x.dispute_type in (DisputeType.DISPUTA_COMERCIANT, DisputeType.EROARE_PROCESARE):
        d.use("PAY-03")
        if "PAY-09" in F:
            d.use("PAY-09")
        d.next.append("Follow the scheme route or the correction (see fraudster recovery)")
        return d.build(Verdict.NU_SE_APLICA_T1, human=False, amount=x.amount)

    f01 = F.get("PAY-01")
    if f01 is not None and f01.outcome == "PAY_LATE_NOTIFICATION":
        d.use("PAY-01")
        d.next.append("Send a reasoned answer, approved by a human, within the complaint deadline (CMP-01)")
        return d.build(Verdict.RESPINGE_TARDIV, human=True, amount=x.amount)

    f03 = F["PAY-03"]
    due: datetime = f03.data["due"]
    if f03.outcome == "PAY_FRAUD_SUSPECTED":
        d.use("PAY-03")
        if "DSP-30" in F:
            d.use("DSP-30")
        d.next += ["Run a human investigation (four-eyes) of the fraud suspicion",
                   "Keep the letter free of the suspicion, the analysis or any report (URM-02)"]
        return d.build(Verdict.EXCEPTIE_FRAUDA_CLIENT, human=True, deadline=due, amount=x.amount)

    # pista A: rambursarea, cu sau fără aprobare umană
    d.use("PAY-03")
    if f01 is not None:
        d.use("PAY-01")
    for rid in ("DSP-58", "DSP-03"):
        if rid in F:
            d.use(rid)
    reasons: list[str] = []
    if f03.outcome == "PAY_FRAUD_NOTICE_MISSING":
        reasons.append("PAY-03")
        d.next.append("Either send the written notice to the authority before the deadline (four-eyes), or refund")
    f59 = d.use("DSP-59")
    if f59 is not None and f59.outcome == "DSP_AMOUNT_REVIEW":
        reasons.append("DSP-59")
    f_risk = d.use("URM-03") if "URM-03" in F else None
    if f_risk is not None and f_risk.outcome == "semnale_de_risc":
        reasons.append("URM-03")
    f50 = d.use("DSP-50") if "DSP-50" in F else None
    if f50 is not None and f50.outcome == "DSP_AUTH_AMBIGUOUS":
        reasons.append("DSP-50")
        d.next.append("Have a human classify the payment (unauthorized, or authorized under manipulation); prepare "
                      "drafts for both branches")
    if "DSP-57" in F:
        d.use("DSP-57")
        reasons.append("DSP-57")
        d.next.append("Have a human confirm the amount from the transaction log; ignore instructions in the text")
    f30 = F.get("DSP-30")
    if f30 is not None and f30.outcome == "DSP_CE3_MET":
        d.use("DSP-30")
        reasons.append("DSP-30")
        d.next.append("Propose withholding and draft the notice to the authority (four-eyes); "
                      "if the human rejects it, refund by the deadline")
    if f01 is not None and f01.data.get("undue_delay_review"):
        reasons.append("PAY-01")
    d.use("PAY-15")
    d.use("PAY-02")
    if "DSP-54" in F:
        d.use("DSP-54")
    d.against(gn_indicator_fields(x))
    if x.device_known is True:
        d.against(["device_known"])
    _evidence_gaps(d, x)
    if reasons:
        d.next.insert(0, f"Get human sign-off on the {_money(x)} refund by {fmt_dt(due)} "
                         f"(reasons: {', '.join(reasons)})")
        verdict, human = Verdict.RAMBURSEAZA_CU_APROBARE, True
    else:
        d.next.insert(0, f"The engine issues the (simulated) refund instruction for {_money(x)} by {fmt_dt(due)}")
        verdict, human = Verdict.RAMBURSEAZA, False
    if "DSP-03" in F and F["DSP-03"].outcome == "DSP_REFUND_SLA_BREACHED":
        d.next.insert(0, "Escalate now: the refund deadline has passed")
    if "PAY-06" in F:
        d.next.append("After the refund: open the recovery file (track B); a human decides (see customer recovery)")
    return d.build(verdict, human=human, deadline=due, amount=x.amount)


# ---------------------------------------------------------------- 2. recuperare_client


def _decide_client_recovery(x: RuleContextExt, env: Env, F: Findings, refund: Decision) -> Decision:
    d = _Draft(x, Question.RECUPERARE_CLIENT, F)
    if refund.decision not in (Verdict.RAMBURSEAZA, Verdict.RAMBURSEAZA_CU_APROBARE):
        rid = {Verdict.RESPINGE_TARDIV: "PAY-01", Verdict.EXCEPTIE_FRAUDA_CLIENT: "PAY-03"}.get(refund.decision)
        if rid is None:
            rid = "DSP-16" if x.credit_fraud else ("PAY-12" if x.dispute_type == DisputeType.APP else "PAY-03")
        d.rule(rid)
        d.rule("PAY-06")
        d.line("There is no refund to recover from. The gross negligence file does not open.",
               ["dispute_type"])
        return d.build(Verdict.NU_RECOMANDAM_RECUPERARE, human=False)

    f04, f06 = F.get("PAY-04"), F.get("PAY-06")
    if f04 is not None:
        d.use("PAY-04")
        d.rule("PAY-06")
        d.next.append("The customer's liability is zero: make no repayment request")
        if f04.outcome == "DSP_STAFF_INVOLVEMENT":
            d.next.append("Report the staff involvement to compliance")
        return d.build(Verdict.NU_RECOMANDAM_RECUPERARE, human=False)

    if f06 is not None:
        d.use("PAY-06")
        d.use("PAY-15")
        d.use("PAY-02")
        if "PAY-08" in F:
            d.use("PAY-08")
        if "PAY-05" in F:
            d.use("PAY-05")
        d.next += ["Open the recovery file (track B) after the refund; the bank carries the burden of proof",
                   "The Prosecutor and the Defender gather the evidence; the rubric and a human decide",
                   "If the human finds no gross negligence: at most EUR 30 (Law 209/2019, art. 179(1))",
                   "If the customer refuses to repay, the bank goes to court (AG opinion)"]
        return d.build(Verdict.RECUPERARE_PROPUSA, human=True, amount=x.amount)

    admitted = [f for f in ("client_admits_approving_in_app", "client_admits_sharing_credentials")
                if getattr(x, f) is True]
    blocked = [rid for rid in ("PAY-02", "PAY-08")
               if F.get(rid) is not None and F[rid].outcome == "PAY_SCA_EVIDENCE_MISSING"]
    if admitted and blocked:
        for rid in blocked:
            d.use(rid)
        d.rule("PAY-06")
        d.line("Recovery from the customer is blocked. Without proof of authentication for this payment, gross "
               "negligence cannot be proven (Law 209/2019, art. 171–172).", admitted)
        d.missing.append("SCA log for the disputed payment, with the amount and beneficiary shown")
        return d.build(Verdict.NU_RECOMANDAM_RECUPERARE, human=False)

    d.rule("PAY-06")
    d.line("There are no signs of gross negligence. A recovery file (PAY-06) needs the screen to have shown the "
           "amount and beneficiary, and the customer to have approved the payment or shared their credentials.",
           GN_FIELDS)
    if "PAY-05" in F:
        d.use("PAY-05")
    _evidence_gaps(d, x)
    return d.build(Verdict.NU_RECOMANDAM_RECUPERARE, human=False)


# ---------------------------------------------------------------- 3. recuperare_escroc


def _decide_fraudster_recovery(x: RuleContextExt, env: Env, F: Findings, refund: Decision) -> Decision:
    d = _Draft(x, Question.RECUPERARE_ESCROC, F)
    if not x.transaction_identified:
        d.use("DSP-53", line=False)
        d.line("No recall or chargeback until the payment is identified in the bank's records.",
               ["transaction_identified"])
        return d.build(Verdict.NU_RECOMANDAM_RECUPERARE, human=True)
    if x.credit_fraud:
        d.use("DSP-16")
        d.line("A loan in the victim's name cannot be recovered by recall or chargeback.", ["credit_fraud"])
        return d.build(Verdict.NU_RECOMANDAM_RECUPERARE, human=False)
    if refund.decision == Verdict.EXCEPTIE_FRAUDA_CLIENT:
        d.rule("PAY-03")
        d.line("The refund is withheld on suspicion of customer fraud. Recovery from third parties waits for the "
               "investigation.", ["hold_signal", "hold_authority_notified"])
        return d.build(Verdict.NU_RECOMANDAM_RECUPERARE, human=True)
    if is_card(x):
        return _card_recovery(d, x, env, F)
    return _transfer_recovery(d, x, env, F)


def _scheme_deadline(F: Findings) -> datetime | None:
    for rid in ("DSP-24", "DSP-42"):
        found = F.get(rid)
        if found is not None and found.deadlines:
            return found.deadlines[0].due_at
    return None


def _card_recovery(d: _Draft, x: RuleContextExt, env: Env, F: Findings) -> Decision:
    f52 = F.get("DSP-52")
    if f52 is None:
        d.rule("DSP-52")
        d.line("Chargeback recoverability cannot be calculated. A human decides.", ["channel"])
        return d.build(Verdict.NU_RECOMANDAM_RECUPERARE, human=True)
    value, blocking, code = f52.data["value"], list(f52.data["blocking_rules"]), f52.data["reason_code"]
    if "DSP-37" in F and value != "NU":
        d.use("DSP-37")
        d.use("DSP-52")
        if "URM-03" in F:
            d.rule("URM-03")
        due = _scheme_deadline(F)
        d.next.append("Have a human clear the signals before any fraud dispute"
                      + (f"; dispute deadline: {fmt_d(due)}" if due else ""))
        return d.build(Verdict.NU_RECOMANDAM_RECUPERARE, human=True)
    d.use("DSP-52")
    for rid in ("DSP-20", *blocking):
        if rid in F:
            d.use(rid)
        elif rid in blocking:
            d.rule(rid)
    label = code or "none"
    if value in ("DA", "INCERT"):
        for rid in ("DSP-24", "DSP-25", "DSP-32", "DSP-40", "DSP-42", "DSP-43", "PAY-07"):
            if rid in F:
                d.use(rid)
        if value == "DA":
            d.next.append(f"Draft the dispute under reason code {label} in VROL; a human submits it")
        else:
            d.next.append(f"Have a human choose the scheme route (candidate reason code: {label}; rules: "
                          f"{', '.join(blocking)})")
        if "DSP-53" in F:
            d.missing.append("Proof that the customer contacted the merchant (or canceled or returned the purchase)")
            d.next.append("Ask the customer for proof of merchant contact before the dispute (DSP-53)")
        f32 = F.get("DSP-32")
        if f32 is not None and f32.outcome == "DSP_CARDHOLDER_PROOF_MISSING":
            d.missing.append("Signed letter from the cardholder")
            d.next.append("Ask for the signed letter before the dispute (DSP-32)")
        if "DSP-25" in F:
            d.next.append(f"Report the fraud to Visa by {fmt_d(F['DSP-25'].data['due'])} (DSP-25)")
        return d.build(Verdict.CHARGEBACK, human=True, deadline=_scheme_deadline(F), amount=x.amount)
    if "DSP-25" in F:
        d.use("DSP-25")
        d.next.append(f"Report the fraud to Visa by {fmt_d(F['DSP-25'].data['due'])}, even without a dispute (DSP-25)")
    if is_unauthorised(x):
        d.next.append("The bank bears the loss if recovery from the customer (track B) fails")
    return d.build(Verdict.NU_RECOMANDAM_RECUPERARE, human=False)


def _transfer_recovery(d: _Draft, x: RuleContextExt, env: Env, F: Findings) -> Decision:
    if not recall_applicable(x):
        d.rule("PAY-03")
        d.line("A fraud recall does not apply to this type of dispute. A human decides the correction.",
               ["dispute_type"])
        return d.build(Verdict.NU_RECOMANDAM_RECUPERARE, human=True)
    if "REC-05" in F:
        d.use("REC-05")
        d.next.append("A human can still try a return request, with no guarantee")
        return d.build(Verdict.NU_RECOMANDAM_RECUPERARE, human=False)
    deadline: datetime | None = None
    if "REC-03" in F:
        d.use("REC-03")
        action = "Block the amount in the beneficiary's account internally and request its return (human sign-off)"
    elif "REC-01" in F:
        d.use("REC-01")
        f02 = d.use("REC-02")
        deadline = f02.data["due"] if f02 is not None else None
        action = "Send camt.056 with reason FRAD (draft) after human sign-off"
    else:
        f04 = d.use("REC-04")
        deadline = f04.deadlines[0].due_at if f04 is not None and f04.deadlines else None
        action = "Send the recall request to the beneficiary's bank (draft) after human sign-off"
    urgent = x.dispute_type == DisputeType.APP or x.channel == Channel.TRANSFER_INSTANT or x.device_known is False
    d.next.append(("URGENT: " if urgent else "") + action)
    if x.dispute_type == DisputeType.APP:
        d.rule("PAY-12")
    if "URM-03" in F and F["URM-03"].outcome == "semnale_de_risc":
        d.use("URM-03")
    d.next.append("Report the fraudster's domain or phone number to DNSC (draft; a human sends it)")
    return d.build(Verdict.RECHEMARE, human=True, deadline=deadline, amount=x.amount)


# ---------------------------------------------------------------- 4. raspuns_reclamatie

_LETTER_OUTCOME = {
    Verdict.RAMBURSEAZA: "the refund within the refund deadline",
    Verdict.RAMBURSEAZA_CU_APROBARE: "the refund, approved by a human within the refund deadline",
    Verdict.RESPINGE_TARDIV: "a reasoned rejection, because the customer reported the payment after 13 months "
                             "(Law 209/2019, art. 169)",
    Verdict.NU_SE_APLICA_T1: "the route that fits the dispute (support, scheme dispute or correction), not the next-business-day "
                             "refund",
}


def _decide_complaint_answer(x: RuleContextExt, env: Env, F: Findings, refund: Decision) -> Decision:
    d = _Draft(x, Question.RASPUNS_RECLAMATIE, F)
    if "CMP-04" in F:
        f04 = d.use("CMP-04")
        d.rule("DSP-16")
        deadline = f04.data["due"] if f04 is not None else None
    else:
        f01 = d.use("CMP-01")
        f02 = d.use("CMP-02")
        d.use("CMP-03")
        deadline = f02.data["effective_due"] if f02 is not None else (f01.data["due"] if f01 is not None else None)
        if f02 is not None and f02.outcome == "CMP_HOLDING_REPLY_REQUIRED":
            d.next.append("Only if the delay is outside the bank's control: send a reasoned holding reply (CMP-02)")
    d.next += ["Answer every point of the complaint on a durable medium (CMP-01)",
               "Include the external complaint routes: ANPC, ANAF, BNR and CSALB (CMP-03)",
               "Send the letter only after the wall filter and human sign-off"]
    gaps = False
    if "DSP-53" in F:
        d.use("DSP-53")
        gap = F["DSP-53"].data
        d.missing.extend(gap["missing"] if gap.get("gap") == "identification" else ["Proof of merchant contact"])
        gaps = True
    f32 = F.get("DSP-32")
    if f32 is not None and f32.outcome == "DSP_CARDHOLDER_PROOF_MISSING":
        d.use("DSP-32")
        d.missing.append("Signed letter from the cardholder")
        gaps = True
    if "DSP-57" in F:
        d.use("DSP-57")
    if refund.decision == Verdict.EXCEPTIE_FRAUDA_CLIENT or x.hold_signal:
        d.rule("URM-02")
        d.line("The letter stays neutral. It does not mention the suspicion, the analysis or any report "
               "(tipping-off ban).")
    if refund.decision == Verdict.EXCEPTIE_FRAUDA_CLIENT or gaps:
        verdict = Verdict.INFORMATII_SUPLIMENTARE
        if gaps:
            d.next.insert(0, "Ask the customer for the missing evidence, with a deadline; the dispute starts once it "
                             "arrives")
    else:
        verdict = refund.decision
        d.line(f"The letter tells the customer about {_LETTER_OUTCOME.get(refund.decision, 'the decision')}.",
               ["dispute_type"])
    return d.build(verdict, human=True, deadline=deadline)


# ---------------------------------------------------------------- gărzi, hit-uri, termene


def _guards(dec: Decision, x: RuleContextExt, env: Env, F: Findings) -> tuple[Decision, list[str]]:
    applied: list[str] = []
    if env.p("require_human_for_unfavourable"):
        guarded = apply_human_review(dec, x)
        if guarded is not dec:
            applied.append("DP-02")
        dec = guarded
    f_risk = F.get("URM-03")
    if (dec.question == Question.RAMBURSARE_T1 and f_risk is not None and f_risk.outcome == "semnale_de_risc"
            and "client_fraud_score" in f_risk.fields and "URM-03" in dec.rule_ids):
        dec = apply_human_review(dec, x, reason="The M2 score is only a signal for a human. A human decides, not the "
                                               "score (GDPR art. 22; CJEU SCHUFA ruling).")
        applied.append("DP-02")
    if not explanation_complete(dec):
        dec = dec.model_copy(update={"requires_human": True, "decided_by": "rules+human",
                                     "rule_ids": [*dec.rule_ids, "DP-03"]})
        applied.append("DP-03")
    return dec, applied


def _hit(spec: RuleSpec, f: Finding, x: RuleContextExt | AmlRuleContext, env: Env) -> RuleHit:
    params: dict[str, Any] = {name: env.params.get(name) for name in spec.params}
    params.update(dict(f.data.get("hit_params", {})))
    inputs = cite(x, f.fields) if isinstance(x, RuleContextExt) else _cite_aml(x, f.fields)
    return RuleHit(rule_id=spec.rule_id, version=spec.version, title=spec.title, basis=spec.basis,
                   confidence=spec.confidence, outcome=f.outcome, explanation=f.explanation, inputs=inputs,
                   params=params)


def _guard_hit(rule_id: str, outcome: str, explanation: str, env: Env) -> RuleHit:
    spec = get_rule(rule_id)
    return RuleHit(rule_id=spec.rule_id, version=spec.version, title=spec.title, basis=spec.basis,
                   confidence=spec.confidence, outcome=outcome, explanation=explanation,
                   params={name: env.params.get(name) for name in spec.params})


def _deadlines(findings: Iterable[Finding]) -> list[Deadline]:
    seen: set[tuple[str, str]] = set()
    out: list[Deadline] = []
    for f in findings:
        for dl in f.deadlines:
            if (dl.rule_id, dl.name) not in seen:
                seen.add((dl.rule_id, dl.name))
                out.append(dl)
    return out


def _params_used(specs: Iterable[RuleSpec], env: Env) -> dict[str, Any]:
    used: dict[str, Any] = {}
    for spec in specs:
        for name in spec.params:
            used[name] = env.params.get(name)
    return used


# ---------------------------------------------------------------- API public (docs/06 §4.4)


def evaluate(ctx: RuleContext, params: dict | None = None) -> RulesOutcome:
    """Evaluează regulile zonei client pe un caz. Determinist și pur: aceleași fapte și parametri dau același
    rezultat. `params=None` folosește parametrii efectivi; un dicționar se pune peste valorile implicite.
    `ctx` poate fi un `RuleContextExt`, cu faptele suplimentare pentru DSP, CMP și REC."""
    p, flags = resolve(params)
    env = make_env(p, flags)
    x = extend(ctx, **({"classification_ambiguous": True} if flags.get("classification_ambiguous") else {}))
    today = local_date(x.now)
    findings: dict[str, Finding] = {}
    specs: dict[str, RuleSpec] = {}
    for spec in engine_rules(Zone.CLIENT):
        if not x.transaction_identified and spec.rule_id not in DECLARED_RULES:
            continue
        if spec.is_effective(today):
            found = spec.fn(x, env) if spec.fn else None
            if found is not None:
                findings[spec.rule_id] = found
                specs[spec.rule_id] = spec
    refund = _decide_refund(x, env, findings)
    drafts = [refund, _decide_client_recovery(x, env, findings, refund),
              _decide_fraudster_recovery(x, env, findings, refund), _decide_complaint_answer(x, env, findings, refund)]
    decisions: list[Decision] = []
    guards: set[str] = set()
    for draft in drafts:
        dec, applied = _guards(draft, x, env, findings)
        decisions.append(dec)
        guards.update(applied)
    hits = [_hit(specs[rid], f, x, env) for rid, f in findings.items()]
    if "DP-02" in guards:
        hits.append(_guard_hit("DP-02", "DP_HUMAN_REVIEW_REQUIRED",
                               "A human signs off adverse decisions and decisions that involve the M2 score "
                               "(GDPR art. 22).", env))
        specs["DP-02"] = get_rule("DP-02")
    if "DP-03" in guards:
        hits.append(_guard_hit("DP-03", "DP_EXPLANATION_MISSING", "A decision had no rule or explanation.", env))
    return RulesOutcome(case_id=x.case_id, decisions=decisions, hits=hits, deadlines=_deadlines(findings.values()),
                        params_used=_params_used(specs.values(), env), engine_version=ENGINE_VERSION)


def _cite_aml(a: AmlRuleContext, fields: Iterable[str]) -> list[str]:
    out: list[str] = []
    for f in fields:
        fid = a.fact_ids.get(f)
        if fid and fid not in out:
            out.append(fid)
    return out


def evaluate_aml(ctx: AmlRuleContext, params: dict | None = None) -> AmlRulesOutcome:
    """Regulile zonei AML (Legea 129/2019 art. 6–8 și extensiile URM): propunerea de RTS, ceasurile și
    constrângerile. Nu rulează niciodată în zona client."""
    p, flags = resolve(params)
    env = make_env(p, flags)
    order = sorted(engine_rules(Zone.AML), key=lambda s: (s.pack != "AML", PACK_ORDER.index(s.pack), s.rule_id))
    findings: dict[str, Finding] = {}
    specs: dict[str, RuleSpec] = {}
    for spec in order:
        found = spec.fn(ctx, env) if spec.fn else None
        if found is not None:
            findings[spec.rule_id] = found
            specs[spec.rule_id] = spec

    def lines(rule_ids: Iterable[str]) -> list[RationaleLine]:
        return [RationaleLine(text=findings[r].explanation, cites=_cite_aml(ctx, findings[r].fields))
                for r in rule_ids if r in findings]

    holds = [f.data["until"] for f in findings.values() if isinstance(f.data.get("until"), datetime)]
    hold_until = max(holds) if holds else None
    rts_rules = [r for r in ("AML-01", "URM-04", "AML-02", "AML-03", "AML-04", "AML-06") if r in findings]
    proposed = "AML-01" in findings or "URM-04" in findings
    next_rts = (["The analyst decides whether to file the STR with ONPCSB (Law 129/2019, art. 6)"]
                + ([f"The linked transaction stays on hold until {fmt_dt(hold_until)}"] if hold_until else [])
                if proposed else ["The lead stays under monitoring; the analyst can decide otherwise"])
    rts_lines = lines(rts_rules) or [RationaleLine(text="No objective indicators are above the thresholds and no "
                                                       "suspicion is confirmed. The lead stays under monitoring.")]
    rts = Decision(case_id=ctx.lead_id, question=Question.RTS,
                   decision=Verdict.RTS_PROPUS if proposed else Verdict.MONITORIZARE,
                   rule_ids=[*rts_rules, "URM-02"] if rts_rules else ["URM-04", "URM-02"],
                   rationale=[*rts_lines, *lines(["URM-02"])],
                   supporting_evidence=sorted({c for r in rts_rules for c in _cite_aml(ctx, findings[r].fields)}),
                   next_actions=next_rts, requires_human=proposed, deadline=hold_until,
                   amount=Money(value=ctx.amount_total, currency="RON") if ctx.amount_total is not None else None,
                   decided_by="rules+human" if proposed else "rules")
    lead_rules = [r for r in ("URM-01", "AML-07", "AML-08", "AML-09") if r in findings]
    profiling = findings.get("URM-01") is not None and findings["URM-01"].outcome == "URM_PROFILING_FEATURE"
    next_lead = [f"Send the threshold report ({findings[r].outcome}) to ONPCSB" for r in ("AML-07", "AML-08")
                 if r in findings]
    if profiling:
        next_lead.insert(0, "Recalculate the score from objective facts only (no personal traits)")
    lead = Decision(case_id=ctx.lead_id, question=Question.PISTA_AML,
                    decision=Verdict.INFORMATII_SUPLIMENTARE if profiling else Verdict.MONITORIZARE,
                    rule_ids=[*lead_rules, "URM-02"],
                    rationale=[*lines(lead_rules), *lines(["URM-02"])],
                    next_actions=next_lead or ["Monitor the linked accounts; the analyst decides"],
                    requires_human=profiling, decided_by="rules+human" if profiling else "rules")
    deadlines = _deadlines(findings.values())
    constraints = ["tipping_off_ban: only the HOLD signal goes to the client zone (URM-02)",
                   "doar_fapte_obiective: no personal traits in scores (URM-01)"]
    hits = [_hit(specs[r], f, ctx, env) for r, f in findings.items()]
    return AmlRulesOutcome(lead_id=ctx.lead_id, decisions=[rts, lead], hits=hits, deadlines=deadlines,
                           tx_hold_until=hold_until, constraints=constraints,
                           params_used=_params_used(specs.values(), env), engine_version=ENGINE_VERSION)


def catalog() -> list[dict]:
    """Catalogul regulilor: {rule_id, title, basis, confidence, pack, params, ...}, în ordinea pachetelor."""
    values = _get_params()
    return [spec.to_catalog(values) for spec in all_rules()]


def get_params() -> dict:
    return _get_params()


def set_params(updates: dict) -> dict:
    return _set_params(updates)


def explain(rule_id: str) -> dict:
    """Fișa unei reguli: metadatele, descrierea (în engleză), parametrii (cu marcajul lor) și aliasurile.
    Acceptă și ID-urile DSP care aplică articolele din PAY/CMP (ex. DSP-04 → PAY-15)."""
    spec = get_rule(rule_id)
    values = _get_params()
    entry = spec.to_catalog(values)
    specs = param_specs()
    entry.update({
        "pack_title": PACK_TITLES[spec.pack],
        "description": spec.description,
        "params_detail": {name: specs[name].public() | {"value": values.get(name)} for name in spec.params},
        "requested_id": rule_id,
        "alias_of": spec.rule_id if resolve_id(rule_id) != rule_id else None,
    })
    if entry["alias_of"]:
        entry["note"] = (f"{rule_id} (docs/context/14) applies rule {spec.rule_id} in the dispute flow "
                         f"({spec.source}).")
    return entry


__all__ = ["ENGINE_VERSION", "QUESTIONS", "catalog", "evaluate", "evaluate_aml", "explain", "get_params",
           "set_params"]
