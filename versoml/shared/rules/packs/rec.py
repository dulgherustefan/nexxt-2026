"""Pachetul REC (EXTENSIE): rechemarea transferurilor. Nu există în catalogul docs/context.

Sursa e docs/05 §3–4 (corecturile verificate și tabelul de reguli), care trimite la ghidurile EPC privind
codurile de motiv (EPC135-18 pentru SCT, EPC059-18 pentru SCT Inst): camt.056 cu motivul FRAD pentru EUR,
iar la SCT Inst banca beneficiarului răspunde în 15 zile bancare [S]. Procedura RON (SENT, Plăți Instant)
nu e publică [U]. Totul e ciornă: trimiterea o aprobă un om.
"""

from __future__ import annotations

from versoml.contracts import Channel, Confidence, Deadline, DisputeType, Question

from ..calendar_ro import add_banking_days, add_months, banking_calendar, end_of_day, local_date, to_local
from ..context import RuleContextExt
from ..facts import Env, fmt_d, iban_bank_code
from ..registry import Finding, rule

S, U = Confidence.S, Confidence.U
SRC = "docs/05 §3–4; ghidurile EPC EPC135-18 și EPC059-18 (absent din docs/context)"
Q_ESCROC = Question.RECUPERARE_ESCROC
SCT_INST_RECALL_ANSWER_BANKING_DAYS = 15     # docs/05 §3 [S]


def recall_applicable(x: RuleContextExt) -> bool:
    return (x.channel in (Channel.TRANSFER, Channel.TRANSFER_INSTANT)
            and x.dispute_type in (DisputeType.NEAUTORIZATA, DisputeType.APP) and not x.credit_fraud)


def internal_beneficiary(x: RuleContextExt, env: Env) -> str | None:
    code = iban_bank_code(x.beneficiary_iban)
    return code if code and code in set(env.p("same_bank_codes")) else None


def _banking_cal(env: Env):
    kind = env.p("banking_calendar")
    return env.cal if kind == "ro" else banking_calendar(kind)


@rule("REC-01", title="Rechemarea unui transfer SEPA în EUR: camt.056 cu motivul FRAD",
      basis="ghidurile EPC privind codurile de motiv (EPC135-18, EPC059-18); docs/05 §3", confidence=S, pack="REC",
      source=SRC, questions=(Q_ESCROC,), tests=("REC-T1",))
def rec_01_sepa_recall(x: RuleContextExt, env: Env) -> Finding | None:
    """Pentru un transfer în EUR, rechemarea se cere băncii beneficiarului cu mesajul ISO 20022 camt.056 și
    motivul FRAD. Mesajul e ciornă; îl trimite un om."""
    if not recall_applicable(x) or internal_beneficiary(x, env) or x.amount.currency.upper() != "EUR":
        return None
    kind = "SCT Inst" if x.channel == Channel.TRANSFER_INSTANT else "SCT"
    return Finding("REC-01", "camt056_FRAD",
                   f"Transfer SEPA ({kind}) în EUR: rechemarea se cere băncii beneficiarului cu mesajul camt.056, "
                   "motivul FRAD (ciornă; o trimite un om).", ("channel", "amount", "beneficiary_iban"),
                   data={"kind": "camt.056", "reason": "FRAD"})


@rule("REC-02", title="La SCT Inst, banca beneficiarului răspunde la rechemare în 15 zile bancare",
      basis="ghidurile EPC (EPC059-18); docs/05 §3", confidence=S, pack="REC", source=SRC, questions=(Q_ESCROC,),
      params=("sct_recall_answer_banking_days", "banking_calendar", "bank_closure_days"), tests=("REC-T2",))
def rec_02_answer_deadline(x: RuleContextExt, env: Env) -> Finding | None:
    """Temporizatorul de răspuns la rechemare: 15 zile bancare la SCT Inst [S]. Pentru SCT non-instant valoarea
    e parametru [U]. Zilele bancare = zilele lucrătoare RO, implicit (calendarul TARGET2 nu e în docs/context).
    Ancora e trimiterea rechemării, estimată la momentul deciziei."""
    if not recall_applicable(x) or internal_beneficiary(x, env) or x.amount.currency.upper() != "EUR":
        return None
    instant = x.channel == Channel.TRANSFER_INSTANT
    days = SCT_INST_RECALL_ANSWER_BANKING_DAYS if instant else env.p("sct_recall_answer_banking_days")
    sent = to_local(x.now)
    due = end_of_day(add_banking_days(sent.date(), days, cal=_banking_cal(env)))
    note = "" if instant else " (pentru SCT non-instant termenul e presupus, [U])"
    return Finding("REC-02", "temporizator_rechemare",
                   f"Banca beneficiarului răspunde la rechemare în {days} zile bancare{note}: până la {fmt_d(due)}, "
                   "socotit de la trimiterea rechemării (estimat: acum).", ("channel",), data={"due": due},
                   deadlines=(Deadline(rule_id="REC-02", name=f"Răspunsul la rechemare ({days} zile bancare)",
                                       due_at=due, basis="ghidurile EPC; docs/05 §3", business_days=True),))


@rule("REC-03", title="Beneficiar la aceeași bancă: blocare internă și cerere de returnare",
      basis="propunere VersoML (procedură internă; docs/05 §3)", confidence=U, pack="REC", source=SRC,
      questions=(Q_ESCROC,), params=("same_bank_codes",), tests=("REC-T3",))
def rec_03_internal_recall(x: RuleContextExt, env: Env) -> Finding | None:
    """Dacă IBAN-ul beneficiarului e la Banca Demo (cod BDEM, parametru [U]), suma se blochează intern și se
    cere returnarea, fără mesaj interbancar. Blocarea o aprobă un om."""
    code = internal_beneficiary(x, env) if recall_applicable(x) else None
    if not code:
        return None
    return Finding("REC-03", "rechemare_interna",
                   f"Beneficiarul are cont tot la Banca Demo (cod {code}): se propune blocarea internă a sumei și "
                   "cererea de returnare către Operațiuni, fără mesaj interbancar.", ("beneficiary_iban",),
                   data={"kind": "interna"})


@rule("REC-04", title="Transfer în RON către altă bancă: cerere de rechemare, procedură de confirmat",
      basis="docs/05 §3 (procedura SENT și Plăți Instant nu e publică)", confidence=U, pack="REC", source=SRC,
      questions=(Q_ESCROC,), params=("ron_recall_answer_banking_days", "banking_calendar"), tests=("REC-T4",))
def rec_04_ron_recall(x: RuleContextExt, env: Env) -> Finding | None:
    """Pentru RON (SENT, Plăți Instant Transfond) procedura de rechemare nu e publică: agentul pregătește cererea
    către banca beneficiarului, iar termenul de răspuns e parametru [U], gol implicit."""
    if not recall_applicable(x) or internal_beneficiary(x, env) or x.amount.currency.upper() == "EUR":
        return None
    days = env.p("ron_recall_answer_banking_days")
    if x.beneficiary_iban:
        text = (f"Transfer în {x.amount.currency} către altă bancă: se pregătește cererea de rechemare către banca "
                "beneficiarului; procedura (SENT, Plăți Instant) nu e publică și se confirmă cu mentorii [U].")
    else:
        text = (f"Transfer în {x.amount.currency}: IBAN-ul beneficiarului nu e în contextul de reguli. Dacă e la altă "
                "bancă, se pregătește cererea de rechemare (procedura SENT / Plăți Instant nu e publică, [U]); dacă e "
                "la Banca Demo, se aplică blocarea internă (REC-03).")
    deadlines: tuple[Deadline, ...] = ()
    if days:
        due = end_of_day(add_banking_days(to_local(x.now).date(), days, cal=_banking_cal(env)))
        text += f" Termen de răspuns configurat: {days} zile bancare, până la {fmt_d(due)} [U]."
        deadlines = (Deadline(rule_id="REC-04", name=f"Răspunsul la rechemarea în RON ({days} zile bancare, [U])",
                              due_at=due, basis="parametru [U]", business_days=True),)
    return Finding("REC-04", "rechemare_ron", text, ("channel", "amount", "beneficiary_iban"),
                   data={"kind": "rechemare_ron"}, deadlines=deadlines)


@rule("REC-05", title="Rechemarea pe motiv de fraudă se propune doar în fereastra de la execuție",
      basis="propunere VersoML; termenul nu e în docs/context", confidence=U, pack="REC", source=SRC,
      questions=(Q_ESCROC,), params=("recall_window_months",), exceptions=("REC_WINDOW_EXPIRED",),
      tests=("reclamatie_tardiva",))
def rec_05_recall_window(x: RuleContextExt, env: Env) -> Finding | None:
    """După fereastra configurată (13 luni, [U]) rechemarea nu se mai propune automat; un om poate încerca."""
    if not recall_applicable(x):
        return None
    months = env.p("recall_window_months")
    limit = add_months(local_date(x.executed_at), months)
    if local_date(x.now) > limit:
        return Finding("REC-05", "REC_WINDOW_EXPIRED",
                       f"Au trecut peste {months} luni de la execuție (limita: {fmt_d(limit)}, parametru [U]): "
                       "rechemarea nu se mai propune automat.", ("executed_at",), data={"limit": limit})
    return None


__all__ = ["internal_beneficiary", "recall_applicable"]
