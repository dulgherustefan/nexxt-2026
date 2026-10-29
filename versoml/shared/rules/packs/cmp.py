"""Pachetul CMP: termenele și conținutul răspunsului la reclamație (docs/context/11 §2.6).

Ceasul pornește la primirea reclamației (`complaint_received_at`, implicit `notified_at`), nu la data poștei;
ziua primirii nu se numără (docs/context/11 §3, „de confirmat”).
"""

from __future__ import annotations

import re
import unicodedata
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


@rule("CMP-01", title="Answer every point within 15 business days of receipt",
      basis="Law 209/2019, art. 224", confidence=P, pack="CMP", source=SRC, questions=(Q_ANSWER,),
      params=("bank_closure_days", "complaint_alert_lead_business_days"),
      exceptions=("CMP_DEADLINE_RISK", "CMP_POINT_UNANSWERED"), aliases=("DSP-14",),
      tests=("TC-34", "DT-01", "DT-02", "DT-05", "DT-07", "DT-09"))
def cmp_01_answer_deadline(x: RuleContextExt, env: Env) -> Finding | None:
    """Complaints about payment services get an answer on paper or another agreed durable medium, covering
    every point, within 15 business days of receipt (including complaints made at a branch or by post)."""
    if x.credit_fraud:
        return None
    received = complaint_received(x)
    due, _ = payment_complaint_deadlines(received, env)
    deadline = Deadline(rule_id="CMP-01", name="Complaint answer (15 business days)", due_at=due,
                        basis="Law 209/2019, art. 224", business_days=True)
    fields = (_received_field(x),)
    now = to_local(x.now)
    left = business_days_between(now, due, env.cal)
    data = {"due": due, "received": received, "business_days_left": left}
    if x.final_answer_sent_at is not None:
        return Finding("CMP-01", "raspuns_trimis", f"The final answer went out on {fmt_dt(x.final_answer_sent_at)}.",
                       ("final_answer_sent_at",), data=data, deadlines=(deadline,))
    if now > due:
        return Finding("CMP-01", "CMP_DEADLINE_RISK",
                       f"The 15-business-day deadline ({fmt_d(due)}) passed with no final answer.", fields,
                       data=data, deadlines=(deadline,))
    if left <= env.p("complaint_alert_lead_business_days"):
        when = "today" if left == 0 else f"{left} business day{'' if left == 1 else 's'} away"
        return Finding("CMP-01", "CMP_DEADLINE_RISK",
                       f"The answer deadline ({fmt_d(due)}) is {when}.", fields,
                       data=data, deadlines=(deadline,))
    return Finding("CMP-01", "in_termen",
                   f"The bank received the complaint on {fmt_dt(received)}. The final answer, on a durable medium and "
                   f"covering every point, goes out by {fmt_d(due)} (15 business days, Law 209/2019, art. 224).",
                   fields, data=data, deadlines=(deadline,))


@rule("CMP-02", title="Exceptional cases: a reasoned holding reply, and a final answer within 35 business days",
      basis="Law 209/2019, art. 224", confidence=P, pack="CMP", source=SRC, questions=(Q_ANSWER,),
      params=("bank_closure_days", "complaint_alert_lead_business_days"),
      exceptions=("CMP_HOLDING_REPLY_REQUIRED",), tests=("TC-34", "EX-22", "DT-02"))
def cmp_02_extension(x: RuleContextExt, env: Env) -> Finding | None:
    """Only in exceptional cases outside the bank's control: a holding reply with the reasons for the delay and
    the date of the final answer, which cannot be later than 35 business days from receipt. A reason within
    the bank's control does not allow the extension."""
    if x.credit_fraud or x.final_answer_sent_at is not None:
        return None
    received = complaint_received(x)
    due15, due35 = payment_complaint_deadlines(received, env)
    deadline = Deadline(rule_id="CMP-02", name="Maximum answer deadline with a holding reply (35 business days)",
                        due_at=due35, basis="Law 209/2019, art. 224", business_days=True)
    if x.holding_reply_sent_at is not None:
        if x.delay_reason_external is True:
            return Finding("CMP-02", "prelungire_valida",
                           f"The holding reply went out on {fmt_dt(x.holding_reply_sent_at)}, with a reason outside "
                           f"the bank's control. The final answer can go out by {fmt_d(due35)}.",
                           ("holding_reply_sent_at", "delay_reason_external"),
                           data={"effective_due": due35}, deadlines=(deadline,))
        return Finding("CMP-02", "prelungire_nepermisa",
                       "The reason for the delay is within the bank's control. The extension to 35 business days is "
                       f"not allowed, and the deadline stays {fmt_d(due15)}.",
                       ("holding_reply_sent_at", "delay_reason_external"),
                       data={"effective_due": due15}, deadlines=(deadline,))
    now = to_local(x.now)
    left = business_days_between(now, due15, env.cal)
    if now > due15 or left <= env.p("complaint_alert_lead_business_days"):
        return Finding("CMP-02", "CMP_HOLDING_REPLY_REQUIRED",
                       "No final answer and no holding reply have gone out. Only in exceptional cases outside the "
                       "bank's control can it send a reasoned holding reply, with a final date no later than "
                       f"{fmt_d(due35)}.", (_received_field(x),), data={"effective_due": due15}, deadlines=(deadline,))
    return Finding("CMP-02", "termen_maxim",
                   "Only in exceptional cases outside the bank's control can the final answer go out as late as "
                   f"{fmt_d(due35)}, after a reasoned holding reply.", (_received_field(x),),
                   data={"effective_due": due15}, deadlines=(deadline,))


@rule("CMP-03", title="The final answer names ANPC, ANAF, BNR and the competent ADR entity",
      basis="Law 209/2019, art. 225 and art. 185(2)", confidence=P, pack="CMP", source=SRC, questions=(Q_ANSWER,),
      exceptions=("CMP_ADR_BLOCK_MISSING",), aliases=("DSP-15",), tests=("TC-36", "DT-18"))
def cmp_03_adr_block(x: RuleContextExt, env: Env) -> Finding | None:
    """The bank states clearly that the customer can complain to ANPC, ANAF, BNR and the ADR entity (CSALB).
    This block is required in every final answer. Without it, the answer does not go out."""
    if x.credit_fraud:
        return None
    return Finding("CMP-03", "bloc_obligatoriu",
                   "The final answer lists the external complaint routes: ANPC, ANAF, BNR and the alternative "
                   "dispute resolution entity (CSALB). Without them, it does not go out.")


def credit_complaint_deadline(registered_on: date) -> date:
    """OUG 50/2010 art. 42 [S]: 30 de zile de la înregistrare (zile calendaristice: inferență din note)."""
    return registered_on + timedelta(days=30)


@rule("CMP-04", title="Consumer credit complaint: answer within 30 days of registration",
      basis="GEO 50/2010, art. 42", confidence=S, pack="CMP", source=SRC, questions=(Q_ANSWER,),
      exceptions=("CMP_DEADLINE_RISK",), tests=("TC-35", "DT-17"))
def cmp_04_credit_complaint(x: RuleContextExt, env: Env) -> Finding | None:
    """Consumer credit complaints are registered and answered within 30 days of registration (calendar days,
    an inference from the notes). This applies to a loan taken out in the victim's name."""
    if not x.credit_fraud:
        return None
    registered = complaint_received(x).date()
    due = credit_complaint_deadline(registered)
    return Finding("CMP-04", "termen_credit",
                   f"The credit complaint gets an answer by {fmt_d(due)} (30 days from registration).",
                   (_received_field(x),), data={"due": end_of_day(due)},
                   deadlines=(Deadline(rule_id="CMP-04", name="Credit complaint answer (30 days)",
                                       due_at=end_of_day(due), basis="GEO 50/2010, art. 42", business_days=False),))


# ---------------------------------------------------------------- verificarea scrisorii


# Termenii se caută în română și în engleză (scrisorile pot fi în oricare dintre limbi).
ADR_TERMS: dict[str, tuple[str, ...]] = {
    "ANPC": ("anpc", "protecția consumatorilor", "protectia consumatorilor", "consumer protection"),
    "ANAF": ("anaf", "administrare fiscală", "administrare fiscala", "fiscal administration", "tax administration"),
    "BNR": ("bnr", "banca națională", "banca nationala", "national bank of romania"),
    "ADR (CSALB)": ("csalb", "soluționare alternativă", "solutionare alternativa", "alternative dispute resolution"),
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
                    f"The final answer cannot go out. It is missing these complaint routes: {', '.join(missing)} "
                    "(Law 209/2019, art. 225).")
    return _hit("CMP-03", "bloc_prezent", "The answer names ANPC, ANAF, BNR and CSALB.")


# CMP-01 on a draft is read from the letter itself, never from the writer's own list of the points it answered. Each
# point gets a topic from its words (Romanian or English); the letter answers it when it holds that topic's answer.
# A point with no known topic counts as answered when most of its content words come back in one paragraph.
# (topic, what the customer asks, what an answer to it says), on folded text: no diacritics, lower case
POINT_TOPICS: tuple[tuple[str, re.Pattern[str], re.Pattern[str]], ...] = tuple(
    (name, re.compile(asked), re.compile(answer)) for name, asked, answer in (
        ("why_not_stopped",
         r"\b(?:why|how\s+come|de\s+ce|cum\s+de)\b.*\b(?:block|stop|bloca|blocat|opri|oprit|permis|lasat|allow|let)\w*",
         (r"\b(?:did\s+not|didn'?t)\s+(?:stop|block)\b|\bnu\s+am\s+(?:oprit|blocat)\b|\bauthentication\s+steps\b"
          r"|\bpasii\s+(?:obisnuiti\s+)?de\s+autentificare\b")),
        ("own_card",
         r"\b(?:block|cancel|freeze|bloca\w*|anula\w*|inghet\w*)\b.{0,30}\b(?:my\s+card|the\s+card|cardul|card)\b",
         r"\bcard\w*\b.{0,60}\b(?:block|bloc)\w*|\b(?:block|bloc)\w*\b.{0,40}\bcard\w*"),
        ("payee",
         (r"\b(?:block|freeze|close|stop|bloca\w*|inghet\w*|inchide\w*|opri\w*)\b.{0,40}\b(?:accounts?|their|them|scammers?"
          r"|recipients?|payees?|cont(?:ul|urile)?|beneficiar\w*|escroc\w*|lor)\b"
          r"|\b(?:get|take|recover|recupera\w*|lua\w*)\b.{0,30}\b(?:from|de\s+la)\b.{0,20}\b(?:them|the\s+(?:scammer"
          r"|recipient|payee|seller|shop|merchant)|escroc\w*|beneficiar\w*|comerciant\w*|magazin\w*|vanzator\w*)"),
         (r"\b(?:bank|account)\s+that\s+received\b|\b(?:banc|cont)\w*\s+(?:care|ce)\s+a\s+primit\b|\brecall\b"
          r"|\bchargeback\b|\brechemar\w*|\bother\s+people'?s\s+accounts\b|\bconturile\s+altor\s+persoane\b"
          r"|\bmerchant'?s\s+bank\b|\bbanc\w*\s+comerciantului\b")),
        ("duplicate", r"\btwice\b|\bde\s+doua\s+ori\b|\bdubl\w*|\bduplicat\w*|\bdouble\b",
         r"\btwice\b|\bde\s+doua\s+ori\b|\bdubl\w*|\bduplicat\w*"),
        ("documents", r"\b(?:documents?|dovad\w*|dovez\w*|proof|evidence|extras\w*|cop(?:y|ie|ia)|documentel\w*)\b",
         (r"\bcopy\s+of\s+the\s+(?:information|documents)\b|\bcopie\s+a\s+(?:informatiilor|documentelor)\b"
          r"|\bdocument\w*\b")),
        ("police", r"\bpolice\b|\bpoliti\w*|\bplangere\s+penala\b|\bcriminal\s+complaint\b",
         r"\bpolice\b|\bpoliti\w*"),
        ("not_me",
         (r"\b(?:did\s*n[o']?t\s+(?:make|do|authori[sz]e|approve|send|order|buy)|never\s+(?:made|authori[sz]ed|approved)"
          r"|wasn'?t\s+me|not\s+me|don'?t\s+recogni[sz]e|nu\s+(?:eu\s+)?am\s+(?:facut|autorizat|efectuat|aprobat)"
          r"|nu\s+recunosc)\b"),
         (r"\brefund\w*|\bramburs\w*|\bcorrect\w*|\bcorect\w*|\bdid\s+not\s+(?:make|authori[sz]e)\b"
          r"|\bnu\s+ati\s+autorizat\b")),
        ("refund",
         (r"\b(?:refund\w*|reimburs\w*|money\s+back|my\s+money|return\w*\s+(?:my|the)\s+money|get\s+(?:it|the\s+money)"
          r"\s+back|cancel\w*\s+the\s+(?:transaction|payment|transfer)|ramburs\w*|restitu\w*|returna\w*|banii"
          r"|banii?\s+inapoi|anula\w*\s+(?:tranzacti|plat|transfer)\w*)"),
         r"\brefund\w*|\bramburs\w*|\brestitu\w*|\breturn\w*\b.{0,30}\bmoney\b|\bcorrect\w*|\bcorect\w*"),
    ))
_STOP = frozenset((
    "the", "and", "that", "this", "with", "from", "have", "your", "you", "our", "for", "was", "were", "are", "not",
    "but", "what", "when", "why", "how", "can", "could", "would", "should", "will", "about", "them", "they", "their",
    "there", "here", "into", "just", "also", "been", "please", "want", "need", "help", "give", "back", "make", "made",
    "some", "other", "than", "then", "very", "much", "more", "most", "such", "only", "over", "under", "after",
    "before", "because", "which", "these", "those", "sunt", "este", "care", "pentru", "prin", "dupa", "inainte",
    "acest", "aceasta", "aceste", "acel", "aceea", "dumneavoastra", "voastra", "noastra", "nostru", "mele", "vreau",
    "doresc", "fost", "avea", "aveti", "putem", "puteti", "poate", "daca", "cand", "unde", "nici", "foarte", "doar",
))


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", normalize_ro(text or ""))
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def point_topic(point: str) -> str | None:
    """The topic of a point of the complaint, from its words, or None."""
    text = _fold(point)
    return next((name for name, asked, _ in POINT_TOPICS if asked.search(text)), None)


def _stems(text: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[a-z]{4,}", _fold(text)) if w not in _STOP}


def point_answered(point: str, body: str, quote: str = "") -> bool:
    """Whether the letter answers the point: by its topic, or else by most of its words coming back in one paragraph
    of the letter. The quote (the customer's own words) helps when the point is in another language."""
    topic = point_topic(point) or (point_topic(quote) if quote else None)
    letter = _fold(body)
    if topic:
        answer = next(a for name, _, a in POINT_TOPICS if name == topic)
        return bool(answer.search(letter))
    paragraphs = [_stems(p) for p in re.split(r"\n\s*\n", body or "") if p.strip()]
    for words in (_stems(point), _stems(quote)):
        if len(words) >= 2 and any(len(words & p) / len(words) >= 0.6 for p in paragraphs):
            return True
    return False


def check_points_answered(points: Sequence[str], body: str, quotes: Sequence[str] = ()) -> RuleHit:
    """CMP-01: scrisoarea răspunde la fiecare punct din reclamație, citit din textul scrisorii."""
    quoted = list(quotes) + [""] * max(0, len(points) - len(quotes))
    missing = [p for p, q in zip(points, quoted) if not point_answered(p, body, q)]
    if missing:
        listed = "; ".join(f"“{p}”" for p in missing)
        n = len(missing)
        return _hit("CMP-01", "CMP_POINT_UNANSWERED",
                    f"The letter does not answer {n} point{'' if n == 1 else 's'}: {listed}.")
    return _hit("CMP-01", "toate_punctele", "The letter answers every point in the complaint.")


def check_complaint_letter(body: str, points: Sequence[str] = (), quotes: Sequence[str] = ()) -> list[RuleHit]:
    """Verificările CMP pe o ciornă: punctele (CMP-01) și căile de sesizare (CMP-03), ambele citite din scrisoare.
    PII și tipping-off le verifică filtrul zidului (`versoml.wall`)."""
    return [check_points_answered(points, body, quotes), check_adr_block(body)]


__all__ = ["ADR_TERMS", "POINT_TOPICS", "check_adr_block", "check_complaint_letter", "check_points_answered",
           "complaint_received", "credit_complaint_deadline", "payment_complaint_deadlines", "point_answered",
           "point_topic"]
