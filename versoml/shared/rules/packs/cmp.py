"""Pachetul CMP: termenele și conținutul răspunsului la reclamație (docs/context/11 §2.6).

Ceasul pornește la primirea reclamației (`complaint_received_at`, implicit `notified_at`), nu la data poștei;
ziua primirii nu se numără (docs/context/11 §3, „de confirmat”).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta

from versoml.contracts import Confidence, Deadline, Question, RuleHit

from ..calendar_ro import add_business_days, business_days_between, end_of_day, to_local
from ..context import RuleContextExt
from ..facts import Env, fmt_d, fmt_dt
from ..registry import Finding, get_rule, normalize_ro, rule

P, S = Confidence.P, Confidence.S
SRC = "docs/context/11 §2.6"
Q_ANSWER = Question.RASPUNS_RECLAMATIE


def complaint_received(x: RuleContextExt) -> datetime:
    return to_local(x.complaint_received_at or x.notified_at)


def _received_field(x: RuleContextExt) -> str:
    return "complaint_received_at" if x.complaint_received_at else "notified_at"


def payment_complaint_deadlines(received: datetime | date, env: Env) -> tuple[datetime, datetime]:
    """Termenul obișnuit (15) și cel maxim (35 de zile lucrătoare), la sfârșitul zilei."""
    d = to_local(received).date() if isinstance(received, datetime) else received
    return (end_of_day(add_business_days(d, 15, env.cal)), end_of_day(add_business_days(d, 35, env.cal)))


@rule("CMP-01", title="Răspuns la toate punctele, în cel mult 15 zile lucrătoare de la primire",
      basis="Legea 209/2019 art. 224", confidence=P, pack="CMP", source=SRC, questions=(Q_ANSWER,),
      params=("bank_closure_days", "complaint_alert_lead_business_days"),
      exceptions=("CMP_DEADLINE_RISK", "CMP_POINT_UNANSWERED"), aliases=("DSP-14",),
      tests=("TC-34", "DT-01", "DT-02", "DT-05", "DT-07", "DT-09"))
def cmp_01_answer_deadline(x: RuleContextExt, env: Env) -> Finding | None:
    """Reclamațiile privind serviciile de plată primesc răspuns pe hârtie sau pe alt suport durabil convenit,
    la toate punctele, în cel mult 15 zile lucrătoare de la primire (inclusiv la ghișeu sau prin poștă)."""
    if x.credit_fraud:
        return None
    received = complaint_received(x)
    due, _ = payment_complaint_deadlines(received, env)
    deadline = Deadline(rule_id="CMP-01", name="Răspuns la reclamație (15 zile lucrătoare)", due_at=due,
                        basis="Legea 209/2019 art. 224", business_days=True)
    fields = (_received_field(x),)
    now = to_local(x.now)
    left = business_days_between(now, due, env.cal)
    data = {"due": due, "received": received, "business_days_left": left}
    if x.final_answer_sent_at is not None:
        return Finding("CMP-01", "raspuns_trimis", f"Răspunsul final a plecat la {fmt_dt(x.final_answer_sent_at)}.",
                       ("final_answer_sent_at",), data=data, deadlines=(deadline,))
    if now > due:
        return Finding("CMP-01", "CMP_DEADLINE_RISK",
                       f"Termenul de 15 zile lucrătoare ({fmt_d(due)}) a trecut fără răspuns final.", fields,
                       data=data, deadlines=(deadline,))
    if left <= env.p("complaint_alert_lead_business_days"):
        return Finding("CMP-01", "CMP_DEADLINE_RISK",
                       f"Mai sunt {left} zile lucrătoare până la termenul de răspuns ({fmt_d(due)}).", fields,
                       data=data, deadlines=(deadline,))
    return Finding("CMP-01", "in_termen",
                   f"Reclamația a fost primită la {fmt_dt(received)}: răspunsul final, pe suport durabil și la fiecare "
                   f"punct, pleacă până la {fmt_d(due)} (15 zile lucrătoare, art. 224).", fields, data=data,
                   deadlines=(deadline,))


@rule("CMP-02", title="Situații excepționale: răspuns intermediar motivat, final în cel mult 35 de zile lucrătoare",
      basis="Legea 209/2019 art. 224", confidence=P, pack="CMP", source=SRC, questions=(Q_ANSWER,),
      params=("bank_closure_days", "complaint_alert_lead_business_days"),
      exceptions=("CMP_HOLDING_REPLY_REQUIRED",), tests=("TC-34", "EX-22", "DT-02"))
def cmp_02_extension(x: RuleContextExt, env: Env) -> Finding | None:
    """Doar în situații excepționale, independente de bancă: răspuns intermediar cu motivele întârzierii și data
    răspunsului final, care nu poate depăși 35 de zile lucrătoare de la primire. Un motiv aflat în controlul
    băncii nu permite prelungirea."""
    if x.credit_fraud or x.final_answer_sent_at is not None:
        return None
    received = complaint_received(x)
    due15, due35 = payment_complaint_deadlines(received, env)
    deadline = Deadline(rule_id="CMP-02", name="Termen maxim de răspuns, cu răspuns intermediar (35 zile lucrătoare)",
                        due_at=due35, basis="Legea 209/2019 art. 224", business_days=True)
    if x.holding_reply_sent_at is not None:
        if x.delay_reason_external is True:
            return Finding("CMP-02", "prelungire_valida",
                           f"Răspunsul intermediar a plecat la {fmt_dt(x.holding_reply_sent_at)}, cu un motiv independent "
                           f"de bancă: răspunsul final poate pleca până la {fmt_d(due35)}.",
                           ("holding_reply_sent_at", "delay_reason_external"),
                           data={"effective_due": due35}, deadlines=(deadline,))
        return Finding("CMP-02", "prelungire_nepermisa",
                       "Motivul întârzierii nu e independent de bancă: prelungirea la 35 de zile nu e permisă, iar "
                       f"termenul rămâne {fmt_d(due15)}.", ("holding_reply_sent_at", "delay_reason_external"),
                       data={"effective_due": due15}, deadlines=(deadline,))
    now = to_local(x.now)
    left = business_days_between(now, due15, env.cal)
    if now > due15 or left <= env.p("complaint_alert_lead_business_days"):
        return Finding("CMP-02", "CMP_HOLDING_REPLY_REQUIRED",
                       "Răspunsul final nu a plecat și nu există răspuns intermediar: doar în situații excepționale, "
                       "independente de bancă, se trimite un răspuns intermediar motivat, cu data finală de cel mult "
                       f"{fmt_d(due35)}.", (_received_field(x),), data={"effective_due": due15}, deadlines=(deadline,))
    return Finding("CMP-02", "termen_maxim",
                   f"Doar în situații excepționale, independente de bancă, răspunsul final poate pleca până la "
                   f"{fmt_d(due35)}, cu un răspuns intermediar motivat.", (_received_field(x),),
                   data={"effective_due": due15}, deadlines=(deadline,))


@rule("CMP-03", title="Răspunsul final indică ANPC, ANAF, BNR și entitatea SAL competentă",
      basis="Legea 209/2019 art. 225 și 185 alin. (2)", confidence=P, pack="CMP", source=SRC, questions=(Q_ANSWER,),
      exceptions=("CMP_ADR_BLOCK_MISSING",), aliases=("DSP-15",), tests=("TC-36", "DT-18"))
def cmp_03_adr_block(x: RuleContextExt, env: Env) -> Finding | None:
    """Banca informează clar despre dreptul de a sesiza ANPC, ANAF, BNR și entitatea SAL (CSALB). Blocul e
    obligatoriu în orice răspuns final; fără el, răspunsul nu pleacă."""
    if x.credit_fraud:
        return None
    return Finding("CMP-03", "bloc_obligatoriu",
                   "Răspunsul final include căile de sesizare: ANPC, ANAF, BNR și entitatea de soluționare "
                   "alternativă a litigiilor (CSALB); fără ele nu pleacă.")


def credit_complaint_deadline(registered_on: date) -> date:
    """OUG 50/2010 art. 42 [S]: 30 de zile de la înregistrare (zile calendaristice: inferență din note)."""
    return registered_on + timedelta(days=30)


@rule("CMP-04", title="Reclamația la creditul de consum: răspuns în cel mult 30 de zile de la înregistrare",
      basis="OUG 50/2010 art. 42", confidence=S, pack="CMP", source=SRC, questions=(Q_ANSWER,),
      exceptions=("CMP_DEADLINE_RISK",), tests=("TC-35", "DT-17"))
def cmp_04_credit_complaint(x: RuleContextExt, env: Env) -> Finding | None:
    """Reclamațiile la creditul de consum se înregistrează și primesc răspuns în cel mult 30 de zile de la
    înregistrare (zile calendaristice: inferență din note). Se aplică la creditul luat pe numele victimei."""
    if not x.credit_fraud:
        return None
    registered = complaint_received(x).date()
    due = credit_complaint_deadline(registered)
    return Finding("CMP-04", "termen_credit",
                   f"Reclamația de credit primește răspuns până la {fmt_d(due)} (30 de zile de la înregistrare).",
                   (_received_field(x),), data={"due": end_of_day(due)},
                   deadlines=(Deadline(rule_id="CMP-04", name="Răspuns la reclamația de credit (30 de zile)",
                                       due_at=end_of_day(due), basis="OUG 50/2010 art. 42", business_days=False),))


# ---------------------------------------------------------------- verificarea scrisorii


ADR_TERMS: dict[str, tuple[str, ...]] = {
    "ANPC": ("anpc", "protecția consumatorilor", "protectia consumatorilor"),
    "ANAF": ("anaf", "administrare fiscală", "administrare fiscala"),
    "BNR": ("bnr", "banca națională", "banca nationala"),
    "SAL (CSALB)": ("csalb", "soluționare alternativă", "solutionare alternativa"),
}


def _hit(rule_id: str, outcome: str, explanation: str) -> RuleHit:
    spec = get_rule(rule_id)
    return RuleHit(rule_id=spec.rule_id, version=spec.version, title=spec.title, basis=spec.basis,
                   confidence=spec.confidence, outcome=outcome, explanation=explanation)


def check_adr_block(body: str) -> RuleHit:
    """CMP-03 pe o ciornă de răspuns final: blocul ANPC / ANAF / BNR / SAL trebuie să existe."""
    text = normalize_ro(body).lower()
    missing = [name for name, terms in ADR_TERMS.items() if not any(t in text for t in terms)]
    if missing:
        return _hit("CMP-03", "CMP_ADR_BLOCK_MISSING",
                    f"Răspunsul final nu poate pleca: lipsesc căile de sesizare {', '.join(missing)} (art. 225).")
    return _hit("CMP-03", "bloc_prezent", "Răspunsul indică ANPC, ANAF, BNR și CSALB.")


def check_points_answered(points: Sequence[str], answered: Sequence[str]) -> RuleHit:
    """CMP-01: scrisoarea răspunde la fiecare punct din reclamație (`LetterDraft.points_answered`)."""
    done = {normalize_ro(a).strip().lower() for a in answered}
    missing = [p for p in points if normalize_ro(p).strip().lower() not in done]
    if missing:
        listed = "; ".join(f"„{p}”" for p in missing)
        return _hit("CMP-01", "CMP_POINT_UNANSWERED", f"Scrisoarea nu răspunde la {len(missing)} puncte: {listed}.")
    return _hit("CMP-01", "toate_punctele", "Scrisoarea răspunde la toate punctele din reclamație.")


def check_complaint_letter(body: str, points: Sequence[str] = (), answered: Sequence[str] = ()) -> list[RuleHit]:
    """Verificările CMP pe o ciornă: punctele (CMP-01) și căile de sesizare (CMP-03). PII și tipping-off le
    verifică filtrul zidului (`versoml.wall`)."""
    return [check_points_answered(points, answered), check_adr_block(body)]


__all__ = ["ADR_TERMS", "check_adr_block", "check_complaint_letter", "check_points_answered",
           "complaint_received", "credit_complaint_deadline", "payment_complaint_deadlines"]
