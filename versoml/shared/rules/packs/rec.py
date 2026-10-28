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
SRC = "docs/05 §3–4; EPC guidance EPC135-18 and EPC059-18 (not in docs/context)"
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


@rule("REC-01", title="Recall of a SEPA transfer in EUR: camt.056 with reason FRAD",
      basis="EPC guidance on reason codes (EPC135-18, EPC059-18); docs/05 §3", confidence=S, pack="REC",
      source=SRC, questions=(Q_ESCROC,), tests=("REC-T1",))
def rec_01_sepa_recall(x: RuleContextExt, env: Env) -> Finding | None:
    """For a transfer in EUR, the bank asks the beneficiary's bank for a recall with the ISO 20022 camt.056
    message and reason FRAD. The message is a draft. A human sends it."""
    if not recall_applicable(x) or internal_beneficiary(x, env) or x.amount.currency.upper() != "EUR":
        return None
    kind = "SCT Inst" if x.channel == Channel.TRANSFER_INSTANT else "SCT"
    return Finding("REC-01", "camt056_FRAD",
                   f"SEPA transfer ({kind}) in EUR. The bank asks the beneficiary's bank for a recall with a camt.056 "
                   "message, reason FRAD (draft; a human sends it).", ("channel", "amount", "beneficiary_iban"),
                   data={"kind": "camt.056", "reason": "FRAD"})


@rule("REC-02", title="For SCT Inst, the beneficiary's bank answers a recall within 15 banking days",
      basis="EPC guidance on SCT Inst reason codes (EPC059-18); docs/05 §3", confidence=S, pack="REC", source=SRC,
      questions=(Q_ESCROC,), params=("sct_recall_answer_banking_days", "banking_calendar", "bank_closure_days"),
      tests=("REC-T2",))
def rec_02_answer_deadline(x: RuleContextExt, env: Env) -> Finding | None:
    """The recall answer timer: 15 banking days for SCT Inst [S]. For non-instant SCT, the value is a [U]
    parameter. By default, banking days are Romanian business days (the TARGET2 calendar is not in
    docs/context). The clock starts when the recall is sent, estimated at the time of the decision."""
    if not recall_applicable(x) or internal_beneficiary(x, env) or x.amount.currency.upper() != "EUR":
        return None
    instant = x.channel == Channel.TRANSFER_INSTANT
    days = SCT_INST_RECALL_ANSWER_BANKING_DAYS if instant else env.p("sct_recall_answer_banking_days")
    sent = to_local(x.now)
    due = end_of_day(add_banking_days(sent.date(), days, cal=_banking_cal(env)))
    note = "" if instant else " (for non-instant SEPA transfers this deadline is an assumption)"
    return Finding("REC-02", "temporizator_rechemare",
                   f"The beneficiary's bank answers the recall within {days} banking days{note}, by {fmt_d(due)}. "
                   "The count starts when the recall is sent (estimated: now).", ("channel",), data={"due": due},
                   deadlines=(Deadline(rule_id="REC-02", name=f"Recall answer ({days} banking days)",
                                       due_at=due, basis="EPC guidance; docs/05 §3", business_days=True),))


@rule("REC-03", title="Beneficiary at the same bank: internal block and return request",
      basis="VersoML proposal (internal procedure; docs/05 §3)", confidence=U, pack="REC", source=SRC,
      questions=(Q_ESCROC,), params=("same_bank_codes",), tests=("REC-T3",))
def rec_03_internal_recall(x: RuleContextExt, env: Env) -> Finding | None:
    """If the beneficiary IBAN is at Banca Demo (code BDEM, a [U] parameter), the bank blocks the amount
    internally and requests its return, with no interbank message. A human approves the block."""
    code = internal_beneficiary(x, env) if recall_applicable(x) else None
    if not code:
        return None
    return Finding("REC-03", "rechemare_interna",
                   f"The beneficiary also banks with Banca Demo (code {code}). The engine proposes an internal block "
                   "on the amount and a return request to Operations, with no interbank message.",
                   ("beneficiary_iban",), data={"kind": "interna"})


@rule("REC-04", title="RON transfer to another bank: recall request, procedure to be confirmed",
      basis="docs/05 §3 (the SENT and Plăți Instant procedure is not public)", confidence=U, pack="REC", source=SRC,
      questions=(Q_ESCROC,), params=("ron_recall_answer_banking_days", "banking_calendar"), tests=("REC-T4",))
def rec_04_ron_recall(x: RuleContextExt, env: Env) -> Finding | None:
    """For RON (SENT, Transfond Plăți Instant), the recall procedure is not public. The agent prepares the
    request to the beneficiary's bank. The answer deadline is a [U] parameter, empty by default."""
    if not recall_applicable(x) or internal_beneficiary(x, env) or x.amount.currency.upper() == "EUR":
        return None
    days = env.p("ron_recall_answer_banking_days")
    if x.beneficiary_iban:
        text = (f"{x.amount.currency} transfer to another bank. The engine prepares the recall request to the "
                "beneficiary's bank. The procedure (SENT, Plăți Instant) is not public and must be confirmed with "
                "the mentors [U].")
    else:
        text = (f"{x.amount.currency} transfer. The beneficiary IBAN is not in the rules context. If it is at another "
                "bank, the engine prepares a recall request (the SENT / Plăți Instant procedure is not public, so this is an assumption). "
                "If it is at Banca Demo, the internal block applies (REC-03).")
    deadlines: tuple[Deadline, ...] = ()
    if days:
        due = end_of_day(add_banking_days(to_local(x.now).date(), days, cal=_banking_cal(env)))
        text += f" Configured answer deadline: {days} banking days, by {fmt_d(due)} (an assumption)."
        deadlines = (Deadline(rule_id="REC-04", name=f"RON recall answer ({days} banking days, assumed)",
                              due_at=due, basis="bank setting (assumption)", business_days=True),)
    return Finding("REC-04", "rechemare_ron", text, ("channel", "amount", "beneficiary_iban"),
                   data={"kind": "rechemare_ron"}, deadlines=deadlines)


@rule("REC-05", title="A fraud recall is proposed only within the window after execution",
      basis="VersoML proposal; the deadline is not in docs/context", confidence=U, pack="REC", source=SRC,
      questions=(Q_ESCROC,), params=("recall_window_months",), exceptions=("REC_WINDOW_EXPIRED",),
      tests=("reclamatie_tardiva",))
def rec_05_recall_window(x: RuleContextExt, env: Env) -> Finding | None:
    """After the configured window (13 months, [U]), the engine no longer proposes a recall automatically. A
    human can still try."""
    if not recall_applicable(x):
        return None
    months = env.p("recall_window_months")
    limit = add_months(local_date(x.executed_at), months)
    if local_date(x.now) > limit:
        return Finding("REC-05", "REC_WINDOW_EXPIRED",
                       f"More than {months} months have passed since execution (limit: {fmt_d(limit)}, [U] "
                       "parameter). The engine no longer proposes a recall automatically.", ("executed_at",),
                       data={"limit": limit})
    return None


__all__ = ["internal_beneficiary", "recall_applicable"]
