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
        d.missing.append("jurnalul SCA al plății: metoda, dispozitivul și ce a afișat ecranul")
    if x.screen_showed_amount_and_payee is None:
        d.unknowns.append("dacă ecranul de autentificare a afișat suma și beneficiarul")


# ---------------------------------------------------------------- 1. rambursare_t1


def _decide_refund(x: RuleContextExt, env: Env, F: Findings) -> Decision:
    d = _Draft(x, Question.RAMBURSARE_T1, F)
    if "DSP-16" in F:
        d.use("DSP-16")
        d.use("CMP-04", line=False)
        d.next += ["rutează la frauda de credit (reclamație de credit, 30 de zile)",
                   "cere suspendarea raportării la Biroul de Credit"]
        return d.build(Verdict.NU_SE_APLICA_T1, human=True, amount=x.amount)

    if x.dispute_type == DisputeType.APP:
        d.use("PAY-12")
        for rid in ("DSP-29", "DSP-51", "DSP-50"):
            if rid in F:
                d.use(rid)
        d.next += ["rechemare urgentă a sumei (recuperare_escroc)", "recomandă plângerea la poliție",
                   "scrisoare explicativă în 15 zile lucrătoare (CMP-01)"]
        return d.build(Verdict.NU_SE_APLICA_T1, human=True, amount=x.amount)

    if x.dispute_type in (DisputeType.DISPUTA_COMERCIANT, DisputeType.EROARE_PROCESARE):
        d.use("PAY-03")
        if "PAY-09" in F:
            d.use("PAY-09")
        d.next.append("urmează traseul de schemă sau corecția (vezi recuperare_escroc)")
        return d.build(Verdict.NU_SE_APLICA_T1, human=False, amount=x.amount)

    f01 = F.get("PAY-01")
    if f01 is not None and f01.outcome == "PAY_LATE_NOTIFICATION":
        d.use("PAY-01")
        d.next.append("răspuns motivat, aprobat de om, în termenul reclamației (CMP-01)")
        return d.build(Verdict.RESPINGE_TARDIV, human=True, amount=x.amount)

    f03 = F["PAY-03"]
    due: datetime = f03.data["due"]
    if f03.outcome == "PAY_FRAUD_SUSPECTED":
        d.use("PAY-03")
        if "DSP-30" in F:
            d.use("DSP-30")
        d.next += ["investigație umană (four-eyes) asupra suspiciunii de fraudă",
                   "scrisoarea către client nu menționează suspiciunea, analiza sau o raportare (URM-02)"]
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
        d.next.append("fie comunicarea scrisă către autoritate pleacă înainte de termen (four-eyes), fie se rambursează")
    f59 = d.use("DSP-59")
    if f59 is not None and f59.outcome == "DSP_AMOUNT_REVIEW":
        reasons.append("DSP-59")
    f_risk = d.use("URM-03") if "URM-03" in F else None
    if f_risk is not None and f_risk.outcome == "semnale_de_risc":
        reasons.append("URM-03")
    f50 = d.use("DSP-50") if "DSP-50" in F else None
    if f50 is not None and f50.outcome == "DSP_AUTH_AMBIGUOUS":
        reasons.append("DSP-50")
        d.next.append("un om clasifică plata (neautorizată sau autorizată sub manipulare); ciorne pentru ambele ramuri")
    if "DSP-57" in F:
        d.use("DSP-57")
        reasons.append("DSP-57")
        d.next.append("un om confirmă suma din jurnal; instrucțiunile din text se ignoră")
    f30 = F.get("DSP-30")
    if f30 is not None and f30.outcome == "DSP_CE3_MET":
        d.use("DSP-30")
        reasons.append("DSP-30")
        d.next.append("propune reținerea și redactează notificarea către autoritate (four-eyes); "
                      "dacă omul infirmă, rambursează la termen")
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
        d.next.insert(0, f"un om aprobă rambursarea a {_money(x)} până la {fmt_dt(due)} (motive: {', '.join(reasons)})")
        verdict, human = Verdict.RAMBURSEAZA_CU_APROBARE, True
    else:
        d.next.insert(0, f"motorul emite instrucțiunea (simulată) de rambursare a {_money(x)} până la {fmt_dt(due)}")
        verdict, human = Verdict.RAMBURSEAZA, False
    if "DSP-03" in F and F["DSP-03"].outcome == "DSP_REFUND_SLA_BREACHED":
        d.next.insert(0, "escaladare imediată: termenul T+1 a trecut")
    if "PAY-06" in F:
        d.next.append("după rambursare: dosarul de recuperare (pista B), decis de om (recuperare_client)")
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
        d.line("Nu există o rambursare din care să se recupereze: dosarul de neglijență gravă nu se deschide.",
               ["dispute_type"])
        return d.build(Verdict.NU_RECOMANDAM_RECUPERARE, human=False)

    f04, f06 = F.get("PAY-04"), F.get("PAY-06")
    if f04 is not None:
        d.use("PAY-04")
        d.rule("PAY-06")
        d.next.append("răspunderea clientului e 0: nicio cerere de restituire")
        if f04.outcome == "DSP_STAFF_INVOLVEMENT":
            d.next.append("sesizează conformitatea (implicarea unui angajat)")
        return d.build(Verdict.NU_RECOMANDAM_RECUPERARE, human=False)

    if f06 is not None:
        d.use("PAY-06")
        d.use("PAY-15")
        d.use("PAY-02")
        if "PAY-08" in F:
            d.use("PAY-08")
        if "PAY-05" in F:
            d.use("PAY-05")
        d.next += ["deschide dosarul de recuperare (pista B), după rambursare: proba e a băncii",
                   "Procurorul și Avocatul strâng probele; rubrica și omul decid",
                   "dacă omul nu reține neglijența gravă: cel mult 30 EUR (art. 179 alin. (1))",
                   "dacă clientul refuză restituirea, banca acționează în instanță (opinia AG)"]
        return d.build(Verdict.RECUPERARE_PROPUSA, human=True, amount=x.amount)

    admitted = [f for f in ("client_admits_approving_in_app", "client_admits_sharing_credentials")
                if getattr(x, f) is True]
    blocked = [rid for rid in ("PAY-02", "PAY-08")
               if F.get(rid) is not None and F[rid].outcome == "PAY_SCA_EVIDENCE_MISSING"]
    if admitted and blocked:
        for rid in blocked:
            d.use(rid)
        d.rule("PAY-06")
        d.line("Recuperarea de la client e blocată: fără probă de autentificare pentru această plată, neglijența "
               "gravă nu poate fi dovedită (art. 171–172).", admitted)
        d.missing.append("jurnalul SCA al plății contestate, cu suma și beneficiarul afișate")
        return d.build(Verdict.NU_RECOMANDAM_RECUPERARE, human=False)

    d.rule("PAY-06")
    d.line("Nu există indicii de neglijență gravă: pentru dosarul de recuperare (PAY-06) ecranul trebuie să fi afișat "
           "suma și beneficiarul, iar clientul să fi aprobat plata sau să-și fi divulgat datele.", GN_FIELDS)
    if "PAY-05" in F:
        d.use("PAY-05")
    _evidence_gaps(d, x)
    return d.build(Verdict.NU_RECOMANDAM_RECUPERARE, human=False)


# ---------------------------------------------------------------- 3. recuperare_escroc


def _decide_fraudster_recovery(x: RuleContextExt, env: Env, F: Findings, refund: Decision) -> Decision:
    d = _Draft(x, Question.RECUPERARE_ESCROC, F)
    if x.credit_fraud:
        d.use("DSP-16")
        d.line("Creditul pe numele victimei nu se recuperează prin rechemare sau chargeback.", ["credit_fraud"])
        return d.build(Verdict.NU_RECOMANDAM_RECUPERARE, human=False)
    if refund.decision == Verdict.EXCEPTIE_FRAUDA_CLIENT:
        d.rule("PAY-03")
        d.line("Rambursarea e reținută pentru suspiciune de fraudă a clientului: recuperarea de la terți așteaptă "
               "investigația.", ["hold_signal", "hold_authority_notified"])
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
        d.line("Recuperabilitatea prin chargeback nu se poate calcula: decide omul.", ["channel"])
        return d.build(Verdict.NU_RECOMANDAM_RECUPERARE, human=True)
    value, blocking, code = f52.data["value"], list(f52.data["blocking_rules"]), f52.data["reason_code"]
    if "DSP-37" in F and value != "NU":
        d.use("DSP-37")
        d.use("DSP-52")
        if "URM-03" in F:
            d.rule("URM-03")
        due = _scheme_deadline(F)
        d.next.append("un om lămurește semnalele înainte de orice dispută de fraudă"
                      + (f"; termenul de dispută: {fmt_d(due)}" if due else ""))
        return d.build(Verdict.NU_RECOMANDAM_RECUPERARE, human=True)
    d.use("DSP-52")
    for rid in ("DSP-20", *blocking):
        if rid in F:
            d.use(rid)
        elif rid in blocking:
            d.rule(rid)
    label = code or "condiția de ales de om"
    if value in ("DA", "INCERT"):
        for rid in ("DSP-24", "DSP-25", "DSP-32", "DSP-40", "DSP-42", "DSP-43", "PAY-07"):
            if rid in F:
                d.use(rid)
        if value == "DA":
            d.next.append(f"pregătește disputa {label} (ciornă în VROL); o trimite un om")
        else:
            d.next.append(f"omul alege ruta de schemă (candidat: {label}; reguli: {', '.join(blocking)})")
        if "DSP-53" in F:
            d.missing.append("dovada contactării comerciantului (sau a anulării ori a returului)")
            d.next.append("cere clientului dovada contactării comerciantului, înainte de dispută (DSP-53)")
        f32 = F.get("DSP-32")
        if f32 is not None and f32.outcome == "DSP_CARDHOLDER_PROOF_MISSING":
            d.missing.append("scrisoarea semnată a titularului")
            d.next.append("cere scrisoarea semnată înainte de dispută (DSP-32)")
        if "DSP-25" in F:
            d.next.append(f"raportează frauda la Visa până la {fmt_d(F['DSP-25'].data['due'])} (DSP-25)")
        return d.build(Verdict.CHARGEBACK, human=True, deadline=_scheme_deadline(F), amount=x.amount)
    if "DSP-25" in F:
        d.use("DSP-25")
        d.next.append(f"raportează frauda la Visa până la {fmt_d(F['DSP-25'].data['due'])}, chiar fără dispută (DSP-25)")
    if is_unauthorised(x):
        d.next.append("pierderea rămâne la bancă dacă recuperarea de la client (pista B) nu reușește")
    return d.build(Verdict.NU_RECOMANDAM_RECUPERARE, human=False)


def _transfer_recovery(d: _Draft, x: RuleContextExt, env: Env, F: Findings) -> Decision:
    if not recall_applicable(x):
        d.rule("PAY-03")
        d.line("Rechemarea pe motiv de fraudă nu se aplică acestui tip de cerere; corecția o decide omul.",
               ["dispute_type"])
        return d.build(Verdict.NU_RECOMANDAM_RECUPERARE, human=True)
    if "REC-05" in F:
        d.use("REC-05")
        d.next.append("un om poate încerca totuși o cerere de returnare, fără garanții")
        return d.build(Verdict.NU_RECOMANDAM_RECUPERARE, human=False)
    deadline: datetime | None = None
    if "REC-03" in F:
        d.use("REC-03")
        action = "blochează intern suma în contul beneficiarului și cere returnarea (aprobare umană)"
    elif "REC-01" in F:
        d.use("REC-01")
        f02 = d.use("REC-02")
        deadline = f02.data["due"] if f02 is not None else None
        action = "trimite camt.056 cu motivul FRAD (ciornă), după aprobarea omului"
    else:
        f04 = d.use("REC-04")
        deadline = f04.deadlines[0].due_at if f04 is not None and f04.deadlines else None
        action = "trimite cererea de rechemare către banca beneficiarului (ciornă), după aprobarea omului"
    urgent = x.dispute_type == DisputeType.APP or x.channel == Channel.TRANSFER_INSTANT or x.device_known is False
    d.next.append(("URGENT: " if urgent else "") + action)
    if x.dispute_type == DisputeType.APP:
        d.rule("PAY-12")
    if "URM-03" in F and F["URM-03"].outcome == "semnale_de_risc":
        d.use("URM-03")
    d.next.append("raportează domeniul sau numărul escrocului la DNSC (ciornă; o trimite un om)")
    return d.build(Verdict.RECHEMARE, human=True, deadline=deadline, amount=x.amount)


# ---------------------------------------------------------------- 4. raspuns_reclamatie

_LETTER_OUTCOME = {
    Verdict.RAMBURSEAZA: "rambursarea sumei, în termenul T+1",
    Verdict.RAMBURSEAZA_CU_APROBARE: "rambursarea sumei, aprobată de un om în termenul T+1",
    Verdict.RESPINGE_TARDIV: "respingerea motivată: notificarea a venit după 13 luni (art. 169)",
    Verdict.NU_SE_APLICA_T1: "traseul potrivit cererii (sprijin, dispută de schemă sau corecție), nu rambursarea T+1",
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
            d.next.append("doar dacă întârzierea e independentă de bancă: răspuns intermediar motivat (CMP-02)")
    d.next += ["răspunde pe suport durabil la fiecare punct din reclamație (CMP-01)",
               "include căile de sesizare: ANPC, ANAF, BNR și CSALB (CMP-03)",
               "scrisoarea pleacă doar după filtrul zidului și aprobarea omului"]
    gaps = False
    if "DSP-53" in F:
        d.use("DSP-53")
        d.missing.append("dovada contactării comerciantului")
        gaps = True
    f32 = F.get("DSP-32")
    if f32 is not None and f32.outcome == "DSP_CARDHOLDER_PROOF_MISSING":
        d.use("DSP-32")
        d.missing.append("scrisoarea semnată a titularului")
        gaps = True
    if "DSP-57" in F:
        d.use("DSP-57")
    if refund.decision == Verdict.EXCEPTIE_FRAUDA_CLIENT or x.hold_signal:
        d.rule("URM-02")
        d.line("Scrisoarea rămâne neutră: nu menționează suspiciunea, analiza sau o raportare (interdicția de "
               "tipping-off).")
    if refund.decision == Verdict.EXCEPTIE_FRAUDA_CLIENT or gaps:
        verdict = Verdict.INFORMATII_SUPLIMENTARE
        if gaps:
            d.next.insert(0, "cere clientului dovezile lipsă, cu termen; disputa pornește după primirea lor")
    else:
        verdict = refund.decision
        d.line(f"Scrisoarea comunică {_LETTER_OUTCOME.get(refund.decision, 'decizia luată')}.", ["dispute_type"])
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
        dec = apply_human_review(dec, x, reason="Scorul M2 e doar un semnal pentru om: decizia o ia omul, nu scorul "
                                               "(GDPR art. 22, CJUE SCHUFA).")
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
                               "Deciziile defavorabile și cele în care apare scorul M2 le semnează un om (GDPR art. 22).",
                               env))
        specs["DP-02"] = get_rule("DP-02")
    if "DP-03" in guards:
        hits.append(_guard_hit("DP-03", "DP_EXPLANATION_MISSING", "O decizie nu avea regulă sau explicație.", env))
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
    next_rts = (["analistul decide depunerea STR-ului la ONPCSB (art. 6)"]
                + ([f"tranzacția legată rămâne în așteptare până la {fmt_dt(hold_until)}"] if hold_until else [])
                if proposed else ["pista rămâne în monitorizare; analistul poate decide altfel"])
    rts_lines = lines(rts_rules) or [RationaleLine(text="Nu există indicii obiective peste praguri și nici o "
                                                       "suspiciune confirmată: pista rămâne în monitorizare.")]
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
    next_lead = [f"trimite raportul de prag ({findings[r].outcome}) la ONPCSB" for r in ("AML-07", "AML-08")
                 if r in findings]
    if profiling:
        next_lead.insert(0, "recalculează scorul doar din fapte obiective (fără trăsături personale)")
    lead = Decision(case_id=ctx.lead_id, question=Question.PISTA_AML,
                    decision=Verdict.INFORMATII_SUPLIMENTARE if profiling else Verdict.MONITORIZARE,
                    rule_ids=[*lead_rules, "URM-02"],
                    rationale=[*lines(lead_rules), *lines(["URM-02"])],
                    next_actions=next_lead or ["monitorizează conturile legate; decide analistul"],
                    requires_human=profiling, decided_by="rules+human" if profiling else "rules")
    deadlines = _deadlines(findings.values())
    constraints = ["tipping_off_ban: spre zona client pleacă doar semnalul HOLD (URM-02)",
                   "doar_fapte_obiective: fără trăsături personale în scoruri (URM-01)"]
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
    """Fișa unei reguli: metadatele, descrierea în română, parametrii (cu marcajul lor) și aliasurile.
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
        entry["note"] = (f"{rule_id} (docs/context/14) aplică în fluxul de dispute regula {spec.rule_id} "
                         f"({spec.source}).")
    return entry


__all__ = ["ENGINE_VERSION", "QUESTIONS", "catalog", "evaluate", "evaluate_aml", "explain", "get_params",
           "set_params"]
